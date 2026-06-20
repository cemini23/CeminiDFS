"""Player usage projection helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import pandas as pd


LEAGUE_TARGET_SHARE = {"WR": 0.18, "TE": 0.12, "RB": 0.08}
LEAGUE_CARRY_SHARE = {"RB": 0.35}
DEFAULT_SHARE_WEIGHTS = (0.5, 0.3, 0.2)


@dataclass(frozen=True)
class PlayerUsageProjection:
    season: int
    week: int
    team: str
    opponent: str
    player_id: str
    player_name: str
    position: str
    target_share: float
    air_yards_share: float
    carry_share: float
    wopr: float
    snap_share: float | None
    projected_targets: float
    projected_carries: float
    projected_pass_attempts: float
    routes_proxy: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def weighted_blend(
    l3: float,
    season: float,
    prior: float,
    weights: tuple[float, float, float] = DEFAULT_SHARE_WEIGHTS,
) -> float:
    """Blend recent, season, and prior values."""

    return (weights[0] * l3) + (weights[1] * season) + (weights[2] * prior)


def wopr(target_share: float, air_yards_share: float) -> float:
    """Return weighted opportunity rating from target and air-yards shares."""

    return (1.5 * target_share) + (0.7 * air_yards_share)


def herfindahl_index(shares: pd.Series) -> float:
    """Return concentration index for a set of player shares."""

    numeric = pd.to_numeric(shares, errors="coerce").fillna(0.0)
    return float((numeric * numeric).sum())


def player_game_stats_from_pbp(pbp: pd.DataFrame) -> pd.DataFrame:
    """Aggregate play-by-play into one row per player-game."""

    columns = [
        "season",
        "week",
        "team",
        "game_id",
        "player_id",
        "player_name",
        "position",
        "targets",
        "air_yards",
        "carries",
        "pass_attempts",
    ]
    if pbp.empty or "posteam" not in pbp.columns or "week" not in pbp.columns:
        return pd.DataFrame(columns=columns)

    events: list[pd.DataFrame] = []
    base = pbp.copy()
    base["_pass_flag"] = _flag_series(base, ("pass_attempt", "pass"))
    base["_rush_flag"] = _flag_series(base, ("rush",))

    receiver_id_col = _first_present(base, ("receiver_player_id", "receiver_id", "player_id"))
    receiver_name_col = _first_present(base, ("receiver_player_name", "receiver", "player_name"))
    if receiver_id_col or receiver_name_col:
        target_mask = base["_pass_flag"].eq(1)
        if receiver_id_col:
            target_mask &= base[receiver_id_col].notna()
        elif receiver_name_col:
            target_mask &= base[receiver_name_col].notna()
        targets = base.loc[target_mask].copy()
        if not targets.empty:
            events.append(
                _usage_events(
                    targets,
                    player_id_col=receiver_id_col,
                    player_name_col=receiver_name_col,
                    position="",
                    targets=1.0,
                    air_yards_col="air_yards" if "air_yards" in targets.columns else None,
                )
            )

    rusher_id_col = _first_present(base, ("rusher_player_id", "rusher_id"))
    rusher_name_col = _first_present(base, ("rusher_player_name", "rusher"))
    if rusher_id_col or rusher_name_col:
        carry_mask = base["_rush_flag"].eq(1)
        if rusher_id_col:
            carry_mask &= base[rusher_id_col].notna()
        elif rusher_name_col:
            carry_mask &= base[rusher_name_col].notna()
        carries = base.loc[carry_mask].copy()
        if not carries.empty:
            events.append(
                _usage_events(
                    carries,
                    player_id_col=rusher_id_col,
                    player_name_col=rusher_name_col,
                    position="",
                    carries=1.0,
                )
            )

    passer_id_col = _first_present(base, ("passer_player_id", "passer_id", "qb_player_id"))
    passer_name_col = _first_present(base, ("passer_player_name", "passer", "qb_player_name"))
    if passer_id_col or passer_name_col:
        pass_mask = base["_pass_flag"].eq(1)
        if passer_id_col:
            pass_mask &= base[passer_id_col].notna()
        elif passer_name_col:
            pass_mask &= base[passer_name_col].notna()
        pass_attempts = base.loc[pass_mask].copy()
        if not pass_attempts.empty:
            events.append(
                _usage_events(
                    pass_attempts,
                    player_id_col=passer_id_col,
                    player_name_col=passer_name_col,
                    position="QB",
                    pass_attempts=1.0,
                )
            )

    if not events:
        return pd.DataFrame(columns=columns)

    stats = pd.concat(events, ignore_index=True)
    group_cols = ["season", "week", "team", "game_id", "player_id", "player_name", "position"]
    result = (
        stats.groupby(group_cols, dropna=False, as_index=False)[
            ["targets", "air_yards", "carries", "pass_attempts"]
        ]
        .sum()
        .reindex(columns=columns)
    )
    return result


def rolling_shares(
    stats: pd.DataFrame,
    team: str,
    through_week: int,
    windows: tuple[int, ...] = (3,),
) -> pd.DataFrame:
    """Return per-player recent and season usage shares for one team."""

    columns = [
        "player_id",
        "player_name",
        "team",
        "position",
        "l3_target_share",
        "season_target_share",
        "l3_air_yards_share",
        "season_air_yards_share",
        "l3_carry_share",
        "season_carry_share",
    ]
    if stats.empty or not {"team", "week", "player_id"}.issubset(stats.columns):
        return pd.DataFrame(columns=columns)

    team_stats = stats.loc[
        (stats["team"] == team) & (pd.to_numeric(stats["week"], errors="coerce") < through_week)
    ].copy()
    if team_stats.empty:
        return pd.DataFrame(columns=columns)

    window = windows[0] if windows else 3
    recent_stats = team_stats.loc[
        pd.to_numeric(team_stats["week"], errors="coerce") >= through_week - window
    ].copy()
    season_usage = _share_frame(team_stats, prefix="season")
    recent_usage = _share_frame(recent_stats, prefix="l3")

    players = _player_index(team_stats)
    result = players.merge(recent_usage, on="player_id", how="left").merge(
        season_usage, on="player_id", how="left"
    )
    for col in columns:
        if col not in result.columns:
            result[col] = 0.0 if col.endswith("_share") else ""

    return result.reindex(columns=columns).fillna(
        {
            "l3_target_share": 0.0,
            "season_target_share": 0.0,
            "l3_air_yards_share": 0.0,
            "season_air_yards_share": 0.0,
            "l3_carry_share": 0.0,
            "season_carry_share": 0.0,
        }
    )


def identify_qb_starter(stats: pd.DataFrame, team: str, through_week: int) -> str | None:
    """Return the team's likely starting QB by recent pass attempts."""

    required = {"team", "week", "player_id", "pass_attempts"}
    if stats.empty or not required.issubset(stats.columns):
        return None

    team_stats = stats.loc[
        (stats["team"] == team)
        & (pd.to_numeric(stats["week"], errors="coerce") < through_week)
        & (pd.to_numeric(stats["week"], errors="coerce") >= through_week - 3)
    ].copy()
    if team_stats.empty:
        return None

    attempts = (
        team_stats.groupby("player_id", dropna=False)["pass_attempts"]
        .sum()
        .sort_values(ascending=False)
    )
    if attempts.empty or attempts.iloc[0] <= 0:
        return None
    return str(attempts.index[0])


