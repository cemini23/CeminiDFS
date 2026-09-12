"""Parse operator research CSVs into lock and exclude name lists.

Does not scrape. The operator supplies a local CSV with a name column plus
``lock`` / ``exclude`` / ``fade`` flag columns.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

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
EXCLUDE_HEADERS = ("exclude", "fade")
TRUTHY = frozenset({"1", "true", "yes", "y", "x", "lock", "exclude", "fade"})


def parse_research_locks(path: str | Path) -> tuple[list[str], list[str]]:
    """Return ``(locks, excludes)`` from a research CSV. Unknown schema skips."""

    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"Research CSV not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        headers = [str(name).strip() for name in (reader.fieldnames or []) if name]
        if not headers:
            print("WARNING: research CSV has no headers; skip locks/excludes", file=sys.stderr)
            return [], []
        fields = {name.lower(): name for name in headers}
        name_key = _first_header(fields, NAME_HEADERS)
        lock_key = _first_header(fields, LOCK_HEADERS)
        exclude_keys = [fields[token] for token in EXCLUDE_HEADERS if token in fields]
        if name_key is None or (lock_key is None and not exclude_keys):
            print(
                f"WARNING: research CSV headers unknown {headers}; skip locks/excludes",
                file=sys.stderr,
            )
            return [], []

        locks: list[str] = []
        excludes: list[str] = []
        for row in reader:
            name = str(row.get(name_key) or "").strip()
            if not name:
                continue
            if lock_key is not None and _is_flag(row.get(lock_key)):
                locks.append(name)
            if any(_is_flag(row.get(key)) for key in exclude_keys):
                excludes.append(name)
        return locks, excludes


def _first_header(fields: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for token in candidates:
        if token in fields:
            return fields[token]
    return None


def _is_flag(value: object) -> bool:
    return str(value or "").strip().lower() in TRUTHY
