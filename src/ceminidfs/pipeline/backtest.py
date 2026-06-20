"""Walk-forward backtest against historical nflverse play-by-play."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ceminidfs.config import load_config
from ceminidfs.data.fetch import _cache_dir, fetch_schedules, filter_by_week
from ceminidfs.data.vegas import enrich_schedules_with_vegas
from ceminidfs.models.scoring import fantasy_points_from_stats
from ceminidfs.models.usage import player_game_stats_from_pbp
from ceminidfs.pipeline.engine import build_diy_projections_from_frames, load_week_artifacts, normalize_join_key
from ceminidfs.pipeline.metrics import accuracy_metrics


@dataclass
class WeekBacktestResult:
    season: int
    week: int
    n_players: int
    mae_fd: float
    rmse_fd: float
    spearman_fd: float


@dataclass
class BacktestSummary:
    season: int
    start_week: int
    end_week: int
    weeks: list[WeekBacktestResult] = field(default_factory=list)
    mae_fd: float = 0.0
    rmse_fd: float = 0.0
    spearman_fd: float = 0.0
    n_player_weeks: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["weeks"] = [asdict(week) for week in self.weeks]
        return payload


def load_season_pbp(season: int) -> pd.DataFrame:
    """Load season-level PBP parquet from the fetch cache."""

    path = _cache_dir() / f"pbp_{season}.parquet"
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing season PBP cache at {path}. "
            f"Run fetch first: ceminidfs fetch --season {season} --week 1"
        )
    return pd.read_parquet(path)


def resolve_vegas_for_week(season: int, week: int) -> pd.DataFrame:
    """Load week vegas from cache or build from season schedules."""

    vegas, _, _ = load_week_artifacts(season, week)
    if not vegas.empty:
        return vegas

    schedules = fetch_schedules(season)
    week_schedules = filter_by_week(schedules, week)
    if week_schedules.empty:
        return pd.DataFrame()
    return enrich_schedules_with_vegas(week_schedules)


def roster_from_historical_pbp(
    historical_pbp: pd.DataFrame,
    vegas: pd.DataFrame,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Build a backtest roster from players with prior usage on teams in the slate."""

    teams = _teams_in_vegas(vegas)
    stats = player_game_stats_from_pbp(historical_pbp)
    if stats.empty or not teams:
        return pd.DataFrame(columns=["player_id", "player_name", "team", "position"])

    if "season" in stats.columns:
        stats = stats.loc[pd.to_numeric(stats["season"], errors="coerce").fillna(season) == season]
    stats = stats.loc[stats["team"].isin(teams)]
    if stats.empty:
        return pd.DataFrame(columns=["player_id", "player_name", "team", "position"])

    stats = stats.sort_values(["week", "game_id"])
    roster = (
        stats.groupby(["player_id", "team"], as_index=False)
        .agg(
            player_name=("player_name", "last"),
            position=("position", "last"),
        )
        .reindex(columns=["player_id", "player_name", "team", "position"])
    )
    roster["position"] = roster["position"].fillna("").astype(str).str.upper()
    return roster


