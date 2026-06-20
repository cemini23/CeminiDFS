import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.ownership import project_ownership


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
