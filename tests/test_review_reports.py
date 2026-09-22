import argparse
import csv
import inspect
import shutil
from pathlib import Path
from unittest.mock import patch

from ceminidfs.cli import build_parser, main
from ceminidfs.export.optimize import LINEUP_HEADERS
from ceminidfs.export.review_reports import (
    DART_CEILING_HEADER,
    DUPLICATE_CORE_HEADER,
    LATE_SWAP_ALERT_HEADER,
    LEVERAGE_FADE_HEADER,
    STACK_FRAGILITY_HEADER,
    maybe_write_review_reports,
    parse_lineup_csv,
)

FD_HEADER = LINEUP_HEADERS["fanduel"]
PLAYERS_HEADER = [
    "Id",
    "First Name",
    "Last Name",
    "Position",
    "Team",
    "Salary",
    "FPPG",
    "Game",
    "Injury Indicator",
    "Projected Ownership",
    "Opponent",
]


def _player(
    player_id: str,
    first: str,
    last: str,
    position: str,
    team: str,
    *,
    game: str = "",
    injury: str = "",
    own: str = "5.0",
    opponent: str = "",
    salary: str = "6000",
    fppg: str = "10.0",
) -> dict[str, str]:
    return {
        "Id": player_id,
        "First Name": first,
        "Last Name": last,
        "Position": position,
        "Team": team,
        "Salary": salary,
        "FPPG": fppg,
        "Game": game,
        "Injury Indicator": injury,
        "Projected Ownership": own,
        "Opponent": opponent,
    }


def _pool() -> list[dict[str, str]]:
    return [
        _player("1", "Joe", "Burrow", "QB", "CIN", game="CIN@TB 01:00PM ET", opponent="TB"),
        _player("2", "Ja'Marr", "Chase", "WR", "CIN", game="CIN@TB 01:00PM ET", opponent="TB"),
        _player("3", "Tee", "Higgins", "WR", "CIN", game="CIN@TB 01:00PM ET", opponent="TB"),
        _player("4", "Mike", "Evans", "WR", "TB", game="CIN@TB 01:00PM ET", opponent="CIN"),
        _player("5", "Josh", "Allen", "QB", "BUF", game="BUF@NYJ 01:00PM ET", opponent="NYJ"),
        _player("6", "Khalil", "Shakir", "WR", "BUF", game="BUF@NYJ 01:00PM ET", opponent="NYJ"),
        _player("7", "Dalton", "Kincaid", "TE", "BUF", game="BUF@NYJ 01:00PM ET", opponent="NYJ"),
        _player("8", "Patrick", "Mahomes", "QB", "KC", game="LAC@KC 04:25PM ET", opponent="LAC"),
        _player("9", "Isiah", "Pacheco", "RB", "KC", game="LAC@KC 04:25PM ET", opponent="LAC"),
        _player("10", "Ray", "Davis", "RB", "BUF", game="BUF@NYJ 01:00PM ET", opponent="NYJ"),
        _player("11", "Rashee", "Rice", "WR", "KC", game="LAC@KC 04:25PM ET", opponent="LAC"),
        _player("12", "Xavier", "Worthy", "WR", "KC", game="LAC@KC 04:25PM ET", opponent="LAC"),
        _player("13", "Travis", "Kelce", "TE", "KC", game="LAC@KC 04:25PM ET", opponent="LAC"),
        _player("14", "Noah", "Gray", "TE", "KC", game="LAC@KC 04:25PM ET", opponent="LAC"),
        _player("15", "Kansas City", "Chiefs", "D", "KC", game="LAC@KC 04:25PM ET", opponent="LAC"),
        _player(
            "16",
            "Rome",
            "Odunze",
            "WR",
            "CHI",
            game="CHI@MIN 01:00PM ET",
            injury="Q",
            opponent="MIN",
        ),
        _player(
            "17",
            "Chalk",
            "Wideout",
            "WR",
            "SEA",
            game="SEA@ARI 04:05PM ET",
            own="25.0",
            opponent="ARI",
        ),
        _player(
            "18",
            "Fade",
            "Wideout",
            "WR",
            "ARI",
            game="SEA@ARI 04:05PM ET",
            own="25.0",
            opponent="SEA",
        ),
        _player("19", "James", "Cook", "RB", "BUF", game="BUF@NYJ 01:00PM ET", opponent="NYJ"),
        _player("20", "Kareem", "Hunt", "RB", "KC", game="LAC@KC 04:25PM ET", opponent="LAC"),
    ]


