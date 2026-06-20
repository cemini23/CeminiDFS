from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ceminidfs.export.normalize import normalize_site
from ceminidfs.export.optimize import LINEUP_HEADERS

SALARY_CAPS = {
    "fanduel": 60_000,
    "draftkings": 50_000,
}


def validate_lineups_csv(
    path: str | Path,
    site: str = "fanduel",
    expected_count: int = 150,
    *,
    players_csv: str | Path | None = None,
) -> dict[str, Any]:
    """Validate an optimizer lineup CSV against site roster slots."""

    site_key = normalize_site(site)
    expected_header = LINEUP_HEADERS[site_key]
    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"Lineups CSV not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Lineups CSV is empty: {csv_path}") from exc
        rows = list(reader)

    if header != expected_header:
        raise ValueError(f"Lineups CSV header mismatch: expected {expected_header}, got {header}")

    lineup_count = len(rows)
    if lineup_count != expected_count:
        raise ValueError(f"Expected {expected_count} lineups, found {lineup_count}")

    salary_by_name = _salary_lookup(players_csv) if players_csv else {}
    salary_cap = SALARY_CAPS.get(site_key)

    empty_slots = 0
    duplicate_players = 0
    salary_violations = 0

    for row_idx, row in enumerate(rows, start=2):
        if len(row) != len(expected_header):
            raise ValueError(
                f"Lineup row {row_idx} has {len(row)} cells; expected {len(expected_header)}"
            )
        empty_slots += sum(1 for cell in row if not cell.strip())

        names = [cell.strip() for cell in row if cell.strip()]
        if len(names) != len(set(_normalize_name(name) for name in names)):
            duplicate_players += 1

        if salary_by_name and salary_cap is not None:
            total = sum(salary_by_name.get(_normalize_name(name), 0) for name in names)
            if total > salary_cap:
                salary_violations += 1

    if empty_slots:
        raise ValueError(f"Lineups CSV contains {empty_slots} empty required slot(s)")
    if duplicate_players:
        raise ValueError(f"Lineups CSV contains {duplicate_players} lineup(s) with duplicate players")
    if salary_violations:
        raise ValueError(f"Lineups CSV contains {salary_violations} lineup(s) over the salary cap")

    return {
        "lineup_count": lineup_count,
        "site": site_key,
        "valid": True,
        "empty_slots": 0,
        "duplicate_lineups": duplicate_players,
        "salary_violations": salary_violations,
    }


def _salary_lookup(players_csv: str | Path) -> dict[str, int]:
    path = Path(players_csv)
    if not path.is_file():
        raise FileNotFoundError(f"Players CSV not found: {path}")

    lookup: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            salary = _parse_salary(row.get("Salary") or row.get("salary"))
            if salary is None:
                continue
            for key in ("Nickname", "Name", "name", "player_name"):
                value = str(row.get(key, "")).strip()
                if value:
                    lookup[_normalize_name(value)] = salary
            first = str(row.get("First Name", "")).strip()
            last = str(row.get("Last Name", "")).strip()
            if first and last:
                lookup[_normalize_name(f"{first} {last}")] = salary
    return lookup


def _parse_salary(value: Any) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).replace("$", "").replace(",", "").strip()
    try:
        return int(float(text))
    except ValueError:
        return None


def _normalize_name(name: str) -> str:
    return " ".join(str(name).strip().lower().split())
