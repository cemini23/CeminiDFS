"""Synthetic play-by-play rows for coherence-risk regression tests."""

from __future__ import annotations

import pandas as pd


def coherence_pbp_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    play_id = 1
    for week in (1, 2):
        for sack, qb_hit in ((1, 1), (0, 1), (1, 0), (0, 0)):
            rows.append(_pass_row(play_id, week, "ALP", sack=sack, qb_hit=qb_hit, yardline_100=45))
            play_id += 1
        rows.extend(
            [
                _run_row(play_id, week, "ALP", yardline_100=12),
                _pass_row(play_id + 1, week, "ALP", yardline_100=15),
                _pass_row(play_id + 2, week, "ALP", yardline_100=18),
                _pass_row(play_id + 3, week, "ALP", yardline_100=8),
            ]
        )
        play_id += 4

        for _ in range(4):
            rows.append(_pass_row(play_id, week, "BET", yardline_100=42))
            play_id += 1
        rows.extend(
            [
                _run_row(play_id, week, "BET", yardline_100=11),
                _run_row(play_id + 1, week, "BET", yardline_100=9),
                _run_row(play_id + 2, week, "BET", yardline_100=6),
                _pass_row(play_id + 3, week, "BET", yardline_100=14),
            ]
        )
        play_id += 4

    for _ in range(4):
        rows.append(_pass_row(play_id, 3, "ALP", yardline_100=40))
        play_id += 1
    rows.extend(
        [
            _run_row(play_id, 3, "BET", yardline_100=7),
            _pass_row(play_id + 1, 3, "BET", yardline_100=10),
        ]
    )
    return pd.DataFrame(rows)


def _pass_row(
    play_id: int,
    week: int,
    team: str,
    *,
    sack: int = 0,
    qb_hit: int = 0,
    yardline_100: int,
) -> dict[str, object]:
    return {
        "play_id": play_id,
        "season": 2024,
        "week": week,
        "posteam": team,
        "play_type": "pass",
        "desc": "Synthetic pass play",
        "pass": 0 if sack else 1,
        "pass_attempt": 0 if sack else 1,
        "rush": 0,
        "rush_attempt": 0,
        "sack": sack,
        "qb_hit": qb_hit,
        "yardline_100": yardline_100,
    }


def _run_row(play_id: int, week: int, team: str, *, yardline_100: int) -> dict[str, object]:
    return {
        "play_id": play_id,
        "season": 2024,
        "week": week,
        "posteam": team,
        "play_type": "run",
        "desc": "Synthetic rush play",
        "pass": 0,
        "pass_attempt": 0,
        "rush": 1,
        "rush_attempt": 1,
        "sack": 0,
        "qb_hit": 0,
        "yardline_100": yardline_100,
    }
