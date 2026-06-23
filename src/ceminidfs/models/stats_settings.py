"""Counting-stat efficiency hyperparameters loaded from nfl_dfs.yaml.

QB projections were systematically under-biased because passing efficiency was
shrunk toward league-wide priors (which include backups / garbage time) with a
single hardcoded ``k``. These settings expose the shrinkage strengths and the
QB-specific priors so they can be calibrated from config instead of magic
constants. Defaults reproduce the historical hardcoded behaviour so callers that
pass no config are unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# League-wide priors (population includes backups; QB starters skew higher).
LEAGUE_YPA = 7.0
LEAGUE_YPC = 4.3
LEAGUE_YPT = 7.8
LEAGUE_CATCH_RATE = 0.65
LEAGUE_ADOT = 10.0
LEAGUE_INT_RATE = 0.025
LEAGUE_TD_PER_ATT = 0.045
LEAGUE_TD_PER_CARRY = 0.03
LEAGUE_TD_PER_TARGET = 0.045

# Historical hardcoded shrinkage strengths (preserved as defaults).
DEFAULT_PASS_SHRINKAGE_K = 250.0
DEFAULT_RUSH_SHRINKAGE_K = 250.0
DEFAULT_YPT_SHRINKAGE_K = 250.0
DEFAULT_CATCH_RATE_SHRINKAGE_K = 80.0
DEFAULT_ADOT_SHRINKAGE_K = 40.0
DEFAULT_TD_TARGET_SHRINKAGE_K = 80.0
QB_PASS_SHRINKAGE_K = 90.0
QB_RUSH_SHRINKAGE_K = 160.0

# RB-specific defaults (starter RBs skew above league; lighter shrinkage retains edge)
RB_YPC_SHRINKAGE_K = 120.0
RB_TD_PER_CARRY_SHRINKAGE_K = 120.0


@dataclass(frozen=True)
class StatsSettings:
    # Non-QB passing/rushing + all receiving shrinkage strengths.
    pass_shrinkage_k: float
    rush_shrinkage_k: float
    ypt_shrinkage_k: float
    catch_rate_shrinkage_k: float
    adot_shrinkage_k: float
    td_target_shrinkage_k: float
    # QB-specific shrinkage strengths.
    qb_pass_ypa_shrinkage_k: float
    qb_pass_td_shrinkage_k: float
    qb_pass_int_shrinkage_k: float
    qb_rush_shrinkage_k: float
    # QB-specific regression priors (anchor for shrinkage).
    qb_ypa_prior: float
    qb_td_rate_prior: float
    qb_int_rate_prior: float
    # RB-specific shrinkage strengths (starter RBs retain more of their observed efficiency).
    rb_ypc_shrinkage_k: float
    rb_td_per_carry_shrinkage_k: float
    # RB-specific regression priors (starter RBs skew above league average).
    rb_ypc_prior: float
    rb_td_per_carry_prior: float

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> "StatsSettings":
        stats = dict((config or {}).get("stats") or {})
        shrink = dict(stats.get("shrinkage") or {})
        priors = dict(stats.get("priors") or {})
        qb_pass_k = float(shrink.get("qb_ypa", QB_PASS_SHRINKAGE_K))
        # RB shrinkage: use rb_ypc/rb_td_per_carry if set, fall back to generic ypc for compatibility
        rb_ypc_k = float(shrink.get("rb_ypc", shrink.get("ypc", RB_YPC_SHRINKAGE_K)))
        rb_td_k = float(shrink.get("rb_td_per_carry", shrink.get("ypc", RB_TD_PER_CARRY_SHRINKAGE_K)))
        return cls(
            pass_shrinkage_k=float(shrink.get("ypa", DEFAULT_PASS_SHRINKAGE_K)),
            rush_shrinkage_k=float(shrink.get("ypc", DEFAULT_RUSH_SHRINKAGE_K)),
            ypt_shrinkage_k=float(shrink.get("ypt", DEFAULT_YPT_SHRINKAGE_K)),
            catch_rate_shrinkage_k=float(
                shrink.get("catch_rate", DEFAULT_CATCH_RATE_SHRINKAGE_K)
            ),
            adot_shrinkage_k=float(shrink.get("adot", DEFAULT_ADOT_SHRINKAGE_K)),
            td_target_shrinkage_k=float(
                shrink.get("td_target", DEFAULT_TD_TARGET_SHRINKAGE_K)
            ),
            qb_pass_ypa_shrinkage_k=qb_pass_k,
            qb_pass_td_shrinkage_k=float(shrink.get("qb_td_rate", qb_pass_k)),
            qb_pass_int_shrinkage_k=float(shrink.get("qb_int_rate", qb_pass_k)),
            qb_rush_shrinkage_k=float(shrink.get("qb_rush", QB_RUSH_SHRINKAGE_K)),
            qb_ypa_prior=float(priors.get("qb_ypa", LEAGUE_YPA)),
            qb_td_rate_prior=float(priors.get("qb_td_rate", LEAGUE_TD_PER_ATT)),
            qb_int_rate_prior=float(priors.get("qb_int_rate", LEAGUE_INT_RATE)),
            rb_ypc_shrinkage_k=rb_ypc_k,
            rb_td_per_carry_shrinkage_k=rb_td_k,
            rb_ypc_prior=float(priors.get("rb_ypc", LEAGUE_YPC)),
            rb_td_per_carry_prior=float(priors.get("rb_td_per_carry", LEAGUE_TD_PER_CARRY)),
        )
