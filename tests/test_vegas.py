import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data import vegas


def test_implied_totals_from_synthetic_schedule_row():
    row = {
        "home_team": "KC",
        "away_team": "BUF",
        "spread_line": -3,
        "total_line": 47,
    }

    result = vegas.implied_team_totals_from_schedule_row(row)

    assert result["home_implied_total"] == 25
    assert result["away_implied_total"] == 22


def test_enrich_schedules_with_vegas_adds_implied_total_columns():
    schedules = pd.DataFrame(
        [
            {
                "week": 1,
                "home_team": "KC",
                "away_team": "BUF",
                "spread_line": -3,
                "total_line": 47,
            }
        ]
    )

    result = vegas.enrich_schedules_with_vegas(schedules)

    assert "home_implied_total" in result.columns
    assert "away_implied_total" in result.columns
    assert result.loc[0, "home_implied_total"] == 25
    assert result.loc[0, "away_implied_total"] == 22


def test_build_week_vegas_uses_loaded_schedule(monkeypatch):
    schedules = pd.DataFrame(
        [
            {
                "week": 1,
                "home_team": "KC",
                "away_team": "BUF",
                "spread_line": -3,
                "total_line": 47,
            }
        ]
    )
    monkeypatch.setattr(vegas, "load_week_schedules", lambda season, week: schedules)

    result = vegas.build_week_vegas(2024, 1)

    assert len(result) == 1
    assert result.loc[0, "home_implied_total"] == 25
    assert result.loc[0, "away_implied_total"] == 22
