"""Surface-shape acceptance metrics for a calibrated leverage surface.

One number, such as mean squared error, hides where a fitted surface is wrong.
The acceptance test here reports the shape instead. It measures the error at
every quoted strike in basis points, then reports the band that holds most of
the quotes. It also reports the fraction of quotes whose model value lies
inside the bid/ask bracket.

All functions accept a model callable with the signature ``model(t, x)``. An
object with a ``value(t, x)`` method also works, for example a
``vol_calibration.LeverageFactor`` instance.

Quotes have two shapes. The error metrics need ``(t, x, target)``. Coverage
and the full report need ``(t, x, target, bid, ask)``. Extra fields are
ignored.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

Model = Callable[[float, float], float]
Quote = Sequence[float]

# Tolerance for the nearest-rank product. It keeps a width such as 0.9 on ten
# quotes on rank 9 when the float product lands just above the integer 9.
_RANK_EPS = 1e-9


def _model_value(model: Model, t: float, x: float) -> float:
    """Return the model value at normalised time ``t`` and spot ``x``."""

    if callable(model):
        return float(model(t, x))

    value = getattr(model, "value", None)
    if value is None:
        raise TypeError("model must be callable as model(t, x) or provide value(t, x)")
    return float(value(t, x))


def _strike(quote: Quote) -> tuple[float, float, float]:
    """Return the ``(t, x, target)`` head of a quote."""

    if len(quote) < 3:
        raise ValueError(f"quote needs at least 3 fields (t, x, target), got {len(quote)}")
    return quote[0], quote[1], quote[2]


def _bracket(quote: Quote) -> tuple[float, float, float, float, float]:
    """Return the ``(t, x, target, bid, ask)`` fields of a quote."""

    if len(quote) < 5:
        raise ValueError(
            f"quote needs 5 fields (t, x, target, bid, ask), got {len(quote)}"
        )
    return quote[0], quote[1], quote[2], quote[3], quote[4]


def strike_errors(model: Model, quotes: Sequence[Quote]) -> list[tuple[float, float]]:
    """Return one ``(x, error_bp)`` pair per quoted strike.

    Each quote is ``(t, x, target)``. The error is::

        error_bp = (model_value - target) / target * 10000

    A quote with ``target == 0`` is skipped because the relative error is
    undefined there. The caller can recover the skip count as
    ``len(quotes) - len(errors)``.
    """

    errors: list[tuple[float, float]] = []
    for quote in quotes:
        t, x, target = _strike(quote)
        if target == 0:
            continue
        value = _model_value(model, t, x)
        errors.append((x, (value - target) / target * 10000.0))
    return errors


def error_band(errors: Sequence[float], width: float) -> tuple[float, float]:
    """Return the absolute-error band that holds at least ``width`` of ``errors``.

    The band uses the nearest-rank method. The errors become absolute values
    and are sorted. The rank is ``ceil(width * n)`` with a minimum of one. The
    band runs from the smallest absolute error to the error at that rank.

    ``width`` must be in ``(0, 1]``. An empty error list returns ``(0.0, 0.0)``.
    """

    magnitudes = sorted(abs(float(error)) for error in errors)
    if not magnitudes:
        return (0.0, 0.0)

    if not 0.0 < width <= 1.0:
        raise ValueError(f"width must be in (0, 1], got {width}")

    rank = math.ceil(width * len(magnitudes) - _RANK_EPS)
    rank = min(max(rank, 1), len(magnitudes))
    return (magnitudes[0], magnitudes[rank - 1])


def coverage(model: Model, quotes: Sequence[Quote]) -> float:
    """Return the fraction of quotes whose model value lies inside ``[bid, ask]``.

    Each quote is ``(t, x, target, bid, ask)``. A quote counts when
    ``bid <= model_value <= ask``. An empty quote list returns ``0.0``.
    """

    quotes = list(quotes)
    if not quotes:
        return 0.0

    inside = 0
    for quote in quotes:
        t, x, _target, bid, ask = _bracket(quote)
        if bid <= _model_value(model, t, x) <= ask:
            inside += 1
    return inside / len(quotes)


def shape_report(model: Model, quotes: Sequence[Quote], band: float = 0.9) -> str:
    """Return a one-line shape report for a model over quoted strikes.

    The line starts with ``quotes=N skipped=K band_bp=<x>`` and ends with
    ``coverage=<c>``. ``band_bp`` is the largest absolute error in the band, so
    it is the basis-point threshold that holds at least ``band`` of the usable
    quotes. ``coverage`` has three decimals.

    Each quote is ``(t, x, target, bid, ask)``. The error part uses the first
    three fields. The coverage part needs the bid and ask.
    """

    quotes = list(quotes)
    errors = strike_errors(model, quotes)
    _low, high = error_band([error for _x, error in errors], band)
    return (
        f"quotes={len(quotes)} skipped={len(quotes) - len(errors)} "
        f"band_bp={high:.2f} "
        f"coverage={coverage(model, quotes):.3f}"
    )
