from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ceminidfs.data.fetch import week_cache_dir
from ceminidfs.models.scoring import add_fantasy_points
from ceminidfs.models.stats import build_week_stats
from ceminidfs.models.usage import build_week_usage, player_game_stats_from_pbp
from ceminidfs.models.volume import build_week_volume


def load_week_artifacts(
    season: int,
    week: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """Load cached weekly vegas, PBP, and weather artifacts."""

    cache_dir = week_cache_dir(season, week)
    vegas = _read_parquet_if_exists(cache_dir / "vegas.parquet")
    pbp = _read_parquet_if_exists(cache_dir / "pbp.parquet")
    weather = _read_parquet_if_exists(cache_dir / "weather.parquet")
    return vegas, pbp, weather


def salary_rows_to_roster(rows: list[dict]) -> pd.DataFrame:
    """Return a usage-model roster frame from canonical salary rows."""

    roster_rows: list[dict[str, Any]] = []
    for row in rows:
        player_id = (
            row.get("fd_id") or row.get("dk_id") or row.get("player_key") or row.get("name", "")
        )
        position = row.get("fd_position") or row.get("dk_position") or row.get("position", "")
        roster_rows.append(
            {
                "player_id": str(player_id or ""),
                "player_name": str(row.get("player_name") or row.get("name") or ""),
                "team": str(row.get("team") or ""),
                "position": str(position or "").upper(),
            }
        )
    return pd.DataFrame(roster_rows, columns=["player_id", "player_name", "team", "position"])


def normalize_join_key(name: Any, team: Any, position: Any) -> str:
    """Return a stable salary-to-stats join key."""

    return "|".join(
        (
            _normalize_token(name),
            _normalize_token(team),
            _normalize_token(position).upper(),
        )
    )


def build_diy_projections(
    season: int,
    week: int,
    salary_rows: list[dict],
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Build scored player projections from cached weekly artifacts."""

    vegas, pbp, weather = load_week_artifacts(season, week)
    if vegas.empty or pbp.empty:
        raise FileNotFoundError(
            f"Missing cached vegas/pbp artifacts for {season} week {week}; run fetch first."
        )

    roster = _align_roster_to_pbp_ids(
        salary_rows_to_roster(salary_rows), pbp, season=season, week=week
    )
    return build_diy_projections_from_frames(
        season,
        week,
        pbp,
        vegas,
        weather,
        roster,
        config=config,
    )


def build_diy_projections_from_frames(
    season: int,
    week: int,
    pbp: pd.DataFrame,
    vegas: pd.DataFrame,
    weather: pd.DataFrame | None,
    roster: pd.DataFrame,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Build scored projections from in-memory weekly frames (backtest-safe)."""

    _ = config  # stats layer reads shrinkage from config; usage reads usage.* keys
    historical_pbp = _historical_pbp(pbp, season, week)
    if vegas.empty or historical_pbp.empty:
        raise ValueError(f"Missing vegas or historical PBP for {season} week {week}")

    volume_df = build_week_volume(vegas, historical_pbp, weather, season=season, week=week)
    if volume_df.empty:
        raise ValueError(f"No team volume projections built for {season} week {week}")

    usage_df = build_week_usage(
        volume_df,
        historical_pbp,
        season=season,
        week=week,
        roster=roster,
        config=config,
    )
    if usage_df.empty:
        raise ValueError(f"No player usage projections built for {season} week {week}")

    stats_df = build_week_stats(usage_df, historical_pbp, season=season, week=week, config=config)
    if stats_df.empty:
        raise ValueError(f"No player stat projections built for {season} week {week}")

    scored = add_fantasy_points(stats_df)
    scored["join_key"] = scored.apply(
        lambda row: normalize_join_key(
            row.get("player_name", ""), row.get("team", ""), row.get("position", "")
        ),
        axis=1,
    )
    scored["opp"] = scored.get("opponent", pd.Series("", index=scored.index)).fillna("").astype(str)
    scored["game"] = scored.apply(_game_key_from_row, axis=1)
    return scored


def merge_projections_into_canonical(
    salary_rows: list[dict],
    stats_df: pd.DataFrame,
) -> list[dict]:
    """Merge DIY FD/DK projections into canonical salary rows."""

    if stats_df.empty or "join_key" not in stats_df.columns:
        return [dict(row) for row in salary_rows]

    merge_columns = ["fd_projection", "dk_projection"]
    for column in ("opp", "game", "opponent"):
        if column in stats_df.columns:
            merge_columns.append(column)
    stats_by_key = (
        stats_df.drop_duplicates(subset=["join_key"], keep="first")
        .set_index("join_key")[merge_columns]
        .to_dict("index")
    )

    merged: list[dict[str, Any]] = []
    for row in salary_rows:
        mapped = dict(row)
        position = row.get("fd_position") or row.get("dk_position") or row.get("position", "")
        key = normalize_join_key(
            row.get("player_name") or row.get("name", ""), row.get("team", ""), position
        )
        projection = stats_by_key.get(key)
        if projection:
            mapped["fd_projection"] = projection.get("fd_projection", "")
            mapped["dk_projection"] = projection.get("dk_projection", "")
            opp = projection.get("opp") or projection.get("opponent")
            if opp:
                mapped["opp"] = opp
                mapped.setdefault("opponent", opp)
            game = projection.get("game")
            if game:
                mapped["game"] = game
        merged.append(mapped)
    return merged


def _game_key_from_row(row: pd.Series) -> str:
    team = str(row.get("team", "") or "").strip().upper()
    opp = str(row.get("opponent", row.get("opp", "")) or "").strip().upper()
    if not team or not opp:
        return ""
    ordered = sorted((team, opp))
    return f"{ordered[0]}@{ordered[1]}"


def _historical_pbp(pbp: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    if pbp.empty:
        return pbp
    frame = pbp.copy()
    if "season" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["season"], errors="coerce").fillna(season) == season]
    if "week" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["week"], errors="coerce") < week]
    return frame


