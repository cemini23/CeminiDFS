from __future__ import annotations

import sys
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
from ceminidfs.data.espn import apply_espn_injury_overlay
from ceminidfs.models.buzz_signal import apply_buzz_signal
from ceminidfs.models.dst import apply_dst_projections
from ceminidfs.pipeline.engine import (
    build_diy_projections,
    load_week_artifacts,
    merge_projections_into_canonical,
    warn_empty_fd_projections,
)


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
    mode = str(cfg.get("projection_mode", "diy")).lower()
    if mode not in {"auto", "diy", "fppg"}:
        raise ValueError("projection_mode must be one of: auto, diy, fppg")
    allow_fppg_fallback = bool(cfg.get("allow_fppg_fallback"))

    if mode == "fppg" or cfg.get("use_salary_fppg") is True:
        rows = apply_salary_fppg_placeholder(rows, site or _site_from_rows(rows))
    elif mode in {"auto", "diy"}:
        try:
            stats_df = build_diy_projections(season, week, rows, cfg)
            rows = merge_projections_into_canonical(rows, stats_df)
            warn_empty_fd_projections(rows)
            vegas, _, _ = load_week_artifacts(season, week)
            rows = apply_dst_projections(rows, vegas, config=cfg)
            rows = _fill_dst_salary_fppg(rows)
            _write_projection_base(stats_df, cfg)
            if mode == "auto" and allow_fppg_fallback and not any(
                row.get("fd_projection") or row.get("dk_projection") for row in rows
            ):
                rows = apply_salary_fppg_placeholder(rows, site or _site_from_rows(rows))
        except (FileNotFoundError, ValueError):
            if mode == "diy" or not allow_fppg_fallback:
                raise
            rows = apply_salary_fppg_placeholder(rows, site or _site_from_rows(rows))

    if _ngs_eval_enabled(cfg):
        rows = _apply_ngs_passing_overlay(rows, season, cfg)

    if _rookie_prior_enabled(cfg):
        rows = _apply_rookie_prior_overlay(rows, cfg)

    if _simulation_enabled(cfg):
        rows = _add_simulation_to_rows(rows, cfg)

    if _ownership_enabled(cfg):
        rows = _add_ownership_to_rows(rows, cfg, site or _site_from_rows(rows))

    if _buzz_enabled(cfg):
        rows = _apply_optional_overlay(rows, apply_buzz_signal, "buzz signal", cfg)

    if _espn_enabled(cfg):
        rows = _apply_optional_overlay(rows, apply_espn_injury_overlay, "ESPN injury", cfg)

    write_canonical_csv(rows, output_path)
    return output_path


