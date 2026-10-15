"""Head-to-head: model per-stat medians vs closing prop lines vs actuals.

The closing line is the market's median estimate for the same stat. This module
joins the model's per-stat medians (``pipeline.distributions``) to a closing
props CSV, joins both to realized stat outcomes
(``pipeline.backtest.actual_week_fantasy_points``), and reports per ``stat_type``
a model-vs-market error comparison in FanDuel points.

Stat-level errors are converted with the repo's existing scoring
(``models.scoring.fd_points``), so a yard error in any stat is expressed on the
same scale the calibration report uses.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ceminidfs.models.scoring import fd_points
from ceminidfs.pipeline import backtest
from ceminidfs.pipeline.distributions import STAT_TYPES, build_week_distributions
from ceminidfs.pipeline.metrics import accuracy_metrics

MIN_COVERAGE_LEGS = 30
VERDICT_MODEL = "MODEL BEATS MARKET"
VERDICT_MARKET = "MARKET BEATS MODEL"
VERDICT_NO_COVERAGE = "NO COVERAGE"


@dataclass
class StatBenchmark:
    stat_type: str
    n_legs: int
    model_mae_fd: float
    market_mae_fd: float
    diff_fd: float
    better: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketBenchmarkResult:
    season: int
    week: int
    n_legs: int
    model_mae_fd: float
    market_mae_fd: float
    verdict: str
    by_stat: list[StatBenchmark] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["by_stat"] = [row.to_dict() for row in self.by_stat]
        return payload


def parse_closing_props(path: str | Path) -> pd.DataFrame:
    """Parse a closing prop lines CSV into ``player_key, stat_type, line`` rows.

    Other columns (``side``, ``platform``, ...) are ignored. A missing file, a
    file without a header, or a file with no usable leg fails loud.
    """

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Closing props CSV not found: {source}")

    with source.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"Closing props CSV is empty (no header): {source}")
        headers = {_normalize_header(name) for name in reader.fieldnames}
        for required in ("player_key", "stat_type", "line"):
            if required not in headers:
                raise ValueError(
                    f"Closing props CSV missing required column {required!r}: {source}"
                )

        rows: list[dict[str, Any]] = []
        for raw in reader:
            row = {_normalize_header(key): value for key, value in raw.items()}
            player_key = str(row.get("player_key") or "").strip()
            stat_type = str(row.get("stat_type") or "").strip().lower()
            line = _as_float(row.get("line"))
            if not player_key or stat_type not in STAT_TYPES or line is None:
                continue
            rows.append({"player_key": player_key, "stat_type": stat_type, "line": line})

    if not rows:
        raise ValueError(
            f"Closing props CSV has no usable legs (player_key/stat_type/line): {source}"
        )
    return pd.DataFrame(rows)


def run_market_benchmark(
    season: int,
    week: int,
    closing_props: str | Path,
    *,
    distributions: pd.DataFrame | None = None,
    actuals: pd.DataFrame | None = None,
    config: Mapping[str, Any] | None = None,
) -> MarketBenchmarkResult:
    """Compare model medians and closing lines against realized stat outcomes."""

    props = parse_closing_props(closing_props)

    model = (
        distributions
        if distributions is not None
        else build_week_distributions(season, week, config=config)
    )
    realized = (
        actuals
        if actuals is not None
        else backtest.actual_week_fantasy_points(backtest.load_season_pbp(season), season, week)
    )

    merged = _join_legs(props, model, realized)
    return _summarize(season, week, merged)


def write_market_benchmark_report(result: MarketBenchmarkResult, path: str | Path) -> Path:
    """Write the market benchmark result as JSON."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


def format_market_benchmark(result: MarketBenchmarkResult) -> str:
    """Render the per-stat table and the single VERDICT line."""

    lines = [
        f"CeminiDFS market benchmark — season {result.season} week {result.week}",
        f"Joined legs: {result.n_legs}",
        "",
        "  stat_type    n_legs  model_MAE  market_MAE   diff_fd  better",
    ]
    for row in result.by_stat:
        lines.append(
            f"  {row.stat_type:10s} {row.n_legs:6d} "
            f"{row.model_mae_fd:10.2f} {row.market_mae_fd:11.2f} "
            f"{row.diff_fd:+9.2f}  {row.better}"
        )
    if result.by_stat:
        pooled_better = "model" if result.model_mae_fd < result.market_mae_fd else "market"
        lines.append(
            f"  {'(pooled)':10s} {result.n_legs:6d} "
            f"{result.model_mae_fd:10.2f} {result.market_mae_fd:11.2f} "
            f"{result.model_mae_fd - result.market_mae_fd:+9.2f}  {pooled_better}"
        )
    lines.append("")
    if result.verdict == VERDICT_NO_COVERAGE:
        lines.append(
            f"VERDICT: {VERDICT_NO_COVERAGE} (joined legs {result.n_legs} < {MIN_COVERAGE_LEGS})"
        )
    else:
        lines.append(f"VERDICT: {result.verdict}")
    return "\n".join(lines)


