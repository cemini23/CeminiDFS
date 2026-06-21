"""Player availability from salary exports and cached nflverse injury reports."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from ceminidfs.data.fetch import week_cache_dir

UNAVAILABLE_STATUSES = frozenset(
    {
        "O",
        "OUT",
        "IR",
        "PUP",
        "NFI",
        "DOUBTFUL",
        "D",
        "DOUBTFUL TO PLAY",
    }
)

PLAYER_ID_COLUMNS = ("gsis_id", "player_id", "gsis_it_id")
STATUS_COLUMNS = (
    "report_status",
    "game_status",
    "injury_status",
    "status",
    "practice_status",
)
WEEK_COLUMNS = ("week", "week_num")


def normalize_injury_status(value: Any) -> str:
    """Return uppercase injury token from FanDuel or nflverse labels."""

    token = str(value or "").strip().upper()
    if not token:
        return ""
    if token in UNAVAILABLE_STATUSES:
        return token
    for prefix in ("OUT", "DOUBTFUL", "IR", "PUP"):
        if token.startswith(prefix):
            return prefix
    return token


def is_unavailable_status(status: Any) -> bool:
    """True when a player should be excluded from the usage projection pool."""

    token = normalize_injury_status(status)
    if not token:
        return False
    if token in {"O", "OUT", "IR", "PUP", "NFI", "D"}:
        return True
    return token.startswith("DOUBTFUL")


def unavailable_player_ids_from_salary_rows(rows: list[Mapping[str, Any]]) -> set[str]:
    """Collect player ids flagged Out/Doubtful on a salary export."""

    excluded: set[str] = set()
    for row in rows:
        status = row.get("injury_status") or row.get("Injury Indicator") or row.get("injury")
        if not is_unavailable_status(status):
            continue
        player_id = str(
            row.get("fd_id")
            or row.get("dk_id")
            or row.get("player_key")
            or row.get("player_id")
            or row.get("Id")
            or ""
        ).strip()
        if player_id:
            excluded.add(player_id)
    return excluded


def unavailable_player_ids_from_week_cache(season: int, week: int) -> set[str]:
    """Collect unavailable player ids from cached injuries.parquet when present."""

    path = week_cache_dir(season, week) / "injuries.parquet"
    if not path.is_file():
        return set()

    try:
        frame = pd.read_parquet(path)
    except (OSError, ValueError):
        return set()

    if frame.empty:
        return set()

    week_col = _first_col(frame, WEEK_COLUMNS)
    if week_col:
        frame = frame.loc[pd.to_numeric(frame[week_col], errors="coerce") == week]

    id_col = _first_col(frame, PLAYER_ID_COLUMNS)
    status_col = _first_col(frame, STATUS_COLUMNS)
    if id_col is None or status_col is None:
        return set()

    excluded: set[str] = set()
    for _, row in frame.iterrows():
        if not is_unavailable_status(row.get(status_col)):
            continue
        player_id = str(row.get(id_col, "") or "").strip()
        if player_id:
            excluded.add(player_id)
    return excluded


def resolve_unavailable_player_ids(
    season: int,
    week: int,
    *,
    roster: pd.DataFrame | None = None,
    salary_rows: list[Mapping[str, Any]] | None = None,
    config: Mapping[str, Any] | None = None,
) -> set[str]:
    """Merge salary and cached injury exclusions for one week."""

    cfg = dict(config or {})
    if cfg.get("ignore_injuries"):
        return set()

    excluded = unavailable_player_ids_from_week_cache(season, week)
    if salary_rows:
        excluded.update(unavailable_player_ids_from_salary_rows(salary_rows))

    if roster is not None and not roster.empty and "injury_status" in roster.columns:
        for _, row in roster.iterrows():
            if is_unavailable_status(row.get("injury_status")):
                player_id = str(row.get("player_id", "") or "").strip()
                if player_id:
                    excluded.add(player_id)
    return excluded


def filter_available_roster(roster: pd.DataFrame, excluded_ids: set[str]) -> pd.DataFrame:
    """Drop unavailable players from a roster frame."""

    if roster.empty or not excluded_ids or "player_id" not in roster.columns:
        return roster
    return roster.loc[~roster["player_id"].astype(str).isin(excluded_ids)].copy()


def _first_col(df: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None
