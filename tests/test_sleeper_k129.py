"""Tests for K129 Sleeper buzz and luck metrics."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data import sleeper
from ceminidfs.models.buzz_signal import attach_buzz_columns, apply_buzz_ownership_boost
from ceminidfs.pipeline.luck_metrics import (
    compute_team_luck_table,
    pythagorean_expected_wins,
    summarize_luck_metrics,
)


def test_fetch_trending_players_parses_payload():
    payload = [
        {"player_id": "1234", "count": 99},
        {"player_id": "5678", "count": 12},
    ]

    with patch.object(sleeper, "_http_get_json", return_value=payload):
        trending = sleeper.fetch_trending_players(direction="add", limit=5)

    assert len(trending) == 2
    assert trending[0].player_id == "1234"
    assert trending[0].count == 99
    assert trending[0].direction == "add"


def test_normalize_player_name_strips_punctuation():
    assert sleeper.normalize_player_name("Ja'Marr Chase") == "jamarr chase"


def test_attach_buzz_columns_matches_name_and_team():
    lookup = {
        ("justin jefferson", "MIN"): {"add": 5000, "drop": 0},
    }
    rows = [
        {
            "name": "Justin Jefferson",
            "team": "MIN",
            "fd_projection": 18.5,
        }
    ]
    config = {"buzz_signal": {"enabled": True, "skip_network": True}}
    enriched = attach_buzz_columns(rows, config=config, lookup=lookup)
    assert enriched[0]["sleeper_buzz_add"] == 5000
    assert enriched[0]["sleeper_buzz_drop"] == 0


def test_apply_buzz_ownership_boost_caps_nudge():
    rows = [
        {
            "sleeper_buzz_add": 9000,
            "Projected Ownership": "10.0",
        }
    ]
    config = {
        "buzz_signal": {
            "enabled": True,
            "ownership_boost_per_1k": 0.5,
            "max_ownership_boost": 2.0,
        }
    }
    boosted = apply_buzz_ownership_boost(rows, config=config)
    # 9000 adds => 9 * 0.5 = 4.5, capped at 2.0
    assert float(boosted[0]["Projected Ownership"]) == pytest.approx(12.0)


def test_pythagorean_expected_wins_midpoint():
    expected = pythagorean_expected_wins(300, 300, 10)
    assert expected == pytest.approx(5.0, abs=0.01)


def test_compute_team_luck_table_from_schedules():
    schedules = pd.DataFrame(
        [
            {
                "week": 1,
                "home_team": "KC",
                "away_team": "BUF",
                "home_score": 30,
                "away_score": 10,
            },
            {
                "week": 2,
                "home_team": "BUF",
                "away_team": "KC",
                "home_score": 17,
                "away_score": 20,
            },
        ]
    )
    table = compute_team_luck_table(2024, through_week=2, schedules=schedules)
    kc = table.loc[table["team"] == "KC"].iloc[0]
    buf = table.loc[table["team"] == "BUF"].iloc[0]
    assert int(kc["wins"]) == 2
    assert int(buf["wins"]) == 0
    assert float(kc["luck"]) > float(buf["luck"])


def test_summarize_luck_metrics_json_shape():
    schedules = pd.DataFrame(
        [
            {
                "week": 1,
                "home_team": "KC",
                "away_team": "BUF",
                "home_score": 24,
                "away_score": 17,
            }
        ]
    )
    summary = summarize_luck_metrics(2024, 1, schedules=schedules)
    assert summary["season"] == 2024
    assert summary["through_week"] == 1
    assert summary["teams"] == 2
    assert "luckiest" in summary
    json.dumps(summary)
