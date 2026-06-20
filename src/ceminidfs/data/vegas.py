from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

import pandas as pd


SPREAD_COLUMNS = ("spread_line", "home_spread", "spread")
TOTAL_COLUMNS = ("total_line", "over_under_line", "game_total", "total")
HOME_TEAM_COLUMNS = ("home_team", "home")
AWAY_TEAM_COLUMNS = ("away_team", "away")


def extract_spread_total(row: Mapping[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    spread = _first_numeric(row, SPREAD_COLUMNS)
    total = _first_numeric(row, TOTAL_COLUMNS)
    return spread, total


def implied_team_totals_from_schedule_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    spread, total = extract_spread_total(row)
    home_team = _first_value(row, HOME_TEAM_COLUMNS)
    away_team = _first_value(row, AWAY_TEAM_COLUMNS)

    if spread is None or total is None:
        return {
            "home_team": home_team,
            "away_team": away_team,
            "spread": spread,
            "total": total,
            "home_implied_total": None,
            "away_implied_total": None,
        }

    # Assumes spread is from the home team's perspective: home -3 means favored by 3.
    home_implied = (total - spread) / 2.0
    away_implied = (total + spread) / 2.0
    return {
        "home_team": home_team,
        "away_team": away_team,
        "spread": spread,
        "total": total,
        "home_implied_total": home_implied,
        "away_implied_total": away_implied,
    }


def add_implied_team_totals(schedules: pd.DataFrame) -> pd.DataFrame:
    implied = schedules.apply(implied_team_totals_from_schedule_row, axis=1)
    implied_df = pd.DataFrame(implied.tolist(), index=schedules.index)
    return schedules.join(
        implied_df[
            ["home_implied_total", "away_implied_total"]
        ]
    )


def _first_numeric(row: Mapping[str, Any], columns: Tuple[str, ...]) -> Optional[float]:
    value = _first_value(row, columns)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_value(row: Mapping[str, Any], columns: Tuple[str, ...]) -> Any:
    for column in columns:
        if column in row and pd.notna(row[column]):
            return row[column]
    return None
