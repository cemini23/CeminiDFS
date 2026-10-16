"""Team-level drive simulation backtest (phase 1, shadow model).

Walk-forward game simulation from nflverse drive data. This script writes only:

- ``outputs/team_backtest.csv``
- ``outputs/team_proj_upcoming.csv``
- ``team_meta.json``

It is a shadow model. It does not bet, post, or submit anything.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.stats import norm

WORKDIR = Path(__file__).resolve().parent.parent
if str(WORKDIR / "src") not in sys.path:
    sys.path.insert(0, str(WORKDIR / "src"))

from ceminidfs.data.vegas import implied_team_totals_from_schedule_row  # noqa: E402

SEED = 20261016
RUNS = 2000
BAND_SCALE_MIN = 0.20
BAND_SCALE_MAX = 1.00
BAND_SCALE_STEP = 0.005
BAND_15_TARGET = 0.70
BAND_10_TARGET = 0.80
BAND_15_LO = 0.65
BAND_15_HI = 0.75
BAND_10_LO = 0.78
BAND_10_HI = 0.84
K_DRIVES = 40
HFA_SHRINK = 0.5
SPREAD_SIGMA = 13.5
BOOTSTRAP_DRAWS = 5000
BOOTSTRAP_SEED = 20261017
PAT_XP_FALLBACK = 0.94
PAT_TRY_FALLBACK = 0.05
PAT_SUCCESS_FALLBACK = 0.48
PBP_URL = "https://github.com/nflverse/nflverse-data/releases/tag/pbp"
SCHEDULES_URL = "https://github.com/nflverse/nfldata"

OUTCOMES = ("td", "fg", "opp_td", "safety", "none")
FOUR = ("td", "fg", "opp_td", "safety")
RESULT_MAP = {
    "Touchdown": "td",
    "Field goal": "fg",
    "Opp touchdown": "opp_td",
    "Safety": "safety",
}
PROJECTION_COLUMNS = [
    "home_mean",
    "away_mean",
    "total_mean",
    "margin_mean",
    "home_wp",
    "home_median",
    "away_median",
    "total_p10",
    "total_p15",
    "total_p85",
    "total_p90",
]
BACKTEST_COLUMNS = [
    "game_id",
    "season",
    "week",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "spread_line",
    "total_line",
    "vegas_home_wp",
] + [f"a_{name}" for name in PROJECTION_COLUMNS] + [f"b_{name}" for name in PROJECTION_COLUMNS]
UPCOMING_COLUMNS = [
    "game_id",
    "season",
    "week",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "spread_line",
    "total_line",
    "vegas_home_wp",
] + [f"a_{name}" for name in PROJECTION_COLUMNS] + [f"b_{name}" for name in PROJECTION_COLUMNS]

PUBLISHED_TARGETS = {
    "A": [12.78, 10.06, 0.587, 0.246, 0.683, 0.889],
    "B": [10.33, 9.46, 0.603, 0.233, 0.658, 0.937],
    "Vegas": [10.31, 9.43, 0.603, 0.234, 0.661, None],
    "Blend_A_Vegas": [11.32, 9.66, 0.571, 0.234, 0.660, None],
}


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def to_pandas(frame: Any) -> pd.DataFrame:
    """Return a pandas DataFrame from a polars or pandas frame."""
    if hasattr(frame, "to_pandas"):
        return frame.to_pandas()
    return pd.DataFrame(frame)


def safe_ratio(numerator: float, denominator: float, fallback: float = 0.0) -> float:
    if denominator == 0 or not np.isfinite(denominator) or not np.isfinite(numerator):
        return fallback
    value = numerator / denominator
    return float(value) if np.isfinite(value) else fallback


def clipped_wp(probability: float) -> float:
    return float(np.clip(probability, 1e-15, 1.0 - 1e-15))


def load_inputs() -> tuple[int, pd.DataFrame, pd.DataFrame]:
    """Load schedules and pbp. Derive the season from the schedule."""
    import nflreadpy as nfl

    schedules = to_pandas(nfl.load_schedules(seasons=True))
    schedules = schedules[schedules["game_type"] == "REG"].copy()
    schedules["home_score"] = pd.to_numeric(schedules["home_score"], errors="coerce")
    schedules["away_score"] = pd.to_numeric(schedules["away_score"], errors="coerce")
    scored = schedules[schedules["home_score"].notna() & schedules["away_score"].notna()]
    season = int(scored["season"].max())
    season_sched = schedules[schedules["season"] == season].copy().sort_values("game_id").reset_index(drop=True)

    pbp = to_pandas(nfl.load_pbp(seasons=[season]))
    pbp = pbp[pbp["season_type"] == "REG"].copy()
    pbp = pbp.sort_values(["game_id", "fixed_drive", "play_id"]).reset_index(drop=True)
    return season, season_sched, pbp


def build_drives(pbp: pd.DataFrame) -> pd.DataFrame:
    """Build one row per (game_id, fixed_drive) with a posteam and a result."""
    mask = pbp["fixed_drive"].notna() & pbp["posteam"].notna() & pbp["fixed_drive_result"].notna()
    drives = pbp.loc[
        mask, ["game_id", "week", "fixed_drive", "posteam", "defteam", "fixed_drive_result"]
    ].copy()
    drives = drives.drop_duplicates(subset=["game_id", "fixed_drive"], keep="first")
    drives["result"] = drives["fixed_drive_result"].map(RESULT_MAP).fillna("none")
    return drives.reset_index(drop=True)


def outcome_rates(drives: pd.DataFrame) -> dict[str, float]:
    total = len(drives)
    if total == 0:
        return {label: 0.0 for label in OUTCOMES}
    counts = drives["result"].value_counts()
    return {label: float(counts.get(label, 0)) / total for label in OUTCOMES}


def pat_rates(pbp: pd.DataFrame, game_ids: set[str]) -> tuple[dict[str, float], bool]:
    """Return league PAT rates for the given prior games."""
    prior = pbp[pbp["game_id"].isin(game_ids)]
    xp_att = prior[prior["extra_point_attempt"] == 1]
    tp_att = prior[prior["two_point_attempt"] == 1]
    xp_den = len(xp_att)
    tp_den = len(tp_att)
    if xp_den == 0 or tp_den == 0 or (xp_den + tp_den) == 0:
        print("PAT_FALLBACK")
        return (
            {"xp_make": PAT_XP_FALLBACK, "try_rate": PAT_TRY_FALLBACK, "tp_success": PAT_SUCCESS_FALLBACK},
            True,
        )
    xp_make = float((xp_att["extra_point_result"] == "good").mean())
    tp_success = float((tp_att["two_point_conv_result"] == "success").mean())
    try_rate = tp_den / (xp_den + tp_den)
    return {"xp_make": xp_make, "try_rate": try_rate, "tp_success": tp_success}, False


def pat_value(rates: dict[str, float]) -> float:
    """Expected PAT points per touchdown."""
    return rates["xp_make"] + rates["try_rate"] * rates["tp_success"]


def finalize(probs: np.ndarray) -> np.ndarray:
    """Clip at 0, set none to the remainder, and rescale when none is negative."""
    out = np.array(probs, dtype=float, copy=True)
    out[:4] = np.clip(out[:4], 0.0, None)
    out[4] = 1.0 - float(out[:4].sum())
    if out[4] < 0.0:
        total = float(out[:4].sum())
        if total > 0.0:
            out[:4] = out[:4] / total
        out[4] = 0.0
    return out


def expected_points(probs: np.ndarray, drives: float, td_points: float) -> float:
    """Expected points for one side: own scores plus opponent gifts."""
    return drives * (
        float(probs[0]) * td_points
        + float(probs[1]) * 3.0
        + float(probs[2]) * td_points
        + float(probs[3]) * 2.0
    )


def solve_scale(target: float, drives: float, probs: np.ndarray, td_points: float) -> float:
    """Solve one td/fg scale that makes the expected points equal the target."""
    if drives <= 0.0 or not np.isfinite(target):
        return float("nan")
    others = drives * (float(probs[2]) * td_points + float(probs[3]) * 2.0)
    per_unit = td_points * float(probs[0]) + 3.0 * float(probs[1])
    if per_unit <= 1e-12 or not np.isfinite(per_unit):
        return float("nan")
    scale = (target - others) / (per_unit * drives)
    if not np.isfinite(scale):
        return float("nan")
    return max(0.0, float(scale))


def apply_scale(probs: np.ndarray, scale: float) -> np.ndarray:
    """Scale td and fg, then recompute none with the clip rule."""
    return finalize(
        np.array([float(probs[0]) * scale, float(probs[1]) * scale, probs[2], probs[3], 0.0])
    )


# --------------------------------------------------------------------------
# prior-week aggregation
# --------------------------------------------------------------------------


def team_prior_stats(drives: pd.DataFrame, games: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Return per-team prior drive counts, game counts, and per-game rates."""
    drive_totals = drives.groupby("posteam").size().to_dict()
    game_teams = pd.concat(
        [games[["home_team"]].rename(columns={"home_team": "team"}), games[["away_team"]].rename(columns={"away_team": "team"})]
    )["team"]
    game_totals = game_teams.value_counts().to_dict()
    league_drives = float(len(drives))
    league_team_games = int(len(game_teams))
    league_rate = safe_ratio(league_drives, league_team_games, 0.0)
    stats: dict[str, dict[str, Any]] = {}
    for team in set(drive_totals) | set(game_totals):
        n_drives = int(drive_totals.get(team, 0))
        n_games = int(game_totals.get(team, 0))
        stats[str(team)] = {
            "drives": n_drives,
            "games": n_games,
            "rate": safe_ratio(n_drives, n_games, league_rate),
        }
    return {"teams": stats, "league_rate": league_rate}


