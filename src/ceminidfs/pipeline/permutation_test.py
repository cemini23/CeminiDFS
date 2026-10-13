"""Permutation null for one projection model.

Shuffle actual FanDuel points, recompute Spearman correlation, and report
the p-value. This module does not build a particle filter.
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

PERMUTATION_DRAWS = 1000
PERMUTATION_SEED = 20261003
NULL_ALPHA = 0.05
PAIRED_COLUMNS = (("fd_projection", "fd_actual"), ("projection", "actual"))
DEFAULT_PROJECTIONS = PROJECT_ROOT / "runs" / "2026_week_3" / "canonical_projections_2026_w3.csv"


@dataclass(frozen=True)
class PermutationResult:
    """One Spearman permutation test."""

    status: str
    week_label: str
    observed: float | None
    p_value: float | None
    n_pairs: int
    draws: int
    seed: int
    source: str
    cleared_null: bool | None


def permutation_p_value(
    projection: list[float] | pd.Series,
    actual: list[float] | pd.Series,
    *,
    draws: int = PERMUTATION_DRAWS,
    seed: int = PERMUTATION_SEED,
) -> float:
    """Return (count of null correlations >= observed, plus one) / (draws + one)."""

    observed = spearman_correlation(projection, actual)
    values = np.asarray(list(actual), dtype=float)
    generator = np.random.default_rng(seed)
    at_least = 0
    for _draw in range(draws):
        shuffled = generator.permutation(values)
        corr = spearman_correlation(projection, shuffled)
        if corr >= observed - 1e-12:
            at_least += 1
    return (at_least + 1) / (draws + 1)


def run_default_permutation() -> PermutationResult:
    """Score the week 3 projection file, or a paired file already on disk."""

    week_label = f"{SEASON} week {WEEK}"
    paired = find_paired_file(PROJECT_ROOT)
    if paired is not None:
        frame = _read_paired_frame(paired)
        if frame is None or len(frame) < 2:
            return _no_evidence(week_label, f"Paired file {paired} has fewer than 2 rows.")
        return _score_frame(frame, week_label, source=str(paired.relative_to(PROJECT_ROOT)))

    return _score_week3_join(week_label)


def find_paired_file(root: Path) -> Path | None:
    """Return a runs/ or artifacts/ file that already has projection and actual columns."""

    found: list[Path] = []
    for folder in (root / "runs", root / "artifacts"):
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".csv", ".parquet"}:
                continue
            columns = _file_columns(path)
            if _paired_column_names(columns) is not None:
                found.append(path)
    if not found:
        return None
    return sorted(found, key=lambda path: (0 if "fd_actual" in _file_columns(path) else 1, str(path)))[0]


def render_permutation(result: PermutationResult) -> str:
    """Return the printed permutation block."""

    lines = [
        f"week: {result.week_label}",
        f"source: {result.source}",
        f"draws: {result.draws}",
        f"seed: {result.seed}",
    ]
    if result.status != "ok" or result.p_value is None or result.observed is None:
        lines.extend(
            [
                "observed_spearman: NO_EVIDENCE",
                "p_value: NO_EVIDENCE",
                "The projection did not join to actual points.",
            ]
        )
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            f"n_pairs: {result.n_pairs}",
            f"observed_spearman: {result.observed:.6f}",
            f"p_value: {result.p_value:.6f}",
        ]
    )
    if result.p_value > NULL_ALPHA:
        lines.append("The model did not clear the null.")
    else:
        lines.append("The model cleared the null at 0.05.")
    return "\n".join(lines) + "\n"


def write_permutation_section(text: str, path: Path = DEFAULT_REPORT) -> Path:
    """Append the permutation block to the measurement brief."""

    heading = "## Permutation test"
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
    """Print the permutation p-value for the week 3 projection model."""

    result = run_default_permutation()
    text = render_permutation(result)
    path = write_permutation_section(text)
    print(text, end="")
    print(f"Wrote permutation section -> {path}")
    return 0


def _score_week3_join(week_label: str) -> PermutationResult:
    if not DEFAULT_PROJECTIONS.is_file() or not DEFAULT_ROSTER.is_file() or not DEFAULT_SCHEDULE.is_file():
        return _no_evidence(week_label, "NO_EVIDENCE")
    try:
        pbp = load_season_pbp(SEASON)
    except FileNotFoundError:
        return _no_evidence(week_label, "NO_EVIDENCE")

    actuals = actual_week_fantasy_points(pbp, SEASON, WEEK)
    if actuals.empty:
        return _no_evidence(week_label, "NO_EVIDENCE")

    games = _teams_with_games(pbp, SEASON, WEEK)
    kickoffs = load_sunday_kickoffs(DEFAULT_SCHEDULE, SEASON, WEEK)
    if not kickoffs or not set(kickoffs).issubset(games):
        return _no_evidence(week_label, "NO_EVIDENCE")

    points = _points_lookup(actuals, DEFAULT_ROSTER, games)
    frame = _pairs_from_projections(DEFAULT_PROJECTIONS, points, kickoffs)
    if frame is None:
        return _no_evidence(week_label, "NO_EVIDENCE")
    source = str(DEFAULT_PROJECTIONS.relative_to(PROJECT_ROOT)) + " joined to nflverse actuals"
    return _score_frame(frame, week_label, source=source)


def _pairs_from_projections(
    path: Path,
    points: dict[tuple[str, str], float],
    kickoffs: dict[str, object],
) -> pd.DataFrame | None:
    projections = pd.read_csv(path)
    if "fd_projection" not in projections.columns:
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
        if pd.isna(projection):
            continue
        lookup = ("__dst__", team) if position == "DEF" else (normalize_person_name(name), team)
        if lookup not in points:
            salary = pd.to_numeric(getattr(row, "fd_salary", 0), errors="coerce")
            if not pd.isna(salary) and float(salary) >= 5_000:
                missing_starters += 1
            continue
        paired_rows.append({"fd_projection": float(projection), "fd_actual": float(points[lookup])})
    if missing_starters:
        return None
    if len(paired_rows) < 2:
        return None
    return pd.DataFrame(paired_rows)


def _score_frame(frame: pd.DataFrame, week_label: str, *, source: str) -> PermutationResult:
    projection_col, actual_col = _paired_column_names(list(frame.columns)) or ("fd_projection", "fd_actual")
    projection = pd.to_numeric(frame[projection_col], errors="coerce")
    actual = pd.to_numeric(frame[actual_col], errors="coerce")
    mask = projection.notna() & actual.notna()
    projection = projection.loc[mask]
    actual = actual.loc[mask]
    if len(projection) < 2:
        return _no_evidence(week_label, source)
    observed = spearman_correlation(projection, actual)
    p_value = permutation_p_value(projection, actual)
    return PermutationResult(
        status="ok",
        week_label=week_label,
        observed=observed,
        p_value=p_value,
        n_pairs=int(len(projection)),
        draws=PERMUTATION_DRAWS,
        seed=PERMUTATION_SEED,
        source=source,
        cleared_null=p_value <= NULL_ALPHA,
    )


def _read_paired_frame(path: Path) -> pd.DataFrame | None:
    columns = _file_columns(path)
    pair = _paired_column_names(columns)
    if pair is None:
        return None
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
    else:
        frame = pd.read_parquet(path, columns=list(pair))
    return frame


def _paired_column_names(columns: list[str]) -> tuple[str, str] | None:
    names = set(columns)
    for left, right in PAIRED_COLUMNS:
        if left in names and right in names:
            return left, right
    return None


def _file_columns(path: Path) -> list[str]:
    try:
        if path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8-sig") as handle:
                header = handle.readline()
            return [column.strip() for column in header.split(",") if column.strip()]
        import pyarrow.parquet as pq

        return list(pq.read_schema(path).names)
    except (OSError, ImportError, ValueError):
        return []


def _no_evidence(week_label: str, source: str) -> PermutationResult:
    return PermutationResult(
        status="NO_EVIDENCE",
        week_label=week_label,
        observed=None,
        p_value=None,
        n_pairs=0,
        draws=PERMUTATION_DRAWS,
        seed=PERMUTATION_SEED,
        source=source,
        cleared_null=None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
