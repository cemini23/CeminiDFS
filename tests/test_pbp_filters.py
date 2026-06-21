import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data.pbp_filters import epa_eligible_plays
from ceminidfs.models.defense import build_defense_ratings
from fixtures.epa_edge_cases import epa_edge_case_frame


def test_epa_eligible_plays_excludes_null_no_play_penalty_punt():
    filtered = epa_eligible_plays(epa_edge_case_frame())
    assert set(filtered["play_id"]) == {1, 3, 7}


def test_epa_eligible_plays_keeps_half_sack_scrimmage_row():
    """Team EPA uses the play row once; half-sack is player attribution only."""

    filtered = epa_eligible_plays(epa_edge_case_frame())
    half_sack = filtered.loc[filtered["play_id"] == 7].iloc[0]
    assert float(half_sack["epa"]) == -0.4


def test_defense_ratings_ignore_ineligible_epa_rows():
    pbp = pd.DataFrame(
        [
            {
                "season": 2024,
                "week": 1,
                "game_id": "g1",
                "posteam": "KC",
                "defteam": "BUF",
                "pass_attempt": 1,
                "rush": 0,
                "epa": 0.5,
                "play_type": "pass",
                "desc": "Big pass",
            },
            {
                "season": 2024,
                "week": 1,
                "game_id": "g1",
                "posteam": "KC",
                "defteam": "BUF",
                "pass_attempt": 1,
                "rush": 0,
                "epa": None,
                "play_type": "pass",
                "desc": "Should drop",
            },
            {
                "season": 2024,
                "week": 1,
                "game_id": "g1",
                "posteam": "KC",
                "defteam": "BUF",
                "pass_attempt": 1,
                "rush": 0,
                "epa": 0.0,
                "play_type": "no_play",
                "desc": "Should drop",
            },
        ]
    )
    ratings = build_defense_ratings(pbp, through_week=2, alpha=0.2)
    assert "BUF" in ratings
    assert ratings["BUF"]["pass"] >= 1.0
