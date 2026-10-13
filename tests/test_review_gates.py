import csv
from pathlib import Path

import pandas as pd

from ceminidfs.cli import build_parser
from ceminidfs.export.optimize import LINEUP_HEADERS
from ceminidfs.export.review_gates import (
    PROJECTION_BANDS_HEADER,
    QB_STARTER_HEADER,
    opponent_context_from_pbp,
)
from ceminidfs.export.review_reports import maybe_write_review_reports
from ceminidfs.models.simulate import add_simulation_columns

FD_HEADER = LINEUP_HEADERS["fanduel"]


def _players(path: Path) -> Path:
    rows = [
        _row("1", "Case", "Keenum", "QB", "CHI", salary="4000", fppg="0.0", snap="0", starter="false"),
        _row("2", "Josh", "Allen", "QB", "BUF", salary="8000", fppg="22.0", snap="0.98", starter="true"),
        _row(
            "3",
            "Khalil",
            "Shakir",
            "WR",
            "BUF",
            salary="5500",
            fppg="9.0",
            share="0.05",
            adot="4.0",
            p85="14.0",
            p15="0.2",
        ),
        _row(
            "4",
            "Dalton",
            "Kincaid",
            "TE",
            "BUF",
            salary="6000",
            fppg="8.0",
            share="0.22",
            adot="9.5",
            p85="16.0",
            p15="4.0",
        ),
        _row("5", "James", "Cook", "RB", "BUF", salary="7000", fppg="15.0", p85="24.0", p15="8.0"),
        _row("6", "Josh", "Palmer", "WR", "BUF", salary="4500", fppg="6.0", p85="12.0", p15="0.4"),
        _row("7", "Las Vegas", "Raiders", "D", "LV", salary="3000", fppg="5.0", opponent="BUF"),
        _row("8", "Buffalo", "Bills", "D", "BUF", salary="3200", fppg="6.0", opponent="LV"),
    ]
    rows[0]["starter_change_hours"] = "10"
    rows[6]["pass_multiplier"] = "1.0400"
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(
    player_id: str,
    first: str,
    last: str,
    position: str,
    team: str,
    *,
    salary: str,
    fppg: str,
    snap: str = "",
    starter: str = "",
    share: str = "",
    adot: str = "",
    p85: str = "",
    p15: str = "",
    opponent: str = "",
) -> dict[str, str]:
    return {
        "Id": player_id,
        "First Name": first,
        "Last Name": last,
        "Position": position,
        "Team": team,
        "Salary": salary,
        "FPPG": fppg,
        "Game": "BUF@LV",
        "Injury Indicator": "",
        "Opponent": opponent,
        "is_qb_starter": starter,
        "snap_share": snap,
        "l3_target_share": share,
        "adot": adot,
        "p85": p85,
        "p15": p15,
        "starter_change_hours": "",
        "pass_multiplier": "",
    }


