"""Detect a running back whose recent usage has fallen off a cliff.

The Week 11 recap held a demoted running back too long. Season-long usage
still looked healthy while the last three games told a different story. The
detector compares a player's trailing three-game touches per game with his
season touches per game and flags a large drop.

Touches are carries plus targets from :func:`player_game_stats_from_pbp`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Tuple

import pandas as pd

ROLE_CLIFF_WARNING = "ROLE_CLIFF_WARNING"
DEFAULT_L3_WINDOW = 3
DEFAULT_DROP_THRESHOLD = 0.40


@dataclass(frozen=True)
class RoleCliff:
    """One player's season-vs-recent usage comparison."""

    player_key: str
    season_touches_pg: float
    l3_touches_pg: float
    drop_pct: float
    flagged: bool


def detect_role_cliffs(
    game_stats: pd.DataFrame,
    *,
    positions: Tuple[str, ...] = ("RB",),
    l3_window: int = DEFAULT_L3_WINDOW,
    drop_threshold: float = DEFAULT_DROP_THRESHOLD,
) -> dict[str, RoleCliff]:
    """Return one :class:`RoleCliff` per player with enough games to judge.

    A player with fewer than ``l3_window`` played games is skipped. That is a
    mid-game injury exit or a missed game, and the warning cannot fire. A
    player whose season touches per game is zero is skipped too.
    """

    if game_stats is None or game_stats.empty:
        return {}

    wanted = {str(position).strip().upper() for position in positions}
    frame = game_stats.copy()
    for column in ("carries", "targets", "week"):
        if column not in frame.columns:
            frame[column] = 0.0

    frame["_touches"] = (
        pd.to_numeric(frame["carries"], errors="coerce").fillna(0.0)
        + pd.to_numeric(frame["targets"], errors="coerce").fillna(0.0)
    )
    frame["_week"] = pd.to_numeric(frame["week"], errors="coerce")

    results: dict[str, RoleCliff] = {}
    for player_key, group in _group_by_player(frame):
        position = _last_position(group)
        if wanted and position and position not in wanted:
            continue
        ordered = group.sort_values(["_week"], kind="stable")
        played = ordered
        season_touches = float(played["_touches"].mean()) if len(played) else 0.0
        if season_touches <= 0:
            continue
        if len(played) < l3_window:
            continue
        recent = played.tail(l3_window)
        # A zero-touch game in the window is most likely a mid-game injury exit.
        # Do not call that a role cliff.
        if (recent["_touches"] <= 0).any():
            continue
        l3_touches = float(recent["_touches"].mean())
        drop_pct = (season_touches - l3_touches) / season_touches
        flagged = l3_touches <= (1.0 - drop_threshold) * season_touches
        results[str(player_key)] = RoleCliff(
            player_key=str(player_key),
            season_touches_pg=season_touches,
            l3_touches_pg=l3_touches,
            drop_pct=drop_pct,
            flagged=flagged,
        )
    return results


def role_flag_for(result: RoleCliff) -> str:
    """Return the warning token for a flagged cliff, else an empty string."""

    return ROLE_CLIFF_WARNING if result.flagged else ""


def flagged_player_keys(results: dict[str, RoleCliff]) -> list[str]:
    """Return the keys of every flagged player."""

    return sorted(key for key, result in results.items() if result.flagged)


def _group_by_player(frame: pd.DataFrame) -> Iterable[tuple[Any, pd.DataFrame]]:
    if "player_id" in frame.columns:
        keyed = frame.loc[frame["player_id"].notna()].copy()
        keyed["_player_key"] = keyed["player_id"].astype(str)
    elif "player_name" in frame.columns:
        keyed = frame.copy()
        keyed["_player_key"] = keyed["player_name"].fillna("").astype(str)
    else:
        keyed = frame.copy()
        keyed["_player_key"] = [str(index) for index in keyed.index]
    keyed = keyed.loc[keyed["_player_key"].str.strip() != ""]
    return keyed.groupby("_player_key", sort=False)


def _last_position(group: pd.DataFrame) -> str:
    if "position" not in group.columns:
        return ""
    values = [
        str(value).strip().upper()
        for value in group["position"].tolist()
        if str(value).strip()
    ]
    return values[-1] if values else ""
