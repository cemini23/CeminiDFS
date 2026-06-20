import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.simulate import (
    add_simulation_columns,
    simulate_fd_points,
    simulate_fd_points_copula,
    simulation_summary,
)


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


def test_simulate_fd_points_copula_boosts_qb_wr1_correlation():
    df = pd.DataFrame(
        [
            _player("kc_qb", "KC", "LV", "KC@LV", "QB", 22.0),
            _player("kc_wr", "KC", "LV", "KC@LV", "WR", 17.0),
            _player("nyj_wr", "NYJ", "MIA", "NYJ@MIA", "WR", 17.0),
        ]
    )

    sims = simulate_fd_points_copula(df, n_iterations=12000, seed=29)
    same_team_corr = np.corrcoef(sims[0], sims[1])[0, 1]
    different_game_corr = np.corrcoef(sims[0], sims[2])[0, 1]

    assert sims.shape == (len(df), 12000)
    assert same_team_corr > different_game_corr + 0.10


def test_simulate_fd_points_dispatches_to_copula_method():
    df = pd.DataFrame(
        [
            _player("kc_qb", "KC", "LV", "KC@LV", "QB", 22.0),
            _player("kc_wr", "KC", "LV", "KC@LV", "WR", 17.0),
        ]
    )

    direct = simulate_fd_points_copula(df, n_iterations=500, seed=31)
    dispatched = simulate_fd_points(df, n_iterations=500, seed=31, method="copula")

    np.testing.assert_allclose(dispatched, direct)


def test_add_simulation_columns_respects_configured_method():
    df = pd.DataFrame(
        [
            _player("kc_qb", "KC", "LV", "KC@LV", "QB", 22.0),
            _player("kc_wr", "KC", "LV", "KC@LV", "WR", 17.0),
        ]
    )

    configured = add_simulation_columns(
        df,
        n_iterations=500,
        seed=37,
        config={"simulate": {"method": "copula"}},
    )
    explicit = simulation_summary(
        simulate_fd_points(df, n_iterations=500, seed=37, method="copula"),
        df["player_id"],
    )

    np.testing.assert_allclose(configured["sim_median"], explicit["median"])


def _sample_players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": "kc_qb", "fd_projection": 22.0, "team": "KC", "position": "QB"},
            {"player_id": "kc_rb", "fd_projection": 15.0, "team": "KC", "position": "RB"},
            {"player_id": "buf_wr", "fd_projection": 13.0, "team": "BUF", "position": "WR"},
            {"player_id": "buf_def", "fd_projection": 8.0, "team": "BUF", "position": "DEF"},
        ]
    )


def _player(
    player_id: str,
    team: str,
    opp: str,
    game: str,
    position: str,
    projection: float,
) -> dict[str, object]:
    return {
        "player_id": player_id,
        "team": team,
        "opp": opp,
        "game": game,
        "position": position,
        "fd_projection": projection,
    }
