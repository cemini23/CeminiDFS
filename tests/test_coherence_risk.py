import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ceminidfs.models.coherence_risk import (
    apply_coherence_risk,
    apply_pass_protection_penalties,
    apply_red_zone_usage_adjustments,
    build_team_pass_protection_stress,
    build_team_red_zone_run_tendency,
    coherence_variance_multiplier,
)
from ceminidfs.models.coherence_settings import CoherenceRiskSettings
from ceminidfs.models.simulate import position_cv_for_row
from fixtures.coherence_pbp import coherence_pbp_frame


def test_build_team_pass_protection_stress_flags_leaky_team():
    stress = build_team_pass_protection_stress(coherence_pbp_frame(), 3, settings=_settings())

    assert stress["ALP"] > 1.0
    assert stress["BET"] < 1.0


def test_pass_protection_stress_uses_walk_forward_cutoff():
    pbp = coherence_pbp_frame()

    through_three = build_team_pass_protection_stress(pbp, 3, settings=_settings())
    through_four = build_team_pass_protection_stress(pbp, 4, settings=_settings())

    assert through_three["ALP"] > through_four["ALP"]


def test_build_team_red_zone_run_tendency_flags_run_heavy_team():
    tendency = build_team_red_zone_run_tendency(coherence_pbp_frame(), 3, settings=_settings())

    assert tendency["BET"] > 1.0
    assert tendency["ALP"] < 1.0


def test_apply_pass_protection_penalties_reduce_qb_and_receiver_yards():
    stats = _stats_frame()

    adjusted = apply_pass_protection_penalties(stats, {"ALP": 1.50, "BET": 1.0}, _settings())

    assert _player_row(adjusted, "alp_qb")["pass_yds"] < _player_row(stats, "alp_qb")["pass_yds"]
    assert _player_row(adjusted, "alp_wr")["rec_yds"] < _player_row(stats, "alp_wr")["rec_yds"]
    assert _player_row(adjusted, "alp_te")["rec_yds"] < _player_row(stats, "alp_te")["rec_yds"]
    assert bool(_player_row(adjusted, "alp_qb")["coherence_risk_flag"]) is True


def test_apply_pass_protection_penalties_leave_low_stress_values_unchanged():
    stats = _stats_frame()

    adjusted = apply_pass_protection_penalties(stats, {"ALP": 1.05, "BET": 1.0}, _settings())

    assert _player_row(adjusted, "alp_qb")["pass_yds"] == pytest.approx(_player_row(stats, "alp_qb")["pass_yds"])
    assert _player_row(adjusted, "alp_wr")["rec_yds"] == pytest.approx(_player_row(stats, "alp_wr")["rec_yds"])
    assert bool(_player_row(adjusted, "alp_qb")["coherence_risk_flag"]) is False


def test_apply_red_zone_usage_adjustments_shift_usage():
    usage = _usage_frame()

    adjusted = apply_red_zone_usage_adjustments(usage, {"BET": 1.50, "ALP": 1.0}, _settings())

    assert _player_row(adjusted, "bet_rb")["projected_carries"] > _player_row(usage, "bet_rb")["projected_carries"]
    assert _player_row(adjusted, "bet_te")["projected_targets"] > _player_row(usage, "bet_te")["projected_targets"]
    assert _player_row(adjusted, "bet_wr")["projected_targets"] < _player_row(usage, "bet_wr")["projected_targets"]
    assert _player_row(adjusted, "bet_rb")["rz_run_index"] == pytest.approx(1.50)


def test_apply_coherence_risk_disabled_is_noop():
    usage = _usage_frame()
    stats = _stats_frame()

    adjusted_usage, adjusted_stats = apply_coherence_risk(
        usage,
        stats,
        coherence_pbp_frame(),
        3,
        {"coherence_risk": {"enabled": False}},
    )

    assert adjusted_usage.equals(usage)
    assert adjusted_stats.equals(stats)


def test_apply_coherence_risk_enabled_applies_both_layers():
    usage = _usage_frame()
    stats = _stats_frame()

    adjusted_usage, adjusted_stats = apply_coherence_risk(
        usage,
        stats,
        coherence_pbp_frame(),
        3,
        _enabled_config(),
    )

    assert _player_row(adjusted_usage, "bet_rb")["projected_carries"] > _player_row(usage, "bet_rb")["projected_carries"]
    assert _player_row(adjusted_stats, "alp_qb")["pass_yds"] < _player_row(stats, "alp_qb")["pass_yds"]


