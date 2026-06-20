import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.correlation import (
    assign_player_roles,
    build_correlation_matrix,
    nearest_psd,
)


def test_assign_player_roles_ranks_players_within_team_and_position():
    df = pd.DataFrame(
        [
            {"player_id": "kc_wr3", "team": "KC", "position": "WR", "fd_projection": 10.0},
            {"player_id": "kc_wr1", "team": "KC", "position": "WR", "fd_projection": 18.0},
            {"player_id": "kc_wr2", "team": "KC", "position": "WR", "fd_projection": 14.0},
            {"player_id": "kc_wr4", "team": "KC", "position": "WR", "fd_projection": 5.0},
            {"player_id": "kc_rb2", "team": "KC", "position": "RB", "fd_projection": 8.0},
            {"player_id": "kc_rb1", "team": "KC", "position": "RB", "fd_projection": 16.0},
            {"player_id": "kc_te", "team": "KC", "position": "TE", "fd_projection": 12.0},
            {"player_id": "kc_def", "team": "KC", "position": "DST", "fd_projection": 7.0},
        ]
    )

    assigned = assign_player_roles(df).set_index("player_id")

    assert assigned.loc["kc_wr1", "role"] == "WR1"
    assert assigned.loc["kc_wr2", "role"] == "WR2"
    assert assigned.loc["kc_wr3", "role"] == "WR3"
    assert assigned.loc["kc_wr4", "role"] == "OTHER"
    assert assigned.loc["kc_rb1", "role"] == "RB1"
    assert assigned.loc["kc_rb2", "role"] == "RB2"
    assert assigned.loc["kc_te", "role"] == "TE1"
    assert assigned.loc["kc_def", "role"] == "DEF"


def test_build_correlation_matrix_uses_role_and_game_priors():
    df = pd.DataFrame(
        [
            _player("kc_qb", "KC", "LV", "KC@LV", "QB", 22.0),
            _player("kc_wr", "KC", "LV", "KC@LV", "WR", 17.0),
            _player("lv_qb", "LV", "KC", "KC@LV", "QB", 20.0),
            _player("lv_def", "LV", "KC", "KC@LV", "DEF", 8.0),
            _player("nyj_wr", "NYJ", "MIA", "NYJ@MIA", "WR", 17.0),
        ]
    )

    corr = build_correlation_matrix(df)

    assert corr.shape == (len(df), len(df))
    np.testing.assert_allclose(corr, corr.T)
    np.testing.assert_allclose(np.diag(corr), np.ones(len(df)))
    assert np.linalg.eigvalsh(corr).min() >= -1e-8
    assert corr[0, 1] > corr[0, 4]
    assert corr[0, 2] > corr[0, 4]
    assert corr[0, 3] < 0


def test_nearest_psd_floors_negative_eigenvalues():
    matrix = np.array([[1.0, 1.5], [1.5, 1.0]])

    psd = nearest_psd(matrix)

    np.testing.assert_allclose(psd, psd.T)
    assert np.linalg.eigvalsh(psd).min() >= -1e-8


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
