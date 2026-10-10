"""Measure book exposure per slate team and flag faded teams that produced.

The report runs after the games. It uses actual points, not projections.

The slate team list comes from the week's FanDuel salary CSV. Never use every
team that played that week. Thursday, Sunday-night, and Monday games are not on
the Sunday slate. Counting them inflates the number.

Run one week:

    python -m ceminidfs.pipeline.fade_coverage --season 2026 --week 3

Run the season rollup:

    python -m ceminidfs.pipeline.fade_coverage --season 2026 --season-rollup
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import Path

import pandas as pd

from ceminidfs.data.salary import parse_salary_csv
from ceminidfs.pipeline.backtest import actual_week_fantasy_points, load_season_pbp

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# An 18-point game from a cheap player is a real hit. Keep one named constant.
DEFAULT_PRODUCED_THRESHOLD = 18.0

# Report paths. The week file is per week; the season file holds the rollup.
WEEK_REPORT_DIR = PROJECT_ROOT / "reports" / "audit"
WEEK_REPORT_TEMPLATE = "fade-coverage-w{week}.md"
SEASON_REPORT_NAME = "fade-coverage-season.md"

# The default salary CSVs for the 2026 Sunday slates. The operator may override.
DEFAULT_SALARY_BY_WEEK: dict[int, Path] = {
    1: PROJECT_ROOT / "data" / "slates" / "2026-09-13_fd_sun.csv",
    2: PROJECT_ROOT / "data" / "slates" / "2026-09-20_fd_sun.csv",
    3: PROJECT_ROOT / "data" / "slates" / "2026-09-27_fd_sun.csv",
    4: PROJECT_ROOT / "data" / "slates" / "2026-10-04_fd_sun.csv",
}

TEAM_COVERAGE_COLUMNS = [
    "team",
    "book_exposure",
    "top_scorer_name",
    "top_scorer_points",
    "zero_exposure",
    "faded_and_produced",
]

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def default_salary_path(season: int, week: int) -> Path:
    """Return the default salary CSV for a week, or the 2026 convention path."""

    if season == 2026 and week in DEFAULT_SALARY_BY_WEEK:
        return DEFAULT_SALARY_BY_WEEK[week]
    return PROJECT_ROOT / "data" / "slates" / f"{season}-w{week:02d}_fd_sun.csv"


def default_lineups_path(season: int, week: int) -> Path:
    """Return the standard book path for one week."""

    return PROJECT_ROOT / "runs" / f"{season}_week_{week}" / "lineups.csv"


def slate_teams(salary_path: str | Path, season: int, week: int) -> list[str]:
    """Return the sorted slate teams from the salary CSV.

    This is the explicit slate input. Do not build it from play-by-play.
    """

    rows = parse_salary_csv(salary_path, season, week)
    teams: list[str] = []
    seen: set[str] = set()
    for row in rows:
        team = str(row.get("team") or "").strip().upper()
        if not team or team in seen:
            continue
        seen.add(team)
        teams.append(team)
    return sorted(teams)


def normalize_player_name(value: object) -> str:
    """Fold a player name to a match key (case, accents, punctuation, suffix)."""

    text = str(value or "").strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = _SUFFIX.sub("", text.lower())
    return re.sub(r"[^a-z0-9]", "", text)


def lineup_player_names(lineups_path: str | Path) -> set[str]:
    """Return the set of name keys that appear in a lineup CSV."""

    path = Path(lineups_path)
    if not path.is_file():
        raise FileNotFoundError(f"Lineups CSV not found: {path}")
    lineups = pd.read_csv(path)
    names: set[str] = set()
    for value in lineups.to_numpy().ravel():
        if isinstance(value, str):
            key = normalize_player_name(value)
            if key:
                names.add(key)
    return names


def book_exposure_by_team(
    salary_path: str | Path,
    lineups_path: str | Path,
    season: int,
    week: int,
) -> dict[str, int]:
    """Count rostered salary rows per slate team. One row is one book seat."""

    rows = parse_salary_csv(salary_path, season, week)
    rostered = lineup_player_names(lineups_path)
    exposure: dict[str, int] = {}
    for row in rows:
        team = str(row.get("team") or "").strip().upper()
        if not team:
            continue
        exposure.setdefault(team, 0)
        key = normalize_player_name(row.get("player_name") or row.get("name"))
        if key and key in rostered:
            exposure[team] += 1
    return exposure


def top_scorer_by_team(pbp: pd.DataFrame, season: int, week: int) -> dict[str, tuple[str, float]]:
    """Return the best actual FanDuel scorer per team for one week."""

    actuals = actual_week_fantasy_points(pbp, season, week)
    if actuals.empty:
        return {}
    points = pd.to_numeric(actuals.get("fd_actual"), errors="coerce")
    actuals = actuals.assign(fd_actual=points).dropna(subset=["fd_actual"])
    actuals = actuals.loc[actuals["fd_actual"] > 0]
    if actuals.empty:
        return {}
    best: dict[str, tuple[str, float]] = {}
    for _, row in actuals.iterrows():
        team = str(row.get("team") or "").strip().upper()
        if not team:
            continue
        name = str(row.get("player_name") or "").strip()
        value = float(row["fd_actual"])
        current = best.get(team)
        if current is None or value > current[1]:
            best[team] = (name, value)
    return best


def team_coverage(
    week: int,
    salary_path: str | Path,
    lineups_path: str | Path,
    *,
    season: int = 2026,
    threshold: float = DEFAULT_PRODUCED_THRESHOLD,
    pbp: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return one coverage row per slate team for one week.

    The slate team list comes from ``salary_path``. Book exposure comes from
    ``lineups_path``. The top scorer comes from actual play-by-play points.

    Columns: ``team``, ``book_exposure``, ``top_scorer_name``,
    ``top_scorer_points``, ``zero_exposure``, ``faded_and_produced``.
    """

    teams = slate_teams(salary_path, season, week)
    print(
        f"slate teams from {Path(salary_path)} (week {week}): {', '.join(teams)}",
        file=sys.stderr,
    )
    exposure = book_exposure_by_team(salary_path, lineups_path, season, week)
    frame = load_season_pbp(season) if pbp is None else pbp
    scorers = top_scorer_by_team(frame, season, week)

    records: list[dict[str, object]] = []
    for team in teams:
        rostered = int(exposure.get(team, 0))
        name, points = scorers.get(team, ("", 0.0))
        zero = rostered == 0
        produced = bool(zero and points >= float(threshold))
        records.append(
            {
                "team": team,
                "book_exposure": rostered,
                "top_scorer_name": name,
                "top_scorer_points": round(float(points), 2),
                "zero_exposure": zero,
                "faded_and_produced": produced,
            }
        )
    return pd.DataFrame(records, columns=TEAM_COVERAGE_COLUMNS)


