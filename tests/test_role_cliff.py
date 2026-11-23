"""Trailing-three-game usage decay and the role-cliff guard."""

import pandas as pd

from ceminidfs.models.role_cliff import detect_role_cliffs, flagged_player_keys
from ceminidfs.models.usage_settings import UsageSettings


def _game_frame(touches):
    rows = []
    for week, value in enumerate(touches, start=1):
        rows.append(
            {
                "player_id": "rb1",
                "player_name": "Demoted Back",
                "position": "RB",
                "season": 2026,
                "week": week,
                "carries": value,
                "targets": 0,
            }
        )
    return pd.DataFrame(rows)


def test_a_drop_of_forty_percent_or_more_flags_the_player():
    stats = _game_frame([15] * 10 + [7, 7, 7])

    result = detect_role_cliffs(stats)["rb1"]

    assert result.flagged
    assert result.drop_pct >= 0.40
    assert flagged_player_keys({"rb1": result}) == ["rb1"]


def test_a_smaller_drop_does_not_flag():
    stats = _game_frame([15] * 10 + [11, 11, 11])

    result = detect_role_cliffs(stats)["rb1"]

    assert not result.flagged
    assert result.drop_pct < 0.40


def test_a_zero_touch_game_is_treated_as_a_mid_game_exit():
    stats = _game_frame([15] * 10 + [8, 0, 8])

    results = detect_role_cliffs(stats)

    assert "rb1" not in results
    assert not any(result.flagged for result in results.values())


def test_a_player_with_too_few_games_is_skipped():
    stats = _game_frame([5, 5])

    assert detect_role_cliffs(stats) == {}


def test_rb_and_wr_blend_the_trailing_three_games_at_sixty_percent():
    settings = UsageSettings.from_config(
        {
            "usage": {
                "share_weights_by_position": {
                    "RB": [0.6, 0.25, 0.15],
                    "WR": [0.6, 0.25, 0.15],
                }
            }
        }
    )

    assert settings.weights_for("RB")[0] >= 0.60
    assert settings.weights_for("WR")[0] >= 0.60
    assert settings.weights_for("QB") == settings.share_weights
