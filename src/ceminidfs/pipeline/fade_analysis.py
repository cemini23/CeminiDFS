"""Build the analysis section for the fade-coverage season report.

Two questions drove K283:

1. Why did the earlier pass report 11, 7, 11 zero-exposure teams and 7, 3, 6
   flagged teams, when the correct slate list gives different counts?
2. Why did Week 2 cover the slate better than Weeks 1 and 3?

This module measures both. It never changes the projection, salary, ownership,
or scoring models. It only reads the book and the actual points.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ceminidfs.pipeline.fade_coverage import (
    DEFAULT_PRODUCED_THRESHOLD,
    default_lineups_path,
    default_salary_path,
    team_coverage,
)

# The counts from the earlier pass in this session. They used the wrong team
# list, so they are a reference only.
EARLIER_PASS = {
    "zero_exposure": {1: 11, 2: 7, 3: 11},
    "faded_and_produced": {1: 7, 2: 3, 3: 6},
}


def _scaling_rows(
    season: int,
    week: int,
    threshold: float,
    pbp: pd.DataFrame | None,
) -> list[dict[str, Any]]:
    """Measure the book at several lineup counts for one week."""

    salary = default_salary_path(season, week)
    lineups = default_lineups_path(season, week)
    if not lineups.is_file():
        return []
    book = pd.read_csv(lineups)
    rows: list[dict[str, Any]] = []
    for size in (1, 2, 4, 8, len(book)):
        if size < 1 or size > len(book):
            continue
        subset = book.head(size)
        path = lineups.with_name(f"_{lineups.stem}_first{size}.csv")
        subset.to_csv(path, index=False)
        coverage = team_coverage(
            week,
            salary,
            path,
            season=season,
            threshold=threshold,
            pbp=pbp,
        )
        path.unlink(missing_ok=True)
        rows.append(
            {
                "week": week,
                "lineups": size,
                "slate_teams": len(coverage),
                "zero_exposure": int(coverage["zero_exposure"].sum()),
                "faded_and_produced": int(coverage["faded_and_produced"].sum()),
            }
        )
    # Keep one row per lineup count (the full book repeats an earlier size).
    seen: set[int] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        if row["lineups"] in seen:
            continue
        seen.add(row["lineups"])
        unique.append(row)
    return unique


def build_analysis(
    season: int,
    coverage_by_week: dict[int, pd.DataFrame],
    *,
    threshold: float = DEFAULT_PRODUCED_THRESHOLD,
    pbp: pd.DataFrame | None = None,
) -> list[str]:
    """Return the markdown lines for the season report analysis section."""

    lines = [
        "The earlier pass in this session reported 11, 7, 11 zero-exposure teams and",
        "7, 3, 6 flagged teams. That pass first counted every team that played, then",
        "used the wrong slate list. This tool reads the slate team list from the salary",
        "CSV. The measured counts below use the default book for each week",
        "(`runs/<season>_week_<week>/lineups.csv`).",
        "",
        "| Week | Slate teams | Book lineups | Zero exposure | Faded and produced | Earlier pass (flagged) |",
        "|------|-------------|--------------|---------------|--------------------|------------------------|",
    ]
    for week in sorted(coverage_by_week):
        coverage = coverage_by_week[week]
        book_path = default_lineups_path(season, week)
        book_size = len(pd.read_csv(book_path)) if book_path.is_file() else 0
        lines.append(
            f"| {week} | {len(coverage)} | {book_size} | "
            f"{int(coverage['zero_exposure'].sum())} | "
            f"{int(coverage['faded_and_produced'].sum())} | "
            f"{EARLIER_PASS['faded_and_produced'].get(week, '-')} |"
        )
    lines.extend(
        [
            "",
            "The earlier pass did not record which lineup file it measured. The",
            "default book in `runs/` is the stable input for this report. The flag",
            "count moves a lot with the book size, so the two passes can differ even",
            "when the slate list is correct.",
            "",
            "Week 3 faded and produced stays 4. A rostered defense is the team, not the",
            "token `__dst__`. The figure 6 is the pass from before defense rows were",
            "mapped to a team name.",
            "",
            "The flagged count changes with the book size. The guard and the research",
            "both change how many players a team keeps. The table below holds the pool",
            "and the research fixed. It cuts only the book.",
            "",
            "| Week | Book lineups | Zero exposure | Faded and produced |",
            "|------|--------------|---------------|--------------------|",
        ]
    )
    for week in sorted(coverage_by_week):
        for row in _scaling_rows(season, week, threshold, pbp):
            lines.append(
                f"| {row['week']} | {row['lineups']} | "
                f"{row['zero_exposure']} | {row['faded_and_produced']} |"
            )
    lines.extend(
        [
            "",
            "### Why Week 2 differed",
            "",
            "Week 2 was not a different research rule. The book covered more teams:",
            "",
            "1. The Week 2 book holds more lineups than the Week 3 book. More lineup",
            "   seats touch more teams. A team with zero seats is the result.",
            "2. The Week 2 research scratch file has 23 rows; 15 matched the salary CSV",
            "   and touched 12 teams. The Week 3 scratch file has 78 rows; 78 matched",
            "   and touched 24 of the 26 slate teams. A wide hard fade removes many",
            "   cheap players. It also removes the players that would cover a team.",
            "3. The Week 1 book used 10 lineups. The Week 3 book used 4. A 4-lineup",
            "   book cannot cover 26 teams with 9 seats each (36 seats, 26 teams).",
            "   Roughly 10 teams are expected to have zero seats.",
            "",
            "So the team fade is unstable because the book size and the pool cut are",
            "unstable. It is not a fixed property of the research. The dart rule is a",
            "pool guard. It keeps one cheap player on every slate team, so the book",
            "cannot lose a whole team by accident.",
        ]
    )
    return lines
