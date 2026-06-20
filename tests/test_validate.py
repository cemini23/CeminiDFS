import csv
from pathlib import Path

import pytest

from ceminidfs.export.optimize import LINEUP_HEADERS
from ceminidfs.orchestrator.validate import validate_lineups_csv


def _write_lineups(path: Path, rows: list[list[str]], site: str = "fanduel") -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(LINEUP_HEADERS[site])
        writer.writerows(rows)


def _valid_row(suffix: str) -> list[str]:
    return [
        f"QB {suffix}",
        f"RB1 {suffix}",
        f"RB2 {suffix}",
        f"WR1 {suffix}",
        f"WR2 {suffix}",
        f"WR3 {suffix}",
        f"TE {suffix}",
        f"FLEX {suffix}",
        f"DEF {suffix}",
    ]


def test_validate_lineups_csv_accepts_expected_file(tmp_path: Path):
    path = tmp_path / "lineups.csv"
    _write_lineups(path, [_valid_row("a"), _valid_row("b")])

    result = validate_lineups_csv(path, expected_count=2)

    assert result["lineup_count"] == 2
    assert result["site"] == "fanduel"
    assert result["valid"] is True
    assert result["empty_slots"] == 0


def test_validate_lineups_csv_requires_existing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="Lineups CSV not found"):
        validate_lineups_csv(tmp_path / "missing.csv", expected_count=1)


def test_validate_lineups_csv_rejects_header_mismatch(tmp_path: Path):
    path = tmp_path / "lineups.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["QB", "RB"])
        writer.writerow(["Player A", "Player B"])

    with pytest.raises(ValueError, match="header mismatch"):
        validate_lineups_csv(path, expected_count=1)


def test_validate_lineups_csv_rejects_wrong_count(tmp_path: Path):
    path = tmp_path / "lineups.csv"
    _write_lineups(path, [_valid_row("a")])

    with pytest.raises(ValueError, match="Expected 2 lineups, found 1"):
        validate_lineups_csv(path, expected_count=2)


def test_validate_lineups_csv_rejects_duplicate_players(tmp_path: Path):
    path = tmp_path / "lineups.csv"
    row = _valid_row("a")
    row[1] = row[0]
    _write_lineups(path, [row])

    with pytest.raises(ValueError, match="duplicate players"):
        validate_lineups_csv(path, expected_count=1)


def test_validate_lineups_csv_checks_salary_cap(tmp_path: Path):
    lineups = tmp_path / "lineups.csv"
    players = tmp_path / "players.csv"
    _write_lineups(lineups, [_valid_row("a")])
    with players.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Nickname", "Salary"])
        for slot in _valid_row("a"):
            writer.writerow([slot, 9000])

    with pytest.raises(ValueError, match="salary cap"):
        validate_lineups_csv(lineups, expected_count=1, players_csv=players)


def test_validate_lineups_csv_rejects_empty_slots(tmp_path: Path):
    path = tmp_path / "lineups.csv"
    row = _valid_row("a")
    row[3] = ""
    _write_lineups(path, [row])

    with pytest.raises(ValueError, match="empty required slot"):
        validate_lineups_csv(path, expected_count=1)
