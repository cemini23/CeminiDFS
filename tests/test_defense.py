import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.defense import (
    DEFENSE_MULTIPLIER_CLAMP,
    build_defense_ratings,
    defense_multiplier,
)
from ceminidfs.models.stats import project_player_stats


def test_build_defense_ratings_returns_rush_for_every_team():
    """A negative league rush EPA must not skip the rush side."""

    pbp = _pbp_both_sides()
    ratings = build_defense_ratings(pbp, through_week=4)

    assert ratings
    for team, team_ratings in ratings.items():
        assert "rush" in team_ratings, f"{team} has no rush rating"
        assert "pass" in team_ratings, f"{team} has no pass rating"


def test_rush_multiplier_separates_good_and_bad_defenses():
    """The best rush defense is below 1.0 and the worst is above 1.0."""

    pbp = _rush_epa_frame({"TEAM_A": 0.2, "TEAM_B": 0.0, "TEAM_C": -0.2})
    ratings = build_defense_ratings(pbp, through_week=4)

    best = ratings["TEAM_C"]["rush"]
    worst = ratings["TEAM_A"]["rush"]
    assert best < 1.0
    assert worst > 1.0
    assert worst - best > 0.05


def test_defense_multiplier_stays_inside_clamp():
    """Every produced multiplier stays inside the configured clamp."""

    low, high = DEFENSE_MULTIPLIER_CLAMP
    ratings = build_defense_ratings(_pbp_both_sides(), through_week=4)

    assert ratings
    for team_ratings in ratings.values():
        for side in ("pass", "rush"):
            assert side in team_ratings
            assert low <= team_ratings[side] <= high


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


def _pbp_both_sides() -> pd.DataFrame:
    """Four teams, each with valid pass and rush plays and a varied EPA rate."""

    rush_epa = {"TEAM_A": 0.2, "TEAM_B": 0.05, "TEAM_C": -0.1, "TEAM_D": -0.2}
    return pd.concat(
        [_rush_epa_frame(rush_epa), _pass_epa_frame(rush_epa)],
        ignore_index=True,
    )


def _rush_epa_frame(team_epa: dict[str, float]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for team, epa in team_epa.items():
        for idx in range(10):
            rows.append(
                {
                    "season": 2024,
                    "week": idx % 3 + 1,
                    "game_id": f"rush_{team}",
                    "posteam": "OFF",
                    "defteam": team,
                    "pass_attempt": 0,
                    "rush": 1,
                    "epa": epa,
                    "rushing_yards": 4,
                }
            )
    return pd.DataFrame(rows)


def _pass_epa_frame(team_epa: dict[str, float]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for team, epa in team_epa.items():
        for idx in range(10):
            rows.append(
                {
                    "season": 2024,
                    "week": idx % 3 + 1,
                    "game_id": f"pass_{team}",
                    "posteam": "OFF",
                    "defteam": team,
                    "pass_attempt": 1,
                    "rush": 0,
                    "epa": epa,
                    "passing_yards": 7,
                }
            )
    return pd.DataFrame(rows)
