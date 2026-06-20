from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd


POSITION_CV = {
    "QB": 0.35,
    "RB": 0.45,
    "WR": 0.50,
    "TE": 0.45,
    "DEF": 0.40,
    "DST": 0.40,
    "D": 0.40,
}
TEAM_CORRELATION = 0.35
DEFAULT_POSITION_CV = 0.45

REQUIRED_COLUMNS = ("player_id", "fd_projection", "team", "position")


def simulate_fd_points(
    df: pd.DataFrame,
    n_iterations: int = 5000,
    seed: int | None = None,
) -> np.ndarray:
    """Return simulated FanDuel points with shape (n_players, n_iterations)."""

    _validate_inputs(df, n_iterations)
    if df.empty:
        return np.empty((0, n_iterations), dtype=float)

    rng = np.random.default_rng(seed)
    projections = pd.to_numeric(df["fd_projection"], errors="coerce").fillna(0.0).clip(lower=0.0)
    medians = projections.to_numpy(dtype=float)

    positions = df["position"].map(_normalize_position)
    cv = positions.map(lambda position: POSITION_CV.get(position, DEFAULT_POSITION_CV)).to_numpy(
        dtype=float
    )
    sigma = np.sqrt(np.log1p(cv * cv))
    team_beta = sigma * TEAM_CORRELATION
    idio_beta = sigma * np.sqrt(1.0 - (TEAM_CORRELATION * TEAM_CORRELATION))

    teams = df["team"].fillna("").astype(str).to_numpy()
    unique_teams, team_codes = np.unique(teams, return_inverse=True)
    team_shocks = rng.standard_normal((len(unique_teams), n_iterations))
    idio_shocks = rng.standard_normal((len(df), n_iterations))

    log_multiplier = (team_beta[:, None] * team_shocks[team_codes]) + (
        idio_beta[:, None] * idio_shocks
    )
    return np.maximum(0.0, medians[:, None] * np.exp(log_multiplier))


def simulation_summary(
    sim_matrix: np.ndarray,
    player_ids: Iterable[Any],
    quantiles: tuple[float, float, float] = (0.2, 0.5, 0.9),
) -> pd.DataFrame:
    """Summarize each player's simulated floor, median, and ceiling."""

    matrix = np.asarray(sim_matrix, dtype=float)
    ids = list(player_ids)
    if matrix.ndim != 2:
        raise ValueError("sim_matrix must be a 2D array")
    if len(ids) != matrix.shape[0]:
        raise ValueError("player_ids length must match sim_matrix rows")
    if len(quantiles) != 3:
        raise ValueError("quantiles must contain floor, median, and ceiling values")

    floor, median, ceiling = np.quantile(matrix, quantiles, axis=1)
    return pd.DataFrame(
        {
            "player_id": ids,
            "floor": floor,
            "median": median,
            "ceiling": ceiling,
        }
    )


def add_simulation_columns(
    df: pd.DataFrame,
    n_iterations: int = 5000,
    seed: int | None = None,
) -> pd.DataFrame:
    """Attach floor and ceiling projection columns to a copy of a projection frame."""

    sim_matrix = simulate_fd_points(df, n_iterations=n_iterations, seed=seed)
    summary = simulation_summary(sim_matrix, df["player_id"])

    output = df.copy()
    output["Projection Floor"] = summary["floor"].to_numpy()
    output["sim_median"] = summary["median"].to_numpy()
    output["Projection Ceil"] = summary["ceiling"].to_numpy()
    return output


def _validate_inputs(df: pd.DataFrame, n_iterations: int) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"simulate_fd_points requires columns: {', '.join(missing)}")
    if n_iterations <= 0:
        raise ValueError("n_iterations must be positive")


def _normalize_position(value: Any) -> str:
    position = str(value or "").strip().upper()
    if position == "DST":
        return "DEF"
    return position
