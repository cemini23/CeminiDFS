"""Parse operator research CSVs into lock, exclude, and fade name lists.

Does not scrape. The operator supplies a local CSV with a name column plus
``lock`` / ``exclude`` / ``fade`` flag columns.

``exclude`` is a hard delete. ``fade`` is a soft discount. A row with both
flags is a hard exclude only.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Mapping

from ceminidfs.data.stadiums import normalize_team_abbr

NAME_HEADERS = (
    "name",
    "player",
    "player_name",
    "player name",
    "nickname",
    "full_name",
    "full name",
)
LOCK_HEADERS = ("lock",)
EXCLUDE_HEADERS = ("exclude",)
FADE_HEADERS = ("fade",)
QB_CELL_HEADERS = ("qb_cell", "qb cell")
TEAM_HEADERS = ("team", "team abbrev", "teamabbrev", "tm")
TRUTHY = frozenset({"1", "true", "yes", "y", "x", "lock", "exclude", "fade"})

# Research cell values that mean the team has no named starting quarterback.
QB_CELL_OPEN_TOKENS = frozenset({"open", "unassigned", "tbd"})


def parse_research_locks(path: str | Path) -> tuple[list[str], list[str], list[str]]:
    """Return ``(locks, excludes, fades)`` from a research CSV. Unknown schema skips.

    A row with an ``exclude`` flag is a hard exclude. The same row is not a
    fade, even when the ``fade`` flag is also set.
    """

    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"Research CSV not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        headers = _read_headers(reader)
        if not headers:
            print("WARNING: research CSV has no headers; skip locks/excludes", file=sys.stderr)
            return [], [], []
        fields = {name.lower(): name for name in headers}
        name_key, lock_key, exclude_keys, fade_keys = _schema_keys(fields)
        if name_key is None or not any((lock_key, exclude_keys, fade_keys)):
            print(
                f"WARNING: research CSV headers unknown {headers}; skip locks/excludes",
                file=sys.stderr,
            )
            return [], [], []

        return _collect_flags(reader, name_key, lock_key, exclude_keys, fade_keys)


def _first_header(fields: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for token in candidates:
        if token in fields:
            return fields[token]
    return None


def _schema_keys(
    fields: dict[str, str],
) -> tuple[str | None, str | None, list[str], list[str]]:
    return (
        _first_header(fields, NAME_HEADERS),
        _first_header(fields, LOCK_HEADERS),
        [fields[token] for token in EXCLUDE_HEADERS if token in fields],
        [fields[token] for token in FADE_HEADERS if token in fields],
    )


def _read_headers(reader: csv.DictReader) -> list[str]:
    return [str(name).strip() for name in (reader.fieldnames or []) if name]


def _collect_flags(
    reader: csv.DictReader,
    name_key: str,
    lock_key: str | None,
    exclude_keys: list[str],
    fade_keys: list[str],
) -> tuple[list[str], list[str], list[str]]:
    locks: list[str] = []
    excludes: list[str] = []
    fades: list[str] = []
    for row in reader:
        name, is_lock, is_exclude, is_fade = _classify_row(
            row, name_key, lock_key, exclude_keys, fade_keys
        )
        if not name:
            continue
        if is_lock:
            locks.append(name)
        if is_exclude:
            excludes.append(name)
        elif is_fade:
            fades.append(name)
    return locks, excludes, fades


def _classify_row(
    row: Mapping[str, object],
    name_key: str,
    lock_key: str | None,
    exclude_keys: list[str],
    fade_keys: list[str],
) -> tuple[str, bool, bool, bool]:
    name = str(row.get(name_key) or "").strip()
    if not name:
        return "", False, False, False
    is_lock = lock_key is not None and _is_flag(row.get(lock_key))
    is_exclude = any(_is_flag(row.get(key)) for key in exclude_keys)
    is_fade = not is_exclude and any(_is_flag(row.get(key)) for key in fade_keys)
    return name, is_lock, is_exclude, is_fade


def parse_research_qb_cells(path: str | Path) -> set[str]:
    """Return teams marked open by a research ``qb_cell`` column.

    Read the ``qb_cell`` value and the row team. Values ``open``,
    ``unassigned``, and ``tbd`` mark the team. Return an empty set when the
    column or the team column is absent.
    """

    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"Research CSV not found: {csv_path}")

    teams: set[str] = set()
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        headers = _read_headers(reader)
        fields = {name.lower(): name for name in headers}
        cell_key = _first_header(fields, QB_CELL_HEADERS)
        team_key = _first_header(fields, TEAM_HEADERS)
        if cell_key is None or team_key is None:
            return teams
        for row in reader:
            cell = str(row.get(cell_key) or "").strip().lower()
            if cell not in QB_CELL_OPEN_TOKENS:
                continue
            team = normalize_team_abbr(str(row.get(team_key) or ""))
            if team:
                teams.add(team)
    return teams


def _is_flag(value: object) -> bool:
    return str(value or "").strip().lower() in TRUTHY
