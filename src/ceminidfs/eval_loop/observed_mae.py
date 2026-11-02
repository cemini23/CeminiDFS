"""Slate MAE for 2025 main-slate weeks 5-17.

Read from reports/backtest_2025_w5-17.json field weeks[].mae_fd on 2026-11-01.
Each row is one slate. The date is the Sunday of that NFL week. The backtest
file has no kickoff time. Do not edit this record during a tuning run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SlateMae:
    """One main slate and its FanDuel projection MAE."""

    slate_date: date
    season: int
    week: int
    mae: float


OBSERVED_SLATE_MAE: tuple[SlateMae, ...] = (
    SlateMae(date(2025, 10, 5), 2025, 5, 4.906093240160165),
    SlateMae(date(2025, 10, 12), 2025, 6, 4.725267869358058),
    SlateMae(date(2025, 10, 19), 2025, 7, 5.130120864633976),
    SlateMae(date(2025, 10, 26), 2025, 8, 4.901330639460166),
    SlateMae(date(2025, 11, 2), 2025, 9, 4.831336899047294),
    SlateMae(date(2025, 11, 9), 2025, 10, 4.726220452195701),
    SlateMae(date(2025, 11, 16), 2025, 11, 4.65821104168795),
    SlateMae(date(2025, 11, 23), 2025, 12, 4.641815857748332),
    SlateMae(date(2025, 11, 30), 2025, 13, 4.695692775947899),
    SlateMae(date(2025, 12, 7), 2025, 14, 4.621704505263236),
    SlateMae(date(2025, 12, 14), 2025, 15, 5.1036558346991745),
    SlateMae(date(2025, 12, 21), 2025, 16, 4.511908833994202),
    SlateMae(date(2025, 12, 28), 2025, 17, 4.421878050460857),
)
