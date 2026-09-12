from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ceminidfs.data.fetch import week_cache_dir
from ceminidfs.data.rosters import load_season_rosters
from ceminidfs.data.stadiums import normalize_team_abbr
from ceminidfs.models.coherence_risk import (
    apply_fourth_down_aggressiveness_adjustments,
    apply_pass_protection_penalties,
    apply_red_zone_usage_adjustments,
    apply_workload_risk_flags,
    build_player_workload_index,
    build_team_fourth_down_aggressiveness,
    build_team_pass_protection_stress,
    build_team_red_zone_run_tendency,
)
from ceminidfs.models.coherence_settings import CoherenceRiskSettings
from ceminidfs.models.scoring import add_fantasy_points
from ceminidfs.models.stats import build_week_stats
from ceminidfs.models.dst import build_week_dst_projections
from ceminidfs.models.usage import build_week_usage, history_week_cutoff, player_game_stats_from_pbp
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
                "injury_status": str(row.get("injury_status") or row.get("Injury Indicator") or ""),
            }
        )
    return pd.DataFrame(
        roster_rows,
        columns=["player_id", "player_name", "team", "position", "injury_status"],
    )


def normalize_join_key(name: Any, team: Any, position: Any) -> str:
    """Return a stable salary-to-stats join key."""

    return "|".join(
        (
            _normalize_token(name),
            _normalize_token(normalize_team_abbr(team)),
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

    coherence_settings = CoherenceRiskSettings.from_config(config)
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

    hist_cutoff = history_week_cutoff(historical_pbp, season, week)
    if coherence_settings.enabled and coherence_settings.red_zone_playcall.enabled:
        rz_by_team = build_team_red_zone_run_tendency(
            historical_pbp,
            hist_cutoff,
            settings=coherence_settings,
        )
        usage_df = apply_red_zone_usage_adjustments(usage_df, rz_by_team, coherence_settings)
    if coherence_settings.enabled and coherence_settings.fourth_down.enabled:
        aggression_by_team = build_team_fourth_down_aggressiveness(
            historical_pbp,
            hist_cutoff,
            settings=coherence_settings,
        )
        usage_df = apply_fourth_down_aggressiveness_adjustments(
            usage_df,
            aggression_by_team,
            coherence_settings,
        )
    if coherence_settings.enabled and coherence_settings.workload.enabled:
        workload_by_player = build_player_workload_index(
            historical_pbp,
            hist_cutoff,
            settings=coherence_settings,
        )
        usage_df = apply_workload_risk_flags(usage_df, workload_by_player, coherence_settings)

    stats_df = build_week_stats(usage_df, historical_pbp, season=season, week=week, config=config)
    if stats_df.empty:
        raise ValueError(f"No player stat projections built for {season} week {week}")

    if coherence_settings.enabled and coherence_settings.pass_protection.enabled:
        stress_by_team = build_team_pass_protection_stress(
            historical_pbp,
            hist_cutoff,
            settings=coherence_settings,
        )
        stats_df = apply_pass_protection_penalties(stats_df, stress_by_team, coherence_settings)

    scored = add_fantasy_points(stats_df)
    dst_df = build_week_dst_projections(
        vegas,
        volume_df,
        season=season,
        week=week,
        config=config,
    )
    if not dst_df.empty:
        scored = pd.concat([scored, dst_df], ignore_index=True, sort=False)
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
    for column in (
        "coherence_risk_flag",
        "pass_protection_stress",
        "workload_index",
        "workload_risk_flag",
    ):
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
            if "coherence_risk_flag" in projection:
                mapped["coherence_risk_flag"] = projection.get("coherence_risk_flag")
            if "pass_protection_stress" in projection:
                mapped["pass_protection_stress"] = projection.get("pass_protection_stress")
            if "workload_index" in projection:
                mapped["workload_index"] = projection.get("workload_index")
            if "workload_risk_flag" in projection:
                mapped["workload_risk_flag"] = projection.get("workload_risk_flag")
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
        season_num = pd.to_numeric(frame["season"], errors="coerce").fillna(season)
        keep_season = season_num == season
        if week <= 1:
            keep_season = keep_season | (season_num == season - 1)
        frame = frame.loc[keep_season].copy()
        season_num = pd.to_numeric(frame["season"], errors="coerce").fillna(season)
    if "week" in frame.columns:
        week_num = pd.to_numeric(frame["week"], errors="coerce")
        if "season" in frame.columns:
            current = season_num == season
            frame = frame.loc[~current | (week_num < week)].copy()
        else:
            frame = frame.loc[week_num < week]
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

    historical = player_game_stats_from_pbp(_historical_pbp(pbp, season, week))
    if historical.empty:
        return roster

    id_by_exact_key: dict[str, str] = {}
    id_by_name_team: dict[str, str] = {}
    id_by_abbrev_team: dict[str, str] = {}
    for _, row in historical.sort_values(["week", "game_id"]).iterrows():
        name = row.get("player_name", "")
        team = row.get("team", "")
        position = row.get("position", "")
        player_id = str(row.get("player_id", ""))
        if not player_id:
            continue
        id_by_exact_key[normalize_join_key(name, team, position)] = player_id
        id_by_name_team[_name_team_key(name, team)] = player_id
        id_by_abbrev_team[_name_team_key(name, team)] = player_id

    roster_by_name_team, roster_by_name = _gsis_lookups_from_weekly_rosters(season, week)

    aligned = roster.copy()
    aligned["player_id"] = aligned.apply(
        lambda row: _resolve_pbp_player_id(
            row,
            id_by_exact_key,
            id_by_name_team,
            id_by_abbrev_team,
            roster_by_name_team,
            roster_by_name,
        ),
        axis=1,
    )
    return aligned


_NAME_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})


