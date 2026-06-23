"""Clean-room coherence-risk adjustments derived from nflverse play-by-play."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from ceminidfs.models.coherence_settings import CoherenceRiskSettings

EXCLUDED_PLAY_TYPES = frozenset(
    {
        "no_play",
        "qb_kneel",
        "qb_spike",
        "extra_point",
        "two_point_conversion",
        "field_goal",
        "kickoff",
        "punt",
        "pat",
        "xp",
    }
)
FOURTH_DOWN_EXCLUDED_PLAY_TYPES = EXCLUDED_PLAY_TYPES - {"field_goal", "punt"}
SKILL_POSITIONS = frozenset({"RB", "WR", "TE"})


def build_team_pass_protection_stress(
    pbp: pd.DataFrame,
    through_week: int,
    *,
    settings: CoherenceRiskSettings,
) -> dict[str, float]:
    """Return team-level dropback stress indices versus league average."""

    _ = settings
    historical = _historical_scrimmage(pbp, through_week)
    if historical.empty or "posteam" not in historical.columns:
        return {}

    dropback_mask = _dropback_mask(historical)
    dropbacks = historical.loc[dropback_mask].copy()
    if dropbacks.empty:
        return {}

    dropbacks["team"] = dropbacks["posteam"].fillna("").astype(str)
    dropbacks = dropbacks.loc[dropbacks["team"] != ""]
    if dropbacks.empty:
        return {}

    dropbacks["sack_flag"] = _flag(dropbacks, ("sack",)).clip(lower=0.0, upper=1.0)
    dropbacks["qb_hit_flag"] = _flag(dropbacks, ("qb_hit",)).clip(lower=0.0, upper=1.0)

    grouped = dropbacks.groupby("team", as_index=False).agg(
        dropbacks=("team", "size"),
        sacks=("sack_flag", "sum"),
        qb_hits=("qb_hit_flag", "sum"),
    )
    grouped["stress_raw"] = (grouped["sacks"] + grouped["qb_hits"]) / grouped["dropbacks"].clip(lower=1.0)

    league_dropbacks = float(len(dropbacks))
    league_raw = float((dropbacks["sack_flag"].sum() + dropbacks["qb_hit_flag"].sum()) / league_dropbacks)
    if league_raw <= 0:
        return {str(row["team"]): 1.0 for _, row in grouped.iterrows()}

    return {
        str(row["team"]): float(row["stress_raw"]) / league_raw
        for _, row in grouped.iterrows()
        if str(row["team"])
    }


def build_team_red_zone_run_tendency(
    pbp: pd.DataFrame,
    through_week: int,
    *,
    settings: CoherenceRiskSettings,
) -> dict[str, float]:
    """Return team red-zone run-share indices versus league average."""

    _ = settings
    historical = _historical_scrimmage(pbp, through_week)
    if historical.empty or "posteam" not in historical.columns:
        return {}

    yardline_100 = _yardline_100(historical)
    historical = historical.loc[yardline_100.le(20)].copy()
    if historical.empty:
        return {}

    historical["team"] = historical["posteam"].fillna("").astype(str)
    historical = historical.loc[historical["team"] != ""]
    if historical.empty:
        return {}

    historical["pass_flag"] = _pass_flag(historical).clip(lower=0.0, upper=1.0)
    historical["rush_flag"] = _rush_flag(historical).clip(lower=0.0, upper=1.0)
    historical = historical.loc[(historical["pass_flag"] + historical["rush_flag"]) > 0]
    if historical.empty:
        return {}

    grouped = historical.groupby("team", as_index=False).agg(
        rz_passes=("pass_flag", "sum"),
        rz_rushes=("rush_flag", "sum"),
    )
    grouped["rz_total"] = grouped["rz_passes"] + grouped["rz_rushes"]
    grouped = grouped.loc[grouped["rz_total"] > 0]
    if grouped.empty:
        return {}

    grouped["rz_run_share"] = grouped["rz_rushes"] / grouped["rz_total"]
    league_rushes = float(grouped["rz_rushes"].sum())
    league_total = float(grouped["rz_total"].sum())
    league_share = league_rushes / league_total if league_total > 0 else 0.0
    if league_share <= 0:
        return {str(row["team"]): 1.0 for _, row in grouped.iterrows()}

    return {
        str(row["team"]): float(row["rz_run_share"]) / league_share
        for _, row in grouped.iterrows()
        if str(row["team"])
    }


def build_team_fourth_down_aggressiveness(
    pbp: pd.DataFrame,
    through_week: int,
    *,
    settings: CoherenceRiskSettings,
) -> dict[str, float]:
    """Return team fourth-down go-rate indices versus league average."""

    _ = settings
    historical = _historical_fourth_down(pbp, through_week)
    if historical.empty or "posteam" not in historical.columns:
        return {}

    historical["team"] = historical["posteam"].fillna("").astype(str)
    historical = historical.loc[historical["team"] != ""].copy()
    if historical.empty:
        return {}

    historical["go_flag"] = _scrimmage_mask(historical).astype(float)
    grouped = historical.groupby("team", as_index=False).agg(
        fourth_downs=("team", "size"),
        go_attempts=("go_flag", "sum"),
    )
    grouped = grouped.loc[grouped["fourth_downs"] > 0].copy()
    if grouped.empty:
        return {}

    grouped["go_rate"] = grouped["go_attempts"] / grouped["fourth_downs"]
    league_rate = float(grouped["go_attempts"].sum() / grouped["fourth_downs"].sum())
    if league_rate <= 0:
        return {str(row["team"]): 1.0 for _, row in grouped.iterrows()}

    return {
        str(row["team"]): float(row["go_rate"]) / league_rate
        for _, row in grouped.iterrows()
        if str(row["team"])
    }


def build_player_workload_index(
    pbp: pd.DataFrame,
    through_week: int,
    *,
    settings: CoherenceRiskSettings,
) -> dict[str, float]:
    """Return player rolling workload z-scores versus same-position pools."""

    if pbp.empty:
        return {}

    from ceminidfs.models.usage import assign_inferred_positions, player_game_stats_from_pbp

    player_games = player_game_stats_from_pbp(pbp)
    if player_games.empty or "player_id" not in player_games.columns or "week" not in player_games.columns:
        return {}

    player_games = player_games.loc[
        pd.to_numeric(player_games["week"], errors="coerce") < through_week
    ].copy()
    if player_games.empty:
        return {}

    player_games = assign_inferred_positions(player_games)
    player_games["position"] = player_games.get("position", "").fillna("").astype(str).str.upper()
    player_games = player_games.loc[player_games["position"].isin(SKILL_POSITIONS)].copy()
    if player_games.empty:
        return {}

    player_games["workload"] = (
        pd.to_numeric(player_games.get("targets", 0.0), errors="coerce").fillna(0.0)
        + pd.to_numeric(player_games.get("carries", 0.0), errors="coerce").fillna(0.0)
    )
    recent_window = max(int(settings.workload.rolling_weeks), 1)
    recent = (
        player_games.sort_values(["player_id", "week", "game_id"])
        .groupby("player_id", group_keys=False)
        .tail(recent_window)
    )
    if recent.empty:
        return {}

    player_recent = recent.groupby("player_id", as_index=False).agg(
        position=("position", "last"),
        workload=("workload", "mean"),
    )
    pool = player_recent.groupby("position")["workload"].agg(["mean", "std"]).to_dict("index")

    index_by_player: dict[str, float] = {}
    for _, row in player_recent.iterrows():
        player_id = str(row["player_id"])
        position = str(row["position"])
        stats = pool.get(position) or {}
        std = float(stats.get("std") or 0.0)
        if std <= 0:
            index_by_player[player_id] = 0.0
            continue
        index_by_player[player_id] = (float(row["workload"]) - float(stats.get("mean") or 0.0)) / std
    return index_by_player


def apply_pass_protection_penalties(
    stats_df: pd.DataFrame,
    stress_by_team: Mapping[str, float],
    settings: CoherenceRiskSettings,
) -> pd.DataFrame:
    """Downshift QB passing and WR/TE receiving yards for stressed offenses."""

    if stats_df.empty:
        return stats_df.copy()

    output = stats_df.copy()
    threshold = settings.pass_protection.stress_threshold
    output["pass_protection_stress"] = output.get("team", pd.Series("", index=output.index)).map(
        lambda team: float(stress_by_team.get(str(team), 1.0))
    )
    output["pass_protection_penalty"] = output["pass_protection_stress"].map(
        lambda value: _index_excess(value, threshold)
    )
    risk_mask = output["pass_protection_stress"].ge(threshold)
    existing_flag = _truthy_series(output.get("coherence_risk_flag", pd.Series(False, index=output.index)))
    output["coherence_risk_flag"] = existing_flag | risk_mask

    qb_mask = output.get("position", pd.Series("", index=output.index)).astype(str).str.upper().eq("QB")
    wr_te_mask = (
        output.get("position", pd.Series("", index=output.index)).astype(str).str.upper().isin({"WR", "TE"})
    )

    qb_penalty_scale = settings.pass_protection.qb_yds_penalty_scale
    qb_penalty = output["pass_protection_penalty"].map(
        lambda excess: _bounded_penalty(
            excess,
            settings.pass_protection.qb_yds_penalty,
            settings.pass_protection.max_penalty,
        )
        * qb_penalty_scale
    )
    recv_penalty = output["pass_protection_penalty"].map(
        lambda excess: _bounded_penalty(
            excess,
            settings.pass_protection.recv_yds_penalty,
            settings.pass_protection.max_penalty,
        )
    )

    if "pass_yds" in output.columns:
        output.loc[qb_mask, "pass_yds"] = (
            pd.to_numeric(output.loc[qb_mask, "pass_yds"], errors="coerce").fillna(0.0)
            * (1.0 - qb_penalty.loc[qb_mask])
        )
    if "rec_yds" in output.columns:
        output.loc[wr_te_mask, "rec_yds"] = (
            pd.to_numeric(output.loc[wr_te_mask, "rec_yds"], errors="coerce").fillna(0.0)
            * (1.0 - recv_penalty.loc[wr_te_mask])
        )
    return output


def apply_fourth_down_aggressiveness_adjustments(
    usage_df: pd.DataFrame,
    aggression_by_team: Mapping[str, float],
    settings: CoherenceRiskSettings,
) -> pd.DataFrame:
    """Slightly boost passing usage for offenses that go for it more often."""

    if usage_df.empty:
        return usage_df.copy()

    output = usage_df.copy()
    threshold = settings.fourth_down.aggression_threshold
    output["fourth_down_aggressiveness"] = output.get(
        "team", pd.Series("", index=output.index)
    ).map(lambda team: float(aggression_by_team.get(str(team), 1.0)))
    output["fourth_down_excess"] = output["fourth_down_aggressiveness"].map(
        lambda value: _index_excess(value, threshold)
    )

    position = output.get("position", pd.Series("", index=output.index)).astype(str).str.upper()
    qb_mask = position.eq("QB")
    skill_mask = position.isin(SKILL_POSITIONS)

    if "projected_pass_attempts" in output.columns:
        output.loc[qb_mask, "projected_pass_attempts"] = (
            pd.to_numeric(output.loc[qb_mask, "projected_pass_attempts"], errors="coerce").fillna(0.0)
            * (
                1.0
                + settings.fourth_down.pass_attempt_boost
                * output.loc[qb_mask, "fourth_down_excess"]
            )
        )
    if "projected_targets" in output.columns:
        output.loc[skill_mask, "projected_targets"] = (
            pd.to_numeric(output.loc[skill_mask, "projected_targets"], errors="coerce").fillna(0.0)
            * (
                1.0
                + settings.fourth_down.target_boost
                * output.loc[skill_mask, "fourth_down_excess"]
            )
        )
    return output


def apply_workload_risk_flags(
    frame: pd.DataFrame,
    workload_by_player: Mapping[str, float],
    settings: CoherenceRiskSettings,
) -> pd.DataFrame:
    """Attach workload z-score and high-workload risk flags to player rows."""

    if frame.empty:
        return frame.copy()

    output = frame.copy()
    output["workload_index"] = output.get("player_id", pd.Series("", index=output.index)).map(
        lambda player_id: float(workload_by_player.get(str(player_id), 0.0))
    )
    position = output.get("position", pd.Series("", index=output.index)).astype(str).str.upper()
    high_workload = position.isin(SKILL_POSITIONS) & output["workload_index"].ge(
        settings.workload.z_threshold
    )
    existing_flag = _truthy_series(output.get("workload_risk_flag", pd.Series(False, index=output.index)))
    output["workload_risk_flag"] = existing_flag | high_workload
    return output


def apply_red_zone_usage_adjustments(
    usage_df: pd.DataFrame,
    rz_by_team: Mapping[str, float],
    settings: CoherenceRiskSettings,
) -> pd.DataFrame:
    """Tilt usage toward RB carries and TE targets for run-heavy red-zone teams."""

    if usage_df.empty:
        return usage_df.copy()

    output = usage_df.copy()
    threshold = settings.red_zone_playcall.run_tendency_threshold
    output["rz_run_index"] = output.get("team", pd.Series("", index=output.index)).map(
        lambda team: float(rz_by_team.get(str(team), 1.0))
    )
    output["rz_run_excess"] = output["rz_run_index"].map(lambda value: _index_excess(value, threshold))

    position = output.get("position", pd.Series("", index=output.index)).astype(str).str.upper()
    rb_mask = position.eq("RB")
    te_mask = position.eq("TE")
    wr_mask = position.eq("WR")

    if "projected_carries" in output.columns:
        output.loc[rb_mask, "projected_carries"] = (
            pd.to_numeric(output.loc[rb_mask, "projected_carries"], errors="coerce").fillna(0.0)
            * (1.0 + (settings.red_zone_playcall.rb_carry_boost * output.loc[rb_mask, "rz_run_excess"]))
        )
    if "projected_targets" in output.columns:
        output.loc[te_mask, "projected_targets"] = (
            pd.to_numeric(output.loc[te_mask, "projected_targets"], errors="coerce").fillna(0.0)
            * (1.0 + (settings.red_zone_playcall.te_target_boost * output.loc[te_mask, "rz_run_excess"]))
        )
        output.loc[wr_mask, "projected_targets"] = (
            pd.to_numeric(output.loc[wr_mask, "projected_targets"], errors="coerce").fillna(0.0)
            * (1.0 - (settings.red_zone_playcall.wr_target_trim * output.loc[wr_mask, "rz_run_excess"]))
        ).clip(lower=0.0)
    return output


def apply_coherence_risk(
    usage_df: pd.DataFrame,
    stats_df: pd.DataFrame,
    pbp: pd.DataFrame,
    through_week: int,
    config: Mapping[str, Any] | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply both coherence-risk prototypes using the provided config."""

    settings = CoherenceRiskSettings.from_config(config)
    if not settings.enabled:
        return usage_df.copy(), stats_df.copy()

    adjusted_usage = usage_df.copy()
    adjusted_stats = stats_df.copy()
    if settings.red_zone_playcall.enabled:
        rz_by_team = build_team_red_zone_run_tendency(pbp, through_week, settings=settings)
        adjusted_usage = apply_red_zone_usage_adjustments(adjusted_usage, rz_by_team, settings)
    if settings.fourth_down.enabled:
        aggression_by_team = build_team_fourth_down_aggressiveness(
            pbp, through_week, settings=settings
        )
        adjusted_usage = apply_fourth_down_aggressiveness_adjustments(
            adjusted_usage, aggression_by_team, settings
        )
    if settings.workload.enabled:
        workload_by_player = build_player_workload_index(pbp, through_week, settings=settings)
        adjusted_usage = apply_workload_risk_flags(adjusted_usage, workload_by_player, settings)
        adjusted_stats = apply_workload_risk_flags(adjusted_stats, workload_by_player, settings)
    if settings.pass_protection.enabled:
        stress_by_team = build_team_pass_protection_stress(pbp, through_week, settings=settings)
        adjusted_stats = apply_pass_protection_penalties(adjusted_stats, stress_by_team, settings)
    return adjusted_usage, adjusted_stats


