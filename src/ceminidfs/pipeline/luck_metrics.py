"""Team expected-wins and luck metrics for MME calibration context (K129).

Inspired by fantasy-football-wrapped Pythagorean expected wins — clean-room from schedules.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from ceminidfs.data.fetch import fetch_schedules

PYTH_EXPONENT = 2.37


def _completed_games(schedules: pd.DataFrame, through_week: int) -> pd.DataFrame:
    if schedules.empty:
        return schedules
    if "week" not in schedules.columns:
        return pd.DataFrame()
    frame = schedules[schedules["week"] <= through_week].copy()
    if "home_score" not in frame.columns or "away_score" not in frame.columns:
        return pd.DataFrame()
    completed = frame[
        frame["home_score"].notna()
        & frame["away_score"].notna()
        & (frame["home_score"] >= 0)
        & (frame["away_score"] >= 0)
    ].copy()
    return completed


def team_game_rows(schedules: pd.DataFrame, through_week: int) -> pd.DataFrame:
    """Expand completed games into per-team rows with points for/against."""

    games = _completed_games(schedules, through_week)
    if games.empty:
        return pd.DataFrame(
            columns=["team", "week", "points_for", "points_against", "win"]
        )

    rows: list[dict[str, Any]] = []
    for _, game in games.iterrows():
        week = int(game.get("week", 0))
        home = str(game.get("home_team", "")).strip()
        away = str(game.get("away_team", "")).strip()
        home_score = float(game["home_score"])
        away_score = float(game["away_score"])
        if not home or not away:
            continue
        home_win = 1 if home_score > away_score else 0
        away_win = 1 if away_score > home_score else 0
        rows.append(
            {
                "team": home,
                "week": week,
                "points_for": home_score,
                "points_against": away_score,
                "win": home_win,
            }
        )
        rows.append(
            {
                "team": away,
                "week": week,
                "points_for": away_score,
                "points_against": home_score,
                "win": away_win,
            }
        )
    return pd.DataFrame(rows)


def pythagorean_expected_wins(
    points_for: float,
    points_against: float,
    games: int,
    *,
    exponent: float = PYTH_EXPONENT,
) -> float:
    if games <= 0:
        return 0.0
    if points_for <= 0 and points_against <= 0:
        return 0.0
    pf_exp = points_for**exponent
    pa_exp = points_against**exponent
    if pf_exp + pa_exp <= 0:
        return 0.0
    return games * pf_exp / (pf_exp + pa_exp)


def compute_team_luck_table(
    season: int,
    through_week: int,
    *,
    schedules: pd.DataFrame | None = None,
    exponent: float = PYTH_EXPONENT,
) -> pd.DataFrame:
    """Aggregate team luck: actual wins minus Pythagorean expected wins."""

    sched = schedules if schedules is not None else fetch_schedules(season)
    games = team_game_rows(sched, through_week)
    if games.empty:
        return pd.DataFrame(
            columns=[
                "team",
                "games",
                "wins",
                "points_for",
                "points_against",
                "expected_wins",
                "luck",
            ]
        )

    grouped = games.groupby("team", as_index=False).agg(
        games=("win", "count"),
        wins=("win", "sum"),
        points_for=("points_for", "sum"),
        points_against=("points_against", "sum"),
    )
    grouped["expected_wins"] = grouped.apply(
        lambda row: pythagorean_expected_wins(
            float(row["points_for"]),
            float(row["points_against"]),
            int(row["games"]),
            exponent=exponent,
        ),
        axis=1,
    )
    grouped["luck"] = grouped["wins"] - grouped["expected_wins"]
    grouped = grouped.sort_values("luck", ascending=False).reset_index(drop=True)
    return grouped


def summarize_luck_metrics(
    season: int,
    through_week: int,
    *,
    schedules: pd.DataFrame | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return JSON-serializable luck summary for CLI / calibration reports."""

    luck_cfg = (config or {}).get("luck_metrics", {})
    exponent = float(luck_cfg.get("pyth_exponent", PYTH_EXPONENT)) if isinstance(
        luck_cfg, Mapping
    ) else PYTH_EXPONENT

    table = compute_team_luck_table(
        season,
        through_week,
        schedules=schedules,
        exponent=exponent,
    )
    if table.empty:
        return {
            "season": season,
            "through_week": through_week,
            "teams": 0,
            "luckiest": [],
            "unluckiest": [],
        }

    luckiest = table.head(5).to_dict(orient="records")
    unluckiest = table.tail(5).sort_values("luck").to_dict(orient="records")
    return {
        "season": season,
        "through_week": through_week,
        "teams": int(len(table)),
        "mean_luck": float(table["luck"].mean()),
        "luckiest": luckiest,
        "unluckiest": unluckiest,
        "table": table.to_dict(orient="records"),
    }
