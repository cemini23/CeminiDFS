"""Plain-text matchup report for one pre-game slate."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from ceminidfs.situational.backtest import format_calibration_table, format_fdr_table
from ceminidfs.situational.engine import HOLD_TIME_SECONDS

_INJURY_COLUMNS = (
    "player_name",
    "team",
    "position",
    "injury_status",
    "lagged_fd",
    "vacated_target_boost",
    "vacated_rz_boost",
)
_DST_COLUMNS = (
    "player_name",
    "team",
    "opp",
    "lagged_fd",
    "p90",
    "p99",
    "p_dst_10",
    "avg_time_to_throw",
    "dst_flag",
)


def format_matchup_report(result: dict[str, Any]) -> str:
    """Return the slate report. The same inputs always return the same text."""

    calibration = result["calibration"]
    scored = result["scored"]
    audit = result.get("feature_audit") or {}
    cache = result.get("cache") or {}
    lines = [
        f"slate {result.get('season')} week {result.get('week')}",
        f"salary {result.get('salary_path')}",
        (
            f"feature rows {audit.get('player_rows', 0)}  "
            f"max prior week {audit.get('max_week_same_season')}  "
            f"lookahead_ok {str(bool(audit.get('lookahead_ok'))).lower()}"
        ),
        "cache used " + ", ".join(cache.get("used") or []),
        "cache missing " + (", ".join(cache.get("missing") or []) or "-"),
        "Ownership is not in the cache. This report does not rank by ownership.",
        (
            "A situational weight is 0 unless one FDR survivor has a positive holdout Brier gain. "
            "The gain interval must be above 0. A holdout under 500 rows can pass when "
            "the point lift is at least 0.40, the top decile rises, and 80 percent of "
            "bootstrap draws are positive."
        ),
        "",
        format_calibration_table(calibration),
        "",
        format_fdr_table(calibration),
        "",
        _section("Top GPP ceiling", _top_ceiling(scored)),
        "",
        _section("100-yard and 300-yard bonus", _bonus_rows(scored)),
        "",
        _section("Q3 script", _flag_rows(scored, "q3_flag")),
        "",
        _section("Q4 bring-back", _flag_rows(scored, "q4_flag")),
        "",
        _section("Injury vacuum", _injury_rows(scored), _INJURY_COLUMNS),
        "",
        _section("Week DST", _dst_rows(scored), _DST_COLUMNS),
        "",
        _section(
            f"DST hold-time over {HOLD_TIME_SECONDS:.2f}s",
            _flag_rows(scored, "dst_flag"),
        ),
        "",
        _spearman_section(scored),
        "",
        _boost_section(result.get("boosts"), calibration),
    ]
    return "\n".join(lines)


def _top_ceiling(scored: pd.DataFrame) -> pd.DataFrame:
    if scored.empty:
        return scored
    work = scored.sort_values(["p99", "player_id"], ascending=[False, True], kind="mergesort")
    return work.head(15)


def _bonus_rows(scored: pd.DataFrame) -> pd.DataFrame:
    if scored.empty:
        return scored
    work = scored.copy()
    work["bonus"] = work[["p_rec_100", "p_rush_100", "p_pass_300"]].max(axis=1)
    # A sleeper is a player whose lagged mean is below the bonus threshold.
    modest = work["lagged_fd"].lt(18)
    work = work.loc[modest].sort_values(
        ["bonus", "player_id"],
        ascending=[False, True],
        kind="mergesort",
    )
    return work.head(15)


def _flag_rows(scored: pd.DataFrame, column: str) -> pd.DataFrame:
    if scored.empty or column not in scored.columns:
        return scored.iloc[0:0] if not scored.empty else scored
    work = scored.loc[scored[column].astype(bool)].copy()
    return work.sort_values(["p99", "player_id"], ascending=[False, True], kind="mergesort")


def _injury_rows(scored: pd.DataFrame) -> pd.DataFrame:
    if scored.empty or "injury_status" not in scored.columns:
        return scored.iloc[0:0] if not scored.empty else scored
    status = scored["injury_status"].astype(str).str.upper()
    work = scored.loc[status.isin(["OUT", "IR", "DOUBTFUL"])].copy()
    return work.sort_values(["injury_status", "player_name"], kind="mergesort")


def _dst_rows(scored: pd.DataFrame) -> pd.DataFrame:
    if scored.empty or "position" not in scored.columns:
        return scored.iloc[0:0] if not scored.empty else scored
    work = scored.loc[scored["position"].astype(str).eq("DST")].copy()
    return work.sort_values(["team", "player_id"], kind="mergesort")


def _spearman_section(scored: pd.DataFrame) -> str:
    lines = ["Spearman p90 and p99 vs lagged_fd"]
    if scored.empty or "position" not in scored.columns:
        lines.append("  none")
        return "\n".join(lines)
    for position, part in scored.groupby("position", sort=True):
        work = part.loc[:, ["lagged_fd", "p90", "p99"]].apply(pd.to_numeric, errors="coerce")
        work = work.loc[work["lagged_fd"].gt(0)].dropna()
        if len(work) < 3:
            continue
        rho90 = work["p90"].corr(work["lagged_fd"], method="spearman")
        rho99 = work["p99"].corr(work["lagged_fd"], method="spearman")
        lines.append(f"  {position:<6} n={len(work):>4}  p90={rho90:.3f}  p99={rho99:.3f}")
    if len(lines) == 1:
        lines.append("  none")
    return "\n".join(lines)


def _section(title: str, frame: pd.DataFrame, columns: tuple[str, ...] | None = None) -> str:
    lines = [title]
    if frame is None or frame.empty:
        lines.append("  none")
        return "\n".join(lines)
    default_columns = (
        "player_name",
        "team",
        "position",
        "salary",
        "fppg",
        "lagged_fd",
        "p90",
        "p99",
        "p_rec_100",
        "p_rush_100",
        "p_pass_300",
        "p_multi_td",
        "q3_flag",
        "q4_flag",
        "dst_flag",
    )
    chosen = columns or default_columns
    show = [column for column in chosen if column in frame.columns]
    header = "  " + "  ".join(
        f"{column:>22}" if column == "player_name" else f"{column:>12}" for column in show
    )
    lines.append(header)
    for row in frame.to_dict(orient="records"):
        cells = []
        for column in show:
            width = 22 if column == "player_name" else 12
            cells.append(f"{_cell(row.get(column)):>{width}}")
        lines.append("  " + "  ".join(cells))
    return "\n".join(lines)


def _boost_section(boosts: pd.DataFrame | None, calibration: dict[str, Any]) -> str:
    lines = ["Correlation boost"]
    for kind, estimate in (calibration.get("correlation") or {}).items():
        lines.append(
            f"  {kind:<16} boost={float(estimate.get('boost') or 0.0):+.3f}  "
            f"test_improved={str(bool(estimate.get('test_improved'))).lower()}"
        )
    if boosts is None or boosts.empty:
        lines.append("  flagged pairs none")
        return "\n".join(lines)
    lines.append(f"  flagged pairs {len(boosts)}")
    for row in boosts.head(20).to_dict(orient="records"):
        lines.append(
            f"  {row.get('kind'):<16} {row.get('player_a')} {row.get('player_b')}  "
            f"{float(row.get('corr_boost') or 0.0):+.3f}"
        )
    return "\n".join(lines)


def _cell(value: object) -> str:
    if isinstance(value, (bool,)):
        return "yes" if value else "no"
    if isinstance(value, str):
        return value.strip()
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(number):
        return "-"
    if abs(number) >= 1000:
        return f"{number:.0f}"
    return f"{number:.3f}"
