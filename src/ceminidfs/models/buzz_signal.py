"""Stage-0 Sleeper buzz signal for canonical slate rows (K129)."""

from __future__ import annotations

from typing import Any, Mapping

from ceminidfs.data.sleeper import (
    normalize_player_name,
    trending_with_names,
)


def _row_name(row: Mapping[str, Any]) -> str:
    for key in ("name", "player_name", "Nickname"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    first = str(row.get("First Name", row.get("first_name", ""))).strip()
    last = str(row.get("Last Name", row.get("last_name", ""))).strip()
    return " ".join(part for part in (first, last) if part).strip()


def _row_team(row: Mapping[str, Any]) -> str:
    return str(row.get("team", "")).strip().upper()


def _buzz_settings(config: Mapping[str, Any]) -> dict[str, Any]:
    buzz_cfg = config.get("buzz_signal", {})
    if not isinstance(buzz_cfg, Mapping):
        buzz_cfg = {}
    return {
        "enabled": bool(buzz_cfg.get("enabled")),
        "lookback_hours": int(buzz_cfg.get("lookback_hours", 24)),
        "limit": int(buzz_cfg.get("limit", 25)),
        "ownership_boost_per_1k": float(buzz_cfg.get("ownership_boost_per_1k", 0.5)),
        "max_ownership_boost": float(buzz_cfg.get("max_ownership_boost", 8.0)),
        "skip_network": bool(buzz_cfg.get("skip_network", False)),
    }


def build_buzz_lookup(
    *,
    lookback_hours: int = 24,
    limit: int = 25,
) -> dict[tuple[str, str], dict[str, int]]:
    """Map (name_norm, team) -> {add, drop} trending counts."""

    trending = trending_with_names(lookback_hours=lookback_hours, limit=limit)
    if trending.empty:
        return {}

    lookup: dict[tuple[str, str], dict[str, int]] = {}
    for _, row in trending.iterrows():
        name_norm = str(row.get("name_norm", "")).strip()
        if not name_norm:
            continue
        team = str(row.get("team", "")).strip().upper()
        direction = str(row.get("direction", "")).strip().lower()
        count = int(row.get("count", 0))
        key = (name_norm, team)
        bucket = lookup.setdefault(key, {"add": 0, "drop": 0})
        if direction in bucket:
            bucket[direction] = max(bucket[direction], count)

        # Also index team-agnostic name for players where team differs (FA/trades)
        if team:
            generic_key = (name_norm, "")
            generic = lookup.setdefault(generic_key, {"add": 0, "drop": 0})
            if direction in generic:
                generic[direction] = max(generic[direction], count)

    return lookup


def attach_buzz_columns(
    rows: list[dict[str, Any]],
    *,
    config: Mapping[str, Any] | None = None,
    lookup: dict[tuple[str, str], dict[str, int]] | None = None,
) -> list[dict[str, Any]]:
    """Attach sleeper_buzz_add/drop counts to canonical rows."""

    settings = _buzz_settings(config or {})
    if not settings["enabled"]:
        return rows
    if settings["skip_network"] and lookup is None:
        return rows

    buzz_lookup = lookup
    if buzz_lookup is None:
        buzz_lookup = build_buzz_lookup(
            lookback_hours=settings["lookback_hours"],
            limit=settings["limit"],
        )

    enriched: list[dict[str, Any]] = []
    for row in rows:
        mapped = dict(row)
        name_norm = normalize_player_name(_row_name(row))
        team = _row_team(row)
        counts = buzz_lookup.get((name_norm, team)) or buzz_lookup.get((name_norm, "")) or {
            "add": 0,
            "drop": 0,
        }
        mapped["sleeper_buzz_add"] = counts.get("add", 0)
        mapped["sleeper_buzz_drop"] = counts.get("drop", 0)
        enriched.append(mapped)
    return enriched


def apply_buzz_ownership_boost(
    rows: list[dict[str, Any]],
    *,
    config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Nudge projected ownership for trending adds (capped)."""

    settings = _buzz_settings(config or {})
    if not settings["enabled"]:
        return rows

    per_1k = settings["ownership_boost_per_1k"]
    max_boost = settings["max_ownership_boost"]
    boosted: list[dict[str, Any]] = []
    for row in rows:
        mapped = dict(row)
        add_count = int(mapped.get("sleeper_buzz_add", 0) or 0)
        ownership = mapped.get("Projected Ownership")
        if add_count > 0 and ownership not in (None, ""):
            try:
                base = float(ownership)
            except (TypeError, ValueError):
                boosted.append(mapped)
                continue
            boost = min(max_boost, (add_count / 1000.0) * per_1k)
            mapped["Projected Ownership"] = f"{base + boost:.2f}"
        boosted.append(mapped)
    return boosted


def apply_buzz_signal(
    rows: list[dict[str, Any]],
    *,
    config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Attach buzz columns and optionally boost ownership."""

    with_buzz = attach_buzz_columns(rows, config=config)
    return apply_buzz_ownership_boost(with_buzz, config=config)