def _write_players(path: Path, rows: list[dict[str, str]] | None = None) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAYERS_HEADER)
        writer.writeheader()
        writer.writerows(rows or _pool())
    return path


def _write_lineups(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(FD_HEADER)
        writer.writerows(rows)
    return path


def _classic(
    qb: str,
    wr1: str,
    wr2: str,
    wr3: str,
    *,
    te: str = "Travis Kelce",
    flex: str = "Noah Gray",
    dst: str = "Kansas City Chiefs",
    rb1: str = "Isiah Pacheco",
    rb2: str = "Ray Davis",
) -> list[str]:
    return [qb, rb1, rb2, wr1, wr2, wr3, te, flex, dst]


def _read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]


def test_burrow_chase_higgins_chalk_row(tmp_path: Path):
    players = _write_players(tmp_path / "players.csv")
    lineups = _write_lineups(
        tmp_path / "lineups.csv",
        [_classic("Joe Burrow", "Ja'Marr Chase", "Tee Higgins", "Rashee Rice")],
    )

    maybe_write_review_reports(lineups, players, flag_wr_triples=True)

    header, rows = _read_csv(tmp_path / "stack_fragility_report.csv")
    assert header == STACK_FRAGILITY_HEADER
    assert len(rows) == 1
    assert rows[0][0] == "1"
    assert rows[0][1] == "CIN@TB"
    assert "Ja'Marr Chase" in rows[0][2]
    assert "Tee Higgins" in rows[0][2]
    assert rows[0][3] == "2"
    assert rows[0][4] == "Y"
    assert rows[0][5] == "do_not_auto_apply"


def test_allen_shakir_kincaid_not_chalk(tmp_path: Path):
    players = _write_players(tmp_path / "players.csv")
    lineups = _write_lineups(
        tmp_path / "lineups.csv",
        [
            _classic(
                "Josh Allen",
                "Khalil Shakir",
                "Rashee Rice",
                "Xavier Worthy",
                te="Dalton Kincaid",
            )
        ],
    )

    maybe_write_review_reports(lineups, players, flag_wr_triples=True)

    header, rows = _read_csv(tmp_path / "stack_fragility_report.csv")
    assert header == STACK_FRAGILITY_HEADER
    assert rows == []


def test_three_wrs_same_game_two_teams(tmp_path: Path):
    players = _write_players(tmp_path / "players.csv")
    lineups = _write_lineups(
        tmp_path / "lineups.csv",
        [_classic("Patrick Mahomes", "Ja'Marr Chase", "Tee Higgins", "Mike Evans")],
    )

    maybe_write_review_reports(lineups, players, flag_wr_triples=True)

    header, rows = _read_csv(tmp_path / "stack_fragility_report.csv")
    assert header == STACK_FRAGILITY_HEADER
    assert len(rows) == 1
    assert rows[0][1] == "CIN@TB"
    assert rows[0][3] == "3"
    assert rows[0][4] == "N"
    names = rows[0][2]
    assert "Ja'Marr Chase" in names
    assert "Tee Higgins" in names
    assert "Mike Evans" in names


def test_late_swap_audit_q_wr_count_does_not_change_lineups(tmp_path: Path):
    players = _write_players(tmp_path / "players.csv")
    q_row = _classic("Patrick Mahomes", "Rome Odunze", "Rashee Rice", "Xavier Worthy")
    healthy = _classic("Patrick Mahomes", "Rashee Rice", "Xavier Worthy", "Khalil Shakir")
    lineups = _write_lineups(
        tmp_path / "lineups.csv",
        [q_row, healthy, q_row, healthy, healthy],
    )
    original = lineups.read_bytes()
    backup = tmp_path / "lineups.copy.csv"
    shutil.copyfile(lineups, backup)

    maybe_write_review_reports(lineups, players, late_swap_audit=True)

    header, rows = _read_csv(tmp_path / "late_swap_alert_report.csv")
    assert header == LATE_SWAP_ALERT_HEADER
    assert len(rows) == 1
    assert rows[0][0] == "Rome Odunze"
    assert rows[0][1] == "Q"
    assert rows[0][2] == "2"
    assert lineups.read_bytes() == original
    assert lineups.read_bytes() == backup.read_bytes()


