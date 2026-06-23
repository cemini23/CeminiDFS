import pandas as pd
import pytest

from ceminidfs.config import load_config
from ceminidfs.models.coherence_risk import (
    apply_coherence_risk,
    apply_fourth_down_aggressiveness_adjustments,
    apply_workload_risk_flags,
    build_player_workload_index,
    build_team_fourth_down_aggressiveness,
)
from ceminidfs.models.coherence_settings import CoherenceRiskSettings
from ceminidfs.models.simulate import position_cv_for_row


def test_fourth_down_aggressiveness_uses_walk_forward_cutoff():
    pbp = _p2_pbp_frame()

    through_three = build_team_fourth_down_aggressiveness(pbp, 3, settings=_settings())
    through_four = build_team_fourth_down_aggressiveness(pbp, 4, settings=_settings())

    assert through_three["ALP"] > 1.0
    assert through_three["BET"] < 1.0
    assert through_four["BET"] > through_three["BET"]


def test_fourth_down_aggressiveness_boosts_passing_usage():
    usage = _usage_frame()

    adjusted = apply_fourth_down_aggressiveness_adjustments(
        usage,
        {"ALP": 1.60, "BET": 1.0},
        _settings(),
    )

    assert _player_row(adjusted, "alp_qb")["projected_pass_attempts"] > _player_row(usage, "alp_qb")[
        "projected_pass_attempts"
    ]
    assert _player_row(adjusted, "alp_wr")["projected_targets"] > _player_row(usage, "alp_wr")[
        "projected_targets"
    ]


def test_skill_workload_index_flags_high_recent_workload():
    workload = build_player_workload_index(_p2_pbp_frame(), 3, settings=_settings())

    assert workload["alp_wr"] > _settings().workload.z_threshold
    assert workload["bet_wr"] < 0.0

    flagged = apply_workload_risk_flags(_usage_frame(), workload, _settings())

    assert bool(_player_row(flagged, "alp_wr")["workload_risk_flag"]) is True
    assert bool(_player_row(flagged, "bet_wr")["workload_risk_flag"]) is False


def test_apply_coherence_risk_p2_disabled_is_noop():
    usage = _usage_frame()
    stats = _stats_frame()

    adjusted_usage, adjusted_stats = apply_coherence_risk(
        usage,
        stats,
        _p2_pbp_frame(),
        3,
        {
            "coherence_risk": {
                "enabled": True,
                "pass_protection": {"enabled": False},
                "red_zone_playcall": {"enabled": False},
                "fourth_down": {"enabled": False},
                "workload": {"enabled": False},
            }
        },
    )

    assert adjusted_usage.equals(usage)
    assert adjusted_stats.equals(stats)


def test_workload_flag_increases_simulation_cv():
    config = _enabled_config()
    config["coherence_risk"]["sim_variance"]["enabled"] = False
    config["coherence_risk"]["workload"]["high_risk_cv_multiplier"] = 1.40

    boosted = position_cv_for_row(
        {"position": "RB", "workload_risk_flag": True, "workload_index": 1.5},
        config=config,
    )
    baseline = position_cv_for_row({"position": "RB"}, config={"coherence_risk": {"enabled": False}})

    assert boosted == pytest.approx(baseline * 1.40)


def test_p2_config_defaults_off_and_gpp_enables():
    base = load_config()
    gpp = load_config(profile="gpp")

    assert base["coherence_risk"]["fourth_down"]["enabled"] is False
    assert base["coherence_risk"]["workload"]["enabled"] is False
    assert gpp["coherence_risk"]["fourth_down"]["enabled"] is True
    assert gpp["coherence_risk"]["workload"]["enabled"] is True


def _settings() -> CoherenceRiskSettings:
    return CoherenceRiskSettings.from_config(_enabled_config())


def _enabled_config() -> dict[str, object]:
    return {
        "coherence_risk": {
            "enabled": True,
            "pass_protection": {"enabled": False},
            "red_zone_playcall": {"enabled": False},
            "fourth_down": {
                "enabled": True,
                "aggression_threshold": 1.10,
                "pass_attempt_boost": 0.05,
                "target_boost": 0.04,
            },
            "workload": {
                "enabled": True,
                "rolling_weeks": 2,
                "z_threshold": 0.50,
                "high_risk_cv_multiplier": 1.20,
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
                "team": "ALP",
                "player_id": "alp_qb",
                "player_name": "ALP QB",
                "position": "QB",
                "projected_targets": 0.0,
                "projected_carries": 2.0,
                "projected_pass_attempts": 32.0,
            },
            {
                "season": 2024,
                "week": 3,
                "team": "ALP",
                "player_id": "alp_wr",
                "player_name": "ALP WR",
                "position": "WR",
                "projected_targets": 9.0,
                "projected_carries": 0.0,
                "projected_pass_attempts": 0.0,
            },
            {
                "season": 2024,
                "week": 3,
                "team": "BET",
                "player_id": "bet_wr",
                "player_name": "BET WR",
                "position": "WR",
                "projected_targets": 5.0,
                "projected_carries": 0.0,
                "projected_pass_attempts": 0.0,
            },
        ]
    )


def _stats_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": "alp_wr", "team": "ALP", "position": "WR", "rec_yds": 90.0},
            {"player_id": "bet_wr", "team": "BET", "position": "WR", "rec_yds": 50.0},
        ]
    )


def _p2_pbp_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    play_id = 1

    for week in (1, 2):
        for _ in range(3):
            rows.append(_pass_row(play_id, week, "ALP", down=4, receiver_id="alp_wr"))
            play_id += 1
        rows.append(_punt_row(play_id, week, "ALP"))
        play_id += 1

        rows.append(_pass_row(play_id, week, "BET", down=4, receiver_id="bet_wr"))
        play_id += 1
        for _ in range(3):
            rows.append(_punt_row(play_id, week, "BET"))
            play_id += 1

        for _ in range(7):
            rows.append(_pass_row(play_id, week, "ALP", down=1, receiver_id="alp_wr"))
            play_id += 1
        rows.append(_pass_row(play_id, week, "BET", down=1, receiver_id="bet_wr"))
        play_id += 1

    for _ in range(6):
        rows.append(_pass_row(play_id, 3, "BET", down=4, receiver_id="bet_wr"))
        play_id += 1
    return pd.DataFrame(rows)


def _pass_row(
    play_id: int,
    week: int,
    team: str,
    *,
    down: int,
    receiver_id: str,
) -> dict[str, object]:
    return {
        "play_id": play_id,
        "game_id": f"2024_{week}_{team}",
        "season": 2024,
        "week": week,
        "posteam": team,
        "down": down,
        "play_type": "pass",
        "desc": "Synthetic pass play",
        "pass": 1,
        "pass_attempt": 1,
        "rush": 0,
        "rush_attempt": 0,
        "sack": 0,
        "receiver_player_id": receiver_id,
        "receiver_player_name": receiver_id.upper(),
    }


def _punt_row(play_id: int, week: int, team: str) -> dict[str, object]:
    return {
        "play_id": play_id,
        "game_id": f"2024_{week}_{team}",
        "season": 2024,
        "week": week,
        "posteam": team,
        "down": 4,
        "play_type": "punt",
        "desc": "Synthetic punt",
        "pass": 0,
        "pass_attempt": 0,
        "rush": 0,
        "rush_attempt": 0,
        "sack": 0,
    }


def _player_row(frame: pd.DataFrame, player_id: str) -> pd.Series:
    return frame.loc[frame["player_id"] == player_id].iloc[0]
