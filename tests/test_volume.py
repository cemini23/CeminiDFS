import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.volume import (
    LEAGUE_SEC_PER_PLAY,
    LEAGUE_TOTAL,
    PLAYS_INTERCEPT,
    _neutral_script,
    allocate_play_volume,
    build_week_volume,
    neutral_seconds_per_play,
    projected_pass_rate,
    projected_plays,
    project_team_volume,
)


def test_projected_plays_formula():
    plays = projected_plays(team_sec=34.2, opp_sec=38.2, total=47.8)

    # 62 + 0.5*(32.45-34.2) + 0.35*(32.45-38.2) + 0.08*(47.8-44.8)
    assert plays == pytest.approx(59.3525)


def test_projected_pass_rate_favorite_runs_more():
    favorite_pass_rate = projected_pass_rate(team_spread=-7)
    underdog_pass_rate = projected_pass_rate(team_spread=7)

    assert favorite_pass_rate < underdog_pass_rate


def test_allocate_play_volume_sums_reasonably():
    allocation = allocate_play_volume(plays=64.0, pass_rate=0.6)

    assert allocation["dropbacks"] == pytest.approx(38.4)
    assert allocation["pass_attempts"] == pytest.approx(33.024)
    assert allocation["rush_attempts"] == pytest.approx(28.672)
    assert allocation["dropbacks"] + allocation["rush_attempts"] - (
        allocation["dropbacks"] * 0.08
    ) == pytest.approx(64.0)


def test_project_team_volume_pass_attempts_use_pass_attempt_share():
    """Pass attempts land on the pass-attempt share of plays, not a shrink of it."""

    projection = project_team_volume(
        season=2025,
        week=5,
        team="KC",
        opponent="BUF",
        implied_total=27.0,
        game_total=47.0,
        spread_team=-3.0,
        team_sec=LEAGUE_SEC_PER_PLAY,
        opp_sec=LEAGUE_SEC_PER_PLAY,
    )

    assert projection.pass_attempts == pytest.approx(
        projection.plays_projected * projection.pass_rate
    )
    assert projection.dropbacks > projection.pass_attempts


def test_project_team_volume_rush_and_pass_attempts_match_actuals():
    """Both attempts land near their 2025 actuals and split the play total.

    Measured actuals over 2025 weeks 5-17 (384 team-games): pass attempts 34.68,
    rush attempts 26.98. ``project_team_volume`` now returns
    ``plays - pass_attempts`` for rush, so the rush side is not docked a sack
    that was never part of the pass+rush attempt total.
    """

    projection = project_team_volume(
        season=2025,
        week=5,
        team="KC",
        opponent="BUF",
        implied_total=LEAGUE_TOTAL / 2.0,
        game_total=LEAGUE_TOTAL,
        spread_team=0.0,
        team_sec=LEAGUE_SEC_PER_PLAY,
        opp_sec=LEAGUE_SEC_PER_PLAY,
    )

    assert projection.pass_attempts == pytest.approx(34.68, abs=0.5)
    assert projection.rush_attempts == pytest.approx(26.98, abs=0.5)
    assert projection.pass_attempts + projection.rush_attempts == pytest.approx(
        projection.plays_projected
    )


def test_neutral_seconds_per_play_synthetic_pbp():
    pbp = pd.DataFrame(
        [
            {"posteam": "KC", "wp": 0.5, "qtr": 1, "game_seconds_remaining": 3600},
            {"posteam": "KC", "wp": 0.6, "qtr": 1, "game_seconds_remaining": 3564},
            {"posteam": "KC", "wp": 0.7, "qtr": 2, "game_seconds_remaining": 3528},
            {"posteam": "KC", "wp": 0.9, "qtr": 2, "game_seconds_remaining": 3492},
            {"posteam": "BUF", "wp": 0.5, "qtr": 1, "game_seconds_remaining": 3600},
        ]
    )

    assert neutral_seconds_per_play(pbp, "KC") == pytest.approx(36.0)


