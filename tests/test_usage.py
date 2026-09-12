import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.usage import (
    build_week_usage,
    history_week_cutoff,
    identify_qb_starter,
    infer_player_position,
    player_game_stats_from_pbp,
    rolling_shares,
    weighted_blend,
    wopr,
)


def test_history_week_cutoff_uses_prior_season_on_week_1():
    frame = pd.DataFrame(
        {
            "season": [2025] * 18 + [2026],
            "week": list(range(1, 19)) + [1],
        }
    )

    assert history_week_cutoff(frame, season=2026, week=1) == 19
    assert history_week_cutoff(frame, season=2026, week=2) == 2


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
    assert wr1["target_share"] == pytest.approx(expected_wr1_share)
    assert wr1["projected_targets"] == pytest.approx(expected_wr1_share * 30)
    assert rb1["projected_carries"] > 0
    assert rb1["projected_carries"] < 20


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
    assert qb1["projected_carries"] > 0
    assert wr1["projected_pass_attempts"] == pytest.approx(0.0)


def test_infer_player_position_from_usage():
    assert infer_player_position(120, 5, 0) == "QB"
    assert infer_player_position(0, 40, 10) == "RB"
    assert infer_player_position(0, 2, 30) == "WR"
    assert infer_player_position(0, 2, 30, fallback="TE") == "TE"


def test_player_game_stats_assigns_inferred_positions():
    stats = player_game_stats_from_pbp(_synthetic_pbp())
    wr1 = stats.loc[(stats["player_id"] == "wr1") & (stats["week"] == 3)].iloc[0]
    rb1 = stats.loc[(stats["player_id"] == "rb1") & (stats["week"] == 3)].iloc[0]
    qb1 = stats.loc[(stats["player_id"] == "qb1") & (stats["week"] == 3)].iloc[0]

    assert wr1["position"] == "WR"
    assert rb1["position"] == "RB"
    assert qb1["position"] == "QB"


def test_identify_qb_starter_falls_back_to_season_leader():
    stats = player_game_stats_from_pbp(_synthetic_pbp())
    sparse = stats.loc[~((stats["team"] == "AAA") & (stats["week"] == 3))]
    assert identify_qb_starter(sparse, team="AAA", through_week=4) == "qb1"


def test_identify_qb_starter_prefers_last_week():
    stats = player_game_stats_from_pbp(_synthetic_pbp())
    assert identify_qb_starter(stats, team="AAA", through_week=4) == "qb1"


def test_week1_new_team_qb_keeps_starter_share():
    volume = pd.DataFrame(
        [
            {
                "season": 2026,
                "week": 1,
                "team": "CCC",
                "opponent": "DDD",
                "pass_attempts": 32.0,
                "rush_attempts": 22.0,
                "implied_total": 24.0,
            }
        ]
    )
    pbp = pd.DataFrame(
        [
            {
                "season": 2025,
                "week": 18,
                "game_id": "old",
                "posteam": "CCC",
                "pass_attempt": 1,
                "rush": 0,
                "passer_player_id": "qb_old",
                "passer_player_name": "Old QB",
                "receiver_player_id": "wr_c",
                "receiver_player_name": "WR C",
                "air_yards": 10,
            }
        ]
        * 20
    )
    roster = pd.DataFrame(
        [
            {
                "player_id": "qb_new",
                "player_name": "New QB",
                "team": "CCC",
                "position": "QB",
                "injury_status": "",
                "salary": 8500,
            },
            {
                "player_id": "qb_old",
                "player_name": "Old QB",
                "team": "CCC",
                "position": "QB",
                "injury_status": "",
                "salary": 5200,
            },
            {
                "player_id": "wr_c",
                "player_name": "WR C",
                "team": "CCC",
                "position": "WR",
                "injury_status": "",
                "salary": 6000,
            },
        ]
    )

    usage = build_week_usage(volume, pbp, season=2026, week=1, roster=roster)
    new_qb = usage.loc[usage["player_id"] == "qb_new"].iloc[0]
    old_qb = usage.loc[usage["player_id"] == "qb_old"].iloc[0]

    assert new_qb["projected_pass_attempts"] > 0
    assert old_qb["projected_pass_attempts"] < new_qb["projected_pass_attempts"]


def test_week1_lone_expensive_rb_keeps_min_share():
    volume = pd.DataFrame(
        [
            {
                "season": 2026,
                "week": 1,
                "team": "CCC",
                "opponent": "DDD",
                "pass_attempts": 30.0,
                "rush_attempts": 25.0,
            }
        ]
    )
    pbp_rows = []
    for week in (16, 17, 18):
        for rusher_id, rusher_name in (
            ("rb_hist", "Hist RB"),
            ("rb_b", "RB B"),
            ("rb_c", "RB C"),
        ):
            for _ in range(3):
                pbp_rows.append(
                    {
                        "season": 2025,
                        "week": week,
                        "game_id": f"g{week}",
                        "posteam": "CCC",
                        "pass_attempt": 0,
                        "rush": 1,
                        "rusher_player_id": rusher_id,
                        "rusher_player_name": rusher_name,
                    }
                )
    pbp = pd.DataFrame(pbp_rows)
    roster = pd.DataFrame(
        [
            {
                "player_id": "rb_star",
                "player_name": "Star RB",
                "team": "CCC",
                "position": "RB",
                "injury_status": "",
                "salary": 7500,
            },
            {
                "player_id": "rb_hist",
                "player_name": "Hist RB",
                "team": "CCC",
                "position": "RB",
                "injury_status": "",
                "salary": 5200,
            },
            {
                "player_id": "rb_b",
                "player_name": "RB B",
                "team": "CCC",
                "position": "RB",
                "injury_status": "",
                "salary": 5000,
            },
            {
                "player_id": "rb_c",
                "player_name": "RB C",
                "team": "CCC",
                "position": "RB",
                "injury_status": "",
                "salary": 4800,
            },
            {
                "player_id": "rb_d",
                "player_name": "RB D",
                "team": "CCC",
                "position": "RB",
                "injury_status": "",
                "salary": 4600,
            },
        ]
    )

    usage = build_week_usage(volume, pbp, season=2026, week=1, roster=roster)
    star = usage.loc[usage["player_id"] == "rb_star"].iloc[0]
    assert star["projected_carries"] > 0
    assert star["carry_share"] >= 0.35


def test_rb_committee_zeros_deep_backups():
    volume = _volume_df()
    pbp = _synthetic_pbp()
    roster = pd.DataFrame(
        [
            {"player_id": "qb1", "player_name": "QB One", "team": "AAA", "position": "QB"},
            {"player_id": "wr1", "player_name": "WR One", "team": "AAA", "position": "WR"},
            {"player_id": "rb1", "player_name": "RB One", "team": "AAA", "position": "RB"},
            {"player_id": "rb2", "player_name": "RB Two", "team": "AAA", "position": "RB"},
            {"player_id": "rb3", "player_name": "RB Three", "team": "AAA", "position": "RB"},
            {"player_id": "rb4", "player_name": "RB Four", "team": "AAA", "position": "RB"},
        ]
    )
    usage = build_week_usage(volume, pbp, season=2024, week=4, roster=roster)
    rb4 = usage.loc[usage["player_id"] == "rb4"].iloc[0]
    rb1 = usage.loc[usage["player_id"] == "rb1"].iloc[0]

    assert rb4["projected_carries"] == pytest.approx(0.0)
    assert rb4["projected_targets"] == pytest.approx(0.0)
    assert rb1["projected_carries"] > rb4["projected_carries"]


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
