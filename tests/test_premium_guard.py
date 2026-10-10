"""Tests for the optional premium-band projection guard."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.premium_guard import (
    apply_premium_guard,
    decision_sentence,
    guard_is_recommended,
    salary_implied_baseline,
)


def _baseline(salary: float) -> float:
    return 10.0


def test_weight_zero_is_exact_noop():
    frame = pd.DataFrame(
        {
            "fd_projection": [0.1 + 0.2, 18.5],
            "fd_salary": [8000, 6500],
        }
    )
    rows = frame.to_dict(orient="records")

    guarded_frame = apply_premium_guard(frame, _baseline, weight=0)
    guarded_rows = apply_premium_guard(rows, _baseline, weight=0)

    assert isinstance(guarded_frame, pd.DataFrame)
    pd.testing.assert_frame_equal(guarded_frame, frame)
    assert guarded_rows == rows
    assert rows[0]["fd_projection"] == frame.loc[0, "fd_projection"]


def test_player_below_threshold_is_unchanged_at_any_weight():
    frame = pd.DataFrame(
        {
            "fd_projection": [20.0, 14.0],
            "fd_salary": [6999, 7000],
        }
    )
    for weight in (0.0, 0.25, 0.5, 1.0):
        guarded = apply_premium_guard(frame, _baseline, weight=weight)
        assert isinstance(guarded, pd.DataFrame)
        assert guarded.loc[0, "fd_projection"] == 20.0

        rows = apply_premium_guard(frame.to_dict(orient="records"), _baseline, weight=weight)
        assert isinstance(rows, list)
        assert rows[0]["fd_projection"] == 20.0


def test_premium_player_moves_toward_baseline_as_weight_rises():
    frame = pd.DataFrame({"fd_projection": [20.0], "fd_salary": [7000]})
    rows = frame.to_dict(orient="records")
    distances = []
    for weight in (0.0, 0.5, 1.0):
        guarded = apply_premium_guard(frame, _baseline, weight=weight)
        guarded_rows = apply_premium_guard(rows, _baseline, weight=weight)
        assert isinstance(guarded, pd.DataFrame)
        assert isinstance(guarded_rows, list)
        assert guarded.loc[0, "fd_projection"] == pytest.approx(guarded_rows[0]["fd_projection"])
        distances.append(abs(float(guarded.loc[0, "fd_projection"]) - 10.0))

    assert distances == [10.0, 5.0, 0.0]
    assert frame.loc[0, "fd_projection"] == 20.0
    assert rows[0]["fd_projection"] == 20.0


def test_salary_implied_baseline_ignores_target_week():
    history = pd.DataFrame(
        {
            "season": [2025, 2025, 2025, 2025, 2026, 2026, 2026],
            "week": [1, 2, 3, 4, 1, 2, 3],
            "fd_salary": [5000, 6000, 7000, 8000, 5500, 12000, 9000],
            "fd_actual": [8.0, 10.0, 12.0, 14.0, 9.0, 1000.0, 800.0],
        }
    )
    # Week 2 and week 3 of 2026 would dominate the fit. They are the target
    # week and a later week when the call is for 2026 week 2.
    fit = salary_implied_baseline(history, 2026, 2)
    prior_only = history.loc[~((history["season"] == 2026) & (history["week"] >= 2))]
    reference = salary_implied_baseline(prior_only, 2026, 2)

    assert fit.slope == reference.slope
    assert fit.intercept == reference.intercept

    leaked = history.copy()
    leaked.loc[(leaked["season"] == 2026) & (leaked["week"] == 2), "week"] = 1
    changed = salary_implied_baseline(leaked, 2026, 2)
    assert changed.slope != fit.slope


def test_decision_rule():
    assert guard_is_recommended([0.1, 0.1, 0.1], [0.2, 0.2, 0.2])
    assert guard_is_recommended([0.1, 0.1, 0.1], [0.1, 0.1, 0.1])
    assert guard_is_recommended([0.20, 0.20, 0.20], [0.30, 0.25, 0.18])
    assert not guard_is_recommended([0.20, 0.20, 0.20], [0.30, 0.25, 0.17])
    assert not guard_is_recommended([0.20, 0.20, 0.20], [0.30, 0.20, 0.19])

    recommended = decision_sentence([0.1, 0.1, 0.1], [0.2, 0.2, 0.2])
    rejected = decision_sentence([0.2, 0.2, 0.2], [0.0, 0.0, 0.0])
    assert "recommended" in recommended
    assert "NOT recommended" not in recommended
    assert "NOT recommended" in rejected
