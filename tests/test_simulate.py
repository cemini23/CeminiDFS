import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.simulate import add_simulation_columns, simulate_fd_points, simulation_summary


def test_simulate_fd_points_is_deterministic_with_seed():
    df = _sample_players()

    first = simulate_fd_points(df, n_iterations=500, seed=7)
    second = simulate_fd_points(df, n_iterations=500, seed=7)

    assert first.shape == (len(df), 500)
    np.testing.assert_allclose(first, second)


def test_simulation_median_is_close_to_projection():
    df = _sample_players()
    sims = simulate_fd_points(df, n_iterations=8000, seed=11)
    summary = simulation_summary(sims, df["player_id"])

    np.testing.assert_allclose(summary["median"], df["fd_projection"], rtol=0.05)


def test_add_simulation_columns_has_ceiling_above_floor():
    df = _sample_players()

    simulated = add_simulation_columns(df, n_iterations=1000, seed=13)

    assert "Projection Floor" in simulated.columns
    assert "Projection Ceil" in simulated.columns
    assert (simulated["Projection Ceil"] >= simulated["Projection Floor"]).all()


def test_same_team_players_are_more_correlated_than_different_teams():
    df = pd.DataFrame(
        [
            {"player_id": "kc_qb", "fd_projection": 22.0, "team": "KC", "position": "QB"},
            {"player_id": "kc_wr", "fd_projection": 16.0, "team": "KC", "position": "WR"},
            {"player_id": "buf_wr", "fd_projection": 16.0, "team": "BUF", "position": "WR"},
        ]
    )

    sims = simulate_fd_points(df, n_iterations=10000, seed=23)
    same_team_corr = np.corrcoef(sims[0], sims[1])[0, 1]
    different_team_corr = np.corrcoef(sims[0], sims[2])[0, 1]

    assert same_team_corr > different_team_corr


def _sample_players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": "kc_qb", "fd_projection": 22.0, "team": "KC", "position": "QB"},
            {"player_id": "kc_rb", "fd_projection": 15.0, "team": "KC", "position": "RB"},
            {"player_id": "buf_wr", "fd_projection": 13.0, "team": "BUF", "position": "WR"},
            {"player_id": "buf_def", "fd_projection": 8.0, "team": "BUF", "position": "DEF"},
        ]
    )
