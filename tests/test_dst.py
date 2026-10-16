import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.dst import (
    LEAGUE_DEF_TD,
    LEAGUE_FUMBLE_RECOVERIES,
    LEAGUE_INTERCEPTIONS_PER_GAME,
    LEAGUE_SACKS_PER_GAME,
    _defense_trailing_event_rates,
    apply_dst_projections,
    build_week_dst_projections,
    expected_dst_points_allowed,
    project_dst_fantasy_points,
)
from ceminidfs.models.scoring import fd_dst_points_allowed


def test_fd_dst_points_allowed_tiers():
    assert fd_dst_points_allowed(0) == 10.0
    assert fd_dst_points_allowed(6) == 7.0
    assert fd_dst_points_allowed(24) == 0.0
    assert fd_dst_points_allowed(35) == -4.0


def test_project_dst_fantasy_points_uses_opponent_implied_total():
    fd, dk = project_dst_fantasy_points(
        team="KC",
        opponent="BUF",
        opponent_implied_total=17.0,
    )

    assert fd > 0
    assert dk == fd
    assert fd > fd_dst_points_allowed(17.0)


def test_apply_dst_projections_marks_model_source():
    vegas = pd.DataFrame(
        [
            {
                "home_team": "KC",
                "away_team": "BUF",
                "home_implied_total": 26.0,
                "away_implied_total": 23.5,
            }
        ]
    )
    rows = [
        {
            "team": "KC",
            "fd_position": "DEF",
            "opp": "BUF",
            "fd_projection": "",
            "dk_projection": "",
        }
    ]

    projected = apply_dst_projections(rows, vegas)

    assert projected[0]["projection_source"] == "dst_model"
    assert float(projected[0]["fd_projection"]) > 0


def test_expected_dst_points_allowed_is_monotone_decreasing():
    implied = [float(value) for value in range(0, 45)]
    values = [expected_dst_points_allowed(value) for value in implied]

    assert all(left >= right for left, right in zip(values, values[1:]))
    assert values[0] > values[-1]


def test_expected_dst_points_allowed_matches_step_rule_at_its_limits():
    # As the scoring deviation shrinks, the expectation collapses onto the raw
    # step rule. Values inside a tier (never on a boundary) converge exactly.
    for implied in (3.0, 10.0, 16.0, 24.0, 31.0, 40.0):
        assert expected_dst_points_allowed(implied, sd=1e-9) == pytest.approx(
            fd_dst_points_allowed(implied)
        )


def test_expected_dst_points_allowed_stays_within_tier_range():
    for implied in (-5.0, 0.0, 13.0, 27.0, 60.0):
        assert -4.0 <= expected_dst_points_allowed(implied) <= 10.0


def _dst_history_pbp() -> pd.DataFrame:
    def play(week, game, *, sack=0, interception=0, recovery="", td=0):
        return {
            "season": 2025,
            "week": week,
            "game_id": game,
            "defteam": "KC",
            "posteam": "BUF",
            "sack": sack,
            "interception": interception,
            "fumble_recovery_1_team": recovery,
            "touchdown": td,
            "return_touchdown": td,
        }

    rows = [play(1, "g1", sack=1) for _ in range(4)]
    rows += [play(1, "g1", interception=1) for _ in range(2)]
    rows.append(play(1, "g1", recovery="KC"))
    rows.append(play(1, "g1", td=1))
    rows += [play(2, "g2", sack=1) for _ in range(2)]
    rows.append(play(2, "g2", recovery="KC"))
    # Target week: these must never leak into the trailing rates.
    rows += [play(3, "g3", sack=1) for _ in range(5)]
    return pd.DataFrame(rows)


def test_defense_trailing_event_rates_are_walk_forward():
    rates = _defense_trailing_event_rates(_dst_history_pbp(), "KC", season=2025, week=3)

    assert rates is not None
    assert rates["sacks"] == pytest.approx(3.0)
    assert rates["interceptions"] == pytest.approx(1.0)
    assert rates["fumbles_recovered"] == pytest.approx(1.0)
    assert rates["def_tds"] == pytest.approx(0.5)


def test_defense_trailing_event_rates_none_without_history():
    pbp = pd.DataFrame(columns=["season", "week", "game_id", "defteam"])

    assert _defense_trailing_event_rates(pbp, "KC", season=2025, week=3) is None


def test_project_dst_event_term_uses_own_rates_then_league_constants():
    implied = 17.0
    own_rates = {
        "sacks": 3.0,
        "interceptions": 1.0,
        "fumbles_recovered": 1.0,
        "def_tds": 0.5,
    }
    pass_factor = 0.95 + 0.1 * 0.565

    own_fd, _ = project_dst_fantasy_points(
        team="KC",
        opponent="BUF",
        opponent_implied_total=implied,
        defense_event_rates=own_rates,
    )
    league_fd, _ = project_dst_fantasy_points(
        team="KC",
        opponent="BUF",
        opponent_implied_total=implied,
    )

    own_events = 3.0 * 1.0 + 1.0 * 2.0 + 1.0 * 2.0 + 0.5 * 6.0
    league_events = (
        LEAGUE_SACKS_PER_GAME * 1.0
        + LEAGUE_INTERCEPTIONS_PER_GAME * 2.0
        + LEAGUE_FUMBLE_RECOVERIES * 2.0
        + LEAGUE_DEF_TD * 6.0
    )
    pa_points = expected_dst_points_allowed(implied)

    assert own_fd == pytest.approx(pa_points + own_events * pass_factor)
    assert league_fd == pytest.approx(pa_points + league_events * pass_factor)


def test_build_week_dst_projections_uses_defense_history_then_falls_back():
    vegas = pd.DataFrame(
        [
            {
                "home_team": "KC",
                "away_team": "BUF",
                "home_implied_total": 20.0,
                "away_implied_total": 17.0,
            }
        ]
    )
    empty_volume = pd.DataFrame()

    with_history = build_week_dst_projections(
        vegas, empty_volume, season=2025, week=3, pbp=_dst_history_pbp()
    )
    without_history = build_week_dst_projections(vegas, empty_volume, season=2025, week=3)

    kc_with = float(with_history.loc[with_history["team"] == "KC", "fd_projection"].iloc[0])
    kc_without = float(without_history.loc[without_history["team"] == "KC", "fd_projection"].iloc[0])
    buf_with = float(with_history.loc[with_history["team"] == "BUF", "fd_projection"].iloc[0])
    buf_without = float(without_history.loc[without_history["team"] == "BUF", "fd_projection"].iloc[0])

    # KC has defensive history, so its event term comes from its own rates.
    assert kc_with > kc_without
    # BUF has none, so the league constants apply either way.
    assert buf_with == pytest.approx(buf_without)

