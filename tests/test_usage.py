import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.usage import (
    build_week_usage,
    identify_qb_starter,
    player_game_stats_from_pbp,
    rolling_shares,
    weighted_blend,
    wopr,
)


def test_weighted_blend():
    assert weighted_blend(0.30, 0.20, 0.10) == pytest.approx(0.23)


def test_wopr_formula():
    assert wopr(0.25, 0.40) == pytest.approx(0.655)


def test_player_game_stats_from_pbp():
    stats = player_game_stats_from_pbp(_synthetic_pbp())

    wr1 = stats.loc[(stats["player_id"] == "wr1") & (stats["week"] == 3)].iloc[0]
    rb1 = stats.loc[(stats["player_id"] == "rb1") & (stats["week"] == 3)].iloc[0]
    qb1 = stats.loc[(stats["player_id"] == "qb1") & (stats["week"] == 3)].iloc[0]

    assert wr1["targets"] == 3
    assert wr1["air_yards"] == 30
    assert rb1["carries"] == 2
    assert qb1["pass_attempts"] == 4


def test_rolling_shares_l3_vs_season():
    stats = player_game_stats_from_pbp(_synthetic_pbp())
    shares = rolling_shares(stats, team="AAA", through_week=4)

    wr1 = shares.loc[shares["player_id"] == "wr1"].iloc[0]
    wr2 = shares.loc[shares["player_id"] == "wr2"].iloc[0]
    rb1 = shares.loc[shares["player_id"] == "rb1"].iloc[0]

    assert wr1["l3_target_share"] == pytest.approx(6 / 9)
    assert wr2["season_target_share"] == pytest.approx(3 / 9)
    assert rb1["l3_carry_share"] == pytest.approx(1.0)


def test_build_week_usage_end_to_end():
    usage = build_week_usage(
        _volume_df(),
        _synthetic_pbp(),
        season=2024,
        week=4,
        roster=_roster(),
    )

    assert len(usage) == 8
    assert set(usage["team"]) == {"AAA", "BBB"}
    assert set(usage["player_id"]) == {"qb1", "wr1", "wr2", "rb1", "qb2", "wr3", "wr4", "rb2"}

    wr1 = usage.loc[usage["player_id"] == "wr1"].iloc[0]
    rb1 = usage.loc[usage["player_id"] == "rb1"].iloc[0]

    expected_wr1_share = (0.5 * (6 / 9)) + (0.3 * (6 / 9)) + (0.2 * 0.18)
    expected_rb1_carry_share = (0.5 * 1.0) + (0.3 * 1.0) + (0.2 * 0.35)
    assert wr1["target_share"] == pytest.approx(expected_wr1_share)
    assert wr1["projected_targets"] == pytest.approx(expected_wr1_share * 30)
    assert rb1["projected_carries"] == pytest.approx(expected_rb1_carry_share * 20)


def test_qb_starter_gets_pass_attempts():
    stats = player_game_stats_from_pbp(_synthetic_pbp())
    assert identify_qb_starter(stats, team="AAA", through_week=4) == "qb1"

    usage = build_week_usage(
        _volume_df(),
        _synthetic_pbp(),
        season=2024,
        week=4,
        roster=_roster(),
    )
    qb1 = usage.loc[usage["player_id"] == "qb1"].iloc[0]
    wr1 = usage.loc[usage["player_id"] == "wr1"].iloc[0]

    assert qb1["projected_pass_attempts"] == pytest.approx(30.0)
    assert wr1["projected_pass_attempts"] == pytest.approx(0.0)


def _volume_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": 2024,
                "week": 4,
                "team": "AAA",
                "opponent": "BBB",
                "pass_attempts": 30.0,
                "rush_attempts": 20.0,
            },
            {
                "season": 2024,
                "week": 4,
                "team": "BBB",
                "opponent": "AAA",
                "pass_attempts": 28.0,
                "rush_attempts": 18.0,
            },
        ]
    )


def _roster() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": "qb1", "player_name": "QB One", "team": "AAA", "position": "QB"},
            {"player_id": "wr1", "player_name": "WR One", "team": "AAA", "position": "WR"},
            {"player_id": "wr2", "player_name": "WR Two", "team": "AAA", "position": "WR"},
            {"player_id": "rb1", "player_name": "RB One", "team": "AAA", "position": "RB"},
            {"player_id": "qb2", "player_name": "QB Two", "team": "BBB", "position": "QB"},
            {"player_id": "wr3", "player_name": "WR Three", "team": "BBB", "position": "WR"},
            {"player_id": "wr4", "player_name": "WR Four", "team": "BBB", "position": "WR"},
            {"player_id": "rb2", "player_name": "RB Two", "team": "BBB", "position": "RB"},
        ]
    )


def _synthetic_pbp() -> pd.DataFrame:
    rows = []
    rows.extend(_game_rows("AAA", 2024, 1, "g1", "qb1", {"wr1": 0, "wr2": 1}, {"rb1": 1}))
    rows.extend(_game_rows("AAA", 2024, 2, "g2", "qb1", {"wr1": 3, "wr2": 1}, {"rb1": 2}))
    rows.extend(_game_rows("AAA", 2024, 3, "g3", "qb1", {"wr1": 3, "wr2": 1}, {"rb1": 2}))
    rows.extend(_game_rows("BBB", 2024, 1, "g1", "qb2", {"wr3": 1, "wr4": 1}, {"rb2": 1}))
    rows.extend(_game_rows("BBB", 2024, 2, "g2", "qb2", {"wr3": 2, "wr4": 1}, {"rb2": 2}))
    rows.extend(_game_rows("BBB", 2024, 3, "g3", "qb2", {"wr3": 2, "wr4": 2}, {"rb2": 2}))
    return pd.DataFrame(rows)


def _game_rows(
    team: str,
    season: int,
    week: int,
    game_id: str,
    qb_id: str,
    targets: dict[str, int],
    carries: dict[str, int],
) -> list[dict[str, object]]:
    names = {
        "qb1": "QB One",
        "qb2": "QB Two",
        "wr1": "WR One",
        "wr2": "WR Two",
        "wr3": "WR Three",
        "wr4": "WR Four",
        "rb1": "RB One",
        "rb2": "RB Two",
    }
    rows: list[dict[str, object]] = []
    for player_id, count in targets.items():
        for _ in range(count):
            rows.append(
                {
                    "season": season,
                    "week": week,
                    "game_id": game_id,
                    "posteam": team,
                    "pass_attempt": 1,
                    "rush": 0,
                    "passer_player_id": qb_id,
                    "passer_player_name": names[qb_id],
                    "receiver_player_id": player_id,
                    "receiver_player_name": names[player_id],
                    "air_yards": 10,
                }
            )
    for player_id, count in carries.items():
        for _ in range(count):
            rows.append(
                {
                    "season": season,
                    "week": week,
                    "game_id": game_id,
                    "posteam": team,
                    "pass_attempt": 0,
                    "rush": 1,
                    "rusher_player_id": player_id,
                    "rusher_player_name": names[player_id],
                    "air_yards": 0,
                }
            )
    return rows