def test_build_week_volume_from_synthetic_vegas_and_pbp():
    vegas = pd.DataFrame(
        [
            {
                "game_id": "2024_01_BUF_KC",
                "home_team": "KC",
                "away_team": "BUF",
                "total": 47.0,
                "spread": -3.0,
                "home_implied_total": 25.0,
                "away_implied_total": 22.0,
            },
            {
                "game_id": "2024_01_DAL_PHI",
                "home_team": "PHI",
                "away_team": "DAL",
                "total": 45.0,
                "spread": 2.0,
                "home_implied_total": 21.5,
                "away_implied_total": 23.5,
            },
        ]
    )
    pbp = pd.DataFrame(
        [
            {
                "game_id": "old1",
                "posteam": "KC",
                "wp": 0.5,
                "qtr": 1,
                "game_seconds_remaining": 3600,
                "pass": 1,
                "rush": 0,
                "xpass": 0.58,
            },
            {
                "game_id": "old1",
                "posteam": "KC",
                "wp": 0.5,
                "qtr": 1,
                "game_seconds_remaining": 3564,
                "pass": 0,
                "rush": 1,
                "xpass": 0.58,
            },
            {
                "game_id": "old1",
                "posteam": "BUF",
                "wp": 0.5,
                "qtr": 1,
                "game_seconds_remaining": 3600,
                "pass": 1,
                "rush": 0,
                "xpass": 0.62,
            },
            {
                "game_id": "old1",
                "posteam": "BUF",
                "wp": 0.5,
                "qtr": 1,
                "game_seconds_remaining": 3560,
                "pass": 1,
                "rush": 0,
                "xpass": 0.62,
            },
            {
                "game_id": "old2",
                "posteam": "PHI",
                "wp": 0.5,
                "qtr": 1,
                "game_seconds_remaining": 3600,
                "pass": 0,
                "rush": 1,
                "xpass": 0.55,
            },
            {
                "game_id": "old2",
                "posteam": "PHI",
                "wp": 0.5,
                "qtr": 1,
                "game_seconds_remaining": 3568,
                "pass": 1,
                "rush": 0,
                "xpass": 0.55,
            },
            {
                "game_id": "old2",
                "posteam": "DAL",
                "wp": 0.5,
                "qtr": 1,
                "game_seconds_remaining": 3600,
                "pass": 1,
                "rush": 0,
                "xpass": 0.6,
            },
            {
                "game_id": "old2",
                "posteam": "DAL",
                "wp": 0.5,
                "qtr": 1,
                "game_seconds_remaining": 3562,
                "pass": 0,
                "rush": 1,
                "xpass": 0.6,
            },
        ]
    )
    weather = pd.DataFrame(
        [
            {"home_team": "KC", "wind_speed_10m_mph": 12.0},
            {"home_team": "PHI", "wind_speed_10m_mph": 3.0},
        ]
    )

    result = build_week_volume(vegas, pbp, weather, season=2024, week=1)

    assert len(result) == 4
    assert set(result["team"]) == {"KC", "BUF", "PHI", "DAL"}
    assert result.loc[result["team"] == "KC", "opponent"].iloc[0] == "BUF"
    assert result.loc[result["team"] == "BUF", "spread_team"].iloc[0] == 3.0
    assert result.loc[result["team"] == "KC", "wind_speed_10m_mph"].iloc[0] == 12.0
    assert result.loc[result["team"] == "KC", "team_sec_per_play"].iloc[0] == pytest.approx(
        36.0
    )
    assert result["plays_projected"].notna().all()
    assert result["pass_attempts"].gt(0).all()


def test_build_week_volume_raises_on_nan_spread():
    vegas = pd.DataFrame(
        [
            {
                "game_id": "2024_01_BUF_KC",
                "home_team": "KC",
                "away_team": "BUF",
                "total": 47.0,
                "spread": float("nan"),
                "home_implied_total": 25.0,
                "away_implied_total": 22.0,
            }
        ]
    )
    pbp = pd.DataFrame(columns=["posteam", "wp", "qtr", "game_seconds_remaining"])

    with pytest.raises(ValueError, match="2024_01_BUF_KC"):
        build_week_volume(vegas, pbp, season=2024, week=1)


def test_projected_pass_rate_treats_nan_wind_as_zero_adj():
    assert projected_pass_rate(team_spread=0, wind_mph=float("nan")) == pytest.approx(
        projected_pass_rate(team_spread=0, wind_mph=None)
    )


def test_neutral_script_drops_non_scrimmage_plays():
    """Only pass and run rows survive the neutral-script filter."""

    pbp = pd.DataFrame(
        [
            {"posteam": "KC", "wp": 0.5, "qtr": 1, "play_type": "kickoff"},
            {"posteam": "KC", "wp": 0.5, "qtr": 1, "play_type": "punt"},
            {"posteam": "KC", "wp": 0.5, "qtr": 1, "play_type": "extra_point"},
            {"posteam": "KC", "wp": 0.5, "qtr": 1, "play_type": "pass"},
            {"posteam": "KC", "wp": 0.5, "qtr": 1, "play_type": "run"},
        ]
    )

    neutral = _neutral_script(pbp)

    assert list(neutral["play_type"]) == ["pass", "run"]


def test_seconds_per_play_ignores_kickoffs():
    """A kickoff between two snaps must not halve the measured pace."""

    pbp = pd.DataFrame(
        [
            {
                "game_id": "g1",
                "posteam": "KC",
                "wp": 0.5,
                "qtr": 1,
                "play_type": "pass",
                "game_seconds_remaining": 3600,
            },
            {
                "game_id": "g1",
                "posteam": "KC",
                "wp": 0.5,
                "qtr": 1,
                "play_type": "kickoff",
                "game_seconds_remaining": 3595,
            },
            {
                "game_id": "g1",
                "posteam": "KC",
                "wp": 0.5,
                "qtr": 1,
                "play_type": "run",
                "game_seconds_remaining": 3570,
            },
        ]
    )

    assert neutral_seconds_per_play(pbp, "KC") == pytest.approx(30.0)


def test_projected_plays_is_centered_at_league_pace():
    """League-average pace and total must return the calibrated intercept."""

    assert (
        projected_plays(LEAGUE_SEC_PER_PLAY, LEAGUE_SEC_PER_PLAY, LEAGUE_TOTAL)
        == PLAYS_INTERCEPT
    )


def test_league_sec_per_play_matches_neutral_script_basis():
    """Pin the constant to the basis neutral_seconds_per_play actually returns.

    Measured per-team mean on the 2026 season cache is 32.454 seconds. The raw
    scrimmage mean without the win-probability and quarter filters is 30.7, and
    using that instead under-projects plays by about 1.5 per team.
    """

    assert LEAGUE_SEC_PER_PLAY == 32.45
