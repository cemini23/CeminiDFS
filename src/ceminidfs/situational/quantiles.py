"""Additive empirical FanDuel quantiles and the telemetry point lift.

p90 and p99 are the lagged mean plus a positional residual quantile.
They are not a scalar multiple of the mean. A hard cap blocks impossible scores.
"""

from __future__ import annotations

import math

import pandas as pd

SKILL_CAP = 60.0
DST_CAP = 35.0
MIN_CELL = 25
BUCKET_EDGES = (0.0, 8.0, 12.0, 16.0, 20.0, 40.0)
BONUS_POINTS = 3.0
TD_POINTS = 6.0
FPTS20_POINTS = 4.0


def bucket_label(value: float) -> str:
    """Return the lagged-mean bucket name."""

    if not math.isfinite(value):
        return "na"
    if value < 8.0:
        return "0-8"
    if value < 12.0:
        return "8-12"
    if value < 16.0:
        return "12-16"
    if value < 20.0:
        return "16-20"
    return "20+"


def fit_residual_table(frame: pd.DataFrame, *, position_col: str = "position") -> list[dict]:
    """Fit train-only residual quantiles by position and lagged-mean bucket."""

    if frame.empty or "lagged_fd" not in frame.columns or "fd_points" not in frame.columns:
        return []
    work = frame.copy()
    work["lagged_fd"] = pd.to_numeric(work["lagged_fd"], errors="coerce")
    work["fd_points"] = pd.to_numeric(work["fd_points"], errors="coerce")
    work = work.loc[work["lagged_fd"].gt(0) & work["fd_points"].notna()].copy()
    if work.empty:
        return []
    if position_col not in work.columns:
        work[position_col] = "UNK"
    work["position"] = work[position_col].astype(str)
    work["bucket"] = work["lagged_fd"].map(bucket_label)
    work["residual"] = work["fd_points"] - work["lagged_fd"]
    rows: list[dict] = []
    for position, part in work.groupby("position", sort=True):
        rows.append(_cell(str(position), "*", part))
        for bucket, cell in part.groupby("bucket", sort=True):
            rows.append(_cell(str(position), str(bucket), cell))
    return rows


def lookup_residual(table: list[dict], position: str, lagged_fd: float) -> tuple[float, float]:
    """Return the q90 and q99 residual adders. Thin cells use the position row."""

    label = bucket_label(lagged_fd)
    exact = _find(table, position, label)
    if exact is not None and int(exact.get("n") or 0) >= MIN_CELL:
        return float(exact["q90"]), float(exact["q99"])
    pooled = _find(table, position, "*")
    if pooled is not None:
        return float(pooled["q90"]), float(pooled["q99"])
    any_pos = _find(table, "UNK", "*")
    if any_pos is not None:
        return float(any_pos["q90"]), float(any_pos["q99"])
    return 0.0, 0.0


def apply_ceiling(lagged_fd: float, position: str, table: list[dict], lift: float) -> tuple[float, float]:
    """Return capped p90 and p99. ``lift`` is the calibrated telemetry point lift."""

    if not math.isfinite(lagged_fd) or lagged_fd <= 0:
        return float("nan"), float("nan")
    q90, q99 = lookup_residual(table, position, lagged_fd)
    if not math.isfinite(q90):
        q90 = 0.0
    if not math.isfinite(q99):
        q99 = q90
    extra = lift if math.isfinite(lift) else 0.0
    p90 = lagged_fd + q90 + extra
    p99 = lagged_fd + max(q99, q90) + extra
    cap = DST_CAP if str(position) == "DST" else SKILL_CAP
    p90 = min(cap, max(0.0, p90))
    p99 = min(cap, max(p90, p99))
    return p90, p99


def telemetry_lift(bonus_delta: float, multi_td_delta: float, fpts20_delta: float) -> float:
    """FanDuel point value of the calibrated probability gaps."""

    def _delta(value: float) -> float:
        if value is None or not math.isfinite(value):
            return 0.0
        return float(value)

    return (
        BONUS_POINTS * _delta(bonus_delta)
        + TD_POINTS * _delta(multi_td_delta)
        + FPTS20_POINTS * _delta(fpts20_delta)
    )


def _cell(position: str, bucket: str, part: pd.DataFrame) -> dict:
    residual = pd.to_numeric(part["residual"], errors="coerce").dropna()
    if residual.empty:
        return {"position": position, "bucket": bucket, "n": 0, "q90": 0.0, "q99": 0.0}
    return {
        "position": position,
        "bucket": bucket,
        "n": int(len(residual)),
        "q90": float(residual.quantile(0.90)),
        "q99": float(residual.quantile(0.99)),
    }


def _find(table: list[dict], position: str, bucket: str) -> dict | None:
    for row in table:
        if str(row.get("position")) == position and str(row.get("bucket")) == bucket:
            return row
    return None