def _read_parquet_if_exists(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_parquet(path)


def _align_roster_to_pbp_ids(
    roster: pd.DataFrame,
    pbp: pd.DataFrame,
    *,
    season: int,
    week: int,
) -> pd.DataFrame:
    if roster.empty or pbp.empty:
        return roster

    historical = player_game_stats_from_pbp(pbp)
    if historical.empty:
        return roster
    if "season" in historical.columns:
        historical = historical.loc[
            pd.to_numeric(historical["season"], errors="coerce").fillna(season) == season
        ]
    if "week" in historical.columns:
        historical = historical.loc[pd.to_numeric(historical["week"], errors="coerce") < week]
    if historical.empty:
        return roster

    id_by_exact_key: dict[str, str] = {}
    id_by_name_team: dict[str, str] = {}
    for _, row in historical.sort_values(["week", "game_id"]).iterrows():
        name = row.get("player_name", "")
        team = row.get("team", "")
        position = row.get("position", "")
        player_id = str(row.get("player_id", ""))
        if not player_id:
            continue
        id_by_exact_key[normalize_join_key(name, team, position)] = player_id
        id_by_name_team[_name_team_key(name, team)] = player_id

    aligned = roster.copy()
    aligned["player_id"] = aligned.apply(
        lambda row: id_by_exact_key.get(
            normalize_join_key(
                row.get("player_name", ""), row.get("team", ""), row.get("position", "")
            ),
            id_by_name_team.get(
                _name_team_key(row.get("player_name", ""), row.get("team", "")), row["player_id"]
            ),
        ),
        axis=1,
    )
    return aligned


def _name_team_key(name: Any, team: Any) -> str:
    return "|".join((_normalize_token(name), _normalize_token(team)))


def _normalize_token(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())
