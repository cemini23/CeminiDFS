"""Pre-upload validation for a FanDuel GPP book."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from ceminidfs.data.availability import (
    PrelockExcludeError,
    assert_upload_ready,
    build_prelock_gate,
    upload_id_prefix,
    upload_validation_issues,
)

SALARY_HEADER = "Id,Nickname,Position,Team,Salary,FPPG,Injury Indicator"
LINEUP_HEADER = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DEF"]
PREFIX = "134251"

POOL = [
    (f"{PREFIX}-100", "Qb One", "QB", "AAA", "7000"),
    (f"{PREFIX}-101", "Rb One", "RB", "AAA", "6000"),
    (f"{PREFIX}-102", "Rb Two", "RB", "AAA", "5000"),
    (f"{PREFIX}-103", "Wr One", "WR", "AAA", "6000"),
    (f"{PREFIX}-104", "Wr Two", "WR", "AAA", "5000"),
    (f"{PREFIX}-105", "Wr Three", "WR", "BBB", "5000"),
    (f"{PREFIX}-106", "Te One", "TE", "BBB", "5000"),
    (f"{PREFIX}-107", "Flex One", "RB", "BBB", "5000"),
    (f"{PREFIX}-108", "Defense One", "D", "BBB", "4000"),
    (f"{PREFIX}-109", "Extra One", "WR", "BBB", "4000"),
    (f"{PREFIX}-110", "Extra Two", "WR", "BBB", "4000"),
]


def _write_salary(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(SALARY_HEADER.split(","))
        for player_id, name, position, team, salary in POOL:
            writer.writerow([player_id, name, position, team, salary, "12", ""])
    return path


def _token(player_id: str) -> str:
    name = next(row[1] for row in POOL if row[0] == player_id)
    return f"{name} ({player_id})"


def _lineup(ids: list[str]) -> list[str]:
    return [_token(player_id) for player_id in ids]


def _write_lineups(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(LINEUP_HEADER)
        writer.writerows(rows)
    return path


def _clean_rows() -> list[list[str]]:
    first = [f"{PREFIX}-{number}" for number in range(100, 109)]
    second = [
        f"{PREFIX}-100",
        f"{PREFIX}-101",
        f"{PREFIX}-102",
        f"{PREFIX}-103",
        f"{PREFIX}-104",
        f"{PREFIX}-107",
        f"{PREFIX}-108",
        f"{PREFIX}-109",
        f"{PREFIX}-110",
    ]
    return [_lineup(first), _lineup(second)]


def _gate(tmp_path: Path, *, scratch: Path | None = None):
    salary = _write_salary(tmp_path / "2026-11-26_fd_thu.csv")
    return build_prelock_gate(salary, scratch_csv=scratch)


def test_clean_book_passes(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    lineups = _write_lineups(tmp_path / "lineups.csv", _clean_rows())

    assert upload_validation_issues(
        lineups,
        gate,
        slate_prefix=PREFIX,
        expected_count=2,
        min_uniques=2,
    ) == []
    assert_upload_ready(
        lineups,
        gate,
        slate_prefix=PREFIX,
        expected_count=2,
        min_uniques=2,
    )


def test_duplicate_lineup_fails(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    rows = _clean_rows()
    lineups = _write_lineups(tmp_path / "lineups.csv", [rows[0], rows[0]])

    issues = upload_validation_issues(lineups, gate, slate_prefix=PREFIX)

    assert any("duplicates lineup" in issue for issue in issues)


def test_wrong_id_prefix_fails(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    rows = _clean_rows()
    rows[1][0] = "Wr One (999999-103)"
    lineups = _write_lineups(tmp_path / "lineups.csv", rows)

    issues = upload_validation_issues(lineups, gate, slate_prefix=PREFIX)

    assert any("does not start with 134251-" in issue for issue in issues)


def test_salary_over_cap_fails(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    lineups = _write_lineups(tmp_path / "lineups.csv", [_clean_rows()[0]])

    issues = upload_validation_issues(
        lineups,
        gate,
        slate_prefix=PREFIX,
        salary_cap=10000,
    )

    assert any("is above the 10000 cap" in issue for issue in issues)


def test_hard_excluded_player_fails(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch.csv"
    scratch.write_text(
        "name,team,status,exclude\nRb One,AAA,O,1\n",
        encoding="utf-8",
    )
    gate = _gate(tmp_path, scratch=scratch)
    lineups = _write_lineups(tmp_path / "lineups.csv", [_clean_rows()[0]])

    with pytest.raises(PrelockExcludeError, match="hard-excluded"):
        assert_upload_ready(lineups, gate, slate_prefix=PREFIX)


def test_unique_gap_fails(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    first = [f"{PREFIX}-{number}" for number in range(100, 109)]
    second = [
        f"{PREFIX}-100",
        f"{PREFIX}-101",
        f"{PREFIX}-102",
        f"{PREFIX}-103",
        f"{PREFIX}-104",
        f"{PREFIX}-107",
        f"{PREFIX}-108",
        f"{PREFIX}-109",
        f"{PREFIX}-105",
    ]
    lineups = _write_lineups(
        tmp_path / "lineups.csv",
        [_lineup(first), _lineup(second)],
    )

    issues = upload_validation_issues(
        lineups,
        gate,
        slate_prefix=PREFIX,
        min_uniques=2,
    )

    assert any("have 1 different players" in issue for issue in issues)


def test_upload_id_prefix_is_the_most_common_dash_prefix(tmp_path: Path) -> None:
    gate = _gate(tmp_path)

    assert upload_id_prefix(gate) == PREFIX
