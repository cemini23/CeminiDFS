"""Open-Meteo weather fetch for NFL game venues.

Uses stadium lat/lon from ``ceminidfs.data.stadiums``. Dome venues skip live
forecast calls; retractable roofs remain weather-exposed until a game-level
roof decision exists (conservative default from the wiki weather spec).

Forecast API: https://api.open-meteo.com/v1/forecast
Historical/archive backtests will use a separate endpoint in Phase 4.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from ceminidfs.data.stadiums import get_stadium, is_weather_exposed

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = (
    "temperature_2m",
    "precipitation",
    "rain",
    "snowfall",
    "wind_speed_10m",
    "wind_gusts_10m",
)

HOME_TEAM_COLUMNS = ("home_team", "home")
AWAY_TEAM_COLUMNS = ("away_team", "away")
GAME_DATE_COLUMNS = ("gameday", "game_date", "date")
GAME_TIME_COLUMNS = ("gametime", "game_time", "kickoff_time")
GAME_ID_COLUMNS = ("game_id", "old_game_id")

WEATHER_OUTPUT_COLUMNS = [
    "game_id",
    "season",
    "week",
    "home_team",
    "away_team",
    "game_date",
    "game_time",
    "stadium_name",
    "lat",
    "lon",
    "roof_type",
    "weather_exposed",
    "temperature_2m_f",
    "wind_speed_10m_mph",
    "wind_gusts_10m_mph",
    "precipitation_in",
    "rain_in",
    "snowfall_in",
    "kickoff_hour",
]

UrlOpener = Callable[..., Any]


def fetch_hourly_forecast(
    lat: float,
    lon: float,
    start: date | datetime | str,
    end: date | datetime | str,
    *,
    opener: UrlOpener | None = None,
) -> dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": _as_date(start),
        "end_date": _as_date(end),
        "hourly": ",".join(HOURLY_VARIABLES),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "auto",
    }
    url = f"{OPEN_METEO_FORECAST_URL}?{urlencode(params)}"
    open_fn = opener or urlopen
    with open_fn(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def build_week_weather_from_schedules(
    schedules: pd.DataFrame,
    config: Mapping[str, Any] | None = None,
    *,
    opener: UrlOpener | None = None,
) -> pd.DataFrame:
    """Build one weather row per scheduled game."""
    cfg = dict(config or {})
    if cfg.get("skip_weather") or schedules.empty or not _has_weather_inputs(schedules):
        return _empty_weather_frame()

    rows = [
        _schedule_game_weather(row, opener=opener)
        for _, row in schedules.iterrows()
        if _first_value(row, HOME_TEAM_COLUMNS)
    ]
    if not rows:
        return _empty_weather_frame()
    return pd.DataFrame(rows, columns=WEATHER_OUTPUT_COLUMNS)


def write_week_weather(
    season: int,
    week: int,
    schedules: pd.DataFrame | None = None,
    config: Mapping[str, Any] | None = None,
    out_path: Path | None = None,
    *,
    opener: UrlOpener | None = None,
) -> Path:
    from ceminidfs.data.fetch import week_cache_dir

    if schedules is None:
        from ceminidfs.data.vegas import load_week_schedules

        schedules = load_week_schedules(season, week)

    path = Path(out_path) if out_path is not None else week_cache_dir(season, week) / "weather.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    build_week_weather_from_schedules(schedules, config=config, opener=opener).to_parquet(
        path, index=False
    )
    return path


def kickoff_weather_snapshot(hourly: Mapping[str, Any], kickoff_hour: int) -> dict[str, Any]:
    times = list(hourly.get("time") or [])
    if not times:
        return {}

    target_suffix = f"T{kickoff_hour:02d}:00"
    index = next((idx for idx, stamp in enumerate(times) if stamp.endswith(target_suffix)), None)
    if index is None:
        index = min(range(len(times)), key=lambda idx: abs(int(times[idx][11:13]) - kickoff_hour))

    snapshot: dict[str, Any] = {"kickoff_hour": kickoff_hour}
    for field in HOURLY_VARIABLES:
        values = hourly.get(field) or []
        snapshot[field] = values[index] if index < len(values) else None
    return snapshot


def _schedule_game_weather(row: Mapping[str, Any], *, opener: UrlOpener | None) -> dict[str, Any]:
    home_team = str(_first_value(row, HOME_TEAM_COLUMNS))
    away_team = str(_first_value(row, AWAY_TEAM_COLUMNS) or "")
    game_date = _parse_game_date(_first_value(row, GAME_DATE_COLUMNS))
    game_time = _parse_game_time(_first_value(row, GAME_TIME_COLUMNS))
    stadium = get_stadium(home_team)
    exposed = is_weather_exposed(stadium)

    base = {
        "game_id": _first_value(row, GAME_ID_COLUMNS) or f"{home_team}@{away_team}:{game_date}",
        "season": row.get("season"),
        "week": row.get("week"),
        "home_team": home_team,
        "away_team": away_team,
        "game_date": game_date,
        "game_time": game_time,
        "stadium_name": stadium.stadium_name,
        "lat": stadium.lat,
        "lon": stadium.lon,
        "roof_type": stadium.roof_type,
        "weather_exposed": exposed,
        "temperature_2m_f": None,
        "wind_speed_10m_mph": None,
        "wind_gusts_10m_mph": None,
        "precipitation_in": None,
        "rain_in": None,
        "snowfall_in": None,
        "kickoff_hour": game_time,
    }

    if not exposed or game_date is None:
        return base

    forecast = fetch_hourly_forecast(
        stadium.lat,
        stadium.lon,
        game_date,
        game_date,
        opener=opener,
    )
    snapshot = kickoff_weather_snapshot(forecast.get("hourly", {}), game_time)
    base.update(
        {
            "temperature_2m_f": snapshot.get("temperature_2m"),
            "wind_speed_10m_mph": snapshot.get("wind_speed_10m"),
            "wind_gusts_10m_mph": snapshot.get("wind_gusts_10m"),
            "precipitation_in": snapshot.get("precipitation"),
            "rain_in": snapshot.get("rain"),
            "snowfall_in": snapshot.get("snowfall"),
            "kickoff_hour": snapshot.get("kickoff_hour", game_time),
        }
    )
    return base


def _has_weather_inputs(schedules: pd.DataFrame) -> bool:
    columns = set(schedules.columns)
    return any(column in columns for column in HOME_TEAM_COLUMNS) and any(
        column in columns for column in GAME_DATE_COLUMNS
    )


def _empty_weather_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=WEATHER_OUTPUT_COLUMNS)


def _parse_game_date(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    if " " in text:
        text = text.split(" ", 1)[0]
    if "T" in text:
        text = text.split("T", 1)[0]
    return text


def _parse_game_time(value: Any) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 13
    if isinstance(value, datetime):
        return value.hour
    text = str(value).strip()
    if not text:
        return 13
    if "T" in text:
        text = text.split("T", 1)[1]
    hour_part = text.split(":", 1)[0]
    try:
        return int(hour_part)
    except ValueError:
        return 13


def _first_value(row: Mapping[str, Any], columns: tuple[str, ...]) -> Any:
    for column in columns:
        if column in row and pd.notna(row[column]):
            return row[column]
    return None


def _as_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
