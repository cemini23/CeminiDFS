"""Canonical projection CSV writer.

The canonical format is the site-neutral handoff between CeminiDFS projections
and downstream site-specific pydfs CSV exports.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

CANONICAL_FIELDS = [
    "slate_id",
    "player_key",
    "fd_id",
    "fd_position",
    "fd_salary",
    "fd_projection",
    "dk_id",
    "dk_position",
    "dk_salary",
    "dk_projection",
    "team",
    "opp",
    "game",
    "injury_status",
]

OPTIONAL_DISPLAY_FIELDS = [
    "name",
    "player_name",
    "Nickname",
    "First Name",
    "Last Name",
    "nickname",
    "first_name",
    "last_name",
]

OPTIONAL_PASS_THROUGH_FIELDS = [
    "Projected Ownership",
    "Projection Floor",
    "Projection Ceil",
    "Max Exposure",
    "Min Exposure",
    "Min Deviation",
    "Max Deviation",
    "projection_source",
    "coherence_risk_flag",
    "pass_protection_stress",
]


def write_canonical_csv(
    players: Iterable[Mapping[str, Any]],
    out_path: str | Path,
    *,
    include_optional: bool = True,
) -> int:
    """Write canonical projection rows and return the number of rows written."""

    rows = list(players)
    fieldnames = list(CANONICAL_FIELDS)
    for field in (*OPTIONAL_DISPLAY_FIELDS, *OPTIONAL_PASS_THROUGH_FIELDS):
        if include_optional and any(field in row for row in rows):
            fieldnames.append(field)

    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})

    return len(rows)
