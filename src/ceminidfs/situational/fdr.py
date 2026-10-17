"""Benjamini-Hochberg false-discovery gate."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

DEFAULT_Q = 0.10


def benjamini_hochberg(
    p_values: dict[str, float] | pd.Series,
    *,
    q: float = DEFAULT_Q,
) -> pd.DataFrame:
    """Return BH q-values and reject flags.

    ``q_value`` is the step-up value ``min_{k >= rank} p_(k) * m / k``,
    enforced so q-values increase with the p-value rank. A feature is rejected
    (kept) when its q-value is at most ``q``.
    """

    if not 0.0 < q < 1.0:
        raise ValueError("q must be between 0 and 1")

    items = list(dict(p_values).items())
    frame = pd.DataFrame(items, columns=["feature", "p_value"])
    if frame.empty:
        frame["rank"] = pd.Series(dtype=int)
        frame["q_value"] = pd.Series(dtype=float)
        frame["reject"] = pd.Series(dtype=bool)
        return frame

    cleaned = []
    for value in frame["p_value"]:
        number = float(value)
        if not math.isfinite(number):
            number = 1.0
        cleaned.append(min(1.0, max(0.0, number)))
    frame["p_value"] = cleaned
    order = frame["p_value"].to_numpy().argsort(kind="mergesort")
    ranked = frame.iloc[order].reset_index(drop=True)
    m = len(ranked)
    ranks = np.arange(1, m + 1, dtype=float)
    raw = ranked["p_value"].to_numpy(dtype=float) * m / ranks
    q_values = raw.copy()
    running = 1.0
    for index in range(m - 1, -1, -1):
        running = min(running, float(q_values[index]))
        q_values[index] = running
    ranked["rank"] = ranks.astype(int)
    ranked["q_value"] = q_values
    ranked["reject"] = ranked["q_value"] <= q
    return ranked.sort_values(["rank", "feature"], kind="mergesort").reset_index(drop=True)


def kept_features(table: pd.DataFrame) -> list[str]:
    """Feature names that pass the BH gate, in rank order."""

    if table.empty or "reject" not in table.columns:
        return []
    passed = table.loc[table["reject"].astype(bool), "feature"]
    return [str(name) for name in passed.tolist()]
