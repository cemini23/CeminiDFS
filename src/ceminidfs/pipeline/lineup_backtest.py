"""Lineup-level walk-forward backtest (project → optimize → score)."""

from __future__ import annotations

import csv
import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ceminidfs.config import load_config
from ceminidfs.data.historical_slate import FD_HEADERS, build_historical_slate_frame
from ceminidfs.pipeline.backtest import (
    _historical_pbp,
    actual_week_fantasy_points,
    load_season_pbp,
    resolve_vegas_for_week,
    resolve_weather_for_week,
    roster_from_historical_pbp,
)
from ceminidfs.pipeline.engine import build_diy_projections_from_frames


@dataclass
class WeekLineupResult:
    season: int
    week: int
    n_slate_players: int
    projected_score: float
    actual_score: float
    status: str


@dataclass
class LineupBacktestSummary:
    season: int
    start_week: int
    end_week: int
    weeks: list[WeekLineupResult] = field(default_factory=list)
    mean_projected_score: float = 0.0
    mean_actual_score: float = 0.0
    n_weeks_scored: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["weeks"] = [asdict(week) for week in self.weeks]
        return payload


def backtest_lineup_week(
    season: int,
    week: int,
    pbp: pd.DataFrame,
    config: Mapping[str, Any] | None = None,
    *,
    workdir: Path | None = None,
) -> WeekLineupResult:
    """Build a synthetic slate, optimize one lineup, and score vs realized points."""

    cfg = dict(config or load_config())
    empty = WeekLineupResult(season, week, 0, 0.0, 0.0, "empty_slate")

    slate = build_historical_slate_frame(season, week, pbp=pbp, config=cfg)
    if slate.empty:
        return empty

    vegas = resolve_vegas_for_week(season, week)
    if vegas.empty:
        return WeekLineupResult(season, week, len(slate), 0.0, 0.0, "missing_vegas")

    historical = _historical_pbp(pbp, season, week)
    roster = roster_from_historical_pbp(historical, vegas, season, week)
    if roster.empty:
        return WeekLineupResult(season, week, len(slate), 0.0, 0.0, "missing_roster")

    try:
        projections = build_diy_projections_from_frames(
            season,
            week,
            pbp,
            vegas,
            resolve_weather_for_week(season, week, config=cfg),
            roster,
            config=cfg,
        )
    except (ValueError, FileNotFoundError):
        return WeekLineupResult(season, week, len(slate), 0.0, 0.0, "projection_failed")

    actuals = actual_week_fantasy_points(pbp, season, week)
    if projections.empty or actuals.empty:
        return WeekLineupResult(season, week, len(slate), 0.0, 0.0, "missing_actuals")

    optimizer_csv = _write_optimizer_csv(slate, projections, workdir, season, week)
    try:
        from ceminidfs.export.optimize import generate_lineups

        lineups = generate_lineups(optimizer_csv, site="fanduel", count=1, max_exposure=1.0)
    except RuntimeError:
        return WeekLineupResult(season, week, len(slate), 0.0, 0.0, "optimizer_unavailable")

    if not lineups:
        return WeekLineupResult(season, week, len(slate), 0.0, 0.0, "no_lineup")

    name_to_projection = _name_map(projections, "fd_projection")
    name_to_actual = _name_map(actuals, "fd_actual")
    projected_score = _score_lineup(lineups[0], name_to_projection)
    actual_score = _score_lineup(lineups[0], name_to_actual)
    return WeekLineupResult(
        season,
        week,
        len(slate),
        projected_score,
        actual_score,
        "ok",
    )


def run_lineup_backtest(
    season: int,
    start_week: int,
    end_week: int,
    config: Mapping[str, Any] | None = None,
) -> LineupBacktestSummary:
    """Run lineup-level backtest across a week range."""

    if start_week > end_week:
        raise ValueError("start_week must be <= end_week")

    cfg = dict(config or load_config())
    pbp = load_season_pbp(season)
    summary = LineupBacktestSummary(season=season, start_week=start_week, end_week=end_week)

    projected: list[float] = []
    actual: list[float] = []
    with tempfile.TemporaryDirectory(prefix="ceminidfs_lineup_backtest_") as tmp:
        workdir = Path(tmp)
        for week in range(start_week, end_week + 1):
            result = backtest_lineup_week(season, week, pbp, config=cfg, workdir=workdir)
            summary.weeks.append(result)
            if result.status == "ok":
                projected.append(result.projected_score)
                actual.append(result.actual_score)

    summary.n_weeks_scored = len(projected)
    if projected:
        summary.mean_projected_score = float(pd.Series(projected).mean())
        summary.mean_actual_score = float(pd.Series(actual).mean())
    return summary


def write_lineup_backtest_report(summary: LineupBacktestSummary, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


def format_lineup_backtest_summary(summary: LineupBacktestSummary) -> str:
    lines = [
        f"CeminiDFS lineup backtest — season {summary.season} weeks {summary.start_week}-{summary.end_week}",
        f"Weeks scored: {summary.n_weeks_scored}",
        f"Mean projected lineup score: {summary.mean_projected_score:.2f}",
        f"Mean actual lineup score: {summary.mean_actual_score:.2f}",
        "",
        "Per week:",
    ]
    for week in summary.weeks:
        lines.append(
            f"  w{week.week:02d}: status={week.status} proj={week.projected_score:.2f} "
            f"actual={week.actual_score:.2f} slate={week.n_slate_players}"
        )
    return "\n".join(lines)


def _write_optimizer_csv(
    slate: pd.DataFrame,
    projections: pd.DataFrame,
    workdir: Path | None,
    season: int,
    week: int,
) -> Path:
    merged = slate.merge(
        projections[["player_id", "fd_projection"]],
        left_on="Id",
        right_on="player_id",
        how="left",
    )
    merged["FPPG"] = (
        pd.to_numeric(merged["fd_projection"], errors="coerce")
        .fillna(pd.to_numeric(merged["FPPG"], errors="coerce"))
        .fillna(0.0)
        .round(2)
    )

    base = workdir or Path(tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"lineup_backtest_{season}_w{week}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FD_HEADERS))
        writer.writeheader()
        for _, row in merged.iterrows():
            writer.writerow({key: row[key] for key in FD_HEADERS})
    return path


def _name_map(frame: pd.DataFrame, value_col: str) -> dict[str, float]:
    mapping: dict[str, float] = {}
    for _, row in frame.iterrows():
        name = _normalize_name(row.get("player_name", ""))
        value = float(pd.to_numeric(row.get(value_col, 0.0), errors="coerce") or 0.0)
        player_id = str(row.get("player_id", "") or "").strip().lower()
        if name:
            mapping[name] = value
        if player_id:
            mapping[player_id] = value
    return mapping


def _normalize_name(name: Any) -> str:
    return str(name or "").strip().lower()


def _score_lineup(lineup: Any, name_to_points: Mapping[str, float]) -> float:
    total = 0.0
    for player in lineup.players:
        key = _normalize_name(getattr(player, "full_name", ""))
        player_id = str(getattr(player, "id", "") or "").strip().lower()
        if key in name_to_points:
            total += float(name_to_points[key])
        elif player_id in name_to_points:
            total += float(name_to_points[player_id])
    return total
