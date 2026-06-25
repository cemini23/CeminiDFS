"""Clean-room Sleeper public API client (K129).

Inspired by dtsong/sleeper-api-wrapper trending endpoint — no third-party dependency.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from ceminidfs.data.fetch import _cache_dir

SLEEPER_API_BASE = "https://api.sleeper.app/v1"
TrendDirection = Literal["add", "drop"]
DEFAULT_PLAYER_CACHE_TTL_SECONDS = 7 * 24 * 3600


@dataclass(frozen=True)
class TrendingPlayer:
    player_id: str
    count: int
    direction: TrendDirection


def _http_get_json(url: str, *, timeout: float = 30.0) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "ceminidfs/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_trending_players(
    *,
    direction: TrendDirection = "add",
    lookback_hours: int = 24,
    limit: int = 25,
) -> list[TrendingPlayer]:
    """Fetch Sleeper trending add or drop counts."""

    if direction not in {"add", "drop"}:
        raise ValueError("direction must be 'add' or 'drop'")
    if lookback_hours < 1:
        raise ValueError("lookback_hours must be >= 1")
    if limit < 1:
        raise ValueError("limit must be >= 1")

    url = (
        f"{SLEEPER_API_BASE}/players/nfl/trending/{direction}"
        f"?lookback_hours={lookback_hours}&limit={limit}"
    )
    payload = _http_get_json(url)
    if not isinstance(payload, list):
        raise ValueError(f"unexpected Sleeper trending response: {type(payload)!r}")

    trending: list[TrendingPlayer] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        player_id = str(row.get("player_id", "")).strip()
        if not player_id:
            continue
        trending.append(
            TrendingPlayer(
                player_id=player_id,
                count=int(row.get("count", 0)),
                direction=direction,
            )
        )
    return trending


def fetch_trending_dataframe(
    *,
    lookback_hours: int = 24,
    limit: int = 25,
) -> pd.DataFrame:
    """Return trending adds and drops in one frame."""

    adds = fetch_trending_players(
        direction="add", lookback_hours=lookback_hours, limit=limit
    )
    drops = fetch_trending_players(
        direction="drop", lookback_hours=lookback_hours, limit=limit
    )
    rows: list[dict[str, Any]] = []
    for item in adds:
        rows.append(
            {
                "player_id": item.player_id,
                "direction": item.direction,
                "count": item.count,
            }
        )
    for item in drops:
        rows.append(
            {
                "player_id": item.player_id,
                "direction": item.direction,
                "count": item.count,
            }
        )
    return pd.DataFrame(rows)


def sleeper_player_cache_path() -> Path:
    return _cache_dir() / "sleeper_players_nfl.json"


def load_player_index(
    *,
    cache_path: Path | None = None,
    max_age_seconds: int = DEFAULT_PLAYER_CACHE_TTL_SECONDS,
    force_refresh: bool = False,
) -> dict[str, dict[str, Any]]:
    """Load Sleeper NFL player index (id -> metadata), with disk cache."""

    path = cache_path or sleeper_player_cache_path()
    if not force_refresh and path.is_file():
        age = time.time() - path.stat().st_mtime
        if age <= max_age_seconds:
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                return payload

    url = f"{SLEEPER_API_BASE}/players/nfl"
    payload = _http_get_json(url, timeout=120.0)
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected Sleeper players response: {type(payload)!r}")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return payload


def player_display_name(player: Mapping[str, Any]) -> str:
    """Best-effort display name from Sleeper player object."""

    if not isinstance(player, dict):
        return ""
    for key in ("full_name", "search_full_name", "last_name"):
        value = str(player.get(key, "")).strip()
        if value and key != "last_name":
            return value
    first = str(player.get("first_name", "")).strip()
    last = str(player.get("last_name", "")).strip()
    return " ".join(part for part in (first, last) if part).strip()


def normalize_player_name(name: str) -> str:
    """Normalize a player name for fuzzy slate matching."""

    cleaned = re.sub(r"[^a-z0-9\s]", "", name.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def trending_with_names(
    *,
    lookback_hours: int = 24,
    limit: int = 25,
    player_index: dict[str, dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """Trending frame enriched with Sleeper names and teams."""

    frame = fetch_trending_dataframe(lookback_hours=lookback_hours, limit=limit)
    if frame.empty:
        return frame

    index = player_index if player_index is not None else load_player_index()
    names: list[str] = []
    teams: list[str] = []
    positions: list[str] = []
    for player_id in frame["player_id"].astype(str):
        meta = index.get(player_id, {})
        names.append(player_display_name(meta))
        teams.append(str(meta.get("team") or "").upper())
        positions.append(str(meta.get("position") or "").upper())
    frame = frame.copy()
    frame["name"] = names
    frame["team"] = teams
    frame["position"] = positions
    frame["name_norm"] = frame["name"].map(normalize_player_name)
    return frame
