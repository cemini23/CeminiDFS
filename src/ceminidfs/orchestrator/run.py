from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

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
    optimize_lineups(
        csv_path=input_path,
        out_path=output_path,
        site=str(config.get("site", "fanduel")),
        count=count,
    )
    return output_path


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