def season_rollup(
    season: int,
    weeks: Iterable[int],
    *,
    salary_paths: dict[int, str | Path] | None = None,
    lineups_paths: dict[int, str | Path] | None = None,
    threshold: float = DEFAULT_PRODUCED_THRESHOLD,
) -> pd.DataFrame:
    """Count per team the weeks with zero exposure and a scorer at the threshold.

    The result is sorted by the count, descending. This shows repeat offenders.
    """

    salary_paths = salary_paths or {}
    lineups_paths = lineups_paths or {}
    counts: dict[str, int] = {}
    weeks_seen: dict[str, list[int]] = {}
    for week in weeks:
        salary_path = salary_paths.get(week) or default_salary_path(season, week)
        lineups_path = lineups_paths.get(week) or default_lineups_path(season, week)
        coverage = team_coverage(
            week,
            salary_path,
            lineups_path,
            season=season,
            threshold=threshold,
        )
        for _, row in coverage.iterrows():
            if not bool(row["faded_and_produced"]):
                continue
            team = str(row["team"])
            counts[team] = counts.get(team, 0) + 1
            weeks_seen.setdefault(team, []).append(week)

    records = [
        {
            "team": team,
            "faded_and_produced_weeks": count,
            "weeks": ",".join(str(item) for item in weeks_seen[team]),
        }
        for team, count in counts.items()
    ]
    frame = pd.DataFrame(
        records,
        columns=["team", "faded_and_produced_weeks", "weeks"],
    )
    if frame.empty:
        return frame
    return frame.sort_values(
        ["faded_and_produced_weeks", "team"],
        ascending=[False, True],
    ).reset_index(drop=True)


def _coverage_table(coverage: pd.DataFrame) -> list[str]:
    lines = [
        "| Team | Book exposure | Top scorer | Points | Zero exposure | Faded and produced |",
        "|------|---------------|------------|--------|---------------|--------------------|",
    ]
    for _, row in coverage.iterrows():
        lines.append(
            "| {team} | {book_exposure} | {name} | {points:.2f} | {zero} | {faded} |".format(
                team=row["team"],
                book_exposure=int(row["book_exposure"]),
                name=row["top_scorer_name"] or "(none)",
                points=float(row["top_scorer_points"]),
                zero="yes" if bool(row["zero_exposure"]) else "no",
                faded="YES" if bool(row["faded_and_produced"]) else "no",
            )
        )
    return lines


