import csv
import inspect
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("pydfs_lineup_optimizer")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.export.late_swap import _load_simple_lineups, late_swap_lineups
from ceminidfs.export.lineup_report import format_lineup_report, lineup_stack_badges
from ceminidfs.export.normalize import normalize_csv
from ceminidfs.export.optimize import (
    LINEUP_HEADERS,
    cell_format,
    optimize_lineups,
    select_with_exposure_caps,
)

UPLOAD_CELL = re.compile(r"^.+ \(\S+\)$")
SALARY_PATH = Path(__file__).resolve().parent / "fixtures" / "synthetic_fd_slate.csv"


def _player(
    name: str,
    team: str,
    positions: list[str],
    *,
    injured: bool = False,
    player_id: str = "",
) -> SimpleNamespace:
    first, _, last = name.partition(" ")
    return SimpleNamespace(
        full_name=name,
        first_name=first,
        last_name=last or first,
        team=team,
        positions=positions,
        lineup_position=positions[0] if positions else "",
        is_injured=injured,
        id=player_id,
        game_info=None,
    )


def _full_name(row: dict[str, str]) -> str:
    return f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip()


def test_optimize_writes_name_upload_and_id_files(tmp_path: Path):
    players_path = tmp_path / "players.csv"
    normalize_csv(SALARY_PATH, players_path, site="fanduel")
    source_ids = {row["Id"] for row in csv.DictReader(SALARY_PATH.open(encoding="utf-8-sig"))}

    out_path = tmp_path / "lineups.csv"
    written = optimize_lineups(
        players_path,
        out_path,
        site="fanduel",
        count=2,
        max_exposure=1.0,
        min_salary=0,
    )
    assert written == 2

    upload_path = tmp_path / "lineups_fanduel_upload.csv"
    ids_path = tmp_path / "lineups_fanduel_ids.csv"
    assert upload_path.is_file()
    assert ids_path.is_file()

    with upload_path.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        upload_rows = list(reader)
    with ids_path.open(encoding="utf-8") as f:
        id_rows = list(csv.reader(f))[1:]

    assert header == LINEUP_HEADERS["fanduel"]
    assert header.count("RB") == 2
    assert len(upload_rows) == 2
    for row in upload_rows:
        assert all(UPLOAD_CELL.match(cell) for cell in row)
        for cell in row:
            player_id = cell[cell.rfind("(") + 1 : cell.rfind(")")]
            assert player_id in source_ids
    for row in id_rows:
        assert all(cell in source_ids for cell in row)


def test_dict_reader_collapses_duplicate_rb_production_keeps_both(tmp_path: Path):
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
    lineups_path = tmp_path / "lineups.csv"
    with lineups_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerow(names)

    with lineups_path.open(encoding="utf-8") as f:
        dict_rows = list(csv.DictReader(f))
    assert list(dict_rows[0].keys()).count("RB") == 1
    assert dict_rows[0]["RB"] == "Ray Davis"

    src = inspect.getsource(_load_simple_lineups)
    assert "DictReader" not in src
    assert "csv.reader" in src

    players_path = tmp_path / "players.csv"
    normalize_csv(SALARY_PATH, players_path, site="fanduel")
    from pydfs_lineup_optimizer import Site, Sport, get_optimizer

    optimizer = get_optimizer(Site.FANDUEL, Sport.FOOTBALL)
    optimizer.load_players_from_csv(str(players_path))
    loaded = _load_simple_lineups(lineups_path, optimizer.player_pool.all_players, "fanduel")
    loaded_names = [player.full_name for player in loaded[0].players]
    assert loaded_names.count("Isiah Pacheco") + loaded_names.count("Ray Davis") == 2
    assert "Isiah Pacheco" in loaded_names
    assert "Ray Davis" in loaded_names


