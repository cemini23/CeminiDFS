"""Walk-forward check of the premium-band guard on 2026 weeks 1, 2, and 3.

The default stays off. The operator reads the report and decides.
This module does not retune the projection model.
"""

from __future__ import annotations

import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ceminidfs.config import PROJECT_ROOT
from ceminidfs.data.historical_slate import (
    POSITION_SALARY_BANDS,
    _normalize_fd_position,
    assign_salaries,
)
from ceminidfs.data.stadiums import normalize_team_abbr
from ceminidfs.models.premium_guard import (
    DEFAULT_GUARD_WEIGHT,
    PREMIUM_SALARY_THRESHOLD,
    apply_premium_guard,
    decision_sentence,
    market_decision_sentence,
    market_premium_projection,
    salary_implied_baseline,
)
from ceminidfs.pipeline.backtest import actual_week_fantasy_points, load_season_pbp


STUDY_SEASON = 2026
STUDY_WEEKS = (1, 2, 3)
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "audit" / "k281-premium-guard.md"
K282_REPORT = PROJECT_ROOT / "reports" / "audit" / "k282-market-premium.md"
K282_SCRATCH = PROJECT_ROOT / "reports" / "audit" / "k282-scratch"
LINEUP_COUNT = 20
_MODES = ("off", "baseline", "market")

_PBP: dict[int, pd.DataFrame] = {}
_POINTS: dict[tuple[int, int], dict[tuple[str, str], float]] = {}
_SYNTHETIC: dict[int, pd.DataFrame] = {}


@dataclass(frozen=True)
class WeekGuardResult:
    """Premium-band partial correlation with the guard off and on."""

    week: int
    n: int
    partial_off: float
    partial_on: float
    delta: float
    history_n: int


@dataclass(frozen=True)
class WeekMarketResult:
    """Rank correlation and lineup points for off, baseline, and market."""

    week: int
    n: int
    partial_off: float
    partial_baseline: float
    partial_market: float
    delta_baseline: float
    delta_market: float
    history_n: int
    points_off: float
    points_baseline: float
    points_market: float
    matched_seats: int
    seats: int
    salary_path: str


def _oracle():
    """Load late-swap helpers only when a study row needs them."""

    from ceminidfs.pipeline import late_swap_oracle

    return late_swap_oracle


def _partial_spearman(projection: Any, salary: Any, actual: Any) -> Any:
    """Load the rank helper only when a study row needs it."""

    from ceminidfs.pipeline.permutation_gate import partial_spearman

    return partial_spearman(projection, salary, actual)


def canonical_projection_path(season: int, week: int) -> Path:
    """Return the canonical projection CSV for one week."""

    return (
        PROJECT_ROOT
        / "runs"
        / f"{season}_week_{week}"
        / f"canonical_projections_{season}_w{week}.csv"
    )


def load_prior_history(season: int, week: int) -> pd.DataFrame:
    """Return salary and actual points from the prior season and earlier weeks.

    Same-season rows come from canonical FanDuel salaries. Prior-season rows
    use a salary band built from scoring before that prior week. The target
    week is not included.
    """

    frames: list[pd.DataFrame] = []
    prior = synthetic_season_history(season - 1)
    if not prior.empty:
        frames.append(prior)
    for earlier in range(1, int(week)):
        rows = real_canonical_rows(season, earlier)
        if rows:
            frames.append(pd.DataFrame(rows))
    columns = ["season", "week", "fd_salary", "fd_actual", "source"]
    if not frames:
        return pd.DataFrame(columns=columns)
    history = pd.concat(frames, ignore_index=True)
    seasons = pd.to_numeric(history["season"], errors="coerce")
    weeks = pd.to_numeric(history["week"], errors="coerce")
    keep = (seasons == int(season) - 1) | ((seasons == int(season)) & (weeks < int(week)))
    return history.loc[keep].reset_index(drop=True)


