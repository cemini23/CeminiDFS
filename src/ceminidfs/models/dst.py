"""Team defense (DST/DEF) projection helpers."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from ceminidfs.models.scoring import fd_dst_points_allowed

LEAGUE_SACKS_PER_GAME = 2.4
LEAGUE_INTERCEPTIONS_PER_GAME = 0.85
LEAGUE_FUMBLE_RECOVERIES = 0.55
LEAGUE_DEF_TD = 0.12


def project_dst_fantasy_points(
    *,
    team: str,
    opponent: str,
    opponent_implied_total: float,
    opponent_pass_rate: float | None = None,
) -> tuple[float, float]:
    """Project FanDuel/DraftKings DST points from opponent implied scoring and event priors."""

    del team, opponent
    implied = max(0.0, float(opponent_implied_total))
    pass_rate = 0.565 if opponent_pass_rate is None else float(opponent_pass_rate)
    pass_rate = max(0.35, min(0.75, pass_rate))

    pa_points = fd_dst_points_allowed(implied)
    event_points = (
        LEAGUE_SACKS_PER_GAME * 1.0
        + LEAGUE_INTERCEPTIONS_PER_GAME * 2.0
        + LEAGUE_FUMBLE_RECOVERIES * 2.0
        + LEAGUE_DEF_TD * 6.0
    )
    # Pass-heavy offenses create slightly more sack/INT opportunity.
    event_points *= 0.95 + (0.1 * pass_rate)

    fd = pa_points + event_points
    dk = fd  # event + PA tiers align closely enough for v1
    return max(0.0, fd), max(0.0, dk)


def implied_total_for_team(vegas: pd.DataFrame, team: str) -> float | None:
    """Look up a team's implied total from enriched schedule/vegas rows."""

    if vegas.empty:
        return None
    team = str(team).strip().upper()
    for _, row in vegas.iterrows():
        home = str(row.get("home_team", "")).strip().upper()
        away = str(row.get("away_team", "")).strip().upper()
        if team == home:
            value = row.get("home_implied_total", row.get("home_total"))
            return _to_float(value)
        if team == away:
            value = row.get("away_implied_total", row.get("away_total"))
            return _to_float(value)
    return None


def opponent_for_team(vegas: pd.DataFrame, team: str) -> str:
    team = str(team).strip().upper()
    for _, row in vegas.iterrows():
        home = str(row.get("home_team", "")).strip().upper()
        away = str(row.get("away_team", "")).strip().upper()
        if team == home:
            return away
        if team == away:
            return home
    return ""


