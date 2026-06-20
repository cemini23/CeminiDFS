"""Load paid projection CSV exports (Stokastic, FantasyLabs, generic)."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ceminidfs.pipeline.engine import normalize_join_key


NAME_KEYS = ("name", "player", "player name", "nickname", "full name")
FIRST_NAME_KEYS = ("first name", "firstname")
LAST_NAME_KEYS = ("last name", "lastname")
POS_KEYS = ("position", "pos", "roster position")
TEAM_KEYS = ("team", "team abbrev", "teamabbrev", "tm")
SALARY_KEYS = ("salary", "fd salary", "fanduel salary", "sal")
PROJECTION_KEYS = (
    "fppg",
    "projection",
    "proj",
    "points",
    "fd pts",
    "fantasy points",
    "median",
    "labs projection",
    "stokastic projection",
    "expected points",
)
OWNERSHIP_KEYS = ("ownership", "own%", "projected ownership", "proj ownership", "own")
ID_KEYS = ("id", "player id", "fd id", "playerid")


def detect_benchmark_source(fieldnames: Sequence[str]) -> str:
    """Infer the paid export vendor from CSV headers."""

    headers = {_normalize_header(field) for field in fieldnames}
    joined = " ".join(sorted(headers))
    if "stokastic" in joined or "boom" in headers or "own%" in headers:
        return "stokastic"
    if "fantasylabs" in joined or "labs projection" in headers:
        return "fantasylabs"
    if "establish the run" in joined or "etr projection" in headers:
        return "etr"
    return "generic"


def parse_benchmark_csv(
    path: str | Path,
    *,
    site: str = "fanduel",
    source: str | None = None,
    season: int | None = None,
    week: int | None = None,
) -> list[dict[str, Any]]:
    """Parse a paid projection export into normalized benchmark rows."""

    benchmark_path = Path(path)
    if not benchmark_path.is_file():
        raise FileNotFoundError(f"Benchmark CSV not found: {benchmark_path}")

    with benchmark_path.open("r", newline="", encoding="utf-8-sig") as src:
        reader = csv.DictReader(src)
        if not reader.fieldnames:
            raise ValueError("empty CSV")
        source_key = source or detect_benchmark_source(reader.fieldnames)
        rows = [
            _parse_benchmark_row(
                row,
                source=source_key,
                site=site,
                season=season,
                week=week,
            )
            for row in reader
        ]
    return [row for row in rows if row.get("player_name") and row.get("projection") is not None]


def write_benchmark_snapshot(rows: list[dict[str, Any]], path: str | Path) -> Path:
    """Write a versioned benchmark snapshot JSON preserving raw vendor columns."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return out


def _parse_benchmark_row(
    row: Mapping[str, str],
    *,
    source: str,
    site: str,
    season: int | None,
    week: int | None,
) -> dict[str, Any]:
    player_name = _player_name(row)
    team = _pick(row, TEAM_KEYS).upper()
    position = _pick(row, POS_KEYS).upper()
    projection = _as_float(_pick(row, PROJECTION_KEYS))
    salary = _as_int(_pick(row, SALARY_KEYS))
    player_id = _pick(row, ID_KEYS)
    ownership = _as_float(_pick(row, OWNERSHIP_KEYS), default=None)

    site_key = site.lower()
    projection_field = "fd_projection" if site_key.startswith("fan") else "dk_projection"

    snapshot = {
        "source": source,
        "site": site_key,
        "season": season,
        "week": week,
        "player_id": player_id,
        "player_name": player_name,
        "team": team,
        "position": position,
        "salary": salary,
        "projection": projection,
        projection_field: projection,
        "ownership": ownership,
        "join_key": normalize_join_key(player_name, team, position),
        "raw": dict(row),
    }
    return snapshot


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


def _as_float(value: str, default: float | None = 0.0) -> float | None:
    clean = _clean_number(value)
    if not clean:
        return default
    try:
        return float(clean)
    except (TypeError, ValueError):
        return default


def _as_int(value: str) -> int | None:
    clean = _clean_number(value)
    if not clean:
        return None
    try:
        return int(float(clean))
    except (TypeError, ValueError):
        return None


def _clean_number(value: str) -> str:
    return str(value or "").replace("$", "").replace("%", "").replace(",", "").strip()


def _normalize_header(value: str) -> str:
    return str(value).strip().lower()
