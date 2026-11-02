"""How many slates a metric needs before a keep is larger than noise."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from scipy.stats import chi2, t


@dataclass(frozen=True)
class NoiseBand:
    """Sample size and the 95% half-width of a slate-level metric."""

    n: int
    mean: float
    stdev: float
    half_width: float
    minimum_effect: float
    n_required: int
    confidence: float


@dataclass(frozen=True)
class KeepResult:
    """Mechanical keep, revert, or blocked result. No judgement field."""

    action: str
    reasons: tuple[str, ...]


def noise_band(
    values: list[float] | tuple[float, ...],
    *,
    minimum_effect: float,
    confidence: float = 0.95,
) -> NoiseBand:
    """Return the half-width of the mean and the slate count that clears it.

    ``values`` holds one number per slate. The standard deviation uses divisor
    ``n - 1``. The half-width is the Student-t critical value times that
    standard deviation over sqrt(n). ``n_required`` is the smallest n whose
    half-width is at most ``minimum_effect``, using this sample spread.
    """

    _check_confidence(confidence)
    if not math.isfinite(minimum_effect) or minimum_effect <= 0:
        raise ValueError("minimum_effect must be positive")
    sample = _finite_sample(values)
    n = len(sample)
    if n < 2:
        raise ValueError("need at least two slates")
    mean = statistics.fmean(sample)
    stdev = statistics.stdev(sample)
    half_width = _half_width(n, stdev, confidence)
    return NoiseBand(
        n=n,
        mean=mean,
        stdev=stdev,
        half_width=half_width,
        minimum_effect=minimum_effect,
        n_required=slates_required(stdev, minimum_effect, confidence=confidence),
        confidence=confidence,
    )


def slates_required(
    stdev: float,
    minimum_effect: float,
    *,
    confidence: float = 0.95,
) -> int:
    """Return the smallest n >= 2 whose half-width is at most ``minimum_effect``."""

    _check_confidence(confidence)
    if not math.isfinite(stdev) or stdev < 0:
        raise ValueError("stdev must be zero or positive")
    if not math.isfinite(minimum_effect) or minimum_effect <= 0:
        raise ValueError("minimum_effect must be positive")
    if stdev == 0:
        return 2
    for n in range(2, 100_001):
        if _half_width(n, stdev, confidence) <= minimum_effect:
            return n
    raise ValueError("n_required exceeds 100000")


def stdev_bounds(
    values: list[float] | tuple[float, ...],
    *,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Return the chi-square confidence interval for the slate standard deviation."""

    _check_confidence(confidence)
    sample = _finite_sample(values)
    n = len(sample)
    if n < 2:
        raise ValueError("need at least two slates")
    stdev = statistics.stdev(sample)
    df = n - 1
    alpha = 1.0 - confidence
    low = math.sqrt(df * stdev * stdev / float(chi2.ppf(1.0 - alpha / 2.0, df)))
    high = math.sqrt(df * stdev * stdev / float(chi2.ppf(alpha / 2.0, df)))
    return (low, high)


def campaign_slate_count(n_required: int, block_count: int) -> int:
    """Return the slates needed for ``block_count`` disjoint blocks."""

    if n_required < 2:
        raise ValueError("n_required must be >= 2")
    if block_count < 1:
        raise ValueError("block_count must be >= 1")
    return block_count * n_required


def loop_block_reasons(band: NoiseBand, *, block_count: int) -> tuple[str, ...]:
    """Return why a keep-or-revert loop must not run. Empty means the loop may run."""

    if block_count < 1:
        raise ValueError("block_count must be >= 1")
    reasons: list[str] = []
    if band.n < band.n_required or band.half_width > band.minimum_effect:
        reasons.append("the history is shorter than one noise-band block")
    needed = campaign_slate_count(band.n_required, block_count)
    if band.n < needed:
        reasons.append("the history is shorter than the train block plus the holdout")
    return tuple(reasons)


def keep_or_revert(
    baseline: float,
    candidate: float,
    band: NoiseBand,
    *,
    lower_is_better: bool,
    block_count: int,
) -> KeepResult:
    """Keep a change only when it clears the noise band on a long enough history.

    A short history returns ``blocked``. A change inside the half-width returns
    ``revert``. A worse metric returns ``revert``.
    """

    reasons = loop_block_reasons(band, block_count=block_count)
    if reasons:
        return KeepResult("blocked", reasons)
    if not math.isfinite(baseline) or not math.isfinite(candidate):
        raise ValueError("baseline and candidate must be finite")
    delta = (baseline - candidate) if lower_is_better else (candidate - baseline)
    if delta > band.half_width:
        return KeepResult("keep", ())
    return KeepResult("revert", ("the metric did not clear the noise band",))


def _half_width(n: int, stdev: float, confidence: float) -> float:
    if stdev == 0:
        return 0.0
    critical = float(t.ppf(1.0 - (1.0 - confidence) / 2.0, n - 1))
    return critical * stdev / math.sqrt(n)


def _finite_sample(values: list[float] | tuple[float, ...]) -> list[float]:
    sample = [float(value) for value in values]
    if any(not math.isfinite(value) for value in sample):
        raise ValueError("slate metric values must be finite")
    return sample


def _check_confidence(confidence: float) -> None:
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise TypeError("confidence must be a real number")
    if not 0.0 < float(confidence) < 1.0:
        raise ValueError("confidence must be between 0 and 1")
