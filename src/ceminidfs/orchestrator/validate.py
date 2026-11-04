from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

from ceminidfs.export.normalize import normalize_site
from ceminidfs.export.optimize import LINEUP_HEADERS, SHOWDOWN_SITES

SALARY_CAPS = {
    "fanduel": 60_000,
    "draftkings": 50_000,
    "fanduel_showdown": 60_000,
    "draftkings_showdown": 50_000,
}

# Lineup header columns whose slot costs the captain (1.5x) salary.
CAPTAIN_HEADERS = frozenset({"MVP", "CPT"})


def _read_lineup_rows(csv_path: Path, expected_header: list[str]) -> list[list[str]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"Lineups CSV is empty: {csv_path}") from exc
        rows = list(reader)
    if header != expected_header:
        raise ValueError(f"Lineups CSV header mismatch: expected {expected_header}, got {header}")
    return rows


def _check_lineup_count(lineup_count: int, expected_count: int) -> None:
    if lineup_count == 0:
        raise ValueError("Expected at least 1 lineup, found 0")
    if lineup_count > expected_count:
        raise ValueError(f"Expected at most {expected_count} lineups, found {lineup_count}")
    if lineup_count < expected_count:
        print(
            f"WARNING: wrote {lineup_count} lineups; requested {expected_count} "
            "(exposure cap or an infeasible stack can shorten the file)",
            file=sys.stderr,
        )


def _duplicate_count(names: list[str]) -> int:
    normalized = {_normalize_name(name) for name in names}
    return int(len(names) != len(normalized))


def _projection_totals(names: list[str], lookup: dict[str, float]) -> tuple[int, float]:
    matched = 0
    points = 0.0
    for name in names:
        value = lookup.get(_normalize_name(name))
        if value is not None:
            matched += 1
            points += value
    return matched, points


def _lineup_salary(
    salary_lookup: dict[str, Any],
    header: list[str],
    names: list[str],
    site_key: str,
) -> float:
    if site_key in SHOWDOWN_SITES:
        return sum(
            _showdown_slot_cost(salary_lookup, slot, name)
            for slot, name in zip(header, names)
        )
    return sum(salary_lookup.get(_normalize_name(name), 0) for name in names)


def _raise_on_problems(
    empty_slots: int,
    duplicate_players: int,
    salary_violations: int,
    projection_lookup: dict[str, float],
    matched_projection_players: int,
    total_projected_points: float,
) -> None:
    if empty_slots:
        raise ValueError(f"Lineups CSV contains {empty_slots} empty required slot(s)")
    if duplicate_players:
        raise ValueError(f"Lineups CSV contains {duplicate_players} lineup(s) with duplicate players")
    if salary_violations:
        raise ValueError(f"Lineups CSV contains {salary_violations} lineup(s) over the salary cap")
    if projection_lookup and matched_projection_players and total_projected_points <= 0:
        raise ValueError(
            "Lineups CSV carries no projected points; every projection is blank or zero"
        )


def _row_totals(
    row: list[str],
    header: list[str],
    projection_lookup: dict[str, float],
    salary_lookup: dict[str, Any],
    salary_cap: int | None,
    site_key: str,
) -> tuple[int, int, int, int, float]:
    empty = sum(1 for cell in row if not cell.strip())
    names = [cell.strip() for cell in row if cell.strip()]
    duplicates = _duplicate_count(names)
    matched, points = _projection_totals(names, projection_lookup)
    violations = 0
    if salary_lookup and salary_cap is not None:
        violations = int(_lineup_salary(salary_lookup, header, names, site_key) > salary_cap)
    return empty, duplicates, violations, matched, points


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

    rows = _read_lineup_rows(csv_path, expected_header)
    lineup_count = len(rows)
    _check_lineup_count(lineup_count, expected_count)

    salary_lookup = _salary_lookup(players_csv, site_key) if players_csv else {}
    projection_lookup = _projection_lookup(players_csv) if players_csv else {}
    salary_cap = SALARY_CAPS.get(site_key)

    empty_slots = 0
    duplicate_players = 0
    salary_violations = 0
    matched_projection_players = 0
    total_projected_points = 0.0

    for row_idx, row in enumerate(rows, start=2):
        if len(row) != len(expected_header):
            raise ValueError(
                f"Lineup row {row_idx} has {len(row)} cells; expected {len(expected_header)}"
            )
        empty, duplicates, violations, matched, points = _row_totals(
            row,
            expected_header,
            projection_lookup,
            salary_lookup,
            salary_cap,
            site_key,
        )
        empty_slots += empty
        duplicate_players += duplicates
        salary_violations += violations
        matched_projection_players += matched
        total_projected_points += points

    _raise_on_problems(
        empty_slots,
        duplicate_players,
        salary_violations,
        projection_lookup,
        matched_projection_players,
        total_projected_points,
    )

    return {
        "lineup_count": lineup_count,
        "site": site_key,
        "valid": True,
        "empty_slots": 0,
        "duplicate_lineups": duplicate_players,
        "salary_violations": salary_violations,
    }


