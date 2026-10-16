"""Home-field shrink sensitivity table for the team drive simulation.

This script reports total MAE and margin MAE for model A and model B at four
home-field shrink values. It writes only ``outputs/hfa_sensitivity.txt``.

It is a shadow study. It does not bet, post, or submit anything. It does not
change the live model.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

WORKDIR = Path(__file__).resolve().parent.parent
if str(WORKDIR / "src") not in sys.path:
    sys.path.insert(0, str(WORKDIR / "src"))

import team_sim  # noqa: E402

SHRINKS = (0.0, 0.25, 0.50, 0.75)
SEED = 20261016
RUNS = 2000
TARGET_SHRINK = 0.50
TARGETS = {
    "a_total": 12.47,
    "a_margin": 10.13,
    "b_total": 10.35,
    "b_margin": 9.40,
}
TOLERANCE = 0.05


def build_rows(
    drives: pd.DataFrame,
    season_sched: pd.DataFrame,
    pbp: pd.DataFrame,
    games: pd.DataFrame,
    cutoff_of: Callable[[pd.Series], int],
    models: dict[int, dict[str, Any]],
    kind: str,
) -> list[dict[str, Any]]:
    """Build one simulation row per game for the given model cutoffs."""
    rows: list[dict[str, Any]] = []
    for _, game in games.sort_values("game_id").iterrows():
        cutoff = int(cutoff_of(game))
        if cutoff not in models:
            models[cutoff] = team_sim.build_model(drives, season_sched, pbp, cutoff)
        model = models[cutoff]
        home = str(game["home_team"])
        away = str(game["away_team"])
        teams = model["teams"]
        home_rate = teams.get(home, {}).get("rate", model["league_drives"])
        away_rate = teams.get(away, {}).get("rate", model["league_drives"])
        mu = (
            float(np.mean([home_rate, away_rate]))
            if np.isfinite(home_rate) and np.isfinite(away_rate)
            else 0.0
        )

        home_probs = team_sim.side_probs(model, home, away)
        away_probs = team_sim.side_probs(model, away, home)
        hfa = model["hfa"]
        home_probs = team_sim.finalize(
            np.array([home_probs[0] * hfa, home_probs[1] * hfa, home_probs[2], home_probs[3], 0.0])
        )
        away_probs = team_sim.finalize(
            np.array([away_probs[0] / hfa, away_probs[1] / hfa, away_probs[2], away_probs[3], 0.0])
        )

        # ---- variant B: scale td/fg to the implied team total ----
        b_home = home_probs.copy()
        b_away = away_probs.copy()
        implied = team_sim.implied_team_totals_from_schedule_row(game)
        home_target = implied.get("home_implied_total")
        away_target = implied.get("away_implied_total")
        expected_drives = mu + 0.5
        if home_target is None or away_target is None:
            print(f"B_SKIP {game['game_id']} missing implied total")
        else:
            home_scale = team_sim.solve_scale(
                float(home_target), expected_drives, home_probs, model["td_points"]
            )
            away_scale = team_sim.solve_scale(
                float(away_target), expected_drives, away_probs, model["td_points"]
            )
            if not np.isfinite(home_scale) or not np.isfinite(away_scale):
                print(f"B_SKIP {game['game_id']} non-finite scale")
            else:
                max_home = 1.0 / max(float(np.max(home_probs[:2])), 1e-12)
                max_away = 1.0 / max(float(np.max(away_probs[:2])), 1e-12)
                home_scale = min(home_scale, max_home)
                away_scale = min(away_scale, max_away)
                b_home = team_sim.apply_scale(home_probs, home_scale)
                b_away = team_sim.apply_scale(away_probs, away_scale)

        rows.append(
            {
                "game_id": str(game["game_id"]),
                "kind": kind,
                "home_score": float(game["home_score"]),
                "away_score": float(game["away_score"]),
                "mu": mu,
                "td_points": model["td_points"],
                "a_home_probs": home_probs,
                "a_away_probs": away_probs,
                "b_home_probs": b_home,
                "b_away_probs": b_away,
            }
        )
    return rows


def mae_pair(
    results: list[dict[str, np.ndarray]],
    rows: list[dict[str, Any]],
    indexes: list[int],
) -> tuple[float, float]:
    """Return total MAE and margin MAE on the given games. Ties stay in."""
    total_error: list[float] = []
    margin_error: list[float] = []
    for index in indexes:
        result = results[index]
        home = result["home"].astype(float)
        away = result["away"].astype(float)
        total_pred = float((home + away).mean())
        margin_pred = float((home - away).mean())
        actual_total = float(rows[index]["home_score"]) + float(rows[index]["away_score"])
        actual_margin = float(rows[index]["home_score"]) - float(rows[index]["away_score"])
        total_error.append(abs(total_pred - actual_total))
        margin_error.append(abs(margin_pred - actual_margin))
    return float(np.mean(total_error)), float(np.mean(margin_error))


def run_shrink(
    shrink: float,
    drives: pd.DataFrame,
    season_sched: pd.DataFrame,
    pbp: pd.DataFrame,
    backtest_games: pd.DataFrame,
    upcoming_games: pd.DataFrame,
    current_week: int,
) -> dict[str, float]:
    """Simulate one shrink value and return the four MAE values."""
    team_sim.HFA_SHRINK = float(shrink)
    models: dict[int, dict[str, Any]] = {}
    rows = build_rows(
        drives, season_sched, pbp, backtest_games, lambda game: int(game["week"]), models, "backtest"
    )
    # The upcoming games do not enter the metrics. They stay in the run so that
    # the random number stream matches the live model.
    rows += build_rows(
        drives, season_sched, pbp, upcoming_games, lambda game: current_week, models, "upcoming"
    )
    backtest_indexes = [index for index, row in enumerate(rows) if row["kind"] == "backtest"]

    rng = np.random.default_rng(SEED)
    results_a = team_sim.simulate_variant(rows, "a", rng)
    team_sim.add_overtime(results_a, rng)
    results_b = team_sim.simulate_variant(rows, "b", rng)
    team_sim.add_overtime(results_b, rng)

    a_total, a_margin = mae_pair(results_a, rows, backtest_indexes)
    b_total, b_margin = mae_pair(results_b, rows, backtest_indexes)
    return {"a_total": a_total, "a_margin": a_margin, "b_total": b_total, "b_margin": b_margin}


def format_table(rows: list[tuple[float, dict[str, float]]]) -> str:
    """Return the sensitivity table as text."""
    lines = [
        f"home-field shrink sensitivity (backtest, seed {SEED}, runs {RUNS})",
        f"{'shrink':>7} {'A_total':>9} {'A_margin':>9} {'B_total':>9} {'B_margin':>9}",
    ]
    for shrink, metrics in rows:
        lines.append(
            f"{shrink:>7.2f} {metrics['a_total']:>9.2f} {metrics['a_margin']:>9.2f} "
            f"{metrics['b_total']:>9.2f} {metrics['b_margin']:>9.2f}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    season, season_sched, pbp = team_sim.load_inputs()

    has_scores = season_sched["home_score"].notna() & season_sched["away_score"].notna()
    unscored = season_sched[~has_scores]
    current_week = int(unscored["week"].min())
    backtest_games = season_sched[
        (season_sched["week"] > 1) & (season_sched["week"] <= current_week) & has_scores
    ].copy()
    upcoming_games = season_sched[(season_sched["week"] == current_week) & ~has_scores].copy()
    drives = team_sim.build_drives(pbp)
    print(
        f"season {season} current_week {current_week} "
        f"backtest games {len(backtest_games)} upcoming games {len(upcoming_games)}"
    )

    table: list[tuple[float, dict[str, float]]] = []
    for shrink in SHRINKS:
        metrics = run_shrink(
            shrink, drives, season_sched, pbp, backtest_games, upcoming_games, current_week
        )
        table.append((shrink, metrics))
        print(
            f"shrink {shrink:.2f} A_total {metrics['a_total']:.2f} A_margin {metrics['a_margin']:.2f} "
            f"B_total {metrics['b_total']:.2f} B_margin {metrics['b_margin']:.2f}"
        )

    text = format_table(table)
    print("")
    print(text, end="")
    out_path = WORKDIR / "outputs" / "hfa_sensitivity.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"wrote {out_path}")

    # ---- sanity check: the live shrink row must match the current backtest ----
    live = dict(table)[TARGET_SHRINK]
    misses = {
        key: abs(live[key] - target)
        for key, target in TARGETS.items()
        if abs(live[key] - target) > TOLERANCE
    }
    if misses:
        print(f"HFA_CHECK_FAIL shrink {TARGET_SHRINK:.2f} misses {misses}")
        return 1
    print(f"HFA_CHECK_OK shrink {TARGET_SHRINK:.2f} matches the current backtest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
