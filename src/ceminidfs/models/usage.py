"""Player usage projection helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import pandas as pd

from ceminidfs.models.volume import DEFAULT_SACK_RATE, DEFAULT_SCRAMBLE_RATE


LEAGUE_TARGET_SHARE = {"WR": 0.18, "TE": 0.12, "RB": 0.08}
LEAGUE_CARRY_SHARE = {"RB": 0.35}
LEAGUE_QB_CARRY_SHARE = 0.12
LEAGUE_RB_COMMITTEE_SIZE = 3
LEAGUE_RB_CARRY_PRIORS = (0.35, 0.12, 0.04)
LEAGUE_RB_TARGET_PRIORS = (0.08, 0.05, 0.03)
DEFAULT_SHARE_WEIGHTS = (0.5, 0.3, 0.2)
MIN_L3_QB_PASS_ATTEMPTS = 10
MIN_LAST_WEEK_QB_PASS_ATTEMPTS = 18
MIN_BACKUP_QB_SEASON_ATTEMPTS = 15
MIN_BACKUP_QB_L3_ATTEMPTS = 5
QB_BACKUP_PASS_SHARE = 0.05
QB_IMPLIED_PASS_BOOST = 0.012
QB_IMPLIED_PASS_BASELINE = 22.0


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


def infer_player_position(
    pass_attempts: float,
    carries: float,
    targets: float,
    *,
    fallback: str = "",
) -> str:
    """Infer skill position from usage totals when roster labels are missing."""

    fallback_pos = str(fallback or "").strip().upper()
    if pass_attempts >= max(carries, targets) and pass_attempts >= 5:
        return "QB"
    if carries >= targets and carries >= 5:
        return "RB"
    if targets >= 3:
        if fallback_pos in {"TE", "WR", "RB", "QB"}:
            return fallback_pos
        return "WR"
    if fallback_pos:
        return fallback_pos
    if pass_attempts > 0:
        return "QB"
    if carries > 0:
        return "RB"
    return "WR"


def assign_inferred_positions(stats: pd.DataFrame) -> pd.DataFrame:
    """Attach inferred positions to player-game usage rows."""

    if stats.empty or "player_id" not in stats.columns:
        return stats

    totals = stats.groupby("player_id", as_index=False).agg(
        pass_attempts=("pass_attempts", "sum"),
        carries=("carries", "sum"),
        targets=("targets", "sum"),
        position=("position", "last"),
    )
    totals["inferred"] = totals.apply(
        lambda row: infer_player_position(
            float(row["pass_attempts"]),
            float(row["carries"]),
            float(row["targets"]),
            fallback=str(row.get("position", "") or ""),
        ),
        axis=1,
    )
    mapping = totals.set_index("player_id")["inferred"]
    enriched = stats.copy()
    enriched["position"] = enriched["player_id"].map(mapping).fillna(enriched.get("position", ""))
    return enriched


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
    group_cols = ["season", "week", "team", "game_id", "player_id", "player_name"]
    result = (
        stats.groupby(group_cols, dropna=False, as_index=False)[
            ["targets", "air_yards", "carries", "pass_attempts"]
        ]
        .sum()
    )
    result["position"] = ""
    result = result.reindex(columns=columns)
    return assign_inferred_positions(result)


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
    """Return the team's likely starting QB by recent or season pass attempts."""

    required = {"team", "week", "player_id", "pass_attempts"}
    if stats.empty or not required.issubset(stats.columns):
        return None

    team_stats = stats.loc[
        (stats["team"] == team)
        & (pd.to_numeric(stats["week"], errors="coerce") < through_week)
    ].copy()
    if team_stats.empty:
        return None

    prior_week = through_week - 1
    if prior_week >= 1:
        last_week = team_stats.loc[pd.to_numeric(team_stats["week"], errors="coerce") == prior_week]
        if not last_week.empty:
            recent_leader = last_week.groupby("player_id", as_index=False)["pass_attempts"].sum()
            recent_leader = recent_leader.sort_values("pass_attempts", ascending=False)
            if (
                not recent_leader.empty
                and float(recent_leader.iloc[0]["pass_attempts"]) >= MIN_LAST_WEEK_QB_PASS_ATTEMPTS
            ):
                return str(recent_leader.iloc[0]["player_id"])

    recent = team_stats.loc[pd.to_numeric(team_stats["week"], errors="coerce") >= through_week - 3]
    if not recent.empty:
        l3 = recent.groupby("player_id", as_index=False)["pass_attempts"].sum()
        l3 = l3.sort_values("pass_attempts", ascending=False)
        if not l3.empty and float(l3.iloc[0]["pass_attempts"]) >= MIN_L3_QB_PASS_ATTEMPTS:
            return str(l3.iloc[0]["player_id"])

    season = team_stats.groupby("player_id", as_index=False)["pass_attempts"].sum()
    season = season.sort_values("pass_attempts", ascending=False)
    if season.empty or float(season.iloc[0]["pass_attempts"]) <= 0:
        return None
    return str(season.iloc[0]["player_id"])