def test_coherence_variance_multiplier_uses_flag_and_stress():
    settings = _settings()

    assert (
        coherence_variance_multiplier({"coherence_risk_flag": True, "pass_protection_stress": 1.0}, settings)
        == pytest.approx(1.25)
    )
    assert (
        coherence_variance_multiplier({"coherence_risk_flag": False, "pass_protection_stress": 1.15}, settings)
        == pytest.approx(1.25)
    )
    assert coherence_variance_multiplier({"coherence_risk_flag": False}, settings) == pytest.approx(1.0)


def test_position_cv_for_row_applies_configured_multiplier():
    boosted = position_cv_for_row(
        {"position": "QB", "pass_protection_stress": 1.15, "coherence_risk_flag": False},
        config=_enabled_config(),
    )
    baseline = position_cv_for_row({"position": "QB"}, config={"coherence_risk": {"enabled": False}})

    assert boosted == pytest.approx(baseline * 1.25)


def _settings() -> CoherenceRiskSettings:
    return CoherenceRiskSettings.from_config(_enabled_config())


def _enabled_config() -> dict[str, object]:
    return {
        "coherence_risk": {
            "enabled": True,
            "pass_protection": {
                "stress_threshold": 1.12,
                "max_penalty": 0.10,
                "qb_yds_penalty": 0.35,
                "recv_yds_penalty": 0.25,
            },
            "red_zone_playcall": {
                "run_tendency_threshold": 1.08,
                "rb_carry_boost": 0.06,
                "te_target_boost": 0.08,
                "wr_target_trim": 0.04,
            },
            "sim_variance": {
                "enabled": True,
                "high_risk_cv_multiplier": 1.25,
                "stress_flag_threshold": 1.12,
            },
        }
    }


def _usage_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": 2024,
                "week": 3,
                "team": "BET",
                "opponent": "ALP",
                "player_id": "bet_rb",
                "player_name": "BET RB",
                "position": "RB",
                "projected_carries": 15.0,
                "projected_targets": 3.0,
                "projected_pass_attempts": 0.0,
            },
            {
                "season": 2024,
                "week": 3,
                "team": "BET",
                "opponent": "ALP",
                "player_id": "bet_te",
                "player_name": "BET TE",
                "position": "TE",
                "projected_carries": 0.0,
                "projected_targets": 5.0,
                "projected_pass_attempts": 0.0,
            },
            {
                "season": 2024,
                "week": 3,
                "team": "BET",
                "opponent": "ALP",
                "player_id": "bet_wr",
                "player_name": "BET WR",
                "position": "WR",
                "projected_carries": 0.0,
                "projected_targets": 7.0,
                "projected_pass_attempts": 0.0,
            },
            {
                "season": 2024,
                "week": 3,
                "team": "ALP",
                "opponent": "BET",
                "player_id": "alp_qb",
                "player_name": "ALP QB",
                "position": "QB",
                "projected_carries": 2.0,
                "projected_targets": 0.0,
                "projected_pass_attempts": 34.0,
            },
        ]
    )


def _stats_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": 2024,
                "week": 3,
                "team": "ALP",
                "opponent": "BET",
                "player_id": "alp_qb",
                "player_name": "ALP QB",
                "position": "QB",
                "pass_yds": 300.0,
                "rec_yds": 0.0,
            },
            {
                "season": 2024,
                "week": 3,
                "team": "ALP",
                "opponent": "BET",
                "player_id": "alp_wr",
                "player_name": "ALP WR",
                "position": "WR",
                "pass_yds": 0.0,
                "rec_yds": 100.0,
            },
            {
                "season": 2024,
                "week": 3,
                "team": "ALP",
                "opponent": "BET",
                "player_id": "alp_te",
                "player_name": "ALP TE",
                "position": "TE",
                "pass_yds": 0.0,
                "rec_yds": 80.0,
            },
            {
                "season": 2024,
                "week": 3,
                "team": "BET",
                "opponent": "ALP",
                "player_id": "bet_wr",
                "player_name": "BET WR",
                "position": "WR",
                "pass_yds": 0.0,
                "rec_yds": 90.0,
            },
        ]
    )


def _player_row(frame: pd.DataFrame, player_id: str) -> pd.Series:
    return frame.loc[frame["player_id"] == player_id].iloc[0]
