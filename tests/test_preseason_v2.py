import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data.availability import (
    filter_available_roster,
    is_unavailable_status,
    unavailable_player_ids_from_salary_rows,
)
from ceminidfs.models.dst import actual_dst_fantasy_points, build_week_dst_projections
from ceminidfs.pipeline.regression_gates import RegressionGates, check_regression_gates
from ceminidfs.pipeline.calibration import CalibrationReport, ModelCalibration, PositionMetrics


def test_is_unavailable_status():
    assert is_unavailable_status("O")
    assert is_unavailable_status("Out")
    assert is_unavailable_status("Doubtful")
    assert not is_unavailable_status("Q")
    assert not is_unavailable_status("")


def test_unavailable_player_ids_from_salary_rows():
    rows = [
        {"fd_id": "qb1", "injury_status": "O"},
        {"fd_id": "wr1", "Injury Indicator": "Q"},
    ]
    assert unavailable_player_ids_from_salary_rows(rows) == {"qb1"}


def test_filter_available_roster():
    roster = pd.DataFrame(
        [
            {"player_id": "qb1", "player_name": "QB", "team": "KC", "position": "QB"},
            {"player_id": "wr1", "player_name": "WR", "team": "KC", "position": "WR"},
        ]
    )
    filtered = filter_available_roster(roster, {"wr1"})
    assert list(filtered["player_id"]) == ["qb1"]


def test_build_week_dst_projections():
    vegas = pd.DataFrame(
        [
            {
                "home_team": "KC",
                "away_team": "BUF",
                "home_implied_total": 25.0,
                "away_implied_total": 22.0,
            }
        ]
    )
    volume = pd.DataFrame(
        [
            {
                "season": 2024,
                "week": 5,
                "team": "BUF",
                "pass_attempts": 30.0,
                "rush_attempts": 20.0,
            }
        ]
    )
    frame = build_week_dst_projections(vegas, volume, season=2024, week=5)
    assert len(frame) == 2
    assert set(frame["position"]) == {"DST"}
    assert frame["fd_projection"].gt(0).all()


def test_actual_dst_fantasy_points_from_pbp():
    pbp = pd.DataFrame(
        [
            {
                "season": 2024,
                "week": 5,
                "game_id": "g1",
                "home_team": "KC",
                "away_team": "BUF",
                "defteam": "KC",
                "posteam": "BUF",
                "sack": 1,
                "interception": 0,
                "touchdown": 0,
                "total_home_score": 24,
                "total_away_score": 17,
            },
            {
                "season": 2024,
                "week": 5,
                "game_id": "g1",
                "home_team": "KC",
                "away_team": "BUF",
                "defteam": "BUF",
                "posteam": "KC",
                "sack": 0,
                "interception": 1,
                "touchdown": 0,
                "total_home_score": 24,
                "total_away_score": 17,
            },
        ]
    )
    vegas = pd.DataFrame([{"home_team": "KC", "away_team": "BUF"}])
    actuals = actual_dst_fantasy_points(pbp, season=2024, week=5, vegas=vegas)
    kc = actuals.loc[actuals["team"] == "KC"].iloc[0]
    assert kc["fd_actual"] > 0


def test_regression_gates_fail_and_pass():
    report = CalibrationReport(
        season=2024,
        start_week=1,
        end_week=5,
        models=[
            ModelCalibration(
                model="diy",
                n_player_weeks=100,
                mae_fd=4.9,
                rmse_fd=6.0,
                spearman_fd=0.55,
                bias_fd=-0.5,
                by_position=[
                    PositionMetrics("QB", 10, 6.8, 8.0, 0.4, -1.0, 6.3, 6.1, "needs work"),
                ],
            )
        ],
    )
    gates = RegressionGates(max_overall_mae=4.85, max_qb_mae=6.75)
    failures = check_regression_gates(report, gates)
    assert any("overall MAE" in failure for failure in failures)
    assert any("QB MAE" in failure for failure in failures)

    passing = RegressionGates(max_overall_mae=5.0, max_qb_mae=7.0)
    assert check_regression_gates(report, passing) == []