def test_late_swap_loads_name_id_and_id_only_and_writes_upload(tmp_path: Path):
    players_path = tmp_path / "players.csv"
    normalize_csv(SALARY_PATH, players_path, site="fanduel")
    rows = list(csv.DictReader(players_path.open(encoding="utf-8-sig")))
    ids = {_full_name(row): row["Id"] for row in rows}

    header = LINEUP_HEADERS["fanduel"]
    name_row = [
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
    name_id_row = [
        f"Josh Allen ({ids['Josh Allen']})",
        "James Cook",
        "Kareem Hunt",
        "Stefon Diggs",
        "Khalil Shakir",
        "Xavier Worthy",
        "Dalton Kincaid",
        "Rashee Rice",
        "Buffalo Bills",
    ]
    id_row = [ids[name] for name in name_row]

    lineups_path = tmp_path / "lineups.csv"
    with lineups_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerow(name_id_row)
        writer.writerow(id_row)

    out_path = tmp_path / "late_swap.csv"
    count = late_swap_lineups(
        lineups_path,
        players_path,
        {"BUF"},
        out_path,
        site="fanduel",
        count=2,
    )
    assert count == 2

    swapped = list(csv.reader(out_path.open(encoding="utf-8")))
    assert swapped[0] == header
    for row in swapped[1:]:
        assert "Josh Allen" in row
        assert "Buffalo Bills" in row

    upload_path = tmp_path / "late_swap_fanduel_upload.csv"
    assert upload_path.is_file()
    upload_rows = list(csv.reader(upload_path.open(encoding="utf-8")))[1:]
    assert all(UPLOAD_CELL.match(cell) for row in upload_rows for cell in row)
    assert any(cell.startswith("Josh Allen (") for row in upload_rows for cell in row)


def test_report_lists_questionable_player_lineup_count():
    q_wr = _player("Q Wideout", "CHI", ["WR"], injured=True)
    qb = _player("Healthy QB", "KC", ["QB"])
    wr = _player("Healthy WR", "KC", ["WR"])
    lineups = [
        SimpleNamespace(players=[qb, q_wr, wr]),
        SimpleNamespace(players=[qb, q_wr]),
        SimpleNamespace(players=[qb, wr]),
        SimpleNamespace(players=[qb, wr]),
        SimpleNamespace(players=[qb, wr]),
    ]

    text = format_lineup_report(lineups)

    assert "Questionable in book" in text
    assert "Q Wideout" in text
    assert "    2  Q Wideout" in text
    assert "Questionable in book: none" not in text


def test_max_team_exposure_cap_limits_constructed_set():
    chi = _player("CHI WR", "CHI", ["WR"])
    kc = _player("KC QB", "KC", ["QB"])
    lineups = [SimpleNamespace(players=[chi, kc]) for _ in range(8)]
    lineups.extend(SimpleNamespace(players=[kc]) for _ in range(2))

    selected = select_with_exposure_caps(lineups, 10, max_team_exposure=0.4)
    chi_count = sum(
        1 for lineup in selected if any(player.team == "CHI" for player in lineup.players)
    )
    assert chi_count <= 4
    assert len(selected) <= 10


def test_chalk_badge_requires_two_wrs_not_te():
    burrow = SimpleNamespace(
        players=[
            _player("Joe Burrow", "CIN", ["QB"]),
            _player("Ja'Marr Chase", "CIN", ["WR"]),
            _player("Tee Higgins", "CIN", ["WR"]),
        ]
    )
    allen = SimpleNamespace(
        players=[
            _player("Josh Allen", "BUF", ["QB"]),
            _player("Khalil Shakir", "BUF", ["WR"]),
            _player("Dalton Kincaid", "BUF", ["TE"]),
        ]
    )

    assert "CHALK-QB-WR-WR" in lineup_stack_badges(burrow)
    assert "CHALK-QB-WR-WR" not in lineup_stack_badges(allen)


def test_report_warns_when_team_share_above_half():
    chi = _player("CHI WR", "CHI", ["WR"])
    kc = _player("KC QB", "KC", ["QB"])
    lineups = [SimpleNamespace(players=[chi, kc]) for _ in range(7)]
    lineups.extend(SimpleNamespace(players=[kc]) for _ in range(3))

    text = format_lineup_report(lineups)
    assert "WARNING: CHI in 70% of lineups (above 50%)" in text


def test_report_prints_all_lineups_when_count_is_20_or_fewer():
    qb = _player("Healthy QB", "KC", ["QB"])
    lineups = [SimpleNamespace(players=[qb]) for _ in range(12)]
    text = format_lineup_report(lineups)
    assert "All 12 lineups" in text
    assert "12. " in text


def test_cell_format_name_id_requires_player_id():
    player = _player("No Id", "KC", ["QB"], player_id="")
    assert cell_format(player, "name") == "No Id"
    with pytest.raises(ValueError, match="No Id"):
        cell_format(player, "name_id")
    with pytest.raises(ValueError, match="No Id"):
        cell_format(player, "id")