def _join_legs(
    props: pd.DataFrame,
    model: pd.DataFrame,
    actuals: pd.DataFrame,
) -> pd.DataFrame:
    """Join props -> model medians -> realized stats and score each leg in FD points."""

    if model.empty or actuals.empty:
        return pd.DataFrame()

    model_frame = model.loc[:, ["player_key", "player_id", "stat_type", "median"]].copy()
    model_frame["player_id"] = model_frame["player_id"].astype(str)

    merged = props.merge(model_frame, on=["player_key", "stat_type"], how="inner")
    if merged.empty:
        return merged

    realized = _actual_stat_long(actuals)
    merged = merged.merge(realized, on=["player_id", "stat_type"], how="inner")
    if merged.empty:
        return merged

    merged["model_fd"] = [
        _stat_fd_points(stat_type, median)
        for stat_type, median in zip(merged["stat_type"], merged["median"])
    ]
    merged["market_fd"] = [
        _stat_fd_points(stat_type, line)
        for stat_type, line in zip(merged["stat_type"], merged["line"])
    ]
    merged["actual_fd"] = [
        _stat_fd_points(stat_type, actual)
        for stat_type, actual in zip(merged["stat_type"], merged["actual"])
    ]
    return merged


def _summarize(season: int, week: int, merged: pd.DataFrame) -> MarketBenchmarkResult:
    if merged.empty:
        return MarketBenchmarkResult(
            season=season,
            week=week,
            n_legs=0,
            model_mae_fd=0.0,
            market_mae_fd=0.0,
            verdict=VERDICT_NO_COVERAGE,
            by_stat=[],
        )

    by_stat: list[StatBenchmark] = []
    for stat_type in STAT_TYPES:
        legs = merged.loc[merged["stat_type"] == stat_type]
        if legs.empty:
            continue
        by_stat.append(_stat_benchmark(stat_type, legs))

    model_metrics = accuracy_metrics(merged["model_fd"], merged["actual_fd"])
    market_metrics = accuracy_metrics(merged["market_fd"], merged["actual_fd"])
    n_legs = int(len(merged))

    if n_legs < MIN_COVERAGE_LEGS:
        verdict = VERDICT_NO_COVERAGE
    elif model_metrics["mae"] < market_metrics["mae"]:
        verdict = VERDICT_MODEL
    else:
        verdict = VERDICT_MARKET

    return MarketBenchmarkResult(
        season=season,
        week=week,
        n_legs=n_legs,
        model_mae_fd=model_metrics["mae"],
        market_mae_fd=market_metrics["mae"],
        verdict=verdict,
        by_stat=by_stat,
    )


def _stat_benchmark(stat_type: str, legs: pd.DataFrame) -> StatBenchmark:
    model_metrics = accuracy_metrics(legs["model_fd"], legs["actual_fd"])
    market_metrics = accuracy_metrics(legs["market_fd"], legs["actual_fd"])
    diff = model_metrics["mae"] - market_metrics["mae"]
    return StatBenchmark(
        stat_type=stat_type,
        n_legs=int(len(legs)),
        model_mae_fd=model_metrics["mae"],
        market_mae_fd=market_metrics["mae"],
        diff_fd=diff,
        better="model" if diff < 0 else "market",
    )


def _actual_stat_long(actuals: pd.DataFrame) -> pd.DataFrame:
    """Melt realized PBP aggregates into ``player_id, stat_type, actual`` rows."""

    if actuals.empty or "player_id" not in actuals.columns:
        return pd.DataFrame(columns=["player_id", "stat_type", "actual"])

    stats = [stat_type for stat_type in STAT_TYPES if stat_type in actuals.columns]
    if not stats:
        return pd.DataFrame(columns=["player_id", "stat_type", "actual"])

    frame = actuals.loc[:, ["player_id", *stats]].copy()
    frame["player_id"] = frame["player_id"].astype(str)
    long = frame.melt(
        id_vars="player_id",
        value_vars=stats,
        var_name="stat_type",
        value_name="actual",
    )
    long["actual"] = pd.to_numeric(long["actual"], errors="coerce").fillna(0.0)
    return long


def _stat_fd_points(stat_type: Any, value: Any) -> float:
    """FanDuel points for a single stat, reusing the repo scoring."""

    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        number = 0.0
    return float(fd_points({str(stat_type): float(number)}))


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(number) else float(number)


def _normalize_header(value: Any) -> str:
    return str(value or "").strip().lower()
