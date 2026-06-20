import csv
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("pydfs_lineup_optimizer")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.export.late_swap import _normalize_teams, _players_on_locked_teams, late_swap_lineups
from ceminidfs.export.normalize import normalize_csv
from ceminidfs.export.optimize import LINEUP_HEADERS


def test_late_swap_module_imports():
    assert callable(late_swap_lineups)


def test_locked_team_normalization():
    players = [
        SimpleNamespace(team="KC", full_name="Patrick Mahomes"),
        SimpleNamespace(team="buf", full_name="Josh Allen"),
        SimpleNamespace(team=" DAL ", full_name="Dallas Cowboys"),
    ]

    assert _normalize_teams({" kc ", "BUF", ""}) == {"KC", "BUF"}
    locked = _players_on_locked_teams(players, {" kc ", "BUF"})
    assert [player.full_name for player in locked] == ["Patrick Mahomes", "Josh Allen"]


def test_late_swap_preserves_locked_team_players_from_simple_lineup_csv(tmp_path: Path):
    salary_path = Path(__file__).resolve().parent / "fixtures" / "synthetic_fd_slate.csv"
    players_path = tmp_path / "players.csv"
    normalize_csv(salary_path, players_path, site="fanduel")

    lineups_path = tmp_path / "lineups.csv"
    header = LINEUP_HEADERS["fanduel"]
    original = [
        "Patrick Mahomes",
        "Isiah Pacheco",
        "Ray Davis",
        "Rashee Rice",
        "Mack Hollins",
        "Marquez Valdes-Scantling",
        "Travis Kelce",
        "Noah Gray",
        "Kansas City Chiefs",
    ]
    with lineups_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerow(original)

    out_path = tmp_path / "late_swap.csv"
    count = late_swap_lineups(lineups_path, players_path, {" kc "}, out_path, site="fanduel", count=1)

    assert count == 1
    rows = list(csv.reader(out_path.open(encoding="utf-8")))
    assert rows[0] == header
    swapped_names = set(rows[1])
    assert {
        "Patrick Mahomes",
        "Isiah Pacheco",
        "Rashee Rice",
        "Travis Kelce",
        "Noah Gray",
        "Kansas City Chiefs",
    }.issubset(swapped_names)
