"""Pre-game context for one slate.

Referee DPI and holding z-scores use games before the target week.
A blank slate referee is filled from the latest prior home-team crew.
Week score columns are not written.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ceminidfs.data.fetch import _cache_dir
from ceminidfs.situational.contract import canon_teams

CONTEXT_COLUMNS = (
    "game_id",
    "season",
    "week",
    "home_team",
    "away_team",
    "roof",
    "surface",
    "temp",
    "wind",
    "spread_line",
    "total_line",
    "referee",
    "referee_dpi_z",
    "referee_holding_z",
)
MIN_CREW_GAMES = 8


def build_game_context(
    season: int,
    week: int,
    *,
    seasons: tuple[int, ...] = (2023, 2024, 2025, 2026),
    cache_dir: Path | None = None,
) -> tuple[pd.DataFrame, int]:
    """Return week games plus lagged crew z-scores, and the max source week."""

    root = cache_dir or _cache_dir()
    schedules = _read_schedules(root, seasons)
    if schedules.empty:
        return pd.DataFrame(columns=list(CONTEXT_COLUMNS)), 0
    prior = _before(schedules, season, week)
    max_week = int(pd.to_numeric(prior["week"], errors="coerce").max()) if not prior.empty else 0
    crews = _crew_rates(prior, root, seasons, season, week)
    slate = schedules.loc[
        (pd.to_numeric(schedules["season"], errors="coerce") == int(season))
        & (pd.to_numeric(schedules["week"], errors="coerce") == int(week))
    ].copy()
    if slate.empty:
        return pd.DataFrame(columns=list(CONTEXT_COLUMNS)), max_week
    slate["referee"] = _fallback_referee(slate, prior)
    slate["referee"] = [_clean_referee(value) for value in slate["referee"]]
    slate = slate.merge(crews, on="referee", how="left")
    for column in CONTEXT_COLUMNS:
        if column not in slate.columns:
            slate[column] = np.nan
    out = slate.loc[:, list(CONTEXT_COLUMNS)].sort_values(["game_id"], kind="mergesort")
    return out.reset_index(drop=True), max_week


def _read_schedules(root: Path, seasons: tuple[int, ...]) -> pd.DataFrame:
    frames = []
    for season in seasons:
        path = root / f"schedules_{int(season)}.parquet"
        if not path.is_file():
            continue
        frames.append(pd.read_parquet(path))
    if not frames:
        return pd.DataFrame()
    schedules = pd.concat(frames, ignore_index=True)
    for column in ("home_team", "away_team"):
        if column in schedules.columns:
            schedules[column] = canon_teams(schedules[column])
    return schedules


def _before(frame: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    season_n = pd.to_numeric(frame["season"], errors="coerce")
    week_n = pd.to_numeric(frame["week"], errors="coerce")
    keep = (season_n < int(season)) | ((season_n == int(season)) & (week_n < int(week)) & (week_n > 0))
    return frame.loc[keep].copy()


def _fallback_referee(slate: pd.DataFrame, prior: pd.DataFrame) -> pd.Series:
    """Fill a blank referee from the latest prior home-team crew."""

    if "referee" not in slate.columns:
        current = pd.Series("", index=slate.index, dtype=object)
    else:
        current = slate["referee"].copy()
    blank = current.map(_is_blank_referee)
    if not bool(blank.any()):
        return current
    if (
        prior.empty
        or "referee" not in prior.columns
        or "home_team" not in prior.columns
        or "home_team" not in slate.columns
    ):
        return current
    history = prior.loc[:, ["season", "week", "home_team", "referee"]].copy()
    history = history.loc[~history["referee"].map(_is_blank_referee)].copy()
    if history.empty:
        return current
    history["_season"] = pd.to_numeric(history["season"], errors="coerce").fillna(-1)
    history["_week"] = pd.to_numeric(history["week"], errors="coerce").fillna(-1)
    history = history.sort_values(["home_team", "_season", "_week"], kind="mergesort")
    latest = history.groupby("home_team", sort=False).tail(1)
    mapping = {
        str(team): _clean_referee(name)
        for team, name in zip(latest["home_team"], latest["referee"], strict=True)
    }
    filled = current.astype(object).copy()
    for idx in slate.index[blank.to_numpy()]:
        name = mapping.get(str(slate.at[idx, "home_team"]), "")
        if name:
            filled.at[idx] = name
    return filled


def _is_blank_referee(value: object) -> bool:
    if value is None:
        return True
    try:
        if bool(pd.isna(value)):
            return True
    except (TypeError, ValueError):
        return False
    text = str(value).strip().lower()
    return text in {"", "nan", "none", "<na>"}


def _clean_referee(value: object) -> str:
    if _is_blank_referee(value):
        return ""
    return str(value).strip()


def _crew_rates(
    schedules: pd.DataFrame,
    root: Path,
    seasons: tuple[int, ...],
    season: int,
    week: int,
) -> pd.DataFrame:
    empty = pd.DataFrame(columns=["referee", "referee_dpi_z", "referee_holding_z"])
    if schedules.empty or "referee" not in schedules.columns or "game_id" not in schedules.columns:
        return empty
    crews = schedules.loc[~schedules["referee"].map(_is_blank_referee), ["game_id", "referee"]].copy()
    crews["referee"] = crews["referee"].map(_clean_referee)
    penalties = _penalty_counts(root, seasons, season, week)
    if penalties.empty:
        return empty
    merged = penalties.merge(crews, on="game_id", how="inner")
    if merged.empty:
        return empty
    totals = merged.groupby("referee", as_index=False).agg(
        games=("game_id", "nunique"),
        dpi=("dpi", "sum"),
        holding=("holding", "sum"),
    )
    totals = totals.loc[totals["games"] >= MIN_CREW_GAMES].copy()
    if totals.empty:
        return empty
    totals["dpi_rate"] = totals["dpi"] / totals["games"]
    totals["holding_rate"] = totals["holding"] / totals["games"]
    totals["referee_dpi_z"] = _z(totals["dpi_rate"])
    totals["referee_holding_z"] = _z(totals["holding_rate"])
    return totals[["referee", "referee_dpi_z", "referee_holding_z"]]


def _penalty_counts(root: Path, seasons: tuple[int, ...], season: int, week: int) -> pd.DataFrame:
    frames = []
    columns = ["game_id", "season", "week", "penalty_type"]
    for item in seasons:
        path = root / f"pbp_{int(item)}.parquet"
        if not path.is_file():
            continue
        frame = pd.read_parquet(path, columns=[column for column in columns if column])
        have = [column for column in columns if column in frame.columns]
        if "penalty_type" not in have or "game_id" not in have:
            continue
        part = frame.loc[:, have].copy()
        part = _before(part, season, week)
        if part.empty:
            continue
        text = part["penalty_type"].astype(str)
        part["dpi"] = text.eq("Defensive Pass Interference").astype(float)
        part["holding"] = text.isin(["Offensive Holding", "Defensive Holding"]).astype(float)
        frames.append(part.groupby("game_id", as_index=False)[["dpi", "holding"]].sum())
    if not frames:
        return pd.DataFrame(columns=["game_id", "dpi", "holding"])
    return pd.concat(frames, ignore_index=True)


def _z(values: pd.Series) -> pd.Series:
    std = float(values.std(ddof=1))
    if not np.isfinite(std) or std < 1e-8:
        return pd.Series(0.0, index=values.index)
    return (values - float(values.mean())) / std
