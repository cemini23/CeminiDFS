"""Optional ESPN fantasy roster injury overlay (K138).

Uses MIT `espn_api` package when installed — see docs/espn-api-eval.md.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from ceminidfs.data.sleeper import normalize_player_name


def _espn_settings(config: Mapping[str, Any] | None) -> dict[str, Any]:
    espn_cfg = (config or {}).get("espn_adjunct", {})
    if not isinstance(espn_cfg, Mapping):
        espn_cfg = {}
    return {
        "enabled": bool(espn_cfg.get("enabled")),
        "league_id": espn_cfg.get("league_id"),
        "year": espn_cfg.get("year"),
        "espn_s2": espn_cfg.get("espn_s2"),
        "swid": espn_cfg.get("swid"),
    }


def fetch_injury_map(
    league_id: int,
    year: int,
    *,
    espn_s2: str | None = None,
    swid: str | None = None,
) -> dict[str, str]:
    """Return normalized player name -> injury status from ESPN league rosters."""

    try:
        from espn_api.football import League
    except ImportError as exc:
        raise RuntimeError(
            "espn_api not installed. Install with: pip install -e '.[espn]'"
        ) from exc

    kwargs: dict[str, Any] = {"league_id": int(league_id), "year": int(year)}
    if espn_s2 and swid:
        kwargs["espn_s2"] = espn_s2
        kwargs["swid"] = swid

    league = League(**kwargs)
    injury_map: dict[str, str] = {}
    for team in league.teams:
        for player in team.roster:
            name = _player_name(player)
            if not name:
                continue
            status = _player_injury_status(player)
            if not status:
                continue
            key = normalize_player_name(name)
            injury_map[key] = status
    return injury_map


def _player_name(player: Any) -> str:
    for attr in ("name", "fullName", "full_name"):
        value = getattr(player, attr, None)
        if value:
            return str(value).strip()
    first = str(getattr(player, "firstName", "") or getattr(player, "first_name", "")).strip()
    last = str(getattr(player, "lastName", "") or getattr(player, "last_name", "")).strip()
    return " ".join(part for part in (first, last) if part).strip()


def _player_injury_status(player: Any) -> str:
    for attr in ("injuryStatus", "injury_status", "status"):
        value = getattr(player, attr, None)
        if value in (None, ""):
            continue
        token = str(value).strip().upper()
        if token in {"ACTIVE", "NORMAL", "HEALTHY"}:
            return ""
        return token
    return ""


def _row_name(row: Mapping[str, Any]) -> str:
    for key in ("name", "player_name", "Nickname"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def apply_espn_injury_overlay(
    rows: list[dict[str, Any]],
    *,
    config: Mapping[str, Any] | None = None,
    injury_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Fill empty injury_status on canonical rows from ESPN roster map."""

    settings = _espn_settings(config)
    if not settings["enabled"]:
        return rows

    mapping = injury_map
    if mapping is None:
        league_id = settings["league_id"]
        if league_id in (None, ""):
            return rows
        year = settings["year"]
        if year in (None, ""):
            if rows and rows[0].get("slate_id"):
                match = re.match(r"(\d{4})_", str(rows[0]["slate_id"]))
                year = int(match.group(1)) if match else None
            if year is None:
                return rows
        mapping = fetch_injury_map(
            int(league_id),
            int(year),
            espn_s2=settings["espn_s2"],
            swid=settings["swid"],
        )

    if not mapping:
        return rows

    enriched: list[dict[str, Any]] = []
    for row in rows:
        mapped = dict(row)
        current = str(mapped.get("injury_status", "") or "").strip()
        if not current:
            name_norm = normalize_player_name(_row_name(row))
            if name_norm and name_norm in mapping:
                mapped["injury_status"] = mapping[name_norm]
                mapped["injury_source"] = "espn_adjunct"
        enriched.append(mapped)
    return enriched


def probe_league(
    league_id: int,
    year: int,
    *,
    espn_s2: str | None = None,
    swid: str | None = None,
) -> dict[str, Any]:
    """Summarize ESPN league connectivity for CLI probe."""

    mapping = fetch_injury_map(league_id, year, espn_s2=espn_s2, swid=swid)
    injured = {name: status for name, status in mapping.items() if status}
    return {
        "league_id": league_id,
        "year": year,
        "roster_players": len(mapping),
        "injured_or_flagged": len(injured),
        "sample": list(injured.items())[:10],
    }