def _rollup_table(rollup: pd.DataFrame) -> list[str]:
    lines = [
        "| Team | Weeks faded and produced | Weeks |",
        "|------|--------------------------|-------|",
    ]
    if rollup.empty:
        lines.append("| (none) | 0 | |")
        return lines
    for _, row in rollup.iterrows():
        lines.append(
            f"| {row['team']} | {int(row['faded_and_produced_weeks'])} | {row['weeks']} |"
        )
    return lines


def _summary_lines(coverage: pd.DataFrame, threshold: float) -> list[str]:
    slate_n = len(coverage)
    zero_n = int(coverage["zero_exposure"].sum())
    faded_n = int(coverage["faded_and_produced"].sum())
    return [
        f"- Slate teams: {slate_n}",
        f"- Zero book exposure: {zero_n}",
        f"- Zero exposure and a scorer at or above {threshold:g}: {faded_n}",
    ]


def render_week_report(
    season: int,
    week: int,
    coverage: pd.DataFrame,
    *,
    salary_path: str | Path,
    lineups_path: str | Path,
    threshold: float = DEFAULT_PRODUCED_THRESHOLD,
) -> str:
    """Render the week report as markdown."""

    lines = [
        f"# Fade coverage — season {season} week {week}",
        "",
        f"Threshold: {threshold:g} points. A team is faded and produced when it has",
        "zero book exposure and its best actual scorer is at or above the threshold.",
        "",
        f"- Salary CSV (slate teams): `{salary_path}`",
        f"- Book lineups: `{lineups_path}`",
        f"- Slate teams read from the salary CSV: {', '.join(coverage['team'].astype(str))}",
        "",
        "## Counts",
        "",
        *_summary_lines(coverage, threshold),
        "",
        "## Per team",
        "",
        *_coverage_table(coverage),
        "",
    ]
    return "\n".join(lines)


def render_season_report(
    season: int,
    weeks: Sequence[int],
    coverage_by_week: dict[int, pd.DataFrame],
    rollup: pd.DataFrame,
    *,
    threshold: float = DEFAULT_PRODUCED_THRESHOLD,
    analysis: list[str] | None = None,
) -> str:
    """Render the season report with the per-week tables and the rollup."""

    lines = [
        f"# Fade coverage — season {season}",
        "",
        f"Threshold: {threshold:g} points. A team is faded and produced when it has",
        "zero book exposure and its best actual scorer is at or above the threshold.",
        "",
        "The slate teams come from each week's FanDuel salary CSV. Games outside the",
        "Sunday slate are not counted.",
        "",
    ]
    for week in weeks:
        coverage = coverage_by_week.get(week)
        if coverage is None:
            continue
        lines.extend(
            [
                f"## Week {week}",
                "",
                "Slate teams: "
                + ", ".join(coverage["team"].astype(str))
                + ".",
                "",
                *_summary_lines(coverage, threshold),
                "",
                *_coverage_table(coverage),
                "",
            ]
        )
    lines.extend(
        [
            "## Season rollup",
            "",
            "One row per team. The count is the number of weeks with zero exposure",
            f"and a scorer at or above {threshold:g}.",
            "",
            *_rollup_table(rollup),
            "",
        ]
    )
    if analysis:
        lines.extend(["## Analysis", "", *analysis, ""])
    return "\n".join(lines)


def write_week_report(
    season: int,
    week: int,
    coverage: pd.DataFrame,
    *,
    salary_path: str | Path,
    lineups_path: str | Path,
    threshold: float = DEFAULT_PRODUCED_THRESHOLD,
    out_dir: str | Path | None = None,
) -> Path:
    """Write ``reports/audit/fade-coverage-w{week}.md`` and return the path."""

    target_dir = Path(out_dir) if out_dir is not None else WEEK_REPORT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / WEEK_REPORT_TEMPLATE.format(week=week)
    text = render_week_report(
        season,
        week,
        coverage,
        salary_path=salary_path,
        lineups_path=lineups_path,
        threshold=threshold,
    )
    path.write_text(text, encoding="utf-8")
    return path