def test_negative_leverage_flag_by_exposure(tmp_path: Path):
    players = _write_players(tmp_path / "players.csv")
    chalk = _classic("Patrick Mahomes", "Chalk Wideout", "Rashee Rice", "Xavier Worthy")
    fade = _classic("Patrick Mahomes", "Fade Wideout", "Rashee Rice", "Xavier Worthy")
    other = _classic("Josh Allen", "Khalil Shakir", "Rashee Rice", "Xavier Worthy")
    lineups = _write_lineups(
        tmp_path / "lineups.csv",
        [chalk, chalk, chalk, chalk, chalk, fade, other, other, other, other],
    )

    maybe_write_review_reports(lineups, players, ownership_fade_report=True)

    header, rows = _read_csv(tmp_path / "leverage_fade_matrix.csv")
    assert header == LEVERAGE_FADE_HEADER
    by_name = {row[0]: row for row in rows}
    chalk_row = by_name["Chalk Wideout"]
    fade_row = by_name["Fade Wideout"]
    assert chalk_row[1] == "50.0"
    assert chalk_row[2] == "25.0"
    assert chalk_row[4] == "NEGATIVE_LEVERAGE"
    assert fade_row[1] == "10.0"
    assert fade_row[2] == "25.0"
    assert fade_row[4] == ""


def test_cli_help_lists_flags_and_review_does_not_optimize(tmp_path: Path):
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    for command in ("optimize", "run", "late-swap", "review"):
        help_text = subparsers.choices[command].format_help()
        assert "--flag-wr-triples" in help_text
        assert "--late-swap-audit" in help_text
        assert "--ownership-fade-report" in help_text
        assert "--flag-duplicate-cores" in help_text
        assert "--dart-ceiling-report" in help_text

    optimize = parser.parse_args(["optimize", "--csv", "p.csv", "--out", "l.csv"])
    assert optimize.flag_wr_triples is False
    assert optimize.late_swap_audit is False
    assert optimize.ownership_fade_report is False
    assert optimize.flag_duplicate_cores is False
    assert optimize.dart_ceiling_report is False

    review = parser.parse_args(["review", "--lineups", "l.csv", "--players", "p.csv"])
    assert review.flag_duplicate_cores is False
    assert review.dart_ceiling_report is False

    src = inspect.getsource(parse_lineup_csv)
    assert "DictReader" not in src
    assert "csv.reader" in src

    players = _write_players(tmp_path / "players.csv")
    lineups = _write_lineups(
        tmp_path / "lineups.csv",
        [_classic("Joe Burrow", "Ja'Marr Chase", "Tee Higgins", "Rashee Rice")],
    )
    out_dir = tmp_path / "reports"
    out_dir.mkdir()

    with (
        patch("ceminidfs.export.optimize.optimize_lineups") as mock_optimize,
        patch("ceminidfs.orchestrator.run._run_optimize") as mock_run,
    ):
        code = main(
            [
                "review",
                "--lineups",
                str(lineups),
                "--players",
                str(players),
                "--out",
                str(out_dir),
                "--flag-wr-triples",
                "--late-swap-audit",
                "--ownership-fade-report",
            ]
        )

    assert code == 0
    mock_optimize.assert_not_called()
    mock_run.assert_not_called()
    assert (out_dir / "stack_fragility_report.csv").is_file()
    assert (out_dir / "late_swap_alert_report.csv").is_file()
    assert (out_dir / "leverage_fade_matrix.csv").is_file()
    late_header, late_rows = _read_csv(out_dir / "late_swap_alert_report.csv")
    assert late_header == LATE_SWAP_ALERT_HEADER
    assert late_rows == []


