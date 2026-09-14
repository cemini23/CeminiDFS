import csv
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("pydfs_lineup_optimizer")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.export.late_swap import (
    _load_simple_lineups,
    _normalize_teams,
    _optimize_existing_lineups,
    _players_on_locked_teams,
    late_swap_lineups,
)
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


def _write_simple_lineup(path: Path, names: list[str]) -> None:
    header = LINEUP_HEADERS["fanduel"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerow(names)


def _normalized_players(tmp_path: Path) -> Path:
    salary_path = Path(__file__).resolve().parent / "fixtures" / "synthetic_fd_slate.csv"
    players_path = tmp_path / "players.csv"
    normalize_csv(salary_path, players_path, site="fanduel")
    return players_path


def _player_full_name(row: dict[str, str]) -> str:
    return f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip()


def test_late_swap_jac_alias_locks_jax(tmp_path: Path):
    players_path = _normalized_players(tmp_path)
    rows = list(csv.DictReader(players_path.open(encoding="utf-8-sig")))
    for row in rows:
        if row.get("Team") == "KC":
            row["Team"] = "JAX"
    with players_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

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
    lineups_path = tmp_path / "lineups.csv"
    _write_simple_lineup(lineups_path, original)
    out_path = tmp_path / "late_swap.csv"
    count = late_swap_lineups(lineups_path, players_path, {"JAC"}, out_path, site="fanduel", count=1)

    assert count == 1
    swapped = list(csv.reader(out_path.open(encoding="utf-8")))[1]
    assert "Patrick Mahomes" in swapped


def test_late_swap_parses_locked_player_with_zero_fppg(tmp_path: Path):
    players_path = _normalized_players(tmp_path)
    rows = list(csv.DictReader(players_path.open(encoding="utf-8-sig")))
    for row in rows:
        if _player_full_name(row) == "Patrick Mahomes":
            row["FPPG"] = "0"
    with players_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

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
    lineups_path = tmp_path / "lineups.csv"
    _write_simple_lineup(lineups_path, original)
    out_path = tmp_path / "late_swap.csv"
    count = late_swap_lineups(lineups_path, players_path, {"KC"}, out_path, site="fanduel", count=1)

    assert count == 1
    swapped = list(csv.reader(out_path.open(encoding="utf-8")))[1]
    assert "Patrick Mahomes" in swapped


def test_late_swap_exclude_unlocked_name(tmp_path: Path):
    players_path = _normalized_players(tmp_path)
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
    lineups_path = tmp_path / "lineups.csv"
    _write_simple_lineup(lineups_path, original)
    out_path = tmp_path / "late_swap.csv"
    count = late_swap_lineups(
        lineups_path,
        players_path,
        {"KC"},
        out_path,
        site="fanduel",
        count=1,
        excludes=["Stefon Diggs"],
    )

    assert count == 1
    swapped = list(csv.reader(out_path.open(encoding="utf-8")))[1]
    assert "Stefon Diggs" not in swapped
    assert "Patrick Mahomes" in swapped


def test_late_swap_two_lineups_two_lock_teams_keep_locked_names(tmp_path: Path):
    players_path = _normalized_players(tmp_path)
    header = LINEUP_HEADERS["fanduel"]
    first = [
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
    second = [
        "Josh Allen",
        "James Cook",
        "Kareem Hunt",
        "Stefon Diggs",
        "Khalil Shakir",
        "Xavier Worthy",
        "Dalton Kincaid",
        "Rashee Rice",
        "Buffalo Bills",
    ]
    lineups_path = tmp_path / "lineups.csv"
    with lineups_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerow(first)
        writer.writerow(second)

    out_path = tmp_path / "late_swap.csv"
    count = late_swap_lineups(
        lineups_path,
        players_path,
        {"KC", "BUF"},
        out_path,
        site="fanduel",
        count=2,
    )

    assert count == 2
    rows = list(csv.reader(out_path.open(encoding="utf-8")))
    assert set(rows[1]) == set(first)
    assert set(rows[2]) == set(second)


def test_simple_lineup_loader_uses_csv_reader_not_dict_reader(tmp_path: Path):
    header = LINEUP_HEADERS["fanduel"]
    names = [
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
    path = tmp_path / "lineups.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerow(names)

    with path.open(encoding="utf-8") as f:
        dict_row = next(csv.DictReader(f))
    assert list(dict_row.keys()).count("RB") == 1

    players_path = _normalized_players(tmp_path)
    from pydfs_lineup_optimizer import Site, Sport, get_optimizer

    optimizer = get_optimizer(Site.FANDUEL, Sport.FOOTBALL)
    optimizer.load_players_from_csv(str(players_path))
    loaded = _load_simple_lineups(path, optimizer.player_pool.all_players, "fanduel")
    loaded_names = [player.full_name for player in loaded[0].players]
    assert "Isiah Pacheco" in loaded_names
    assert "Ray Davis" in loaded_names


def test_optimize_existing_lineups_keeps_original_when_one_fails():
    originals = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

    class Optimizer:
        def optimize_lineups(self, lineups, max_exposure=None):
            if lineups[0].id == 2:
                raise RuntimeError("Unable to build lineup")
            return [SimpleNamespace(id=10)]

    result = _optimize_existing_lineups(Optimizer(), originals, max_exposure=0.35)

    assert result[0].id == 10
    assert result[1].id == 2