def project_player_usage(
    volume_row: Mapping[str, Any],
    player_shares: Mapping[str, Any],
    *,
    position: str,
) -> PlayerUsageProjection:
    """Project a player's usage from team volume and blended shares."""

    pos = position.upper()
    target_share = weighted_blend(
        _mapping_float(player_shares, "l3_target_share", "target_share"),
        _mapping_float(player_shares, "season_target_share", "target_share"),
        LEAGUE_TARGET_SHARE.get(pos, 0.0),
    )
    air_yards_share = weighted_blend(
        _mapping_float(player_shares, "l3_air_yards_share", "air_yards_share"),
        _mapping_float(player_shares, "season_air_yards_share", "air_yards_share"),
        LEAGUE_TARGET_SHARE.get(pos, 0.0),
    )
    carry_share = weighted_blend(
        _mapping_float(player_shares, "l3_carry_share", "carry_share"),
        _mapping_float(player_shares, "season_carry_share", "carry_share"),
        LEAGUE_CARRY_SHARE.get(pos, 0.0),
    )
    pass_attempts = float(volume_row.get("pass_attempts", 0.0) or 0.0)
    rush_attempts = float(volume_row.get("rush_attempts", 0.0) or 0.0)
    projected_pass_attempts = pass_attempts if pos == "QB" and player_shares.get("is_qb_starter") else 0.0

    return PlayerUsageProjection(
        season=int(volume_row.get("season", 0) or 0),
        week=int(volume_row.get("week", 0) or 0),
        team=str(volume_row.get("team", "")),
        opponent=str(volume_row.get("opponent", "")),
        player_id=str(player_shares.get("player_id", "")),
        player_name=str(player_shares.get("player_name", "")),
        position=pos,
        target_share=target_share,
        air_yards_share=air_yards_share,
        carry_share=carry_share,
        wopr=wopr(target_share, air_yards_share),
        snap_share=_optional_float(player_shares.get("snap_share")),
        projected_targets=target_share * pass_attempts,
        projected_carries=carry_share * rush_attempts,
        projected_pass_attempts=projected_pass_attempts,
        routes_proxy=_optional_float(player_shares.get("routes_proxy")),
    )


