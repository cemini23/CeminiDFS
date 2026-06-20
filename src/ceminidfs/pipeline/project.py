from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Mapping


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
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with salary_csv.open("r", newline="", encoding="utf-8-sig") as src:
        reader = csv.DictReader(src)
        rows = [_canonical_row(row, season, week) for row in reader]

    fieldnames = [
        "season",
        "week",
        "player_id",
        "name",
        "player_name",
        "team",
        "opponent",
        "position",
        "salary",
        "projection",
        "baseline_fppg",
        "source",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as dst:
        writer = csv.DictWriter(dst, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def _canonical_row(row: Mapping[str, str], season: int, week: int) -> dict[str, Any]:
    salary = _first(row, "Salary", "salary", "SALARY")
    fppg = _as_float(_first(row, "FPPG", "AvgPointsPerGame", "avg_points_per_game"), default=0.0)
    player_name = _first(row, "Nickname", "Name", "Player", "player_name")
    return {
        "season": season,
        "week": week,
        "player_id": _first(row, "Id", "ID", "PlayerID", "player_id"),
        "name": player_name,
        "player_name": player_name,
        "team": _first(row, "Team", "TEAM", "team"),
        "opponent": _first(row, "Opponent", "OPP", "opponent"),
        "position": _first(row, "Position", "POS", "position"),
        "salary": _as_int(salary),
        "projection": fppg,
        "baseline_fppg": fppg,
        "source": "salary_fppg_placeholder",
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
