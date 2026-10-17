"""Empirical Bayes shrinkage for small-sample rate features."""

from __future__ import annotations

import pandas as pd

EB_K = 15.0


def empirical_bayes(success: pd.Series, trials: pd.Series, prior: pd.Series, *, k: float = EB_K) -> pd.Series:
    """Shrink a rate toward ``prior``. ``k`` is the prior strength in trials."""

    numer = success.astype(float) + float(k) * prior.astype(float)
    denom = trials.astype(float) + float(k)
    return numer / denom
