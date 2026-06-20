from pathlib import Path

import pytest

from ceminidfs.data.salary import (
    apply_salary_fppg_placeholder,
    detect_salary_site,
    parse_salary_csv,
    parse_salary_row,
)


def test_detect_fanduel_site():
    assert detect_salary_site(["Id", "Nickname", "Position", "Salary"]) == "fanduel"
    assert detect_salary_site(["First Name", "Last Name", "Position", "Salary"]) == "fanduel"


def test_detect_draftkings_site():
    assert detect_salary_site(["Position", "Roster Position", "TeamAbbrev", "Salary"]) == "draftkings"
    assert detect_salary_site(["Position", "Name", "ID", "AvgPointsPerGame"]) == "draftkings"


def test_detect_salary_site_rejects_unknown_headers():
    with pytest.raises(ValueError, match="Unable to detect salary site"):
        detect_salary_site(["Player", "Cost"])


def test_parse_fanduel_salary_row():
    row = {
        "Id": "1",
        "Nickname": "Patrick Mahomes",
        "Position": "QB",
        "Team": "KC",
        "Opponent": "BUF",
        "Salary": "8500",
        "FPPG": "22.5",
        "Injury Indicator": "",
    }

    parsed = parse_salary_row(row, "fd", 2024, 1)

    assert parsed["slate_id"] == "2024_w1"
    assert parsed["player_key"] == "1"
    assert parsed["name"] == "Patrick Mahomes"
    assert parsed["player_name"] == "Patrick Mahomes"
    assert parsed["fd_id"] == "1"
    assert parsed["fd_position"] == "QB"
    assert parsed["fd_salary"] == 8500
    assert parsed["fd_projection"] == ""
    assert parsed["dk_id"] == ""
    assert parsed["team"] == "KC"
    assert parsed["opp"] == "BUF"
    assert parsed["game"] == "KC@BUF"
    assert parsed["injury_status"] == ""


def test_parse_draftkings_salary_row():
    row = {
        "Position": "QB",
        "Name": "Josh Allen",
        "ID": "12345",
        "Roster Position": "QB",
        "Salary": "8200",
        "Game Info": "BUF@MIA",
        "TeamAbbrev": "BUF",
        "AvgPointsPerGame": "24.5",
    }

    parsed = parse_salary_row(row, "draftkings", 2024, 1)

    assert parsed["slate_id"] == "2024_w1"
    assert parsed["player_key"] == "12345"
    assert parsed["name"] == "Josh Allen"
    assert parsed["fd_id"] == ""
    assert parsed["dk_id"] == "12345"
    assert parsed["dk_position"] == "QB"
    assert parsed["dk_salary"] == 8200
    assert parsed["dk_projection"] == ""
    assert parsed["team"] == "BUF"
    assert parsed["opp"] == "MIA"
    assert parsed["game"] == "BUF@MIA"


def test_apply_salary_fppg_placeholder_fills_fd_projection():
    rows = [
        {
            "fd_projection": "",
            "dk_projection": "",
            "salary_fppg": 22.5,
        }
    ]

    filled = apply_salary_fppg_placeholder(rows, "fanduel")

    assert filled[0]["fd_projection"] == 22.5
    assert filled[0]["dk_projection"] == ""


def test_parse_salary_csv_file(tmp_path: Path):
    salary = tmp_path / "fd_salary.csv"
    salary.write_text(
        "Id,Nickname,Position,Team,Opponent,Salary,FPPG,Injury Indicator\n"
        "1,Patrick Mahomes,QB,KC,BUF,8500,22.5,\n",
        encoding="utf-8",
    )

    rows = parse_salary_csv(salary, 2024, 1)

    assert len(rows) == 1
    assert rows[0]["fd_id"] == "1"
    assert rows[0]["fd_projection"] == ""
    assert rows[0]["salary_fppg"] == 22.5


def test_parse_salary_csv_rejects_empty_file(tmp_path: Path):
    salary = tmp_path / "empty.csv"
    salary.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty CSV"):
        parse_salary_csv(salary, 2024, 1)