def coherence_variance_multiplier(row: Mapping[str, Any], settings: CoherenceRiskSettings) -> float:
    """Return a simulation CV multiplier for rows flagged by coherence risk."""

    if not settings.enabled:
        return 1.0

    sim_settings = settings.sim_variance
    multiplier = 1.0

    flag = _truthy(row.get("coherence_risk_flag", False))
    stress = _row_float(row, "pass_protection_stress", default=1.0)
    if sim_settings.enabled and (flag or stress >= sim_settings.stress_flag_threshold):
        multiplier = max(multiplier, sim_settings.high_risk_cv_multiplier)

    workload_flag = _truthy(row.get("workload_risk_flag", False))
    workload_index = _row_float(row, "workload_index", default=0.0)
    if settings.workload.enabled and (
        workload_flag or workload_index >= settings.workload.z_threshold
    ):
        multiplier = max(multiplier, settings.workload.high_risk_cv_multiplier)
    return multiplier


def _historical_fourth_down(pbp: pd.DataFrame, through_week: int) -> pd.DataFrame:
    if pbp.empty or "week" not in pbp.columns or "down" not in pbp.columns:
        return pd.DataFrame()

    frame = pbp.copy()
    frame = frame.loc[pd.to_numeric(frame["week"], errors="coerce") < through_week].copy()
    if frame.empty:
        return frame

    frame = frame.loc[pd.to_numeric(frame["down"], errors="coerce").eq(4)].copy()
    if frame.empty:
        return frame

    if "play_type" in frame.columns:
        play_type = frame["play_type"].astype(str).str.lower()
        frame = frame.loc[~play_type.isin(FOURTH_DOWN_EXCLUDED_PLAY_TYPES)]
    if "desc" in frame.columns:
        desc = frame["desc"].astype(str)
        frame = frame.loc[~desc.str.startswith("Penalty", na=False)]
    return frame.reset_index(drop=True)


