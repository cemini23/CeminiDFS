"""Synthetic FanDuel slates from nflverse for offseason pipeline and backtests."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from ceminidfs.pipeline.backtest import (
    _historical_pbp,
    actual_week_fantasy_points,
    load_season_pbp,
    resolve_vegas_for_week,
    roster_from_historical_pbp,
)

FD_HEADERS = ("Id", "Nickname", "Position", "Team", "Opponent", "Salary", "FPPG", "Injury Indicator")

POSITION_SALARY_BANDS: dict[str, tuple[int, int]] = {
    "QB": (6000, 9500),
    "RB": (5000, 9000),
    "WR": (5000, 8800),
    "TE": (4500, 7800),
    "DST": (3500, 5400),
}

DEFAULT_FPPG: dict[str, float] = {
    "QB": 18.0,
    "RB": 10.0,
    "WR": 9.0,
    "TE": 7.0,
    "DST": 7.5,
}


def walk_forward_fppg(pbp: pd.DataFrame, season: int, week: int) -> pd.Series:
    """Mean realized FanDuel points per player using only weeks strictly before ``week``."""

    if pbp.empty or week <= 1:
        return pd.Series(dtype=float)

    frames: list[pd.DataFrame] = []
    for prior_week in range(1, week):
        actuals = actual_week_fantasy_points(pbp, season, prior_week)
        if actuals.empty:
            continue
        frames.append(actuals[["player_id", "fd_actual"]])

    if not frames:
        return pd.Series(dtype=float)

    history = pd.concat(frames, ignore_index=True)
    return history.groupby("player_id", as_index=True)["fd_actual"].mean()


def team_opponents(vegas: pd.DataFrame) -> dict[str, str]:
    """Map each team on the slate to its opponent for the week."""

    opponents: dict[str, str] = {}
    if vegas.empty:
        return opponents

    for _, row in vegas.iterrows():
        home = str(row.get("home_team", "") or "")
        away = str(row.get("away_team", "") or "")
        if home and away:
            opponents[home] = away
            opponents[away] = home
    return opponents


def _normalize_fd_position(position: str) -> str:
    token = str(position or "").strip().upper()
    if token in POSITION_SALARY_BANDS:
        return token
    if token.startswith("QB"):
        return "QB"
    if token.startswith("RB"):
        return "RB"
    if token.startswith("WR"):
        return "WR"
    if token.startswith("TE"):
        return "TE"
    if token in {"DEF", "D", "DST"}:
        return "DST"
    return "WR"


def assign_salaries(frame: pd.DataFrame) -> pd.Series:
    """Assign FanDuel-style salaries from walk-forward FPPG within each position."""

    salaries = pd.Series(0, index=frame.index, dtype=int)
    for position, group in frame.groupby("fd_position", sort=False):
        low, high = POSITION_SALARY_BANDS.get(position, (5000, 8000))
        ordered = group.sort_values("fppg", ascending=False)
        count = len(ordered)
        for rank, idx in enumerate(ordered.index):
            if count == 1:
                salaries.loc[idx] = (low + high) // 2
                continue
            pct = rank / (count - 1)
            value = high - pct * (high - low)
            salaries.loc[idx] = int(round(value / 100.0) * 100)
    return salaries


def build_historical_slate_frame(
    season: int,
    week: int,
    pbp: pd.DataFrame | None = None,
    *,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Build a synthetic main-slate player pool for one historical week."""

    _ = config
    pbp_frame = pbp if pbp is not None else load_season_pbp(season)
    vegas = resolve_vegas_for_week(season, week)
    if vegas.empty:
        return pd.DataFrame(columns=list(FD_HEADERS))

    historical = _historical_pbp(pbp_frame, season, week)
    roster = roster_from_historical_pbp(historical, vegas, season, week)
    if roster.empty:
        return pd.DataFrame(columns=list(FD_HEADERS))

    fppg = walk_forward_fppg(pbp_frame, season, week)
    opponents = team_opponents(vegas)

    rows: list[dict[str, Any]] = []
    for _, player in roster.iterrows():
        player_id = str(player["player_id"])
        position = _normalize_fd_position(str(player.get("position", "")))
        team = str(player.get("team", ""))
        fppg_value = float(fppg.get(player_id, DEFAULT_FPPG.get(position, 8.0)))
        rows.append(
            {
                "Id": player_id,
                "Nickname": str(player.get("player_name", "")),
                "Position": position if position != "DST" else "DEF",
                "Team": team,
                "Opponent": opponents.get(team, ""),
                "Salary": 0,
                "FPPG": round(fppg_value, 2),
                "Injury Indicator": "",
                "fd_position": position,
                "fppg": fppg_value,
            }
        )

    for team in sorted(opponents.keys()):
        rows.append(
            {
                "Id": f"dst_{team.lower()}",
                "Nickname": f"{team} DST",
                "Position": "DEF",
                "Team": team,
                "Opponent": opponents.get(team, ""),
                "Salary": 0,
                "FPPG": DEFAULT_FPPG["DST"],
                "Injury Indicator": "",
                "fd_position": "DST",
                "fppg": DEFAULT_FPPG["DST"],
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=list(FD_HEADERS))

    frame["Salary"] = assign_salaries(frame)
    return frame[list(FD_HEADERS)]


def write_historical_fd_slate(
    season: int,
    week: int,
    path: str | Path,
    *,
    config: Mapping[str, Any] | None = None,
    pbp: pd.DataFrame | None = None,
) -> Path:
    """Write a FanDuel-shaped salary CSV for a historical week."""

    frame = build_historical_slate_frame(season, week, pbp=pbp, config=config)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FD_HEADERS))
        writer.writeheader()
        for _, row in frame.iterrows():
            writer.writerow({key: row[key] for key in FD_HEADERS})
    return out
