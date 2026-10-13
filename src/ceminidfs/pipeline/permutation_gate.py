"""Salary-controlled permutation gate.

Tests whether a projection model beats a salary-only null. The null is
built by shuffling actual points while keeping projection and salary fixed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ceminidfs.config import PROJECT_ROOT
from ceminidfs.data.stadiums import normalize_team_abbr
from ceminidfs.pipeline.backtest import actual_week_fantasy_points, load_season_pbp
from ceminidfs.pipeline.late_swap_oracle import (
    DEFAULT_REPORT,
    DEFAULT_ROSTER,
    DEFAULT_SCHEDULE,
    SEASON,
    WEEK,
    _points_lookup,
    _teams_with_games,
    canonical_position,
    load_sunday_kickoffs,
    normalize_person_name,
)
from ceminidfs.pipeline.metrics import spearman_correlation


PERMUTATION_GATE_DRAWS = 2000
PERMUTATION_GATE_SEED = 20261003
NULL_ALPHA = 0.05


@dataclass(frozen=True)
class BandResult:
    """One salary-band result."""

    band: str
    n: int
    model_spearman: float | None
    salary_spearman: float | None
    partial_spearman: float | None
    p_value: float | None
    cleared_null: bool | None


def partial_spearman(
    projection: list[float] | pd.Series,
    salary: list[float] | pd.Series,
    actual: list[float] | pd.Series,
) -> float:
    """Return Spearman correlation of rank(actual) and rank(projection) residualized on rank(salary).

    Uses pandas rank() with default tie handling (average) to match
    spearman_correlation in metrics.py.
    """
    proj_series = pd.Series(projection, dtype=float)
    sal_series = pd.Series(salary, dtype=float)
    act_series = pd.Series(actual, dtype=float)

    proj_rank = proj_series.rank()
    sal_rank = sal_series.rank()
    act_rank = act_series.rank()

    n = len(proj_rank)
    if n < 3:
        return 0.0

    sum_x = sal_rank.sum()
    sum_y = proj_rank.sum()
    sum_z = act_rank.sum()
    sum_xx = (sal_rank * sal_rank).sum()
    sum_xy = (sal_rank * proj_rank).sum()
    sum_xz = (sal_rank * act_rank).sum()

    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return 0.0

    beta_proj = (n * sum_xy - sum_x * sum_y) / denom
    beta_act = (n * sum_xz - sum_x * sum_z) / denom

    alpha_proj = (sum_y - beta_proj * sum_x) / n
    alpha_act = (sum_z - beta_act * sum_x) / n

    resid_proj = proj_rank - (alpha_proj + beta_proj * sal_rank)
    resid_act = act_rank - (alpha_act + beta_act * sal_rank)

    cov = (resid_proj * resid_act).sum()
    std_proj = (resid_proj * resid_proj).sum() ** 0.5
    std_act = (resid_act * resid_act).sum() ** 0.5

    if std_proj == 0 or std_act == 0:
        return 0.0

    value = cov / (std_proj * std_act)
    return 0.0 if pd.isna(value) else float(value)


def salary_controlled_p(
    projection: list[float] | pd.Series,
    salary: list[float] | pd.Series,
    actual: list[float] | pd.Series,
    *,
    draws: int = PERMUTATION_GATE_DRAWS,
    seed: int = PERMUTATION_GATE_SEED,
) -> float:
    """Return one-sided p-value: (count of null partials >= observed + 1) / (draws + 1).

    Shuffles the actual column only. Keeps projection and salary fixed.
    """
    observed = partial_spearman(projection, salary, actual)
    values = np.asarray(list(actual), dtype=float)
    generator = np.random.default_rng(seed)
    at_least = 0
    for _draw in range(draws):
        shuffled = generator.permutation(values)
        null_partial = partial_spearman(projection, salary, shuffled)
        if null_partial >= observed - 1e-12:
            at_least += 1
    return (at_least + 1) / (draws + 1)


def _pairs_with_salary(
    path: Path,
    points: dict[tuple[str, str], float],
    kickoffs: dict[str, object],
) -> pd.DataFrame | None:
    """Build paired frame with projection, actual, and salary columns."""
    projections = pd.read_csv(path)
    if "fd_projection" not in projections.columns or "fd_salary" not in projections.columns:
        return None
    paired_rows: list[dict[str, float]] = []
    missing_starters = 0
    for row in projections.itertuples(index=False):
        team = normalize_team_abbr(str(getattr(row, "team", "") or ""))
        if team not in kickoffs:
            continue
        position = canonical_position(str(getattr(row, "fd_position", "") or ""))
        name = str(getattr(row, "player_name", "") or getattr(row, "name", "") or "")
        projection = pd.to_numeric(getattr(row, "fd_projection", None), errors="coerce")
        salary = pd.to_numeric(getattr(row, "fd_salary", None), errors="coerce")
        if pd.isna(projection) or pd.isna(salary):
            continue
        lookup = ("__dst__", team) if position == "DEF" else (normalize_person_name(name), team)
        if lookup not in points:
            if float(salary) >= 5_000:
                missing_starters += 1
            continue
        paired_rows.append(
            {"fd_projection": float(projection), "fd_salary": float(salary), "fd_actual": float(points[lookup])}
        )
    if missing_starters:
        return None
    if len(paired_rows) < 2:
        return None
    return pd.DataFrame(paired_rows)


def _build_paired_frame() -> pd.DataFrame | None:
    """Build the paired frame for the default week 3 slate."""
    if not (PROJECT_ROOT / "runs" / "2026_week_3" / "canonical_projections_2026_w3.csv").is_file():
        return None
    if not DEFAULT_ROSTER.is_file() or not DEFAULT_SCHEDULE.is_file():
        return None
    try:
        pbp = load_season_pbp(SEASON)
    except FileNotFoundError:
        return None

    actuals = actual_week_fantasy_points(pbp, SEASON, WEEK)
    if actuals.empty:
        return None

    games = _teams_with_games(pbp, SEASON, WEEK)
    kickoffs = load_sunday_kickoffs(DEFAULT_SCHEDULE, SEASON, WEEK)
    if not kickoffs or not set(kickoffs).issubset(games):
        return None

    points = _points_lookup(actuals, DEFAULT_ROSTER, games)
    path = PROJECT_ROOT / "runs" / "2026_week_3" / "canonical_projections_2026_w3.csv"
    frame = _pairs_with_salary(path, points, kickoffs)
    return frame


def band_report(
    frame: pd.DataFrame | None = None,
    *,
    draws: int = PERMUTATION_GATE_DRAWS,
    seed: int = PERMUTATION_GATE_SEED,
) -> list[BandResult]:
    """Return band results for all, salary>=6000, salary>=7000, salary<6000."""
    if frame is None:
        frame = _build_paired_frame()
    if frame is None or len(frame) < 2:
        return [
            BandResult("all", 0, None, None, None, None, None),
            BandResult("salary>=6000", 0, None, None, None, None, None),
            BandResult("salary>=7000", 0, None, None, None, None, None),
            BandResult("salary<6000", 0, None, None, None, None, None),
        ]

    projection = pd.to_numeric(frame["fd_projection"], errors="coerce")
    salary = pd.to_numeric(frame["fd_salary"], errors="coerce")
    actual = pd.to_numeric(frame["fd_actual"], errors="coerce")
    mask = projection.notna() & salary.notna() & actual.notna()
    projection = projection.loc[mask].reset_index(drop=True)
    salary = salary.loc[mask].reset_index(drop=True)
    actual = actual.loc[mask].reset_index(drop=True)

    bands: list[tuple[str, pd.Series]] = [
        ("all", pd.Series([True] * len(projection))),
        ("salary>=6000", salary >= 6000),
        ("salary>=7000", salary >= 7000),
        ("salary<6000", salary < 6000),
    ]

    results: list[BandResult] = []
    for band_name, band_mask in bands:
        sub_proj = projection[band_mask].reset_index(drop=True)
        sub_sal = salary[band_mask].reset_index(drop=True)
        sub_act = actual[band_mask].reset_index(drop=True)
        n = len(sub_proj)

        if n < 20:
            results.append(
                BandResult(band_name, n, None, None, None, None, None)
            )
            continue

        model_spearman = spearman_correlation(sub_proj, sub_act)
        salary_spearman = spearman_correlation(sub_sal, sub_act)
        partial = partial_spearman(sub_proj, sub_sal, sub_act)
        p_val = salary_controlled_p(sub_proj, sub_sal, sub_act, draws=draws, seed=seed)
        cleared = p_val <= NULL_ALPHA
        results.append(
            BandResult(band_name, n, model_spearman, salary_spearman, partial, p_val, cleared)
        )
    return results


def render_band_results(results: list[BandResult]) -> str:
    """Return a formatted string of band results."""
    lines = []
    for r in results:
        if r.n < 20 or r.model_spearman is None:
            lines.append(f"{r.band}: n={r.n} NO_EVIDENCE")
            continue
        lines.append(
            f"{r.band}: n={r.n} model_spearman={r.model_spearman:.6f} "
            f"salary_spearman={r.salary_spearman:.6f} partial_spearman={r.partial_spearman:.6f} "
            f"p_value={r.p_value:.6f} cleared_null={r.cleared_null}"
        )
    return "\n".join(lines) + "\n"


def write_gate_section(text: str, path: Path = DEFAULT_REPORT) -> Path:
    """Append the salary-controlled permutation section to the measurement brief.

    Does not clobber existing sections: Verdict, Oracle ceiling, Permutation test, Leak-free replay.
    """
    heading = "## Salary-controlled permutation"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if heading in existing:
            existing = existing.split(heading)[0].rstrip() + "\n\n"
        else:
            existing = existing.rstrip() + "\n\n"
        path.write_text(existing + heading + "\n\n" + text, encoding="utf-8")
    else:
        path.write_text(heading + "\n\n" + text, encoding="utf-8")
    return path


def main() -> int:
    """Run the salary-controlled permutation gate and append to the brief."""
    frame = _build_paired_frame()
    results = band_report(frame)
    lines = [render_band_results(results).rstrip(), ""]
    clearing = [r.band for r in results if r.cleared_null]
    not_clearing = [r.band for r in results if r.cleared_null is False]
    if clearing:
        lines.append(f"The model clears the salary-controlled null in: {', '.join(clearing)}.")
    if not_clearing:
        lines.append(f"The model does not clear the null in: {', '.join(not_clearing)}.")
    text = "\n".join(lines) + "\n"
    path = write_gate_section(text)
    print(text, end="")
    print(f"Wrote salary-controlled permutation section -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())