def _historical_scrimmage(pbp: pd.DataFrame, through_week: int) -> pd.DataFrame:
    if pbp.empty or "week" not in pbp.columns:
        return pd.DataFrame()

    frame = pbp.copy()
    frame = frame.loc[pd.to_numeric(frame["week"], errors="coerce") < through_week].copy()
    if frame.empty:
        return frame

    scrimmage = _scrimmage_mask(frame)
    frame = frame.loc[scrimmage].copy()
    if frame.empty:
        return frame

    if "play_type" in frame.columns:
        play_type = frame["play_type"].astype(str).str.lower()
        frame = frame.loc[~play_type.isin(EXCLUDED_PLAY_TYPES)]
    if "desc" in frame.columns:
        desc = frame["desc"].astype(str)
        frame = frame.loc[~desc.str.startswith("Penalty", na=False)]
    return frame.reset_index(drop=True)


def _scrimmage_mask(frame: pd.DataFrame) -> pd.Series:
    pass_flag = _pass_flag(frame)
    rush_flag = _rush_flag(frame)
    sack_flag = _flag(frame, ("sack",))
    if (
        pass_flag.eq(0).all()
        and rush_flag.eq(0).all()
        and sack_flag.eq(0).all()
        and "play_type" in frame.columns
    ):
        play_type = frame["play_type"].astype(str).str.lower()
        return play_type.isin({"pass", "run"})
    return pass_flag.eq(1) | rush_flag.eq(1) | sack_flag.eq(1)