def synthetic_season_history(season: int) -> pd.DataFrame:
    """Build prior-season salary and point rows from the local play-by-play cache."""

    if season in _SYNTHETIC:
        return _SYNTHETIC[season]

    pbp = _season_pbp(season)
    weeks = sorted(
        {
            int(value)
            for value in pd.to_numeric(pbp["week"], errors="coerce").dropna().unique()
            if 1 <= int(value) <= 18
        }
    )
    prior_parts: list[pd.DataFrame] = []
    rows: list[dict[str, Any]] = []
    for week in weeks:
        print(f"premium-guard history: {season} week {week}", file=sys.stderr)
        actuals = actual_week_fantasy_points(pbp, season, week)
        if actuals.empty or "fd_actual" not in actuals.columns:
            continue
        work = actuals.loc[pd.to_numeric(actuals["fd_actual"], errors="coerce").notna()].copy()
        if work.empty or "player_id" not in work.columns:
            continue
        work["fd_position"] = [
            _normalize_fd_position(str(value)) for value in work["position"].tolist()
        ]
        work["fppg"] = np.nan
        known = pd.Series(False, index=work.index)
        if prior_parts:
            means = (
                pd.concat(prior_parts, ignore_index=True)
                .groupby("player_id")["fd_actual"]
                .mean()
            )
            work["fppg"] = work["player_id"].map(means)
            known = work["fppg"].notna()
        # Cold-start players share one salary per position. Rank only players
        # who already have a prior mean.
        work["fd_salary"] = _position_midpoint(work)
        if bool(known.any()):
            ranked = assign_salaries(work.loc[known, ["fd_position", "fppg"]])
            work.loc[ranked.index, "fd_salary"] = ranked.astype(float)
        for record in work.itertuples(index=False):
            salary = float(getattr(record, "fd_salary"))
            points = float(getattr(record, "fd_actual"))
            if salary <= 0 or not math.isfinite(points):
                continue
            rows.append(
                {
                    "season": int(season),
                    "week": int(week),
                    "fd_salary": salary,
                    "fd_actual": points,
                    "source": "prior_season_band",
                }
            )
        prior_parts.append(work.loc[:, ["player_id", "fd_actual"]].copy())

    frame = pd.DataFrame(rows, columns=["season", "week", "fd_salary", "fd_actual", "source"])
    _SYNTHETIC[season] = frame
    return frame


def real_canonical_rows(season: int, week: int) -> list[dict[str, Any]]:
    """Join one canonical salary file to actual points. Skip a missing file."""

    path = canonical_projection_path(season, week)
    if not path.is_file():
        return []
    points = _week_points(season, week)
    oracle = _oracle()
    frame = pd.read_csv(path)
    rows: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        team = normalize_team_abbr(str(getattr(row, "team", "") or ""))
        position = oracle.canonical_position(str(getattr(row, "fd_position", "") or ""))
        name = str(getattr(row, "player_name", "") or getattr(row, "name", "") or "")
        salary = pd.to_numeric(getattr(row, "fd_salary", None), errors="coerce")
        if not team or pd.isna(salary) or float(salary) <= 0:
            continue
        lookup = ("__dst__", team) if position == "DEF" else (oracle.normalize_person_name(name), team)
        if lookup not in points:
            continue
        rows.append(
            {
                "season": int(season),
                "week": int(week),
                "fd_salary": float(salary),
                "fd_actual": float(points[lookup]),
                "source": "canonical",
            }
        )
    return rows


