"""Optional post-projection guard for the premium salary band.

The guard blends a projection toward a salary baseline. The baseline is fit
on earlier weeks only. It never reads the target week.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


PREMIUM_SALARY_THRESHOLD = 7000
DEFAULT_GUARD_WEIGHT = 0.5

_SALARY_COLUMNS = ("fd_salary", "salary")
_POINTS_COLUMNS = ("fd_actual", "points", "actual")
_PROJECTION_COLUMNS = ("fd_projection", "projection")


@dataclass(frozen=True)
class SalaryBaseline:
    """Log-linear map from salary to an implied point total."""

    intercept: float
    slope: float

    def __call__(self, salary: float) -> float:
        value = float(salary)
        if not math.isfinite(value) or value <= 0:
            return float("nan")
        if not math.isfinite(self.intercept) or not math.isfinite(self.slope):
            return float("nan")
        return float(self.intercept + self.slope * math.log(value))


def salary_implied_baseline(
    history: pd.DataFrame,
    season: int,
    week: int,
) -> SalaryBaseline:
    """Fit points ~ a + b * log(salary) on weeks strictly before ``week``.

    Rows from the target season are used only when their week is earlier than
    ``week``. Rows from the prior season are used for every week. The target
    week and any later week are ignored.
    """

    if history.empty:
        raise ValueError(f"No salary history for {season} week {week}")

    season_col = _require_column(history.columns, ("season",))
    week_col = _require_column(history.columns, ("week",))
    salary_col = _require_column(history.columns, _SALARY_COLUMNS)
    points_col = _require_column(history.columns, _POINTS_COLUMNS)

    seasons = pd.to_numeric(history[season_col], errors="coerce")
    weeks = pd.to_numeric(history[week_col], errors="coerce")
    target = int(season)
    target_week = int(week)
    keep = ((seasons == target) & (weeks < target_week)) | (seasons == target - 1)
    prior = history.loc[keep]
    if prior.empty:
        raise ValueError(f"No prior salary history for {season} week {week}")

    fit = pd.DataFrame(
        {
            "season": seasons.loc[keep],
            "week": weeks.loc[keep],
            "salary": pd.to_numeric(prior[salary_col], errors="coerce"),
            "points": pd.to_numeric(prior[points_col], errors="coerce"),
        }
    )
    fit = fit.loc[fit["salary"].gt(0) & fit["points"].notna() & np.isfinite(fit["points"])]
    fit = fit.sort_values(["season", "week", "salary", "points"]).reset_index(drop=True)
    if len(fit) < 2:
        raise ValueError(f"Not enough prior rows to fit a salary baseline for {season} week {week}")
    return _fit_log_linear(fit["salary"].to_numpy(dtype=float), fit["points"].to_numpy(dtype=float))


def apply_premium_guard(
    projections: pd.DataFrame | Sequence[Mapping[str, Any]],
    baseline: Any,
    *,
    threshold: float = PREMIUM_SALARY_THRESHOLD,
    weight: float = DEFAULT_GUARD_WEIGHT,
) -> pd.DataFrame | list[dict[str, Any]]:
    """Blend premium projections toward ``baseline``. Other players stay as they are.

    ``weight=0`` returns a copy with the same projection values. A player at or
    above ``threshold`` becomes ``(1 - weight) * projection + weight * baseline(salary)``.
    """

    if isinstance(projections, pd.DataFrame):
        return _apply_frame(projections, baseline, threshold=float(threshold), weight=float(weight))
    return _apply_rows(projections, baseline, threshold=float(threshold), weight=float(weight))


def guard_is_recommended(
    partial_off: Sequence[float],
    partial_on: Sequence[float],
) -> bool:
    """Return True when the walk-forward rule accepts the guard.

    Accept the guard when the partial correlation is at least as high in every
    week. Also accept it when it wins at least two weeks and never loses by
    more than 0.02. A tie is not a win on the second path.
    """

    if len(partial_off) != len(partial_on) or not partial_off:
        return False
    deltas = [_rounded_delta(on, off) for off, on in zip(partial_off, partial_on, strict=True)]
    if all(delta >= 0 for delta in deltas):
        return True
    strict_wins = sum(delta > 0 for delta in deltas)
    worst_loss = max(-delta for delta in deltas)
    return strict_wins >= 2 and worst_loss <= 0.02


def decision_sentence(partial_off: Sequence[float], partial_on: Sequence[float]) -> str:
    """Return one sentence for the walk-forward decision."""

    if not guard_is_recommended(partial_off, partial_on):
        return (
            "The guard is NOT recommended because the walk-forward partial "
            "correlation does not meet the decision rule, so the flag stays off."
        )
    deltas = [_rounded_delta(on, off) for off, on in zip(partial_off, partial_on, strict=True)]
    if all(delta >= 0 for delta in deltas):
        return (
            "The guard is recommended because the partial correlation "
            "is at least as high in every week."
        )
    return (
        "The guard is recommended because it wins at least two weeks "
        "and never loses by more than 0.02."
    )


def market_premium_projection(
    projections: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    threshold: float = PREMIUM_SALARY_THRESHOLD,
) -> pd.DataFrame | list[dict[str, Any]]:
    """Reorder premium projections by salary. Do not fit a parameter.

    Rows below ``threshold`` stay unchanged. Premium rows are ordered by salary
    descending, then by the model projection descending. Their projection values
    are reattached in that order. The premium multiset does not change.
    """

    if isinstance(projections, pd.DataFrame):
        records = projections.to_dict(orient="records")
        return pd.DataFrame(_market_rows(records, float(threshold)))
    return _market_rows(list(projections), float(threshold))


def apply_premium_mode(
    projections: pd.DataFrame | Sequence[Mapping[str, Any]],
    mode: str,
    *,
    baseline: Any = None,
    threshold: float = PREMIUM_SALARY_THRESHOLD,
    weight: float = DEFAULT_GUARD_WEIGHT,
) -> pd.DataFrame | list[dict[str, Any]]:
    """Dispatch one premium mode. ``off`` returns the same object."""

    chosen = str(mode or "off").strip().lower()
    if chosen == "off":
        return projections
    if chosen == "baseline":
        if baseline is None:
            raise ValueError("baseline mode needs a salary baseline")
        return apply_premium_guard(
            projections,
            baseline,
            threshold=threshold,
            weight=weight,
        )
    if chosen == "market":
        return market_premium_projection(projections, threshold=threshold)
    raise ValueError("premium_mode must be one of: off, baseline, market")


def market_lineup_is_recommended(
    points_off: Sequence[float],
    points_baseline: Sequence[float],
    points_market: Sequence[float],
) -> bool:
    """Return True when market wins the lineup rule.

    Market must have the highest total in at least two weeks. A tie is not a
    win. It must not lose to off by more than 2 percent in any week.
    """

    if (
        not points_off
        or len(points_off) != len(points_baseline)
        or len(points_off) != len(points_market)
    ):
        return False
    wins = 0
    for off, baseline, market in zip(points_off, points_baseline, points_market, strict=True):
        off_value = float(off)
        baseline_value = float(baseline)
        market_value = float(market)
        if market_value > off_value and market_value > baseline_value:
            wins += 1
        if off_value > 0 and market_value < off_value * 0.98:
            return False
        if off_value <= 0 and market_value < off_value:
            return False
    return wins >= 2


def market_decision_sentence(
    points_off: Sequence[float],
    points_baseline: Sequence[float],
    points_market: Sequence[float],
) -> str:
    """Return one sentence for the lineup decision."""

    if market_lineup_is_recommended(points_off, points_baseline, points_market):
        return (
            "Market is recommended because its lineup total is highest in at least "
            "two weeks and it never loses to off by more than 2 percent."
        )
    return (
        "Market is NOT recommended because the lineup totals do not meet the "
        "decision rule, so the default stays off."
    )


def _rounded_delta(on: float, off: float) -> float:
    return round(float(on) - float(off), 6)


def _fit_log_linear(salary: np.ndarray, points: np.ndarray) -> SalaryBaseline:
    log_salary = np.log(salary)
    if np.unique(log_salary).size < 2:
        return SalaryBaseline(intercept=float(np.median(points)), slope=0.0)
    slope, intercept = np.polyfit(log_salary, points, 1)
    return SalaryBaseline(intercept=float(intercept), slope=float(slope))


def _apply_frame(
    projections: pd.DataFrame,
    baseline: Any,
    *,
    threshold: float,
    weight: float,
) -> pd.DataFrame:
    out = projections.copy(deep=True)
    if weight == 0.0:
        return out

    proj_col = _require_column(out.columns, _PROJECTION_COLUMNS)
    sal_col = _require_column(out.columns, _SALARY_COLUMNS)
    original = out[proj_col].copy()
    out["fd_projection_unguarded"] = original
    salary = pd.to_numeric(out[sal_col], errors="coerce")
    projection = pd.to_numeric(original, errors="coerce")
    premium = salary.ge(threshold) & salary.notna() & projection.notna()
    for index in out.index[premium]:
        implied = _baseline_points(baseline, float(salary.loc[index]))
        if implied is None:
            continue
        blended = (1.0 - weight) * float(projection.loc[index]) + weight * implied
        out.at[index, proj_col] = blended
    return out


def _apply_rows(
    projections: Sequence[Mapping[str, Any]],
    baseline: Any,
    *,
    threshold: float,
    weight: float,
) -> list[dict[str, Any]]:
    adjusted: list[dict[str, Any]] = []
    for row in projections:
        new_row = dict(row)
        if weight == 0.0:
            adjusted.append(new_row)
            continue
        proj_key = _first_key(new_row, _PROJECTION_COLUMNS)
        sal_key = _first_key(new_row, _SALARY_COLUMNS)
        if proj_key is None or sal_key is None:
            adjusted.append(new_row)
            continue
        new_row["fd_projection_unguarded"] = new_row.get(proj_key)
        salary = pd.to_numeric(new_row.get(sal_key), errors="coerce")
        projection = pd.to_numeric(new_row.get(proj_key), errors="coerce")
        if pd.isna(salary) or pd.isna(projection) or float(salary) < threshold:
            adjusted.append(new_row)
            continue
        implied = _baseline_points(baseline, float(salary))
        if implied is None:
            adjusted.append(new_row)
            continue
        new_row[proj_key] = (1.0 - weight) * float(projection) + weight * implied
        adjusted.append(new_row)
    return adjusted


def _baseline_points(baseline: Any, salary: float) -> float | None:
    try:
        if isinstance(baseline, Mapping):
            if salary in baseline:
                implied = baseline[salary]
            else:
                key = int(round(salary))
                implied = baseline[key]
        else:
            implied = baseline(salary)
    except KeyError:
        return None
    value = float(implied)
    if not math.isfinite(value):
        return None
    return value


def _require_column(columns: Sequence[str], names: Sequence[str]) -> str:
    found = _first_present(columns, names)
    if found is None:
        joined = ", ".join(names)
        raise ValueError(f"Missing required column. Expected one of: {joined}")
    return found


def _first_present(columns: Sequence[str], names: Sequence[str]) -> str | None:
    present = set(columns)
    for name in names:
        if name in present:
            return name
    return None


def _first_key(row: Mapping[str, Any], names: Sequence[str]) -> str | None:
    for name in names:
        if name in row:
            return name
    return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    parsed = float(number)
    if not math.isfinite(parsed):
        return None
    return parsed


def _mapping_salary(row: Mapping[str, Any]) -> float | None:
    key = _first_key(row, _SALARY_COLUMNS)
    if key is None:
        return None
    return _as_float(row.get(key))


def _mapping_projection(row: Mapping[str, Any]) -> float | None:
    key = _first_key(row, _PROJECTION_COLUMNS)
    if key is None:
        return None
    return _as_float(row.get(key))


def _premium_sort_key(row: Mapping[str, Any]) -> tuple[float, float]:
    salary = _mapping_salary(row) or 0.0
    projection = _mapping_projection(row)
    projection_key = projection if projection is not None else float("-inf")
    return (-salary, -projection_key)


def _sorted_projections(values: Sequence[float | None]) -> list[float | None]:
    present = [value for value in values if value is not None]
    absent = [value for value in values if value is None]
    return sorted(present, reverse=True) + absent


def _with_market_projection(row: Mapping[str, Any], projection: float | None) -> dict[str, Any]:
    new_row = dict(row)
    key = _first_key(new_row, _PROJECTION_COLUMNS)
    if key is None:
        return new_row
    new_row["fd_projection_unguarded"] = new_row.get(key)
    if projection is None:
        return new_row
    new_row[key] = projection
    return new_row


def _market_rows(
    rows: Sequence[Mapping[str, Any]],
    threshold: float,
) -> list[dict[str, Any] | Mapping[str, Any]]:
    result: list[dict[str, Any] | Mapping[str, Any]] = list(rows)
    slots: list[int] = []
    picked: list[Mapping[str, Any]] = []
    for index, row in enumerate(rows):
        salary = _mapping_salary(row)
        if salary is None or salary < threshold:
            continue
        slots.append(index)
        picked.append(row)
    ordered = sorted(picked, key=_premium_sort_key)
    assigned = _sorted_projections([_mapping_projection(row) for row in ordered])
    for slot, source, projection in zip(slots, ordered, assigned, strict=True):
        result[slot] = _with_market_projection(source, projection)
    return result
