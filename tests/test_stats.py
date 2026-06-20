import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.stats import (
    LEAGUE_ADOT,
    LEAGUE_CATCH_RATE,
    LEAGUE_TD_PER_TARGET,
    LEAGUE_YPA,
    LEAGUE_YPC,
    LEAGUE_YPT,
    build_week_stats,
    player_efficiency_from_pbp,
    project_player_stats,
    regress_rate,
)


def test_regress_rate_shrinkage_toward_prior():
    rate = regress_rate(observed=10.0, sample=10.0, prior=7.0, k=30.0)

    assert rate == pytest.approx(7.75)


def test_player_efficiency_from_pbp_synthetic():
    efficiency = player_efficiency_from_pbp(_synthetic_pbp(), "wr1", through_week=4)

    expected_ypt = regress_rate(10.0, 6.0, LEAGUE_YPT, 250.0)
    expected_catch_rate = regress_rate(4 / 6, 6.0, LEAGUE_CATCH_RATE, 80.0)
    expected_adot = regress_rate(12.0, 6.0, LEAGUE_ADOT, 40.0)
    expected_td_per_target = regress_rate(1 / 6, 6.0, LEAGUE_TD_PER_TARGET, 80.0)

    assert efficiency["ypt"] == pytest.approx(expected_ypt)
    assert efficiency["catch_rate"] == pytest.approx(expected_catch_rate)
    assert efficiency["adot"] == pytest.approx(expected_adot)
    assert efficiency["td_per_target"] == pytest.approx(expected_td_per_target)


def test_project_qb_passing_stats():
    projection = project_player_stats(
        {
            "season": 2024,
            "week": 4,
            "team": "AAA",
            "opponent": "BBB",
            "player_id": "qb1",
            "player_name": "QB One",
            "position": "QB",
            "projected_pass_attempts": 32.0,
            "projected_carries": 3.0,
            "projected_targets": 0.0,
        },
        {
            "ypa": 7.5,
            "td_rate": 0.05,
            "int_rate": 0.02,
            "ypc": 5.0,
            "td_per_carry": 0.04,
        },
        week=4,
    )

    assert projection.pass_yds == pytest.approx(240.0)
    assert projection.pass_td == pytest.approx(1.6)
    assert projection.int == pytest.approx(0.64)
    assert projection.rush_yds == pytest.approx(15.0)
    assert projection.rush_td == pytest.approx(0.12)


def test_project_wr_receiving_stats():
    projection = project_player_stats(
        {
            "season": 2024,
            "week": 4,
            "team": "AAA",
            "opponent": "BBB",
            "player_id": "wr1",
            "player_name": "WR One",
            "position": "WR",
            "projected_pass_attempts": 0.0,
            "projected_carries": 0.0,
            "projected_targets": 8.0,
        },
        {
            "ypt": 8.25,
            "catch_rate": 0.7,
            "td_per_target": 0.06,
            "adot": 11.0,
        },
        week=4,
    )

    assert projection.rec == pytest.approx(5.6)
    assert projection.rec_yds == pytest.approx(66.0)
    assert projection.rec_td == pytest.approx(0.48)
    assert projection.adot == pytest.approx(11.0)


def test_build_week_stats_end_to_end():
    stats = build_week_stats(_usage_df(), _synthetic_pbp(), season=2024, week=4)

    assert len(stats) == 3
    assert set(stats["player_id"]) == {"qb1", "rb1", "wr1"}

    qb = stats.loc[stats["player_id"] == "qb1"].iloc[0]
    rb = stats.loc[stats["player_id"] == "rb1"].iloc[0]
    wr = stats.loc[stats["player_id"] == "wr1"].iloc[0]

    expected_qb_ypa = regress_rate(7.5, 24.0, LEAGUE_YPA, 250.0)
    expected_rb_ypc = regress_rate(4.5, 12.0, LEAGUE_YPC, 250.0)
    expected_wr_catch_rate = regress_rate(4 / 6, 6.0, LEAGUE_CATCH_RATE, 80.0)

    assert qb["pass_yds"] == pytest.approx(30.0 * expected_qb_ypa)
    assert rb["rush_yds"] == pytest.approx(15.0 * expected_rb_ypc)
    assert wr["rec"] == pytest.approx(7.0 * expected_wr_catch_rate)
    assert {"ypa", "ypc", "ypt", "catch_rate", "adot"}.issubset(stats.columns)


def _usage_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": 2024,
                "week": 4,
                "team": "AAA",
                "opponent": "BBB",
                "player_id": "qb1",
                "player_name": "QB One",
                "position": "QB",
                "projected_targets": 0.0,
                "projected_carries": 2.0,
                "projected_pass_attempts": 30.0,
            },
            {
                "season": 2024,
                "week": 4,
                "team": "AAA",
                "opponent": "BBB",
                "player_id": "rb1",
                "player_name": "RB One",
                "position": "RB",
                "projected_targets": 2.0,
                "projected_carries": 15.0,
                "projected_pass_attempts": 0.0,
            },
            {
                "season": 2024,
                "week": 4,
                "team": "AAA",
                "opponent": "BBB",
                "player_id": "wr1",
                "player_name": "WR One",
                "position": "WR",
                "projected_targets": 7.0,
                "projected_carries": 0.0,
                "projected_pass_attempts": 0.0,
            },
        ]
    )


def _synthetic_pbp() -> pd.DataFrame:
    rows = []
    for week in (1, 2, 3):
        rows.extend(_passing_rows(week))
        rows.extend(_rushing_rows(week))
    return pd.DataFrame(rows)


def _passing_rows(week: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx in range(8):
        is_wr_target = idx < 2
        complete = (is_wr_target and (idx == 0 or week == 1)) or (not is_wr_target and idx in {2, 3, 4, 5})
        yards = 15 if is_wr_target and complete else 10 if complete else 0
        rows.append(
            {
                "season": 2024,
                "week": week,
                "game_id": f"g{week}",
                "posteam": "AAA",
                "pass_attempt": 1,
                "rush": 0,
                "passer_player_id": "qb1",
                "passer_player_name": "QB One",
                "receiver_player_id": "wr1" if is_wr_target else "rb1",
                "receiver_player_name": "WR One" if is_wr_target else "RB One",
                "passing_yards": yards,
                "receiving_yards": yards,
                "passing_tds": 1 if week == 1 and idx == 0 else 0,
                "receiving_tds": 1 if week == 1 and idx == 0 else 0,
                "interceptions": 1 if week == 2 and idx == 7 else 0,
                "complete_pass": 1 if complete else 0,
                "air_yards": 12 if is_wr_target else 2,
            }
        )
    return rows


def _rushing_rows(week: int) -> list[dict[str, object]]:
    return [
        {
            "season": 2024,
            "week": week,
            "game_id": f"g{week}",
            "posteam": "AAA",
            "pass_attempt": 0,
            "rush": 1,
            "rusher_player_id": "rb1",
            "rusher_player_name": "RB One",
            "rushing_yards": 4.5,
            "rushing_tds": 1 if week == 3 and idx == 0 else 0,
        }
        for idx in range(4)
    ]