def sunday_paired_frame(season: int, week: int) -> pd.DataFrame:
    """Return Sunday pairs used by the permutation gate's salary bands.

    The gate drops a full slate when a player at $5,000 or more has no actual
    line. This study keeps every Sunday player who does have an actual line,
    then scores the premium band on that set.
    """

    path = canonical_projection_path(season, week)
    if not path.is_file():
        raise FileNotFoundError(f"Missing canonical projections: {path}")
    schedule = PROJECT_ROOT / "artifacts" / "cache" / f"schedules_{season}.parquet"
    oracle = _oracle()
    kickoffs = oracle.load_sunday_kickoffs(schedule, season, week)
    points = _week_points(season, week)
    projections = pd.read_csv(path)
    paired_rows: list[dict[str, float]] = []
    for row in projections.itertuples(index=False):
        team = normalize_team_abbr(str(getattr(row, "team", "") or ""))
        if team not in kickoffs:
            continue
        position = oracle.canonical_position(str(getattr(row, "fd_position", "") or ""))
        name = str(getattr(row, "player_name", "") or getattr(row, "name", "") or "")
        projection = pd.to_numeric(getattr(row, "fd_projection", None), errors="coerce")
        salary = pd.to_numeric(getattr(row, "fd_salary", None), errors="coerce")
        if pd.isna(projection) or pd.isna(salary):
            continue
        lookup = ("__dst__", team) if position == "DEF" else (oracle.normalize_person_name(name), team)
        if lookup not in points:
            continue
        paired_rows.append(
            {
                "fd_projection": float(projection),
                "fd_salary": float(salary),
                "fd_actual": float(points[lookup]),
            }
        )
    if len(paired_rows) < 2:
        raise RuntimeError(f"No Sunday salary pairs for {season} week {week}")
    return pd.DataFrame(paired_rows)


def run_study(
    season: int = STUDY_SEASON,
    weeks: tuple[int, ...] = STUDY_WEEKS,
) -> list[WeekGuardResult]:
    """Compare the premium band with the guard off and on."""

    results: list[WeekGuardResult] = []
    for week in weeks:
        history = load_prior_history(season, week)
        baseline = salary_implied_baseline(history, season, week)
        paired = sunday_paired_frame(season, week)
        premium = _premium_band(paired)
        partial_off = float(
            _partial_spearman(premium["fd_projection"], premium["fd_salary"], premium["fd_actual"])
        )
        guarded = apply_premium_guard(
            paired,
            baseline,
            threshold=PREMIUM_SALARY_THRESHOLD,
            weight=DEFAULT_GUARD_WEIGHT,
        )
        if not isinstance(guarded, pd.DataFrame):
            raise TypeError("Expected a projection frame from apply_premium_guard")
        guarded_premium = _premium_band(guarded)
        if len(guarded_premium) != len(premium):
            raise RuntimeError(f"Premium band size changed in {season} week {week}")
        partial_on = float(
            _partial_spearman(
                guarded_premium["fd_projection"],
                guarded_premium["fd_salary"],
                guarded_premium["fd_actual"],
            )
        )
        results.append(
            WeekGuardResult(
                week=int(week),
                n=int(len(premium)),
                partial_off=partial_off,
                partial_on=partial_on,
                delta=round(partial_on - partial_off, 6),
                history_n=int(len(history)),
            )
        )
    return results


def format_study(results: list[WeekGuardResult]) -> str:
    """Return the stdout lines for one study."""

    lines = [
        (
            f"week={row.week} n={row.n} partial_off={row.partial_off:.6f} "
            f"partial_on={row.partial_on:.6f} delta={row.delta:.6f}"
        )
        for row in results
    ]
    lines.append(
        decision_sentence(
            [row.partial_off for row in results],
            [row.partial_on for row in results],
        )
    )
    return "\n".join(lines) + "\n"


def render_report(results: list[WeekGuardResult]) -> str:
    """Return the markdown audit report."""

    sentence = decision_sentence(
        [row.partial_off for row in results],
        [row.partial_on for row in results],
    )
    lines = [
        "# K281 premium-band guard",
        "",
        "The guard is optional. The default is off.",
        "It changes a projection only when salary is at least 7000.",
        "The blend keeps half of the model and takes half from a salary baseline.",
        "The weight is 0.5. The weight is not fit on these weeks.",
        "The baseline uses the prior season and earlier weeks of the same season.",
        "It does not use the target week.",
        "",
        "Prior-season salaries come from a position salary band on earlier scoring.",
        "Same-season salaries are the canonical FanDuel salaries.",
        "",
        (
            "The guard is recommended only if the partial correlation is at least "
            "as high in every week, or if it wins at least two weeks and never "
            "loses by more than 0.02."
        ),
        "",
        "| Week | n | partial_off | partial_on | delta |",
        "|------|---|-------------|------------|-------|",
    ]
    for row in results:
        lines.append(
            f"| {row.week} | {row.n} | {row.partial_off:.6f} | "
            f"{row.partial_on:.6f} | {row.delta:.6f} |"
        )
    lines.extend(["", sentence, ""])
    return "\n".join(lines)


