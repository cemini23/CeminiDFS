"""Calibration report and wiki brief generation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ceminidfs.config import load_config
from ceminidfs.data.benchmark import parse_benchmark_csv
from ceminidfs.data.historical_slate import walk_forward_fppg
from ceminidfs.pipeline.backtest import (
    actual_week_fantasy_points,
    load_season_pbp,
    resolve_vegas_for_week,
    resolve_weather_for_week,
    roster_from_historical_pbp,
    _historical_pbp,
)
from ceminidfs.pipeline.engine import build_diy_projections_from_frames
from ceminidfs.pipeline.metrics import accuracy_metrics

POSITION_ORDER = ("QB", "RB", "WR", "TE", "DST", "K", "OTHER")

MAE_TARGETS: dict[str, dict[str, float]] = {
    "QB": {"good": 6.3, "very_good": 6.1},
    "RB": {"good": 5.3, "very_good": 5.0},
    "WR": {"good": 5.0, "very_good": 4.85},
    "TE": {"good": 3.9, "very_good": 3.75},
    "DST": {"good": 4.5, "very_good": 4.2},
}


@dataclass
class PositionMetrics:
    position: str
    n: int
    mae_fd: float
    rmse_fd: float
    spearman_fd: float
    bias_fd: float
    target_good: float | None = None
    target_very_good: float | None = None
    verdict: str = "n/a"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelCalibration:
    model: str
    n_player_weeks: int
    mae_fd: float
    rmse_fd: float
    spearman_fd: float
    bias_fd: float
    by_position: list[PositionMetrics] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["by_position"] = [row.to_dict() for row in self.by_position]
        return payload


@dataclass
class CalibrationReport:
    season: int
    start_week: int
    end_week: int
    models: list[ModelCalibration]
    benchmark_source: str | None = None
    benchmark_week: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "start_week": self.start_week,
            "end_week": self.end_week,
            "benchmark_source": self.benchmark_source,
            "benchmark_week": self.benchmark_week,
            "models": [model.to_dict() for model in self.models],
        }


def build_calibration_report(
    season: int,
    start_week: int,
    end_week: int,
    *,
    benchmark_csv: str | Path | None = None,
    benchmark_week: int | None = None,
    config: Mapping[str, Any] | None = None,
) -> CalibrationReport:
    """Build a walk-forward calibration report with optional paid benchmark."""

    if start_week > end_week:
        raise ValueError("start_week must be <= end_week")

    cfg = dict(config or load_config())
    pbp = load_season_pbp(season)

    diy_frames: list[pd.DataFrame] = []
    fppg_frames: list[pd.DataFrame] = []
    for week in range(start_week, end_week + 1):
        frame = diy_comparison_rows(season, week, pbp, config=cfg)
        if not frame.empty:
            diy_frames.append(frame)
        fppg_frame = rolling_fppg_comparison_rows(season, week, pbp)
        if not fppg_frame.empty:
            fppg_frames.append(fppg_frame)

    models: list[ModelCalibration] = []
    if diy_frames:
        models.append(_calibrate_model("diy", pd.concat(diy_frames, ignore_index=True)))
    if fppg_frames:
        models.append(_calibrate_model("rolling_fppg", pd.concat(fppg_frames, ignore_index=True)))

    benchmark_source: str | None = None
    benchmark_week_value = benchmark_week
    if benchmark_csv is not None:
        week = benchmark_week if benchmark_week is not None else end_week
        benchmark_week_value = week
        bench_rows = parse_benchmark_csv(benchmark_csv, season=season, week=week)
        benchmark_source = bench_rows[0].get("source", "generic") if bench_rows else "generic"
        bench_frame = benchmark_comparison_rows(season, week, pbp, bench_rows)
        if not bench_frame.empty:
            models.append(_calibrate_model("benchmark", bench_frame))

    return CalibrationReport(
        season=season,
        start_week=start_week,
        end_week=end_week,
        models=models,
        benchmark_source=benchmark_source,
        benchmark_week=benchmark_week_value if benchmark_csv is not None else None,
    )


def diy_comparison_rows(
    season: int,
    week: int,
    pbp: pd.DataFrame,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Return player-week DIY projection vs actual rows."""

    vegas = resolve_vegas_for_week(season, week)
    if vegas.empty:
        return pd.DataFrame()

    historical = _historical_pbp(pbp, season, week)
    roster = roster_from_historical_pbp(historical, vegas, season, week)
    if roster.empty:
        return pd.DataFrame()

    projections = build_diy_projections_from_frames(
        season,
        week,
        pbp,
        vegas,
        resolve_weather_for_week(season, week, config=config),
        roster,
        config=config,
    )
    actuals = actual_week_fantasy_points(pbp, season, week)
    if projections.empty or actuals.empty:
        return pd.DataFrame()

    merged = _merge_projection_actuals(projections, actuals)
    if merged.empty:
        return pd.DataFrame()

    merged["season"] = season
    merged["week"] = week
    merged["model"] = "diy"
    return merged[
        [
            "season",
            "week",
            "model",
            "player_id",
            "player_name",
            "team",
            "position",
            "fd_projection",
            "fd_actual",
        ]
    ]


