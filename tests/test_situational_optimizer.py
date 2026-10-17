"""Ceiling override reaches the solver. Two solves with one seed match."""

import csv
from pathlib import Path

import pytest

pytest.importorskip("pydfs_lineup_optimizer")

from ceminidfs.export.optimize import generate_lineups

HEADER = [
    "Id",
    "First Name",
    "Last Name",
    "Position",
    "Team",
    "Salary",
    "FPPG",
    "Game",
    "Injury Indicator",
    "Opponent",
]

POOL = [
    ("1", "Patrick", "Mahomes", "QB", "KC", "8000", "30", "BUF"),
    ("2", "Isiah", "Pacheco", "RB", "KC", "6100", "18", "BUF"),
    ("3", "Kareem", "Hunt", "RB", "KC", "5200", "12", "BUF"),
    ("4", "Rashee", "Rice", "WR", "KC", "6400", "16", "BUF"),
    ("5", "Xavier", "Worthy", "WR", "KC", "5600", "14", "BUF"),
    ("6", "Travis", "Kelce", "TE", "KC", "7000", "17", "BUF"),
    ("7", "Kansas City", "Chiefs", "D", "KC", "3600", "8", "BUF"),
    ("8", "Josh", "Allen", "QB", "BUF", "8100", "29", "KC"),
    ("9", "James", "Cook", "RB", "BUF", "6800", "17", "KC"),
    ("10", "Ray", "Davis", "RB", "BUF", "5000", "11", "KC"),
    ("11", "Khalil", "Shakir", "WR", "BUF", "5900", "13", "KC"),
    ("12", "Stefon", "Diggs", "WR", "BUF", "6200", "15", "KC"),
    ("13", "Dalton", "Kincaid", "TE", "BUF", "5500", "12", "KC"),
    ("14", "Buffalo", "Bills", "D", "BUF", "3500", "7", "KC"),
    ("15", "Joe", "Burrow", "QB", "CIN", "7900", "28", "KC"),
    ("16", "Ja'Marr", "Chase", "WR", "CIN", "8200", "24", "KC"),
    ("17", "Tee", "Higgins", "WR", "CIN", "7100", "18", "KC"),
    ("18", "Chase", "Brown", "RB", "CIN", "6000", "15", "KC"),
    ("19", "Mike", "Gesicki", "WR", "CIN", "4500", "8", "KC"),
    ("20", "Cincinnati", "Bengals", "D", "CIN", "3400", "6", "KC"),
]


def test_gesicki_override_is_stable(tmp_path: Path):
    path = _write_pool(tmp_path / "pool.csv")
    kwargs = {
        "count": 1,
        "max_exposure": 1.0,
        "min_salary": 0,
        "fppg_overrides": {"19": 50.0},
    }
    first = _names(generate_lineups(path, **kwargs))
    second = _names(generate_lineups(path, **kwargs))
    assert first == second
    assert "Mike Gesicki" in first
    plain = _names(generate_lineups(path, count=1, max_exposure=1.0, min_salary=0))
    assert "Mike Gesicki" not in plain


def _write_pool(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for row in POOL:
            player_id, first, last, pos, team, salary, fppg, opp = row
            game = f"{team}@{opp} 01:00PM ET"
            writer.writerow([player_id, first, last, pos, team, salary, fppg, game, "", opp])
    return path


def _names(lineups) -> tuple[str, ...]:
    lineup = lineups[0]
    return tuple(player.full_name for player in lineup.players)
