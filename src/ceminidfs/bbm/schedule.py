"""2026 bye-week calendar for BBM drafting."""

from __future__ import annotations

from typing import Final

WEEK_BYES: Final[dict[int, list[str]]] = {
    5: ["CAR", "KC"],
    6: ["CIN", "DET", "MIA", "MIN"],
    7: ["BUF", "JAX", "LAC", "WAS"],
    8: ["HOU", "NO", "NYG", "SF"],
    9: ["PIT", "TEN"],
    10: ["CHI", "DEN", "PHI", "TB"],
    11: ["ATL", "CLE", "GB", "LAR", "NE", "SEA"],
    12: [],
    13: ["BAL", "IND", "LV", "NYJ"],
    14: ["ARI", "DAL"],
}

BYE_WEEKS_2026: Final[dict[str, int]] = {
    team: week for week, teams in WEEK_BYES.items() for team in teams
}


def get_bye_week(team: str) -> int | None:
    """Return the 2026 bye week for a team abbreviation."""

    return BYE_WEEKS_2026.get(team.strip().upper())

