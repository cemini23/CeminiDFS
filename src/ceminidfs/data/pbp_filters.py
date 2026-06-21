"""Play-by-play row filters for EPA-based analytics.

Clean-room policy (K125 brief, 2026-06-21): align with nflverse/nflfastR scrimmage
play conventions. Inspired by public descriptions of playmaking-EPA attribution
(danmorse314/nfl-stuff, null license — no R code copied). CeminiDFS applies
team-level EPA filters only; player-level half-sack credit is out of scope.
"""

from __future__ import annotations

import pandas as pd

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


def epa_eligible_plays(pbp: pd.DataFrame) -> pd.DataFrame:
    """Return scrimmage pass/rush rows with non-null EPA suitable for team defense ratings."""

    if pbp.empty:
        return pbp

    frame = pbp.copy()
    if "epa" not in frame.columns:
        return frame.iloc[0:0].copy()

    epa = pd.to_numeric(frame["epa"], errors="coerce")
    frame = frame.loc[epa.notna()]

    scrimmage = _scrimmage_mask(frame)
    frame = frame.loc[scrimmage]
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
    pass_flag = _flag(frame, ("pass", "pass_attempt"))
    rush_flag = _flag(frame, ("rush", "rush_attempt"))
    if pass_flag.eq(0).all() and rush_flag.eq(0).all() and "play_type" in frame.columns:
        play_type = frame["play_type"].astype(str).str.lower()
        return play_type.isin({"pass", "run"})
    return pass_flag.eq(1) | rush_flag.eq(1)


def _flag(df: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    for name in names:
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce").fillna(0)
    return pd.Series(0, index=df.index)
