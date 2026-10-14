"""Prior-season window tests for the historical PBP gate.

The prior season enters the historical frame from Week 1 through
``PRIOR_SEASON_THROUGH_WEEK`` of the current season. No later season
ever enters the frame.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.config import PRIOR_SEASON_THROUGH_WEEK
from ceminidfs.pipeline import engine


def _window_frame() -> pd.DataFrame:
    """Rows for season 2025 weeks 1..18, season 2026 weeks 1..5, and 2027 weeks 1..5."""

    rows = [
        {"season": 2025, "week": week, "play_id": f"prior_w{week}"} for week in range(1, 19)
    ]
    rows += [
        {"season": 2026, "week": week, "play_id": f"current_w{week}"} for week in range(1, 6)
    ]
    rows += [
        {"season": 2027, "week": week, "play_id": f"future_w{week}"} for week in range(1, 6)
    ]
    return pd.DataFrame(rows)


def test_prior_season_retained_at_week_2():
    historical = engine._historical_pbp(_window_frame(), season=2026, week=2)

    assert set(historical.loc[historical["season"] == 2025, "play_id"]) == {
        f"prior_w{week}" for week in range(1, 19)
    }


def test_prior_season_retained_at_week_4():
    historical = engine._historical_pbp(_window_frame(), season=2026, week=4)

    assert 2025 in set(historical["season"])


def test_prior_season_dropped_at_week_5():
    historical = engine._historical_pbp(_window_frame(), season=2026, week=5)

    assert 2025 not in set(historical["season"])


def test_prior_season_boundary_follows_shared_constant():
    frame = _window_frame()

    at_boundary = engine._historical_pbp(frame, season=2026, week=PRIOR_SEASON_THROUGH_WEEK)
    past_boundary = engine._historical_pbp(
        frame, season=2026, week=PRIOR_SEASON_THROUGH_WEEK + 1
    )

    assert 2025 in set(at_boundary["season"])
    assert 2025 not in set(past_boundary["season"])


def test_future_season_never_retained():
    frame = _window_frame()

    for week in range(1, 6):
        historical = engine._historical_pbp(frame, season=2026, week=week)
        assert 2027 not in set(historical["season"]), f"week {week} retained 2027"


def test_current_week_is_still_excluded():
    historical = engine._historical_pbp(_window_frame(), season=2026, week=3)

    current = historical.loc[historical["season"] == 2026, "week"]
    assert set(current) == {1, 2}