def _dropback_mask(frame: pd.DataFrame) -> pd.Series:
    return _pass_flag(frame).eq(1) | _flag(frame, ("sack",)).eq(1)


def _pass_flag(df: pd.DataFrame) -> pd.Series:
    return _flag(df, ("pass_attempt", "pass"))


def _rush_flag(df: pd.DataFrame) -> pd.Series:
    return _flag(df, ("rush_attempt", "rush"))


def _flag(df: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    for name in names:
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=df.index, dtype=float)


def _yardline_100(df: pd.DataFrame) -> pd.Series:
    if "yardline_100" in df.columns:
        return pd.to_numeric(df["yardline_100"], errors="coerce")
    if "yrdln" not in df.columns:
        return pd.Series(float("nan"), index=df.index, dtype=float)
    return df.apply(_parse_yrdln, axis=1)


def _parse_yrdln(row: pd.Series) -> float:
    raw = str(row.get("yrdln", "") or "").strip()
    if not raw:
        return float("nan")
    parts = raw.split()
    if len(parts) != 2:
        return float("nan")
    side, yard_text = parts
    try:
        yard = float(yard_text)
    except ValueError:
        return float("nan")
    posteam = str(row.get("posteam", "") or "").strip().upper()
    side = side.strip().upper()
    if not posteam:
        return float("nan")
    return yard if side == posteam else 100.0 - yard


def _index_excess(index_value: float, threshold: float) -> float:
    margin = max(abs(float(threshold) - 1.0), 1e-6)
    excess = max(0.0, float(index_value) - float(threshold)) / margin
    return min(excess, 1.0)


def _bounded_penalty(excess: float, rate: float, max_penalty: float) -> float:
    return min(float(max_penalty), max(0.0, float(rate) * float(excess)))


def _truthy_series(values: pd.Series) -> pd.Series:
    return values.map(_truthy)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y"}


def _row_float(row: Mapping[str, Any], key: str, *, default: float = 0.0) -> float:
    value = pd.to_numeric(pd.Series([row.get(key, default)]), errors="coerce").iloc[0]
    return default if pd.isna(value) else float(value)
