"""Shared projection accuracy metrics."""

from __future__ import annotations

import pandas as pd


def spearman_correlation(x: list[float] | pd.Series, y: list[float] | pd.Series) -> float:
    left = pd.Series(x).rank()
    right = pd.Series(y).rank()
    if len(left) < 2:
        return 0.0
    value = left.corr(right)
    return 0.0 if pd.isna(value) else float(value)


def accuracy_metrics(projections: list[float] | pd.Series, actuals: list[float] | pd.Series) -> dict[str, float]:
    """Return MAE, RMSE, and Spearman for aligned projection/actual series."""

    left = pd.Series(projections, dtype=float)
    right = pd.Series(actuals, dtype=float)
    if left.empty or right.empty:
        return {"mae": 0.0, "rmse": 0.0, "spearman": 0.0, "bias": 0.0, "n": 0.0}

    errors = left - right
    return {
        "mae": float(errors.abs().mean()),
        "rmse": float((errors**2).mean()) ** 0.5,
        "spearman": spearman_correlation(left, right),
        "bias": float(errors.mean()),
        "n": float(len(errors)),
    }