def _identify_qb_backup(
    stats: pd.DataFrame,
    team: str,
    through_week: int,
    starter_id: str | None,
) -> str | None:
    """Return the team's secondary QB by season pass attempts when distinct from starter."""

    required = {"team", "week", "player_id", "pass_attempts"}
    if stats.empty or not required.issubset(stats.columns):
        return None

    team_stats = stats.loc[
        (stats["team"] == team)
        & (pd.to_numeric(stats["week"], errors="coerce") < through_week)
    ].copy()
    if team_stats.empty:
        return None

    season = team_stats.groupby("player_id", as_index=False)["pass_attempts"].sum()
    season = season.sort_values("pass_attempts", ascending=False)
    if len(season) < 2:
        return None

    backup = str(season.iloc[1]["player_id"])
    if starter_id and backup == starter_id:
        return None
    if float(season.iloc[1]["pass_attempts"]) < MIN_BACKUP_QB_SEASON_ATTEMPTS:
        return None

    recent = team_stats.loc[pd.to_numeric(team_stats["week"], errors="coerce") >= through_week - 3]
    if not recent.empty:
        l3 = recent.groupby("player_id", as_index=False)["pass_attempts"].sum()
        backup_row = l3.loc[l3["player_id"] == backup]
        if backup_row.empty or float(backup_row.iloc[0]["pass_attempts"]) < MIN_BACKUP_QB_L3_ATTEMPTS:
            return None
    return backup