def shrunk_side_rates(drives: pd.DataFrame, kind: str) -> dict[str, np.ndarray]:
    """Return shrunk outcome rates per team for offense or defense."""
    league = np.array([outcome_rates(drives)[label] for label in FOUR])
    key = "posteam" if kind == "off" else "defteam"
    grouped = drives.groupby(key)["result"]
    totals = grouped.size()
    out: dict[str, np.ndarray] = {}
    for team, n in totals.items():
        sub = drives[drives[key] == team]["result"]
        counts = np.array([float((sub == label).sum()) for label in FOUR])
        rate = counts / float(n)
        out[str(team)] = float(n) / (float(n) + K_DRIVES) * (rate - league)
    return out


def home_field_factor(drives: pd.DataFrame, games: pd.DataFrame) -> float:
    """Return the shrunk home-to-away points-per-drive factor from prior weeks."""
    if len(drives) == 0 or len(games) == 0:
        return 1.0
    pairs = games[["game_id", "home_team", "away_team"]]
    merged = drives.merge(pairs, on="game_id", how="inner")
    home_drives = merged[merged["posteam"] == merged["home_team"]]
    away_drives = merged[merged["posteam"] == merged["away_team"]]
    if len(home_drives) == 0 or len(away_drives) == 0:
        return 1.0
    home_ppd = safe_ratio(float(games["home_score"].sum()), float(len(home_drives)), 0.0)
    away_ppd = safe_ratio(float(games["away_score"].sum()), float(len(away_drives)), 0.0)
    if away_ppd <= 0.0:
        return 1.0
    ratio = home_ppd / away_ppd
    if not np.isfinite(ratio):
        return 1.0
    return float(1.0 + HFA_SHRINK * (ratio - 1.0))


