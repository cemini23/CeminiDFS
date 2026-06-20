import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data.stadiums import STADIUMS, Stadium, get_stadium, is_weather_exposed


EXPECTED_TEAMS = {
    "ARI",
    "ATL",
    "BAL",
    "BUF",
    "CAR",
    "CHI",
    "CIN",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GB",
    "HOU",
    "IND",
    "JAX",
    "KC",
    "LAC",
    "LAR",
    "LV",
    "MIA",
    "MIN",
    "NE",
    "NO",
    "NYG",
    "NYJ",
    "PHI",
    "PIT",
    "SEA",
    "SF",
    "TB",
    "TEN",
    "WAS",
}


def test_all_32_teams_present():
    assert set(STADIUMS) == EXPECTED_TEAMS
    assert len(STADIUMS) == 32


def test_get_stadium_is_case_insensitive():
    assert get_stadium("kc") == STADIUMS["KC"]


def test_get_stadium_handles_los_angeles_aliases():
    assert get_stadium("LA").stadium_name == "SoFi Stadium"
    assert get_stadium("LAR").stadium_name == "SoFi Stadium"
    assert get_stadium("LAC").stadium_name == "SoFi Stadium"


def test_is_weather_exposed_by_roof_type():
    assert not is_weather_exposed(
        Stadium("DET", "Ford Field", "Detroit", 42.3400, -83.0456, "dome")
    )
    assert is_weather_exposed(
        Stadium("KC", "GEHA Field at Arrowhead Stadium", "Kansas City", 39.0489, -94.4839, "open")
    )
    assert is_weather_exposed(
        Stadium("LAR", "SoFi Stadium", "Inglewood", 33.9535, -118.3392, "semi_open")
    )


def test_coordinates_are_within_reasonable_us_bounds():
    for stadium in STADIUMS.values():
        assert 25 <= stadium.lat <= 50
        assert -125 <= stadium.lon <= -65
