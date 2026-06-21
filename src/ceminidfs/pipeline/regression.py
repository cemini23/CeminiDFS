"""One-command offseason regression: prepare → backtest → calibrate (+ optional extras)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ceminidfs.config import load_config
from ceminidfs.pipeline.backtest import format_backtest_summary, run_backtest, write_backtest_report
from ceminidfs.pipeline.backtest_prepare import prepare_season_cache
from ceminidfs.pipeline.benchmark_replay import (
    format_benchmark_replay,
    replay_benchmark_directory,
    write_benchmark_replay_report,
)
from ceminidfs.pipeline.calibration import (
    build_calibration_report,
    render_calibration_brief,
    write_calibration_brief,
    write_calibration_json,
)
from ceminidfs.pipeline.lineup_backtest import (
    format_lineup_backtest_summary,
    run_lineup_backtest,
    write_lineup_backtest_report,
)


@dataclass
class RegressionResult:
    season: int
    start_week: int
    end_week: int
    prepared_weeks: list[int] = field(default_factory=list)
    backtest_report: str | None = None
    calibration_brief: str | None = None
    calibration_json: str | None = None
    lineup_backtest_report: str | None = None
    benchmark_replay_report: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_weekly_regression(
    season: int,
    start_week: int,
    end_week: int,
    *,
    config: Mapping[str, Any] | None = None,
    output_dir: str | Path = "reports",
    prepare: bool = False,
    skip_lineup: bool = False,
    benchmark_dir: str | Path | None = None,
    benchmark_csv: str | Path | None = None,
    benchmark_week: int | None = None,
) -> RegressionResult:
    """Run the full pre-season validation stack for a week range."""

    if start_week > end_week:
        raise ValueError("start_week must be <= end_week")

    cfg = dict(config or load_config())
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = f"{season}_w{start_week}-{end_week}"

    result = RegressionResult(season=season, start_week=start_week, end_week=end_week)
    if prepare:
        prepared = prepare_season_cache(season, start_week, end_week, config=cfg)
        result.prepared_weeks = list(prepared.weeks_fetched)

    backtest_summary = run_backtest(season, start_week, end_week, config=cfg)
    backtest_path = write_backtest_report(backtest_summary, out / f"backtest_{tag}.json")
    result.backtest_report = str(backtest_path)
    print(format_backtest_summary(backtest_summary))

    calibration = build_calibration_report(
        season,
        start_week,
        end_week,
        benchmark_csv=benchmark_csv,
        benchmark_week=benchmark_week,
        config=cfg,
    )
    brief_path = write_calibration_brief(calibration, out / f"calibration_{tag}.md")
    json_path = write_calibration_json(calibration, out / f"calibration_{tag}.json")
    result.calibration_brief = str(brief_path)
    result.calibration_json = str(json_path)
    print(render_calibration_brief(calibration))

    if not skip_lineup:
        lineup_summary = run_lineup_backtest(season, start_week, end_week, config=cfg)
        lineup_path = write_lineup_backtest_report(
            lineup_summary, out / f"lineup_backtest_{tag}.json"
        )
        result.lineup_backtest_report = str(lineup_path)
        print(format_lineup_backtest_summary(lineup_summary))

    if benchmark_dir is not None:
        replay = replay_benchmark_directory(
            season,
            start_week,
            end_week,
            benchmark_dir,
            config=cfg,
        )
        replay_path = write_benchmark_replay_report(replay, out / f"benchmark_replay_{tag}.json")
        result.benchmark_replay_report = str(replay_path)
        print(format_benchmark_replay(replay))

    manifest_path = out / f"regression_{tag}.json"
    manifest_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    return result


def format_regression_result(result: RegressionResult) -> str:
    lines = [
        f"Regression complete — season {result.season} weeks {result.start_week}-{result.end_week}",
    ]
    if result.prepared_weeks:
        lines.append(f"Prepared weeks: {', '.join(str(week) for week in result.prepared_weeks)}")
    if result.backtest_report:
        lines.append(f"Backtest: {result.backtest_report}")
    if result.calibration_brief:
        lines.append(f"Calibration brief: {result.calibration_brief}")
    if result.calibration_json:
        lines.append(f"Calibration JSON: {result.calibration_json}")
    if result.lineup_backtest_report:
        lines.append(f"Lineup backtest: {result.lineup_backtest_report}")
    if result.benchmark_replay_report:
        lines.append(f"Benchmark replay: {result.benchmark_replay_report}")
    return "\n".join(lines)
