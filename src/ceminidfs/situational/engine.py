"""Cache loader, slate scorer, and deterministic calibration export.

This module reads parquet files that are already on disk. It does not
download play-by-play, Next Gen Stats, or FTN charting.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ceminidfs.data.fetch import _cache_dir
from ceminidfs.situational.backtest import calibrate_history, predict_bonus, predict_pair
from ceminidfs.situational.contract import canon_team
from ceminidfs.situational.features import build_history_grains, tables_from_grains
from ceminidfs.situational.game_context import build_game_context
from ceminidfs.situational.injuries import apply_injury_vacuum, load_week_injuries
from ceminidfs.situational.quantiles import apply_ceiling, telemetry_lift
from ceminidfs.situational.shared_cache import write_shared_cache
from ceminidfs.situational.tail import (
    PASS_YARD_BONUS,
    REC_YARD_BONUS,
    RUSH_YARD_BONUS,
    poisson_at_least,
)

DEFAULT_SEED = 20261017
DEFAULT_SEASONS = (2023, 2024, 2025, 2026)
HOLD_TIME_SECONDS = 2.85
SALARY_BY_SLATE = {
    (2026, 6): Path("data/slates/2026-10-18_fd_sun.csv"),
}

_PBP_COLUMNS = (
    "season",
    "week",
    "qtr",
    "game_id",
    "play_id",
    "posteam",
    "defteam",
    "play_type",
    "pass",
    "rush",
    "epa",
    "touchdown",
    "pass_touchdown",
    "rush_touchdown",
    "yards_gained",
    "air_yards",
    "receiver_player_id",
    "receiver_player_name",
    "rusher_player_id",
    "rusher_player_name",
    "passer_player_id",
    "passer_player_name",
    "fumbled_1_player_id",
    "fumbled_1_player_name",
    "yardline_100",
    "score_differential",
    "no_huddle",
    "qb_dropback",
    "complete_pass",
    "sack",
    "interception",
    "fumble_lost",
    "yards_after_catch",
    "fixed_drive",
    "drive_quarter_start",
    "drive_inside20",
    "pass_oe",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "return_touchdown",
    "td_team",
    "safety",
)
_FTN_COLUMNS = (
    "nflverse_game_id",
    "nflverse_play_id",
    "is_no_huddle",
    "is_play_action",
    "is_motion",
    "is_qb_fault_sack",
    "is_interception_worthy",
    "n_defense_box",
)
_NGS_COLUMNS = (
    "season",
    "week",
    "player_gsis_id",
    "player_id",
    "player_display_name",
    "player_name",
    "player_position",
    "avg_cushion",
    "avg_separation",
    "avg_intended_air_yards",
    "percent_share_of_intended_air_yards",
    "avg_yac_above_expectation",
    "completion_percentage_above_expectation",
    "avg_time_to_throw",
    "rush_yards_over_expected_per_att",
)


def load_history_frames(
    seasons: tuple[int, ...] = DEFAULT_SEASONS,
    *,
    cache_dir: Path | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Read cached seasons. A missing file becomes an empty frame."""

    root = Path(cache_dir) if cache_dir is not None else _cache_dir()
    used: list[str] = []
    missing: list[str] = []
    pbp_parts = []
    ftn_parts = []
    ngs = {"passing": [], "receiving": [], "rushing": []}
    for season in seasons:
        pbp_path = root / f"pbp_{season}.parquet"
        pbp = _read_cached(pbp_path, _PBP_COLUMNS, used, missing)
        if not pbp.empty:
            pbp_parts.append(pbp)
        ftn_path = root / f"ftn_charting_{season}.parquet"
        ftn = _read_cached(ftn_path, _FTN_COLUMNS, used, missing)
        if not ftn.empty:
            ftn_parts.append(ftn)
        for kind in ngs:
            path = root / f"ngs_{kind}_{season}.parquet"
            frame = _read_cached(path, _NGS_COLUMNS, used, missing)
            if not frame.empty:
                ngs[kind].append(frame)
    frames = {
        "pbp": _concat(pbp_parts),
        "ftn": _concat(ftn_parts),
        "ngs_passing": _concat(ngs["passing"]),
        "ngs_receiving": _concat(ngs["receiving"]),
        "ngs_rushing": _concat(ngs["rushing"]),
    }
    audit = {"cache_dir": str(root), "used": used, "missing": missing}
    return frames, audit


