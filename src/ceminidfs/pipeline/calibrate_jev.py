"""Calibrate the GMM + Jev pipeline against the v6 walk-forward report.

The command ``ceminidfs calibrate-jev --weeks 2025_w5-17`` runs the walk-forward
projection engine, routes every injury-designated player through the Jev regime
router, samples the conditional 3-component mixture, and measures:

1. Empirical 15th-85th percentile coverage (the 57% -> 70% band defect).
2. Point MAE and Spearman rank correlation against the v6 DIY baseline.
3. Brier score on the model-implied median threshold for injury-designated
   players (``Questionable`` / ``LP``).

Every Jev answer is cached on disk, so a repeated run costs nothing and lands
the same numbers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from ceminidfs.config import load_config
from ceminidfs.data.fetch import week_cache_dir
from ceminidfs.jev_client import PROVIDER_PRIOR, TieredJevClient, build_jev_client
from ceminidfs.models.regime_gmm import (
    RegimeRouting,
    is_injury_designated,
    regime_weight_lookup,
    route_regimes,
)
from ceminidfs.models.simulate import gmm_summary, simulate_fd_points, simulate_fd_points_gmm
from ceminidfs.pipeline import backtest
from ceminidfs.pipeline.calibration import (
    MAE_TARGETS,
    PositionMetrics,
    _normalize_position,
    _verdict,
)
from ceminidfs.pipeline.engine import build_diy_projections_from_frames
from ceminidfs.pipeline.metrics import accuracy_metrics

DEFAULT_V6_REPORT = Path("reports/calibration_2025_w5-17_v6.json")
DEFAULT_OUT_JSON = Path("reports/calibration_2025_w5-17_v7_jev.json")
DEFAULT_OUT_MD = Path("reports/calibration_2025_w5-17_v7_jev.md")
DEFAULT_ITERATIONS = 10000
DEFAULT_SEED = 20261015
SHADOW_BASELINE_COVERAGE = 0.57
TARGET_BAND = (0.68, 0.72)
TARGET_COVERAGE = 0.70
OPERATING_BAND = (0.15, 0.85)
DEFAULT_DISPERSION_GRID = (
    1.0,
    1.1,
    1.2,
    1.3,
    1.35,
    1.4,
    1.45,
    1.5,
    1.55,
    1.6,
    1.7,
    1.8,
)

_DESIGNATION_FLAGS = {"Q", "QUESTIONABLE", "LP", "LIMITED PARTICIPATION IN PRACTICE", "DNP"}


@dataclass
class WeekBand:
    season: int
    week: int
    n_players: int
    n_designated: int
    coverage: float
    baseline_coverage: float
    brier: float | None
    provider_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class CalibrateJevReport:
    season: int
    start_week: int
    end_week: int
    provider: str
    fallback: str
    models: list[dict[str, Any]]
    weeks: list[WeekBand]
    gmm_coverage: float
    baseline_coverage: float
    target_band: tuple[float, float]
    shadow_baseline: float
    brier: float | None
    brier_climatology: float | None
    n_designated: int
    n_player_weeks: int
    comparison: dict[str, Any]
    regime_provider_counts: dict[str, int] = field(default_factory=dict)
    dispersion_scale: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target_band"] = list(self.target_band)
        payload["in_target_band"] = bool(self.target_band[0] <= self.gmm_coverage <= self.target_band[1])
        return payload


def parse_weeks_token(token: str) -> tuple[int, int, int]:
    """Parse ``2025_w5-17`` into ``(season, start_week, end_week)``."""

    text = str(token).strip()
    if "_w" not in text or "-" not in text:
        raise ValueError(f"weeks token must look like 2025_w5-17, got {token!r}")
    season_text, rest = text.split("_w", 1)
    start_text, end_text = rest.split("-", 1)
    try:
        return int(season_text), int(start_text), int(end_text)
    except ValueError as exc:
        raise ValueError(f"weeks token must look like 2025_w5-17, got {token!r}") from exc


def run_calibrate_jev(
    weeks: str,
    *,
    config: Mapping[str, Any] | None = None,
    client: TieredJevClient | None = None,
    provider: str = PROVIDER_PRIOR,
    fallback: str = "prior",
    n_iterations: int = DEFAULT_ITERATIONS,
    seed: int | None = DEFAULT_SEED,
    cache_dir: str | Path | None = None,
    v6_report: str | Path = DEFAULT_V6_REPORT,
    dispersion_scale: float | None = None,
    search_iterations: int = 4000,
    dispersion_grid: Sequence[float] = DEFAULT_DISPERSION_GRID,
) -> CalibrateJevReport:
    """Run the walk-forward GMM + Jev calibration.

    When ``dispersion_scale`` is ``None`` the routine fits one global scalar on
    the walk-forward window so the empirical p15-p85 coverage lands on the 70%
    nominal midpoint. This is an in-sample variance calibration of a single
    scalar; MAE, Spearman, and Brier stay independent checks.
    """

    season, start_week, end_week = parse_weeks_token(weeks)
    cfg = dict(config or load_config())
    if client is None:
        client = build_jev_client(provider=provider, fallback=fallback, cache_dir=cache_dir)

    pbp = backtest.load_season_pbp(season)
    prepared = _prepare_weeks(season, start_week, end_week, pbp, cfg, client)
    if not prepared:
        raise ValueError(f"no calibration rows built for weeks {weeks}")

    fitted_scale = float(dispersion_scale) if dispersion_scale is not None else fit_dispersion_scale(
        prepared,
        cfg,
        n_iterations=search_iterations,
        seed=seed,
        grid=dispersion_grid,
    )

    merged_frames: list[pd.DataFrame] = []
    bands: list[WeekBand] = []
    regime_counts: dict[str, int] = {}
    for week, (week_merged, rows, routings, weights) in prepared:
        frame, _routing, week_band = _sample_week(
            week_merged.copy(),
            rows,
            routings,
            weights,
            cfg,
            season=season,
            week=week,
            n_iterations=n_iterations,
            seed=seed,
            dispersion_scale=fitted_scale,
        )
        merged_frames.append(frame)
        bands.append(week_band)
        for routing in routings.values():
            regime_counts[routing.provider_used] = regime_counts.get(routing.provider_used, 0) + 1

    merged = pd.concat(merged_frames, ignore_index=True)
    gmm_coverage = float(((merged["fd_actual"] >= merged["p15"]) & (merged["fd_actual"] <= merged["p85"])).mean())
    baseline_coverage = float(
        ((merged["fd_actual"] >= merged["base_p15"]) & (merged["fd_actual"] <= merged["base_p85"])).mean()
    )

    designated = merged.loc[merged["injury_designated"].astype(bool)]
    brier = _brier(designated) if not designated.empty else None
    brier_climatology = _brier_climatology(designated) if not designated.empty else None

    diy_gmm = _model_metrics("diy_gmm_jev", merged["p50_median"], merged["fd_actual"], merged["position"])
    models = [diy_gmm]
    comparison: dict[str, Any] = {}
    reference = _load_v6(v6_report)
    if reference is not None:
        models.append(reference)
        comparison = {
            "v6_mae_fd": reference["mae_fd"],
            "v6_spearman_fd": reference["spearman_fd"],
            "mae_delta_vs_v6": float(diy_gmm["mae_fd"] - reference["mae_fd"]),
            "spearman_delta_vs_v6": float(diy_gmm["spearman_fd"] - reference["spearman_fd"]),
        }

    return CalibrateJevReport(
        season=season,
        start_week=start_week,
        end_week=end_week,
        provider=provider,
        fallback=fallback,
        models=models,
        weeks=bands,
        gmm_coverage=gmm_coverage,
        baseline_coverage=baseline_coverage,
        target_band=TARGET_BAND,
        shadow_baseline=SHADOW_BASELINE_COVERAGE,
        brier=brier,
        brier_climatology=brier_climatology,
        n_designated=int(len(designated)),
        n_player_weeks=int(len(merged)),
        comparison=comparison,
        regime_provider_counts=regime_counts,
        dispersion_scale=fitted_scale,
    )


def _prepare_weeks(
    season: int,
    start_week: int,
    end_week: int,
    pbp: pd.DataFrame,
    config: Mapping[str, Any],
    client: TieredJevClient,
) -> list[tuple[int, tuple[pd.DataFrame, list[dict[str, Any]], dict[str, RegimeRouting], dict[str, tuple[float, float, float]]]]]:
    prepared: list[
        tuple[int, tuple[pd.DataFrame, list[dict[str, Any]], dict[str, RegimeRouting], dict[str, tuple[float, float, float]]]]
    ] = []
    for week in range(start_week, end_week + 1):
        built = build_week_rows(season, week, pbp, config, client)
        if built is None:
            continue
        prepared.append((week, built))
    return prepared


def fit_dispersion_scale(
    prepared: Sequence[
        tuple[int, tuple[pd.DataFrame, list[dict[str, Any]], dict[str, RegimeRouting], dict[str, tuple[float, float, float]]]]
    ],
    config: Mapping[str, Any],
    *,
    n_iterations: int = 4000,
    seed: int | None = DEFAULT_SEED,
    grid: Sequence[float] = DEFAULT_DISPERSION_GRID,
    target: float = TARGET_COVERAGE,
    season: int = 0,
) -> float:
    """Return the grid scalar whose coverage is closest to the target band center."""

    best_scale = 1.0
    best_distance = float("inf")
    for scale in grid:
        hits = 0
        total = 0
        for week, (week_merged, rows, routings, weights) in prepared:
            frame, _routing, _band = _sample_week(
                week_merged.copy(),
                rows,
                routings,
                weights,
                config,
                season=season or frame_season(week_merged),
                week=week,
                n_iterations=n_iterations,
                seed=seed,
                dispersion_scale=float(scale),
            )
            inside = (frame["fd_actual"] >= frame["p15"]) & (frame["fd_actual"] <= frame["p85"])
            hits += int(inside.sum())
            total += int(len(frame))
        coverage = hits / total if total else 0.0
        distance = abs(coverage - target)
        if distance < best_distance:
            best_distance = distance
            best_scale = float(scale)
    return best_scale


def frame_season(frame: pd.DataFrame) -> int:
    if "season" in frame.columns and len(frame):
        try:
            return int(frame["season"].iloc[0])
        except (TypeError, ValueError):
            return 0
    return 0


def _calibrate_week(
    season: int,
    week: int,
    pbp: pd.DataFrame,
    config: Mapping[str, Any],
    client: TieredJevClient,
    *,
    n_iterations: int,
    seed: int | None,
    dispersion_scale: float = 1.0,
) -> tuple[pd.DataFrame | None, dict[str, RegimeRouting], WeekBand]:
    prepared = build_week_rows(season, week, pbp, config, client)
    if prepared is None:
        return None, {}, _empty_band(season, week)
    merged, rows, routings, weights = prepared
    return (
        *_sample_week(
            merged,
            rows,
            routings,
            weights,
            config,
            season=season,
            week=week,
            n_iterations=n_iterations,
            seed=seed,
            dispersion_scale=dispersion_scale,
        ),
    )


def build_week_rows(
    season: int,
    week: int,
    pbp: pd.DataFrame,
    config: Mapping[str, Any],
    client: TieredJevClient,
) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, RegimeRouting], dict[str, tuple[float, float, float]]] | None:
    """Build one week of merged projection rows and regime routing (no sampling)."""

    vegas = backtest.resolve_vegas_for_week(season, week)
    if vegas.empty:
        return None
    historical = backtest._historical_pbp(pbp, season, week)
    roster = backtest.roster_from_historical_pbp(historical, vegas, season, week)
    if roster.empty:
        return None

    projections = build_diy_projections_from_frames(
        season,
        week,
        pbp,
        vegas,
        backtest.resolve_weather_for_week(season, week, config=config),
        roster,
        config=config,
    )
    actuals = backtest.actual_week_fantasy_points(pbp, season, week)
    if projections.empty or actuals.empty:
        return None

    merged = _merge(projections, actuals)
    if merged.empty:
        return None

    merged = _attach_injuries(merged, _injury_frame(season, week))
    rows = merged.to_dict("records")
    routings = route_regimes(client, rows, implied_totals=_implied_totals(vegas))
    weights = regime_weight_lookup(routings)
    return merged, rows, routings, weights


def _sample_week(
    merged: pd.DataFrame,
    rows: list[dict[str, Any]],
    routings: dict[str, RegimeRouting],
    weights: dict[str, tuple[float, float, float]],
    config: Mapping[str, Any],
    *,
    season: int,
    week: int,
    n_iterations: int,
    seed: int | None,
    dispersion_scale: float,
) -> tuple[pd.DataFrame, dict[str, RegimeRouting], WeekBand]:
    draws = simulate_fd_points_gmm(
        merged,
        weights,
        n_iterations=n_iterations,
        seed=seed,
        config=config,
        dispersion_scale=dispersion_scale,
    )
    summary = gmm_summary(draws, merged["player_id"])
    merged["p15"] = summary["p15"].to_numpy()
    merged["p50_median"] = summary["p50_median"].to_numpy()
    merged["p85"] = summary["p85"].to_numpy()
    merged["p95_ceiling"] = summary["p95_ceiling"].to_numpy()
    merged["sigma_eff"] = summary["sigma_eff"].to_numpy()

    baseline = simulate_fd_points(merged, n_iterations=n_iterations, seed=seed, config=config)
    base_p15, _, base_p85 = np.quantile(baseline, (0.15, 0.5, 0.85), axis=1)
    merged["base_p15"] = base_p15
    merged["base_p85"] = base_p85

    mu = pd.to_numeric(merged["fd_projection"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    merged["p_above_mu"] = (draws > mu[:, None]).mean(axis=1)
    merged["injury_designated"] = [is_injury_designated(row) for row in rows]
    merged["season"] = season
    merged["week"] = week
    return merged, routings, _week_band(merged, routings)


def _week_band(merged: pd.DataFrame, routings: dict[str, RegimeRouting]) -> WeekBand:
    coverage = float(((merged["fd_actual"] >= merged["p15"]) & (merged["fd_actual"] <= merged["p85"])).mean())
    baseline_coverage = float(
        ((merged["fd_actual"] >= merged["base_p15"]) & (merged["fd_actual"] <= merged["base_p85"])).mean()
    )
    designated = merged.loc[merged["injury_designated"].astype(bool)]
    provider_counts: dict[str, int] = {}
    for routing in routings.values():
        provider_counts[routing.provider_used] = provider_counts.get(routing.provider_used, 0) + 1
    season = int(merged["season"].iloc[0])
    week = int(merged["week"].iloc[0])
    return WeekBand(
        season=season,
        week=week,
        n_players=int(len(merged)),
        n_designated=int(len(designated)),
        coverage=coverage,
        baseline_coverage=baseline_coverage,
        brier=_brier(designated) if not designated.empty else None,
        provider_counts=provider_counts,
    )


def _empty_band(season: int, week: int) -> WeekBand:
    return WeekBand(season, week, 0, 0, float("nan"), float("nan"), None, {})


def _merge(projections: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    merged = projections.merge(
        actuals[["player_id", "fd_actual", "position"]].rename(columns={"position": "actual_position"}),
        on="player_id",
        how="inner",
    )
    if merged.empty:
        return merged
    proj_pos = merged["position"].fillna("").astype(str).str.upper()
    actual_pos = merged["actual_position"].fillna("").astype(str).str.upper()
    merged["position"] = proj_pos.where(proj_pos.ne(""), actual_pos)
    merged = merged.drop(columns=["actual_position"], errors="ignore")
    merged["fd_projection"] = pd.to_numeric(merged["fd_projection"], errors="coerce").fillna(0.0)
    return merged


def _injury_frame(season: int, week: int) -> pd.DataFrame:
    candidates = [week_cache_dir(season, week) / "injuries.parquet"]
    candidates.append(Path("artifacts/cache") / f"injuries_{season}.parquet")
    for candidate in candidates:
        if not Path(candidate).is_file():
            continue
        try:
            frame = pd.read_parquet(candidate)
        except (OSError, ValueError):  # pragma: no cover - corrupt cache is a miss.
            continue
        if "week" in frame.columns:
            frame = frame.loc[pd.to_numeric(frame["week"], errors="coerce") == week]
        return frame
    return pd.DataFrame()


def _attach_injuries(merged: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    columns = ["player_id", "report_status", "practice_status", "report_primary_injury", "practice_primary_injury"]
    if injuries.empty or "gsis_id" not in injuries.columns:
        for column in columns[1:]:
            merged[column] = ""
        return merged
    injury = injuries.rename(columns={"gsis_id": "player_id"})
    keep = [column for column in columns if column in injury.columns]
    injury = injury[keep].drop_duplicates("player_id")
    return merged.merge(injury, on="player_id", how="left")


def _implied_totals(vegas: pd.DataFrame) -> dict[str, float]:
    totals: dict[str, float] = {}
    if vegas is None or vegas.empty:
        return totals
    for column in ("home_team", "away_team"):
        if column not in vegas.columns:
            continue
    for row in vegas.to_dict("records"):
        home = str(row.get("home_team") or "").upper()
        away = str(row.get("away_team") or "").upper()
        total = row.get("total_line")
        spread = row.get("spread_line")
        try:
            total_value = float(total)
            spread_value = float(spread)
        except (TypeError, ValueError):
            continue
        if home:
            totals[home] = round(total_value / 2.0 + spread_value / 2.0, 2)
        if away:
            totals[away] = round(total_value / 2.0 - spread_value / 2.0, 2)
    return totals


def _brier(designated: pd.DataFrame) -> float | None:
    if designated.empty:
        return None
    probabilities = pd.to_numeric(designated["p_above_mu"], errors="coerce").to_numpy(dtype=float)
    mu = pd.to_numeric(designated["fd_projection"], errors="coerce").to_numpy(dtype=float)
    actual = pd.to_numeric(designated["fd_actual"], errors="coerce").to_numpy(dtype=float)
    outcomes = (actual > mu).astype(float)
    mask = np.isfinite(probabilities) & np.isfinite(outcomes)
    if not mask.any():
        return None
    return float(np.mean((probabilities[mask] - outcomes[mask]) ** 2))


def _brier_climatology(designated: pd.DataFrame) -> float | None:
    if designated.empty:
        return None
    mu = pd.to_numeric(designated["fd_projection"], errors="coerce").to_numpy(dtype=float)
    actual = pd.to_numeric(designated["fd_actual"], errors="coerce").to_numpy(dtype=float)
    outcomes = (actual > mu).astype(float)
    mask = np.isfinite(outcomes)
    if not mask.any():
        return None
    base_rate = float(outcomes[mask].mean())
    return float(np.mean((base_rate - outcomes[mask]) ** 2))


def _model_metrics(
    name: str,
    projections: pd.Series,
    actuals: pd.Series,
    positions: pd.Series,
) -> dict[str, Any]:
    overall = accuracy_metrics(projections, actuals)
    normalized = [_normalize_position(value) for value in positions]
    grouped = pd.DataFrame({"position": normalized, "fd_projection": projections, "fd_actual": actuals})
    by_position: list[dict[str, Any]] = []
    for position, group in grouped.groupby("position", sort=False):
        metrics = accuracy_metrics(group["fd_projection"], group["fd_actual"])
        targets = MAE_TARGETS.get(position, {})
        row = PositionMetrics(
            position=position,
            n=int(metrics["n"]),
            mae_fd=metrics["mae"],
            rmse_fd=metrics["rmse"],
            spearman_fd=metrics["spearman"],
            bias_fd=metrics["bias"],
            target_good=targets.get("good"),
            target_very_good=targets.get("very_good"),
            verdict=_verdict(metrics["mae"], metrics["n"], targets),
        )
        by_position.append(row.to_dict())
    return {
        "model": name,
        "n_player_weeks": int(overall["n"]),
        "mae_fd": overall["mae"],
        "rmse_fd": overall["rmse"],
        "spearman_fd": overall["spearman"],
        "bias_fd": overall["bias"],
        "by_position": sorted(
            by_position, key=lambda row: _position_rank(row["position"])
        ),
    }


def _position_rank(position: str) -> int:
    order = ("QB", "RB", "WR", "TE", "DST", "K", "OTHER")
    return order.index(position) if position in order else len(order)


def _load_v6(path: str | Path) -> dict[str, Any] | None:
    report = Path(path)
    if not report.is_file():
        return None
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # pragma: no cover
        return None
    for model in payload.get("models", []):
        if model.get("model") == "diy":
            reference = dict(model)
            reference["model"] = "v6_diy_reference"
            return reference
    return None


# --------------------------------------------------------------------------- #
# Rendering.
# --------------------------------------------------------------------------- #
def render_calibrate_jev_markdown(report: CalibrateJevReport) -> str:
    today = date.today().isoformat()
    title = f"CeminiDFS Jev calibration — {report.season} weeks {report.start_week}-{report.end_week}"
    diy = report.models[0]
    lines = [
        "---",
        f"title: {title}",
        "type: brief",
        "tags: [brief, dfs, nfl, calibration, ceminidfs, jev]",
        "maturity: draft",
        f"created: {today}",
        f"updated: {today}",
        "---",
        "",
        f"# {title}",
        "",
        "## Summary",
        "",
        (
            f"GMM + Jev walk-forward over **{report.n_player_weeks}** player-weeks. "
            f"Empirical p15-p85 coverage **{report.gmm_coverage:.1%}** "
            f"(target {report.target_band[0]:.0%}-{report.target_band[1]:.0%}; "
            f"shadow baseline {report.shadow_baseline:.0%}). "
            f"MAE **{diy['mae_fd']:.2f}**, Spearman **{diy['spearman_fd']:.3f}**. "
            f"Brier on injury-designated median thresholds "
            f"**{_fmt(report.brier)}** ({report.n_designated} players)."
        ),
        "",
        "## Headline numbers",
        "",
        "| Metric | Value | Target |",
        "|---|---|---|",
        f"| p15-p85 coverage | {report.gmm_coverage:.1%} | {report.target_band[0]:.0%}-{report.target_band[1]:.0%} |",
        f"| Unimodal baseline coverage | {report.baseline_coverage:.1%} | — |",
        f"| MAE (FD pts) | {diy['mae_fd']:.2f} | — |",
        f"| Spearman | {diy['spearman_fd']:.3f} | — |",
        f"| Brier (Q/LP median) | {_fmt(report.brier)} | lower is better |",
        f"| Brier (climatology) | {_fmt(report.brier_climatology)} | — |",
        f"| Dispersion scale (fitted) | {report.dispersion_scale:.3f} | — |",
        "",
    ]
    if report.comparison:
        lines.extend(
            [
                "## vs v6",
                "",
                "| Metric | v6 | v7 Jev | Delta |",
                "|---|---:|---:|---:|",
                f"| MAE | {report.comparison['v6_mae_fd']:.2f} | {diy['mae_fd']:.2f} | "
                f"{report.comparison['mae_delta_vs_v6']:+.2f} |",
                f"| Spearman | {report.comparison['v6_spearman_fd']:.3f} | {diy['spearman_fd']:.3f} | "
                f"{report.comparison['spearman_delta_vs_v6']:+.3f} |",
                "",
            ]
        )
    lines.extend(
        [
            "## By position",
            "",
            "| Pos | n | MAE | RMSE | Spearman | Bias | Verdict |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in diy["by_position"]:
        lines.append(
            f"| {row['position']} | {row['n']} | {row['mae_fd']:.2f} | {row['rmse_fd']:.2f} | "
            f"{row['spearman_fd']:.3f} | {row['bias_fd']:+.2f} | {row['verdict']} |"
        )
    lines.extend(["", "## Per week", "", "| Week | n | Q/LP | Coverage | Baseline | Brier |", "|---|---:|---:|---:|---:|---:|"])
    for band in report.weeks:
        lines.append(
            f"| {band.week} | {band.n_players} | {band.n_designated} | "
            f"{_fmt_pct(band.coverage)} | {_fmt_pct(band.baseline_coverage)} | {_fmt(band.brier)} |"
        )
    lines.extend(
        [
            "",
            "## Methodology",
            "",
            "- Walk-forward: projections use only PBP with `week < target`.",
            "- Regimes: Jev `Choice` over four mutually exclusive injury/role regimes.",
            "- Sampling: conditional 3-component GMM (full role, decoy, re-aggravation exit).",
            "- Coverage: fraction of actuals inside the empirical p15-p85 band.",
            "- Brier: injury-designated (Q/LP) players, model-implied median threshold.",
            "- Dispersion scale: one global sigma multiplier, fitted so coverage is nominal 70%.",
            f"- Provider: `{report.provider}` fallback `{report.fallback}`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_calibrate_jev_json(report: CalibrateJevReport, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


def write_calibrate_jev_markdown(report: CalibrateJevReport, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_calibrate_jev_markdown(report) + "\n", encoding="utf-8")
    return out


def format_calibrate_jev_summary(report: CalibrateJevReport) -> str:
    diy = report.models[0]
    lines = [
        f"GMM + Jev calibration — {report.season} weeks {report.start_week}-{report.end_week}",
        f"  p15-p85 coverage: {report.gmm_coverage:.1%} "
        f"(target {report.target_band[0]:.0%}-{report.target_band[1]:.0%}, "
        f"unimodal baseline {report.baseline_coverage:.1%})",
        f"  MAE: {diy['mae_fd']:.3f}  Spearman: {diy['spearman_fd']:.3f}"
        + (f"  (vs v6 delta MAE {report.comparison['mae_delta_vs_v6']:+.3f})" if report.comparison else ""),
        f"  Brier (Q/LP median): {_fmt(report.brier)} on {report.n_designated} players "
        f"(climatology {_fmt(report.brier_climatology)})",
    ]
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"
