import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.volume import (
    allocate_play_volume,
    build_week_volume,
    neutral_seconds_per_play,
    projected_pass_rate,
    projected_plays,
)


def test_projected_plays_formula():
    plays = projected_plays(team_sec=34.2, opp_sec=38.2, total=47.8)

    assert plays == pytest.approx(62.54)


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
