"""Season roster positions from nflverse (cached parquet)."""

from __future__ import annotations

import importlib
from typing import Mapping

import pandas as pd

from ceminidfs.data.fetch import _cache_dir

INSTALL_HINT = "Install nflreadpy with `pip install nflreadpy` to fetch roster data."

PLAYER_ID_COLUMNS = ("gsis_id", "player_id", "gsis_it_id")
POSITION_COLUMNS = ("position", "pos")
TEAM_COLUMNS = ("team", "recent_team")
WEEK_COLUMNS = ("week", "week_num")


def load_season_rosters(season: int) -> pd.DataFrame:
    """Load weekly roster rows for a season from cache or nflreadpy."""

    cache_path = _cache_dir() / f"rosters_{season}.parquet"
    if cache_path.is_file():
        return pd.read_parquet(cache_path)

    nflreadpy = _require_nflreadpy()
    loader_names = (
        "load_rosters_weekly",
        "import_rosters_weekly",
        "load_rosters",
        "import_rosters",
    )
    data = _call_loader(nflreadpy, loader_names, season)
    frame = _to_pandas(data)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(cache_path, index=False)
    return frame


def position_lookup_for_week(season: int, week: int) -> dict[str, str]:
    """Return player_id → uppercase position for one season week."""

    try:
        rosters = load_season_rosters(season)
    except (ImportError, FileNotFoundError, OSError, AttributeError):
        return {}
    if rosters.empty:
        return {}

    frame = rosters.copy()
    if "season" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["season"], errors="coerce") == season]
    week_col = _first_col(frame, WEEK_COLUMNS)
    if week_col:
        frame = frame.loc[pd.to_numeric(frame[week_col], errors="coerce") == week]
    if frame.empty:
        return {}

    id_col = _first_col(frame, PLAYER_ID_COLUMNS)
    pos_col = _first_col(frame, POSITION_COLUMNS)
    if id_col is None or pos_col is None:
        return {}

    lookup: dict[str, str] = {}
    for _, row in frame.iterrows():
        player_id = str(row.get(id_col, "") or "").strip()
        position = str(row.get(pos_col, "") or "").strip().upper()
        if player_id and position:
            lookup[player_id] = _normalize_position(position)
    return lookup


def enrich_roster_positions(
    roster: pd.DataFrame,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Fill missing roster positions from nflverse weekly rosters."""

    if roster.empty or "player_id" not in roster.columns:
        return roster

    lookup = position_lookup_for_week(season, week)
    if not lookup:
        return roster

    enriched = roster.copy()
    enriched["position"] = enriched["position"].fillna("").astype(str).str.upper()
    empty = enriched["position"].eq("")
    if empty.any():
        enriched.loc[empty, "position"] = (
            enriched.loc[empty, "player_id"].astype(str).map(lookup).fillna("")
        )
    else:
        mapped = enriched["player_id"].astype(str).map(lookup)
        still_empty = enriched["position"].eq("") & mapped.notna()
        enriched.loc[still_empty, "position"] = mapped.loc[still_empty]
    return enriched


def apply_position_lookup(stats: pd.DataFrame, lookup: Mapping[str, str]) -> pd.DataFrame:
    """Prefer nflverse roster labels when inferring player positions."""

    if stats.empty or not lookup:
        return stats

    enriched = stats.copy()
    if "position" not in enriched.columns:
        enriched["position"] = ""
    roster_pos = enriched["player_id"].astype(str).map(dict(lookup)).fillna("")
    empty = enriched["position"].fillna("").astype(str).str.upper().eq("")
    enriched.loc[empty, "position"] = roster_pos.loc[empty]
    return enriched


def _normalize_position(position: str) -> str:
    token = position.strip().upper()
    if token in {"QB", "RB", "WR", "TE", "K"}:
        return token
    if token.startswith("QB"):
        return "QB"
    if token.startswith("RB"):
        return "RB"
    if token.startswith("WR"):
        return "WR"
    if token.startswith("TE"):
        return "TE"
    return token


def _require_nflreadpy():
    try:
        return importlib.import_module("nflreadpy")
    except ImportError as exc:
        raise ImportError(INSTALL_HINT) from exc


def _call_loader(module, loader_names: tuple[str, ...], season: int):
    for name in loader_names:
        loader = getattr(module, name, None)
        if loader is None:
            continue
        try:
            return loader(season)
        except TypeError:
            return loader(seasons=season)
    raise AttributeError(f"No roster loader found on nflreadpy ({', '.join(loader_names)})")


def _to_pandas(data) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data
    if hasattr(data, "to_pandas"):
        return data.to_pandas()
    return pd.DataFrame(data)


def _first_col(df: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None
