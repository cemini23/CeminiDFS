import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.vol_calibration import (
    LeverageFactor,
    fit_fixed_point,
    fit_quotes,
    quote_coverage,
)


def test_empty_coeffs_raise_value_error():
    factor = LeverageFactor(())

    with pytest.raises(ValueError):
        factor.value(0.5, 1.0)


def test_value_is_positive_and_finite_over_grid():
    factor = LeverageFactor((0.05, -0.2, 0.1, 0.02, -0.03, 0.01))

    for t in (0.0, 0.1, 0.5, 1.0, 2.0):
        for x in (0.0, 0.25, 1.0, 2.0, 4.0):
            value = factor.value(t, x)
            assert math.isfinite(value)
            assert value > 0.0


def test_fit_fixed_point_preserves_count_and_converges():
    initial = LeverageFactor((0.0, 0.0, 0.0, 0.0))
    target = (0.4, -0.25, 0.1, 0.05)
    calls = {"simulate": 0, "regress": 0}

    def simulate(factor):
        calls["simulate"] += 1
        return factor.coeffs

    def regress(samples):
        calls["regress"] += 1
        assert len(samples) == len(target)
        return target

    fitted = fit_fixed_point(simulate, regress, initial, n_iter=60, damping=0.5)

    assert isinstance(fitted, LeverageFactor)
    assert len(fitted.coeffs) == len(initial.coeffs)
    assert fitted.coeffs == pytest.approx(target, abs=1e-9)
    assert calls == {"simulate": 60, "regress": 60}


def test_quote_coverage_empty_and_full():
    factor = LeverageFactor((0.0,))

    assert quote_coverage(factor, []) == 0.0

    bracketed = [
        (0.2, 1.0, 1.0, 0.5, 1.5),
        (0.8, 2.0, 1.0, 0.9, 1.1),
        (0.0, 0.5, 1.0, 1.0, 1.0),
    ]
    assert quote_coverage(factor, bracketed) == 1.0

    mixed = bracketed + [(1.0, 1.0, 1.0, 1.5, 2.5)]
    assert quote_coverage(factor, mixed) == 0.75


def test_fit_quotes_returns_factor_and_coverage_in_range():
    factor = LeverageFactor((0.0,))
    quotes = [
        (0.5, 1.0, 2.0, 1.8, 2.2),
        (1.0, 1.0, 2.0, 1.8, 2.2),
    ]

    updated, coverage = fit_quotes(factor, quotes, steps=5, step_size=1.0)

    assert isinstance(updated, LeverageFactor)
    assert len(updated.coeffs) == len(factor.coeffs)
    assert 0.0 <= coverage <= 1.0
    assert coverage == 1.0


def test_fit_quotes_empty_list_is_safe():
    factor = LeverageFactor((0.1, 0.2))

    updated, coverage = fit_quotes(factor, [])

    assert updated == factor
    assert coverage == 0.0
