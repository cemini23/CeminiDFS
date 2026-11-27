"""Tiered exposure caps for the GPP profile."""

import pandas as pd
import pytest

from ceminidfs.config import load_config
from ceminidfs.data.vegas import team_spreads_from_frame
from ceminidfs.export.exposure_tiers import (
    exposure_cap_for_player,
    exposure_cap_map,
    exposure_tier_config,
)


def _tier_config():
    return exposure_tier_config(load_config(profile="gpp"))


def test_cheap_rb_on_a_blowout_underdog_is_capped_at_ten_percent():
    cap = exposure_cap_for_player(
        "RB",
        5600,
        "CLE",
        cfg=_tier_config(),
        spreads={"CLE": 15.5},
    )

    assert cap is not None
    assert cap <= 0.10


def test_value_wr_punt_is_capped_at_twelve_percent():
    cap = exposure_cap_for_player("WR", 5100, "KC", cfg=_tier_config())

    assert cap == pytest.approx(0.12)


def test_salary_tiers_hold_at_the_boundaries():
    cfg = _tier_config()

    assert exposure_cap_for_player("QB", 5000, cfg=cfg) == pytest.approx(0.35)
    assert exposure_cap_for_player("RB", 7000, cfg=cfg) == pytest.approx(0.35)
    assert exposure_cap_for_player("WR", 5500, cfg=cfg) == pytest.approx(0.20)
    assert exposure_cap_for_player("WR", 5499, cfg=cfg) == pytest.approx(0.12)


def test_an_explicit_override_beats_the_guard_caps():
    cap = exposure_cap_for_player(
        "RB",
        5600,
        "CLE",
        cfg=_tier_config(),
        spreads={"CLE": 15.5},
        explicit={"Tyler Allgeier": 0.35},
        name="Tyler Allgeier",
    )

    assert cap == pytest.approx(0.35)


def test_a_role_cliff_flag_applies_the_reduced_cap():
    cap = exposure_cap_for_player(
        "RB",
        7200,
        "KC",
        cfg=_tier_config(),
        role_flags="ROLE_CLIFF_WARNING",
    )

    assert cap == pytest.approx(0.10)


def test_away_team_on_a_home_underdog_line_takes_the_opposite_sign():
    frame = pd.DataFrame(
        [{"home_team": "KC", "away_team": "CLE", "spread": -15.5}]
    )

    spreads = team_spreads_from_frame(frame)

    assert spreads["KC"] == pytest.approx(-15.5)
    assert spreads["CLE"] == pytest.approx(15.5)


def test_cap_map_uses_each_player_tier():
    players = [
        {"name": "Stud Receiver", "position": "WR", "salary": "8200", "team": "KC"},
        {"name": "Mid Receiver", "position": "WR", "salary": "6000", "team": "KC"},
        {"name": "Punt Receiver", "position": "WR", "salary": "4800", "team": "KC"},
        {"name": "Demoted Back", "position": "RB", "salary": "7100", "team": "CLE"},
    ]

    caps, reasons = exposure_cap_map(
        players,
        config=load_config(profile="gpp"),
        spreads={"CLE": 12.0},
        role_flags={"demoted back": "ROLE_CLIFF_WARNING"},
    )

    assert caps["stud receiver"] == pytest.approx(0.35)
    assert caps["mid receiver"] == pytest.approx(0.20)
    assert caps["punt receiver"] == pytest.approx(0.12)
    assert caps["demoted back"] == pytest.approx(0.10)
    assert reasons["demoted back"] == "role_cliff"


def test_solver_override_map_applies_the_tier_and_the_rb_guard():
    pytest.importorskip("pydfs_lineup_optimizer")
    from ceminidfs.export.optimize import merged_exposure_overrides

    players = [
        {"name": "Cheap Back", "position": "RB", "salary": "5600", "team": "CLE"},
        {"name": "Stud Receiver", "position": "WR", "salary": "8200", "team": "KC"},
    ]

    overrides, reasons = merged_exposure_overrides(
        players,
        gates=None,
        max_exposure=0.35,
        exposure_config=load_config(profile="gpp")["exposure_tiers"],
        spreads={"CLE": 15.5},
    )

    assert overrides["cheap back"] <= 0.10
    assert reasons["cheap back"] == "rb_bad_game_script"
    assert overrides["stud receiver"] == pytest.approx(0.35)


def _slate_player(name, pos, salary, team="KC", hard=False):
    from ceminidfs.data.availability import SlatePlayer

    return SlatePlayer(
        player_id=f"137125-{name}",
        name=name,
        team_raw=team,
        team=team,
        pos=pos,
        salary=str(salary),
        proj_fd_pts="10.0",
        ownership_proj="5.0",
        fd_status="",
        hard_excluded=hard,
    )


def test_top_stud_warning_fires_when_stud_rb_is_dry():
    from ceminidfs.data.availability import top_stud_warnings

    players = [
        _slate_player("Stud Back", "RB", 9000),
        _slate_player("Other Back", "RB", 4000),
        _slate_player("Stud Wideout", "WR", 9500),
    ]
    # Stud Back appears in only 1 of 20 lineups (5%); floor is 8% for RB1.
    resolved = [[players[0], players[2]]] + [[players[1], players[2]]] * 19
    warnings = top_stud_warnings(players, resolved, 20)
    assert any("TOP_STUD_ZERO_EXPOSURE" in w and "Stud Back" in w for w in warnings)
    assert not any("Stud Wideout" in w for w in warnings)


def test_top_stud_warning_silent_when_studs_are_exposed():
    from ceminidfs.data.availability import top_stud_warnings

    players = [
        _slate_player("Stud Back", "RB", 9000),
        _slate_player("Stud Wideout", "WR", 9500),
    ]
    resolved = [[players[0], players[1]]] * 10
    assert top_stud_warnings(players, resolved, 10) == []


def test_normalize_fanduel_team_folds_to_espn_form():
    from ceminidfs.data.availability import normalize_fanduel_team

    assert normalize_fanduel_team("JAC") == "JAX"
    assert normalize_fanduel_team("WAS") == "WSH"
    assert normalize_fanduel_team("CIN") == "CIN"
    assert normalize_fanduel_team("jac") == "JAX"
