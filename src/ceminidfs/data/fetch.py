from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from ceminidfs.config import PROJECT_ROOT, load_config


INSTALL_HINT = "Install nflreadpy with `pip install nflreadpy` to fetch NFL data."


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