def _merge_projection_actuals(projections: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Join projections to actuals and prefer non-empty projection positions."""

    merged = projections.merge(
        actuals[["player_id", "fd_actual", "position"]].rename(
            columns={"position": "actual_position"}
        ),
        on="player_id",
        how="inner",
    )
    if merged.empty:
        return merged

    proj_pos = merged["position"].fillna("").astype(str).str.upper()
    actual_pos = merged["actual_position"].fillna("").astype(str).str.upper()
    merged["position"] = proj_pos.where(proj_pos.ne(""), actual_pos)
    return merged.drop(columns=["actual_position"], errors="ignore")


def rolling_fppg_comparison_rows(season: int, week: int, pbp: pd.DataFrame) -> pd.DataFrame:
    """Return player-week rolling FPPG baseline vs actual rows (walk-forward naive baseline)."""

    vegas = resolve_vegas_for_week(season, week)
    if vegas.empty:
        return pd.DataFrame()

    historical = _historical_pbp(pbp, season, week)
    roster = roster_from_historical_pbp(historical, vegas, season, week)
    if roster.empty:
        return pd.DataFrame()

    fppg = walk_forward_fppg(pbp, season, week)
    actuals = actual_week_fantasy_points(pbp, season, week)
    if actuals.empty:
        return pd.DataFrame()

    merged = roster.merge(
        actuals[["player_id", "fd_actual", "position"]].rename(
            columns={"position": "actual_position"}
        ),
        on="player_id",
        how="inner",
    )
    if merged.empty:
        return pd.DataFrame()

    merged["fd_projection"] = merged["player_id"].map(fppg).fillna(0.0)
    merged = merged.loc[merged["fd_projection"] > 0]
    if merged.empty:
        return pd.DataFrame()

    roster_pos = merged["position"].fillna("").astype(str).str.upper()
    actual_pos = merged["actual_position"].fillna("").astype(str).str.upper()
    merged["position"] = roster_pos.where(roster_pos.ne(""), actual_pos)
    merged = merged.drop(columns=["actual_position"], errors="ignore")

    merged["season"] = season
    merged["week"] = week
    merged["model"] = "rolling_fppg"
    return merged[
        [
            "season",
            "week",
            "model",
            "player_id",
            "player_name",
            "team",
            "position",
            "fd_projection",
            "fd_actual",
        ]
    ]


def benchmark_comparison_rows(
    season: int,
    week: int,
    pbp: pd.DataFrame,
    benchmark_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    """Return player-week benchmark projection vs actual rows."""

    if not benchmark_rows:
        return pd.DataFrame()

    benchmark = pd.DataFrame(benchmark_rows)
    actuals = actual_week_fantasy_points(pbp, season, week)
    if actuals.empty:
        return pd.DataFrame()

    merged = benchmark.merge(
        actuals[["join_key", "player_id", "fd_actual"]],
        on="join_key",
        how="inner",
        suffixes=("", "_actual"),
    )
    if merged.empty:
        return pd.DataFrame()

    if "player_id_actual" in merged.columns:
        merged["player_id"] = merged["player_id"].fillna(merged["player_id_actual"])

    merged["season"] = season
    merged["week"] = week
    merged["model"] = "benchmark"
    merged["fd_projection"] = merged["projection"]
    merged["player_name"] = merged["player_name"].fillna("")
    return merged[
        [
            "season",
            "week",
            "model",
            "player_id",
            "player_name",
            "team",
            "position",
            "fd_projection",
            "fd_actual",
        ]
    ]


def render_calibration_brief(report: CalibrationReport) -> str:
    """Render a gambling-wiki-ready calibration brief in Markdown."""

    today = date.today().isoformat()
    title = f"CeminiDFS calibration — {report.season} weeks {report.start_week}-{report.end_week}"
    lines = [
        "---",
        f"title: {title}",
        "type: brief",
        "tags: [brief, dfs, nfl, calibration, ceminidfs]",
        "maturity: draft",
        f"created: {today}",
        f"updated: {today}",
        "related:",
        "  - concepts/dfs-backtesting-framework.md",
        "  - concepts/diy-nfl-dfs-model-architecture.md",
        "  - entities/tools/stokastic-dfs.md",
        "---",
        "",
        f"# {title}",
        "",
        "## Summary",
        "",
        _summary_paragraph(report),
        "",
        "## Overall accuracy",
        "",
        _overall_table(report),
        "",
        "## By position (DIY vs targets)",
        "",
        _position_table(report, model="diy"),
    ]

    if any(model.model == "benchmark" for model in report.models):
        lines.extend(
            [
                "",
                "## Paid benchmark snapshot",
                "",
                _benchmark_section(report),
            ]
        )

    lines.extend(
        [
            "",
            "## Methodology",
            "",
            "- Walk-forward: projections use only PBP with `week < target`.",
            "- Actuals: FanDuel half-PPR points aggregated from nflverse PBP.",
            "- Join: DIY on `player_id`; benchmark on name+team+position (`join_key`).",
            "- MAE targets from `@concepts/dfs-backtesting-framework.md` (Fantasy Football Analytics vendor review, tentative).",
            "",
            "## Calibration actions",
            "",
            *_calibration_actions(report),
            "",
        ]
    )
    return "\n".join(lines)


def write_calibration_brief(report: CalibrationReport, path: str | Path) -> Path:
    """Write markdown wiki brief to disk."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_calibration_brief(report) + "\n", encoding="utf-8")
    return out


def write_calibration_json(report: CalibrationReport, path: str | Path) -> Path:
    """Write structured calibration JSON alongside the brief."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


def _calibrate_model(model: str, frame: pd.DataFrame) -> ModelCalibration:
    overall = accuracy_metrics(frame["fd_projection"], frame["fd_actual"])
    by_position = _position_metrics(frame)
    return ModelCalibration(
        model=model,
        n_player_weeks=int(overall["n"]),
        mae_fd=overall["mae"],
        rmse_fd=overall["rmse"],
        spearman_fd=overall["spearman"],
        bias_fd=overall["bias"],
        by_position=by_position,
    )


def _position_metrics(frame: pd.DataFrame) -> list[PositionMetrics]:
    positions = [_normalize_position(value) for value in frame["position"]]
    grouped = frame.assign(position=positions).groupby("position", dropna=False)
    rows: list[PositionMetrics] = []
    for position, group in grouped:
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
        rows.append(row)
    return sorted(rows, key=lambda row: _position_sort_key(row.position))


def _verdict(mae: float, n: float, targets: Mapping[str, float]) -> str:
    if n < 5:
        return "insufficient data"
    if not targets:
        return "no target"
    if mae <= targets.get("very_good", float("inf")):
        return "very good"
    if mae <= targets.get("good", float("inf")):
        return "good"
    return "needs work"


def _normalize_position(value: Any) -> str:
    token = str(value or "").strip().upper()
    if not token:
        return "OTHER"
    for position in POSITION_ORDER:
        if token == position or token.startswith(position):
            return position
    return "OTHER"


def _position_sort_key(position: str) -> int:
    try:
        return POSITION_ORDER.index(position)
    except ValueError:
        return len(POSITION_ORDER)


def _summary_paragraph(report: CalibrationReport) -> str:
    diy = _model(report, "diy")
    if diy is None:
        return "No DIY comparison rows were available for this window."

    parts = [
        f"DIY walk-forward over **{diy.n_player_weeks}** player-weeks: "
        f"MAE **{diy.mae_fd:.2f}**, RMSE **{diy.rmse_fd:.2f}**, "
        f"Spearman **{diy.spearman_fd:.3f}**, bias **{diy.bias_fd:+.2f}** FD pts."
    ]
    bench = _model(report, "benchmark")
    if bench is not None and report.benchmark_week is not None:
        parts.append(
            f"Paid benchmark ({report.benchmark_source}, week {report.benchmark_week}): "
            f"MAE **{bench.mae_fd:.2f}**, Spearman **{bench.spearman_fd:.3f}** on {bench.n_player_weeks} matched players."
        )
    baseline = _model(report, "rolling_fppg")
    if baseline is not None:
        parts.append(
            f"Rolling FPPG baseline: MAE **{baseline.mae_fd:.2f}**, Spearman **{baseline.spearman_fd:.3f}**."
        )
    return " ".join(parts)


def _overall_table(report: CalibrationReport) -> str:
    header = "| Model | n | MAE | RMSE | Spearman | Bias |"
    sep = "|---|---:|---:|---:|---:|---:|"
    rows = [header, sep]
    for model in report.models:
        rows.append(
            f"| {model.model} | {model.n_player_weeks} | {model.mae_fd:.2f} | "
            f"{model.rmse_fd:.2f} | {model.spearman_fd:.3f} | {model.bias_fd:+.2f} |"
        )
    return "\n".join(rows)


def _position_table(report: CalibrationReport, *, model: str) -> str:
    selected = _model(report, model)
    if selected is None or not selected.by_position:
        return "_No position breakdown available._"

    header = "| Pos | n | MAE | Target (good) | Target (very good) | Bias | Verdict |"
    sep = "|---|---:|---:|---:|---:|---:|---|"
    rows = [header, sep]
    for row in selected.by_position:
        good = f"{row.target_good:.2f}" if row.target_good is not None else "—"
        very_good = f"{row.target_very_good:.2f}" if row.target_very_good is not None else "—"
        rows.append(
            f"| {row.position} | {row.n} | {row.mae_fd:.2f} | {good} | {very_good} | "
            f"{row.bias_fd:+.2f} | {row.verdict} |"
        )
    return "\n".join(rows)


def _benchmark_section(report: CalibrationReport) -> str:
    bench = _model(report, "benchmark")
    if bench is None:
        return "_Benchmark comparison unavailable._"
    return "\n".join(
        [
            f"- Source: `{report.benchmark_source}` (week {report.benchmark_week})",
            f"- Matched players: {bench.n_player_weeks}",
            f"- MAE: {bench.mae_fd:.2f} | RMSE: {bench.rmse_fd:.2f} | Spearman: {bench.spearman_fd:.3f}",
            "",
            _position_table(report, model="benchmark"),
        ]
    )


def _calibration_actions(report: CalibrationReport) -> list[str]:
    diy = _model(report, "diy")
    if diy is None:
        return [
            "- Re-run `ceminidfs fetch` and widen the week window once season PBP cache is populated."
        ]

    actions: list[str] = []
    for row in diy.by_position:
        if row.verdict == "needs work":
            actions.append(
                f"- **{row.position}**: MAE {row.mae_fd:.2f} exceeds good target "
                f"({row.target_good:.2f}) — review volume/usage priors for this role."
            )
        elif row.verdict == "insufficient data":
            actions.append(f"- **{row.position}**: only {row.n} samples — extend backtest window.")
        if abs(row.bias_fd) > 1.5 and row.n >= 5:
            direction = "high" if row.bias_fd > 0 else "low"
            actions.append(
                f"- **{row.position}**: bias {row.bias_fd:+.2f} suggests systematic {direction} projection — check efficiency regression."
            )

    bench = _model(report, "benchmark")
    if bench is not None and diy is not None and bench.mae_fd < diy.mae_fd:
        actions.append(
            "- Paid benchmark beat DIY on MAE for the snapshot week — prioritize rank correlation and tail accuracy before contest sims."
        )

    if not actions:
        actions.append("- No urgent calibration flags; continue walk-forward monitoring weekly.")
    return actions


def _model(report: CalibrationReport, name: str) -> ModelCalibration | None:
    for model in report.models:
        if model.model == name:
            return model
    return None
