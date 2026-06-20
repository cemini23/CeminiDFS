import json
import sys
from io import BytesIO
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data import weather


def _mock_opener(payload: dict):
    body = json.dumps(payload).encode("utf-8")

    def opener(url, timeout=30):
        return BytesIO(body)

    return opener


def test_kickoff_weather_snapshot_picks_kickoff_hour():
    hourly = {
        "time": ["2024-09-08T12:00", "2024-09-08T13:00", "2024-09-08T14:00"],
        "temperature_2m": [70.0, 72.0, 74.0],
        "wind_speed_10m": [5.0, 8.0, 10.0],
        "wind_gusts_10m": [9.0, 12.0, 15.0],
        "precipitation": [0.0, 0.01, 0.02],
        "rain": [0.0, 0.01, 0.02],
        "snowfall": [0.0, 0.0, 0.0],
    }

    snapshot = weather.kickoff_weather_snapshot(hourly, 13)

    assert snapshot["temperature_2m"] == 72.0
    assert snapshot["wind_speed_10m"] == 8.0
    assert snapshot["kickoff_hour"] == 13


def test_build_week_weather_skips_open_meteo_for_dome():
    schedules = pd.DataFrame(
        [
            {
                "game_id": "g1",
                "season": 2024,
                "week": 1,
                "home_team": "DET",
                "away_team": "GB",
                "gameday": "2024-09-08",
                "gametime": "13:00",
            }
        ]
    )

    def fail_opener(url, timeout=30):
        raise AssertionError("Open-Meteo should not be called for dome games")

    result = weather.build_week_weather_from_schedules(schedules, opener=fail_opener)

    assert len(result) == 1
    assert not result.loc[0, "weather_exposed"]
    assert pd.isna(result.loc[0, "wind_speed_10m_mph"])


def test_build_week_weather_fetches_open_meteo_for_open_air_game():
    schedules = pd.DataFrame(
        [
            {
                "game_id": "g2",
                "season": 2024,
                "week": 1,
                "home_team": "KC",
                "away_team": "BUF",
                "gameday": "2024-09-08",
                "gametime": "13:00",
            }
        ]
    )
    payload = {
        "hourly": {
            "time": ["2024-09-08T13:00"],
            "temperature_2m": [68.0],
            "wind_speed_10m": [11.0],
            "wind_gusts_10m": [18.0],
            "precipitation": [0.0],
            "rain": [0.0],
            "snowfall": [0.0],
        }
    }

    result = weather.build_week_weather_from_schedules(
        schedules,
        opener=_mock_opener(payload),
    )

    assert len(result) == 1
    assert result.loc[0, "weather_exposed"]
    assert result.loc[0, "temperature_2m_f"] == 68.0
    assert result.loc[0, "wind_speed_10m_mph"] == 11.0
    assert result.loc[0, "stadium_name"] == "GEHA Field at Arrowhead Stadium"


def test_build_week_weather_returns_empty_frame_without_schedule_columns():
    schedules = pd.DataFrame({"week": [1], "game_id": ["g1"]})

    result = weather.build_week_weather_from_schedules(schedules)

    assert list(result.columns) == weather.WEATHER_OUTPUT_COLUMNS
    assert len(result) == 0
