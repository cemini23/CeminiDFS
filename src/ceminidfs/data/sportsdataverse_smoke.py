"""Smoke helpers for evaluating sportsdataverse PBP access."""

from __future__ import annotations

import importlib
import time
from typing import Any

import pandas as pd


INSTALL_HINT = (
    "Install sportsdataverse with `pip install sportsdataverse` "
    "or `pip install -e '.[eval]'`."
)


def load_sdv_pbp_sample(season: int) -> pd.DataFrame:
    """Load one season of sportsdataverse NFL PBP as a pandas DataFrame."""

    try:
        sdv_nfl = importlib.import_module("sportsdataverse.nfl")
    except Exception as exc:
        raise ImportError(f"{INSTALL_HINT} Original import error: {exc}") from exc

    loader = getattr(sdv_nfl, "load_nfl_pbp", None)
    if loader is None:
        raise AttributeError("sportsdataverse.nfl does not expose load_nfl_pbp")

    data = loader(seasons=[season], return_as_pandas=True)
    return _to_pandas(data)


def smoke_fetch_pbp(season: int) -> dict[str, Any]:
    """Fetch sportsdataverse PBP and return a CI-friendly smoke summary."""

    start = time.perf_counter()
    try:
        frame = load_sdv_pbp_sample(season)
    except Exception as exc:  # pragma: no cover - exercised with live dependency failures
        return {
            "rows": 0,
            "cols": 0,
            "elapsed_sec": round(time.perf_counter() - start, 3),
            "error": str(exc),
        }

    return {
        "rows": int(len(frame)),
        "cols": int(len(frame.columns)),
        "elapsed_sec": round(time.perf_counter() - start, 3),
    }


def _to_pandas(data: Any) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data
    if hasattr(data, "to_pandas"):
        return data.to_pandas()
    return pd.DataFrame(data)
