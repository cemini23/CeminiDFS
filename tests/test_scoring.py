import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.scoring import dk_points, fantasy_points_from_stats, fd_points


def test_fd_points_half_ppr_with_bonuses_and_fumbles():
    stats = {
        "pass_yds": 305,
        "pass_td": 2,
        "int": 1,
        "rush_yds": 101,
        "rush_td": 1,
        "rec": 5,
        "rec_yds": 105,
        "rec_td": 1,
        "fumbles_lost": 1,
    }

    assert fd_points(stats) == pytest.approx(61.3)


def test_dk_points_full_ppr_with_bonuses_and_fumbles():
    stats = {
        "pass_yds": 305,
        "pass_td": 2,
        "int": 1,
        "rush_yds": 101,
        "rush_td": 1,
        "rec": 5,
        "rec_yds": 105,
        "rec_td": 1,
        "fumbles_lost": 1,
    }

    assert dk_points(stats) == pytest.approx(64.8)


def test_missing_stats_score_as_zero():
    assert fd_points({}) == 0.0
    assert dk_points({}) == 0.0


def test_dst_stub_event_points():
    stats = {
        "dst_sacks": 3,
        "dst_int": 1,
        "dst_fumbles_recovered": 1,
        "dst_td": 1,
        "dst_safety": 1,
        "dst_blocked_kick": 1,
    }

    assert fd_points(stats) == 17.0
    assert dk_points(stats) == 17.0


def test_fantasy_points_from_projected_stat_row():
    row = {
        "pass_yds": 250,
        "pass_td": 2,
        "int": 1,
        "rush_yds": 20,
        "rush_td": 0,
        "rec": 0,
        "rec_yds": 0,
        "rec_td": 0,
        "fumbles_lost": 0,
    }

    fd, dk = fantasy_points_from_stats(row)

    assert fd == pytest.approx(19.0)
    assert dk == pytest.approx(19.0)

