"""Sunday kickoff load keeps a morning game and rejects a blank clock."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from ceminidfs.pipeline.late_swap_oracle import load_sunday_kickoffs


def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    pd.DataFrame(rows).to_parquet(path)
    return path


def test_sunday_0930_is_kept_and_blank_clock_raises(tmp_path: Path):
    early = _write(
        tmp_path / "early.parquet",
        [
            {
                "season": 2026,
                "week": 4,
                "weekday": "Sunday",
                "gametime": "09:30",
                "gameday": "2026-09-28",
                "away_team": "KC",
                "home_team": "BUF",
            }
        ],
    )
    kickoffs = load_sunday_kickoffs(early, 2026, 4)
    assert set(kickoffs) == {"KC", "BUF"}
    assert kickoffs["KC"] == datetime(2026, 9, 28, 9, 30)
    assert kickoffs["BUF"] == kickoffs["KC"]

    blank = _write(
        tmp_path / "blank.parquet",
        [
            {
                "season": 2026,
                "week": 4,
                "weekday": "Sunday",
                "gametime": "",
                "gameday": "2026-09-28",
                "away_team": "CIN",
                "home_team": "TB",
            }
        ],
    )
    with pytest.raises(ValueError, match="no parsable gametime"):
        load_sunday_kickoffs(blank, 2026, 4)

    monday = _write(
        tmp_path / "monday.parquet",
        [
            {
                "season": 2026,
                "week": 4,
                "weekday": "Monday",
                "gametime": "20:15",
                "gameday": "2026-09-29",
                "away_team": "DAL",
                "home_team": "PHI",
            }
        ],
    )
    assert load_sunday_kickoffs(monday, 2026, 4) == {}
