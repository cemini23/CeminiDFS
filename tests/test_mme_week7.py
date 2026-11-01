"""Week 7 guardrails for the FanDuel 150-lineup book."""

import pandas as pd
import pytest

from ceminidfs.export.mme_portfolio import Candidate, select_book
from ceminidfs.export.mme_week7 import (
    BOOK_CAP,
    LATE_Q_CAP,
    RB_PAIR_CAP,
    WATSON_CAP,
    TouchIndex,
    adjust_tails_week7,
    backup_quarterback,
    blocked_by_touch_floor,
    lookup_touches,
    score_week7_frame,
    trailing_active_touches,
)
from ceminidfs.situational.engine import _cache_players


def test_exposure_caps_match_the_week7_budget():
    assert BOOK_CAP["RB"] == 45
    assert BOOK_CAP["WR"] == 48
    assert BOOK_CAP["TE"] == 48
    assert BOOK_CAP["QB"] == 36
    assert BOOK_CAP["DST"] == 33
    assert RB_PAIR_CAP == 24
    assert WATSON_CAP == 7
    assert LATE_Q_CAP == 12


def test_only_the_named_quarterback_stays_eligible():
    assert not backup_quarterback("TB", "Baker Mayfield", "QB")
    assert backup_quarterback("TB", "Jalon Daniels", "QB")
    assert backup_quarterback("BAL", "Lamar Jackson", "QB")
    assert not backup_quarterback("BAL", "Tyler Huntley", "QB")
    assert backup_quarterback("ARI", "Carson Beck", "QB")
    assert not backup_quarterback("ARI", "Jacoby Brissett", "QB")
    assert backup_quarterback("ATL", "Tua Tagovailoa", "QB")
    assert not backup_quarterback("CLE", "Deshaun Watson", "QB")
    assert not backup_quarterback("TB", "Baker Mayfield", "WR")


def _touches() -> TouchIndex:
    pbp = pd.DataFrame(
        {
            "week": [5, 5, 5],
            "posteam": ["TB", "TB", "HOU"],
            "pass": [1, 0, 1],
            "rush": [0, 1, 0],
            "receiver_player_id": ["wr1", None, "wr2"],
            "receiver_player_name": ["Mike Evans", None, "Nico Collins"],
            "rusher_player_id": [None, "rb1", None],
            "rusher_player_name": [None, "Bucky Irving", None],
        }
    )
    rosters = pd.DataFrame(
        {
            "gsis_id": ["wr1", "rb1", "wr2"],
            "full_name": ["Mike Evans", "Bucky Irving", "Nico Collins"],
            "football_name": ["Mike", "Bucky", "Nico"],
            "first_name": ["Mike", "Bucky", "Nico"],
            "last_name": ["Evans", "Irving", "Collins"],
            "team": ["TB", "TB", "HOU"],
        }
    )
    return trailing_active_touches(pbp, rosters)


def test_touch_floor_uses_active_team_weeks_only():
    index = _touches()
    assert lookup_touches(index, "TB", "Mike Evans", "Evans") == 1
    assert lookup_touches(index, "TB", "Bucky Irving", "Irving") == 1
    assert lookup_touches(index, "CAR", "Chuba Hubbard", "Hubbard") is None
    assert lookup_touches(index, "TB", "Zach Ertz", "Ertz") == 0
    assert blocked_by_touch_floor("WR", "TB", "Zach Ertz", "Ertz", index)
    assert not blocked_by_touch_floor("WR", "CAR", "Chuba Hubbard", "Hubbard", index)
    assert not blocked_by_touch_floor("RB", "HOU", "Woody Marks", "Marks", index)
    assert not blocked_by_touch_floor("QB", "TB", "Baker Mayfield", "Mayfield", index)


def test_open_roof_fades_perimeter_passes_and_boosts_the_named_backs():
    assert adjust_tails_week7("SF@ATL", "SF", "WR", "Brandon Aiyuk", 10, 20) == pytest.approx((9.0, 18.0))
    assert adjust_tails_week7("SF@ATL", "SF", "RB", "Christian McCaffrey", 10, 20) == pytest.approx(
        (10.8, 21.6)
    )
    assert adjust_tails_week7("SF@ATL", "ATL", "RB", "Bijan Robinson", 10, 20) == pytest.approx(
        (10.8, 21.6)
    )
    assert adjust_tails_week7("TB@CAR", "TB", "WR", "Chris Godwin", 10, 20) == pytest.approx((9.7, 19.4))
    assert adjust_tails_week7("GB@DET", "DET", "QB", "Jared Goff", 10, 20) == pytest.approx((10.6, 21.2))
    assert adjust_tails_week7("LAR@LV", "LAR", "TE", "Tyler Higbee", 10, 20) == pytest.approx(
        (10.4 * 1.08, 20.8 * 1.08)
    )


def _salary_row(**kwargs):
    base = {
        "Id": "135562-1",
        "Position": "QB",
        "First Name": "Tyler",
        "Nickname": "Tyler Huntley",
        "Last Name": "Huntley",
        "FPPG": 10.39,
        "Salary": 7000,
        "Game": "CIN@BAL",
        "Team": "BAL",
        "Opponent": "CIN",
        "Injury Indicator": "",
        "Injury Details": "",
    }
    base.update(kwargs)
    return base


