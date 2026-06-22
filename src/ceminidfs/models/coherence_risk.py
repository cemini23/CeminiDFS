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

    qb_penalty = output["pass_protection_penalty"].map(
        lambda excess: _bounded_penalty(
            excess,
            settings.pass_protection.qb_yds_penalty,
            settings.pass_protection.max_penalty,
        )
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
    if settings.pass_protection.enabled:
        stress_by_team = build_team_pass_protection_stress(pbp, through_week, settings=settings)
        adjusted_stats = apply_pass_protection_penalties(adjusted_stats, stress_by_team, settings)
    return adjusted_usage, adjusted_stats


def coherence_variance_multiplier(row: Mapping[str, Any], settings: CoherenceRiskSettings) -> float:
    """Return a simulation CV multiplier for rows flagged by coherence risk."""

    sim_settings = settings.sim_variance
    if not sim_settings.enabled:
        return 1.0

    flag = _truthy(row.get("coherence_risk_flag", False))
    stress = _row_float(row, "pass_protection_stress", default=1.0)
    if flag or stress >= sim_settings.stress_flag_threshold:
        return sim_settings.high_risk_cv_multiplier
    return 1.0


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
