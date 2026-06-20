"""Compare paid benchmark projections against actuals and optional DIY model."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ceminidfs.data.benchmark import parse_benchmark_csv
from ceminidfs.pipeline.backtest import (
    actual_week_fantasy_points,
    backtest_week,
    load_season_pbp,
)
from ceminidfs.pipeline.metrics import accuracy_metrics


@dataclass
class ModelAccuracy:
    model: str
    n_players: int
    mae_fd: float
    rmse_fd: float
    spearman_fd: float


@dataclass
class BenchmarkCompareResult:
    season: int
    week: int
    benchmark_source: str
    models: list[ModelAccuracy]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_benchmark_week(
    season: int,
    week: int,
    benchmark_csv: str | Path,
    *,
    site: str = "fanduel",
    source: str | None = None,
    include_diy: bool = True,
    config: Mapping[str, Any] | None = None,
) -> BenchmarkCompareResult:
    """Compare a paid export against realized FD points for one week."""

    rows = parse_benchmark_csv(
        benchmark_csv,
        site=site,
        source=source,
        season=season,
        week=week,
    )
    if not rows:
        raise ValueError(f"No benchmark rows parsed from {benchmark_csv}")

    benchmark = pd.DataFrame(rows)
    pbp = load_season_pbp(season)
    actuals = actual_week_fantasy_points(pbp, season, week)
    if actuals.empty:
        raise ValueError(f"No actual fantasy points found for {season} week {week}")

    merged = benchmark.merge(
        actuals[["join_key", "player_id", "fd_actual"]],
        on="join_key",
        how="inner",
    )
    if merged.empty:
        raise ValueError("Benchmark rows did not join to actual outcomes; check team/position headers")

    models: list[ModelAccuracy] = [
        _model_accuracy("benchmark", merged["projection"], merged["fd_actual"], len(merged))
    ]

    if include_diy:
        diy_result, diy_merged = backtest_week(season, week, pbp, config=config)
        if not diy_merged.empty:
            models.append(
                ModelAccuracy(
                    model="diy",
                    n_players=diy_result.n_players,
                    mae_fd=diy_result.mae_fd,
                    rmse_fd=diy_result.rmse_fd,
                    spearman_fd=diy_result.spearman_fd,
                )
            )

    return BenchmarkCompareResult(
        season=season,
        week=week,
        benchmark_source=str(rows[0].get("source", source or "generic")),
        models=models,
    )


def write_benchmark_compare_report(result: BenchmarkCompareResult, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


def format_benchmark_compare(result: BenchmarkCompareResult) -> str:
    lines = [
        f"Benchmark compare — season {result.season} week {result.week} ({result.benchmark_source})",
        "",
    ]
    for model in result.models:
        lines.append(
            f"  {model.model:10s} n={model.n_players:4d} "
            f"MAE={model.mae_fd:.2f} RMSE={model.rmse_fd:.2f} rho={model.spearman_fd:.3f}"
        )
    return "\n".join(lines)


def _model_accuracy(
    name: str,
    projections: pd.Series,
    actuals: pd.Series,
    n_players: int,
) -> ModelAccuracy:
    metrics = accuracy_metrics(projections, actuals)
    return ModelAccuracy(
        model=name,
        n_players=n_players,
        mae_fd=metrics["mae"],
        rmse_fd=metrics["rmse"],
        spearman_fd=metrics["spearman"],
    )
