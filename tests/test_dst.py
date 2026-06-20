import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.dst import apply_dst_projections, project_dst_fantasy_points
from ceminidfs.models.scoring import fd_dst_points_allowed


def test_fd_dst_points_allowed_tiers():
    assert fd_dst_points_allowed(0) == 10.0
    assert fd_dst_points_allowed(6) == 7.0
    assert fd_dst_points_allowed(24) == 0.0
    assert fd_dst_points_allowed(35) == -4.0


def test_project_dst_fantasy_points_uses_opponent_implied_total():
    fd, dk = project_dst_fantasy_points(
        team="KC",
        opponent="BUF",
        opponent_implied_total=17.0,
    )

    assert fd > 0
    assert dk == fd
    assert fd > fd_dst_points_allowed(17.0)


def test_apply_dst_projections_marks_model_source():
    vegas = pd.DataFrame(
        [
            {
                "home_team": "KC",
                "away_team": "BUF",
                "home_implied_total": 26.0,
                "away_implied_total": 23.5,
            }
        ]
    )
    rows = [
        {
            "team": "KC",
            "fd_position": "DEF",
            "opp": "BUF",
            "fd_projection": "",
            "dk_projection": "",
        }
    ]

    projected = apply_dst_projections(rows, vegas)

    assert projected[0]["projection_source"] == "dst_model"
    assert float(projected[0]["fd_projection"]) > 0
