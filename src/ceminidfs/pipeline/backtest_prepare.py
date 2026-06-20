"""Batch cache preparation for offseason backtests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ceminidfs.data.fetch import fetch_pbp
from ceminidfs.pipeline.fetch import fetch_week


@dataclass
class PrepareSeasonResult:
    season: int
    start_week: int
    end_week: int
    weeks_fetched: list[int] = field(default_factory=list)
    pbp_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "start_week": self.start_week,
            "end_week": self.end_week,
            "weeks_fetched": self.weeks_fetched,
            "pbp_rows": self.pbp_rows,
        }


def prepare_season_cache(
    season: int,
    start_week: int,
    end_week: int,
    config: Mapping[str, Any] | None = None,
) -> PrepareSeasonResult:
    """Fetch nflverse week caches for a season range (no FanDuel salary required)."""

    if start_week > end_week:
        raise ValueError("start_week must be <= end_week")

    result = PrepareSeasonResult(season=season, start_week=start_week, end_week=end_week)
    for week in range(start_week, end_week + 1):
        fetch_week(season, week, config=config)
        result.weeks_fetched.append(week)

    pbp = fetch_pbp(season)
    result.pbp_rows = int(len(pbp))
    return result


def format_prepare_summary(result: PrepareSeasonResult) -> str:
    weeks = ", ".join(str(week) for week in result.weeks_fetched)
    return (
        f"Prepared season {result.season} weeks {result.start_week}-{result.end_week}\n"
        f"Fetched weeks: {weeks}\n"
        f"Season PBP rows: {result.pbp_rows}"
    )
