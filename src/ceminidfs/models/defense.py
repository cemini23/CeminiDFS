"""Walk-forward defensive matchup multipliers from nflverse play-by-play."""

from __future__ import annotations

from typing import Mapping

import pandas as pd

DEFENSE_MULTIPLIER_CLAMP = (0.85, 1.15)
DEFAULT_DEFENSE_ALPHA = 0.08


def build_defense_ratings(
    pbp: pd.DataFrame,
    through_week: int,
    *,
    alpha: float = DEFAULT_DEFENSE_ALPHA,
) -> dict[str, dict[str, float]]:
    """Return per-team pass/rush multipliers using only weeks strictly before ``through_week``."""

    historical = _historical_pbp(pbp, through_week)
    if historical.empty:
        return {}

    ratings: dict[str, dict[str, float]] = {}
    for side in ("pass", "rush"):
        league_avg = _league_rate(historical, side)
        if league_avg <= 0:
            continue
        for team, team_rate in _team_rates(historical, side).items():
            multiplier = 1.0 + (alpha * (team_rate - league_avg))
            ratings.setdefault(team, {})[side] = _clamp(multiplier)

    return ratings


def defense_multiplier(
    opponent: str,
    side: str,
    ratings: Mapping[str, Mapping[str, float]] | None = None,
    *,
    alpha: float | None = None,
) -> float:
    """Return offensive boost/penalty multiplier vs ``opponent`` defense on pass or rush."""

    del alpha  # reserved for future tuning; ``build_defense_ratings`` applies alpha
    if side not in {"pass", "rush"}:
        msg = "side must be 'pass' or 'rush'"
        raise ValueError(msg)

    team = str(opponent or "").strip().upper()
    if not team or not ratings:
        return 1.0

    team_ratings = ratings.get(team, {})
    return float(team_ratings.get(side, 1.0))


def _historical_pbp(pbp: pd.DataFrame, through_week: int) -> pd.DataFrame:
    if pbp.empty or "week" not in pbp.columns:
        return pd.DataFrame()
    weeks = pd.to_numeric(pbp["week"], errors="coerce")
    return pbp.loc[weeks < through_week].copy()


def _team_rates(pbp: pd.DataFrame, side: str) -> dict[str, float]:
    defense_col = _first_col(pbp, ("defteam", "defense_team"))
    if defense_col is None:
        return {}

    mask = _side_mask(pbp, side)
    frame = pbp.loc[mask].copy()
    if frame.empty:
        return {}

    values = _play_values(frame, side)
    frame["_value"] = values
    grouped = frame.groupby(defense_col)["_value"].mean()
    return {str(team).strip().upper(): float(rate) for team, rate in grouped.items() if str(team).strip()}


def _league_rate(pbp: pd.DataFrame, side: str) -> float:
    mask = _side_mask(pbp, side)
    frame = pbp.loc[mask]
    if frame.empty:
        return 0.0
    return float(_play_values(frame, side).mean())


def _play_values(frame: pd.DataFrame, side: str) -> pd.Series:
    if "epa" in frame.columns:
        return pd.to_numeric(frame["epa"], errors="coerce").fillna(0.0)
    if side == "pass":
        yards = _sum_first_numeric(frame, ("passing_yards", "pass_yards", "yards_gained"))
        attempts = float(len(frame))
        return pd.Series([yards / attempts] * len(frame), index=frame.index)
    yards = _sum_first_numeric(frame, ("rushing_yards", "rush_yards", "yards_gained"))
    attempts = float(len(frame))
    per_play = yards / attempts if attempts else 0.0
    return pd.Series([per_play] * len(frame), index=frame.index)


def _side_mask(pbp: pd.DataFrame, side: str) -> pd.Series:
    if side == "pass":
        return _flag(pbp, ("pass_attempt", "pass")).eq(1)
    return _flag(pbp, ("rush_attempt", "rush")).eq(1)


def _sum_first_numeric(df: pd.DataFrame, aliases: tuple[str, ...]) -> float:
    col = _first_col(df, aliases)
    if df.empty or col is None:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0.0).sum())


def _flag(df: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    col = _first_col(df, names)
    if col is None:
        return pd.Series(0, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0)


def _first_col(df: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def _clamp(value: float) -> float:
    low, high = DEFENSE_MULTIPLIER_CLAMP
    return max(low, min(high, value))
