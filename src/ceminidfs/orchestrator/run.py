from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from ceminidfs.pipeline.project import project_week
except Exception:  # pragma: no cover - defensive for partial installs
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

    manifest: dict[str, Any] = {
        "season": season,
        "week": week,
        "salary_path": str(Path(salary_path)),
        "stages": selected_stages,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {},
        "status": "running",
    }
    manifest_path = work_dir / "manifest.json"
    _write_manifest(manifest_path, manifest)

    canonical_csv = Path(salary_path)
    normalized_csv = work_dir / "normalized_players.csv"
    lineups_csv = work_dir / "lineups.csv"
    stage_config = {**cfg, "work_dir": work_dir}

    if "fetch" in selected_stages:
        manifest["artifacts"]["fetch"] = str(_run_fetch(season, week, stage_config))
        _write_manifest(manifest_path, manifest)

    if "project" in selected_stages:
        if project_week is None:
            raise RuntimeError("Projection stage unavailable: ceminidfs.pipeline.project missing")
        canonical_csv = project_week(season, week, salary_path, stage_config)
        manifest["artifacts"]["canonical_csv"] = str(canonical_csv)
        _write_manifest(manifest_path, manifest)

    if "normalize" in selected_stages:
        normalized_csv = _run_normalize(canonical_csv, normalized_csv, site=cfg.get("site", "fanduel"), config=stage_config)
        manifest["artifacts"]["normalized_csv"] = str(normalized_csv)
        _write_manifest(manifest_path, manifest)

    if "optimize" in selected_stages:
        optimizer_input = normalized_csv if "normalize" in selected_stages else canonical_csv
        lineups_csv = _run_optimize(optimizer_input, lineups_csv, int(cfg.get("count", 150)), stage_config)
        manifest["artifacts"]["lineups_csv"] = str(lineups_csv)

    manifest["status"] = "complete"
    _write_manifest(manifest_path, manifest)
    return manifest_path


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
    return [stage for stage in STAGE_ORDER if stage in requested]


def _run_fetch(season: int, week: int, config: Mapping[str, Any]) -> Path:
    try:
        from ceminidfs.pipeline.fetch import fetch_week  # type: ignore

        result = fetch_week(season=season, week=week, config=config)
        return Path(result) if result else _write_fetch_stub(season, week, config)
    except Exception:
        pass

    try:
        from ceminidfs.data.fetch import fetch_injuries, fetch_pbp, fetch_schedules

        summaries = {}
        for name, fetcher in (
            ("schedules", fetch_schedules),
            ("pbp", fetch_pbp),
            ("injuries", fetch_injuries),
        ):
            frame = fetcher(season)
            summaries[name] = {"rows": len(frame)}
        return _write_fetch_summary(season, week, summaries, config)
    except Exception:
        return _write_fetch_stub(season, week, config)


def _run_normalize(input_path: Path, output_path: Path, site: str, config: Mapping[str, Any]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for module_name in ("ceminidfs.pipeline.normalize", "ceminidfs.export.normalize"):
        try:
            module = __import__(module_name, fromlist=["normalize_csv"])
            normalize_csv = getattr(module, "normalize_csv")
            result = normalize_csv(input_path, output_path, site=site)
            return Path(result) if isinstance(result, (str, Path)) else output_path
        except Exception:
            continue
    shutil.copyfile(input_path, output_path)
    return output_path


def _run_optimize(input_path: Path, output_path: Path, count: int, config: Mapping[str, Any]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    optimizer = _load_optimizer()
    if optimizer is not None:
        try:
            result = optimizer(
                csv_path=input_path,
                out_path=output_path,
                site=str(config.get("site", "fanduel")),
                count=count,
            )
            return Path(result) if isinstance(result, (str, Path)) else output_path
        except Exception:
            pass

    with output_path.open("w", newline="", encoding="utf-8") as dst:
        writer = csv.DictWriter(dst, fieldnames=["lineup_id", "source_csv", "note"])
        writer.writeheader()
        for lineup_id in range(1, count + 1):
            writer.writerow(
                {
                    "lineup_id": lineup_id,
                    "source_csv": str(input_path),
                    "note": "optimizer_placeholder",
                }
            )
    return output_path


def _load_optimizer():
    candidates = (
        ("ceminidfs.pipeline.optimize", "optimize_lineups"),
        ("ceminidfs.pipeline.optimize", "optimize"),
        ("ceminidfs.export.optimize", "optimize_lineups"),
        ("ceminidfs.optimize", "optimize_lineups"),
        ("ceminidfs.optimize", "optimize"),
    )
    for module_name, attr in candidates:
        try:
            module = __import__(module_name, fromlist=[attr])
            return getattr(module, attr)
        except Exception:
            continue
    return None


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


def _write_fetch_summary(
    season: int,
    week: int,
    summaries: Mapping[str, Mapping[str, int]],
    config: Mapping[str, Any],
) -> Path:
    path = Path(config.get("work_dir", ".")) / "fetch_summary.json"
    path.write_text(
        json.dumps(
            {
                "season": season,
                "week": week,
                "status": "complete",
                "datasets": summaries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(_jsonable(manifest), indent=2) + "\n", encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
