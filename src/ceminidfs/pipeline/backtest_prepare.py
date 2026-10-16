"""Batch cache preparation for offseason backtests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ceminidfs.data.fetch import fetch_force_enabled, fetch_pbp, warm_ngs_caches, week_cache_dir
from ceminidfs.data.rosters import load_season_rosters
from ceminidfs.pipeline.fetch import fetch_week


@dataclass
class PrepareSeasonResult:
    season: int
    start_week: int
    end_week: int
    weeks_fetched: list[int] = field(default_factory=list)
    weather_weeks: list[int] = field(default_factory=list)
    pbp_rows: int = 0
    roster_rows: int = 0
    ngs_receiving_rows: int = 0
    ngs_passing_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "start_week": self.start_week,
            "end_week": self.end_week,
            "weeks_fetched": self.weeks_fetched,
            "weather_weeks": self.weather_weeks,
            "pbp_rows": self.pbp_rows,
            "roster_rows": self.roster_rows,
            "ngs_receiving_rows": self.ngs_receiving_rows,
            "ngs_passing_rows": self.ngs_passing_rows,
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
        if _week_weather_cached(season, week):
            result.weather_weeks.append(week)

    pbp = fetch_pbp(season)
    result.pbp_rows = int(len(pbp))

    try:
        rosters = load_season_rosters(season)
        result.roster_rows = int(len(rosters))
    except (ImportError, OSError, AttributeError):
        result.roster_rows = 0

    # NGS is season-scoped; warm both caches for the receiving elasticity layer.
    ngs = warm_ngs_caches(season, force=fetch_force_enabled(config))
    receiving_ngs = ngs.get("receiving")
    passing_ngs = ngs.get("passing")
    result.ngs_receiving_rows = int(len(receiving_ngs)) if receiving_ngs is not None else 0
    result.ngs_passing_rows = int(len(passing_ngs)) if passing_ngs is not None else 0

    return result


def format_prepare_summary(result: PrepareSeasonResult) -> str:
    weeks = ", ".join(str(week) for week in result.weeks_fetched)
    weather = ", ".join(str(week) for week in result.weather_weeks) or "none"
    return (
        f"Prepared season {result.season} weeks {result.start_week}-{result.end_week}\n"
        f"Fetched weeks: {weeks}\n"
        f"Weather cached weeks: {weather}\n"
        f"Season PBP rows: {result.pbp_rows}\n"
        f"Season roster rows: {result.roster_rows}\n"
        f"Season NGS rows: receiving {result.ngs_receiving_rows}, passing {result.ngs_passing_rows}"
    )


def _week_weather_cached(season: int, week: int) -> bool:
    path = week_cache_dir(season, week) / "weather.parquet"
    return path.is_file() and path.stat().st_size > 0
