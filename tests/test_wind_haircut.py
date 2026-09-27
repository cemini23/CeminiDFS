"""One outdoor wind haircut on the passing-yards mean."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data.stadiums import roof_type_is_weather_exposed
from ceminidfs.models.stats import (
    apply_wind_passing_haircut,
    build_wind_pass_yards_multipliers,
    passing_yards_wind_multiplier,
)


@pytest.mark.parametrize(
    ("roof_type", "expected"),
    [
        ("open", pytest.approx(0.96)),
        ("retractable", pytest.approx(0.96)),
        ("dome", pytest.approx(1.0)),
        ("semi_open", pytest.approx(1.0)),
    ],
)
def test_light_wind_multiplier_skips_indoor_roofs(roof_type: str, expected: float):
    assert passing_yards_wind_multiplier(12.0, roof_type) == expected


@pytest.mark.parametrize(
    ("roof_type", "expected"),
    [
        ("open", pytest.approx(0.90)),
        ("retractable", pytest.approx(0.90)),
        ("dome", pytest.approx(1.0)),
        ("semi_open", pytest.approx(1.0)),
    ],
)
def test_heavy_wind_multiplier_skips_indoor_roofs(roof_type: str, expected: float):
    assert passing_yards_wind_multiplier(18.0, roof_type) == expected


def test_calm_wind_and_missing_wind_return_one():
    assert passing_yards_wind_multiplier(5.0, "open") == pytest.approx(1.0)
    assert passing_yards_wind_multiplier(None, "open") == pytest.approx(1.0)
    assert passing_yards_wind_multiplier(float("nan"), "open") == pytest.approx(1.0)


def test_build_multipliers_uses_home_roof_and_wind():
    vegas = pd.DataFrame(
        [
            {"home_team": "KC", "away_team": "BUF"},
            {"home_team": "DET", "away_team": "MIN"},
        ]
    )
    weather = pd.DataFrame(
        [
            {"home_team": "KC", "wind_speed_10m_mph": 18.0},
            {"home_team": "DET", "wind_speed_10m_mph": 18.0},
        ]
    )

    multipliers = build_wind_pass_yards_multipliers(vegas, weather)

    assert multipliers["KC"] == pytest.approx(0.90)
    assert multipliers["BUF"] == pytest.approx(0.90)
    assert multipliers["DET"] == pytest.approx(1.0)
    assert multipliers["MIN"] == pytest.approx(1.0)


def test_haircut_changes_only_pass_yds():
    stats = pd.DataFrame(
        [
            {
                "team": "KC",
                "player_id": "qb1",
                "position": "QB",
                "pass_yds": 300.0,
                "pass_td": 2.0,
                "rush_yds": 10.0,
                "rec_yds": 0.0,
            }
        ]
    )

    adjusted = apply_wind_passing_haircut(stats, {"KC": 0.90})

    assert adjusted["pass_yds"].iloc[0] == pytest.approx(270.0)
    assert adjusted["pass_td"].iloc[0] == pytest.approx(2.0)
    assert adjusted["rush_yds"].iloc[0] == pytest.approx(10.0)
    assert adjusted["rec_yds"].iloc[0] == pytest.approx(0.0)


def test_roof_type_helper_matches_is_weather_exposed():
    assert roof_type_is_weather_exposed("open") is True
    assert roof_type_is_weather_exposed("retractable") is True
    assert roof_type_is_weather_exposed("dome") is False
    assert roof_type_is_weather_exposed("semi_open") is False