def _lineups(path: Path) -> Path:
    keenum = [
        "Case Keenum",
        "James Cook",
        "Josh Palmer",
        "Khalil Shakir",
        "Khalil Shakir",
        "Josh Palmer",
        "Dalton Kincaid",
        "Josh Palmer",
        "Las Vegas Raiders",
    ]
    allen = [
        "Josh Allen",
        "James Cook",
        "Josh Palmer",
        "Khalil Shakir",
        "Josh Palmer",
        "Josh Palmer",
        "Dalton Kincaid",
        "Khalil Shakir",
        "Las Vegas Raiders",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(FD_HEADER)
        writer.writerow(keenum)
        writer.writerow(allen)
    return path


def _read(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]


def test_week4_gates_report_and_do_not_change_the_projection(tmp_path: Path):
    players = _players(tmp_path / "players.csv")
    lineups = _lineups(tmp_path / "lineups.csv")
    before = players.read_text(encoding="utf-8")

    written = maybe_write_review_reports(
        lineups,
        players,
        flag_qb_starter=True,
        flag_stack_concentration=True,
        flag_correlated_pairs=True,
        defense_context_report=True,
        projection_bands=True,
        environment=None,
    )
    assert players.read_text(encoding="utf-8") == before
    names = {path.name for path in written}
    assert "qb_starter_report.csv" in names
    assert "stack_concentration_report.csv" in names
    assert "correlated_pair_report.csv" in names
    assert "defense_context_report.csv" in names
    assert "projection_bands.csv" in names

    qb_header, qb_rows = _read(tmp_path / "qb_starter_report.csv")
    assert qb_header == QB_STARTER_HEADER
    by_qb = {row[0]: row for row in qb_rows}
    assert "starter_not_confirmed" in by_qb["Case Keenum"][5]
    assert "snap_share_below_90" in by_qb["Case Keenum"][5]
    assert "starter_change_72h" in by_qb["Case Keenum"][5]
    assert by_qb["Josh Allen"][5] == ""
    assert "no_starter_change_timestamp" in by_qb["Josh Allen"][6]

    _share_header, share_rows = _read(tmp_path / "stack_concentration_report.csv")
    shakir = [row for row in share_rows if row[2] == "Khalil Shakir"]
    assert shakir
    assert shakir[0][5] == "0.05"
    assert "low_target_share" in shakir[0][7]
    assert "low_adot" in shakir[0][7]
    kincaid = [row for row in share_rows if row[2] == "Dalton Kincaid"]
    assert kincaid
    assert kincaid[0][5] == "0.22"
    assert kincaid[0][7] == ""

    _pair_header, pair_rows = _read(tmp_path / "correlated_pair_report.csv")
    assert pair_rows == [["Dalton Kincaid", "Las Vegas Raiders", "2", "1 2", "identical_te_dst_pair"]]

    _dst_header, dst_rows = _read(tmp_path / "defense_context_report.csv")
    raiders = next(row for row in dst_rows if row[0] == "Las Vegas Raiders")
    assert raiders[3] == "1.0400"
    assert raiders[7] == "" or raiders[7] == "0" or raiders[7]
    assert "fr_source=opponent_fumbles_lost" in raiders[8]

    band_header, band_rows = _read(tmp_path / "projection_bands.csv")
    assert band_header == PROJECTION_BANDS_HEADER
    by_name = {row[0]: row for row in band_rows}
    assert by_name["Khalil Shakir"][4] == "9.0"
    assert by_name["Khalil Shakir"][7] == "p15_near_zero"
    assert by_name["Josh Palmer"][7] == "p15_near_zero"
    assert by_name["James Cook"][4] == "15.0"
    assert by_name["James Cook"][7] == ""


def test_opponent_context_keeps_fumbles_lost_only():
    pbp = pd.DataFrame(
        {
            "week": [1, 1, 1],
            "posteam": ["KC", "KC", "KC"],
            "pass_attempt": [1, 1, 0],
            "sack": [1, 0, 0],
            "interception": [0, 1, 0],
            "fumble_lost": [0, 0, 1],
            "fumble": [1, 1, 1],
        }
    )

    context = opponent_context_from_pbp(pbp, through_week=2)

    assert context["KC"]["sack_pct"] == "0.5000"
    assert context["KC"]["fumbles_lost"] == "1"
    assert "fumble" not in context["KC"]


def test_cli_help_lists_week4_gates():
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
    )
    for command in ("optimize", "run", "late-swap", "review"):
        help_text = subparsers.choices[command].format_help()
        assert "--flag-qb-starter" in help_text
        assert "--flag-stack-concentration" in help_text
        assert "--flag-correlated-pairs" in help_text
        assert "--defense-context-report" in help_text
        assert "--projection-bands" in help_text


def test_simulation_adds_bands_without_changing_the_mean():
    frame = pd.DataFrame(
        [
            {"player_id": "wr", "fd_projection": 9.0, "team": "BUF", "position": "WR"},
        ]
    )

    simulated = add_simulation_columns(frame, n_iterations=400, seed=3)

    assert simulated.loc[0, "fd_projection"] == 9.0
    assert simulated.loc[0, "p15"] <= simulated.loc[0, "p85"]
    assert "p15" in simulated.columns
    assert "p85" in simulated.columns