def build_week_usage(
    volume_df: pd.DataFrame,
    pbp: pd.DataFrame,
    *,
    season: int,
    week: int,
    roster: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build player usage projections for all teams in a weekly volume frame."""

    columns = list(PlayerUsageProjection.__dataclass_fields__)
    if volume_df.empty:
        return pd.DataFrame(columns=columns)

    week_volume = volume_df.loc[
        (pd.to_numeric(volume_df.get("season", season), errors="coerce") == season)
        & (pd.to_numeric(volume_df.get("week", week), errors="coerce") == week)
    ].copy()
    if week_volume.empty:
        return pd.DataFrame(columns=columns)

    stats = player_game_stats_from_pbp(pbp)
    if "season" in stats.columns:
        stats = stats.loc[pd.to_numeric(stats["season"], errors="coerce").fillna(season) == season]
    stats = stats.loc[pd.to_numeric(stats.get("week", pd.Series(dtype=float)), errors="coerce") < week]

    roster_by_team = _normalize_roster(roster)
    rows: list[dict[str, Any]] = []
    for _, volume_row in week_volume.iterrows():
        team = str(volume_row["team"])
        shares = rolling_shares(stats, team=team, through_week=week)
        share_records = _projection_pool(team, shares, roster_by_team)
        starter_id = identify_qb_starter(stats, team=team, through_week=week)

        for player in share_records:
            player["is_qb_starter"] = bool(starter_id and str(player.get("player_id", "")) == starter_id)
            projection = project_player_usage(
                volume_row.to_dict(),
                player,
                position=str(player.get("position", "")),
            )
            rows.append(projection.to_dict())

    return pd.DataFrame(rows, columns=columns)


def _usage_events(
    plays: pd.DataFrame,
    *,
    player_id_col: str | None,
    player_name_col: str | None,
    position: str,
    targets: float = 0.0,
    air_yards_col: str | None = None,
    carries: float = 0.0,
    pass_attempts: float = 0.0,
) -> pd.DataFrame:
    event = pd.DataFrame(
        {
            "season": plays["season"] if "season" in plays.columns else pd.NA,
            "week": plays["week"],
            "team": plays["posteam"],
            "game_id": plays["game_id"] if "game_id" in plays.columns else "",
            "player_id": _identity_series(plays, player_id_col, player_name_col),
            "player_name": _identity_series(plays, player_name_col, player_id_col),
            "position": position,
            "targets": targets,
            "air_yards": pd.to_numeric(plays[air_yards_col], errors="coerce").fillna(0.0)
            if air_yards_col
            else 0.0,
            "carries": carries,
            "pass_attempts": pass_attempts,
        }
    )
    return event


def _share_frame(stats: pd.DataFrame, *, prefix: str) -> pd.DataFrame:
    usage = (
        stats.groupby("player_id", dropna=False)[["targets", "air_yards", "carries"]]
        .sum()
        .reset_index()
    )
    totals = usage[["targets", "air_yards", "carries"]].sum()
    for source, dest in (
        ("targets", f"{prefix}_target_share"),
        ("air_yards", f"{prefix}_air_yards_share"),
        ("carries", f"{prefix}_carry_share"),
    ):
        denominator = float(totals[source])
        usage[dest] = usage[source] / denominator if denominator > 0 else 0.0
    return usage[
        [
            "player_id",
            f"{prefix}_target_share",
            f"{prefix}_air_yards_share",
            f"{prefix}_carry_share",
        ]
    ]


def _player_index(stats: pd.DataFrame) -> pd.DataFrame:
    players = (
        stats.sort_values(["week", "game_id"])
        .groupby("player_id", dropna=False, as_index=False)
        .tail(1)[["player_id", "player_name", "team", "position"]]
    )
    return players


def _projection_pool(
    team: str,
    shares: pd.DataFrame,
    roster_by_team: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    if team in roster_by_team:
        pool = roster_by_team[team].merge(shares, on=["player_id", "team"], how="left", suffixes=("", "_hist"))
        if "player_name_hist" in pool.columns:
            pool["player_name"] = pool["player_name"].fillna(pool["player_name_hist"])
        if "position_hist" in pool.columns:
            pool["position"] = pool["position"].fillna(pool["position_hist"])
    else:
        pool = shares.copy()

    share_cols = [
        "l3_target_share",
        "season_target_share",
        "l3_air_yards_share",
        "season_air_yards_share",
        "l3_carry_share",
        "season_carry_share",
    ]
    for col in share_cols:
        if col not in pool.columns:
            pool[col] = 0.0
    if "player_name" not in pool.columns:
        pool["player_name"] = pool.get("player_id", "")
    if "position" not in pool.columns:
        pool["position"] = ""

    return pool.fillna({col: 0.0 for col in share_cols}).to_dict("records")


def _normalize_roster(roster: pd.DataFrame | None) -> dict[str, pd.DataFrame]:
    required = {"player_id", "player_name", "team", "position"}
    if roster is None or roster.empty or not required.issubset(roster.columns):
        return {}

    normalized = roster.copy()
    normalized["player_id"] = normalized["player_id"].astype(str)
    normalized["team"] = normalized["team"].astype(str)
    normalized["position"] = normalized["position"].astype(str).str.upper()
    return {team: team_roster.copy() for team, team_roster in normalized.groupby("team")}


def _flag_series(df: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    col = _first_present(df, aliases)
    if col is None:
        return pd.Series(0, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)


def _first_present(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    for col in aliases:
        if col in df.columns:
            return col
    return None


def _identity_series(
    df: pd.DataFrame,
    primary_col: str | None,
    fallback_col: str | None,
) -> pd.Series:
    if primary_col:
        identity = df[primary_col]
    elif fallback_col:
        identity = df[fallback_col]
    else:
        identity = pd.Series("", index=df.index)

    if fallback_col and fallback_col != primary_col:
        identity = identity.fillna(df[fallback_col])
    return identity.fillna("").astype(str)


def _mapping_float(mapping: Mapping[str, Any], primary: str, fallback: str) -> float:
    value = mapping.get(primary, mapping.get(fallback, 0.0))
    coerced = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return 0.0 if pd.isna(coerced) else float(coerced)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    coerced = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(coerced) else float(coerced)
