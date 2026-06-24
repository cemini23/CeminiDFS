"""Fantasy scoring helpers for NFL DFS projections."""

from __future__ import annotations

from typing import Any, Mapping, TypedDict

import pandas as pd


class CountingStats(TypedDict, total=False):
    """Supported counting stats for FD/DK scoring."""

    pass_yds: float
    pass_td: float
    int: float
    rush_yds: float
    rush_td: float
    rec: float
    rec_yds: float
    rec_td: float
    fumbles_lost: float
    dst_sacks: float
    dst_int: float
    dst_fumbles_recovered: float
    dst_td: float
    dst_safety: float
    dst_blocked_kick: float


StatsMapping = Mapping[str, Any]

COUNTING_STAT_KEYS = (
    "pass_yds",
    "pass_td",
    "int",
    "rush_yds",
    "rush_td",
    "rec",
    "rec_yds",
    "rec_td",
    "fumbles_lost",
)


def _stat(stats: StatsMapping, key: str) -> float:
    value = pd.to_numeric(pd.Series([stats.get(key, 0.0)]), errors="coerce").iloc[0]
    return 0.0 if pd.isna(value) else float(value)


def _yardage_bonuses(stats: StatsMapping) -> float:
    bonus = 0.0
    if _stat(stats, "pass_yds") >= 300:
        bonus += 3.0
    if _stat(stats, "rush_yds") >= 100:
        bonus += 3.0
    if _stat(stats, "rec_yds") >= 100:
        bonus += 3.0
    return bonus


def _dst_stub_points(stats: StatsMapping) -> float:
    """Basic DST event scoring stub; points-allowed tiers can be layered later."""

    points = (
        _stat(stats, "dst_sacks") * 1.0
        + _stat(stats, "dst_int") * 2.0
        + _stat(stats, "dst_fumbles_recovered") * 2.0
        + _stat(stats, "dst_td") * 6.0
        + _stat(stats, "dst_safety") * 2.0
        + _stat(stats, "dst_blocked_kick") * 2.0
    )
    if "dst_points_allowed" in stats:
        points += fd_dst_points_allowed(_stat(stats, "dst_points_allowed"))
    return points


def fd_dst_points_allowed(points_allowed: float) -> float:
    """FanDuel DST fantasy points from expected opponent points allowed."""

    points = max(0.0, float(points_allowed))
    if points == 0:
        return 10.0
    if points <= 6:
        return 7.0
    if points <= 13:
        return 4.0
    if points <= 20:
        return 1.0
    if points <= 27:
        return 0.0
    if points <= 34:
        return -1.0
    return -4.0


def score_half_ppr_season(stats: StatsMapping) -> float:
    """Return Underdog BBM half-PPR season fantasy points (no yardage bonuses)."""

    return (
        _stat(stats, "pass_yds") * 0.04
        + _stat(stats, "pass_td") * 4.0
        - _stat(stats, "int") * 1.0
        + _stat(stats, "rush_yds") * 0.1
        + _stat(stats, "rush_td") * 6.0
        + _stat(stats, "rec") * 0.5
        + _stat(stats, "rec_yds") * 0.1
        + _stat(stats, "rec_td") * 6.0
        - _stat(stats, "fumbles_lost") * 2.0
    )


def fd_points(stats: StatsMapping) -> float:
    """Return FanDuel half-PPR fantasy points from counting stats."""

    return (
        _stat(stats, "pass_yds") * 0.04
        + _stat(stats, "pass_td") * 4.0
        - _stat(stats, "int") * 1.0
        + _stat(stats, "rush_yds") * 0.1
        + _stat(stats, "rush_td") * 6.0
        + _stat(stats, "rec") * 0.5
        + _stat(stats, "rec_yds") * 0.1
        + _stat(stats, "rec_td") * 6.0
        - _stat(stats, "fumbles_lost") * 2.0
        + _yardage_bonuses(stats)
        + _dst_stub_points(stats)
    )


def dk_points(stats: StatsMapping) -> float:
    """Return DraftKings full-PPR fantasy points from counting stats."""

    return (
        _stat(stats, "pass_yds") * 0.04
        + _stat(stats, "pass_td") * 4.0
        - _stat(stats, "int") * 1.0
        + _stat(stats, "rush_yds") * 0.1
        + _stat(stats, "rush_td") * 6.0
        + _stat(stats, "rec") * 1.0
        + _stat(stats, "rec_yds") * 0.1
        + _stat(stats, "rec_td") * 6.0
        - _stat(stats, "fumbles_lost") * 1.0
        + _yardage_bonuses(stats)
        + _dst_stub_points(stats)
    )


def stats_to_counting_stats(row: Mapping[str, Any]) -> dict[str, float]:
    """Map a PlayerStatProjection-like row into scoring counting stats."""

    return {key: _stat(row, key) for key in COUNTING_STAT_KEYS}


def fantasy_points_from_stats(row: Mapping[str, Any]) -> tuple[float, float]:
    """Return FanDuel and DraftKings fantasy points from a stat projection row."""

    stats = stats_to_counting_stats(row)
    return fd_points(stats), dk_points(stats)


def add_fantasy_points(stats_df: pd.DataFrame) -> pd.DataFrame:
    """Return stats with fd_projection and dk_projection columns."""

    scored = stats_df.copy()
    if scored.empty:
        scored["fd_projection"] = pd.Series(dtype=float)
        scored["dk_projection"] = pd.Series(dtype=float)
        return scored

    points = scored.apply(lambda row: fantasy_points_from_stats(row.to_dict()), axis=1)
    scored["fd_projection"] = [fd for fd, _ in points]
    scored["dk_projection"] = [dk for _, dk in points]
    return scored

