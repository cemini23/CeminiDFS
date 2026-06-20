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
        opponent = str(mapped.get("opp") or mapped.get("opponent") or opponent_for_team(vegas, team))
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
