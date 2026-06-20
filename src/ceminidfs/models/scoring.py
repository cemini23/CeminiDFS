"""Fantasy scoring helpers for NFL DFS projections."""

from __future__ import annotations

from typing import Mapping, TypedDict


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


StatsMapping = Mapping[str, float]


def _stat(stats: StatsMapping, key: str) -> float:
    return float(stats.get(key, 0.0))


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

    return (
        _stat(stats, "dst_sacks") * 1.0
        + _stat(stats, "dst_int") * 2.0
        + _stat(stats, "dst_fumbles_recovered") * 2.0
        + _stat(stats, "dst_td") * 6.0
        + _stat(stats, "dst_safety") * 2.0
        + _stat(stats, "dst_blocked_kick") * 2.0
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

