import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.cli import main
from ceminidfs.models.ownership import (
    OwnershipCalibration,
    fit_ownership_calibration,
    load_ownership_calibration,
    project_ownership,
    project_ownership_calibrated,
    save_ownership_calibration,
)
from ceminidfs.pipeline.engine import normalize_join_key
from ceminidfs.pipeline.project import project_week


def test_higher_projection_salary_ratio_gets_higher_ownership_within_position():
    rows = [
        {"fd_position": "WR", "fd_salary": "8000", "fd_projection": "16.0"},
        {"fd_position": "WR", "fd_salary": "6000", "fd_projection": "15.0"},
    ]

    project_ownership(rows)

    assert float(rows[1]["Projected Ownership"]) > float(rows[0]["Projected Ownership"])


def test_rb_group_ownership_sums_to_two_slots():
    rows = [
        {"fd_position": "RB", "fd_salary": "9000", "fd_projection": "20.0"},
        {"fd_position": "RB", "fd_salary": "7000", "fd_projection": "15.0"},
        {"fd_position": "RB", "fd_salary": "5000", "fd_projection": "11.0"},
    ]

    project_ownership(rows)

    total = sum(float(row["Projected Ownership"]) for row in rows)
    assert total == pytest.approx(200.0, abs=0.2)


def test_fit_ownership_calibration_projects_paid_labels(tmp_path: Path):
    rows = [
        _row("Patrick Mahomes", "KC", "QB", 8500, 22.0),
        _row("Josh Allen", "BUF", "QB", 8700, 24.0),
        _row("Cheap QB", "LV", "QB", 6000, 16.0),
        _row("Travis Kelce", "KC", "TE", 7200, 14.0),
        _row("Value TE", "BUF", "TE", 4500, 10.0),
    ]
    labels = [
        _label("Patrick Mahomes", "KC", "QB", 10.0),
        _label("Josh Allen", "BUF", "QB", 16.0),
        _label("Cheap QB", "LV", "QB", 4.0),
        _label("Travis Kelce", "KC", "TE", 24.0),
        _label("Value TE", "BUF", "TE", 9.0),
    ]

    calibration = fit_ownership_calibration(labels, rows)
    out = save_ownership_calibration(calibration, tmp_path / "ownership_calibration.json")
    loaded = load_ownership_calibration(out)
    projected = project_ownership_calibrated([dict(row) for row in rows], loaded)

    by_name = {row["player_name"]: float(row["Projected Ownership"]) for row in projected}
    assert by_name["Josh Allen"] > by_name["Cheap QB"]
    assert by_name["Travis Kelce"] > by_name["Value TE"]
    assert loaded.sample_size == 5


def test_project_ownership_calibrated_falls_back_to_heuristic_without_calibration():
    rows = [
        {"fd_position": "WR", "fd_salary": "8000", "fd_projection": "16.0"},
        {"fd_position": "WR", "fd_salary": "6000", "fd_projection": "15.0"},
    ]

    project_ownership_calibrated(rows)

    assert float(rows[1]["Projected Ownership"]) > float(rows[0]["Projected Ownership"])


def test_project_week_uses_configured_ownership_calibration(tmp_path: Path):
    salary = tmp_path / "salary.csv"
    salary.write_text(
        "Id,Nickname,Position,Team,Opponent,Salary,FPPG,Injury Indicator\n"
        "1,Patrick Mahomes,QB,KC,BUF,8500,22.5,\n"
        "2,Travis Kelce,TE,KC,BUF,7200,14.1,Q\n",
        encoding="utf-8",
    )
    calibration_path = save_ownership_calibration(
        OwnershipCalibration(
            coefficients={"__global__": [33.0, 0.0, 0.0, 0.0, 0.0]},
            sample_size=2,
        ),
        tmp_path / "ownership_calibration.json",
    )

    canonical = project_week(
        2024,
        1,
        salary,
        {
            "work_dir": tmp_path,
            "allow_fppg_fallback": True,
            "projection_mode": "auto",
            "ownership": {"enabled": True, "calibration_path": str(calibration_path)},
        },
    )
    rows = list(csv.DictReader(canonical.open(encoding="utf-8")))

    assert rows[0]["Projected Ownership"] == "33.0"
    assert rows[1]["Projected Ownership"] == "33.0"


def test_ownership_calibrate_cli_writes_calibration_json(tmp_path: Path):
    salary = tmp_path / "salary.csv"
    salary.write_text(
        "Id,Nickname,Position,Team,Opponent,Salary,FPPG,Injury Indicator\n"
        "1,Patrick Mahomes,QB,KC,BUF,8500,22.5,\n"
        "2,Josh Allen,QB,BUF,KC,8700,24.0,\n",
        encoding="utf-8",
    )
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "Player,Team,Position,Own%\n"
        "Patrick Mahomes,KC,QB,10.0\n"
        "Josh Allen,BUF,QB,16.0\n",
        encoding="utf-8",
    )
    output = tmp_path / "ownership_calibration.json"

    status = main(
        [
            "ownership",
            "calibrate",
            "--labels",
            str(labels),
            "--salary",
            str(salary),
            "--season",
            "2024",
            "--week",
            "1",
            "--out",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert status == 0
    assert payload["sample_size"] == 2
    assert "__global__" in payload["coefficients"]


def _row(name: str, team: str, position: str, salary: int, projection: float) -> dict[str, object]:
    return {
        "player_name": name,
        "name": name,
        "team": team,
        "fd_position": position,
        "fd_salary": salary,
        "fd_projection": projection,
    }


def _label(name: str, team: str, position: str, ownership: float) -> dict[str, object]:
    return {
        "join_key": normalize_join_key(name, team, position),
        "player_name": name,
        "team": team,
        "position": position,
        "ownership": ownership,
    }
