"""Matchup-conditioned correlation adjustments.

The exported boost is the train-set difference in pair correlation between
flagged and unflagged weeks. It is kept only when the bootstrap interval
excludes zero and the same boost lowers pair-product error on later weeks.
Otherwise the boost is zero.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MAX_ABS_BOOST = 0.25
MIN_GROUP = 30


@dataclass(frozen=True)
class BoostEstimate:
    """One pair-kind correlation adjustment after the holdout gate."""

    kind: str
    boost: float
    train_delta: float
    ci_low: float
    ci_high: float
    test_improved: bool
    n_flag_train: int
    n_base_train: int


def apply_corr_boost(
    matrix: np.ndarray,
    keys: list[str] | np.ndarray,
    boosts: pd.DataFrame | None,
    *,
    max_abs: float = 0.95,
) -> np.ndarray:
    """Add pairwise boosts and return a symmetric clipped matrix.

    The diagonal stays 1. Off-diagonal values are clipped to ``[-max_abs, max_abs]``.
    Positive-semidefinite repair is left to the caller.
    """

    base = np.array(matrix, dtype=float, copy=True)
    if base.ndim != 2 or base.shape[0] != base.shape[1]:
        raise ValueError("matrix must be square")
    if len(keys) != base.shape[0]:
        raise ValueError("keys must match the matrix order")
    if boosts is None or boosts.empty:
        np.fill_diagonal(base, 1.0)
        return base

    index = {str(key): position for position, key in enumerate(keys)}
    required = {"player_a", "player_b", "corr_boost"}
    missing = required - set(boosts.columns)
    if missing:
        raise ValueError(f"corr boost frame needs {sorted(required)}")

    for row in boosts.itertuples(index=False):
        left = index.get(str(row.player_a))
        right = index.get(str(row.player_b))
        if left is None or right is None or left == right:
            continue
        value = float(row.corr_boost)
        if not np.isfinite(value):
            continue
        updated = base[left, right] + value
        updated = float(min(max_abs, max(-max_abs, updated)))
        base[left, right] = updated
        base[right, left] = updated

    np.fill_diagonal(base, 1.0)
    clip = float(max_abs)
    off = ~np.eye(base.shape[0], dtype=bool)
    base[off] = np.clip(base[off], -clip, clip)
    return (base + base.T) / 2.0


def estimate_pair_boost(
    frame: pd.DataFrame,
    *,
    kind: str,
    min_group: int = MIN_GROUP,
    seed: int = 20261017,
    n_boot: int = 400,
    max_abs: float = MAX_ABS_BOOST,
) -> BoostEstimate:
    """Estimate one correlation boost from historical pair weeks.

    ``frame`` columns are ``season``, ``week``, ``flag``, ``points_a``, and
    ``points_b``. The earlier 70 percent of weeks are the train set.
    """

    required = {"season", "week", "flag", "points_a", "points_b"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"pair frame needs {sorted(required)}")

    work = frame.copy()
    work["season"] = pd.to_numeric(work["season"], errors="coerce")
    work["week"] = pd.to_numeric(work["week"], errors="coerce")
    work["flag"] = work["flag"].astype(bool)
    work["points_a"] = pd.to_numeric(work["points_a"], errors="coerce")
    work["points_b"] = pd.to_numeric(work["points_b"], errors="coerce")
    work = work.dropna(subset=["season", "week", "points_a", "points_b"])
    empty = BoostEstimate(kind, 0.0, 0.0, 0.0, 0.0, False, 0, 0)
    if work.empty:
        return empty

    weeks = (
        work[["season", "week"]]
        .drop_duplicates()
        .sort_values(["season", "week"], kind="mergesort")
        .reset_index(drop=True)
    )
    cut = max(1, int(len(weeks) * 0.70))
    train_keys = set(zip(weeks.loc[: cut - 1, "season"], weeks.loc[: cut - 1, "week"], strict=False))
    test_keys = set(zip(weeks.loc[cut:, "season"], weeks.loc[cut:, "week"], strict=False))
    keys = list(zip(work["season"], work["week"], strict=True))
    train = work.loc[[key in train_keys for key in keys]].copy()
    test = work.loc[[key in test_keys for key in keys]].copy()

    flag_n = int(train["flag"].sum())
    base_n = int((~train["flag"]).sum())
    if flag_n < min_group or base_n < min_group or test.empty:
        return BoostEstimate(kind, 0.0, 0.0, 0.0, 0.0, False, flag_n, base_n)

    delta = _delta_corr(train)
    if not np.isfinite(delta):
        return BoostEstimate(kind, 0.0, 0.0, 0.0, 0.0, False, flag_n, base_n)

    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot, dtype=float)
    train_index = train.index.to_numpy()
    for draw in range(n_boot):
        chosen = rng.choice(train_index, size=len(train_index), replace=True)
        sample_delta = _delta_corr(train.loc[chosen])
        draws[draw] = sample_delta if np.isfinite(sample_delta) else np.nan
    finite = draws[np.isfinite(draws)]
    if finite.size < max(20, n_boot // 5):
        return BoostEstimate(kind, 0.0, float(delta), 0.0, 0.0, False, flag_n, base_n)
    ci_low, ci_high = np.quantile(finite, [0.025, 0.975])
    improved = _test_improved(train, test, float(delta))
    keep = bool(improved and ci_low > 0.0) or bool(improved and ci_high < 0.0)
    boost = float(np.clip(delta, -max_abs, max_abs)) if keep else 0.0
    return BoostEstimate(
        kind,
        boost,
        float(delta),
        float(ci_low),
        float(ci_high),
        bool(improved),
        flag_n,
        base_n,
    )


def _delta_corr(frame: pd.DataFrame) -> float:
    flagged = _pearson(frame.loc[frame["flag"], "points_a"], frame.loc[frame["flag"], "points_b"])
    base = _pearson(frame.loc[~frame["flag"], "points_a"], frame.loc[~frame["flag"], "points_b"])
    if not np.isfinite(flagged) or not np.isfinite(base):
        return float("nan")
    return float(flagged - base)


def _pearson(left: pd.Series, right: pd.Series) -> float:
    a = np.asarray(left, dtype=float)
    b = np.asarray(right, dtype=float)
    if a.size < 3 or b.size < 3:
        return float("nan")
    if float(np.std(a)) < 1e-8 or float(np.std(b)) < 1e-8:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _test_improved(train: pd.DataFrame, test: pd.DataFrame, delta: float) -> bool:
    """True when the train delta lowers standardized cross-product error."""

    mean_a = float(train["points_a"].mean())
    mean_b = float(train["points_b"].mean())
    std_a = float(train["points_a"].std(ddof=1))
    std_b = float(train["points_b"].std(ddof=1))
    if std_a < 1e-8 or std_b < 1e-8:
        return False
    z_a = (test["points_a"].to_numpy(dtype=float) - mean_a) / std_a
    z_b = (test["points_b"].to_numpy(dtype=float) - mean_b) / std_b
    product = z_a * z_b
    unflagged = train.loc[~train["flag"].astype(bool)]
    base_rho = _pearson(unflagged["points_a"], unflagged["points_b"])
    pooled = _pearson(train["points_a"], train["points_b"])
    if not np.isfinite(base_rho):
        base_rho = 0.0
    if not np.isfinite(pooled):
        pooled = base_rho
    flags = test["flag"].to_numpy(dtype=bool)
    model_rho = np.where(flags, base_rho + delta, base_rho)
    base_error = float(np.mean((product - pooled) ** 2))
    model_error = float(np.mean((product - model_rho) ** 2))
    return model_error < base_error
