"""Rust scoring kernel. The Python path stays available as a kill switch."""

from __future__ import annotations

import os
from typing import Any

import numpy as np

try:
    from ceminidfs import _sim_kernel_rust as _rust
except ImportError:
    _rust = None

SIM_KERNEL_AVAILABLE = _rust is not None


def use_sim_kernel() -> bool:
    """Return True when the Rust extension is loaded and the kill switch is off."""

    if os.environ.get("FAST_ANYTHING_DISABLE") == "1":
        return False
    return _rust is not None


def _require() -> Any:
    if not use_sim_kernel() or _rust is None:
        raise RuntimeError("sim kernel is disabled")
    return _rust


def _groups(groups: list[list[int]]) -> list[list[int]]:
    return [[int(index) for index in group] for group in groups]


def lineup_totals(
    matrix: np.ndarray,
    groups: list[list[int]],
) -> tuple[list[float], list[int]]:
    """Sum matrix rows for each index group. The flat vector is iteration-major."""

    rust = _require()
    array = np.ascontiguousarray(matrix, dtype=np.float64)
    flat, lengths = rust.lineup_totals(array, _groups(groups))
    return [float(value) for value in flat], [int(length) for length in lengths]


def quantile_linear(values: np.ndarray | list[float], q: float) -> float:
    """Return the linear quantile. Empty input and NaN input return NaN."""

    rust = _require()
    array = np.ascontiguousarray(values, dtype=np.float64).ravel()
    return float(rust.quantile_linear(array.tolist(), float(q)))


def leverage_scores(
    matrix: np.ndarray,
    groups: list[list[int]],
    ownership_fractions: list[float],
    top_fraction: float,
    exponent: float,
) -> tuple[list[float], float]:
    """Return leverage scores and the shared pooled threshold."""

    rust = _require()
    array = np.ascontiguousarray(matrix, dtype=np.float64)
    fractions = [float(value) for value in ownership_fractions]
    scores, threshold = rust.leverage_scores(
        array,
        _groups(groups),
        fractions,
        float(top_fraction),
        float(exponent),
    )
    return [float(score) for score in scores], float(threshold)
