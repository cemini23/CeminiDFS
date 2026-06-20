from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ceminidfs.data.salary import apply_salary_fppg_placeholder, parse_salary_csv
from ceminidfs.export.canonical import write_canonical_csv
from ceminidfs.pipeline.engine import build_diy_projections, merge_projections_into_canonical


def project_week(
    season: int,
    week: int,
    salary_path: str | Path,
    config: Mapping[str, Any] | None = None,
) -> Path:
    """Create a canonical projection CSV from a salary export."""
    cfg = dict(config or {})
    salary_csv = Path(salary_path)

    output_path = Path(
        cfg.get("canonical_path")
        or Path(cfg.get("work_dir", ".")) / f"canonical_projections_{season}_w{week}.csv"
    )

    site = str(cfg["site"]) if cfg.get("site") else None
    rows = parse_salary_csv(salary_csv, season, week, site=site)
    mode = str(cfg.get("projection_mode", "auto")).lower()
    if mode not in {"auto", "diy", "fppg"}:
        raise ValueError("projection_mode must be one of: auto, diy, fppg")

    if mode == "fppg" or cfg.get("use_salary_fppg") is True:
        rows = apply_salary_fppg_placeholder(rows, site or _site_from_rows(rows))
    elif mode in {"auto", "diy"}:
        try:
            stats_df = build_diy_projections(season, week, rows, cfg)
            rows = merge_projections_into_canonical(rows, stats_df)
            _write_projection_base(stats_df, cfg)
            if mode == "auto" and not any(
                row.get("fd_projection") or row.get("dk_projection") for row in rows
            ):
                rows = apply_salary_fppg_placeholder(rows, site or _site_from_rows(rows))
        except (FileNotFoundError, ValueError):
            if mode == "diy":
                raise
            rows = apply_salary_fppg_placeholder(rows, site or _site_from_rows(rows))

    write_canonical_csv(rows, output_path)
    return output_path


def _site_from_rows(rows: list[dict[str, Any]]) -> str:
    if rows and rows[0].get("dk_id") and not rows[0].get("fd_id"):
        return "draftkings"
    return "fanduel"


def _write_projection_base(stats_df: pd.DataFrame, config: Mapping[str, Any]) -> Path:
    work_dir = Path(config.get("work_dir", "."))
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "player_projection_base.parquet"
    stats_df.to_parquet(path, index=False)
    return path
