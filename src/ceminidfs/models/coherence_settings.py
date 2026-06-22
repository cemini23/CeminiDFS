"""Coherence-risk hyperparameters loaded from nfl_dfs.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class PassProtectionSettings:
    enabled: bool
    stress_threshold: float
    max_penalty: float
    qb_yds_penalty: float
    recv_yds_penalty: float


@dataclass(frozen=True)
class RedZonePlaycallSettings:
    enabled: bool
    run_tendency_threshold: float
    rb_carry_boost: float
    te_target_boost: float
    wr_target_trim: float


@dataclass(frozen=True)
class CoherenceSimVarianceSettings:
    enabled: bool
    high_risk_cv_multiplier: float
    stress_flag_threshold: float


@dataclass(frozen=True)
class CoherenceRiskSettings:
    enabled: bool
    pass_protection: PassProtectionSettings
    red_zone_playcall: RedZonePlaycallSettings
    sim_variance: CoherenceSimVarianceSettings

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> CoherenceRiskSettings:
        coherence = dict((config or {}).get("coherence_risk") or {})
        pass_protection = dict(coherence.get("pass_protection") or {})
        red_zone_playcall = dict(coherence.get("red_zone_playcall") or {})
        sim_variance = dict(coherence.get("sim_variance") or {})
        return cls(
            enabled=bool(coherence.get("enabled", True)),
            pass_protection=PassProtectionSettings(
                enabled=bool(pass_protection.get("enabled", True)),
                stress_threshold=float(pass_protection.get("stress_threshold", 1.12)),
                max_penalty=float(pass_protection.get("max_penalty", 0.10)),
                qb_yds_penalty=float(pass_protection.get("qb_yds_penalty", 0.35)),
                recv_yds_penalty=float(pass_protection.get("recv_yds_penalty", 0.25)),
            ),
            red_zone_playcall=RedZonePlaycallSettings(
                enabled=bool(red_zone_playcall.get("enabled", True)),
                run_tendency_threshold=float(red_zone_playcall.get("run_tendency_threshold", 1.08)),
                rb_carry_boost=float(red_zone_playcall.get("rb_carry_boost", 0.06)),
                te_target_boost=float(red_zone_playcall.get("te_target_boost", 0.08)),
                wr_target_trim=float(red_zone_playcall.get("wr_target_trim", 0.04)),
            ),
            sim_variance=CoherenceSimVarianceSettings(
                enabled=bool(sim_variance.get("enabled", True)),
                high_risk_cv_multiplier=float(sim_variance.get("high_risk_cv_multiplier", 1.25)),
                stress_flag_threshold=float(sim_variance.get("stress_flag_threshold", 1.12)),
            ),
        )
