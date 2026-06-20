from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ceminidfs.data.salary import apply_salary_fppg_placeholder, parse_salary_csv
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

    output_path = Path(
        cfg.get("canonical_path")
        or Path(cfg.get("work_dir", ".")) / f"canonical_projections_{season}_w{week}.csv"
    )

    site = str(cfg["site"]) if cfg.get("site") else None
    rows = parse_salary_csv(salary_csv, season, week, site=site)
    if cfg.get("use_salary_fppg", True):
        rows = apply_salary_fppg_placeholder(rows, site or _site_from_rows(rows))

    write_canonical_csv(rows, output_path)
    return output_path


def _site_from_rows(rows: list[dict[str, Any]]) -> str:
    if rows and rows[0].get("dk_id") and not rows[0].get("fd_id"):
        return "draftkings"
    return "fanduel"