# --------------------------------------------------------------------------
# model build
# --------------------------------------------------------------------------


def build_model(
    drives: pd.DataFrame,
    games: pd.DataFrame,
    pbp: pd.DataFrame,
    cutoff_week: int,
) -> dict[str, Any]:
    """Build base probabilities and drive rates from weeks < cutoff_week."""
    drive_slice = drives[drives["week"] < cutoff_week]
    game_slice = games[games["week"] < cutoff_week]
    if len(drive_slice) and int(drive_slice["week"].max()) >= cutoff_week:
        raise AssertionError(f"prior drive slice reaches cutoff week {cutoff_week}")
    if len(game_slice) and int(game_slice["week"].max()) >= cutoff_week:
        raise AssertionError(f"prior game slice reaches cutoff week {cutoff_week}")

    league = np.array([outcome_rates(drive_slice)[label] for label in FOUR])
    off_shrunk = shrunk_side_rates(drive_slice, "off")
    def_shrunk = shrunk_side_rates(drive_slice, "def")
    prior = team_prior_stats(drive_slice, game_slice)
    rates, _fallback = pat_rates(pbp, set(game_slice["game_id"]))
    hfa = home_field_factor(drive_slice, game_slice)
    return {
        "league": league,
        "off": off_shrunk,
        "def": def_shrunk,
        "teams": prior["teams"],
        "league_drives": prior["league_rate"],
        "pat": rates,
        "td_points": 6.0 + pat_value(rates),
        "hfa": hfa,
        "cutoff": cutoff_week,
    }


def side_probs(model: dict[str, Any], offense: str, defense: str) -> np.ndarray:
    league = model["league"]
    off_term = model["off"].get(offense, np.zeros(4))
    def_term = model["def"].get(defense, np.zeros(4))
    four = league + off_term + def_term
    return finalize(np.array([four[0], four[1], four[2], four[3], 0.0]))


# --------------------------------------------------------------------------
# simulation
# --------------------------------------------------------------------------


