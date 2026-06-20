from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


ROLE_CORRELATION_PRIORS: dict[tuple[str, str], float] = {
    ("QB", "WR1"): 0.45,
    ("QB", "TE1"): 0.28,
    ("QB", "RB1"): 0.10,
    ("QB", "OPP_QB"): 0.20,
    ("QB", "OPP_DEF"): -0.35,
    ("SKILL", "SKILL"): 0.15,
}

SKILL_ROLES = {"RB1", "RB2", "WR1", "WR2", "WR3", "TE1"}


def assign_player_roles(df: pd.DataFrame) -> pd.DataFrame:
    """Assign DFS correlation roles based on team-position projection rank."""

    output = df.copy()
    if output.empty:
        output["role"] = pd.Series(dtype=object)
        return output

    teams = output.get("team", pd.Series("", index=output.index)).map(_normalize_token)
    positions = output.get("position", pd.Series("", index=output.index)).map(_normalize_position)
    projections = pd.to_numeric(
        output.get("fd_projection", pd.Series(0.0, index=output.index)),
        errors="coerce",
    ).fillna(0.0)

    ranked = pd.DataFrame(
        {
            "team": teams,
            "position": positions,
            "projection": projections,
        },
        index=output.index,
    )
    ranks = ranked.groupby(["team", "position"])["projection"].rank(method="first", ascending=False)
    output["role"] = [
        _role_for_position_rank(position, int(rank))
        for position, rank in zip(positions, ranks, strict=True)
    ]
    return output


def build_correlation_matrix(df: pd.DataFrame, site: str = "fanduel") -> np.ndarray:
    """Build a game-aware player correlation matrix from role priors."""

    del site  # FanDuel is the only calibrated projection scale today.

    if df.empty:
        return np.empty((0, 0), dtype=float)

    frame = _ensure_correlation_columns(df)
    assigned = assign_player_roles(frame)
    n_players = len(assigned)
    matrix = np.eye(n_players, dtype=float)

    roles = assigned["role"].astype(str).to_numpy()
    teams = assigned.get("team", pd.Series("", index=assigned.index)).map(_normalize_token).to_numpy()
    opps = assigned.get("opp", pd.Series("", index=assigned.index)).map(_normalize_token).to_numpy()
    games = assigned.get("game", pd.Series("", index=assigned.index)).map(_normalize_token).to_numpy()

    for i in range(n_players):
        for j in range(i + 1, n_players):
            value = _pair_correlation(
                roles[i],
                roles[j],
                teams[i],
                teams[j],
                opps[i],
                opps[j],
                games[i],
                games[j],
            )
            matrix[i, j] = value
            matrix[j, i] = value

    return _correlation_psd(matrix)


def nearest_psd(matrix: np.ndarray, eigenvalue_floor: float = 1e-8) -> np.ndarray:
    """Return a symmetric positive semidefinite approximation using eigenvalue flooring."""

    array = np.asarray(matrix, dtype=float)
    if array.ndim != 2 or array.shape[0] != array.shape[1]:
        raise ValueError("matrix must be a square 2D array")

    symmetric = (array + array.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    floored = np.maximum(eigenvalues, eigenvalue_floor)
    psd = (eigenvectors * floored) @ eigenvectors.T
    return (psd + psd.T) / 2.0


def _pair_correlation(
    role_a: str,
    role_b: str,
    team_a: str,
    team_b: str,
    opp_a: str,
    opp_b: str,
    game_a: str,
    game_b: str,
) -> float:
    same_team = bool(team_a and team_a == team_b)
    opponents = _are_opponents(team_a, team_b, opp_a, opp_b)
    same_game = _same_game(game_a, game_b) or opponents

    if same_team:
        explicit = _lookup_role_prior(role_a, role_b)
        if explicit is not None:
            return explicit
        if role_a in SKILL_ROLES and role_b in SKILL_ROLES:
            return ROLE_CORRELATION_PRIORS[("SKILL", "SKILL")]
        return 0.0

    if same_game and opponents:
        if {role_a, role_b} == {"QB", "DEF"}:
            return ROLE_CORRELATION_PRIORS[("QB", "OPP_DEF")]
        if role_a == "QB" and role_b == "QB":
            return ROLE_CORRELATION_PRIORS[("QB", "OPP_QB")]

    return 0.0


def _lookup_role_prior(role_a: str, role_b: str) -> float | None:
    if (role_a, role_b) in ROLE_CORRELATION_PRIORS:
        return ROLE_CORRELATION_PRIORS[(role_a, role_b)]
    if (role_b, role_a) in ROLE_CORRELATION_PRIORS:
        return ROLE_CORRELATION_PRIORS[(role_b, role_a)]
    return None


def _correlation_psd(matrix: np.ndarray) -> np.ndarray:
    psd = nearest_psd(matrix)
    diagonal = np.sqrt(np.maximum(np.diag(psd), 1e-12))
    corr = psd / np.outer(diagonal, diagonal)
    corr = np.clip((corr + corr.T) / 2.0, -0.999, 0.999)
    np.fill_diagonal(corr, 1.0)
    return corr


def _same_game(game_a: str, game_b: str) -> bool:
    return bool(game_a and game_b and game_a == game_b)


def _are_opponents(team_a: str, team_b: str, opp_a: str, opp_b: str) -> bool:
    return bool(team_a and team_b and ((opp_a == team_b) or (opp_b == team_a)))


def _role_for_position_rank(position: str, rank: int) -> str:
    if position == "QB" and rank == 1:
        return "QB"
    if position == "RB" and rank in {1, 2}:
        return f"RB{rank}"
    if position == "WR" and rank in {1, 2, 3}:
        return f"WR{rank}"
    if position == "TE" and rank == 1:
        return "TE1"
    if position == "DEF":
        return "DEF"
    return "OTHER"


def _normalize_position(value: Any) -> str:
    position = _normalize_token(value)
    if position in {"DST", "D"}:
        return "DEF"
    return position


def _ensure_correlation_columns(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    if "opp" not in frame.columns and "opponent" in frame.columns:
        frame["opp"] = frame["opponent"]
    if "game" not in frame.columns:
        teams = frame.get("team", pd.Series("", index=frame.index)).map(_normalize_token)
        opps = frame.get("opp", pd.Series("", index=frame.index)).map(_normalize_token)
        frame["game"] = [
            f"{min(team, opp)}@{max(team, opp)}" if team and opp else ""
            for team, opp in zip(teams, opps, strict=True)
        ]
    return frame


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().upper()