def project_player_usage(
    volume_row: Mapping[str, Any],
    player_shares: Mapping[str, Any],
    *,
    position: str,
) -> PlayerUsageProjection:
    """Project a player's usage from team volume and blended shares."""

    pos = str(position or player_shares.get("position", "") or "").upper()
    if player_shares.get("is_qb_starter") and pos != "QB":
        pos = "QB"
    carry_share = float(player_shares["carry_share_override"]) if "carry_share_override" in player_shares else weighted_blend(
        _mapping_float(player_shares, "l3_carry_share", "carry_share"),
        _mapping_float(player_shares, "season_carry_share", "carry_share"),
        LEAGUE_CARRY_SHARE.get(pos, 0.0),
    )
    if "target_share_override" in player_shares:
        target_share = float(player_shares["target_share_override"])
        air_yards_share = float(player_shares.get("air_yards_share_override", target_share))
    else:
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
    pass_attempts = float(volume_row.get("pass_attempts", 0.0) or 0.0)
    rush_attempts = float(volume_row.get("rush_attempts", 0.0) or 0.0)
    rush_pool = float(volume_row.get("rb_rush_attempts", rush_attempts) if pos == "RB" else rush_attempts)
    projected_pass_attempts = 0.0
    projected_carries = carry_share * rush_pool
    if pos == "QB" and player_shares.get("is_qb_starter"):
        implied = float(volume_row.get("implied_total", 0.0) or 0.0)
        volume_scale = 1.0 + QB_IMPLIED_PASS_BOOST * max(0.0, implied - QB_IMPLIED_PASS_BASELINE)
        projected_pass_attempts = pass_attempts * volume_scale
        qb_carry_share = weighted_blend(
            _mapping_float(player_shares, "l3_carry_share", "carry_share"),
            _mapping_float(player_shares, "season_carry_share", "carry_share"),
            LEAGUE_QB_CARRY_SHARE,
        )
        dropback_est = projected_pass_attempts / max(1.0 - DEFAULT_SACK_RATE - DEFAULT_SCRAMBLE_RATE, 0.5)
        scramble_carries = dropback_est * DEFAULT_SCRAMBLE_RATE
        designed_rush = float(player_shares.get("qb_rush_per_game", 0.0) or 0.0)
        projected_carries = max(
            projected_carries,
            qb_carry_share * rush_attempts,
            scramble_carries,
            designed_rush,
        )
    elif pos == "QB" and player_shares.get("is_qb_backup"):
        projected_pass_attempts = pass_attempts * QB_BACKUP_PASS_SHARE

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
        projected_carries=projected_carries,
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
        backup_id = _identify_qb_backup(stats, team=team, through_week=week, starter_id=starter_id)
        volume_dict = volume_row.to_dict()
        volume_dict["rb_rush_attempts"] = _rb_rush_pool(volume_dict)
        _assign_rb_committee_shares(share_records)
        _enrich_qb_player_context(share_records, stats, team=team, through_week=week)

        for player in share_records:
            player_id = str(player.get("player_id", ""))
            player["is_qb_starter"] = bool(starter_id and player_id == starter_id)
            player["is_qb_backup"] = bool(backup_id and player_id == backup_id)
            projection = project_player_usage(
                volume_dict,
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

    pool["position"] = pool["position"].fillna("").astype(str).str.upper()
    empty = pool["position"].eq("")
    if empty.any() and "position_hist" in pool.columns:
        pool.loc[empty, "position"] = pool.loc[empty, "position_hist"].fillna("").astype(str).str.upper()

    return pool.fillna({col: 0.0 for col in share_cols}).to_dict("records")


def _enrich_qb_player_context(
    share_records: list[dict[str, Any]],
    stats: pd.DataFrame,
    *,
    team: str,
    through_week: int,
) -> None:
    """Attach per-game designed rush baselines for QBs on a team."""

    if stats.empty or "week" not in stats.columns:
        return

    team_stats = stats.loc[
        (stats["team"] == team)
        & (pd.to_numeric(stats["week"], errors="coerce") < through_week)
    ].copy()
    if team_stats.empty:
        return

    for player in share_records:
        if str(player.get("position", "")).upper() != "QB":
            continue
        player_id = str(player.get("player_id", ""))
        player_stats = team_stats.loc[team_stats["player_id"].astype(str) == player_id]
        if player_stats.empty:
            player["qb_rush_per_game"] = 0.0
            continue
        games = int(pd.to_numeric(player_stats["week"], errors="coerce").nunique())
        carries = float(pd.to_numeric(player_stats["carries"], errors="coerce").fillna(0.0).sum())
        player["qb_rush_per_game"] = carries / max(games, 1)


def _rb_rush_pool(volume_row: Mapping[str, Any]) -> float:
    """Rush attempts available to RBs after reserving QB scrambles."""

    rush_attempts = float(volume_row.get("rush_attempts", 0.0) or 0.0)
    pass_attempts = float(volume_row.get("pass_attempts", 0.0) or 0.0)
    dropback_est = pass_attempts / max(1.0 - DEFAULT_SACK_RATE - DEFAULT_SCRAMBLE_RATE, 0.5)
    qb_scrambles = dropback_est * DEFAULT_SCRAMBLE_RATE
    return max(rush_attempts - qb_scrambles, rush_attempts * 0.70)


def _assign_rb_committee_shares(share_records: list[dict[str, Any]]) -> None:
    """Normalize top-N RB carry/target shares so backups do not inflate the team pool."""

    rbs = [player for player in share_records if str(player.get("position", "")).upper() == "RB"]
    if not rbs:
        return

    ranked = sorted(
        rbs,
        key=lambda player: (
            _mapping_float(player, "season_carry_share", "l3_carry_share"),
            _mapping_float(player, "l3_carry_share", "season_carry_share"),
            _mapping_float(player, "season_target_share", "l3_target_share"),
        ),
        reverse=True,
    )
    committee = ranked[:LEAGUE_RB_COMMITTEE_SIZE]
    for rank, player in enumerate(committee):
        carry_prior = LEAGUE_RB_CARRY_PRIORS[min(rank, len(LEAGUE_RB_CARRY_PRIORS) - 1)]
        target_prior = LEAGUE_RB_TARGET_PRIORS[min(rank, len(LEAGUE_RB_TARGET_PRIORS) - 1)]
        player["carry_share_override"] = weighted_blend(
            _mapping_float(player, "l3_carry_share", "carry_share"),
            _mapping_float(player, "season_carry_share", "carry_share"),
            carry_prior,
        )
        player["target_share_override"] = weighted_blend(
            _mapping_float(player, "l3_target_share", "target_share"),
            _mapping_float(player, "season_target_share", "target_share"),
            target_prior,
        )
        player["air_yards_share_override"] = weighted_blend(
            _mapping_float(player, "l3_air_yards_share", "air_yards_share"),
            _mapping_float(player, "season_air_yards_share", "air_yards_share"),
            target_prior,
        )

    committee_ids = {player.get("player_id") for player in committee}
    for player in rbs:
        if player.get("player_id") not in committee_ids:
            player["carry_share_override"] = 0.0
            player["target_share_override"] = 0.0
            player["air_yards_share_override"] = 0.0

    carry_total = sum(float(player.get("carry_share_override", 0.0)) for player in committee)
    if carry_total > 1.0:
        for player in committee:
            player["carry_share_override"] = float(player["carry_share_override"]) / carry_total

    target_total = sum(float(player.get("target_share_override", 0.0)) for player in committee)
    if target_total > 1.0:
        for player in committee:
            player["target_share_override"] = float(player["target_share_override"]) / target_total
            player["air_yards_share_override"] = float(player.get("air_yards_share_override", 0.0)) / target_total


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
