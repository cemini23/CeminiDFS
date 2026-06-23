"""Smoke helpers for evaluating sportsdataverse PBP access."""

from __future__ import annotations

import time
from typing import Any

import pandas as pd


def load_sdv_pbp_sample(season: int) -> pd.DataFrame:
    """Load one season of sportsdataverse NFL PBP as a pandas DataFrame."""

    from ceminidfs.pipeline.sdv_benchmark import _load_sdv_pbp

    return _load_sdv_pbp(season)


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