def test_duplicate_core_same_qb_and_two_rb_slots(tmp_path: Path):
    players = _write_players(tmp_path / "players.csv")
    same = _classic(
        "Josh Allen",
        "Rashee Rice",
        "Xavier Worthy",
        "Khalil Shakir",
        rb1="James Cook",
        rb2="Ray Davis",
    )
    swapped = _classic(
        "Josh Allen",
        "Rashee Rice",
        "Xavier Worthy",
        "Khalil Shakir",
        rb1="Ray Davis",
        rb2="James Cook",
    )
    other = _classic(
        "Josh Allen",
        "Rashee Rice",
        "Xavier Worthy",
        "Khalil Shakir",
        rb1="Isiah Pacheco",
        rb2="Kareem Hunt",
        flex="James Cook",
    )
    lineups = _write_lineups(tmp_path / "lineups.csv", [same, swapped, same, other])
    original = lineups.read_bytes()

    maybe_write_review_reports(lineups, players, flag_duplicate_cores=True)

    assert lineups.read_bytes() == original
    header, rows = _read_csv(tmp_path / "duplicate_core_report.csv")
    assert header == DUPLICATE_CORE_HEADER
    assert len(rows) == 1
    assert rows[0][0] == "Josh Allen"
    assert rows[0][1] == "James Cook"
    assert rows[0][2] == "Ray Davis"
    assert rows[0][3] == "3"
    assert rows[0][4] == "1,2,3"
    assert rows[0][5] == "do_not_auto_apply"


def test_duplicate_core_writes_header_when_none_exceed_two(tmp_path: Path):
    players = _write_players(tmp_path / "players.csv")
    one = _classic(
        "Josh Allen",
        "Rashee Rice",
        "Xavier Worthy",
        "Khalil Shakir",
        rb1="James Cook",
        rb2="Ray Davis",
    )
    lineups = _write_lineups(tmp_path / "lineups.csv", [one, one])

    maybe_write_review_reports(lineups, players, flag_duplicate_cores=True)

    header, rows = _read_csv(tmp_path / "duplicate_core_report.csv")
    assert header == DUPLICATE_CORE_HEADER
    assert rows == []


def test_dart_ceiling_report_ranks_existing_mean_and_does_not_invent_ceiling(tmp_path: Path):
    players = tmp_path / "players.csv"
    fieldnames = PLAYERS_HEADER + ["Ceiling"]
    pool = [
        {
            **_player("101", "Jalen", "Coker", "WR", "CAR", salary="5900", fppg="18"),
            "Ceiling": "30",
        },
        {
            **_player("102", "Ada", "Twelve", "WR", "CAR", salary="5300", fppg="12"),
            "Ceiling": "",
        },
        {
            **_player("103", "Bea", "Seven", "RB", "CAR", salary="5400", fppg="7"),
            "Ceiling": "20",
        },
        {
            **_player("104", "Cam", "Edge", "WR", "CAR", salary="$5,500", fppg="1"),
            "Ceiling": "",
        },
        {
            **_player("105", "No", "Salary", "WR", "CAR", salary="", fppg="99"),
            "Ceiling": "40",
        },
    ]
    with players.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(pool)
    lineups = _write_lineups(
        tmp_path / "lineups.csv",
        [_classic("Josh Allen", "Rashee Rice", "Xavier Worthy", "Khalil Shakir")],
    )
    original = lineups.read_bytes()

    maybe_write_review_reports(lineups, players, dart_ceiling_report=True)

    assert lineups.read_bytes() == original
    header, rows = _read_csv(tmp_path / "dart_ceiling_rank.csv")
    assert header == DART_CEILING_HEADER
    by_name = {row[0]: row for row in rows}
    assert "Jalen Coker" not in by_name
    assert "No Salary" not in by_name
    high = by_name["Ada Twelve"]
    low = by_name["Bea Seven"]
    edge = by_name["Cam Edge"]
    assert high[1] == "CAR"
    assert high[2] == "WR"
    assert high[3] == "5300"
    assert high[4] == "12"
    assert high[5] == ""
    assert high[6] == "1"
    assert high[7] == ""
    assert high[8] == "ceiling_missing"
    assert low[3] == "5400"
    assert low[4] == "7"
    assert low[5] == "20"
    assert low[6] == "2"
    assert low[7] == "1"
    assert low[8] == ""
    assert edge[3] == "$5,500"
    assert edge[6] == "3"
    assert edge[8] == "ceiling_missing"
