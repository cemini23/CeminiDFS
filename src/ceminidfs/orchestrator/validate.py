from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ceminidfs.export.normalize import normalize_site
from ceminidfs.export.optimize import LINEUP_HEADERS


def validate_lineups_csv(
    path: str | Path,
    site: str = "fanduel",
    expected_count: int = 150,
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

    empty_slots = 0
    for row_idx, row in enumerate(rows, start=2):
        if len(row) != len(expected_header):
            raise ValueError(
                f"Lineup row {row_idx} has {len(row)} cells; expected {len(expected_header)}"
            )
        empty_slots += sum(1 for cell in row if not cell.strip())

    if empty_slots:
        raise ValueError(f"Lineups CSV contains {empty_slots} empty required slot(s)")

    return {
        "lineup_count": lineup_count,
        "site": site_key,
        "valid": True,
        "empty_slots": 0,
    }