def apply_dst_projections(
    rows: list[dict[str, Any]],
    vegas: pd.DataFrame,
    *,
    config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Fill DST/DEF rows with model projections when vegas context is available."""

    cfg = dict(config or {}).get("dst", {})
    if not isinstance(cfg, Mapping):
        cfg = {}

    output: list[dict[str, Any]] = []
    for row in rows:
        mapped = dict(row)
        if not _is_dst_row(mapped):
            output.append(mapped)
            continue

        team = str(mapped.get("team") or "").strip().upper()
        opponent = str(
            mapped.get("opp") or mapped.get("opponent") or opponent_for_team(vegas, team)
        )
        implied = implied_total_for_team(vegas, opponent) if opponent else None
        if implied is None:
            mapped["projection_source"] = mapped.get("projection_source") or "dst_fppg_fallback"
            output.append(mapped)
            continue

        fd, dk = project_dst_fantasy_points(
            team=team,
            opponent=opponent,
            opponent_implied_total=implied,
        )
        mapped["fd_projection"] = fd
        mapped["dk_projection"] = dk
        mapped["projection_source"] = "dst_model"
        if opponent:
            mapped.setdefault("opp", opponent)
        output.append(mapped)

    return output


def _is_dst_row(row: Mapping[str, Any]) -> bool:
    for key in ("fd_position", "dk_position", "position"):
        value = str(row.get(key, "")).strip().upper()
        if value in {"DEF", "DST", "D"}:
            return True
    return False


def _to_float(value: Any) -> float | None:
    coerced = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(coerced):
        return None
    return float(coerced)


def teams_on_slate(vegas: pd.DataFrame) -> list[str]:
    """Return sorted home/away teams present on a weekly vegas frame."""

    if vegas.empty:
        return []
    teams: set[str] = set()
    for _, row in vegas.iterrows():
        home = str(row.get("home_team", "") or "").strip().upper()
        away = str(row.get("away_team", "") or "").strip().upper()
        if home:
            teams.add(home)
        if away:
            teams.add(away)
    return sorted(teams)


def build_week_dst_projections(
    vegas: pd.DataFrame,
    volume_df: pd.DataFrame,
    *,
    season: int,
    week: int,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Return one DST projection row per team on the weekly slate."""

    _ = config
    columns = [
        "season",
        "week",
        "team",
        "opponent",
        "player_id",
        "player_name",
        "position",
        "fd_projection",
        "dk_projection",
    ]
    if vegas.empty:
        return pd.DataFrame(columns=columns)

    pass_rate_by_team: dict[str, float] = {}
    if not volume_df.empty and {"team", "pass_attempts", "rush_attempts"}.issubset(
        volume_df.columns
    ):
        scoped = volume_df.loc[
            (pd.to_numeric(volume_df.get("season", season), errors="coerce") == season)
            & (pd.to_numeric(volume_df.get("week", week), errors="coerce") == week)
        ]
        for _, row in scoped.iterrows():
            team = str(row.get("team", "") or "").strip().upper()
            passes = float(row.get("pass_attempts", 0.0) or 0.0)
            rushes = float(row.get("rush_attempts", 0.0) or 0.0)
            plays = passes + rushes
            if team and plays > 0:
                pass_rate_by_team[team] = passes / plays

    rows: list[dict[str, Any]] = []
    for team in teams_on_slate(vegas):
        opponent = opponent_for_team(vegas, team)
        implied = implied_total_for_team(vegas, opponent) if opponent else None
        if implied is None:
            continue
        fd, dk = project_dst_fantasy_points(
            team=team,
            opponent=opponent,
            opponent_implied_total=implied,
            opponent_pass_rate=pass_rate_by_team.get(opponent),
        )
        rows.append(
            {
                "season": season,
                "week": week,
                "team": team,
                "opponent": opponent,
                "player_id": f"dst_{team.lower()}",
                "player_name": f"{team} DST",
                "position": "DST",
                "fd_projection": fd,
                "dk_projection": dk,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def actual_dst_fantasy_points(
    pbp: pd.DataFrame,
    season: int,
    week: int,
    vegas: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Aggregate realized FanDuel DST points for teams on the weekly slate."""

    columns = ["player_id", "player_name", "team", "position", "fd_actual", "dk_actual"]
    if pbp.empty or "week" not in pbp.columns:
        return pd.DataFrame(columns=columns)

    week_pbp = pbp.loc[pd.to_numeric(pbp["week"], errors="coerce") == week].copy()
    if "season" in week_pbp.columns:
        week_pbp = week_pbp.loc[
            pd.to_numeric(week_pbp["season"], errors="coerce").fillna(season) == season
        ]
    if week_pbp.empty:
        return pd.DataFrame(columns=columns)

    teams = (
        teams_on_slate(vegas)
        if vegas is not None and not vegas.empty
        else _teams_from_pbp(week_pbp)
    )
    if not teams:
        return pd.DataFrame(columns=columns)

    game_scores = _game_scores(week_pbp)
    rows: list[dict[str, Any]] = []
    for team in teams:
        opponent = opponent_for_team(vegas, team) if vegas is not None else ""
        points_allowed = _points_allowed_for_team(team, opponent, game_scores)
        events = _defensive_events(week_pbp, team)
        fd = fd_dst_points_allowed(points_allowed) + _dst_event_points(events)
        rows.append(
            {
                "player_id": f"dst_{team.lower()}",
                "player_name": f"{team} DST",
                "team": team,
                "position": "DST",
                "fd_actual": max(0.0, fd),
                "dk_actual": max(0.0, fd),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _teams_from_pbp(pbp: pd.DataFrame) -> list[str]:
    teams: set[str] = set()
    for column in ("home_team", "away_team", "posteam", "defteam"):
        if column in pbp.columns:
            teams.update(
                str(value).strip().upper() for value in pbp[column].dropna() if str(value).strip()
            )
    return sorted(team for team in teams if team and team != "NAN")


def _game_scores(pbp: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if "game_id" not in pbp.columns:
        return {}
    scores: dict[str, dict[str, Any]] = {}
    grouped = pbp.groupby("game_id", dropna=False)
    for game_id, frame in grouped:
        home = str(frame.get("home_team", pd.Series([""])).iloc[0] or "").strip().upper()
        away = str(frame.get("away_team", pd.Series([""])).iloc[0] or "").strip().upper()
        home_score = _max_numeric(frame, ("total_home_score", "home_score", "score_home"))
        away_score = _max_numeric(frame, ("total_away_score", "away_score", "score_away"))
        scores[str(game_id)] = {
            "home_team": home,
            "away_team": away,
            "home_score": home_score,
            "away_score": away_score,
        }
    return scores


def _points_allowed_for_team(
    team: str,
    opponent: str,
    game_scores: Mapping[str, Mapping[str, Any]],
) -> float:
    team = team.strip().upper()
    opponent = opponent.strip().upper()
    for payload in game_scores.values():
        home = str(payload.get("home_team", "") or "").strip().upper()
        away = str(payload.get("away_team", "") or "").strip().upper()
        if team == home and (not opponent or opponent == away):
            return float(payload.get("away_score", 0.0) or 0.0)
        if team == away and (not opponent or opponent == home):
            return float(payload.get("home_score", 0.0) or 0.0)
    return 0.0


def _defensive_events(pbp: pd.DataFrame, team: str) -> dict[str, float]:
    if "defteam" not in pbp.columns:
        return {
            "sacks": 0.0,
            "interceptions": 0.0,
            "fumbles_recovered": 0.0,
            "def_tds": 0.0,
            "safeties": 0.0,
        }
    defense = pbp.loc[pbp["defteam"].astype(str).str.upper().eq(team.strip().upper())]
    if defense.empty:
        return {
            "sacks": 0.0,
            "interceptions": 0.0,
            "fumbles_recovered": 0.0,
            "def_tds": 0.0,
            "safeties": 0.0,
        }
    return {
        "sacks": _sum_flag(defense, ("sack",)),
        "interceptions": _sum_flag(defense, ("interception",)),
        "fumbles_recovered": _sum_fumble_recoveries(defense, team),
        "def_tds": _sum_def_touchdowns(defense),
        "safeties": _sum_flag(defense, ("safety",)),
    }


def _dst_event_points(events: Mapping[str, float]) -> float:
    return (
        float(events.get("sacks", 0.0)) * 1.0
        + float(events.get("interceptions", 0.0)) * 2.0
        + float(events.get("fumbles_recovered", 0.0)) * 2.0
        + float(events.get("def_tds", 0.0)) * 6.0
        + float(events.get("safeties", 0.0)) * 2.0
    )


def _sum_flag(frame: pd.DataFrame, columns: tuple[str, ...]) -> float:
    total = 0.0
    for column in columns:
        if column not in frame.columns:
            continue
        total += float(pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(bool).sum())
    return total


def _sum_fumble_recoveries(frame: pd.DataFrame, team: str) -> float:
    team = team.strip().upper()
    for column in ("fumble_recovery_1_team", "fumble_recovery_2_team"):
        if column in frame.columns:
            return float(frame[column].astype(str).str.upper().eq(team).sum())
    if "fumble_lost" in frame.columns:
        return float(pd.to_numeric(frame["fumble_lost"], errors="coerce").fillna(0).sum())
    return 0.0


def _sum_def_touchdowns(frame: pd.DataFrame) -> float:
    if "touchdown" not in frame.columns:
        return 0.0
    mask = pd.to_numeric(frame["touchdown"], errors="coerce").fillna(0).astype(bool)
    if "return_touchdown" in frame.columns:
        mask &= pd.to_numeric(frame["return_touchdown"], errors="coerce").fillna(0).astype(bool)
    return float(mask.sum())


def _max_numeric(frame: pd.DataFrame, columns: tuple[str, ...]) -> float:
    for column in columns:
        if column in frame.columns:
            value = pd.to_numeric(frame[column], errors="coerce").max()
            if pd.notna(value):
                return float(value)
    return 0.0
