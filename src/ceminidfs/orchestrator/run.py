from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from ceminidfs.manifest import RunManifest, config_sha256, git_commit
from ceminidfs.orchestrator.validate import validate_lineups_csv

try:
    from ceminidfs.pipeline.project import project_week
except ImportError:  # pragma: no cover - defensive for partial installs
    project_week = None  # type: ignore[assignment]


STAGE_ORDER = ("fetch", "project", "normalize", "optimize")


def run_pipeline(
    season: int,
    week: int,
    salary_path: str | Path,
    stages: str | Iterable[str],
    config: Mapping[str, Any] | None = None,
) -> Path:
    """Run the requested CeminiDFS stages and write a JSON manifest."""
    cfg = dict(config or {})
    selected_stages = _parse_stages(stages)
    work_dir = Path(cfg.get("work_dir", Path("runs") / f"{season}_week_{week}"))
    work_dir.mkdir(parents=True, exist_ok=True)

    run_id = f"{season}_week_{week}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    manifest = RunManifest(
        run_id=run_id,
        git_commit=git_commit(),
        config_sha256=config_sha256(cfg),
        input_artifacts={
            "season": season,
            "week": week,
            "salary_path": str(Path(salary_path)),
            "stages": selected_stages,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": {},
        },
    )
    manifest_path = work_dir / "manifest.json"
    manifest.write(manifest_path)

    canonical_csv = Path(salary_path)
    normalized_csv = work_dir / "normalized_players.csv"
    lineups_csv = work_dir / "lineups.csv"
    stage_config = {**cfg, "work_dir": work_dir}

    try:
        if "fetch" in selected_stages:
            artifact = _run_fetch(season, week, stage_config)
            manifest.record_artifact("fetch", artifact)
            manifest.record_stage("fetch", "complete")
            manifest.write(manifest_path)

        if "project" in selected_stages:
            if project_week is None:
                raise RuntimeError("Projection stage unavailable: ceminidfs.pipeline.project missing")
            canonical_csv = project_week(season, week, salary_path, stage_config)
            manifest.record_artifact("canonical_csv", canonical_csv)
            manifest.record_stage("project", "complete")
            manifest.write(manifest_path)

        if "normalize" in selected_stages:
            normalized_csv = _run_normalize(
                canonical_csv,
                normalized_csv,
                site=str(cfg.get("site", "fanduel")),
                config=stage_config,
            )
            manifest.record_artifact("normalized_csv", normalized_csv)
            manifest.record_stage("normalize", "complete")
            manifest.write(manifest_path)

        if "optimize" in selected_stages:
            expected_count = int(cfg.get("count", 150))
            lineups_csv = _run_optimize(
                normalized_csv,
                lineups_csv,
                expected_count,
                stage_config,
            )
            validation = validate_lineups_csv(
                lineups_csv,
                site=str(cfg.get("site", "fanduel")),
                expected_count=expected_count,
            )
            manifest.record_artifact("lineups_csv", lineups_csv)
            projection_mode = str(cfg.get("projection_mode", "auto")).lower()
            manifest.input_artifacts.update(
                {
                    "lineup_count": validation["lineup_count"],
                    "lineup_validation": validation,
                    "projection_mode": projection_mode,
                    "projection_source": _projection_source(projection_mode, work_dir),
                }
            )
            manifest.record_stage("optimize", "complete")
            manifest.write(manifest_path)

        manifest.record_stage("pipeline", "complete")
        manifest.write(manifest_path)
        return manifest_path
    except Exception:
        manifest.record_stage("pipeline", "failed")
        manifest.write(manifest_path)
        raise


def _parse_stages(stages: str | Iterable[str]) -> list[str]:
    if isinstance(stages, str):
        requested = [part.strip() for part in stages.split(",") if part.strip()]
    else:
        requested = [str(part).strip() for part in stages if str(part).strip()]

    if not requested or requested == ["all"] or "all" in requested:
        return list(STAGE_ORDER)

    unknown = [stage for stage in requested if stage not in STAGE_ORDER]
    if unknown:
        raise ValueError(f"Unknown stage(s): {', '.join(unknown)}")

    selected = [stage for stage in STAGE_ORDER if stage in requested]
    if "optimize" in selected and "normalize" not in selected:
        optimize_idx = selected.index("optimize")
        selected.insert(optimize_idx, "normalize")
    return selected


def _projection_source(projection_mode: str, work_dir: Path) -> str:
    if projection_mode == "diy":
        return "diy"
    if projection_mode == "fppg":
        return "fppg"
    if (work_dir / "player_projection_base.parquet").is_file():
        return "diy"
    return "fppg"


def _run_fetch(season: int, week: int, config: Mapping[str, Any]) -> Path:
    allow_stub = bool(config.get("allow_stub", False))

    try:
        from ceminidfs.pipeline.fetch import fetch_week

        return Path(fetch_week(season=season, week=week, config=config))
    except ImportError as exc:
        if allow_stub:
            return _write_fetch_stub(season, week, config)
        raise RuntimeError(
            "Fetch stage requires nflreadpy. Install with: pip install ceminidfs[data]"
        ) from exc
    except Exception:
        if not allow_stub:
            raise
        return _write_fetch_stub(season, week, config)


def _run_normalize(input_path: Path, output_path: Path, site: str, config: Mapping[str, Any]) -> Path:
    from ceminidfs.export.normalize import normalize_csv

    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalize_csv(input_path, output_path, site=site)
    return output_path


