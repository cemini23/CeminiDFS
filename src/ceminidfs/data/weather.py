from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, Union
from urllib.parse import urlencode
from urllib.request import urlopen


OPEN_METEO_ARCHIVE_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = (
    "temperature_2m",
    "precipitation",
    "rain",
    "snowfall",
    "wind_speed_10m",
    "wind_gusts_10m",
)


def fetch_hourly_forecast(
    lat: float,
    lon: float,
    start: Union[date, datetime, str],
    end: Union[date, datetime, str],
) -> Dict[str, Any]:
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
    url = f"{OPEN_METEO_ARCHIVE_URL}?{urlencode(params)}"

    with urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _as_date(value: Union[date, datetime, str]) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