def _apply_optional_overlay(
    rows: list[dict[str, Any]],
    overlay_fn: Any,
    label: str,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Apply a network-backed overlay; on any failure warn and return rows unchanged."""
    try:
        return overlay_fn(rows, config=config)
    except Exception as exc:
        print(f"WARNING: {label} overlay failed; continuing without it: {exc}", file=sys.stderr)
        return rows


def _espn_enabled(config: Mapping[str, Any]) -> bool:
    espn_cfg = config.get("espn_adjunct", {})
    if isinstance(espn_cfg, Mapping):
        return bool(espn_cfg.get("enabled"))
    return bool(config.get("espn_adjunct_enabled"))


def _ngs_eval_enabled(config: Mapping[str, Any]) -> bool:
    ngs_cfg = config.get("ngs_eval", {})
    if isinstance(ngs_cfg, Mapping):
        return bool(ngs_cfg.get("enabled"))
    return bool(config.get("ngs_eval_enabled"))


def _rookie_prior_enabled(config: Mapping[str, Any]) -> bool:
    rookie_cfg = config.get("rookie_prior", {})
    if isinstance(rookie_cfg, Mapping):
        return bool(rookie_cfg.get("enabled"))
    return bool(config.get("rookie_prior_enabled"))


def _apply_ngs_passing_overlay(
    rows: list[dict[str, Any]],
    season: int,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Store NGS passing columns on the rows. The live coefficient stays zero."""

    try:
        from ceminidfs.data.ngs_eval import apply_ngs_passing_residual, load_ngs_passing_sample

        ngs_df = load_ngs_passing_sample(season=season)
        return apply_ngs_passing_residual(rows, ngs_df, config=config)
    except Exception as exc:
        print(f"WARNING: NGS passing overlay failed; continuing without it: {exc}", file=sys.stderr)
        return rows


def _apply_rookie_prior_overlay(
    rows: list[dict[str, Any]],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Add the rookie prior from a local college CSV. The default prior is zero."""

    try:
        from ceminidfs.models.rookie_prior import (
            RookiePriorSettings,
            apply_rookie_prior,
            load_college_features_csv,
        )

        rookie_cfg = config.get("rookie_prior", {})
        rookie_cfg = rookie_cfg if isinstance(rookie_cfg, Mapping) else {}
        csv_path = rookie_cfg.get("csv_path")
        features = load_college_features_csv(csv_path) if csv_path else {}
        settings = RookiePriorSettings.from_config(config)
        return apply_rookie_prior(rows, features, settings)
    except Exception as exc:
        print(f"WARNING: rookie prior overlay failed; continuing without it: {exc}", file=sys.stderr)
        return rows


def _buzz_enabled(config: Mapping[str, Any]) -> bool:
    buzz_cfg = config.get("buzz_signal", {})
    if isinstance(buzz_cfg, Mapping):
        return bool(buzz_cfg.get("enabled"))
    return bool(config.get("buzz_signal_enabled"))


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
                "coherence_risk_flag": row.get("coherence_risk_flag", False),
                "pass_protection_stress": row.get("pass_protection_stress", 1.0),
                "workload_index": row.get("workload_index", 0.0),
                "workload_risk_flag": row.get("workload_risk_flag", False),
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
        config=config,
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
    _write_projection_partitions(stats_df, work_dir)
    return path


def projection_partition_dir(work_dir: str | Path, season: int, week: int) -> Path:
    """Return the season/week partition directory for our own projection rows."""

    return (
        Path(work_dir)
        / "player_projection_base"
        / f"season={int(season)}"
        / f"week={int(week)}"
    )


def _write_projection_partitions(stats_df: pd.DataFrame, work_dir: Path) -> list[Path]:
    """Write one parquet file per season/week partition. Empty frames write nothing."""

    if stats_df.empty or "season" not in stats_df.columns or "week" not in stats_df.columns:
        return []

    seasons = pd.to_numeric(stats_df["season"], errors="coerce")
    weeks = pd.to_numeric(stats_df["week"], errors="coerce")
    frame = stats_df.loc[seasons.notna() & weeks.notna()].copy()
    if frame.empty:
        return []

    frame["season"] = pd.to_numeric(frame["season"], errors="coerce").astype(int)
    frame["week"] = pd.to_numeric(frame["week"], errors="coerce").astype(int)

    written: list[Path] = []
    for (season, week), partition in frame.groupby(["season", "week"], dropna=False):
        partition_dir = projection_partition_dir(work_dir, int(season), int(week))
        partition_dir.mkdir(parents=True, exist_ok=True)
        partition_path = partition_dir / "player_projection_base.parquet"
        partition.to_parquet(partition_path, index=False)
        written.append(partition_path)
    return written


def load_projection_partitions(work_dir: str | Path) -> pd.DataFrame:
    """Read all season/week projection partitions. Return an empty frame if absent."""

    root = Path(work_dir) / "player_projection_base"
    if not root.is_dir():
        return pd.DataFrame()

    files = sorted(root.glob("season=*/week=*/player_projection_base.parquet"))
    if not files:
        return pd.DataFrame()

    frames = [pd.read_parquet(path) for path in files]
    return pd.concat(frames, ignore_index=True, sort=False)
