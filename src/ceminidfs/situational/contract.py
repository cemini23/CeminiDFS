"""Column contracts for the situational feature tables."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# FanDuel uses LAR. The cached play-by-play uses LA for the Rams.
TEAM_ALIASES = {
    "LA": "LAR",
    "JAC": "JAX",
    "WSH": "WAS",
    "ARZ": "ARI",
}

PLAYER_ID_COLUMNS = ("player_id", "player_name", "team", "position")

PLAYER_RATE_COLUMNS = (
    "games",
    "pass_yds_per_game",
    "rush_yds_per_game",
    "rec_yds_per_game",
    "targets_per_game",
    "carries_per_game",
    "receptions_per_game",
    "pass_att_per_game",
    "pass_td_per_game",
    "rush_td_per_game",
    "rec_td_per_game",
    "int_per_game",
    "fumbles_per_game",
    "q3_td_share",
    "q3_rz_touch_share",
    "q4_trail_target_share",
    "q4_trail_carry_share",
    "explosive_rec_rate",
    "explosive_rush_rate",
    "inside10_target_share",
    "inside5_carry_share",
    "team_q3_opening_epa",
    "team_q3_opening_proe",
    "team_rz_td_rate",
    "team_between_20_epa",
    "team_q4_trail_pass_share",
    "team_no_huddle_rate",
    "avg_separation",
    "avg_cushion",
    "air_yards_share",
    "avg_intended_air_yards",
    "avg_yac_above_expectation",
    "cpoe",
    "avg_time_to_throw",
    "ryoe",
    "play_action_target_share",
    "motion_target_share",
    "qb_fault_sack_rate",
    "int_worthy_rate",
    "fd_points_per_game",
    "trail4_opps",
)

PLAYER_COLUMNS = PLAYER_ID_COLUMNS + PLAYER_RATE_COLUMNS

DEFENSE_COLUMNS = (
    "team",
    "plays",
    "def_q3_epa",
    "def_1h_epa",
    "def_q3_slow_start",
    "def_q4_dropback_epa",
    "def_q4_yac",
    "def_explosive_comp_rate",
    "def_q4_comp_rate",
    "def_light_box_rate",
    "def_rz_td_rate",
    "def_sack_rate",
    "def_to_rate",
    "lagged_fd",
)

SKILL_FEATURES = (
    "q3_td_share",
    "q3_rz_touch_share",
    "q3_script",
    "q4_trail_target_share",
    "q4_bringback",
    "avg_separation",
    "avg_yac_above_expectation",
    "cpoe",
    "air_yards_share",
    "avg_intended_air_yards",
    "explosive_rec_rate",
    "explosive_align",
    "ryoe",
    "explosive_rush_rate",
    "rush_light_box",
    "inside10_target_share",
    "rz_funnel",
    "team_no_huddle_rate",
    "play_action_target_share",
    "motion_target_share",
)

DST_FEATURES = (
    "opp_avg_time_to_throw",
    "opp_int_worthy_rate",
    "opp_qb_fault_sack_rate",
    "opp_q4_trail_pass_share",
    "def_sack_rate",
    "def_to_rate",
    "pressure_mismatch",
)

COUNTING_COLUMNS = (
    "targets",
    "receptions",
    "rec_yds",
    "rec_td",
    "q3_rec_td",
    "rz_targets",
    "q3_rz_targets",
    "q4_trail_targets",
    "explosive_recs",
    "inside10_targets",
    "pa_known",
    "pa_sum",
    "motion_known",
    "motion_sum",
    "carries",
    "rush_yds",
    "rush_td",
    "q3_rush_td",
    "rz_carries",
    "q3_rz_carries",
    "q4_trail_carries",
    "explosive_rushes",
    "inside5_carries",
    "pass_att",
    "pass_yds",
    "pass_td",
    "q3_pass_td",
    "interceptions",
    "fumbles_lost",
    "sacks_taken",
    "qb_fault_known",
    "qb_fault_sum",
    "int_worthy_known",
    "int_worthy_sum",
    "games",
)


def canon_team(value: object) -> str:
    """Return the FanDuel team code for a play-by-play abbreviation."""

    text = str(value).strip().upper()
    if text in {"", "NAN", "NONE", "NAT"}:
        return ""
    return TEAM_ALIASES.get(text, text)


def canon_teams(values: pd.Series) -> pd.Series:
    """Map a team column onto FanDuel abbreviations. Missing values stay missing."""

    mapped = values.map(canon_team)
    return mapped.where(values.notna(), values)


@dataclass
class FeatureTables:
    """Lagged player and defense tables for one target week."""

    players: pd.DataFrame
    defense: pd.DataFrame
    audit: dict


@dataclass
class HistoryGrains:
    """Player-week and team-week counts before any target-week cutoff."""

    players: pd.DataFrame
    offense: pd.DataFrame
    defense: pd.DataFrame
    ngs_receiving: pd.DataFrame
    ngs_passing: pd.DataFrame
    ngs_rushing: pd.DataFrame
    slate_sizes: pd.DataFrame