def build_cached_grains(
    seasons: tuple[int, ...] = DEFAULT_SEASONS,
    *,
    cache_dir: Path | None = None,
):
    """Build history grains from the local cache."""

    frames, audit = load_history_frames(seasons, cache_dir=cache_dir)
    grains = build_history_grains(
        frames["pbp"],
        ngs_passing=frames["ngs_passing"],
        ngs_rushing=frames["ngs_rushing"],
        ngs_receiving=frames["ngs_receiving"],
        ftn=frames["ftn"],
    )
    return grains, audit


_BOOST_COLUMNS = ("vacated_target_boost", "vacated_rz_boost")


def _cache_players(players: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    """Copy injury-vacuum boosts onto the point-in-time player frame.

    The feature table is keyed by gsis ``player_id``. The boosts live on the
    scored salary frame under ``gsis_id``. A player who is not on the slate gets 0.
    """

    frame = players.copy()
    frame = frame.drop(columns=list(_BOOST_COLUMNS), errors="ignore")
    if "player_id" not in frame.columns:
        for column in _BOOST_COLUMNS:
            frame[column] = 0.0
        return frame
    frame["player_id"] = frame["player_id"].astype(str)
    frame = frame.merge(_slate_boosts(scored), left_on="player_id", right_on="gsis_id", how="left")
    frame = frame.drop(columns=["gsis_id"], errors="ignore")
    for column in _BOOST_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return frame.sort_values(["player_id"], kind="mergesort").reset_index(drop=True)


def _slate_boosts(scored: pd.DataFrame) -> pd.DataFrame:
    columns = ["gsis_id", *_BOOST_COLUMNS]
    empty = pd.DataFrame(columns=columns)
    if scored is None or scored.empty or "gsis_id" not in scored.columns:
        return empty
    if not set(_BOOST_COLUMNS).issubset(scored.columns):
        return empty
    boosts = scored.loc[:, ["gsis_id", *_BOOST_COLUMNS]].copy()
    if boosts.empty:
        return empty
    boosts["gsis_id"] = boosts["gsis_id"].astype(str)
    for column in _BOOST_COLUMNS:
        boosts[column] = pd.to_numeric(boosts[column], errors="coerce").fillna(0.0)
    return boosts.groupby("gsis_id", as_index=False)[list(_BOOST_COLUMNS)].sum()


def run_slate(
    season: int,
    week: int,
    *,
    salary_path: Path | None = None,
    out_dir: Path | None = None,
    seasons: tuple[int, ...] = DEFAULT_SEASONS,
    seed: int = DEFAULT_SEED,
    n_boot: int = 400,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    """Calibrate history, score one pre-game slate, and write the files."""

    grains, cache_audit = build_cached_grains(seasons, cache_dir=cache_dir)
    calibration = calibrate_history(grains, seed=seed, n_boot=n_boot)
    tables = tables_from_grains(grains, season=int(season), week=int(week))
    salary = _read_salary(_salary_path(season, week, salary_path))
    injuries = load_week_injuries(int(season), int(week))
    scored = score_players(tables, calibration, salary, injuries=injuries)
    games, _schedule_week = build_game_context(
        int(season),
        int(week),
        seasons=seasons,
        cache_dir=cache_dir,
    )
    max_source_week = tables.audit.get("max_week_same_season")
    max_source_week = int(max_source_week) if max_source_week is not None else 0
    shared_dir = Path("data/shared_cache") / f"{int(season)}_w{int(week):02d}"
    manifest = write_shared_cache(
        shared_dir,
        players=_cache_players(tables.players, scored),
        defense=tables.defense.sort_values(["team"], kind="mergesort"),
        games=games,
        season=int(season),
        week=int(week),
        max_source_week=max_source_week,
    )
    boosts = slate_corr_boosts(scored, calibration)
    payload = {
        "seed": int(seed),
        "season": int(season),
        "week": int(week),
        "cache": cache_audit,
        "feature_audit": tables.audit,
        "calibration": calibration,
    }
    text = dumps_calibration(payload)
    destination = out_dir or Path("runs") / f"{season}_week_{week}" / "situational"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "calibration.json").write_text(text + "\n", encoding="utf-8")
    scored_path = destination / "ceiling.csv"
    boost_path = destination / "corr_boost.csv"
    scored.to_csv(scored_path, index=False)
    boosts.to_csv(boost_path, index=False)
    return {
        "out_dir": destination,
        "season": int(season),
        "week": int(week),
        "scored": scored,
        "boosts": boosts,
        "calibration": calibration,
        "cache": cache_audit,
        "feature_audit": tables.audit,
        "salary_path": _salary_path(season, week, salary_path),
        "shared_cache": str(shared_dir),
        "manifest": manifest,
    }


def score_players(
    tables,
    calibration: dict[str, Any],
    salary: pd.DataFrame | None = None,
    injuries: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Join lagged features to a salary file and score bounded tails."""

    players = tables.players.copy()
    if players.empty and (salary is None or salary.empty):
        return pd.DataFrame()
    if players.empty:
        players = pd.DataFrame(columns=["player_id", "player_name", "team", "position"])
    scored = _attach_salary(players, salary)
    scored = _attach_opponent_defense(scored, tables.defense)
    scored = _attach_own_defense(scored, tables.defense)
    scored = _add_slate_interactions(scored)
    scored = apply_injury_vacuum(scored, injuries)
    scored = _apply_dst_lagged(scored)
    scored = _copy_opposing_qb(scored)
    scored = _apply_report_flags(scored, calibration)
    rows = [_score_row(row, calibration) for row in scored.to_dict(orient="records")]
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(
        ["p99", "player_id"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def slate_corr_boosts(scored: pd.DataFrame, calibration: dict[str, Any]) -> pd.DataFrame:
    """Flagged pair rows. The boost is 0 when the holdout gate rejects it."""

    columns = ["player_a", "player_b", "kind", "corr_boost"]
    if scored.empty:
        return pd.DataFrame(columns=columns)
    thresholds = calibration.get("thresholds") or {}
    correlation = calibration.get("correlation") or {}
    pairs = []
    pairs.extend(_qb_pairs(scored, thresholds, correlation, "qb_skill", same_team=True))
    pairs.extend(_qb_pairs(scored, thresholds, correlation, "qb_bringback", same_team=False))
    pairs.extend(_rb_dst_pairs(scored, thresholds, correlation))
    frame = pd.DataFrame(pairs, columns=columns)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return frame.sort_values(["kind", "player_a", "player_b"], kind="mergesort").reset_index(drop=True)


def dumps_calibration(payload: dict[str, Any]) -> str:
    """Stable JSON. Floats are rounded. Keys are sorted. No timestamps."""

    return json.dumps(_canon(payload), sort_keys=True, separators=(",", ":"))


def _score_row(row: dict[str, Any], calibration: dict[str, Any]) -> dict[str, Any]:
    targets = calibration.get("targets") or {}
    position = str(row.get("position") or "")
    lagged_fd = _num(row.get("lagged_fd"))
    injury = str(row.get("injury_status") or "")
    unavailable = injury in {"OUT", "IR"}
    rec_model = targets.get("rec_100") or {}
    rush_model = targets.get("rush_100") or {}
    pass_model = targets.get("pass_300") or {}
    point_model = targets.get("fpts_25") or {}
    f20_model = targets.get("fpts_20") or {}
    td_model = targets.get("multi_td") or {}
    dst_model = targets.get("dst_10") or {}
    rec_base, rec_p = _pair(row, rec_model, "rec_yds_per_game", REC_YARD_BONUS, position)
    rush_base, rush_p = _pair(row, rush_model, "rush_yds_per_game", RUSH_YARD_BONUS, position)
    pass_base, pass_p = _pair(row, pass_model, "pass_yds_per_game", PASS_YARD_BONUS, position)
    _f20_base, f20_p = _pair(row, f20_model, "lagged_fd", 20.0, position)
    td_base, td_p = _td_pair(row, td_model)
    lift = 0.0
    if not unavailable:
        lift = telemetry_lift(
            _bonus_gap(position, rec_base, rec_p, rush_base, rush_p, pass_base, pass_p),
            _gap(td_p, td_base),
            _gap(f20_p, _f20_base),
        )
    table = _quantile_table(calibration, position)
    p90, p99 = apply_ceiling(float("nan") if unavailable else lagged_fd, position, table, lift)
    if position == "DST" and not unavailable:
        _dst_base, dst_p = _pair(row, dst_model, "lagged_fd", 10.0, "DST")
    else:
        dst_p = float("nan")
    return {
        "player_id": str(row.get("salary_id") or row.get("player_id") or ""),
        "gsis_id": str(row.get("player_id") or ""),
        "player_name": str(row.get("salary_name") or row.get("player_name") or ""),
        "team": str(row.get("salary_team") or row.get("team") or ""),
        "opp": str(row.get("salary_opp") or ""),
        "position": position,
        "salary": _num(row.get("salary")),
        "fppg": _num(row.get("fppg")),
        "lagged_fd": 0.0 if unavailable else lagged_fd,
        "p90": p90,
        "p99": p99,
        "ceiling_fppg": p90,
        "p_rec_100": rec_p,
        "p_rush_100": rush_p,
        "p_pass_300": pass_p,
        "p_fpts_25": _bonus(row, point_model, "lagged_fd", 25.0, position),
        "p_fpts_20": f20_p,
        "p_multi_td": td_p,
        "p_dst_10": dst_p,
        "injury_status": injury,
        "vacated_target_boost": _num(row.get("vacated_target_boost")),
        "vacated_rz_boost": _num(row.get("vacated_rz_boost")),
        "vacated_carry_boost": _num(row.get("vacated_carry_boost")),
        "trail4_opps": _num(row.get("trail4_opps")),
        "q3_flag": bool(row.get("q3_flag")) and not unavailable,
        "q4_flag": bool(row.get("q4_flag")) and not unavailable,
        "dst_flag": bool(row.get("dst_flag")),
        "q3_script": _num(row.get("q3_script")),
        "q4_bringback": _num(row.get("q4_bringback")),
        "pressure_mismatch": _num(row.get("pressure_mismatch")),
        "avg_time_to_throw": _num(row.get("avg_time_to_throw")),
        "avg_yac_above_expectation": _num(row.get("avg_yac_above_expectation")),
        "q3_rz_touch_share": _num(row.get("q3_rz_touch_share")),
        "q4_trail_target_share": _num(row.get("q4_trail_target_share")),
        "inside10_target_share": _num(row.get("inside10_target_share")),
        "opp_def_q3_slow_start": _num(row.get("opp_def_q3_slow_start")),
        "opp_def_sack_rate": _num(row.get("opp_def_sack_rate")),
        "ryoe": _num(row.get("ryoe")),
        "air_yards_share": _num(row.get("air_yards_share")),
    }


def _bonus(row, model, mean_col, threshold, position) -> float:
    mean = _num(row.get(mean_col))
    sigma = _sigma_for(model, position)
    if not math.isfinite(mean) or sigma is None:
        return float("nan")
    features = {key: _num(row.get(key)) for key in (model.get("kept") or [])}
    return predict_bonus(
        mean,
        sigma,
        threshold,
        weight=float(model.get("mixture_weight") or 1.0),
        model=model,
        features=features,
    )


def _multi_td(row, model) -> float:
    rate = _num(row.get("lagged_td"))
    if not math.isfinite(rate):
        return float("nan")
    baseline = poisson_at_least(2, rate)
    if not model or not model.get("export"):
        return baseline
    features = {key: _num(row.get(key)) for key in (model.get("kept") or [])}
    return predict_bonus(rate, 1.0, 2.0, weight=1.0, model=model, features=features)


def _pair(row, model, mean_col, threshold, position) -> tuple[float, float]:
    mean = _num(row.get(mean_col))
    sigma = _sigma_for(model or {}, position)
    if model and model.get("count_model"):
        sigma = 1.0
    if not math.isfinite(mean) or sigma is None:
        return float("nan"), float("nan")
    features = {key: _num(row.get(key)) for key in ((model or {}).get("kept") or [])}
    return predict_pair(
        mean,
        sigma,
        threshold,
        weight=float((model or {}).get("mixture_weight") or 1.0),
        model=model,
        features=features,
    )


def _td_pair(row, model) -> tuple[float, float]:
    rate = _num(row.get("lagged_td"))
    if not math.isfinite(rate):
        return float("nan"), float("nan")
    features = {key: _num(row.get(key)) for key in ((model or {}).get("kept") or [])}
    if not model:
        baseline = poisson_at_least(2, rate)
        return baseline, baseline
    return predict_pair(rate, 1.0, 2.0, weight=1.0, model=model, features=features)


def _bonus_gap(position, rec_base, rec_p, rush_base, rush_p, pass_base, pass_p) -> float:
    total = 0.0
    if position in {"WR", "TE", "RB"}:
        total += _gap(rec_p, rec_base)
    if position in {"RB", "QB"}:
        total += _gap(rush_p, rush_base)
    if position == "QB":
        total += _gap(pass_p, pass_base)
    return total


def _gap(model_p: float, base_p: float) -> float:
    if not math.isfinite(model_p) or not math.isfinite(base_p):
        return 0.0
    return float(model_p) - float(base_p)


def _quantile_table(calibration: dict[str, Any], position: str) -> list:
    quantiles = calibration.get("quantiles") or {}
    if position == "DST":
        return list(quantiles.get("dst") or [])
    return list(quantiles.get("skill") or [])


def _apply_dst_lagged(frame: pd.DataFrame) -> pd.DataFrame:
    """Use the prior mean of actual DST points on each defense row."""

    out = frame.copy()
    if out.empty or "position" not in out.columns or "own_lagged_fd" not in out.columns:
        return out
    dst = out["position"].astype(str).eq("DST")
    values = pd.to_numeric(out["own_lagged_fd"], errors="coerce")
    out.loc[dst, "lagged_fd"] = values.loc[dst]
    return out


def _sigma_for(model: dict[str, Any], position: str) -> float | None:
    sigma = model.get("sigma") or {}
    value = sigma.get(position, sigma.get("__all__"))
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _add_slate_interactions(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["lagged_fd"] = _lagged_fd(out)
    out["lagged_td"] = (
        _series(out, "pass_td_per_game")
        + _series(out, "rush_td_per_game")
        + _series(out, "rec_td_per_game")
    )
    out["q3_script"] = _series(out, "q3_rz_touch_share", nan=True) * _series(
        out, "opp_def_q3_slow_start", nan=True
    )
    out["q4_bringback"] = _series(out, "q4_trail_target_share", nan=True) * _series(
        out, "avg_yac_above_expectation", nan=True
    )
    out["explosive_align"] = _series(out, "air_yards_share", nan=True) * _series(
        out, "opp_def_explosive_comp_rate", nan=True
    )
    out["rush_light_box"] = _series(out, "ryoe", nan=True) * _series(
        out, "opp_def_light_box_rate", nan=True
    )
    out["rz_funnel"] = _series(out, "inside10_target_share", nan=True) * _series(
        out, "opp_def_rz_td_rate", nan=True
    )
    out["pressure_mismatch"] = _series(out, "avg_time_to_throw", nan=True) * _series(
        out, "opp_def_sack_rate", nan=True
    )
    return out


def _attach_opponent_defense(frame: pd.DataFrame, defense: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    if defense.empty or "opp" not in frame.columns and "salary_opp" not in frame.columns:
        for column in defense.columns if not defense.empty else []:
            if column != "team":
                frame[f"opp_{column}"] = np.nan
        return frame
    renamed = defense.rename(columns={column: f"opp_{column}" for column in defense.columns if column != "team"})
    renamed = renamed.rename(columns={"team": "salary_opp"})
    key = "salary_opp" if "salary_opp" in frame.columns else "opp"
    if key != "salary_opp":
        renamed = renamed.rename(columns={"salary_opp": key})
    renamed[key] = renamed[key].astype(str)
    out = frame.copy()
    out[key] = out[key].astype(str)
    return out.merge(renamed, on=key, how="left")


def _attach_salary(players: pd.DataFrame, salary: pd.DataFrame | None) -> pd.DataFrame:
    out = players.copy()
    out["player_id"] = out["player_id"].astype(str)
    out["name_key"] = out["player_name"].map(_norm_name)
    out["team_key"] = out["team"].astype(str).str.upper()
    if salary is None or salary.empty:
        out["salary_id"] = out["player_id"]
        out["salary_name"] = out["player_name"]
        out["salary_team"] = out["team"]
        out["salary_opp"] = ""
        out["salary"] = np.nan
        out["fppg"] = np.nan
        return out
    sal = salary.copy()
    sal["name_key"] = sal["full_name"].map(_norm_name)
    sal["team_key"] = sal["team"].astype(str).str.upper()
    sal["last_key"] = sal["last_name"].map(_norm_name)
    merged = sal.merge(out, on=["name_key", "team_key"], how="left", suffixes=("", "_feat"))
    missing = merged["player_id"].isna()
    if bool(missing.any()):
        _fill_unique_full_name(merged, out)
        missing = merged["player_id"].isna()
    if bool(missing.any()):
        lookup = _unique_last_name(out).drop_duplicates(["team_key", "last_key"])
        salary_counts = sal.groupby(["team_key", "last_key"]).size()
        unique_salary = set(salary_counts[salary_counts == 1].index)
        keyed = lookup.set_index(["team_key", "last_key"])
        for column in out.columns:
            if column not in merged.columns:
                merged[column] = np.nan
        for idx in merged.index[missing]:
            key = (str(merged.at[idx, "team_key"]), _norm_name(merged.at[idx, "last_name"]))
            if key not in keyed.index or key not in unique_salary:
                continue
            source = keyed.loc[key]
            if isinstance(source, pd.DataFrame):
                continue
            for column in out.columns:
                if column in {"name_key", "team_key", "team"} or column not in source.index:
                    continue
                merged.at[idx, column] = source[column]
    dst = merged["position_salary"].isin(["D", "DST", "DEF"])
    if bool(dst.any()):
        merged.loc[dst, "position"] = "DST"
        merged.loc[dst, "player_id"] = merged.loc[dst, "team_key"].map(lambda team: f"DST:{team}")
    merged["salary_id"] = merged["salary_id"].astype(str)
    merged["salary_name"] = merged["full_name"]
    merged["salary_team"] = merged["team_key"]
    merged["salary_opp"] = merged["opponent"].astype(str).str.upper()
    if "position" not in merged.columns:
        merged["position"] = merged["position_salary"]
    else:
        merged["position"] = merged["position"].where(
            merged["position"].notna(),
            merged["position_salary"],
        )
    merged.loc[merged["position"].isin(["D", "DST", "DEF"]), "position"] = "DST"
    # The salary file team is the current team. History must not replace it.
    merged["team"] = merged["team_key"].astype(str)
    merged["salary_team"] = merged["team"]
    return merged


def _fill_unique_full_name(merged: pd.DataFrame, features: pd.DataFrame) -> None:
    """Attach a traded player's history. The salary team stays in place."""

    if "name_key" not in features.columns or features.empty:
        return
    feature_counts = features.groupby("name_key").size()
    unique_features = set(feature_counts[feature_counts == 1].index)
    salary_counts = merged.groupby("name_key").size()
    unique_salary = set(salary_counts[salary_counts == 1].index)
    keyed = features.drop_duplicates("name_key").set_index("name_key")
    missing = merged["player_id"].isna()
    for column in features.columns:
        if column not in merged.columns:
            merged[column] = np.nan
    for idx in merged.index[missing]:
        key = merged.at[idx, "name_key"]
        if key not in unique_features or key not in unique_salary or key not in keyed.index:
            continue
        source = keyed.loc[key]
        if isinstance(source, pd.DataFrame):
            continue
        for column in features.columns:
            if column in {"name_key", "team_key", "team"} or column not in source.index:
                continue
            merged.at[idx, column] = source[column]


def _unique_last_name(players: pd.DataFrame) -> pd.DataFrame:
    work = players.copy()
    work["last_key"] = work["player_name"].map(lambda name: _norm_name(str(name).split(" ")[-1]))
    counts = work.groupby(["team_key", "last_key"]).size()
    unique = counts[counts == 1].reset_index()[["team_key", "last_key"]]
    return work.merge(unique, on=["team_key", "last_key"], how="inner")


def _qb_pairs(scored, thresholds, correlation, kind, *, same_team: bool) -> list[dict[str, Any]]:
    boost = float((correlation.get(kind) or {}).get("boost") or 0.0)
    qbs = scored.loc[scored["position"].astype(str).eq("QB")]
    if kind == "qb_skill":
        skills = scored.loc[scored["position"].astype(str).isin(["WR", "TE"])].copy()
        cutoff = thresholds.get("q3_rz_touch_share_p75", float("nan"))
        skills = skills.loc[
            _series(skills, "q3_rz_touch_share").ge(cutoff)
            & _series(skills, "opp_def_q3_slow_start").gt(0)
            if math.isfinite(_float_or_nan(cutoff))
            else False
        ]
    else:
        skills = scored.loc[scored["position"].astype(str).isin(["WR", "RB"])].copy()
        cutoff = thresholds.get("q4_trail_target_share_p75", float("nan"))
        skills = skills.loc[
            _series(skills, "q4_trail_target_share").ge(cutoff)
            & _series(skills, "avg_yac_above_expectation").gt(0)
            if math.isfinite(_float_or_nan(cutoff))
            else False
        ]
    rows = []
    for skill in skills.to_dict(orient="records"):
        if same_team:
            mates = qbs.loc[qbs["team"].astype(str).eq(str(skill.get("team")))]
        else:
            mates = qbs.loc[qbs["team"].astype(str).eq(str(skill.get("opp")))]
        for qb in mates.to_dict(orient="records"):
            rows.append(
                {
                    "player_a": qb.get("player_id"),
                    "player_b": skill.get("player_id"),
                    "kind": kind,
                    "corr_boost": boost,
                }
            )
    return rows


def _rb_dst_pairs(scored, thresholds, correlation) -> list[dict[str, Any]]:
    boost = float((correlation.get("rb_dst") or {}).get("boost") or 0.0)
    cutoff = _float_or_nan(thresholds.get("def_sack_rate_p75"))
    rbs = scored.loc[scored["position"].astype(str).eq("RB")]
    dsts = scored.loc[scored["position"].astype(str).eq("DST")]
    rows = []
    if not math.isfinite(cutoff):
        return rows
    for rb in rbs.to_dict(orient="records"):
        mates = dsts.loc[dsts["team"].astype(str).eq(str(rb.get("opp")))]
        for dst in mates.to_dict(orient="records"):
            rate = _num(rb.get("opp_def_sack_rate"))
            if not math.isfinite(rate) or rate < cutoff:
                continue
            rows.append(
                {
                    "player_a": rb.get("player_id"),
                    "player_b": dst.get("player_id"),
                    "kind": "rb_dst",
                    "corr_boost": boost,
                }
            )
    return rows


def _read_salary(path: Path | None) -> pd.DataFrame:
    if path is None or not path.is_file():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    rename = {column: column.strip() for column in frame.columns}
    frame = frame.rename(columns=rename)

    def col(name: str) -> pd.Series:
        if name in frame.columns:
            return frame[name]
        return pd.Series([""] * len(frame))

    first = col("First Name").astype(str)
    last = col("Last Name").astype(str)
    nickname = col("Nickname").astype(str)
    full = nickname.where(nickname.str.strip().ne("") & nickname.ne("nan"), (first + " " + last).str.strip())
    return pd.DataFrame(
        {
            "salary_id": col("Id").astype(str),
            "position_salary": col("Position").astype(str).str.upper(),
            "full_name": full,
            "last_name": last,
            "team": col("Team").map(canon_team),
            "opponent": col("Opponent").map(canon_team),
            "salary": pd.to_numeric(col("Salary"), errors="coerce"),
            "fppg": pd.to_numeric(col("FPPG"), errors="coerce"),
            "injury_indicator": col("Injury Indicator").astype(str),
        }
    )


def _salary_path(season: int, week: int, salary_path: Path | None) -> Path | None:
    if salary_path is not None:
        return Path(salary_path)
    return SALARY_BY_SLATE.get((int(season), int(week)))


def _read_cached(path: Path, columns: tuple[str, ...], used: list[str], missing: list[str]) -> pd.DataFrame:
    if not path.is_file():
        missing.append(path.name)
        return pd.DataFrame()
    frame = pd.read_parquet(path)
    used.append(path.name)
    keep = [column for column in columns if column in frame.columns]
    if not keep:
        return frame
    return frame.loc[:, keep].copy()


def _concat(parts: list[pd.DataFrame]) -> pd.DataFrame:
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def _attach_own_defense(frame: pd.DataFrame, defense: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or defense.empty or "salary_team" not in frame.columns:
        return frame
    renamed = defense.rename(
        columns={column: f"own_{column}" for column in defense.columns if column != "team"}
    )
    renamed = renamed.rename(columns={"team": "salary_team"})
    renamed["salary_team"] = renamed["salary_team"].astype(str).str.upper()
    out = frame.copy()
    out["salary_team"] = out["salary_team"].astype(str).str.upper()
    return out.merge(renamed, on="salary_team", how="left")


def _copy_opposing_qb(frame: pd.DataFrame) -> pd.DataFrame:
    """Copy the active opposing quarterback onto each defense row.

    Out and IR quarterbacks are skipped. The two dst_10 features and the
    hold time use that active quarterback's salary-file team.
    """

    out = frame.copy()
    out["opp_qb_time"] = np.nan
    if out.empty or "position" not in out.columns or "salary_opp" not in out.columns:
        return out
    status = out.get("injury_status", pd.Series("", index=out.index)).astype(str)
    active = ~status.isin(["OUT", "IR"])
    qbs = out.loc[out["position"].astype(str).eq("QB") & active].copy()
    dst = out["position"].astype(str).eq("DST")
    if not qbs.empty:
        qbs["_team"] = qbs["team"].astype(str)
        qbs["_attempts"] = _series(qbs, "pass_att_per_game")
        qbs = qbs.sort_values(["_team", "_attempts"], kind="mergesort")
        starter = qbs.groupby("_team", as_index=False).tail(1)
        opp = out.loc[dst, "salary_opp"].astype(str)
        copied = {
            "avg_time_to_throw": "opp_avg_time_to_throw",
            "int_worthy_rate": "opp_int_worthy_rate",
            "qb_fault_sack_rate": "opp_qb_fault_sack_rate",
            "team_q4_trail_pass_share": "opp_q4_trail_pass_share",
        }
        for source, target in copied.items():
            series = _series(starter, source, nan=True)
            mapping = pd.Series(series.to_numpy(), index=starter["_team"].astype(str).to_numpy())
            out.loc[dst, target] = opp.map(mapping).to_numpy()
        out.loc[dst, "opp_qb_time"] = out.loc[dst, "opp_avg_time_to_throw"]
        out.loc[dst, "avg_time_to_throw"] = out.loc[dst, "opp_avg_time_to_throw"]
    own_sack = _series(out, "own_def_sack_rate", nan=True)
    own_to = _series(out, "own_def_to_rate", nan=True)
    out.loc[dst, "def_sack_rate"] = own_sack.loc[dst].to_numpy()
    out.loc[dst, "def_to_rate"] = own_to.loc[dst].to_numpy()
    hold = _series(out, "opp_avg_time_to_throw", nan=True)
    out.loc[dst, "pressure_mismatch"] = hold.loc[dst].to_numpy() * own_sack.loc[dst].to_numpy()
    return out


def _apply_report_flags(frame: pd.DataFrame, calibration: dict[str, Any]) -> pd.DataFrame:
    out = frame.copy()
    thresholds = calibration.get("thresholds") or {}
    q3_cut = _float_or_nan(thresholds.get("q3_rz_touch_share_p75"))
    q4_cut = _float_or_nan(thresholds.get("q4_trail_target_share_p75"))
    position = out.get("position", pd.Series("", index=out.index)).astype(str)
    eligible = _series(out, "lagged_fd").ge(6.0) | _series(out, "trail4_opps").ge(12.0)
    if math.isfinite(q3_cut):
        q3 = (
            position.isin(["WR", "TE"])
            & eligible
            & _series(out, "q3_rz_touch_share").ge(q3_cut)
            & _series(out, "opp_def_q3_slow_start").gt(0)
        )
    else:
        q3 = pd.Series(False, index=out.index)
    if math.isfinite(q4_cut):
        q4 = (
            position.isin(["WR", "RB", "QB"])
            & eligible
            & _series(out, "q4_trail_target_share").ge(q4_cut)
            & _series(out, "avg_yac_above_expectation").gt(0)
        )
    else:
        q4 = pd.Series(False, index=out.index)
    dst = position.eq("DST") & _series(out, "avg_time_to_throw", nan=True).gt(HOLD_TIME_SECONDS)
    out["q3_flag"] = q3.fillna(False).to_numpy()
    out["q4_flag"] = q4.fillna(False).to_numpy()
    out["dst_flag"] = dst.fillna(False).to_numpy()
    return out


def _lagged_fd(frame: pd.DataFrame) -> pd.Series:
    formula = (
        _series(frame, "pass_yds_per_game") * 0.04
        + _series(frame, "pass_td_per_game") * 4.0
        - _series(frame, "int_per_game")
        + _series(frame, "rush_yds_per_game") * 0.1
        + _series(frame, "rush_td_per_game") * 6.0
        + _series(frame, "receptions_per_game") * 0.5
        + _series(frame, "rec_yds_per_game") * 0.1
        + _series(frame, "rec_td_per_game") * 6.0
        - _series(frame, "fumbles_per_game") * 2.0
    )
    if "fd_points_per_game" not in frame.columns:
        return formula
    hist = _series(frame, "fd_points_per_game", nan=True)
    return hist.where(hist.notna() & hist.gt(0), formula)


def _series(frame: pd.DataFrame, column: str, *, nan: bool = False) -> pd.Series:
    if column not in frame.columns:
        fill = np.nan if nan else 0.0
        return pd.Series(fill, index=frame.index)
    values = pd.to_numeric(frame[column], errors="coerce")
    if nan:
        return values
    return values.fillna(0.0)


def _norm_name(value: object) -> str:
    text = re.sub(r"[^a-z0-9 ]+", "", str(value).lower())
    return " ".join(text.split())


def _num(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("nan")
    if not math.isfinite(number):
        return float("nan")
    return number


def _float_or_nan(value: object) -> float:
    return _num(value)


def _canon(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canon(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canon(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if not math.isfinite(number):
            return None
        return round(number, 6)
    if value is None:
        return None
    return value
