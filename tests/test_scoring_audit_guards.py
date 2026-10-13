"""Guards for the scoring claims that a model reported and the audit refuted.

A six-model Week 5 audit produced three "HIGH severity" scoring bugs. Each was
checked against the live ESPN API and each was false. These tests pin the
correct behavior, so the next reader cannot "fix" a non-bug and introduce one.

| Claim | Verdict |
|-------|---------|
| D/ST sacks are always zero | FALSE. The input is the counting stat ``dst_sacks``. |
| D/ST interceptions and opponent fumbles lost are not scored | FALSE. Both are scored. |
| Return-TD keys are wrong, so every return TD is dropped | FALSE. The D/ST is paid through ``dst_td``. |

**The trap.** A proposed repair reads a team-level ``defensive.sacks`` key.
ESPN team stats carry no ``defensive`` category, so that change would set every
D/ST sack to zero. It would introduce the bug it claims to repair. Do not add a
team-level sack input. ``test_team_level_sack_keys_are_not_read`` fails if
anyone does.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.scoring import (
    fd_points,
    fantasy_points_from_stats,
    stats_to_counting_stats,
)

DST_EVENTS = {
    "dst_sacks": 8,
    "dst_int": 2,
    "dst_opp_fumbles_lost": 2,
    "dst_td": 1,
    "dst_safety": 1,
    "dst_blocked_kick": 1,
}


# --- The three refuted claims --------------------------------------------------


def test_dst_sacks_are_scored():
    assert fd_points({"dst_sacks": 8}) == pytest.approx(8.0)
    assert fd_points({"dst_sacks": 1}) == pytest.approx(1.0)


def test_dst_interceptions_are_scored():
    assert fd_points({"dst_int": 2}) == pytest.approx(4.0)


def test_dst_opponent_fumbles_lost_are_scored():
    assert fd_points({"dst_opp_fumbles_lost": 2}) == pytest.approx(4.0)


def test_dst_return_touchdown_is_paid_to_the_defense():
    assert fd_points({"dst_td": 1}) == pytest.approx(6.0)


def test_every_dst_event_key_contributes():
    # 8 sacks + 2 INT + 2 opp FL + 1 TD + 1 safety + 1 blocked kick
    assert fd_points(DST_EVENTS) == pytest.approx(8 + 4 + 4 + 6 + 2 + 2)


def test_team_level_sack_keys_are_not_read():
    """The wrong "fix": a team-level sack key must never move the score."""

    assert fd_points({"sacks": 8, "defensive_sacks": 8, "defensive": {"sacks": 8}}) == 0.0


def test_skill_player_is_not_paid_for_a_return_touchdown():
    """FanDuel pays only the D/ST for a return TD. No skill key grants 6."""

    for key in ("kick_return_td", "punt_return_td", "kr_td", "pr_td", "return_td"):
        assert fd_points({key: 1}) == 0.0, key


def test_own_team_fumble_recovery_is_not_scored():
    assert fd_points({"dst_fumbles_recovered": 5}) == 0.0
    assert fd_points({"dst_opp_fumbles_lost": 1}) == pytest.approx(2.0)


# --- The row API must score a D/ST row ----------------------------------------


def test_row_api_scores_a_dst_row_like_fd_points():
    fd, dk = fantasy_points_from_stats(DST_EVENTS)

    assert fd == pytest.approx(fd_points(DST_EVENTS))
    assert dk == pytest.approx(fd_points(DST_EVENTS))
    assert fd > 0.0


def test_row_api_keeps_every_dst_event_key():
    stats = stats_to_counting_stats(DST_EVENTS)

    for key in DST_EVENTS:
        assert stats[key] == pytest.approx(float(DST_EVENTS[key]))


def test_row_api_still_scores_a_skill_row_unchanged():
    fd, dk = fantasy_points_from_stats(
        {"pass_yds": 250, "pass_td": 2, "int": 1, "rush_yds": 20}
    )

    assert fd == pytest.approx(19.0)
    assert dk == pytest.approx(19.0)


# --- Points allowed is a tier, not a counting stat ----------------------------


def test_points_allowed_key_is_absent_when_the_row_has_no_value():
    stats = stats_to_counting_stats({"pass_yds": 250})

    assert "dst_points_allowed" not in stats
    assert "dst_sacks" in stats


def test_points_allowed_is_not_invented_for_a_skill_row():
    """A fabricated zero would pay 10 points to a row with no defense."""

    for missing in (None, "", "  ", float("nan")):
        fd, _dk = fantasy_points_from_stats({"pass_yds": 100, "dst_points_allowed": missing})
        assert fd == pytest.approx(4.0), repr(missing)


def test_a_real_points_allowed_value_pays_the_tier():
    assert fantasy_points_from_stats({"dst_sacks": 8, "dst_points_allowed": 0})[0] == pytest.approx(18.0)
    assert fantasy_points_from_stats({"dst_sacks": 8, "dst_points_allowed": 24})[0] == pytest.approx(8.0)
