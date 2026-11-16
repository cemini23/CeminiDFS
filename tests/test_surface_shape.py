"""Tests for the surface-shape acceptance metrics."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.surface_shape import (
    coverage,
    error_band,
    shape_report,
    strike_errors,
)
from ceminidfs.vol_calibration import LeverageFactor


def test_exact_model_gives_zero_errors():
    quotes = [(0.0, 100.0, 20.0), (0.5, 150.0, 30.0), (1.0, 200.0, 40.0)]

    errors = strike_errors(lambda t, x: x / 5.0, quotes)

    assert [x for x, _ in errors] == [100.0, 150.0, 200.0]
    assert [error for _, error in errors] == pytest.approx([0.0, 0.0, 0.0])


def test_error_bp_is_signed_and_scaled():
    # The model is 1% high at x=1 and 2% low at x=2.
    values = {1.0: 101.0, 2.0: 49.0}
    quotes = [(0.0, 1.0, 100.0), (0.0, 2.0, 50.0)]

    errors = strike_errors(lambda t, x: values[x], quotes)

    assert [error for _, error in errors] == pytest.approx([100.0, -200.0])


def test_zero_target_is_skipped_and_counted():
    quotes = [(0.0, 1.0, 10.0, 9.0, 11.0), (0.0, 2.0, 0.0, 9.0, 11.0)]

    def model(t, x):
        return 10.0

    errors = strike_errors(model, quotes)
    assert [x for x, _ in errors] == [1.0]

    report = shape_report(model, quotes)
    assert report.startswith("quotes=2 skipped=1 band_bp=")
    assert report.endswith("coverage=1.000")


def test_error_band_uses_nearest_rank():
    # Absolute values are 1, 2, 3, 5.
    errors = [3.0, -1.0, 2.0, -5.0]

    assert error_band(errors, 0.25) == pytest.approx((1.0, 1.0))
    assert error_band(errors, 0.5) == pytest.approx((1.0, 2.0))
    assert error_band(errors, 0.75) == pytest.approx((1.0, 3.0))
    assert error_band(errors, 1.0) == pytest.approx((1.0, 5.0))


def test_error_band_empty_is_zero():
    assert error_band([], 0.9) == (0.0, 0.0)


def test_error_band_rejects_width_out_of_range():
    with pytest.raises(ValueError):
        error_band([1.0], 0.0)
    with pytest.raises(ValueError):
        error_band([1.0], 1.5)


def test_coverage_full_and_none():
    quotes = [(0.0, 100.0, 20.0, 19.0, 21.0), (1.0, 200.0, 40.0, 39.0, 41.0)]

    def model(t, x):
        return x / 5.0

    assert coverage(model, quotes) == 1.0

    outside = [(0.0, 100.0, 20.0, 40.0, 50.0)]
    assert coverage(model, outside) == 0.0
    assert coverage(model, []) == 0.0


def test_shape_report_line_for_known_errors():
    # Targets are 100. The model values are 100, 101 and 102.
    # The errors are 0, 100 and 200 bp, and the median band ends at 100 bp.
    quotes = [
        (0.0, 100.0, 100.0, 90.0, 110.0),
        (0.0, 101.0, 100.0, 90.0, 110.0),
        (0.0, 102.0, 100.0, 90.0, 110.0),
    ]

    report = shape_report(lambda t, x: x, quotes, band=0.5)

    assert report == "quotes=3 skipped=0 band_bp=100.00 coverage=1.000"


def test_leverage_factor_object_is_accepted():
    factor = LeverageFactor((0.0,))
    quotes = [(0.5, 1.0, 1.0, 0.9, 1.1)]

    assert strike_errors(factor, quotes) == [(1.0, 0.0)]
    assert coverage(factor, quotes) == 1.0
