import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.defense import build_defense_ratings, defense_multiplier
from ceminidfs.models.stats import project_player_stats


def test_build_defense_ratings_boosts_offense_vs_weak_pass_defense():
    pbp = _pbp_with_defense()
    ratings = build_defense_ratings(pbp, through_week=4, alpha=0.2)

    assert ratings["BUF"]["pass"] > 1.0
    assert ratings["KC"]["pass"] < 1.0


def test_project_player_stats_applies_opponent_multiplier():
    pbp = _pbp_with_defense()
    ratings = build_defense_ratings(pbp, through_week=4, alpha=0.2)
    efficiency = {
        "ypa": 7.0,
        "td_rate": 0.05,
        "int_rate": 0.02,
        "ypc": 4.0,
        "td_per_carry": 0.03,
    }

    neutral = project_player_stats(
        _usage("BUF"),
        efficiency,
        week=4,
        defense_ratings={"BUF": {"pass": 1.0, "rush": 1.0}},
    )
    boosted = project_player_stats(_usage("BUF"), efficiency, week=4, defense_ratings=ratings)

    assert boosted.pass_yds > neutral.pass_yds
    assert defense_multiplier("BUF", "pass", ratings) > 1.0


def _usage(opponent: str) -> dict[str, object]:
    return {
        "season": 2024,
        "week": 4,
        "team": "KC",
        "opponent": opponent,
        "player_id": "qb1",
        "player_name": "QB One",
        "position": "QB",
        "projected_pass_attempts": 30.0,
        "projected_carries": 2.0,
        "projected_targets": 0.0,
    }


def _pbp_with_defense() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for week in (1, 2, 3):
        for idx in range(20):
            rows.append(
                {
                    "season": 2024,
                    "week": week,
                    "game_id": f"g{week}",
                    "posteam": "KC",
                    "defteam": "BUF",
                    "pass_attempt": 1,
                    "rush": 0,
                    "epa": 0.25,
                    "passing_yards": 8,
                }
            )
        for idx in range(20):
            rows.append(
                {
                    "season": 2024,
                    "week": week,
                    "game_id": f"g{week}b",
                    "posteam": "BUF",
                    "defteam": "KC",
                    "pass_attempt": 1,
                    "rush": 0,
                    "epa": -0.05,
                    "passing_yards": 4,
                }
            )
    return pd.DataFrame(rows)