def sample_points(
    prob_matrix: np.ndarray,
    drives: np.ndarray,
    own_points: np.ndarray,
    gift_points: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample drive points for one team across every run, without a run loop.

    Returns the points the offense scores on its own drives and the points it
    gives the defense on those same drives.
    """
    cumulative = np.cumsum(prob_matrix, axis=1)
    cumulative[:, -1] = 1.0
    draws = rng.random((len(drives), int(drives.max())))
    indexes = (draws[:, :, None] >= cumulative[:, None, :]).sum(axis=2)
    own = own_points[indexes]
    gift = gift_points[indexes]
    mask = np.arange(own.shape[1])[None, :] < drives[:, None]
    own = np.where(mask, own, 0.0).sum(axis=1)
    gift = np.where(mask, gift, 0.0).sum(axis=1)
    return own, gift


def simulate_variant(
    rows: list[dict[str, Any]],
    prefix: str,
    rng: np.random.Generator,
) -> list[dict[str, np.ndarray]]:
    """Simulate regulation for every game with the given probability set."""
    results: list[dict[str, np.ndarray]] = []
    for row in rows:
        probs_home = row[f"{prefix}_home_probs"]
        probs_away = row[f"{prefix}_away_probs"]
        td_points = row["td_points"]
        # Each drive is scored from both sides. The offense can score on its own
        # drive, or give the defense points on a takeaway touchdown or a safety.
        offense_points = np.array([td_points, 3.0, 0.0, 0.0, 0.0])
        defense_points = np.array([0.0, 0.0, td_points, 2.0, 0.0])
        mu = row["mu"]
        base = rng.poisson(mu, size=RUNS).astype(np.int64)
        home_extra = (rng.random(RUNS) < 0.5).astype(np.int64)
        home_drives = base + home_extra
        away_drives = base + (1 - home_extra)

        matrix_home = np.repeat(probs_home[None, :], RUNS, axis=0)
        matrix_away = np.repeat(probs_away[None, :], RUNS, axis=0)
        home_own, home_gift = sample_points(matrix_home, home_drives, offense_points, defense_points, rng)
        away_own, away_gift = sample_points(matrix_away, away_drives, offense_points, defense_points, rng)
        results.append({"home": home_own + away_gift, "away": away_own + home_gift})
    return results


def add_overtime(results: list[dict[str, np.ndarray]], rng: np.random.Generator) -> None:
    """Resolve tied runs with the home share of the non-tied runs."""
    for res in results:
        home = res["home"]
        away = res["away"]
        tied = home == away
        if not tied.any():
            continue
        decided_home = (~tied) & (home > away)
        decided_away = (~tied) & (away > home)
        decided_total = int(decided_home.sum() + decided_away.sum())
        probability = 0.5 if decided_total == 0 else float(decided_home.sum()) / decided_total
        home_wins = rng.random(int(tied.sum())) < probability
        home[tied] = home[tied] + np.where(home_wins, 3, 0)
        away[tied] = away[tied] + np.where(home_wins, 0, 3)


def projection_row(
    game_id: str,
    game: pd.Series,
    result: dict[str, np.ndarray],
    prefix: str,
    band_scale: float = 1.0,
) -> dict[str, Any]:
    home = result["home"].astype(float)
    away = result["away"].astype(float)
    total = home + away
    margin = home - away
    total_mean = float(total.mean())
    # The band scale narrows or widens the game total around its mean. The mean
    # itself, the win probability, and the margin stay on the raw scores.
    adjusted = total_mean + band_scale * (total - total_mean)
    return {
        "game_id": game_id,
        "season": int(game["season"]),
        "week": int(game["week"]),
        "home_team": str(game["home_team"]),
        "away_team": str(game["away_team"]),
        f"{prefix}_home_mean": float(home.mean()),
        f"{prefix}_away_mean": float(away.mean()),
        f"{prefix}_total_mean": total_mean,
        f"{prefix}_margin_mean": float(margin.mean()),
        f"{prefix}_home_wp": float((home > away).mean()),
        f"{prefix}_home_median": float(np.median(home)),
        f"{prefix}_away_median": float(np.median(away)),
        f"{prefix}_total_p10": float(np.quantile(adjusted, 0.10, method="linear")),
        f"{prefix}_total_p15": float(np.quantile(adjusted, 0.15, method="linear")),
        f"{prefix}_total_p85": float(np.quantile(adjusted, 0.85, method="linear")),
        f"{prefix}_total_p90": float(np.quantile(adjusted, 0.90, method="linear")),
    }


def band_scale_rows(results: list[dict[str, np.ndarray]], actual_total: np.ndarray) -> list[tuple[float, float, float]]:
    """Return (scale, p15-p85 coverage, p10-p90 coverage) for each candidate scale."""
    totals = np.array([res["home"] + res["away"] for res in results], dtype=float)
    means = totals.mean(axis=1, keepdims=True)
    steps = int(round((BAND_SCALE_MAX - BAND_SCALE_MIN) / BAND_SCALE_STEP)) + 1
    rows: list[tuple[float, float, float]] = []
    for index in range(steps):
        scale = round(BAND_SCALE_MIN + index * BAND_SCALE_STEP, 4)
        adjusted = means + scale * (totals - means)
        p10 = np.quantile(adjusted, 0.10, axis=1, method="linear")
        p15 = np.quantile(adjusted, 0.15, axis=1, method="linear")
        p85 = np.quantile(adjusted, 0.85, axis=1, method="linear")
        p90 = np.quantile(adjusted, 0.90, axis=1, method="linear")
        cover15 = float(((actual_total >= p15) & (actual_total <= p85)).mean())
        cover10 = float(((actual_total >= p10) & (actual_total <= p90)).mean())
        rows.append((scale, cover15, cover10))
    return rows


def select_band_scale(
    results: list[dict[str, np.ndarray]], actual_total: np.ndarray
) -> tuple[tuple[float, float, float] | None, tuple[float, float, float]]:
    """Pick one scale. Return the chosen row, or None plus the closest row."""
    rows = band_scale_rows(results, actual_total)

    def miss(row: tuple[float, float, float]) -> float:
        return (row[1] - BAND_15_TARGET) ** 2 + (row[2] - BAND_10_TARGET) ** 2

    qualifying = [
        row for row in rows if BAND_15_LO <= row[1] <= BAND_15_HI and BAND_10_LO <= row[2] <= BAND_10_HI
    ]
    if not qualifying:
        return None, min(rows, key=miss)
    best = min(qualifying, key=miss)
    return best, best


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------


def per_game_metrics(
    total_pred: np.ndarray,
    margin_pred: np.ndarray,
    wp: np.ndarray,
    actual_total: np.ndarray,
    actual_margin: np.ndarray,
) -> dict[str, np.ndarray]:
    """Return per-game metric arrays. Ties become NaN for the winner metrics."""
    probability = np.clip(wp, 1e-15, 1.0 - 1e-15)
    decided = actual_margin != 0
    home_won = (actual_margin > 0).astype(float)
    picks_home = (wp > 0.5).astype(float)
    hits = np.where(decided, np.where(picks_home == home_won, 1.0, 0.0), np.nan)
    # The home and away terms of a game are mirror images. The home term uses
    # the home win probability, the away term uses its complement. Each term
    # uses the result of its own side.
    squared_error = (probability - home_won) ** 2
    brier = np.where(decided, squared_error, np.nan)
    side_loss = -(home_won * np.log(probability) + (1.0 - home_won) * np.log(1.0 - probability))
    log_loss = np.where(decided, side_loss, np.nan)
    return {
        "total": np.abs(total_pred - actual_total),
        "margin": np.abs(margin_pred - actual_margin),
        "accuracy": hits,
        "brier": brier,
        "log_loss": log_loss,
    }


def model_metrics(
    total_pred: np.ndarray,
    margin_pred: np.ndarray,
    wp: np.ndarray,
    actual_total: np.ndarray,
    actual_margin: np.ndarray,
    coverage_mask: np.ndarray | None = None,
) -> dict[str, float]:
    values = per_game_metrics(total_pred, margin_pred, wp, actual_total, actual_margin)
    coverage = float("nan") if coverage_mask is None else float(np.mean(coverage_mask))
    return {
        "total_mae": float(np.nanmean(values["total"])),
        "margin_mae": float(np.nanmean(values["margin"])),
        "winner_accuracy": float(np.nanmean(values["accuracy"])),
        "brier": float(np.nanmean(values["brier"])),
        "log_loss": float(np.nanmean(values["log_loss"])),
        "coverage": coverage,
    }


def metric_row(name: str, metrics: dict[str, float]) -> str:
    coverage = "n/a" if not np.isfinite(metrics["coverage"]) else f"{metrics['coverage']:.3f}"
    return (
        f"{name:<16} {metrics['total_mae']:>9.2f} {metrics['margin_mae']:>10.2f} "
        f"{metrics['winner_accuracy']:>8.3f} {metrics['brier']:>7.3f} {metrics['log_loss']:>9.3f} {coverage:>9}"
    )


def bootstrap_differences(
    model_values: dict[str, np.ndarray],
    vegas_values: dict[str, np.ndarray],
) -> dict[str, dict[str, tuple[float, float, float]]]:
    """Bootstrap model minus Vegas differences."""
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(vegas_values["total"])
    indexes = rng.integers(0, n, size=(BOOTSTRAP_DRAWS, n))
    out: dict[str, dict[str, tuple[float, float, float]]] = {}
    for name, values in model_values.items():
        diffs: dict[str, np.ndarray] = {}
        for key in ("total", "margin", "accuracy", "brier", "log_loss"):
            model_draw = values[key][indexes]
            vegas_draw = vegas_values[key][indexes]
            diffs[key] = np.nanmean(model_draw - vegas_draw, axis=1)
        out[name] = {
            key: (
                float(np.nanmean(diff)),
                float(np.nanpercentile(diff, 2.5)),
                float(np.nanpercentile(diff, 97.5)),
            )
            for key, diff in diffs.items()
        }
    return out


def calibration_buckets(
    names: list[str],
    wp_by_model: dict[str, np.ndarray],
    actual_margin: np.ndarray,
) -> dict[str, list[tuple[int, float, float]]]:
    edges = np.array([-0.001, 0.3, 0.45, 0.55, 0.7, 1.0])
    mask = actual_margin != 0
    out: dict[str, list[tuple[int, float, float]]] = {}
    for name in names:
        wp = wp_by_model[name][mask]
        outcome = (actual_margin[mask] > 0).astype(float)
        rows: list[tuple[int, float, float]] = []
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            in_bin = (wp > lo) & (wp <= hi)
            n = int(in_bin.sum())
            mean_pred = float(np.mean(wp[in_bin])) if n else float("nan")
            home_rate = float(np.mean(outcome[in_bin])) if n else float("nan")
            rows.append((n, mean_pred, home_rate))
        out[name] = rows
    return out


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main() -> int:
    print(f"WORKDIR {WORKDIR}")
    print(f"INTERPRETER {sys.executable}")

    season, season_sched, pbp = load_inputs()
    retrieved_at = datetime.now(ZoneInfo("America/New_York")).isoformat()

    has_scores = season_sched["home_score"].notna() & season_sched["away_score"].notna()
    unscored = season_sched[~has_scores]
    cw = int(unscored["week"].min())
    backtest_games = season_sched[(season_sched["week"] > 1) & (season_sched["week"] <= cw) & has_scores].copy()
    upcoming_games = season_sched[(season_sched["week"] == cw) & ~has_scores].copy()
    weeks = sorted(int(w) for w in backtest_games["week"].unique())
    print(f"season {season} current_week {cw}")
    print(f"backtest games {len(backtest_games)} weeks {weeks[0]}-{weeks[-1]} (n={len(backtest_games)})")
    print(f"upcoming games {len(upcoming_games)}")

    drives = build_drives(pbp)
    print("drive label counts:")
    for label in OUTCOMES:
        print(f"  {label}: {int((drives['result'] == label).sum())}")

    # ---- ordered work list: backtest then upcoming, sorted by game_id ----
    work: list[dict[str, Any]] = []
    for _, game in backtest_games.sort_values("game_id").iterrows():
        work.append({"game": game, "kind": "backtest", "cutoff": int(game["week"])})
    for _, game in upcoming_games.sort_values("game_id").iterrows():
        work.append({"game": game, "kind": "upcoming", "cutoff": cw})

    models: dict[int, dict[str, Any]] = {}

    def model_for(cutoff: int) -> dict[str, Any]:
        if cutoff not in models:
            models[cutoff] = build_model(drives, season_sched, pbp, cutoff)
        return models[cutoff]

    rows: list[dict[str, Any]] = []
    cutoffs_seen: set[int] = set()
    for item in work:
        game = item["game"]
        cutoff = item["cutoff"]
        model = model_for(cutoff)
        if cutoff not in cutoffs_seen:
            check = drives[drives["week"] < cutoff]
            if len(check) and int(check["week"].max()) >= cutoff:
                raise AssertionError(f"PIT violation at cutoff {cutoff}")
            cutoffs_seen.add(cutoff)
        game_id = str(game["game_id"])
        home = str(game["home_team"])
        away = str(game["away_team"])
        teams = model["teams"]
        home_rate = teams.get(home, {}).get("rate", model["league_drives"])
        away_rate = teams.get(away, {}).get("rate", model["league_drives"])
        mu = float(np.mean([home_rate, away_rate])) if np.isfinite(home_rate) and np.isfinite(away_rate) else 0.0

        home_probs = side_probs(model, home, away)
        away_probs = side_probs(model, away, home)
        hfa = model["hfa"]
        home_probs = finalize(
            np.array([home_probs[0] * hfa, home_probs[1] * hfa, home_probs[2], home_probs[3], 0.0])
        )
        away_probs = finalize(
            np.array([away_probs[0] / hfa, away_probs[1] / hfa, away_probs[2], away_probs[3], 0.0])
        )
        row: dict[str, Any] = {
            "game_id": game_id,
            "season": int(game["season"]),
            "week": int(game["week"]),
            "home_team": home,
            "away_team": away,
            "home_score": float(game["home_score"]) if pd.notna(game["home_score"]) else None,
            "away_score": float(game["away_score"]) if pd.notna(game["away_score"]) else None,
            "spread_line": float(game["spread_line"]) if pd.notna(game["spread_line"]) else None,
            "total_line": float(game["total_line"]) if pd.notna(game["total_line"]) else None,
            "game": game,
            "kind": item["kind"],
            "mu": mu,
            "a_home_probs": home_probs,
            "a_away_probs": away_probs,
            "td_points": model["td_points"],
            "pat": model["pat"],
        }
        row["vegas_home_wp"] = (
            float(norm.cdf(float(game["spread_line"]) / SPREAD_SIGMA)) if pd.notna(game["spread_line"]) else None
        )

        # ---- variant B: scale td/fg to the implied team total ----
        b_home = home_probs.copy()
        b_away = away_probs.copy()
        implied = implied_team_totals_from_schedule_row(game)
        home_target = implied.get("home_implied_total")
        away_target = implied.get("away_implied_total")
        expected_drives = mu + 0.5
        scaled = False
        if home_target is None or away_target is None:
            print(f"B_SKIP {game_id} missing implied total")
        else:
            home_scale = solve_scale(float(home_target), expected_drives, home_probs, model["td_points"])
            away_scale = solve_scale(float(away_target), expected_drives, away_probs, model["td_points"])
            if not np.isfinite(home_scale) or not np.isfinite(away_scale):
                print(f"B_SKIP {game_id} non-finite scale")
            else:
                max_home = 1.0 / max(float(np.max(home_probs[:2])), 1e-12)
                max_away = 1.0 / max(float(np.max(away_probs[:2])), 1e-12)
                home_scale = min(home_scale, max_home)
                away_scale = min(away_scale, max_away)
                b_home = apply_scale(home_probs, home_scale)
                b_away = apply_scale(away_probs, away_scale)
                scaled = True
        row["b_home_probs"] = b_home
        row["b_away_probs"] = b_away
        row["b_scaled"] = scaled
        rows.append(row)

    rng = np.random.default_rng(SEED)
    results_a = simulate_variant(rows, "a", rng)
    add_overtime(results_a, rng)
    results_b = simulate_variant(rows, "b", rng)
    add_overtime(results_b, rng)

    # ---- one band scale per model, fit on the backtest games ----
    backtest_indexes = [index for index, row in enumerate(rows) if row["kind"] == "backtest"]
    backtest_actual_total = np.array(
        [float(rows[index]["home_score"]) + float(rows[index]["away_score"]) for index in backtest_indexes],
        dtype=float,
    )
    band_choice: dict[str, tuple[float, float, float]] = {}
    band_fail = False
    for name, results in (("A", results_a), ("B", results_b)):
        subset = [results[index] for index in backtest_indexes]
        chosen, closest = select_band_scale(subset, backtest_actual_total)
        if chosen is None:
            print(
                f"BAND_FAIL {name} closest scale {closest[0]:.3f} "
                f"p15-p85 {closest[1]:.4f} p10-p90 {closest[2]:.4f}"
            )
            band_fail = True
        band_choice[name] = chosen if chosen is not None else closest
    if band_fail:
        return 1
    scale_a = band_choice["A"][0]
    scale_b = band_choice["B"][0]

    backtest_rows: list[dict[str, Any]] = []
    upcoming_rows: list[dict[str, Any]] = []
    for row, res_a, res_b in zip(rows, results_a, results_b, strict=True):
        out = {
            "game_id": row["game_id"],
            "season": row["season"],
            "week": row["week"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "home_score": row["home_score"],
            "away_score": row["away_score"],
            "spread_line": row["spread_line"],
            "total_line": row["total_line"],
            "vegas_home_wp": row["vegas_home_wp"],
        }
        out.update(projection_row(row["game_id"], row["game"], res_a, "a", scale_a))
        out.update(projection_row(row["game_id"], row["game"], res_b, "b", scale_b))
        out["_a_home"] = res_a["home"]
        out["_a_away"] = res_a["away"]
        out["_b_home"] = res_b["home"]
        out["_b_away"] = res_b["away"]
        if row["kind"] == "backtest":
            backtest_rows.append(out)
        else:
            upcoming_rows.append(out)

    print("PIT_OK")

    # ---- metrics on the backtest slice ----
    bt = pd.DataFrame(backtest_rows).sort_values("game_id").reset_index(drop=True)
    actual_home = bt["home_score"].to_numpy(dtype=float)
    actual_away = bt["away_score"].to_numpy(dtype=float)
    actual_total = actual_home + actual_away
    actual_margin = actual_home - actual_away
    ties = bt.loc[actual_margin == 0, "game_id"].tolist()
    if ties:
        print(f"skipped ties: {', '.join(ties)}")
    else:
        print("skipped ties: none")

    wp_a = bt["a_home_wp"].to_numpy(dtype=float)
    wp_b = bt["b_home_wp"].to_numpy(dtype=float)
    vegas_wp = bt["vegas_home_wp"].to_numpy(dtype=float)
    blend_wp = (wp_a + vegas_wp) / 2.0

    metrics: dict[str, dict[str, float]] = {}
    metrics["A"] = model_metrics(
        bt["a_total_mean"].to_numpy(dtype=float),
        bt["a_margin_mean"].to_numpy(dtype=float),
        wp_a,
        actual_total,
        actual_margin,
        (actual_total >= bt["a_total_p15"].to_numpy(dtype=float)) & (actual_total <= bt["a_total_p85"].to_numpy(dtype=float)),
    )
    metrics["B"] = model_metrics(
        bt["b_total_mean"].to_numpy(dtype=float),
        bt["b_margin_mean"].to_numpy(dtype=float),
        wp_b,
        actual_total,
        actual_margin,
        (actual_total >= bt["b_total_p15"].to_numpy(dtype=float)) & (actual_total <= bt["b_total_p85"].to_numpy(dtype=float)),
    )
    metrics["Vegas"] = model_metrics(
        bt["total_line"].to_numpy(dtype=float),
        bt["spread_line"].to_numpy(dtype=float),
        vegas_wp,
        actual_total,
        actual_margin,
        None,
    )
    metrics["Blend_A_Vegas"] = model_metrics(
        (bt["a_total_mean"].to_numpy(dtype=float) + bt["total_line"].to_numpy(dtype=float)) / 2.0,
        (bt["a_margin_mean"].to_numpy(dtype=float) + bt["spread_line"].to_numpy(dtype=float)) / 2.0,
        blend_wp,
        actual_total,
        actual_margin,
        None,
    )

    print("")
    print("metric table (backtest)")
    print(f"{'model':<16} {'totMAE':>9} {'marMAE':>10} {'winAcc':>8} {'Brier':>7} {'logLoss':>9} {'cover':>9}")
    for name in ("A", "B", "Vegas", "Blend_A_Vegas"):
        print(metric_row(name, metrics[name]))

    print("")
    print("band coverage (backtest)")
    print(f"{'model':<16} {'p15-p85':>9} {'p10-p90':>9} {'scale':>7}")
    for name in ("A", "B"):
        cover15, cover10, scale = band_choice[name][1], band_choice[name][2], band_choice[name][0]
        print(f"{name:<16} {cover15:>9.4f} {cover10:>9.4f} {scale:>7.3f}")

    # ---- bootstrap versus Vegas ----
    vegas_values = per_game_metrics(
        bt["total_line"].to_numpy(dtype=float),
        bt["spread_line"].to_numpy(dtype=float),
        vegas_wp,
        actual_total,
        actual_margin,
    )
    model_values = {
        "A": per_game_metrics(
            bt["a_total_mean"].to_numpy(dtype=float),
            bt["a_margin_mean"].to_numpy(dtype=float),
            wp_a,
            actual_total,
            actual_margin,
        ),
        "B": per_game_metrics(
            bt["b_total_mean"].to_numpy(dtype=float),
            bt["b_margin_mean"].to_numpy(dtype=float),
            wp_b,
            actual_total,
            actual_margin,
        ),
        "Blend_A_Vegas": per_game_metrics(
            (bt["a_total_mean"].to_numpy(dtype=float) + bt["total_line"].to_numpy(dtype=float)) / 2.0,
            (bt["a_margin_mean"].to_numpy(dtype=float) + bt["spread_line"].to_numpy(dtype=float)) / 2.0,
            blend_wp,
            actual_total,
            actual_margin,
        ),
    }
    boot = bootstrap_differences(model_values, vegas_values)
    print("")
    print("bootstrap differences versus Vegas (5000 draws, seed 20261017)")
    print(f"{'model':<16} {'metric':<10} {'mean':>10} {'p2.5':>10} {'p97.5':>10}")
    for name in ("A", "B", "Blend_A_Vegas"):
        for key in ("total", "margin", "accuracy", "brier", "log_loss"):
            mean, lo, hi = boot[name][key]
            print(f"{name:<16} {key:<10} {mean:>10.4f} {lo:>10.4f} {hi:>10.4f}")

    # ---- calibration ----
    wp_by_model = {"A": wp_a, "B": wp_b, "Vegas": vegas_wp, "Blend_A_Vegas": blend_wp}
    calibration = calibration_buckets(["A", "B", "Vegas", "Blend_A_Vegas"], wp_by_model, actual_margin)
    print("")
    print("home win calibration (right-closed bins, ties skipped)")
    print(f"{'model':<16} {'range':<14} {'n':>4} {'pred':>8} {'home_rate':>10}")
    edges = [-0.001, 0.3, 0.45, 0.55, 0.7, 1.0]
    for name in ("A", "B", "Vegas", "Blend_A_Vegas"):
        for i, (n, pred, rate) in enumerate(calibration[name]):
            label = f"({edges[i]:.3f}, {edges[i + 1]:.2f}]"
            pred_text = "n/a" if not np.isfinite(pred) else f"{pred:.3f}"
            rate_text = "n/a" if not np.isfinite(rate) else f"{rate:.3f}"
            print(f"{name:<16} {label:<14} {n:>4} {pred_text:>8} {rate_text:>10}")

    # ---- published comparison ----
    print("")
    print("published comparison (reference only; a miss is a finding, not a failure)")
    print(
        f"{'model':<16} {'totMAE':>9} {'marMAE':>10} {'winAcc':>8} {'Brier':>7} {'logLoss':>9} {'cover':>9}"
    )
    for name in ("A", "B", "Vegas", "Blend_A_Vegas"):
        target = PUBLISHED_TARGETS[name]
        print(metric_row(name + "_pub", {
            "total_mae": target[0],
            "margin_mae": target[1],
            "winner_accuracy": target[2],
            "brier": target[3],
            "log_loss": target[4],
            "coverage": target[5] if target[5] is not None else float("nan"),
        }))
    print("gaps model minus published (published columns in order):")
    keys = ("total_mae", "margin_mae", "winner_accuracy", "brier", "log_loss", "coverage")
    for name in ("A", "B", "Vegas", "Blend_A_Vegas"):
        target = PUBLISHED_TARGETS[name]
        parts = []
        for i, key in enumerate(keys):
            if target[i] is None:
                continue
            parts.append(f"{key}={metrics[name][key] - target[i]:+.4f}")
        print(f"  {name:<16} " + " ".join(parts))

    # ---- specific game row ----
    sea_den = bt[bt["game_id"] == "2026_06_SEA_DEN"]
    if len(sea_den):
        row = sea_den.iloc[0]
        print("")
        print("SEA at DEN week 6:")
        print(
            f"  DEN {int(row['home_score'])} SEA {int(row['away_score'])} "
            f"total_line {row['total_line']} vegas_home_wp {row['vegas_home_wp']:.3f}"
        )

    # ---- write outputs ----
    outputs = WORKDIR / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    bt_public = bt[BACKTEST_COLUMNS].copy()
    up_public = pd.DataFrame(upcoming_rows)[UPCOMING_COLUMNS].sort_values("game_id").reset_index(drop=True)
    bt_public.to_csv(outputs / "team_backtest.csv", index=False, float_format="%.6f", lineterminator="\n")
    up_public.to_csv(outputs / "team_proj_upcoming.csv", index=False, float_format="%.6f", lineterminator="\n", na_rep="")

    meta = {
        "seed": SEED,
        "runs": RUNS,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "k_drives": K_DRIVES,
        "hfa_shrink": HFA_SHRINK,
        "spread_sigma": SPREAD_SIGMA,
        "season": season,
        "backtest_weeks": weeks,
        "band_scale_a": scale_a,
        "band_scale_b": scale_b,
        "n_backtest": int(len(bt_public)),
        "n_upcoming": int(len(up_public)),
        "current_week": cw,
        "retrieved_at": retrieved_at,
        "sources": {"pbp": PBP_URL, "schedules": SCHEDULES_URL},
    }
    (WORKDIR / "team_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print("")
    print(f"wrote {len(bt_public)} backtest rows and {len(up_public)} upcoming rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
