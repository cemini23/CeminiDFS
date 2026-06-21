"""Replay paid benchmark CSVs across multiple weeks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ceminidfs.pipeline.benchmark_compare import (
    BenchmarkCompareResult,
    compare_benchmark_week,
    format_benchmark_compare,
)


@dataclass
class BenchmarkReplaySummary:
    season: int
    start_week: int
    end_week: int
    directory: str
    weeks: list[BenchmarkCompareResult] = field(default_factory=list)
    missing_weeks: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["weeks"] = [week.to_dict() for week in self.weeks]
        return payload


def find_benchmark_csv(directory: str | Path, week: int) -> Path | None:
    """Locate a benchmark export for one week inside a directory."""

    root = Path(directory)
    if not root.is_dir():
        return None

    patterns = (
        f"*w{week:02d}*.csv",
        f"*w{week}*.csv",
        f"*week*{week}*.csv",
        f"*{week}.csv",
    )
    for pattern in patterns:
        matches = sorted(root.glob(pattern))
        if matches:
            return matches[0]
    return None


def replay_benchmark_directory(
    season: int,
    start_week: int,
    end_week: int,
    directory: str | Path,
    *,
    site: str = "fanduel",
    source: str | None = None,
    include_diy: bool = True,
    config: Mapping[str, Any] | None = None,
) -> BenchmarkReplaySummary:
    """Compare every discoverable benchmark CSV in a folder across a week range."""

    if start_week > end_week:
        raise ValueError("start_week must be <= end_week")

    summary = BenchmarkReplaySummary(
        season=season,
        start_week=start_week,
        end_week=end_week,
        directory=str(directory),
    )
    for week in range(start_week, end_week + 1):
        csv_path = find_benchmark_csv(directory, week)
        if csv_path is None:
            summary.missing_weeks.append(week)
            continue
        result = compare_benchmark_week(
            season,
            week,
            csv_path,
            site=site,
            source=source,
            include_diy=include_diy,
            config=config,
        )
        summary.weeks.append(result)
    return summary


def write_benchmark_replay_report(summary: BenchmarkReplaySummary, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


def format_benchmark_replay(summary: BenchmarkReplaySummary) -> str:
    lines = [
        f"Benchmark replay — season {summary.season} weeks {summary.start_week}-{summary.end_week}",
        f"Directory: {summary.directory}",
        f"Weeks found: {len(summary.weeks)}",
        f"Missing weeks: {', '.join(str(week) for week in summary.missing_weeks) or 'none'}",
        "",
    ]
    for result in summary.weeks:
        lines.append(format_benchmark_compare(result))
        lines.append("")
    return "\n".join(lines).rstrip()
