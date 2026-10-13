"""Hindsight oracle decision rule. No network."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.pipeline.late_swap_oracle import (
    OraclePlayer,
    Seat,
    apply_hindsight_oracle,
    player_is_locked,
)


def test_first_lock_swaps_only_the_later_game():
    decision = datetime(2026, 9, 27, 13, 0)
    early = datetime(2026, 9, 27, 13, 0)
    later = datetime(2026, 9, 27, 16, 5)
    started = OraclePlayer("Started", "EAR", "WR", 4000, early, 3.0)
    held = OraclePlayer("Later", "LAT", "WR", 4000, later, 4.0)
    upgrade = OraclePlayer("Upgrade", "UPG", "WR", 4000, later, 18.0)
    boom = OraclePlayer("Boom", "BOOM", "WR", 4000, early, 40.0)

    assert player_is_locked(started.kickoff, decision) is True
    assert player_is_locked(boom.kickoff, decision) is True
    assert player_is_locked(held.kickoff, decision) is False

    result = apply_hindsight_oracle(
        [Seat("WR", started), Seat("WR", held)],
        [started, held, upgrade, boom],
        decision,
        salary_cap=8000,
        salary_floor=8000,
    )

    assert result.hindsight_oracle is True
    assert result.live_information_only is False
    assert result.seats[0].player.name == "Started"
    assert result.seats[1].player.name == "Upgrade"
    assert [seat.player.name for seat in result.seats] != ["Started", "Boom"]
    assert "Boom" not in {seat.player.name for seat in result.seats}
