"""Backtest comparison helpers for the K126 coherence-risk layer."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

import pandas as pd

from ceminidfs.config import load_config
from ceminidfs.pipeline.backtest import (
    actual_week_fantasy_points,
    load_season_pbp,
    resolve_vegas_for_week,
    resolve_weather_for_week,
    roster_from_historical_pbp,
)
from ceminidfs.pipeline.engine import build_diy_projections_from_frames
from ceminidfs.pipeline.metrics import accuracy_metrics


def run_coherence_comparison(
    season: int,
    start_week: int,
    end_week: int,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare baseline vs coherence-enabled projections across a week range."""

    if start_week > end_week:
        raise ValueError("start_week must be <= end_week")

    cfg = deepcopy(dict(config or load_config()))
    pbp = load_season_pbp(season)

    baseline_frames: list[pd.DataFrame] = []
    coherence_frames: list[pd.DataFrame] = []
    weeks: list[dict[str, Any]] = []

    for week in range(start_week, end_week + 1):
        baseline = _week_projection_actuals(season, week, pbp, _config_with_enabled(cfg, False))
        coherence = _week_projection_actuals(season, week, pbp, _config_with_enabled(cfg, True))
        baseline_frames.append(baseline)
        coherence_frames.append(coherence)
        baseline_metrics = _frame_metrics(baseline)
        coherence_metrics = _frame_metrics(coherence)
        weeks.append(
            {
                "week": week,
                "baseline": baseline_metrics,
                "coherence": coherence_metrics,
                "delta_mae": coherence_metrics["mae_fd"] - baseline_metrics["mae_fd"],
                "top50_delta": coherence_metrics["top50_mae"] - baseline_metrics["top50_mae"],
            }
        )

    baseline_all = pd.concat(baseline_frames, ignore_index=True) if baseline_frames else pd.DataFrame()
    coherence_all = pd.concat(coherence_frames, ignore_index=True) if coherence_frames else pd.DataFrame()
    baseline_summary = _frame_metrics(baseline_all)
    coherence_summary = _frame_metrics(coherence_all)
    return {
        "season": season,
        "start_week": start_week,
        "end_week": end_week,
        "baseline": baseline_summary,
        "coherence": coherence_summary,
        "delta_mae": coherence_summary["mae_fd"] - baseline_summary["mae_fd"],
        "top50_delta": coherence_summary["top50_mae"] - baseline_summary["top50_mae"],
        "weeks": weeks,
    }


def _week_projection_actuals(
    season: int,
    week: int,
    pbp: pd.DataFrame,
    config: Mapping[str, Any],
) -> pd.DataFrame:
    vegas = resolve_vegas_for_week(season, week)
    if vegas.empty:
        return pd.DataFrame()

    historical = _historical_pbp(pbp, season, week)
    roster = roster_from_historical_pbp(historical, vegas, season, week)
    if roster.empty:
        return pd.DataFrame()

    weather = resolve_weather_for_week(season, week, config=config)
    projections = build_diy_projections_from_frames(
        season,
        week,
        pbp,
        vegas,
        weather,
        roster,
        config=config,
    )
    actuals = actual_week_fantasy_points(pbp, season, week)
    if projections.empty or actuals.empty:
        return pd.DataFrame()

    return projections.merge(
        actuals[["player_id", "fd_actual"]],
        on="player_id",
        how="inner",
    )


def _frame_metrics(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return {"mae_fd": 0.0, "top50_mae": 0.0, "n_players": 0.0}

    overall = accuracy_metrics(frame["fd_projection"], frame["fd_actual"])
    top50 = frame.nlargest(50, "fd_actual")
    top50_metrics = accuracy_metrics(top50["fd_projection"], top50["fd_actual"])
    return {
        "mae_fd": overall["mae"],
        "top50_mae": top50_metrics["mae"],
        "n_players": float(len(frame)),
    }


def _config_with_enabled(config: Mapping[str, Any], enabled: bool) -> dict[str, Any]:
    output = deepcopy(dict(config))
    coherence = dict(output.get("coherence_risk") or {})
    coherence["enabled"] = enabled
    output["coherence_risk"] = coherence
    return output


def _historical_pbp(pbp: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    frame = pbp.copy()
    if "season" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["season"], errors="coerce").fillna(season) == season]
    if "week" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["week"], errors="coerce") < week]
    return frame
