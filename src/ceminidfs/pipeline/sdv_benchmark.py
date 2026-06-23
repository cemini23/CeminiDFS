"""Benchmark nflreadpy against sportsdataverse for PBP evaluation."""

from __future__ import annotations

import importlib
import time
from typing import Any, Callable

import pandas as pd


STAGE2_CRITICAL_COLUMNS = [
    "season",
    "week",
    "game_id",
    "play_id",
    "posteam",
    "defteam",
    "pass",
    "pass_attempt",
    "rush",
    "rush_attempt",
    "sack",
    "qb_hit",
    "complete_pass",
    "passer_player_id",
    "rusher_player_id",
    "receiver_player_id",
    "passer_player_name",
    "rusher_player_name",
    "receiver_player_name",
    "air_yards",
    "passing_yards",
    "rushing_yards",
    "receiving_yards",
    "yards_gained",
    "interception",
    "touchdown",
    "game_seconds_remaining",
    "wp",
    "qtr",
    "epa",
    "play_type",
    "desc",
    "yardline_100",
]


def critical_column_coverage(df: pd.DataFrame) -> dict[str, bool]:
    """Return whether each Stage-2 critical PBP column is present."""

    columns = set(df.columns)
    return {column: column in columns for column in STAGE2_CRITICAL_COLUMNS}


def coverage_pct(df: pd.DataFrame) -> float:
    """Return critical-column coverage percentage for a PBP frame."""

    coverage = critical_column_coverage(df)
    present = sum(coverage.values())
    return round((present / len(coverage)) * 100, 2)


def benchmark_pbp_fetch(season: int, week: int | None = None) -> dict[str, Any]:
    """Compare nflreadpy and sportsdataverse PBP fetches for one season or week."""

    return {
        "season": season,
        "week": week,
        "providers": {
            "nflreadpy": _benchmark_provider(
                lambda: _load_nflreadpy_pbp(season),
                week=week,
            ),
            "sportsdataverse": _benchmark_provider(
                lambda: _load_sdv_pbp(season),
                week=week,
            ),
        },
    }


def _benchmark_provider(loader: Callable[[], pd.DataFrame], week: int | None) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        frame = loader()
        if week is not None:
            frame = _filter_week(frame, week)
    except Exception as exc:  # pragma: no cover - live dependency/network failures
        return {
            "elapsed_sec": round(time.perf_counter() - start, 3),
            "rows": 0,
            "coverage_pct": 0.0,
            "error": str(exc),
        }

    return {
        "elapsed_sec": round(time.perf_counter() - start, 3),
        "rows": int(len(frame)),
        "coverage_pct": coverage_pct(frame),
    }


def _load_nflreadpy_pbp(season: int) -> pd.DataFrame:
    try:
        nflreadpy = importlib.import_module("nflreadpy")
    except ImportError as exc:
        raise ImportError(
            "Install nflreadpy with `pip install nflreadpy` or `pip install -e '.[eval]'`."
        ) from exc

    data = _call_first_loader(
        nflreadpy,
        ("load_pbp", "import_pbp_data"),
        season,
    )
    return _to_pandas(data)


def _load_sdv_pbp(season: int) -> pd.DataFrame:
    """Load PBP via sportsdataverse, or the same nflverse release parquet when opted in."""

    import os

    try:
        sdv_nfl = importlib.import_module("sportsdataverse.nfl")
    except Exception as exc:
        if os.environ.get("CEMINIDFS_LIVE_SDV") == "1":
            return _load_nflverse_release_pbp(season)
        raise ImportError(
            "Install sportsdataverse with `pip install sportsdataverse` "
            "or `pip install -e '.[eval]'`, or set CEMINIDFS_LIVE_SDV=1 to "
            "fetch the nflverse release parquet directly. "
            f"Original import error: {exc}"
        ) from exc

    loader = getattr(sdv_nfl, "load_nfl_pbp", None)
    if loader is None:
        if os.environ.get("CEMINIDFS_LIVE_SDV") == "1":
            return _load_nflverse_release_pbp(season)
        raise AttributeError("sportsdataverse.nfl does not expose load_nfl_pbp")
    return _to_pandas(loader(seasons=[season], return_as_pandas=True))


def _load_nflverse_release_pbp(season: int) -> pd.DataFrame:
    """Direct nflverse release fetch — same asset sportsdataverse uses for ``load_nfl_pbp``."""

    url = (
        "https://github.com/nflverse/nflverse-data/releases/download/pbp/"
        f"play_by_play_{season}.parquet"
    )
    return pd.read_parquet(url)


def _call_first_loader(module: Any, loader_names: tuple[str, ...], season: int) -> Any:
    for loader_name in loader_names:
        loader = getattr(module, loader_name, None)
        if loader is None:
            continue
        for args, kwargs in (
            ((season,), {}),
            (([season],), {}),
            ((), {"seasons": [season]}),
        ):
            try:
                return loader(*args, **kwargs)
            except TypeError:
                continue

    raise AttributeError(f"nflreadpy does not expose any expected loaders: {loader_names}")


def _filter_week(df: pd.DataFrame, week: int) -> pd.DataFrame:
    column = "week" if "week" in df.columns else "week_num" if "week_num" in df.columns else None
    if column is None:
        return df
    return df[df[column] == week].reset_index(drop=True)


def _to_pandas(data: Any) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data
    if hasattr(data, "to_pandas"):
        return data.to_pandas()
    return pd.DataFrame(data)
