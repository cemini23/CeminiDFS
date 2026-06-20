"""NFL home stadium metadata for weather-aware DFS features.

The coordinates and roof categories follow the greerreNFL/stadiums style of
venue metadata: one row per home team, with latitude, longitude, and roof type.
Retractable roofs are treated as weather-exposed until a game-level roof
decision is available, which keeps Phase 1-D weather adjustments conservative.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import pandas as pd


RoofType = Literal["dome", "open", "retractable", "semi_open"]


@dataclass(frozen=True)
class Stadium:
    team: str
    name: str
    city: str
    lat: float
    lon: float
    roof_type: RoofType

    @property
    def team_abbr(self) -> str:
        return self.team

    @property
    def stadium_name(self) -> str:
        return self.name


STADIUMS: dict[str, Stadium] = {
    "ARI": Stadium("ARI", "State Farm Stadium", "Glendale", 33.5276, -112.2626, "retractable"),
    "ATL": Stadium("ATL", "Mercedes-Benz Stadium", "Atlanta", 33.7554, -84.4008, "retractable"),
    "BAL": Stadium("BAL", "M&T Bank Stadium", "Baltimore", 39.2780, -76.6227, "open"),
    "BUF": Stadium("BUF", "Highmark Stadium", "Orchard Park", 42.7738, -78.7869, "open"),
    "CAR": Stadium("CAR", "Bank of America Stadium", "Charlotte", 35.2258, -80.8528, "open"),
    "CHI": Stadium("CHI", "Soldier Field", "Chicago", 41.8623, -87.6167, "open"),
    "CIN": Stadium("CIN", "Paycor Stadium", "Cincinnati", 39.0955, -84.5160, "open"),
    "CLE": Stadium("CLE", "Huntington Bank Field", "Cleveland", 41.5061, -81.6995, "open"),
    "DAL": Stadium("DAL", "AT&T Stadium", "Arlington", 32.7473, -97.0945, "retractable"),
    "DEN": Stadium("DEN", "Empower Field at Mile High", "Denver", 39.7439, -105.0201, "open"),
    "DET": Stadium("DET", "Ford Field", "Detroit", 42.3400, -83.0456, "dome"),
    "GB": Stadium("GB", "Lambeau Field", "Green Bay", 44.5013, -88.0622, "open"),
    "HOU": Stadium("HOU", "NRG Stadium", "Houston", 29.6847, -95.4107, "retractable"),
    "IND": Stadium("IND", "Lucas Oil Stadium", "Indianapolis", 39.7601, -86.1639, "retractable"),
    "JAX": Stadium("JAX", "EverBank Stadium", "Jacksonville", 30.3239, -81.6373, "open"),
    "KC": Stadium("KC", "GEHA Field at Arrowhead Stadium", "Kansas City", 39.0489, -94.4839, "open"),
    "LAC": Stadium("LAC", "SoFi Stadium", "Inglewood", 33.9535, -118.3392, "semi_open"),
    "LAR": Stadium("LAR", "SoFi Stadium", "Inglewood", 33.9535, -118.3392, "semi_open"),
    "LV": Stadium("LV", "Allegiant Stadium", "Paradise", 36.0908, -115.1830, "dome"),
    "MIA": Stadium("MIA", "Hard Rock Stadium", "Miami Gardens", 25.9580, -80.2389, "open"),
    "MIN": Stadium("MIN", "U.S. Bank Stadium", "Minneapolis", 44.9738, -93.2581, "dome"),
    "NE": Stadium("NE", "Gillette Stadium", "Foxborough", 42.0909, -71.2643, "open"),
    "NO": Stadium("NO", "Caesars Superdome", "New Orleans", 29.9509, -90.0810, "dome"),
    "NYG": Stadium("NYG", "MetLife Stadium", "East Rutherford", 40.8135, -74.0745, "open"),
    "NYJ": Stadium("NYJ", "MetLife Stadium", "East Rutherford", 40.8135, -74.0745, "open"),
    "PHI": Stadium("PHI", "Lincoln Financial Field", "Philadelphia", 39.9008, -75.1675, "open"),
    "PIT": Stadium("PIT", "Acrisure Stadium", "Pittsburgh", 40.4468, -80.0158, "open"),
    "SEA": Stadium("SEA", "Lumen Field", "Seattle", 47.5952, -122.3316, "open"),
    "SF": Stadium("SF", "Levi's Stadium", "Santa Clara", 37.4030, -121.9700, "open"),
    "TB": Stadium("TB", "Raymond James Stadium", "Tampa", 27.9759, -82.5033, "open"),
    "TEN": Stadium("TEN", "Nissan Stadium", "Nashville", 36.1665, -86.7713, "open"),
    "WAS": Stadium("WAS", "Northwest Stadium", "Landover", 38.9077, -76.8645, "open"),
}

TEAM_ALIASES = {
    "LA": "LAR",
}


def get_stadium(team: str) -> Stadium:
    normalized = team.strip().upper()
    normalized = TEAM_ALIASES.get(normalized, normalized)
    return STADIUMS[normalized]


def load_stadiums_df() -> pd.DataFrame:
    rows = []
    for stadium in STADIUMS.values():
        row = asdict(stadium)
        row["team_abbr"] = row.pop("team")
        row["stadium_name"] = row.pop("name")
        rows.append(row)
    return pd.DataFrame(rows, columns=["team_abbr", "stadium_name", "city", "lat", "lon", "roof_type"])


def is_weather_exposed(stadium: Stadium) -> bool:
    return stadium.roof_type != "dome"
