from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ceminidfs.data.salary import apply_salary_fppg_placeholder, parse_salary_csv
from ceminidfs.export.canonical import write_canonical_csv
from ceminidfs.models.simulate import add_simulation_columns
from ceminidfs.models.ownership import (
    load_ownership_calibration,
    project_ownership_calibrated,
)
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
            rows = _fill_dst_salary_fppg(rows)
            _write_projection_base(stats_df, cfg)
            if mode == "auto" and not any(
                row.get("fd_projection") or row.get("dk_projection") for row in rows
            ):
                rows = apply_salary_fppg_placeholder(rows, site or _site_from_rows(rows))
        except (FileNotFoundError, ValueError):
            if mode == "diy":
                raise
            rows = apply_salary_fppg_placeholder(rows, site or _site_from_rows(rows))

    if _simulation_enabled(cfg):
        rows = _add_simulation_to_rows(rows, cfg)

    if _ownership_enabled(cfg):
        rows = _add_ownership_to_rows(rows, cfg, site or _site_from_rows(rows))

    write_canonical_csv(rows, output_path)
    return output_path


def _ownership_enabled(config: Mapping[str, Any]) -> bool:
    ownership_cfg = config.get("ownership", {})
    ownership_enabled = (
        bool(ownership_cfg.get("enabled")) if isinstance(ownership_cfg, Mapping) else False
    )
    return ownership_enabled or bool(config.get("project_ownership"))


def _simulation_enabled(config: Mapping[str, Any]) -> bool:
    simulate_cfg = config.get("simulate", {})
    simulate_enabled = bool(simulate_cfg.get("enabled")) if isinstance(simulate_cfg, Mapping) else False
    return simulate_enabled or bool(config.get("run_simulation"))


def _add_ownership_to_rows(
    rows: list[dict[str, Any]],
    config: Mapping[str, Any],
    site: str,
) -> list[dict[str, Any]]:
    ownership_cfg = config.get("ownership", {})
    calibration_path = (
        ownership_cfg.get("calibration_path") if isinstance(ownership_cfg, Mapping) else None
    )
    calibration = load_ownership_calibration(calibration_path) if calibration_path else None
    return project_ownership_calibrated(rows, calibration=calibration, site=site)


def _site_from_rows(rows: list[dict[str, Any]]) -> str:
    if rows and rows[0].get("dk_id") and not rows[0].get("fd_id"):
        return "draftkings"
    return "fanduel"


def _fill_dst_salary_fppg(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filled: list[dict[str, Any]] = []
    for row in rows:
        mapped = dict(row)
        salary_fppg = row.get("salary_fppg", "")
        if _is_empty_projection(mapped.get("fd_projection")) and _position_is_dst(
            mapped.get("fd_position")
        ):
            mapped["fd_projection"] = salary_fppg
        if _is_empty_projection(mapped.get("dk_projection")) and _position_is_dst(
            mapped.get("dk_position")
        ):
            mapped["dk_projection"] = salary_fppg
        filled.append(mapped)
    return filled


def _position_is_dst(value: Any) -> bool:
    return str(value or "").strip().upper() in {"DEF", "DST"}


def _is_empty_projection(value: Any) -> bool:
    if value in (None, ""):
        return True
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return bool(pd.isna(numeric) or float(numeric) == 0.0)


def _add_simulation_to_rows(
    rows: list[dict[str, Any]],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if _is_empty_projection(row.get("fd_projection")):
            continue
        candidates.append(
            {
                "_row_index": index,
                "player_id": row.get("fd_id") or row.get("dk_id") or row.get("player_key") or index,
                "fd_projection": row.get("fd_projection"),
                "team": row.get("team", ""),
                "opp": row.get("opp") or row.get("opponent") or "",
                "game": row.get("game", ""),
                "position": row.get("fd_position") or row.get("dk_position") or row.get("position", ""),
            }
        )

    merged = [dict(row) for row in rows]
    if not candidates:
        return merged

    simulate_cfg = config.get("simulate", {})
    if not isinstance(simulate_cfg, Mapping):
        simulate_cfg = {}
    n_iterations = int(simulate_cfg.get("n_iterations", config.get("simulation_iterations", 5000)))
    seed = simulate_cfg.get("seed", config.get("simulation_seed"))
    method = str(simulate_cfg.get("method", config.get("simulation_method", "team_shock")))

    simulated = add_simulation_columns(
        pd.DataFrame(candidates),
        n_iterations=n_iterations,
        seed=int(seed) if seed is not None else None,
        method=method,
    )
    for _, row in simulated.iterrows():
        index = int(row["_row_index"])
        merged[index]["Projection Floor"] = row["Projection Floor"]
        merged[index]["Projection Ceil"] = row["Projection Ceil"]
    return merged


def _write_projection_base(stats_df: pd.DataFrame, config: Mapping[str, Any]) -> Path:
    work_dir = Path(config.get("work_dir", "."))
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "player_projection_base.parquet"
    stats_df.to_parquet(path, index=False)
    return path