def _salary_lookup(players_csv: str | Path, site_key: str) -> dict[str, Any]:
    """Map normalized player names to salaries from a players CSV.

    Classic sites map a name to its single salary. Showdown sites map a name
    to ``{"cpt": ..., "flex": ...}`` when the CSV carries CPT/FLEX roster rows
    (row salaries are slot-specific: CPT already at 1.5x); when only FLEX
    prices exist, the captain slot falls back to round(flex * 1.5).
    """
    path = Path(players_csv)
    if not path.is_file():
        raise FileNotFoundError(f"Players CSV not found: {path}")

    showdown = site_key in SHOWDOWN_SITES
    lookup: dict[str, Any] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            salary = _parse_salary(row.get("Salary") or row.get("salary"))
            if salary is None:
                continue
            names: list[str] = []
            for key in ("Nickname", "Name", "name", "player_name"):
                value = str(row.get(key, "")).strip()
                if value:
                    names.append(value)
            first = str(row.get("First Name", "")).strip()
            last = str(row.get("Last Name", "")).strip()
            if first and last:
                names.append(f"{first} {last}")

            roster = str(row.get("Roster Position") or row.get("roster position") or "")
            roster = roster.strip().upper()
            for name in names:
                norm = _normalize_name(name)
                if not showdown:
                    lookup[norm] = salary
                else:
                    entry = lookup.setdefault(norm, {"cpt": None, "flex": None})
                    if roster == "CPT":
                        entry["cpt"] = salary
                    else:
                        entry["flex"] = salary
    return lookup


def _projection_lookup(players_csv: str | Path) -> dict[str, float]:
    """Map normalized player names to projected points from a players CSV."""

    path = Path(players_csv)
    if not path.is_file():
        return {}
    lookup: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            projection = _parse_projection(row)
            if projection is None:
                continue
            names: list[str] = []
            for key in ("Nickname", "Name", "name", "player_name"):
                value = str(row.get(key, "")).strip()
                if value:
                    names.append(value)
            first = str(row.get("First Name", "")).strip()
            last = str(row.get("Last Name", "")).strip()
            if first and last:
                names.append(f"{first} {last}")
            for name in names:
                lookup[_normalize_name(name)] = projection
    return lookup


def _parse_projection(row: dict[str, Any]) -> float | None:
    for key in ("FPPG", "AvgPointsPerGame", "fd_projection", "dk_projection", "Projection"):
        value = row.get(key)
        if value in (None, ""):
            continue
        text = str(value).replace("$", "").replace(",", "").strip()
        try:
            return float(text)
        except ValueError:
            continue
    return None


def _showdown_slot_cost(
    lookup: dict[str, Any],
    slot: str,
    name: str,
) -> int:
    """Cost of one showdown lineup cell: captain slots pay the 1.5x row salary."""

    entry = lookup.get(_normalize_name(name)) or {}
    flex = entry.get("flex")
    cpt = entry.get("cpt")
    if slot in CAPTAIN_HEADERS:
        if cpt is not None:
            return cpt
        return round((flex or 0) * 1.5)
    if flex is not None:
        return flex
    return round((cpt or 0) / 1.5) if cpt else 0


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
