"""Goal-line player share tests. The live coefficient defaults to zero."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.coherence_risk import (
    apply_goal_line_usage_adjustments,
    build_player_goal_line_shares,
)
from ceminidfs.models.coherence_settings import CoherenceRiskSettings


def test_build_player_goal_line_shares_uses_the_goal_line_zone():
    shares = build_player_goal_line_shares(_goal_line_pbp(), 2, settings=_settings())

    assert shares["rb1"]["carry_share"] == pytest.approx(2 / 3)
    assert shares["rb2"]["carry_share"] == pytest.approx(1 / 3)
    assert shares["te1"]["target_share"] == pytest.approx(1 / 2)
    assert shares["wr1"]["target_share"] == pytest.approx(1 / 2)
    assert shares["rb1"]["target_share"] == pytest.approx(0.0)


def test_default_coefficient_is_zero_and_keeps_projected_carries():
    usage = _usage_frame()

    adjusted = apply_goal_line_usage_adjustments(
        usage, build_player_goal_line_shares(_goal_line_pbp(), 2, settings=_settings()), _settings()
    )

    assert adjusted["goal_line_carry_share"].tolist() == pytest.approx([2 / 3, 1 / 3])
    assert adjusted["projected_carries"].tolist() == pytest.approx(usage["projected_carries"].tolist())


def test_explicit_coefficient_raises_the_running_back_mean():
    usage = _usage_frame()
    settings = _settings(carry_share_coefficient=0.30)

    adjusted = apply_goal_line_usage_adjustments(
        usage, build_player_goal_line_shares(_goal_line_pbp(), 2, settings=settings), settings
    )

    base_rb1 = usage.loc[usage["player_id"] == "rb1", "projected_carries"].iloc[0]
    base_rb2 = usage.loc[usage["player_id"] == "rb2", "projected_carries"].iloc[0]
    rb1 = adjusted.loc[adjusted["player_id"] == "rb1", "projected_carries"].iloc[0]
    rb2 = adjusted.loc[adjusted["player_id"] == "rb2", "projected_carries"].iloc[0]

    assert rb1 == pytest.approx(base_rb1 * (1.0 + 0.30 * (2 / 3)))
    assert rb2 == pytest.approx(base_rb2 * (1.0 + 0.30 * (1 / 3)))
    assert (rb1 - base_rb1) > (rb2 - base_rb2)


def test_goal_line_disabled_is_unchanged():
    usage = _usage_frame()
    settings = CoherenceRiskSettings.from_config(
        {"coherence_risk": {"enabled": True, "goal_line": {"enabled": False}}}
    )

    adjusted = apply_goal_line_usage_adjustments(
        usage, build_player_goal_line_shares(_goal_line_pbp(), 2, settings=settings), settings
    )

    assert adjusted.equals(usage)


def _settings(carry_share_coefficient: float = 0.0) -> CoherenceRiskSettings:
    return CoherenceRiskSettings.from_config(
        {
            "coherence_risk": {
                "enabled": True,
                "goal_line": {
                    "enabled": True,
                    "carry_share_coefficient": carry_share_coefficient,
                },
            }
        }
    )


def _goal_line_pbp() -> pd.DataFrame:
    rows = [
        _run("rb1", yardline_100=3),
        _run("rb1", yardline_100=5),
        _run("rb2", yardline_100=4),
        _run("rb2", yardline_100=12),
        _target("te1", yardline_100=4),
        _target("wr1", yardline_100=2),
    ]
    return pd.DataFrame(rows)


def _run(player_id: str, *, yardline_100: int) -> dict[str, object]:
    return {
        "season": 2024,
        "week": 1,
        "posteam": "RUN",
        "play_type": "run",
        "desc": "Synthetic rush play",
        "pass": 0,
        "pass_attempt": 0,
        "rush": 1,
        "rush_attempt": 1,
        "sack": 0,
        "yardline_100": yardline_100,
        "rusher_player_id": player_id,
        "rusher_player_name": player_id.upper(),
    }


def _target(player_id: str, *, yardline_100: int) -> dict[str, object]:
    return {
        "season": 2024,
        "week": 1,
        "posteam": "RUN",
        "play_type": "pass",
        "desc": "Synthetic pass play",
        "pass": 1,
        "pass_attempt": 1,
        "rush": 0,
        "rush_attempt": 0,
        "sack": 0,
        "yardline_100": yardline_100,
        "receiver_player_id": player_id,
        "receiver_player_name": player_id.upper(),
    }


def _usage_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": 2024,
                "week": 2,
                "team": "RUN",
                "opponent": "PAS",
                "player_id": "rb1",
                "player_name": "RB One",
                "position": "RB",
                "projected_carries": 15.0,
                "projected_targets": 3.0,
            },
            {
                "season": 2024,
                "week": 2,
                "team": "RUN",
                "opponent": "PAS",
                "player_id": "rb2",
                "player_name": "RB Two",
                "position": "RB",
                "projected_carries": 5.0,
                "projected_targets": 1.0,
            },
        ]
    )
