"""Right-tail yard, touchdown, and fantasy-point probabilities.

Yards use a lognormal distribution, a gamma distribution matched to the same
mean and variance, or a mixture of the two. Touchdown counts use a Poisson
distribution or a gamma-Poisson (negative binomial) mixture.

The mixture weight and the log-scale sigma are fit on training weeks. This
module does not apply a matchup multiplier.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import gamma, lognorm, nbinom, poisson

PASS_YARD_BONUS = 300.0
RUSH_YARD_BONUS = 100.0
REC_YARD_BONUS = 100.0
MIN_SIGMA_SAMPLE = 20

_YARD_THRESHOLDS = {
    "pass_yds": PASS_YARD_BONUS,
    "rush_yds": RUSH_YARD_BONUS,
    "rec_yds": REC_YARD_BONUS,
}


def norm_sf(z: float) -> float:
    """Upper tail of a standard normal distribution."""

    return float(0.5 * math.erfc(float(z) / math.sqrt(2.0)))


def fit_log_sigma(samples: np.ndarray | pd.Series) -> float | None:
    """Sample standard deviation of log(positive values).

    Returns None when fewer than 20 positive observations are available.
    """

    values = np.asarray(samples, dtype=float)
    positive = values[np.isfinite(values) & (values > 0)]
    if positive.size < MIN_SIGMA_SAMPLE:
        return None
    sigma = float(np.std(np.log(positive), ddof=1))
    if not math.isfinite(sigma) or sigma <= 0:
        return None
    return sigma


def median_from_mean(mean: float, sigma: float) -> float:
    """Lognormal median whose mean equals ``mean``."""

    if mean <= 0 or sigma <= 0 or not math.isfinite(mean) or not math.isfinite(sigma):
        return 0.0
    return float(mean * math.exp(-0.5 * sigma * sigma))


def lognormal_survival(median: float, sigma: float, threshold: float) -> float:
    """P(Y >= threshold) for a lognormal with the given median and log sigma."""

    if median <= 0 or sigma <= 0 or threshold <= 0:
        return 0.0
    if not all(math.isfinite(value) for value in (median, sigma, threshold)):
        return 0.0
    probability = float(lognorm.sf(threshold, s=sigma, scale=median))
    return float(min(1.0, max(0.0, probability)))


def lognormal_quantile(median: float, sigma: float, probability: float) -> float:
    """Return the lognormal quantile at ``probability``."""

    if median <= 0 or sigma <= 0 or not 0.0 < probability < 1.0:
        return 0.0
    return float(lognorm.ppf(probability, s=sigma, scale=median))


def lognormal_moments(median: float, sigma: float) -> dict[str, float]:
    """Mean, variance, skew, p90, and p99 of a lognormal."""

    if median <= 0 or sigma <= 0:
        return {"mean": 0.0, "variance": 0.0, "skew": 0.0, "p90": 0.0, "p99": 0.0}
    variance_factor = math.exp(sigma * sigma)
    mean = median * math.exp(0.5 * sigma * sigma)
    variance = (variance_factor - 1.0) * math.exp(2.0 * math.log(median) + sigma * sigma)
    skew = (variance_factor + 2.0) * math.sqrt(variance_factor - 1.0)
    return {
        "mean": float(mean),
        "variance": float(variance),
        "skew": float(skew),
        "p90": lognormal_quantile(median, sigma, 0.90),
        "p99": lognormal_quantile(median, sigma, 0.99),
    }


def gamma_survival_matched(median: float, sigma: float, threshold: float) -> float:
    """Gamma survival matched to the lognormal mean and variance."""

    if median <= 0 or sigma <= 0 or threshold <= 0:
        return 0.0
    moments = lognormal_moments(median, sigma)
    mean = moments["mean"]
    variance = moments["variance"]
    if mean <= 0 or variance <= 0:
        return 0.0
    shape = (mean * mean) / variance
    scale = variance / mean
    probability = float(gamma.sf(threshold, a=shape, scale=scale))
    return float(min(1.0, max(0.0, probability)))


def mixture_yard_survival(
    median: float,
    sigma: float,
    threshold: float,
    weight_lognormal: float,
) -> float:
    """Mixture of lognormal and matched-gamma survival.

    ``weight_lognormal`` is the lognormal share. 1 is pure lognormal.
    0 is pure gamma. Values outside 0..1 are clipped.
    """

    weight = min(1.0, max(0.0, float(weight_lognormal)))
    lognormal_p = lognormal_survival(median, sigma, threshold)
    gamma_p = gamma_survival_matched(median, sigma, threshold)
    return float(weight * lognormal_p + (1.0 - weight) * gamma_p)


def yard_bonus_probability(
    mean: float,
    sigma: float,
    stat: str,
    *,
    weight_lognormal: float = 1.0,
) -> float:
    """P(yards reach the FanDuel bonus) from a per-game mean."""

    threshold = _YARD_THRESHOLDS[stat]
    median = median_from_mean(mean, sigma)
    return mixture_yard_survival(median, sigma, threshold, weight_lognormal)


def poisson_at_least(count: int, rate: float) -> float:
    """P(K >= count) for a Poisson random variable."""

    if count <= 0:
        return 1.0
    if rate <= 0 or not math.isfinite(rate):
        return 0.0
    probability = float(poisson.sf(count - 1, mu=rate))
    return float(min(1.0, max(0.0, probability)))


def gamma_poisson_at_least(count: int, rate: float, dispersion: float) -> float:
    """P(K >= count) for a gamma-Poisson (negative binomial) mixture.

    ``dispersion`` is the extra-Poisson factor alpha in
    ``Var = rate + alpha * rate^2``. A near-zero alpha matches the Poisson.
    """

    if count <= 0:
        return 1.0
    if rate <= 0 or not math.isfinite(rate):
        return 0.0
    alpha = max(float(dispersion), 1e-8)
    successes = 1.0 / alpha
    probability = 1.0 / (1.0 + alpha * rate)
    tail = float(nbinom.sf(count - 1, successes, probability))
    return float(min(1.0, max(0.0, tail)))