def write_report(text: str, path: Path = DEFAULT_REPORT) -> Path:
    """Write the audit report and return its path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_market_study(
    season: int = STUDY_SEASON,
    weeks: tuple[int, ...] = STUDY_WEEKS,
) -> list[WeekMarketResult]:
    """Compare off, baseline, and market on rank and on a 20-lineup book."""

    results: list[WeekMarketResult] = []
    for week in weeks:
        history = load_prior_history(season, week)
        baseline = salary_implied_baseline(history, season, week)
        paired = sunday_paired_frame(season, week)
        premium = _premium_band(paired)
        partial_off = float(
            _partial_spearman(premium["fd_projection"], premium["fd_salary"], premium["fd_actual"])
        )
        guarded = apply_premium_guard(
            paired,
            baseline,
            threshold=PREMIUM_SALARY_THRESHOLD,
            weight=DEFAULT_GUARD_WEIGHT,
        )
        if not isinstance(guarded, pd.DataFrame):
            raise TypeError("Expected a projection frame from apply_premium_guard")
        partial_baseline = _partial_on_band(guarded, season, week, len(premium))
        ordered = market_premium_projection(paired)
        if not isinstance(ordered, pd.DataFrame):
            raise TypeError("Expected a projection frame from market_premium_projection")
        partial_market = _partial_on_band(ordered, season, week, len(premium))
        canonical_rows = _read_canonical_rows(season, week)
        salary_path = _require_salary_path(season, week)
        points = _week_points(season, week)
        book_points: dict[str, float] = {}
        matched_seats = 0
        seats = 0
        for mode in _MODES:
            mode_rows = _rows_for_mode(canonical_rows, mode, baseline)
            total, matched, seat_count = _score_mode_book(
                season,
                week,
                mode,
                mode_rows,
                points,
            )
            book_points[mode] = total
            if mode == "off":
                matched_seats = matched
                seats = seat_count
        results.append(
            WeekMarketResult(
                week=int(week),
                n=int(len(premium)),
                partial_off=partial_off,
                partial_baseline=partial_baseline,
                partial_market=partial_market,
                delta_baseline=round(partial_baseline - partial_off, 6),
                delta_market=round(partial_market - partial_off, 6),
                history_n=int(len(history)),
                points_off=book_points["off"],
                points_baseline=book_points["baseline"],
                points_market=book_points["market"],
                matched_seats=matched_seats,
                seats=seats,
                salary_path=str(salary_path),
            )
        )
    return results


def render_market_report(results: list[WeekMarketResult]) -> str:
    """Return the K282 markdown report."""

    sentence = market_decision_sentence(
        [row.points_off for row in results],
        [row.points_baseline for row in results],
        [row.points_market for row in results],
    )
    lines = [
        "# K282 market premium",
        "",
        "The default mode is off.",
        "Market orders the premium band by salary. It does not fit a parameter.",
        "Baseline is the existing blend. Its math is unchanged.",
        "A premium row has salary of at least 7000.",
        "Three weeks is a small sample. A tie is not a win.",
        "",
        "The pool comes from the canonical projection file.",
        "The salary file for the week must exist. The optimizer does not read FanDuel FPPG.",
        "Each book has 20 lineups. Sim rerank is off.",
        "Scratch files are in `reports/audit/k282-scratch/`.",
        "",
        "## Rank",
        "",
        "| Week | n | partial_off | partial_baseline | partial_market | delta_baseline | delta_market |",
        "|------|---|-------------|------------------|----------------|----------------|--------------|",
    ]
    for row in results:
        lines.append(
            f"| {row.week} | {row.n} | {row.partial_off:.6f} | {row.partial_baseline:.6f} | "
            f"{row.partial_market:.6f} | {row.delta_baseline:.6f} | {row.delta_market:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Lineups",
            "",
            "| Week | points_off | points_baseline | points_market | market_vs_off | seats matched |",
            "|------|------------|-----------------|---------------|---------------|---------------|",
        ]
    )
    for row in results:
        lines.append(
            f"| {row.week} | {row.points_off:.2f} | {row.points_baseline:.2f} | "
            f"{row.points_market:.2f} | {_market_vs_off(row)} | "
            f"{row.matched_seats}/{row.seats} |"
        )
    lines.extend(["", "## Salary files", ""])
    for row in results:
        lines.append(f"- Week {row.week}: `{row.salary_path}`")
    lines.extend(["", "## Decision", "", sentence, ""])
    return "\n".join(lines)


def format_market_study(results: list[WeekMarketResult]) -> str:
    """Return the stdout lines for the market study."""

    lines = []
    for row in results:
        lines.append(
            f"week={row.week} n={row.n} partial_off={row.partial_off:.6f} "
            f"partial_baseline={row.partial_baseline:.6f} "
            f"partial_market={row.partial_market:.6f} "
            f"delta_baseline={row.delta_baseline:.6f} delta_market={row.delta_market:.6f} "
            f"points_off={row.points_off:.2f} points_baseline={row.points_baseline:.2f} "
            f"points_market={row.points_market:.2f}"
        )
    lines.append(
        market_decision_sentence(
            [row.points_off for row in results],
            [row.points_baseline for row in results],
            [row.points_market for row in results],
        )
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    """Run the 2026 weeks 1-3 market study and write both audit reports."""

    results = run_market_study()
    legacy = [
        WeekGuardResult(
            week=row.week,
            n=row.n,
            partial_off=row.partial_off,
            partial_on=row.partial_baseline,
            delta=row.delta_baseline,
            history_n=row.history_n,
        )
        for row in results
    ]
    text = format_market_study(results)
    legacy_path = write_report(render_report(legacy))
    path = write_report(render_market_report(results), K282_REPORT)
    print(text, end="")
    print(f"Wrote {legacy_path}")
    print(f"Wrote {path}")
    return 0


def _partial_on_band(frame: pd.DataFrame, season: int, week: int, expected_n: int) -> float:
    band = _premium_band(frame)
    if len(band) != expected_n:
        raise RuntimeError(f"Premium band size changed in {season} week {week}")
    return float(_partial_spearman(band["fd_projection"], band["fd_salary"], band["fd_actual"]))


def _read_canonical_rows(season: int, week: int) -> list[dict[str, str]]:
    path = canonical_projection_path(season, week)
    if not path.is_file():
        raise FileNotFoundError(f"Missing canonical projections: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _require_salary_path(season: int, week: int) -> Path:
    from ceminidfs.pipeline.fade_coverage import default_salary_path

    path = default_salary_path(season, week)
    if not path.is_file():
        raise FileNotFoundError(f"Missing salary CSV: {path}")
    return path


def _rows_for_mode(
    rows: list[dict[str, str]],
    mode: str,
    baseline: Any,
) -> list[dict[str, Any]]:
    if mode == "off":
        return rows
    if mode == "baseline":
        adjusted = apply_premium_guard(rows, baseline)
    elif mode == "market":
        adjusted = market_premium_projection(rows)
    else:
        raise ValueError(f"Unknown premium mode: {mode}")
    if not isinstance(adjusted, list):
        raise TypeError(f"Expected projection rows for mode {mode}")
    return adjusted


def _score_mode_book(
    season: int,
    week: int,
    mode: str,
    rows: list[dict[str, Any]],
    points: dict[tuple[str, str], float],
) -> tuple[float, int, int]:
    from ceminidfs.export.canonical import write_canonical_csv
    from ceminidfs.export.normalize import normalize_csv
    from ceminidfs.export.optimize import generate_lineups

    scratch = _scratch_dir(season, week, mode)
    canonical = scratch / "canonical.csv"
    players = scratch / "players.csv"
    write_canonical_csv(rows, canonical)
    normalize_csv(canonical, players, site="fanduel")
    print(
        f"premium market lineups: {season} week {week} mode={mode} count={LINEUP_COUNT}",
        file=sys.stderr,
    )
    lineups = generate_lineups(players, site="fanduel", count=LINEUP_COUNT)
    total = 0.0
    matched = 0
    seats = 0
    unmatched: list[str] = []
    for lineup in lineups:
        for player in lineup.players:
            seats += 1
            value, label = _seat_points(player, points)
            if value is None:
                if len(unmatched) < 5:
                    unmatched.append(label)
                continue
            matched += 1
            total += value
    if seats == 0 or matched / seats < 0.9:
        raise RuntimeError(
            f"{season} week {week} mode {mode} matched {matched}/{seats} seats. "
            f"Unmatched sample: {unmatched}"
        )
    return total, matched, seats


def _scratch_dir(season: int, week: int, mode: str) -> Path:
    scratch = K282_SCRATCH / f"{season}_w{week}" / mode
    resolved = scratch.resolve()
    for banned_week in (1, 2, 3):
        banned = (PROJECT_ROOT / "runs" / f"{season}_week_{banned_week}").resolve()
        if resolved == banned or banned in resolved.parents:
            raise RuntimeError(f"Refusing to write {resolved}")
    scratch.mkdir(parents=True, exist_ok=True)
    return scratch


def _seat_points(
    player: Any,
    points: dict[tuple[str, str], float],
) -> tuple[float | None, str]:
    team = normalize_team_abbr(str(getattr(player, "team", "") or ""))
    raw_position = getattr(player, "position", None)
    if not raw_position:
        positions = getattr(player, "positions", None) or ()
        raw_position = positions[0] if positions else ""
    oracle = _oracle()
    position = oracle.canonical_position(str(raw_position))
    name = str(getattr(player, "full_name", "") or "")
    if position == "DEF":
        key = ("__dst__", team)
        label = f"DST {team}"
    else:
        key = (oracle.normalize_person_name(name), team)
        label = f"{name} {team}"
    if key not in points:
        return None, label
    return float(points[key]), label


def _market_vs_off(row: WeekMarketResult) -> str:
    if row.points_off == 0:
        return "n/a"
    percent = (row.points_market - row.points_off) / row.points_off * 100.0
    return f"{percent:.2f}%"


def _premium_band(frame: pd.DataFrame) -> pd.DataFrame:
    salary = pd.to_numeric(frame["fd_salary"], errors="coerce")
    projection = pd.to_numeric(frame["fd_projection"], errors="coerce")
    actual = pd.to_numeric(frame["fd_actual"], errors="coerce")
    mask = salary.ge(PREMIUM_SALARY_THRESHOLD) & projection.notna() & actual.notna()
    return frame.loc[mask].reset_index(drop=True)


def _position_midpoint(frame: pd.DataFrame) -> pd.Series:
    salaries = pd.Series(np.nan, index=frame.index, dtype=float)
    for position, group in frame.groupby("fd_position", sort=False):
        low, high = POSITION_SALARY_BANDS.get(str(position), (5000, 8000))
        salaries.loc[group.index] = int(round(((low + high) / 2) / 100.0) * 100)
    return salaries


def _season_pbp(season: int) -> pd.DataFrame:
    if season not in _PBP:
        _PBP[season] = load_season_pbp(season)
    return _PBP[season]


def _week_points(season: int, week: int) -> dict[tuple[str, str], float]:
    key = (int(season), int(week))
    if key in _POINTS:
        return _POINTS[key]
    pbp = _season_pbp(season)
    actuals = actual_week_fantasy_points(pbp, season, week)
    roster = PROJECT_ROOT / "artifacts" / "cache" / f"rosters_{season}.parquet"
    oracle = _oracle()
    games = oracle._teams_with_games(pbp, season, week)
    points = oracle._points_lookup(actuals, roster, games)
    _POINTS[key] = points
    return points


if __name__ == "__main__":
    raise SystemExit(main())