def _resolve_pbp_player_id(
    row: pd.Series,
    id_by_exact_key: dict[str, str],
    id_by_name_team: dict[str, str],
    id_by_abbrev_team: dict[str, str],
    roster_by_name_team: dict[str, str],
    roster_by_name: dict[str, str],
) -> str:
    name = row.get("player_name", "")
    team = row.get("team", "")
    position = row.get("position", "")
    fallback = str(row.get("player_id", "") or "")
    if str(position or "").upper() in {"D", "DEF", "DST"}:
        return fallback
    return (
        id_by_exact_key.get(normalize_join_key(name, team, position))
        or id_by_name_team.get(_name_team_key(name, team))
        or roster_by_name_team.get(_name_team_key(name, team))
        or roster_by_name.get(_normalize_token(name))
        or id_by_abbrev_team.get(_name_team_key(_abbrev_last_name(name), team))
        or fallback
    )


def _gsis_lookups_from_weekly_rosters(season: int, week: int) -> tuple[dict[str, str], dict[str, str]]:
    frames: list[pd.DataFrame] = []
    seasons = (season, season - 1) if week <= 1 and season > 0 else (season,)
    for roster_season in seasons:
        try:
            frame = load_season_rosters(roster_season)
        except (ImportError, FileNotFoundError, OSError, AttributeError, ValueError):
            continue
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return {}, {}

    rosters = pd.concat(frames, ignore_index=True)
    if "week" in rosters.columns:
        rosters = rosters.sort_values(by="week")
    by_name_team: dict[str, str] = {}
    ids_by_name: dict[str, set[str]] = {}
    last_id_by_name: dict[str, str] = {}
    for _, row in rosters.iterrows():
        gsis_id = str(row.get("gsis_id") or "").strip()
        full_name = str(row.get("full_name") or "").strip()
        team = str(row.get("team") or "").strip()
        if not gsis_id or not full_name:
            continue
        by_name_team[_name_team_key(full_name, team)] = gsis_id
        name_key = _normalize_token(full_name)
        ids_by_name.setdefault(name_key, set()).add(gsis_id)
        last_id_by_name[name_key] = gsis_id
    by_name = {name: gid for name, gid in last_id_by_name.items() if len(ids_by_name.get(name, ())) == 1}
    return by_name_team, by_name


def _abbrev_last_name(name: Any) -> str:
    parts = [part for part in str(name or "").replace("'", "").split() if part]
    parts = [part for part in parts if part.lower().rstrip(".") not in _NAME_SUFFIXES]
    if len(parts) < 2:
        return ""
    return f"{parts[0][0]}.{parts[-1]}"


def _name_team_key(name: Any, team: Any) -> str:
    return "|".join((_normalize_token(name), _normalize_token(normalize_team_abbr(team))))


def _normalize_token(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())
