"""Score the upcoming team-sim games against final scores (phase T6).

This script joins a finals CSV to ``outputs/team_proj_upcoming.csv`` and scores
the 13 upcoming rows with ``team_sim.model_metrics``. It does not resimulate and
does not retune a scale, a shrink, or a seed.

It reads only:

- ``outputs/team_proj_upcoming.csv``
- ``outputs/team_backtest.csv``

It writes only the ``--out`` file. It never changes the two source files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

WORKDIR = Path(__file__).resolve().parent.parent
if str(WORKDIR / "src") not in sys.path:
    sys.path.insert(0, str(WORKDIR / "src"))

import team_sim  # noqa: E402  (needs the src path above)

UPCOMING_PATH = WORKDIR / "outputs/team_proj_upcoming.csv"
BACKTEST_PATH = WORKDIR / "outputs/team_backtest.csv"
DEFAULT_OUT = WORKDIR / "outputs/team_backtest_appended.csv"
MODELS = ("A", "B", "Vegas", "Blend_A_Vegas")


def fail(message: str) -> int:
    """Print the failure reason and the failure marker. Return exit code 2."""
    print(f"SCORE_FAIL {message}")
    return 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score upcoming team-sim games against finals.")
    parser.add_argument("--finals", required=True, help="CSV with game_id, home_score, away_score")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="append output CSV path")
    return parser.parse_args(argv)


def load_finals(path: Path) -> pd.DataFrame:
    """Read the finals CSV and return one finite score row per game_id."""
    frame = pd.read_csv(path)
    missing = {"game_id", "home_score", "away_score"} - set(frame.columns)
    if missing:
        raise ValueError(f"finals file lacks columns {sorted(missing)}")
    frame = frame[["game_id", "home_score", "away_score"]].copy()
    frame["game_id"] = frame["game_id"].astype(str)
    frame["home_score"] = pd.to_numeric(frame["home_score"], errors="coerce")
    frame["away_score"] = pd.to_numeric(frame["away_score"], errors="coerce")
    return frame


def scored_upcoming(upcoming: pd.DataFrame, finals: pd.DataFrame) -> pd.DataFrame:
    """Return the upcoming rows with the final scores joined in."""
    upcoming_ids = upcoming["game_id"].astype(str)
    counts = finals["game_id"].value_counts()
    duplicated = [game_id for game_id in upcoming_ids if int(counts.get(game_id, 0)) > 1]
    if duplicated:
        raise ValueError(f"finals has duplicate game_id {sorted(set(duplicated))}")
    lookup = finals.set_index("game_id")
    absent = [game_id for game_id in upcoming_ids if game_id not in lookup.index]
    if absent:
        raise ValueError(f"finals misses game_id {absent}")
    home = lookup.loc[upcoming_ids, "home_score"].to_numpy(dtype=float)
    away = lookup.loc[upcoming_ids, "away_score"].to_numpy(dtype=float)
    if not (np.isfinite(home).all() and np.isfinite(away).all()):
        raise ValueError("finals has a non-finite score")

    scored = upcoming.copy()
    scored["home_score"] = home
    scored["away_score"] = away
    return scored


def score_rows(scored: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Score the joined rows with the team_sim model metrics."""
    actual_home = scored["home_score"].to_numpy(dtype=float)
    actual_away = scored["away_score"].to_numpy(dtype=float)
    actual_total = actual_home + actual_away
    actual_margin = actual_home - actual_away

    wp_a = scored["a_home_wp"].to_numpy(dtype=float)
    wp_b = scored["b_home_wp"].to_numpy(dtype=float)
    vegas_wp = scored["vegas_home_wp"].to_numpy(dtype=float)
    blend_wp = (wp_a + vegas_wp) / 2.0

    total_a = scored["a_total_mean"].to_numpy(dtype=float)
    margin_a = scored["a_margin_mean"].to_numpy(dtype=float)
    total_b = scored["b_total_mean"].to_numpy(dtype=float)
    margin_b = scored["b_margin_mean"].to_numpy(dtype=float)
    vegas_total = scored["total_line"].to_numpy(dtype=float)
    vegas_margin = scored["spread_line"].to_numpy(dtype=float)

    return {
        "A": team_sim.model_metrics(
            total_a,
            margin_a,
            wp_a,
            actual_total,
            actual_margin,
            (actual_total >= scored["a_total_p15"].to_numpy(dtype=float))
            & (actual_total <= scored["a_total_p85"].to_numpy(dtype=float)),
        ),
        "B": team_sim.model_metrics(
            total_b,
            margin_b,
            wp_b,
            actual_total,
            actual_margin,
            (actual_total >= scored["b_total_p15"].to_numpy(dtype=float))
            & (actual_total <= scored["b_total_p85"].to_numpy(dtype=float)),
        ),
        "Vegas": team_sim.model_metrics(
            vegas_total,
            vegas_margin,
            vegas_wp,
            actual_total,
            actual_margin,
            None,
        ),
        "Blend_A_Vegas": team_sim.model_metrics(
            (total_a + vegas_total) / 2.0,
            (margin_a + vegas_margin) / 2.0,
            blend_wp,
            actual_total,
            actual_margin,
            None,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    print(f"WORKDIR {WORKDIR}")
    print(f"INTERPRETER {sys.executable}")

    args = parse_args(argv)
    try:
        finals = load_finals(Path(args.finals))
    except (OSError, ValueError, pd.errors.ParserError) as error:
        return fail(str(error))

    upcoming = pd.read_csv(UPCOMING_PATH)
    backtest = pd.read_csv(BACKTEST_PATH)
    try:
        scored = scored_upcoming(upcoming, finals)
    except (ValueError, KeyError) as error:
        return fail(str(error))

    metrics = score_rows(scored)

    print("")
    print("metric table (upcoming)")
    print(f"{'model':<16} {'totMAE':>9} {'marMAE':>10} {'winAcc':>8} {'Brier':>7} {'logLoss':>9} {'cover':>9}")
    for name in MODELS:
        print(team_sim.metric_row(name, metrics[name]))

    appended = pd.concat([backtest, scored], ignore_index=True)
    appended = appended.sort_values("game_id").reset_index(drop=True)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = WORKDIR / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    appended.to_csv(out_path, index=False, float_format="%.6f", lineterminator="\n")

    print("")
    print(f"wrote {out_path} rows {len(appended)}")
    print("SCORE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