def actual_week_fantasy_points(pbp: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    """Aggregate realized counting stats and fantasy points for one week."""

    if pbp.empty or "week" not in pbp.columns:
        return pd.DataFrame()

    week_pbp = pbp.loc[pd.to_numeric(pbp["week"], errors="coerce") == week].copy()
    if "season" in week_pbp.columns:
        week_pbp = week_pbp.loc[pd.to_numeric(week_pbp["season"], errors="coerce").fillna(season) == season]
    if week_pbp.empty:
        return pd.DataFrame()

    rows: dict[str, dict[str, Any]] = {}

    def upsert(player_id: str, player_name: str, team: str, position: str, updates: Mapping[str, float]) -> None:
        if not player_id:
            return
        record = rows.setdefault(
            player_id,
            {
                "player_id": player_id,
                "player_name": player_name,
                "team": team,
                "position": position,
                "pass_yds": 0.0,
                "pass_td": 0.0,
                "int": 0.0,
                "rush_yds": 0.0,
                "rush_td": 0.0,
                "rec": 0.0,
                "rec_yds": 0.0,
                "rec_td": 0.0,
                "fumbles_lost": 0.0,
            },
        )
        if player_name:
            record["player_name"] = player_name
        if team:
            record["team"] = team
        if position:
            record["position"] = position
        for key, value in updates.items():
            record[key] = float(record.get(key, 0.0)) + float(value)

    _aggregate_passing(week_pbp, upsert)
    _aggregate_rushing(week_pbp, upsert)
    _aggregate_receiving(week_pbp, upsert)

    if not rows:
        return pd.DataFrame()

    actuals = pd.DataFrame(rows.values())
    points = actuals.apply(lambda row: fantasy_points_from_stats(row.to_dict()), axis=1)
    actuals["fd_actual"] = [fd for fd, _ in points]
    actuals["dk_actual"] = [dk for _, dk in points]
    actuals["join_key"] = actuals.apply(
        lambda row: normalize_join_key(row["player_name"], row["team"], row["position"]),
        axis=1,
    )
    return actuals


def backtest_week(
    season: int,
    week: int,
    pbp: pd.DataFrame,
    config: Mapping[str, Any] | None = None,
) -> tuple[WeekBacktestResult, pd.DataFrame]:
    """Walk-forward backtest for a single week."""

    empty = WeekBacktestResult(season, week, 0, 0.0, 0.0, 0.0)
    vegas = resolve_vegas_for_week(season, week)
    if vegas.empty:
        return empty, pd.DataFrame()

    historical = _historical_pbp(pbp, season, week)
    roster = roster_from_historical_pbp(historical, vegas, season, week)
    if roster.empty:
        return empty, pd.DataFrame()

    projections = build_diy_projections_from_frames(
        season,
        week,
        pbp,
        vegas,
        None,
        roster,
        config=config,
    )
    actuals = actual_week_fantasy_points(pbp, season, week)
    if projections.empty or actuals.empty:
        return empty, pd.DataFrame()

    merged = projections.merge(
        actuals[["player_id", "fd_actual", "dk_actual"]],
        on="player_id",
        how="inner",
    )
    if merged.empty:
        return empty, pd.DataFrame()

    metrics = accuracy_metrics(merged["fd_projection"], merged["fd_actual"])
    result = WeekBacktestResult(
        season,
        week,
        len(merged),
        metrics["mae"],
        metrics["rmse"],
        metrics["spearman"],
    )
    return result, merged[["fd_projection", "fd_actual"]]


def run_backtest(
    season: int,
    start_week: int,
    end_week: int,
    config: Mapping[str, Any] | None = None,
) -> BacktestSummary:
    """Run walk-forward backtest across a week range."""

    if start_week > end_week:
        raise ValueError("start_week must be <= end_week")

    cfg = dict(config or load_config())
    pbp = load_season_pbp(season)
    summary = BacktestSummary(season=season, start_week=start_week, end_week=end_week)

    all_errors: list[float] = []
    all_proj: list[float] = []
    all_actual: list[float] = []

    for week in range(start_week, end_week + 1):
        result, merged = backtest_week(season, week, pbp, config=cfg)
        summary.weeks.append(result)
        if merged.empty:
            continue
        errors = merged["fd_projection"] - merged["fd_actual"]
        all_errors.extend(errors.tolist())
        all_proj.extend(merged["fd_projection"].tolist())
        all_actual.extend(merged["fd_actual"].tolist())

    if all_errors:
        series = pd.Series(all_errors)
        summary.n_player_weeks = len(series)
        overall = accuracy_metrics(all_proj, all_actual)
        summary.mae_fd = overall["mae"]
        summary.rmse_fd = overall["rmse"]
        summary.spearman_fd = overall["spearman"]
    return summary


def write_backtest_report(summary: BacktestSummary, path: str | Path) -> Path:
    """Write JSON backtest summary to disk."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary.to_dict(), indent=2) + "\n", encoding="utf-8")
    return out


def format_backtest_summary(summary: BacktestSummary) -> str:
    """Return a human-readable backtest summary."""

    lines = [
        f"CeminiDFS backtest — season {summary.season} weeks {summary.start_week}-{summary.end_week}",
        f"Player-weeks: {summary.n_player_weeks}",
        f"MAE (FD): {summary.mae_fd:.2f}",
        f"RMSE (FD): {summary.rmse_fd:.2f}",
        f"Spearman (FD): {summary.spearman_fd:.3f}",
        "",
        "Per week:",
    ]
    for week in summary.weeks:
        lines.append(
            f"  w{week.week:02d}: n={week.n_players} MAE={week.mae_fd:.2f} "
            f"RMSE={week.rmse_fd:.2f} rho={week.spearman_fd:.3f}"
        )
    return "\n".join(lines)


def _historical_pbp(pbp: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    frame = pbp.copy()
    if "season" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["season"], errors="coerce").fillna(season) == season]
    if "week" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["week"], errors="coerce") < week]
    return frame


def _teams_in_vegas(vegas: pd.DataFrame) -> set[str]:
    if vegas.empty:
        return set()
    teams = set(vegas.get("home_team", pd.Series(dtype=str)).astype(str))
    teams.update(vegas.get("away_team", pd.Series(dtype=str)).astype(str))
    return {team for team in teams if team and team != "nan"}


def _aggregate_passing(pbp: pd.DataFrame, upsert) -> None:
    id_col = _first_col(pbp, ("passer_player_id", "passer_id"))
    name_col = _first_col(pbp, ("passer_player_name", "passer"))
    if id_col is None and name_col is None:
        return
    mask = _flag(pbp, ("pass_attempt", "pass")).eq(1)
    for _, row in pbp.loc[mask].iterrows():
        player_id = str(row.get(id_col, "") if id_col else row.get(name_col, ""))
        upsert(
            player_id,
            str(row.get(name_col, "") if name_col else ""),
            str(row.get("posteam", "")),
            "QB",
            {
                "pass_yds": _num(row, ("passing_yards", "pass_yards", "yards_gained")),
                "pass_td": _num(row, ("passing_tds", "pass_touchdown")),
                "int": _num(row, ("interception", "interceptions")),
            },
        )


def _aggregate_rushing(pbp: pd.DataFrame, upsert) -> None:
    id_col = _first_col(pbp, ("rusher_player_id", "rusher_id"))
    name_col = _first_col(pbp, ("rusher_player_name", "rusher"))
    if id_col is None and name_col is None:
        return
    mask = _flag(pbp, ("rush_attempt", "rush")).eq(1)
    for _, row in pbp.loc[mask].iterrows():
        player_id = str(row.get(id_col, "") if id_col else row.get(name_col, ""))
        upsert(
            player_id,
            str(row.get(name_col, "") if name_col else ""),
            str(row.get("posteam", "")),
            "RB",
            {
                "rush_yds": _num(row, ("rushing_yards", "rush_yards", "yards_gained")),
                "rush_td": _num(row, ("rushing_tds", "rush_touchdown")),
            },
        )


def _aggregate_receiving(pbp: pd.DataFrame, upsert) -> None:
    id_col = _first_col(pbp, ("receiver_player_id", "receiver_id"))
    name_col = _first_col(pbp, ("receiver_player_name", "receiver"))
    if id_col is None and name_col is None:
        return
    mask = _flag(pbp, ("pass_attempt", "pass")).eq(1)
    for _, row in pbp.loc[mask].iterrows():
        if _num(row, ("complete_pass",)) < 1:
            continue
        player_id = str(row.get(id_col, "") if id_col else row.get(name_col, ""))
        upsert(
            player_id,
            str(row.get(name_col, "") if name_col else ""),
            str(row.get("posteam", "")),
            "WR",
            {
                "rec": 1.0,
                "rec_yds": _num(row, ("receiving_yards", "yards_gained")),
                "rec_td": _num(row, ("receiving_tds", "pass_touchdown")),
            },
        )


def _first_col(df: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def _flag(df: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    col = _first_col(df, names)
    if col is None:
        return pd.Series(0, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0)


def _num(row: pd.Series, names: tuple[str, ...]) -> float:
    for name in names:
        if name in row.index and pd.notna(row[name]):
            return float(row[name])
    return 0.0
