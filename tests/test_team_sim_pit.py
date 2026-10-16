"""Point-in-time tests for the team drive simulation model.

``build_model`` must use only weeks strictly before ``cutoff_week``. The
in-function assert cannot catch a leak, because the slice already filters
``week < cutoff_week``. This test builds two frames instead. The prior frame
holds weeks 1 and 2 only. The full frame adds a very different week 3.

A model built at cutoff 3 on the full frame must equal a model built at cutoff 3
on the prior frame. When week 3 leaks into the prior slice, the values differ
and the test fails. The last test proves that the fixture detects a leak: at
cutoff 4 the week-3 drives must change the league touchdown rate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import team_sim  # noqa: E402

PRIOR_WEEKS = (1, 2)
CUTOFF = 3

DRIVE_COLUMNS = ["game_id", "week", "posteam", "defteam", "result"]
GAME_COLUMNS = ["game_id", "week", "home_team", "away_team", "home_score", "away_score"]
PLAY_COLUMNS = [
    "game_id",
    "extra_point_attempt",
    "extra_point_result",
    "two_point_attempt",
    "two_point_conv_result",
]


def _game_id(week: int) -> str:
    return f"2026_{week:02d}_AAA_BBB"


def _prior_drives() -> pd.DataFrame:
    """Weeks 1 and 2. Four drives each, all ``none`` results."""

    rows: list[dict[str, object]] = []
    for week in PRIOR_WEEKS:
        for _ in range(2):
            rows.append(
                {
                    "game_id": _game_id(week),
                    "week": week,
                    "posteam": "AAA",
                    "defteam": "BBB",
                    "result": "none",
                }
            )
        for _ in range(2):
            rows.append(
                {
                    "game_id": _game_id(week),
                    "week": week,
                    "posteam": "BBB",
                    "defteam": "AAA",
                    "result": "none",
                }
            )
    return pd.DataFrame(rows, columns=DRIVE_COLUMNS)


def _week3_drives() -> pd.DataFrame:
    """Week 3. Twenty touchdown drives for the home team."""

    rows = [
        {
            "game_id": _game_id(3),
            "week": 3,
            "posteam": "AAA",
            "defteam": "BBB",
            "result": "td",
        }
        for _ in range(20)
    ]
    return pd.DataFrame(rows, columns=DRIVE_COLUMNS)


def _prior_games() -> pd.DataFrame:
    rows = [
        {
            "game_id": _game_id(week),
            "week": week,
            "home_team": "AAA",
            "away_team": "BBB",
            "home_score": 20,
            "away_score": 20,
        }
        for week in PRIOR_WEEKS
    ]
    return pd.DataFrame(rows, columns=GAME_COLUMNS)


def _week3_game() -> pd.DataFrame:
    rows = [
        {
            "game_id": _game_id(3),
            "week": 3,
            "home_team": "AAA",
            "away_team": "BBB",
            "home_score": 70,
            "away_score": 0,
        }
    ]
    return pd.DataFrame(rows, columns=GAME_COLUMNS)


def _xp_row(game_id: str, result: str) -> dict[str, object]:
    return {
        "game_id": game_id,
        "extra_point_attempt": 1,
        "extra_point_result": result,
        "two_point_attempt": 0,
        "two_point_conv_result": None,
    }


def _two_point_row(game_id: str, result: str) -> dict[str, object]:
    return {
        "game_id": game_id,
        "extra_point_attempt": 0,
        "extra_point_result": None,
        "two_point_attempt": 1,
        "two_point_conv_result": result,
    }


def _prior_pbp() -> pd.DataFrame:
    """Two good XP attempts and one successful two-point attempt per prior game."""

    rows: list[dict[str, object]] = []
    for week in PRIOR_WEEKS:
        game_id = _game_id(week)
        rows.append(_xp_row(game_id, "good"))
        rows.append(_xp_row(game_id, "good"))
        rows.append(_two_point_row(game_id, "success"))
    return pd.DataFrame(rows, columns=PLAY_COLUMNS)


def _week3_pbp() -> pd.DataFrame:
    """Two failed XP attempts and one failed two-point attempt."""

    game_id = _game_id(3)
    rows = [
        _xp_row(game_id, "failed"),
        _xp_row(game_id, "failed"),
        _two_point_row(game_id, "failure"),
    ]
    return pd.DataFrame(rows, columns=PLAY_COLUMNS)


def _prior_frame() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return _prior_drives(), _prior_games(), _prior_pbp()


def _full_frame() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    drives = pd.concat([_prior_drives(), _week3_drives()], ignore_index=True)
    games = pd.concat([_prior_games(), _week3_game()], ignore_index=True)
    pbp = pd.concat([_prior_pbp(), _week3_pbp()], ignore_index=True)
    return drives, games, pbp


def test_cutoff_3_model_ignores_week_3() -> None:
    """A cutoff-3 model on the full frame must equal a cutoff-3 model on the prior frame."""

    prior_drives, prior_games, prior_pbp = _prior_frame()
    full_drives, full_games, full_pbp = _full_frame()

    prior_model = team_sim.build_model(prior_drives, prior_games, prior_pbp, CUTOFF)
    full_model = team_sim.build_model(full_drives, full_games, full_pbp, CUTOFF)

    np.testing.assert_allclose(full_model["league"], prior_model["league"])
    assert full_model["hfa"] == prior_model["hfa"]
    assert full_model["pat"] == prior_model["pat"]
    assert full_model["league_drives"] == prior_model["league_drives"]
    assert full_model["teams"]["AAA"]["rate"] == prior_model["teams"]["AAA"]["rate"]


def test_cutoff_3_model_counts_only_prior_weeks() -> None:
    """The cutoff-3 prior slice holds the two prior weeks only."""

    full_drives, full_games, full_pbp = _full_frame()
    model = team_sim.build_model(full_drives, full_games, full_pbp, CUTOFF)

    # Every week-1 and week-2 drive is a ``none`` result, so the td rate is zero.
    assert model["league"][0] == 0.0
    assert model["teams"]["AAA"]["drives"] == 4
    assert model["teams"]["AAA"]["games"] == 2
    assert model["teams"]["AAA"]["rate"] == 2.0
    assert model["league_drives"] == 2.0


def test_fixture_detects_week_3_leak() -> None:
    """At cutoff 4 the week-3 drives must change the league touchdown rate."""

    full_drives, full_games, full_pbp = _full_frame()

    model_c3 = team_sim.build_model(full_drives, full_games, full_pbp, CUTOFF)
    model_c4 = team_sim.build_model(full_drives, full_games, full_pbp, CUTOFF + 1)

    td_index = team_sim.OUTCOMES.index("td")
    assert model_c4["league"][td_index] != model_c3["league"][td_index]
    assert model_c3["league"][td_index] == 0.0
    assert model_c4["league"][td_index] > 0.0
