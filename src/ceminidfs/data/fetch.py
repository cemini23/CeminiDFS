from __future__ import annotations

import importlib
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from ceminidfs.config import PRIOR_SEASON_THROUGH_WEEK, PROJECT_ROOT, load_config
from ceminidfs.manifest import RunManifest, config_sha256, git_commit


INSTALL_HINT = "Install nflreadpy with `pip install nflreadpy` to fetch NFL data."

WEEK_COLUMNS = ("week", "week_num")
CACHE_TTL_SECONDS = 12 * 60 * 60
CACHE_TTL_SECONDS_BY_KIND = {"injuries": 15 * 60}


def fetch_schedules(season: int, *, force: bool = False) -> pd.DataFrame:
    return _fetch_cached("schedules", season, ("load_schedules", "import_schedules"), force=force)


def fetch_pbp(season: int, *, force: bool = False) -> pd.DataFrame:
    """Load season PBP from nflverse cache (unfiltered — see ``data.pbp_filters`` at use time)."""

    return _fetch_cached("pbp", season, ("load_pbp", "import_pbp_data"), force=force)


def fetch_injuries(season: int, *, force: bool = False) -> pd.DataFrame:
    return _fetch_cached("injuries", season, ("load_injuries", "import_injuries"), force=force)


def fetch_rosters(season: int, *, force: bool = False) -> pd.DataFrame:
    """Warm the season roster cache. Reuse the rosters loader, not a second one."""

    from ceminidfs.data.rosters import load_season_rosters

    if force:
        (_cache_dir() / f"rosters_{season}.parquet").unlink(missing_ok=True)
    return load_season_rosters(season)


def fetch_ngs_receiving(season: int, *, force: bool = False) -> pd.DataFrame:
    """Fetch nflverse Next Gen Stats receiving, caching ``ngs_receiving_<season>.parquet``."""

    return _fetch_ngs("receiving", season, force=force)


def fetch_ngs_passing(season: int, *, force: bool = False) -> pd.DataFrame:
    """Fetch nflverse Next Gen Stats passing, caching ``ngs_passing_<season>.parquet``."""

    return _fetch_ngs("passing", season, force=force)


def fetch_ngs_rushing(season: int, *, force: bool = False) -> pd.DataFrame:
    """Fetch nflverse Next Gen Stats rushing, caching ``ngs_rushing_<season>.parquet``."""

    return _fetch_ngs("rushing", season, force=force)


def fetch_ftn_charting(season: int, *, force: bool = False) -> pd.DataFrame:
    """Fetch nflverse FTN charting, caching ``ftn_charting_<season>.parquet``.

    Telemetry is auxiliary to the projection engine, so a missing ``nflreadpy``,
    a missing ``load_ftn_charting``, or an unreachable release degrades to an
    empty frame instead of failing the whole fetch.
    """

    cache_path = _cache_dir() / f"ftn_charting_{season}.parquet"
    if cache_path.exists() and not force and _cache_is_fresh(cache_path):
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
        print(f"WARNING: reusing cache {cache_path} (mtime {mtime.isoformat()})", file=sys.stderr)
        return pd.read_parquet(cache_path)

    try:
        nflreadpy = _require_nflreadpy()
        loader = getattr(nflreadpy, "load_ftn_charting", None)
        if loader is None:
            return pd.DataFrame()
        try:
            data = _call_with_season(loader, season)
        except ValueError as exc:
            if "Season must be between" not in str(exc):
                raise
            return pd.DataFrame()
        frame = _to_pandas(data)
    except (ImportError, OSError):
        return pd.DataFrame()

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(cache_path, index=False)
    return frame


def warm_ngs_caches(season: int, *, force: bool = False) -> dict[str, pd.DataFrame]:
    """Warm both season NGS caches for the receiving-elasticity layer.

    NGS is auxiliary to the projection engine, so a missing ``nflreadpy`` or an
    unreachable release degrades to empty frames (and a warning) instead of
    failing the whole fetch.
    """

    warmed: dict[str, pd.DataFrame] = {}
    for stat_type, fetcher in (("receiving", fetch_ngs_receiving), ("passing", fetch_ngs_passing)):
        try:
            warmed[stat_type] = fetcher(season, force=force)
        except (ImportError, OSError) as exc:
            print(f"WARNING: ngs {stat_type} fetch unavailable: {exc}", file=sys.stderr)
            warmed[stat_type] = pd.DataFrame()
    return warmed


def warm_telemetry_caches(season: int, *, force: bool = False) -> dict[str, pd.DataFrame]:
    """Warm the NGS rushing and FTN charting caches for the rushing-telemetry layer.

    Like ``warm_ngs_caches`` this is auxiliary to the projection engine, so a
    missing ``nflreadpy`` or an unreachable release degrades to empty frames
    (and a warning) instead of failing the whole fetch.
    """

    warmed: dict[str, pd.DataFrame] = {}
    for key, fetcher in (("rushing", fetch_ngs_rushing), ("ftn_charting", fetch_ftn_charting)):
        try:
            warmed[key] = fetcher(season, force=force)
        except (ImportError, OSError) as exc:
            print(f"WARNING: telemetry {key} fetch unavailable: {exc}", file=sys.stderr)
            warmed[key] = pd.DataFrame()
    return warmed


def fetch_force_enabled(config: Mapping[str, Any] | None) -> bool:
    """Return True when config asks fetch to ignore a fresh parquet cache."""

    if not config:
        return False
    fetch_cfg = config.get("fetch")
    if isinstance(fetch_cfg, Mapping) and fetch_cfg.get("force"):
        return True
    return bool(config.get("force"))


