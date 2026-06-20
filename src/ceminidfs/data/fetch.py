from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from ceminidfs.config import PROJECT_ROOT, load_config
from ceminidfs.manifest import RunManifest, config_sha256, git_commit


INSTALL_HINT = "Install nflreadpy with `pip install nflreadpy` to fetch NFL data."

WEEK_COLUMNS = ("week", "week_num")


def fetch_schedules(season: int) -> pd.DataFrame:
    return _fetch_cached("schedules", season, ("load_schedules", "import_schedules"))


def fetch_pbp(season: int) -> pd.DataFrame:
    return _fetch_cached("pbp", season, ("load_pbp", "import_pbp_data"))


def fetch_injuries(season: int) -> pd.DataFrame:
    return _fetch_cached("injuries", season, ("load_injuries", "import_injuries"))


def _fetch_cached(kind: str, season: int, loader_names: Iterable[str]) -> pd.DataFrame:
    cache_path = _cache_dir() / f"{kind}_{season}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)

    nflreadpy = _require_nflreadpy()
    data = _call_loader(nflreadpy, loader_names, season)
    frame = _to_pandas(data)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(cache_path, index=False)
    return frame


def _require_nflreadpy() -> Any:
    try:
        return importlib.import_module("nflreadpy")
    except ImportError as exc:
        raise ImportError(INSTALL_HINT) from exc


def _call_loader(module: Any, loader_names: Iterable[str], season: int) -> Any:
    for loader_name in loader_names:
        loader = getattr(module, loader_name, None)
        if loader is None:
            continue
        return _call_with_season(loader, season)

    raise AttributeError(
        f"nflreadpy does not expose any expected loaders: {', '.join(loader_names)}"
    )


def _call_with_season(loader: Callable[..., Any], season: int) -> Any:
    for value in (season, [season]):
        try:
            return loader(value)
        except TypeError:
            continue
    return loader(seasons=[season])


def _to_pandas(data: Any) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data
    if hasattr(data, "to_pandas"):
        return data.to_pandas()
    return pd.DataFrame(data)


def _cache_dir() -> Path:
    paths = load_config().get("paths", {})
    cache_dir = Path(paths.get("cache_dir", "artifacts/cache"))
    if cache_dir.is_absolute():
        return cache_dir
    return PROJECT_ROOT / cache_dir


def season_cache_dir(season: int) -> Path:
    return _cache_dir() / str(season)


def week_cache_dir(season: int, week: int) -> Path:
    return season_cache_dir(season) / f"week_{week}"


def _week_column(df: pd.DataFrame) -> str | None:
    for column in WEEK_COLUMNS:
        if column in df.columns:
            return column
    return None


def filter_by_week(df: pd.DataFrame, week: int) -> pd.DataFrame:
    column = _week_column(df)
    if column is None:
        return df
    return df[df[column] == week].reset_index(drop=True)


def fetch_week_datasets(
    season: int,
    week: int,
    config: Mapping[str, Any] | None = None,
) -> dict:
    """Fetch schedules/pbp/injuries, write week-scoped parquet copies."""
    out_dir = week_cache_dir(season, week)
    out_dir.mkdir(parents=True, exist_ok=True)

    fetchers = {
        "schedules": fetch_schedules,
        "pbp": fetch_pbp,
        "injuries": fetch_injuries,
    }

    datasets: dict[str, dict[str, Any]] = {}
    for kind, fetcher in fetchers.items():
        frame = fetcher(season)
        scope = "season"
        if week > 0 and _week_column(frame) is not None:
            frame = filter_by_week(frame, week)
            scope = "week"
        path = out_dir / f"{kind}.parquet"
        frame.to_parquet(path, index=False)
        datasets[kind] = {"path": str(path), "rows": int(len(frame)), "scope": scope}
    return datasets


def write_fetch_manifest(
    season: int,
    week: int,
    datasets: Mapping[str, Mapping[str, Any]],
    output_dir: Path,
    config: Mapping[str, Any] | None = None,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = dict(config or load_config())
    run_id = (
        f"fetch_{season}_week_{week}_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    manifest = RunManifest(
        run_id=run_id,
        git_commit=git_commit(),
        config_sha256=config_sha256(cfg),
        input_artifacts={
            "season": season,
            "week": week,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": {name: dict(info) for name, info in datasets.items()},
        },
    )
    manifest.record_stage("fetch", "complete")

    manifest_path = output_dir / "fetch_manifest.json"
    manifest.write(manifest_path)
    return manifest_path
