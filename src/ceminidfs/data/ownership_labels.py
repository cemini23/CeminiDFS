"""Load paid ownership labels for ownership calibration."""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ceminidfs.data.benchmark import (
    FIRST_NAME_KEYS,
    LAST_NAME_KEYS,
    NAME_KEYS,
    OWNERSHIP_KEYS,
    POS_KEYS,
    TEAM_KEYS,
)


def load_ownership_labels(path: str | Path) -> list[dict[str, Any]]:
    """Parse a paid ownership CSV into normalized label rows."""

    labels_path = Path(path)
    if not labels_path.is_file():
        raise FileNotFoundError(f"Ownership labels CSV not found: {labels_path}")

    with labels_path.open("r", newline="", encoding="utf-8-sig") as src:
        reader = csv.DictReader(src)
        if not reader.fieldnames:
            raise ValueError("empty CSV")
        rows = [_parse_label_row(row) for row in reader]
    return [row for row in rows if row]


def _parse_label_row(row: Mapping[str, str]) -> dict[str, Any]:
    player_name = _player_name(row)
    team = _pick(row, TEAM_KEYS).upper()
    position = _pick(row, POS_KEYS).upper()
    ownership = _as_ownership(_pick(row, OWNERSHIP_KEYS))
    if not player_name or ownership is None:
        return {}
    return {
        "join_key": _normalize_join_key(player_name, team, position),
        "player_name": player_name,
        "team": team,
        "position": position,
        "ownership": ownership,
    }


def _player_name(row: Mapping[str, str]) -> str:
    name = _pick(row, NAME_KEYS)
    if name:
        return name
    first = _pick(row, FIRST_NAME_KEYS)
    last = _pick(row, LAST_NAME_KEYS)
    return " ".join(part for part in (first, last) if part).strip()


def _pick(row: Mapping[str, str], keys: tuple[str, ...]) -> str:
    values = {_normalize_header(key): value for key, value in row.items()}
    for key in keys:
        value = values.get(_normalize_header(key))
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _as_ownership(value: str) -> float | None:
    clean = str(value or "").replace("%", "").replace(",", "").strip()
    if not clean:
        return None
    try:
        parsed = float(clean)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return max(0.0, min(100.0, parsed))


def _normalize_header(value: str) -> str:
    return str(value).strip().lower()


def _normalize_join_key(name: Any, team: Any, position: Any) -> str:
    return "|".join(
        (
            _normalize_token(name),
            _normalize_token(team),
            _normalize_token(position).upper(),
        )
    )


def _normalize_token(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())
