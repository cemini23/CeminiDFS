from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Mapping

from ceminidfs.export.canonical import write_canonical_csv


def project_week(
    season: int,
    week: int,
    salary_path: str | Path,
    config: Mapping[str, Any] | None = None,
) -> Path:
    """Create a placeholder canonical projection CSV from a salary export."""
    cfg = dict(config or {})
    salary_csv = Path(salary_path)
    if not salary_csv.exists():
        raise FileNotFoundError(f"Salary CSV not found: {salary_csv}")

    output_path = Path(
        cfg.get("canonical_path")
        or Path(cfg.get("work_dir", ".")) / f"canonical_projections_{season}_w{week}.csv"
    )

    with salary_csv.open("r", newline="", encoding="utf-8-sig") as src:
        reader = csv.DictReader(src)
        rows = [_canonical_row(row, season, week) for row in reader]

    write_canonical_csv(rows, output_path)
    return output_path


def _canonical_row(row: Mapping[str, str], season: int, week: int) -> dict[str, Any]:
    salary = _first(row, "Salary", "salary", "SALARY")
    fppg = _as_float(_first(row, "FPPG", "AvgPointsPerGame", "avg_points_per_game"), default=0.0)
    player_name = _first(row, "Nickname", "Name", "Player", "player_name")
    team = _first(row, "Team", "TEAM", "team")
    opponent = _first(row, "Opponent", "OPP", "opponent")
    position = _first(row, "Position", "POS", "position")
    fd_id = _first(row, "Id", "ID", "PlayerID", "player_id", "fd_id")
    injury = _first(row, "Injury Indicator", "Injury", "injury_status", "status")
    game = _first(row, "Game", "game")
    if not game and team and opponent:
        game = f"{team}@{opponent}"

    player_key = fd_id or player_name
    return {
        "slate_id": f"{season}_w{week}",
        "player_key": player_key,
        "name": player_name,
        "player_name": player_name,
        "fd_id": fd_id,
        "fd_position": position,
        "fd_salary": _as_int(salary),
        "fd_projection": fppg,
        "dk_id": "",
        "dk_position": "",
        "dk_salary": "",
        "dk_projection": "",
        "team": team,
        "opp": opponent,
        "game": game,
        "injury_status": injury,
    }


def _first(row: Mapping[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _as_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