def write_season_report(
    season: int,
    weeks: Sequence[int],
    coverage_by_week: dict[int, pd.DataFrame],
    rollup: pd.DataFrame,
    *,
    threshold: float = DEFAULT_PRODUCED_THRESHOLD,
    analysis: list[str] | None = None,
    out_dir: str | Path | None = None,
) -> Path:
    """Write ``reports/audit/fade-coverage-season.md`` and return the path."""

    target_dir = Path(out_dir) if out_dir is not None else WEEK_REPORT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / SEASON_REPORT_NAME
    text = render_season_report(
        season,
        weeks,
        coverage_by_week,
        rollup,
        threshold=threshold,
        analysis=analysis,
    )
    path.write_text(text, encoding="utf-8")
    return path


def _season_weeks(season: int, pbp: pd.DataFrame | None = None) -> list[int]:
    """Return complete weeks that have both a salary file and actual games.

    A week is complete when a later week has already started. The current,
    unfinished week is not part of the season rollup.
    """

    frame = load_season_pbp(season) if pbp is None else pbp
    played = sorted(
        {
            int(week)
            for week in pd.to_numeric(frame.get("week"), errors="coerce").dropna().unique()
            if int(week) >= 1
        }
    )
    if not played:
        return []
    latest = max(played)
    return [
        week
        for week in played
        if week < latest and default_salary_path(season, week).is_file()
    ]


def _parse_weeks(value: str | None, season: int) -> list[int]:
    if not value:
        return _season_weeks(season)
    weeks: list[int] = []
    for token in str(value).split(","):
        token = token.strip()
        if not token:
            continue
        weeks.append(int(token))
    return weeks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ceminidfs.pipeline.fade_coverage",
        description="Measure book exposure per slate team and flag faded teams that produced",
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, default=None, help="One week to measure")
    parser.add_argument(
        "--salary",
        type=Path,
        default=None,
        help="Salary CSV for the week (default: the 2026 slate file)",
    )
    parser.add_argument(
        "--lineups",
        type=Path,
        default=None,
        help="Book lineups CSV (default: runs/<season>_week_<week>/lineups.csv)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_PRODUCED_THRESHOLD,
        help=f"Produced threshold in points (default {DEFAULT_PRODUCED_THRESHOLD:g})",
    )
    parser.add_argument(
        "--weeks",
        default=None,
        help="Comma-separated weeks for the season rollup (default: every week with games)",
    )
    parser.add_argument(
        "--season-rollup",
        action="store_true",
        help="Write reports/audit/fade-coverage-season.md and the week files",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Report directory (default: reports/audit)",
    )
    args = parser.parse_args(argv)

    try:
        if args.season_rollup:
            weeks = _parse_weeks(args.weeks, args.season)
            coverage_by_week: dict[int, pd.DataFrame] = {}
            for week in weeks:
                salary_path = args.salary or default_salary_path(args.season, week)
                lineups_path = args.lineups or default_lineups_path(args.season, week)
                coverage = team_coverage(
                    week,
                    salary_path,
                    lineups_path,
                    season=args.season,
                    threshold=args.threshold,
                )
                coverage_by_week[week] = coverage
                path = write_week_report(
                    args.season,
                    week,
                    coverage,
                    salary_path=salary_path,
                    lineups_path=lineups_path,
                    threshold=args.threshold,
                    out_dir=args.out_dir,
                )
                print(f"wrote {path}")
            rollup = season_rollup(
                args.season,
                weeks,
                threshold=args.threshold,
            )
            from ceminidfs.pipeline.fade_analysis import build_analysis

            analysis = build_analysis(
                args.season,
                coverage_by_week,
                threshold=args.threshold,
            )
            path = write_season_report(
                args.season,
                weeks,
                coverage_by_week,
                rollup,
                threshold=args.threshold,
                analysis=analysis,
                out_dir=args.out_dir,
            )
            print(f"wrote {path}")
            return 0

        if args.week is None:
            parser.error("--week is required unless --season-rollup is set")
        salary_path = args.salary or default_salary_path(args.season, args.week)
        lineups_path = args.lineups or default_lineups_path(args.season, args.week)
        coverage = team_coverage(
            args.week,
            salary_path,
            lineups_path,
            season=args.season,
            threshold=args.threshold,
        )
        path = write_week_report(
            args.season,
            args.week,
            coverage,
            salary_path=salary_path,
            lineups_path=lineups_path,
            threshold=args.threshold,
            out_dir=args.out_dir,
        )
        print(coverage.to_string(index=False))
        print(f"wrote {path}")
        return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
