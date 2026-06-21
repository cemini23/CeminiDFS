"""Threshold checks for offseason regression runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ceminidfs.pipeline.calibration import CalibrationReport


@dataclass(frozen=True)
class RegressionGates:
    max_overall_mae: float | None = None
    max_qb_mae: float | None = None
    max_rb_mae: float | None = None
    max_wr_mae: float | None = None
    max_te_mae: float | None = None
    max_dst_mae: float | None = None
    min_overall_spearman: float | None = None

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> RegressionGates:
        regression = dict((config or {}).get("regression") or {})
        return cls(
            max_overall_mae=_optional_float(regression.get("max_overall_mae")),
            max_qb_mae=_optional_float(regression.get("max_qb_mae")),
            max_rb_mae=_optional_float(regression.get("max_rb_mae")),
            max_wr_mae=_optional_float(regression.get("max_wr_mae")),
            max_te_mae=_optional_float(regression.get("max_te_mae")),
            max_dst_mae=_optional_float(regression.get("max_dst_mae")),
            min_overall_spearman=_optional_float(regression.get("min_overall_spearman")),
        )


def check_regression_gates(report: CalibrationReport, gates: RegressionGates) -> list[str]:
    """Return human-readable gate failures for the DIY model."""

    diy = next((model for model in report.models if model.model == "diy"), None)
    if diy is None:
        return ["DIY model missing from calibration report"]

    failures: list[str] = []
    if gates.max_overall_mae is not None and diy.mae_fd > gates.max_overall_mae:
        failures.append(f"overall MAE {diy.mae_fd:.2f} exceeds max {gates.max_overall_mae:.2f}")
    if gates.min_overall_spearman is not None and diy.spearman_fd < gates.min_overall_spearman:
        failures.append(
            f"overall Spearman {diy.spearman_fd:.3f} below min {gates.min_overall_spearman:.3f}"
        )

    by_position = {row.position: row for row in diy.by_position}
    checks = (
        ("QB", gates.max_qb_mae),
        ("RB", gates.max_rb_mae),
        ("WR", gates.max_wr_mae),
        ("TE", gates.max_te_mae),
        ("DST", gates.max_dst_mae),
    )
    for position, limit in checks:
        if limit is None:
            continue
        row = by_position.get(position)
        if row is None:
            failures.append(f"{position} metrics missing from calibration report")
            continue
        if row.mae_fd > limit:
            failures.append(f"{position} MAE {row.mae_fd:.2f} exceeds max {limit:.2f}")
    return failures


def format_gate_failures(failures: list[str]) -> str:
    lines = ["Regression gates failed:"]
    lines.extend(f"- {failure}" for failure in failures)
    return "\n".join(lines)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