def test_overlay_zeros_the_backup_and_lifts_the_huntley_floor():
    salary = pd.DataFrame(
        [
            _salary_row(),
            _salary_row(
                **{
                    "Id": "135562-2",
                    "Nickname": "Lamar Jackson",
                    "First Name": "Lamar",
                    "Last Name": "Jackson",
                    "FPPG": 20.0,
                    "Injury Indicator": "O",
                    "Injury Details": "Ankle",
                }
            ),
            _salary_row(
                **{
                    "Id": "135562-3",
                    "Position": "WR",
                    "Nickname": "Zach Ertz",
                    "First Name": "Zach",
                    "Last Name": "Ertz",
                    "Team": "TB",
                    "Opponent": "CAR",
                    "Game": "TB@CAR",
                    "FPPG": 8.0,
                }
            ),
            _salary_row(
                **{
                    "Id": "135562-4",
                    "Position": "RB",
                    "Nickname": "Woody Marks",
                    "First Name": "Woody",
                    "Last Name": "Marks",
                    "Team": "HOU",
                    "Opponent": "NYG",
                    "Game": "NYG@HOU",
                    "FPPG": 12.0,
                }
            ),
        ]
    )
    ceiling = pd.DataFrame(
        [
            {"player_id": "135562-1", "lagged_fd": 4.0, "p90": 6.0, "p99": 8.0},
            {"player_id": "135562-2", "lagged_fd": 18.0, "p90": 24.0, "p99": 30.0},
            {"player_id": "135562-3", "lagged_fd": 8.0, "p90": 12.0, "p99": 16.0},
            {"player_id": "135562-4", "lagged_fd": 12.0, "p90": 16.0, "p99": 20.0},
        ]
    )
    quantiles = {
        "skill": [{"position": "QB", "bucket": "*", "n": 100, "q90": 5.0, "q99": 12.0}],
        "dst": [],
    }
    frame = score_week7_frame(salary, ceiling, quantiles, _touches()).set_index("player_id")
    assert frame.loc["135562-1", "portfolio_lagged"] == pytest.approx(17.0)
    assert frame.loc["135562-1", "never_enter"] == 0
    assert frame.loc["135562-2", "never_enter"] == 1
    assert frame.loc["135562-2", "portfolio_fpts"] == 0
    assert frame.loc["135562-3", "never_enter"] == 1
    assert frame.loc["135562-4", "never_enter"] == 0
    assert frame.loc["135562-4", "portfolio_fpts"] > 0


def _candidate(ids: list[str], blend: float, positions: list[tuple[str, str]]) -> Candidate:
    return Candidate(
        ids=tuple(ids),
        key=frozenset(ids),
        salary=59600,
        blend=blend,
        bringback=True,
        secondary=True,
        catchers=2,
        dst_conflict=False,
        positions=tuple(positions),
        game="GB@DET",
        tags="QB+2 DET",
    )


def _nine(prefix: str, rbs: tuple[str, str]) -> list[tuple[str, str]]:
    return [
        (f"{prefix}-qb", "QB"),
        (rbs[0], "RB"),
        (rbs[1], "RB"),
        (f"{prefix}-w1", "WR"),
        (f"{prefix}-w2", "WR"),
        (f"{prefix}-w3", "WR"),
        (f"{prefix}-te", "TE"),
        (f"{prefix}-dst", "DST"),
        (f"{prefix}-flex", "WR"),
    ]


def test_rb_pair_cap_blocks_the_same_two_backs():
    first = _nine("a", ("rb1", "rb2"))
    second = _nine("b", ("rb1", "rb2"))
    third = _nine("c", ("rb3", "rb4"))
    caps = {"QB": 5, "RB": 5, "WR": 5, "TE": 5, "DST": 5}
    book = select_book(
        [
            _candidate([pid for pid, _pos in first], 50.0, first),
            _candidate([pid for pid, _pos in second], 40.0, second),
            _candidate([pid for pid, _pos in third], 30.0, third),
        ],
        count=3,
        bringback_min=0,
        secondary_min=0,
        caps=caps,
        pair_cap=1,
    )
    assert [item.blend for item in book] == [50.0, 30.0]


def test_cache_players_adds_the_rb_checkdown_score():
    players = pd.DataFrame(
        {
            "player_id": ["rb", "wr"],
            "position": ["RB", "WR"],
            "targets_per_game": [4.0, 8.0],
            "q4_trail_target_share": [0.5, 0.5],
        }
    )
    scored = pd.DataFrame(
        {
            "gsis_id": ["rb"],
            "vacated_target_boost": [1.0],
            "vacated_rz_boost": [0.2],
        }
    )
    out = _cache_players(players, scored).set_index("player_id")
    assert out.loc["rb", "q4_rb_checkdown_score"] == pytest.approx(2.7)
    assert out.loc["wr", "q4_rb_checkdown_score"] == 0.0
    assert out.loc["rb", "vacated_target_boost"] == pytest.approx(1.0)
