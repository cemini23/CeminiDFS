"""Heuristic ownership projection for canonical DFS rows."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

POSITION_SLOT_MASS = {
    "QB": 1.0,
    "RB": 2.0,
    "WR": 3.0,
    "TE": 1.0,
    "DEF": 1.0,
}

OWNERSHIP_TEMPERATURE = 1.0


def project_ownership(rows: list[dict], site: str = "fanduel") -> list[dict]:
    """Add projected ownership percentages to rows and return the same list.

    Ownership is a v1 value-rank softmax: projection per $1k of salary is
    converted to a position-local probability distribution, then scaled by
    roster slot mass so each position group sums to its expected lineup share.
    """

    site_key = _site_key(site)
    position_key = f"{site_key}_position"
    salary_key = f"{site_key}_salary"
    projection_key = f"{site_key}_projection"

    groups: dict[str, list[tuple[dict, float]]] = defaultdict(list)
    unsupported: list[dict] = []
    for row in rows:
        position = _normalize_position(row.get(position_key))
        if position not in POSITION_SLOT_MASS:
            unsupported.append(row)
            continue
        groups[position].append((row, _value_score(row.get(projection_key), row.get(salary_key))))

    for position, entries in groups.items():
        weights = _softmax([value for _, value in entries], OWNERSHIP_TEMPERATURE)
        scale = POSITION_SLOT_MASS[position] * 100.0
        for (row, _), weight in zip(entries, weights, strict=True):
            row["Projected Ownership"] = f"{weight * scale:.1f}"

    for row in unsupported:
        row["Projected Ownership"] = "0.0"

    return rows


def _site_key(site: str) -> str:
    normalized = str(site or "fanduel").strip().lower()
    if normalized in {"fanduel", "fd"}:
        return "fd"
    if normalized in {"draftkings", "dk"}:
        return "dk"
    raise ValueError("site must be one of: fanduel, draftkings")


def _normalize_position(value: Any) -> str:
    position = str(value or "").strip().upper()
    if position == "DST":
        return "DEF"
    return position


def _value_score(projection: Any, salary: Any) -> float:
    salary_float = _to_float(salary)
    if salary_float <= 0.0:
        return 0.0
    return _to_float(projection) / (salary_float / 1000.0)


def _to_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _softmax(values: list[float], temperature: float) -> list[float]:
    if not values:
        return []
    temp = max(float(temperature), 1e-9)
    max_value = max(values)
    exp_values = [math.exp((value - max_value) / temp) for value in values]
    total = sum(exp_values)
    if total <= 0.0:
        return [1.0 / len(values)] * len(values)
    return [value / total for value in exp_values]
