"""Point-in-time row filters. A target week never sees itself."""

from __future__ import annotations

import pandas as pd


def cut_point_in_time(
    frame: pd.DataFrame | None,
    *,
    season: int,
    week: int,
    season_col: str = "season",
    week_col: str = "week",
) -> pd.DataFrame:
    """Return rows strictly before ``season``/``week``.

    Week 0 is dropped. NGS uses week 0 as a season aggregate, and a season
    aggregate includes games that have not been played yet.

    A row is kept only when its season is earlier than the target season, or
    its season equals the target season and its week is greater than 0 and
    less than the target week.
    """

    if frame is None:
        return pd.DataFrame()
    if frame.empty:
        return frame.copy()
    if season_col not in frame.columns or week_col not in frame.columns:
        raise ValueError(f"frame needs {season_col!r} and {week_col!r}")

    seasons = pd.to_numeric(frame[season_col], errors="coerce")
    weeks = pd.to_numeric(frame[week_col], errors="coerce")
    keep = seasons.notna() & weeks.notna() & (weeks > 0) & (
        (seasons < int(season)) | ((seasons == int(season)) & (weeks < int(week)))
    )
    cut = frame.loc[keep].copy()
    _assert_no_lookahead(cut, season=int(season), week=int(week), season_col=season_col, week_col=week_col)
    return cut


def _assert_no_lookahead(
    frame: pd.DataFrame,
    *,
    season: int,
    week: int,
    season_col: str,
    week_col: str,
) -> None:
    if frame.empty:
        return
    seasons = pd.to_numeric(frame[season_col], errors="coerce")
    weeks = pd.to_numeric(frame[week_col], errors="coerce")
    leaked = (
        seasons.isna()
        | weeks.isna()
        | (weeks <= 0)
        | (seasons > season)
        | ((seasons == season) & (weeks >= week))
    )
    if bool(leaked.any()):
        raise RuntimeError(
            f"point-in-time cutoff leaked {int(leaked.sum())} rows "
            f"for season {season} week {week}"
        )
