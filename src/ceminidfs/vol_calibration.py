"""Two-stage leverage-factor calibration for local stochastic volatility.

Stage one fits a compact global leverage factor by fixed-point iteration: a
simulator produces variance samples under the current factor, a regressor turns
those samples into a target coefficient vector, and the factor moves toward that
target with damping.

Stage two refines the factor against quoted bid/ask levels. Quotes are local:
each one carries its own normalised time ``t`` and spot ``x``, so the correction
uses the full basis rather than a single global multiplier.

Both stages are deliberately separate. The global object can be tested in
isolation, and the quote stage can be measured with :func:`quote_coverage`
before and after refinement.

The factor is smooth and strictly positive by construction::

    value(t, x) = exp(sum(c * t**i * x**j))

Coefficients are consumed in a fixed total-degree basis order, so a factor with
``n`` coefficients always uses the first ``n`` basis terms.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

# Fixed small basis: constant, linear, then quadratic terms. Longer coefficient
# vectors extend this ordering by total degree, so the mapping stays deterministic.
_BASIS: tuple[tuple[int, int], ...] = (
    (0, 0),
    (1, 0),
    (0, 1),
    (2, 0),
    (1, 1),
    (0, 2),
)

Quote = tuple[float, float, float, float, float]


def _basis_terms(n: int) -> tuple[tuple[int, int], ...]:
    """Return the first ``n`` ``(i, j)`` exponent pairs of the fixed basis."""

    if n <= len(_BASIS):
        return _BASIS[:n]

    terms = list(_BASIS)
    degree = 3
    while len(terms) < n:
        for i in range(degree, -1, -1):
            terms.append((i, degree - i))
            if len(terms) >= n:
                break
        degree += 1
    return tuple(terms)


@dataclass(frozen=True)
class LeverageFactor:
    """Compact global leverage factor over normalised time and spot.

    ``coeffs`` are the coefficients of the exponent in the fixed basis. The
    factor must have at least one coefficient; :meth:`value` raises
    :class:`ValueError` otherwise.
    """

    coeffs: tuple[float, ...]

    def value(self, t: float, x: float) -> float:
        """Return the smooth positive factor at normalised time ``t`` and spot ``x``."""

        if not self.coeffs:
            raise ValueError("LeverageFactor requires at least one coefficient")

        exponent = 0.0
        for coeff, (i, j) in zip(self.coeffs, _basis_terms(len(self.coeffs))):
            exponent += coeff * (t**i) * (x**j)
        return math.exp(exponent)


def _target_coeffs(target: object) -> tuple[float, ...]:
    """Normalise a regressor result into a coefficient vector."""

    if isinstance(target, LeverageFactor):
        return target.coeffs
    if isinstance(target, (int, float)):
        raise ValueError("regress must return a coefficient sequence, not a scalar")
    return tuple(float(coeff) for coeff in target)


def fit_fixed_point(
    simulate: Callable[[LeverageFactor], object],
    regress: Callable[[object], object],
    initial: LeverageFactor,
    n_iter: int = 5,
    damping: float = 0.5,
) -> LeverageFactor:
    """Fit the global factor by damped fixed-point iteration.

    Each iteration calls ``simulate(factor)`` for variance samples, then
    ``regress(samples)`` for a positive target coefficient vector (a
    :class:`LeverageFactor` is also accepted). Coefficients move toward the
    target by ``damping``. The coefficient count never changes.
    """

    if not initial.coeffs:
        raise ValueError("initial LeverageFactor requires at least one coefficient")

    width = len(initial.coeffs)
    factor = initial

    for _ in range(max(0, n_iter)):
        samples = simulate(factor)
        target = _target_coeffs(regress(samples))
        if len(target) != width:
            raise ValueError(
                f"regress returned {len(target)} coefficients, expected {width}"
            )
        factor = LeverageFactor(
            tuple(
                current + damping * (wanted - current)
                for current, wanted in zip(factor.coeffs, target)
            )
        )

    return factor


def quote_coverage(factor: LeverageFactor, quotes: Sequence[Quote]) -> float:
    """Return the fraction of quotes whose model value lies within ``[bid, ask]``.

    Each quote is ``(t, x, target, bid, ask)``. The ``target`` field describes
    the observed quote but coverage is measured against the bid/ask bracket. An
    empty quote list returns ``0.0``.
    """

    if not quotes:
        return 0.0

    inside = 0
    for t, x, _target, bid, ask in quotes:
        if bid <= factor.value(t, x) <= ask:
            inside += 1
    return inside / len(quotes)


def fit_quotes(
    factor: LeverageFactor,
    quotes: Sequence[Quote],
    steps: int = 3,
    step_size: float = 0.1,
) -> tuple[LeverageFactor, float]:
    """Refine ``factor`` against quote targets and return it with its coverage.

    Each step takes one damped gradient step on the mean squared log error
    between the model value and each quote target. The correction uses every
    basis term, so quotes at different times and spots pull different parts of
    the surface. Coverage is recomputed after the final step.
    """

    if not quotes:
        return factor, 0.0
    if not factor.coeffs:
        raise ValueError("LeverageFactor requires at least one coefficient")

    terms = _basis_terms(len(factor.coeffs))
    current = factor

    for _ in range(max(0, steps)):
        gradient = [0.0] * len(current.coeffs)
        usable = 0

        for t, x, target, _bid, _ask in quotes:
            model = current.value(t, x)
            if model <= 0.0 or target <= 0.0:
                continue
            error = math.log(target) - math.log(model)
            for index, (i, j) in enumerate(terms):
                gradient[index] += error * (t**i) * (x**j)
            usable += 1

        if usable == 0:
            break

        scale = step_size / usable
        current = LeverageFactor(
            tuple(
                coeff + scale * grad
                for coeff, grad in zip(current.coeffs, gradient)
            )
        )

    return current, quote_coverage(current, quotes)