def _run_optimize(input_path: Path, output_path: Path, count: int, config: Mapping[str, Any]) -> Path:
    from ceminidfs.export.optimize import optimize_lineups

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if _sim_rerank_enabled(config):
        from ceminidfs.export.sim_rerank import optimize_with_sim_rerank

        rerank_cfg = _sim_rerank_config(config)
        sim_matrix, player_index = _load_or_build_sim_rerank_inputs(input_path, config)
        optimize_with_sim_rerank(
            csv_path=input_path,
            out_path=output_path,
            sim_matrix=sim_matrix,
            player_index=player_index,
            candidates=int(rerank_cfg.get("candidates", config.get("candidates", 2000))),
            final=int(rerank_cfg.get("final_count", config.get("final_count", count))),
            site=str(config.get("site", "fanduel")),
        )
        return output_path

    optimize_lineups(
        csv_path=input_path,
        out_path=output_path,
        site=str(config.get("site", "fanduel")),
        count=count,
    )
    return output_path


def _sim_rerank_enabled(config: Mapping[str, Any]) -> bool:
    rerank_cfg = config.get("sim_rerank", {})
    if isinstance(rerank_cfg, Mapping):
        return bool(rerank_cfg.get("enabled"))
    return bool(rerank_cfg)


def _sim_rerank_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    rerank_cfg = config.get("sim_rerank", {})
    return rerank_cfg if isinstance(rerank_cfg, Mapping) else {}


def _load_or_build_sim_rerank_inputs(
    normalized_csv: Path,
    config: Mapping[str, Any],
) -> tuple[Any, dict[str, int]]:
    from ceminidfs.export.sim_rerank import build_player_index
    from ceminidfs.models.simulate import simulate_fd_points

    saved = _load_saved_sim_matrix(normalized_csv, config)
    if saved is not None:
        return saved

    source = _canonical_for_sim(config) or normalized_csv
    sim_rows = _simulation_rows(pd.read_csv(source))
    if not sim_rows:
        raise ValueError(f"no simulation-ready player rows found in {source}")

    rerank_cfg = _sim_rerank_config(config)
    simulate_cfg = config.get("simulate", {})
    if not isinstance(simulate_cfg, Mapping):
        simulate_cfg = {}
    n_iterations = int(
        rerank_cfg.get(
            "n_iterations",
            simulate_cfg.get("n_iterations", config.get("simulation_iterations", 5000)),
        )
    )
    seed = rerank_cfg.get("seed", simulate_cfg.get("seed", config.get("simulation_seed")))
    sim_matrix = simulate_fd_points(
        pd.DataFrame(sim_rows),
        n_iterations=n_iterations,
        seed=int(seed) if seed is not None else None,
    )
    return sim_matrix, build_player_index(sim_rows)


def _load_saved_sim_matrix(
    normalized_csv: Path,
    config: Mapping[str, Any],
) -> tuple[Any, dict[str, int]] | None:
    from ceminidfs.export.sim_rerank import build_player_index

    work_dir = Path(config.get("work_dir", "."))
    candidates = [
        config.get("sim_matrix_path"),
        work_dir / "simulation.parquet",
        work_dir / "sim_matrix.parquet",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_file():
            continue
        frame = pd.read_parquet(path)
        numeric = frame.select_dtypes(include="number")
        if numeric.empty:
            raise ValueError(f"simulation parquet has no numeric matrix columns: {path}")
        if any(column in frame.columns for column in ("name", "Name", "player_name", "Player Name")):
            player_index = build_player_index(frame.to_dict("records"))
        else:
            player_index = build_player_index(normalized_csv)
        return numeric.to_numpy(dtype=float), player_index
    return None


def _canonical_for_sim(config: Mapping[str, Any]) -> Path | None:
    configured = config.get("canonical_path")
    if configured and Path(configured).is_file():
        return Path(configured)

    work_dir = Path(config.get("work_dir", "."))
    matches = sorted(work_dir.glob("canonical_projections_*.csv"))
    return matches[-1] if matches else None


def _simulation_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, raw in frame.fillna("").iterrows():
        row = raw.to_dict()
        name = _first_present(row, ("name", "player_name", "Name", "Player Name", "Nickname"))
        if not name:
            first = _first_present(row, ("First Name", "first_name"))
            last = _first_present(row, ("Last Name", "last_name"))
            name = " ".join(part for part in (first, last) if part).strip()
        if not name:
            continue
        rows.append(
            {
                "name": name,
                "player_id": _first_present(row, ("player_id", "fd_id", "dk_id", "Id", "ID"))
                or index,
                "fd_projection": _first_present(
                    row,
                    ("fd_projection", "FPPG", "projection", "AvgPointsPerGame"),
                )
                or 0.0,
                "team": _first_present(row, ("team", "Team", "TeamAbbrev")) or "",
                "position": _first_present(row, ("fd_position", "Position", "dk_position")) or "",
            }
        )
    return rows


def _first_present(row: Mapping[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _write_fetch_stub(season: int, week: int, config: Mapping[str, Any]) -> Path:
    path = Path(config.get("work_dir", ".")) / "fetch_stub.json"
    path.write_text(
        json.dumps(
            {
                "season": season,
                "week": week,
                "status": "stub",
                "message": "Fetch stage placeholder until data connectors are implemented.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