def _fetch_cached(
    kind: str,
    season: int,
    loader_names: Iterable[str],
    *,
    force: bool = False,
) -> pd.DataFrame:
    cache_path = _cache_dir() / f"{kind}_{season}.parquet"
    if cache_path.exists() and not force and _cache_is_fresh(cache_path, kind):
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
        print(f"WARNING: reusing cache {cache_path} (mtime {mtime.isoformat()})", file=sys.stderr)
        return pd.read_parquet(cache_path)

    nflreadpy = _require_nflreadpy()
    try:
        data = _call_loader(nflreadpy, loader_names, season)
    except ValueError as exc:
        if "Season must be between" not in str(exc):
            raise
        return pd.DataFrame()
    frame = _to_pandas(data)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(cache_path, index=False)
    return frame


def _fetch_ngs(stat_type: str, season: int, *, force: bool = False) -> pd.DataFrame:
    """Cache one NGS stat type with the same freshness rules as ``_fetch_cached``."""

    cache_path = _cache_dir() / f"ngs_{stat_type}_{season}.parquet"
    if cache_path.exists() and not force and _cache_is_fresh(cache_path):
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
        print(f"WARNING: reusing cache {cache_path} (mtime {mtime.isoformat()})", file=sys.stderr)
        return pd.read_parquet(cache_path)

    nflreadpy = _require_nflreadpy()
    try:
        data = _call_nextgen_stats(nflreadpy, stat_type, season)
    except ValueError as exc:
        if "Season must be between" not in str(exc):
            raise
        return pd.DataFrame()
    frame = _canonicalize_ngs_frame(_to_pandas(data))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(cache_path, index=False)
    return frame


def _cache_is_fresh(cache_path: Path, kind: str | None = None) -> bool:
    ttl = CACHE_TTL_SECONDS_BY_KIND.get(kind, CACHE_TTL_SECONDS) if kind else CACHE_TTL_SECONDS
    age = time.time() - cache_path.stat().st_mtime
    return age < ttl


def _call_season_fetcher(fetcher: Callable[..., pd.DataFrame], season: int, *, force: bool) -> pd.DataFrame:
    try:
        return fetcher(season, force=force)
    except TypeError:
        return fetcher(season)


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


def _call_nextgen_stats(module: Any, stat_type: str, season: int) -> Any:
    """Call ``load_nextgen_stats``; it takes ``stat_type`` so it needs its own entry point."""

    loader = getattr(module, "load_nextgen_stats", None)
    if loader is None:
        raise AttributeError("nflreadpy does not expose load_nextgen_stats")
    return loader(seasons=season, stat_type=stat_type)


def _canonicalize_ngs_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Map nflverse NGS columns onto the names the receiving elasticity consumes.

    nflverse ships the player identifier as ``player_gsis_id`` and the display
    name as ``player_display_name``; the elasticity layer keys on ``player_id``
    (a GSIS id) and ``player_name``. Renaming here keeps the cache directly
    consumable without weakening the loader.
    """

    rename: dict[str, str] = {}
    if "player_gsis_id" in frame.columns and "player_id" not in frame.columns:
        rename["player_gsis_id"] = "player_id"
    if "player_display_name" in frame.columns and "player_name" not in frame.columns:
        rename["player_display_name"] = "player_name"
    return frame.rename(columns=rename) if rename else frame


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
    """Fetch schedules/pbp/injuries/rosters, write week-scoped parquet copies."""
    cfg = dict(config or {})
    out_dir = week_cache_dir(season, week)
    out_dir.mkdir(parents=True, exist_ok=True)

    fetchers = {
        "schedules": fetch_schedules,
        "pbp": fetch_pbp,
        "injuries": fetch_injuries,
        "rosters": fetch_rosters,
    }

    force = fetch_force_enabled(cfg)
    datasets: dict[str, dict[str, Any]] = {}
    for kind, fetcher in fetchers.items():
        frame = _call_season_fetcher(fetcher, season, force=force)
        scope = "season"
        # Keep last season while the same-season sample is still thin.
        if kind == "pbp" and week <= PRIOR_SEASON_THROUGH_WEEK and season > 0:
            prior = fetcher(season - 1)
            if not prior.empty:
                frame = pd.concat([prior, frame], ignore_index=True)
        # PBP must retain prior weeks for DIY walk-forward projection cutoff.
        # Rosters are season-scoped, so they are never filtered by week.
        if kind not in {"pbp", "rosters"} and week > 0 and _week_column(frame) is not None:
            frame = filter_by_week(frame, week)
            scope = "week"
        path = out_dir / f"{kind}.parquet"
        frame.to_parquet(path, index=False)
        datasets[kind] = {"path": str(path), "rows": int(len(frame)), "scope": scope}
        if kind == "schedules":
            from ceminidfs.data.vegas import enrich_schedules_with_vegas
            from ceminidfs.data.weather import build_week_weather_from_schedules

            vegas = enrich_schedules_with_vegas(frame)
            vegas_path = out_dir / "vegas.parquet"
            vegas.to_parquet(vegas_path, index=False)
            datasets["vegas"] = {
                "path": str(vegas_path),
                "rows": int(len(vegas)),
                "scope": scope,
            }

            weather = build_week_weather_from_schedules(frame, config=cfg)
            weather_path = out_dir / "weather.parquet"
            weather.to_parquet(weather_path, index=False)
            datasets["weather"] = {
                "path": str(weather_path),
                "rows": int(len(weather)),
                "scope": scope,
            }

    # NGS is season-scoped and consumed by the receiving elasticity. Warm it
    # without recording a week-scoped artifact (it lives at the cache root).
    warm_ngs_caches(season, force=force)
    # Rushing NGS + FTN charting are telemetry caches: season-scoped at the
    # cache root, warmed alongside NGS and never recorded per week.
    warm_telemetry_caches(season, force=force)
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
    run_id = f"fetch_{season}_week_{week}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
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
