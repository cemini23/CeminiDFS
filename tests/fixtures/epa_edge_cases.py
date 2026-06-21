"""Synthetic PBP rows for EPA filter regression tests."""

from __future__ import annotations

import pandas as pd


def epa_edge_case_frame() -> pd.DataFrame:
    """Rows that should be included or excluded by epa_eligible_plays()."""

    return pd.DataFrame(
        [
            {
                "play_id": 1,
                "week": 1,
                "pass_attempt": 1,
                "rush": 0,
                "epa": 0.15,
                "play_type": "pass",
                "desc": "(10:12) (Shotgun) PASS ...",
            },
            {
                "play_id": 2,
                "week": 1,
                "pass_attempt": 1,
                "rush": 0,
                "epa": None,
                "play_type": "pass",
                "desc": "Missing EPA",
            },
            {
                "play_id": 3,
                "week": 1,
                "pass_attempt": 0,
                "rush": 1,
                "epa": -0.08,
                "play_type": "run",
                "desc": "Run play",
            },
            {
                "play_id": 4,
                "week": 1,
                "pass_attempt": 1,
                "rush": 0,
                "epa": 0.0,
                "play_type": "no_play",
                "desc": "Penalty declined",
            },
            {
                "play_id": 5,
                "week": 1,
                "pass_attempt": 1,
                "rush": 0,
                "epa": 0.05,
                "play_type": "pass",
                "desc": "Penalty on Defense, accepted",
            },
            {
                "play_id": 6,
                "week": 1,
                "pass_attempt": 0,
                "rush": 0,
                "epa": 0.02,
                "play_type": "punt",
                "desc": "Punt",
            },
            {
                "play_id": 7,
                "week": 1,
                "pass_attempt": 1,
                "rush": 0,
                "epa": -0.4,
                "play_type": "pass",
                "desc": "Half-sack play row still one scrimmage snap",
                "sack": 1,
                "half_sack_1_player_id": "def_a",
                "half_sack_2_player_id": "def_b",
            },
        ]
    )
