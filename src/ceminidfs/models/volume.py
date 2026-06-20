"""Team play volume projection helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


LEAGUE_SEC_PER_PLAY = 36.2
LEAGUE_TOTAL = 44.8
PLAYS_INTERCEPT = 62.0
BASE_PASS_RATE = 0.565
DEFAULT_SACK_RATE = 0.06
DEFAULT_SCRAMBLE_RATE = 0.08


@dataclass(frozen=True)
class TeamVolumeProjection:
    season: int
    week: int
    team: str
    opponent: str
    game_id: str = ""
    implied_total: float = 0.0
    game_total: float = 0.0
    spread_team: float = 0.0
    team_sec_per_play: float = LEAGUE_SEC_PER_PLAY
    opp_sec_per_play: float = LEAGUE_SEC_PER_PLAY
    neutral_proe: float = 0.0
    plays_projected: float = PLAYS_INTERCEPT
    pass_rate: float = BASE_PASS_RATE
    dropbacks: float = 0.0
    pass_attempts: float = 0.0
    rush_attempts: float = 0.0
    wind_speed_10m_mph: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def neutral_seconds_per_play(pbp: pd.DataFrame, team: str) -> float:
    """Return neutral-script seconds per offensive play for a team."""

    required = {"posteam", "game_seconds_remaining"}
    if pbp.empty or not required.issubset(pbp.columns):
        return LEAGUE_SEC_PER_PLAY

    team_pbp = _neutral_script(pbp)
    team_pbp = team_pbp.loc[team_pbp["posteam"] == team].copy()
    if len(team_pbp) < 2:
        return LEAGUE_SEC_PER_PLAY

    group_cols = [col for col in ("game_id", "drive") if col in team_pbp.columns]
    if group_cols:
        deltas = team_pbp.groupby(group_cols)["game_seconds_remaining"].diff(-1)
    else:
        deltas = team_pbp["game_seconds_remaining"].diff(-1)

    deltas = pd.to_numeric(deltas, errors="coerce")
    valid_deltas = deltas[(deltas > 0) & (deltas <= 120)]
    if valid_deltas.empty:
        return LEAGUE_SEC_PER_PLAY

    return float(valid_deltas.mean())


def neutral_proe(pbp: pd.DataFrame, team: str) -> float:
    """Return a simple neutral-script pass rate over expected proxy."""

    required = {"posteam", "pass", "rush", "xpass"}
    if pbp.empty or not required.issubset(pbp.columns):
        return 0.0

    team_pbp = _neutral_script(pbp)
    team_pbp = team_pbp.loc[team_pbp["posteam"] == team].copy()
    if team_pbp.empty:
        return 0.0

    actual_pass = pd.to_numeric(team_pbp["pass"], errors="coerce")
    actual_rush = pd.to_numeric(team_pbp["rush"], errors="coerce")
    expected_pass = pd.to_numeric(team_pbp["xpass"], errors="coerce")
    valid = actual_pass.notna() & actual_rush.notna() & expected_pass.notna()
    valid &= (actual_pass + actual_rush) > 0
    if not valid.any():
        return 0.0

    return float(((actual_pass[valid] - expected_pass[valid]).mean()) * 100.0)


def projected_plays(
    team_sec: float,
    opp_sec: float,
    total: float,
    *,
    intercept: float = PLAYS_INTERCEPT,
    league_sec: float = LEAGUE_SEC_PER_PLAY,
    league_total: float = LEAGUE_TOTAL,
) -> float:
    """Project offensive plays from team pace, opponent pace, and game total."""

    return (
        intercept
        + (0.5 * (league_sec - team_sec))
        + (0.35 * (league_sec - opp_sec))
        + (0.08 * (total - league_total))
    )


def projected_pass_rate(
    team_spread: float,
    neutral_proe: float = 0.0,
    wind_mph: float | None = None,
    base: float = BASE_PASS_RATE,
) -> float:
    """Project pass rate from PROE, spread, and wind."""

    spread_adj = 0.005 * team_spread
    wind_adj = 0.0
    if wind_mph is not None:
        if wind_mph >= 15:
            wind_adj = -0.03
        elif wind_mph >= 10:
            wind_adj = -0.015

    pass_rate = base + (0.8 * (neutral_proe / 100.0)) + spread_adj + wind_adj
    return max(0.35, min(0.75, pass_rate))


def allocate_play_volume(
    plays: float,
    pass_rate: float,
    sack_rate: float = DEFAULT_SACK_RATE,
    scramble_rate: float = DEFAULT_SCRAMBLE_RATE,
) -> dict[str, float]:
    """Allocate plays into dropbacks, pass attempts, and rush attempts."""

    dropbacks = plays * pass_rate
    scrambles = dropbacks * scramble_rate
    pass_attempts = dropbacks * (1.0 - sack_rate - scramble_rate)
    rush_attempts = plays - dropbacks + scrambles
    return {
        "dropbacks": dropbacks,
        "pass_attempts": pass_attempts,
        "rush_attempts": rush_attempts,
    }


def project_team_volume(
    season: int,
    week: int,
    team: str,
    opponent: str,
    *,
    implied_total: float,
    game_total: float,
    spread_team: float,
    team_sec: float,
    opp_sec: float,
    neutral_proe: float = 0.0,
    wind_mph: float | None = None,
    game_id: str = "",
) -> TeamVolumeProjection:
    """Return a team-level volume projection."""

    plays = projected_plays(team_sec=team_sec, opp_sec=opp_sec, total=game_total)
    pass_rate = projected_pass_rate(
        team_spread=spread_team,
        neutral_proe=neutral_proe,
        wind_mph=wind_mph,
    )
    allocation = allocate_play_volume(plays=plays, pass_rate=pass_rate)

    return TeamVolumeProjection(
        season=season,
        week=week,
        team=team,
        opponent=opponent,
        game_id=game_id,
        implied_total=implied_total,
        game_total=game_total,
        spread_team=spread_team,
        team_sec_per_play=team_sec,
        opp_sec_per_play=opp_sec,
        neutral_proe=neutral_proe,
        plays_projected=plays,
        pass_rate=pass_rate,
        dropbacks=allocation["dropbacks"],
        pass_attempts=allocation["pass_attempts"],
        rush_attempts=allocation["rush_attempts"],
        wind_speed_10m_mph=wind_mph,
    )


def build_week_volume(
    vegas: pd.DataFrame,
    pbp: pd.DataFrame,
    weather: pd.DataFrame | None = None,
    *,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Build one team-volume row per team in each Vegas game row."""

    required = {
        "home_team",
        "away_team",
        "total",
        "spread",
        "home_implied_total",
        "away_implied_total",
    }
    columns = list(TeamVolumeProjection.__dataclass_fields__)
    if vegas.empty or not required.issubset(vegas.columns):
        return pd.DataFrame(columns=columns)

    wind_by_home = _wind_by_home_team(weather)
    teams = set(vegas["home_team"]).union(set(vegas["away_team"]))
    pace_by_team = {team: neutral_seconds_per_play(pbp, team) for team in teams}
    proe_by_team = {team: neutral_proe(pbp, team) for team in teams}

    rows: list[dict[str, Any]] = []
    for _, game in vegas.iterrows():
        home_team = game["home_team"]
        away_team = game["away_team"]
        total = float(game["total"])
        home_spread = float(game["spread"])
        game_id = str(game.get("game_id", ""))
        wind_mph = wind_by_home.get(home_team)

        rows.append(
            project_team_volume(
                season=season,
                week=week,
                team=home_team,
                opponent=away_team,
                implied_total=float(game["home_implied_total"]),
                game_total=total,
                spread_team=home_spread,
                team_sec=pace_by_team[home_team],
                opp_sec=pace_by_team[away_team],
                neutral_proe=proe_by_team[home_team],
                wind_mph=wind_mph,
                game_id=game_id,
            ).to_dict()
        )
        rows.append(
            project_team_volume(
                season=season,
                week=week,
                team=away_team,
                opponent=home_team,
                implied_total=float(game["away_implied_total"]),
                game_total=total,
                spread_team=-home_spread,
                team_sec=pace_by_team[away_team],
                opp_sec=pace_by_team[home_team],
                neutral_proe=proe_by_team[away_team],
                wind_mph=wind_mph,
                game_id=game_id,
            ).to_dict()
        )

    return pd.DataFrame(rows, columns=columns)


def _neutral_script(pbp: pd.DataFrame) -> pd.DataFrame:
    neutral = pbp
    if "wp" in neutral.columns:
        wp = pd.to_numeric(neutral["wp"], errors="coerce")
        neutral = neutral.loc[wp.between(0.2, 0.8)]
    if "qtr" in neutral.columns:
        qtr = pd.to_numeric(neutral["qtr"], errors="coerce")
        neutral = neutral.loc[qtr <= 3]
    return neutral


def _wind_by_home_team(weather: pd.DataFrame | None) -> dict[str, float | None]:
    if weather is None or weather.empty:
        return {}
    if not {"home_team", "wind_speed_10m_mph"}.issubset(weather.columns):
        return {}

    wind: dict[str, float | None] = {}
    for _, row in weather.iterrows():
        value = pd.to_numeric(row["wind_speed_10m_mph"], errors="coerce")
        wind[row["home_team"]] = None if pd.isna(value) else float(value)
    return wind
