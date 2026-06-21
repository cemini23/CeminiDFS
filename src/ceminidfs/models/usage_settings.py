"""Usage-model hyperparameters loaded from nfl_dfs.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class UsageSettings:
    share_weights: tuple[float, float, float]
    l3_window: int
    qb_carry_share: float
    min_l3_qb_pass_attempts: int
    min_last_week_qb_pass_attempts: int
    min_backup_start_qb_pass_attempts: int
    min_two_week_qb_pass_attempts: int
    qb_backup_pass_share: float
    qb_implied_pass_boost: float
    qb_implied_pass_baseline: float
    rb_committee_size: int
    rb_carry_priors: tuple[float, ...]
    rb_target_priors: tuple[float, ...]
    min_backup_qb_season_attempts: int
    min_backup_qb_l3_attempts: int

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> UsageSettings:
        usage = dict((config or {}).get("usage") or {})
        return cls(
            share_weights=_tuple3(usage.get("share_weights"), (0.5, 0.3, 0.2)),
            l3_window=int(usage.get("l3_window", 3)),
            qb_carry_share=float(usage.get("qb_carry_share", 0.12)),
            min_l3_qb_pass_attempts=int(usage.get("min_l3_qb_pass_attempts", 10)),
            min_last_week_qb_pass_attempts=int(usage.get("min_last_week_qb_pass_attempts", 18)),
            min_backup_start_qb_pass_attempts=int(usage.get("min_backup_start_qb_pass_attempts", 12)),
            min_two_week_qb_pass_attempts=int(usage.get("min_two_week_qb_pass_attempts", 25)),
            qb_backup_pass_share=float(usage.get("qb_backup_pass_share", 0.05)),
            qb_implied_pass_boost=float(usage.get("qb_implied_pass_boost", 0.014)),
            qb_implied_pass_baseline=float(usage.get("qb_implied_pass_baseline", 22.0)),
            rb_committee_size=int(usage.get("rb_committee_size", 3)),
            rb_carry_priors=_tuple_floats(usage.get("rb_carry_priors"), (0.35, 0.12, 0.04)),
            rb_target_priors=_tuple_floats(usage.get("rb_target_priors"), (0.08, 0.05, 0.03)),
            min_backup_qb_season_attempts=int(usage.get("min_backup_qb_season_attempts", 15)),
            min_backup_qb_l3_attempts=int(usage.get("min_backup_qb_l3_attempts", 5)),
        )


def _tuple3(value: Any, default: tuple[float, float, float]) -> tuple[float, float, float]:
    if value is None:
        return default
    items = tuple(float(v) for v in value)
    if len(items) != 3:
        raise ValueError("share_weights must contain exactly three values")
    return items  # type: ignore[return-value]


def _tuple_floats(value: Any, default: tuple[float, ...]) -> tuple[float, ...]:
    if value is None:
        return default
    return tuple(float(v) for v in value)
