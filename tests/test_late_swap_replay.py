"""Leak-free late-swap replay. No network."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.pipeline.late_swap_oracle import (
    DEFAULT_LINEUPS,
    DEFAULT_ROSTER,
    DEFAULT_SALARY,
    DEFAULT_SCHEDULE,
    DEFAULT_SCRATCH,
    OraclePlayer,
    Seat,
    apply_hindsight_oracle,
    player_is_locked,
)
from ceminidfs.pipeline.late_swap_replay import (
    DEFAULT_PROJECTIONS,
    assert_no_future,
    audit_decision_inputs,
    measure_slate,
    swappable_with_live_data,
)

EARLY = datetime(2026, 9, 27, 13, 0)
LATER = datetime(2026, 9, 27, 16, 5)


def test_hindsight_takes_the_future_but_leak_free_does_not():
    """A huge final line must not pull a swap when only the projection is known."""

    held = OraclePlayer("Held", "AAA", "WR", 5000, LATER, 5.0)
    bait = OraclePlayer("Bait", "BBB", "WR", 5000, LATER, 40.0)

    hindsight = apply_hindsight_oracle(
        [Seat("WR", held)],
        [held, bait],
        EARLY,
        salary_cap=5000,
        salary_floor=5000,
    )
    assert hindsight.seats[0].player.name == "Bait"

    held_proj = OraclePlayer("Held", "AAA", "WR", 5000, LATER, 20.0)
    bait_proj = OraclePlayer("Bait", "BBB", "WR", 5000, LATER, 3.0)
    leak_free = apply_hindsight_oracle(
        [Seat("WR", held_proj)],
        [held_proj, bait_proj],
        EARLY,
        salary_cap=5000,
        salary_floor=5000,
    )
    assert leak_free.seats[0].player.name == "Held"


def test_assert_no_future_passes_on_the_past_and_raises_on_the_future():
    assert_no_future("fd_actual", datetime(2026, 9, 27, 15, 0), datetime(2026, 9, 27, 16, 5))
    with pytest.raises(ValueError):
        assert_no_future("fd_actual", datetime(2026, 9, 27, 18, 0), datetime(2026, 9, 27, 13, 0))
    with pytest.raises(ValueError):
        assert_no_future("not_a_field", EARLY, EARLY)


def test_decision_guard_fires_when_the_real_pool_reaches_the_decision():
    """The guard must raise when a decision-pool player is a real-points player."""

    real = OraclePlayer("Real", "AAA", "WR", 5000, LATER, 40.0)
    scored = OraclePlayer("Real", "AAA", "WR", 5000, LATER, 12.0)

    audit_decision_inputs([real], [scored], EARLY, datetime(2026, 9, 27, 0, 0))
    with pytest.raises(ValueError):
        audit_decision_inputs([real], [real], EARLY, datetime(2026, 9, 27, 0, 0))


def test_swappable_players_never_have_live_data():
    """Unlocked means the game has not started, so no live play exists yet."""

    pool = [
        OraclePlayer("Started", "EAR", "WR", 4000, EARLY, 1.0),
        OraclePlayer("Later", "LAT", "WR", 4000, LATER, 1.0),
        OraclePlayer("Latest", "LTE", "WR", 4000, datetime(2026, 9, 27, 16, 25), 1.0),
    ]
    for decision in (EARLY, LATER, datetime(2026, 9, 27, 16, 25)):
        assert swappable_with_live_data(pool, decision) == 0
        assert any(player_is_locked(player.kickoff, decision) for player in pool)

    # Both sets are non-empty at the first wave, so the zero is not vacuous.
    assert any(not player_is_locked(player.kickoff, EARLY) for player in pool)


@pytest.mark.skipif(
    not all(
        path.is_file()
        for path in (
            DEFAULT_LINEUPS,
            DEFAULT_SALARY,
            DEFAULT_SCRATCH,
            DEFAULT_SCHEDULE,
            DEFAULT_ROSTER,
            DEFAULT_PROJECTIONS,
        )
    ),
    reason="week 3 slate files are not on disk",
)
def test_default_slate_leak_free_stays_under_the_ceiling():
    result = measure_slate()
    assert result.status == "ok"
    assert result.leak_free_points is not None
    assert result.hindsight_points is not None
    assert result.leak_free_points <= result.hindsight_points + 1e-9
    assert all(wave.unlocked_with_live_data == 0 for wave in result.waves)
