"""Implied team totals and game environment helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImpliedTotals:
    favorite: float
    underdog: float


@dataclass(frozen=True)
class GameEnvironmentInputs:
    total: float
    pace: float | None = None
    pass_rate: float | None = None
    total_mean: float = 44.0
    total_stdev: float = 4.5
    pace_mean: float = 1.0
    pace_stdev: float = 0.1
    pass_rate_mean: float = 0.58
    pass_rate_stdev: float = 0.07


def implied_team_total(total: float, spread: float) -> float:
    """Return a team's implied total using ITT = (T / 2) - (S / 2)."""

    return (total / 2.0) - (spread / 2.0)


def implied_totals_from_spreads(total: float, team_spread: float) -> tuple[float, float]:
    """Return implied totals for a team and its opponent from one signed spread."""

    team_total = implied_team_total(total, team_spread)
    opponent_total = total - team_total
    return team_total, opponent_total


def implied_totals_from_favorite(total: float, favorite_spread: float) -> ImpliedTotals:
    """Return favorite/underdog ITTs from a favorite spread.

    Accepts either common signed form (-3) or absolute favorite form (3).
    """

    signed_favorite_spread = -abs(favorite_spread)
    favorite_total = implied_team_total(total, signed_favorite_spread)
    return ImpliedTotals(favorite=favorite_total, underdog=total - favorite_total)


def _z_score(value: float | None, mean: float, stdev: float) -> float:
    if value is None or stdev == 0:
        return 0.0
    return (value - mean) / stdev


def game_environment_score(inputs: GameEnvironmentInputs) -> float:
    """Placeholder z-score blend for ranking DFS game environments."""

    total_z = _z_score(inputs.total, inputs.total_mean, inputs.total_stdev)
    pace_z = _z_score(inputs.pace, inputs.pace_mean, inputs.pace_stdev)
    pass_z = _z_score(inputs.pass_rate, inputs.pass_rate_mean, inputs.pass_rate_stdev)
    return (0.6 * total_z) + (0.25 * pace_z) + (0.15 * pass_z)

