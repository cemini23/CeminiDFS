"""Tests for the market-ordered premium projection mode."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.cli import _premium_mode_override, build_parser
from ceminidfs.models.premium_guard import (
    apply_premium_mode,
    market_decision_sentence,
    market_lineup_is_recommended,
    market_premium_projection,
)


def _premium_rows():
    return [
        {"player_name": "Mid", "fd_salary": 7500, "fd_projection": 20.0},
        {"player_name": "Cheap", "fd_salary": 5000, "fd_projection": 30.0},
        {"player_name": "Top", "fd_salary": 9000, "fd_projection": 8.0},
    ]


def test_premium_rows_come_out_in_descending_salary_order():
    rows = _premium_rows()
    out = market_premium_projection(rows)
    premium = [row for row in out if row["fd_salary"] >= 7000]

    assert [row["player_name"] for row in premium] == ["Top", "Mid"]
    assert [row["fd_salary"] for row in premium] == [9000, 7500]
    assert [row["fd_projection"] for row in premium] == [20.0, 8.0]


def test_premium_projection_multiset_is_unchanged():
    rows = _premium_rows()
    before = sorted(row["fd_projection"] for row in rows if row["fd_salary"] >= 7000)
    out = market_premium_projection(rows)
    after = sorted(row["fd_projection"] for row in out if row["fd_salary"] >= 7000)

    assert after == before
    assert rows[0]["fd_projection"] == 20.0
    assert rows[2]["fd_projection"] == 8.0


def test_salary_tie_keeps_the_model_order():
    rows = [
        {"player_name": "Low Model", "fd_salary": 8000, "fd_projection": 9.0},
        {"player_name": "High Model", "fd_salary": 8000, "fd_projection": 15.0},
    ]
    out = market_premium_projection(rows)

    assert [row["player_name"] for row in out] == ["High Model", "Low Model"]
    assert [row["fd_projection"] for row in out] == [15.0, 9.0]


def test_rows_under_7000_stay_untouched():
    rows = _premium_rows()
    out = market_premium_projection(rows)

    assert out[1] is rows[1]
    assert out[1]["fd_projection"] == 30.0
    assert out[1]["fd_salary"] == 5000
    assert "fd_projection_unguarded" not in out[1]


def test_off_mode_is_a_byte_identical_noop():
    rows = _premium_rows()
    assert apply_premium_mode(rows, "off") is rows

    frame_rows = [dict(row) for row in rows]
    again = apply_premium_mode(frame_rows, "off")
    assert again is frame_rows
    assert again == frame_rows


def test_premium_mode_defaults_off_and_guard_aliases_baseline():
    parser = build_parser()
    project = parser.parse_args(
        ["project", "--season", "2026", "--week", "1", "--salary", "salary.csv"]
    )
    run = parser.parse_args(
        ["run", "--season", "2026", "--week", "1", "--salary", "salary.csv"]
    )
    market = parser.parse_args(
        [
            "run",
            "--season",
            "2026",
            "--week",
            "1",
            "--salary",
            "salary.csv",
            "--premium-mode",
            "market",
        ]
    )

    assert project.premium_mode == "off"
    assert run.premium_mode == "off"
    assert _premium_mode_override(project) == {"premium_mode": "off"}
    assert _premium_mode_override(run) == {"premium_mode": "off"}
    assert market.premium_mode == "market"
    assert _premium_mode_override(market) == {"premium_mode": "market"}

    project.premium_guard = True
    assert _premium_mode_override(project) == {"premium_mode": "baseline"}
    market.premium_guard = True
    assert _premium_mode_override(market) == {"premium_mode": "market"}


def test_market_lineup_rule_needs_two_wins_and_a_small_loss():
    assert market_lineup_is_recommended([100, 100, 100], [90, 90, 90], [110, 110, 99])
    assert market_lineup_is_recommended([100, 100, 100], [90, 90, 90], [100, 110, 110])
    assert not market_lineup_is_recommended([100, 100, 100], [90, 90, 90], [110, 110, 97])
    assert not market_lineup_is_recommended([100, 100, 100], [90, 90, 90], [110, 100, 100])

    rejected = market_decision_sentence([100, 100, 100], [90, 90, 90], [110, 100, 100])
    assert "NOT recommended" in rejected
    assert "default stays off" in rejected
