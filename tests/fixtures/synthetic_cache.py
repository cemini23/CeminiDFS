from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


SYNTHETIC_PLAYERS: list[dict[str, str]] = [
    {"id": "gsis_mahomes", "name": "Patrick Mahomes", "team": "KC", "position": "QB"},
    {"id": "gsis_allen", "name": "Josh Allen", "team": "BUF", "position": "QB"},
    {"id": "gsis_pacheco", "name": "Isiah Pacheco", "team": "KC", "position": "RB"},
    {"id": "gsis_hunt", "name": "Kareem Hunt", "team": "KC", "position": "RB"},
    {"id": "gsis_ceh", "name": "Clyde Edwards-Helaire", "team": "KC", "position": "RB"},
    {"id": "gsis_perine", "name": "Samaje Perine", "team": "KC", "position": "RB"},
    {"id": "gsis_cook", "name": "James Cook", "team": "BUF", "position": "RB"},
    {"id": "gsis_davis", "name": "Ray Davis", "team": "BUF", "position": "RB"},
    {"id": "gsis_tyjohnson", "name": "Ty Johnson", "team": "BUF", "position": "RB"},
    {"id": "gsis_murray", "name": "Latavius Murray", "team": "BUF", "position": "RB"},
    {"id": "gsis_rice", "name": "Rashee Rice", "team": "KC", "position": "WR"},
    {"id": "gsis_worthy", "name": "Xavier Worthy", "team": "KC", "position": "WR"},
    {"id": "gsis_hollywood", "name": "Marquise Brown", "team": "KC", "position": "WR"},
    {"id": "gsis_watson", "name": "Justin Watson", "team": "KC", "position": "WR"},
    {"id": "gsis_skyy", "name": "Skyy Moore", "team": "KC", "position": "WR"},
    {"id": "gsis_hardman", "name": "Mecole Hardman", "team": "KC", "position": "WR"},
    {"id": "gsis_diggs", "name": "Stefon Diggs", "team": "BUF", "position": "WR"},
    {"id": "gsis_shakir", "name": "Khalil Shakir", "team": "BUF", "position": "WR"},
    {"id": "gsis_samuel", "name": "Curtis Samuel", "team": "BUF", "position": "WR"},
    {"id": "gsis_coleman", "name": "Keon Coleman", "team": "BUF", "position": "WR"},
    {"id": "gsis_hollins", "name": "Mack Hollins", "team": "BUF", "position": "WR"},
    {"id": "gsis_mvs", "name": "Marquez Valdes-Scantling", "team": "BUF", "position": "WR"},
    {"id": "gsis_kelce", "name": "Travis Kelce", "team": "KC", "position": "TE"},
    {"id": "gsis_noahgray", "name": "Noah Gray", "team": "KC", "position": "TE"},
    {"id": "gsis_kincaid", "name": "Dalton Kincaid", "team": "BUF", "position": "TE"},
    {"id": "gsis_knox", "name": "Dawson Knox", "team": "BUF", "position": "TE"},
]


def write_synthetic_week_cache(base_dir: Path, season: int = 2024, week: int = 4) -> Path:
    """Write a KC-BUF cache with historical PBP plus target-week context."""

    week_dir = Path(base_dir) / "cache" / str(season) / f"week_{week}"
    week_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "game_id": f"{season}_{week:02d}_BUF_KC",
                "home_team": "KC",
                "away_team": "BUF",
                "total": 49.5,
                "spread": -2.5,
                "home_implied_total": 26.0,
                "away_implied_total": 23.5,
            }
        ]
    ).to_parquet(week_dir / "vegas.parquet", index=False)
    pd.DataFrame([{"home_team": "KC", "wind_speed_10m_mph": 5.0}]).to_parquet(
        week_dir / "weather.parquet",
        index=False,
    )
    _synthetic_pbp(season, week).to_parquet(week_dir / "pbp.parquet", index=False)
    return week_dir


def _synthetic_pbp(season: int, target_week: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for game_week in range(1, target_week + 1):
        rows.extend(_team_game_rows(season, game_week, "KC", "BUF"))
        rows.extend(_team_game_rows(season, game_week, "BUF", "KC"))
    return pd.DataFrame(rows)


def _team_game_rows(season: int, week: int, team: str, opponent: str) -> list[dict[str, Any]]:
    qb = _players(team, "QB")[0]
    receivers = _players(team, "WR") + _players(team, "TE") + _players(team, "RB")
    rushers = _players(team, "RB")
    rows: list[dict[str, Any]] = []
    game_id = f"{season}_{week:02d}_{team}_{opponent}"

    pass_attempts = 30 if team == "KC" else 32
    for idx in range(pass_attempts):
        receiver = receivers[idx % len(receivers)]
        complete = idx % 5 != 4
        yards = 0 if not complete else 8 + (idx % 6)
        rows.append(
            {
                "season": season,
                "week": week,
                "game_id": game_id,
                "posteam": team,
                "wp": 0.5,
                "qtr": 1 + (idx // 12),
                "game_seconds_remaining": 3600 - (idx * 31),
                "pass": 1,
                "pass_attempt": 1,
                "rush": 0,
                "xpass": 0.61 if team == "KC" else 0.64,
                "passer_player_id": qb["id"],
                "passer_player_name": qb["name"],
                "receiver_player_id": receiver["id"],
                "receiver_player_name": receiver["name"],
                "passing_yards": yards,
                "receiving_yards": yards,
                "passing_tds": 1 if idx in {3, 18} else 0,
                "receiving_tds": 1 if idx in {3, 18} and complete else 0,
                "interceptions": 1 if idx == pass_attempts - 1 and week == 2 else 0,
                "complete_pass": 1 if complete else 0,
                "air_yards": 7 + (idx % 8),
            }
        )

    rush_attempts = 24 if team == "KC" else 22
    for idx in range(rush_attempts):
        rusher = rushers[idx % len(rushers)]
        rows.append(
            {
                "season": season,
                "week": week,
                "game_id": game_id,
                "posteam": team,
                "wp": 0.5,
                "qtr": 2 + (idx // 12),
                "game_seconds_remaining": 2600 - (idx * 32),
                "pass": 0,
                "pass_attempt": 0,
                "rush": 1,
                "xpass": 0.43,
                "rusher_player_id": rusher["id"],
                "rusher_player_name": rusher["name"],
                "rushing_yards": 3 + (idx % 5),
                "rushing_tds": 1 if idx == 7 else 0,
            }
        )
    return rows


def _players(team: str, position: str) -> list[dict[str, str]]:
    return [
        player
        for player in SYNTHETIC_PLAYERS
        if player["team"] == team and player["position"] == position
    ]
