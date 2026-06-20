from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ceminidfs.export.canonical import write_canonical_csv
from ceminidfs.export.normalize import normalize_site


def detect_salary_site(fieldnames: Sequence[str]) -> str:
    """Infer the DFS site from a salary CSV header."""

    headers = {_normalize_header(field) for field in fieldnames}
    if "id" in headers and ("nickname" in headers or "first name" in headers):
        return "fanduel"
    if "first name" in headers:
        return "fanduel"
    if {"roster position", "teamabbrev"}.issubset(headers) or "avgpointspergame" in headers:
        return "draftkings"
    raise ValueError("Unable to detect salary site from CSV headers")


def normalize_salary_site(site: str) -> str:
    """Return the canonical salary site key."""

    return normalize_site(site)


def parse_salary_row(row: Mapping[str, str], site: str, season: int, week: int) -> dict[str, Any]:
    """Map one site salary row into the canonical schema without projections."""

    site_key = normalize_salary_site(site)
    if site_key == "fanduel":
        return _parse_fanduel_row(row, season, week)
    if site_key == "draftkings":
        return _parse_draftkings_row(row, season, week)
    raise ValueError(f"Unsupported salary site: {site!r}")


def parse_salary_csv(
    path: str | Path,
    season: int,
    week: int,
    site: str | None = None,
) -> list[dict[str, Any]]:
    """Read a salary CSV and return canonical rows without projections."""

    salary_path = Path(path)
    if not salary_path.is_file():
        raise FileNotFoundError(f"Salary CSV not found: {salary_path}")

    with salary_path.open("r", newline="", encoding="utf-8-sig") as src:
        reader = csv.DictReader(src)
        if not reader.fieldnames:
            raise ValueError("empty CSV")
        site_key = normalize_salary_site(site) if site else detect_salary_site(reader.fieldnames)
        return [parse_salary_row(row, site_key, season, week) for row in reader]


def apply_salary_fppg_placeholder(rows: list[dict[str, Any]], site: str) -> list[dict[str, Any]]:
    """Use salary-export FPPG as temporary projections for Phase 0 compatibility."""

    site_key = normalize_salary_site(site)
    projection_field = "fd_projection" if site_key == "fanduel" else "dk_projection"
    filled: list[dict[str, Any]] = []
    for row in rows:
        mapped = dict(row)
        mapped[projection_field] = row.get("salary_fppg", "")
        filled.append(mapped)
    return filled


def write_salary_canonical(
    path: str | Path,
    out_path: str | Path,
    season: int,
    week: int,
    site: str | None = None,
) -> Path:
    """Parse a salary CSV and write canonical rows without FPPG placeholders."""

    rows = parse_salary_csv(path, season, week, site=site)
    output = Path(out_path)
    write_canonical_csv(rows, output)
    return output


def _parse_fanduel_row(row: Mapping[str, str], season: int, week: int) -> dict[str, Any]:
    fd_id = _first(row, "Id", "ID", "PlayerID", "player_id", "fd_id")
    name = _first(row, "Nickname", "Name", "Player", "player_name")
    if not name:
        first = _first(row, "First Name", "FirstName", "first_name")
        last = _first(row, "Last Name", "LastName", "last_name")
        name = " ".join(part for part in (first, last) if part).strip()

    team = _first(row, "Team", "TEAM", "team", "TeamAbbrev")
    opp = _first(row, "Opponent", "OPP", "opponent")
    game = _first(row, "Game", "game", "Game Info")
    if not game and team and opp:
        game = f"{team}@{opp}"

    return {
        "slate_id": f"{season}_w{week}",
        "player_key": fd_id or name,
        "name": name,
        "player_name": name,
        "fd_id": fd_id,
        "fd_position": _first(row, "Position", "POS", "position"),
        "fd_salary": _as_int(_first(row, "Salary", "salary", "SALARY")),
        "fd_projection": "",
        "dk_id": "",
        "dk_position": "",
        "dk_salary": "",
        "dk_projection": "",
        "team": team,
        "opp": opp,
        "game": game,
        "injury_status": _first(row, "Injury Indicator", "Injury", "injury_status", "status"),
        "salary_fppg": _as_float(
            _first(row, "FPPG", "AvgPointsPerGame", "avg_points_per_game"),
            default="",
        ),
    }


def _parse_draftkings_row(row: Mapping[str, str], season: int, week: int) -> dict[str, Any]:
    dk_id = _first(row, "ID", "Id", "PlayerID", "player_id", "dk_id")
    name = _first(row, "Name", "Nickname", "Player", "player_name")
    team = _first(row, "TeamAbbrev", "Team", "TEAM", "team")
    game = _first(row, "Game Info", "Game", "game")
    opp = _opponent_from_game(game, team) or _first(row, "Opponent", "OPP", "opponent")

    return {
        "slate_id": f"{season}_w{week}",
        "player_key": dk_id or name,
        "name": name,
        "player_name": name,
        "fd_id": "",
        "fd_position": "",
        "fd_salary": "",
        "fd_projection": "",
        "dk_id": dk_id,
        "dk_position": _first(row, "Position", "Roster Position", "POS", "position"),
        "dk_salary": _as_int(_first(row, "Salary", "salary", "SALARY")),
        "dk_projection": "",
        "team": team,
        "opp": opp,
        "game": game,
        "injury_status": _first(row, "Injury Indicator", "Injury", "injury_status", "status"),
        "salary_fppg": _as_float(
            _first(row, "AvgPointsPerGame", "FPPG", "avg_points_per_game"),
            default="",
        ),
    }


def _opponent_from_game(game: str, team: str) -> str:
    matchup = game.split()[0].strip() if game else ""
    if "@" not in matchup:
        return ""
    away, home = (part.strip() for part in matchup.split("@", 1))
    if team == away:
        return home
    if team == home:
        return away
    return ""


def _first(row: Mapping[str, str], *keys: str) -> str:
    values = {_normalize_header(key): value for key, value in row.items()}
    for key in keys:
        value = values.get(_normalize_header(key))
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _as_float(value: str, default: float | str = 0.0) -> float | str:
    clean = _clean_number(value)
    if not clean:
        return default
    try:
        return float(clean)
    except (TypeError, ValueError):
        return default


def _as_int(value: str) -> int:
    clean = _clean_number(value)
    try:
        return int(float(clean))
    except (TypeError, ValueError):
        return 0


def _clean_number(value: str) -> str:
    return str(value or "").replace("$", "").replace(",", "").strip()


def _normalize_header(value: str) -> str:
    return str(value).strip().lower()
