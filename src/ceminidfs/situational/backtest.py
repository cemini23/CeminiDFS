"""Out-of-sample tail calibration and BH-FDR feature gate.

Training weeks choose the lognormal sigma, the mixture weight, and the
situational coefficients. Stage 1 runs BH-FDR on that training split.
Stage 2 refits an offset logistic on the FDR survivors only. The fit uses a
strong ridge penalty, divides the feature log-odds by the square root of the
survivor count, then shrinks that delta by an inner-validation alpha. Later
weeks score Brier, log loss, and top-decile hit rate. A coefficient is exported
when the holdout Brier gain is positive and its interval is above zero. A
holdout under 500 rows may also pass when the point lift is at least 0.40, the
top decile rises, and at least 80 percent of bootstrap draws are positive.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import gamma, lognorm, norm

from ceminidfs.models.scoring import fd_points
from ceminidfs.situational.contract import DST_FEATURES, SKILL_FEATURES
from ceminidfs.situational.fdr import benjamini_hochberg, kept_features
from ceminidfs.situational.features import tables_from_grains
from ceminidfs.situational.quantiles import fit_residual_table
from ceminidfs.situational.stack_corr import estimate_pair_boost
from ceminidfs.situational.tail import fit_log_sigma, poisson_at_least

DEFAULT_SEED = 20261017
MIN_TRAIN_WEEKS = 6
MIN_TEST_WEEKS = 2
MIN_SLATE_GAMES = 8
RIDGE_C = 0.05
ALPHA_GRID = (0.02, 0.05, 0.08, 0.12, 0.18, 0.25, 0.40, 0.60, 1.00)
SMALL_HOLDOUT = 500
POINT_LIFT_FLOOR = 0.40
POSITIVE_DRAW_FLOOR = 0.80


def calibrate_history(
    grains,
    *,
    seed: int = DEFAULT_SEED,
    n_boot: int = 400,
) -> dict[str, Any]:
    """Fit the gated tail models and the stack boosts on a history grain."""

    skill = _skill_panel(grains)
    defense = _dst_panel(grains, skill)
    result: dict[str, Any] = {"seed": int(seed), "targets": {}, "correlation": {}}
    specs = (
        ("rec_100", skill, "rec_yds", 100.0, "rec_yds_per_game", SKILL_FEATURES, _rec_mask),
        ("rush_100", skill, "rush_yds", 100.0, "rush_yds_per_game", SKILL_FEATURES, _rush_mask),
        ("pass_300", skill, "pass_yds", 300.0, "pass_yds_per_game", SKILL_FEATURES, _pass_mask),
        ("fpts_25", skill, "fd_points", 25.0, "lagged_fd", SKILL_FEATURES, _skill_mask),
        ("fpts_20", skill, "fd_points", 20.0, "lagged_fd", SKILL_FEATURES, _skill_mask),
        ("multi_td", skill, "total_td", 2.0, "lagged_td", SKILL_FEATURES, _skill_mask),
        ("dst_10", defense, "fd_points", 10.0, "lagged_fd", DST_FEATURES, _dst_mask),
    )
    for name, panel, actual, threshold, mean_col, features, mask in specs:
        if panel.empty:
            result["targets"][name] = _empty_target(name)
            continue
        part = panel.loc[mask(panel)].copy()
        result["targets"][name] = _calibrate_one(
            part,
            name=name,
            actual_col=actual,
            threshold=threshold,
            mean_col=mean_col,
            features=features,
            seed=seed,
            n_boot=n_boot,
            count_model=name == "multi_td",
        )
    result["correlation"] = _calibrate_correlations(skill, defense, seed=seed, n_boot=min(n_boot, 200))
    result["thresholds"] = _thresholds(skill)
    result["quantiles"] = {
        "skill": fit_residual_table(_train_frame(skill)),
        "dst": fit_residual_table(_dst_quantile_rows(_train_frame(defense))),
    }
    return result


def format_calibration_table(result: dict[str, Any]) -> str:
    """Plain text table of the holdout tail calibration."""

    lines = [
        "target      n_test  base_brier  model_brier  delta_brier   ci_low   ci_high  "
        "base_top10  model_top10  point_lift  kept  gate   alpha"
    ]
    for name, model in result.get("targets", {}).items():
        metrics = model.get("metrics", {})
        kept = ",".join(model.get("kept", [])) or "-"
        lines.append(
            f"{name:<11} {int(metrics.get('n_test', 0)):>6}  "
            f"{_fmt(metrics.get('baseline_brier')):>10}  "
            f"{_fmt(metrics.get('model_brier')):>11}  "
            f"{_fmt(metrics.get('delta_brier')):>11}  "
            f"{_fmt(metrics.get('delta_brier_ci_low')):>8}  "
            f"{_fmt(metrics.get('delta_brier_ci_high')):>8}  "
            f"{_fmt(metrics.get('baseline_top_decile'), 3):>10}  "
            f"{_fmt(metrics.get('model_top_decile'), 3):>11}  "
            f"{_fmt(metrics.get('top_decile_point_lift'), 3):>10}  "
            f"{kept}  {str(bool(model.get('export'))).lower()}  {_fmt(model.get('alpha'), 2)}"
        )
    lines.append("correlation")
    for kind, estimate in result.get("correlation", {}).items():
        lines.append(
            f"  {kind:<16} boost={estimate.get('boost', 0.0):+.3f}  "
            f"delta={estimate.get('train_delta', 0.0):+.3f}  "
            f"ci=[{estimate.get('ci_low', 0.0):+.3f}, {estimate.get('ci_high', 0.0):+.3f}]  "
            f"test_improved={str(bool(estimate.get('test_improved'))).lower()}"
        )
    return "\n".join(lines)


def format_fdr_table(result: dict[str, Any]) -> str:
    """Plain text table of BH q-values for each target."""

    lines = ["target      feature                          p_value   q_value  reject  exported"]
    for name, model in result.get("targets", {}).items():
        exported = set(model.get("kept") or [])
        rows = model.get("fdr") or []
        if not rows:
            lines.append(f"{name:<11} {'-':<32} {'-':>7}  {'-':>7}  false   false")
            continue
        for row in rows:
            feature = str(row.get("feature", ""))
            lines.append(
                f"{name:<11} {feature:<32} "
                f"{_fmt(row.get('p_value'), 4):>7}  {_fmt(row.get('q_value'), 4):>7}  "
                f"{str(bool(row.get('reject'))).lower():<5}  {str(feature in exported).lower()}"
            )
    return "\n".join(lines)


def _fmt(value: Any, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "nan"
    if not math.isfinite(number):
        return "nan"
    return f"{number:.{digits}f}"


def predict_bonus(
    mean: float,
    sigma: float,
    threshold: float,
    *,
    weight: float,
    model: dict[str, Any] | None = None,
    features: dict[str, float] | None = None,
) -> float:
    """Baseline mixture probability, replaced by the gated logit when exported."""

    baseline, adjusted = predict_pair(
        mean,
        sigma,
        threshold,
        weight=weight,
        model=model,
        features=features,
    )
    if not model or not model.get("export"):
        return baseline
    return adjusted


def predict_pair(
    mean: float,
    sigma: float,
    threshold: float,
    *,
    weight: float,
    model: dict[str, Any] | None = None,
    features: dict[str, float] | None = None,
) -> tuple[float, float]:
    """Return the baseline probability and the gated probability."""

    baseline = _baseline_probability(mean, sigma, threshold, weight, model)
    if not model or not model.get("export"):
        return baseline, baseline
    return baseline, _apply_logit(baseline, features or {}, model)


def _skill_panel(grains) -> pd.DataFrame:
    weeks = _eval_weeks(grains)
    frames = []
    for season, week in weeks:
        tables = tables_from_grains(grains, season=int(season), week=int(week))
        outcomes = _week_outcomes(grains, int(season), int(week))
        if outcomes.empty or tables.players.empty:
            continue
        features = tables.players.copy()
        features["player_id"] = features["player_id"].astype(str)
        merged = outcomes.merge(features, on="player_id", how="inner", suffixes=("", "_feat"))
        defense = _prefix_defense(tables.defense)
        if not defense.empty and "opp" in merged.columns:
            merged = merged.merge(defense, on="opp", how="left")
        merged["season"] = int(season)
        merged["week"] = int(week)
        frames.append(merged)
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)
    panel["lagged_fd"] = _lagged_fd(panel)
    panel["lagged_td"] = (
        pd.to_numeric(panel.get("pass_td_per_game"), errors="coerce").fillna(0.0)
        + pd.to_numeric(panel.get("rush_td_per_game"), errors="coerce").fillna(0.0)
        + pd.to_numeric(panel.get("rec_td_per_game"), errors="coerce").fillna(0.0)
    )
    return _add_interactions(panel)


def _dst_panel(grains, skill: pd.DataFrame) -> pd.DataFrame:
    if grains.defense.empty:
        return pd.DataFrame()
    weeks = _eval_weeks(grains)
    frames = []
    for season, week in weeks:
        current = grains.defense.loc[
            (pd.to_numeric(grains.defense["season"]) == season)
            & (pd.to_numeric(grains.defense["week"]) == week)
        ].copy()
        if current.empty:
            continue
        tables = tables_from_grains(grains, season=int(season), week=int(week))
        lagged = tables.defense.rename(columns={"team": "team"})
        merged = current.merge(lagged, on="team", how="left", suffixes=("", "_lag"))
        merged["fd_points"] = [
            _dst_points(row) for row in merged.to_dict(orient="records")
        ]
        merged["season"] = int(season)
        merged["week"] = int(week)
        merged["opp"] = _offense_opponent(grains, int(season), int(week), merged["team"])
        qb = _opposing_qb(skill, merged)
        merged = merged.merge(qb, on=["season", "week", "team"], how="left")
        merged["pressure_mismatch"] = pd.to_numeric(
            merged.get("opp_avg_time_to_throw"), errors="coerce"
        ) * pd.to_numeric(merged.get("def_sack_rate"), errors="coerce")
        frames.append(merged)
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values(["team", "season", "week"], kind="mergesort")
    panel["lagged_fd"] = panel.groupby("team", sort=False)["fd_points"].transform(
        lambda values: values.shift(1).expanding(min_periods=1).mean()
    )
    return panel.reset_index(drop=True)


def _calibrate_one(
    panel: pd.DataFrame,
    *,
    name: str,
    actual_col: str,
    threshold: float,
    mean_col: str,
    features: tuple[str, ...],
    seed: int,
    n_boot: int,
    count_model: bool,
) -> dict[str, Any]:
    if panel.empty or actual_col not in panel.columns or mean_col not in panel.columns:
        return _empty_target(name)
    train, test = _time_split(panel)
    if len(train) < 40 or test.empty:
        return _empty_target(name)
    sigma_map = _sigma_by_position(train, actual_col)
    if not sigma_map or sigma_map.get("__all__") is None and len(sigma_map) == 0:
        return _empty_target(name)
    train = _with_baseline(train, actual_col, threshold, mean_col, sigma_map, count_model)
    test = _with_baseline(test, actual_col, threshold, mean_col, sigma_map, count_model)
    train = train.loc[train["p_base"].notna() & train["y"].notna()].copy()
    test = test.loc[test["p_base"].notna() & test["y"].notna()].copy()
    if len(train) < 40 or test.empty:
        return _empty_target(name)
    weight = 1.0 if count_model else _choose_weight(train, threshold)
    if not count_model:
        train = _with_baseline(train, actual_col, threshold, mean_col, sigma_map, False, weight)
        test = _with_baseline(test, actual_col, threshold, mean_col, sigma_map, False, weight)
    design = _design(train, test, features)
    metrics = _score_design(train, test, design, seed=seed, n_boot=n_boot)
    export = _export_gate(metrics)
    return {
        "name": name,
        "export": export,
        "alpha": metrics.get("alpha", 1.0),
        "kept": metrics["kept"] if export else [],
        "coefficients": metrics["coefficients"] if export else {},
        "center": metrics["center"] if export else {},
        "scale": metrics["scale"] if export else {},
        "sigma": {key: value for key, value in sigma_map.items() if value is not None},
        "mixture_weight": weight,
        "threshold": threshold,
        "mean_column": mean_col,
        "count_model": count_model,
        "metrics": {key: value for key, value in metrics.items() if key not in {"coefficients", "center", "scale", "kept", "fdr"}},
        "fdr": metrics["fdr"],
        "candidate_kept": metrics["kept"],
    }


def _score_design(train, test, design, *, seed: int, n_boot: int) -> dict[str, Any]:
    names = design["names"]
    y_train = train["y"].to_numpy(dtype=float)
    _beta, _se, p_values = _fit_logit(design["x_train"], y_train)
    # Column 0 is the intercept. Column 1 is the baseline logit. FDR starts at column 2.
    feature_p = p_values[2:]
    fdr = benjamini_hochberg(dict(zip(names, feature_p, strict=True)))
    kept = [feature for feature in kept_features(fdr) if feature in names]
    p_base = test["p_base"].to_numpy(dtype=float)
    y = test["y"].to_numpy(dtype=float)
    points = test["fd_points"].to_numpy(dtype=float) if "fd_points" in test.columns else y
    alpha = 1.0
    coefficients: dict[str, float] = {}
    if not kept:
        p_model = p_base
    else:
        # Stage 2 uses only the baseline offset and the FDR survivors.
        kept_index = [names.index(feature) + 2 for feature in kept]
        x_train = design["x_train"][:, kept_index]
        x_test = design["x_test"][:, kept_index]
        offset_train = _logit(train["p_base"].to_numpy(dtype=float))
        offset_test = _logit(p_base)
        l2 = _ridge_penalty()
        damp = _collinear_damp(x_train.shape[1])
        alpha = _choose_alpha(train, x_train, offset_train, y_train, l2=l2, damp=damp)
        beta = _fit_logit_offset(x_train, y_train, offset_train, l2=l2)
        p_model = _sigmoid(offset_test + (alpha * damp) * (x_test @ beta))
        coefficients = {"intercept": 0.0, "baseline": 1.0}
        coefficients.update(
            {
                feature: float(alpha * damp * value)
                for feature, value in zip(kept, beta, strict=True)
            }
        )
    delta, ci_low, ci_high, lift, positive_share = _bootstrap(
        y, points, p_base, p_model, seed=seed, n_boot=n_boot
    )
    return {
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "baseline_brier": _brier(p_base, y),
        "model_brier": _brier(p_model, y),
        "baseline_logloss": _logloss(p_base, y),
        "model_logloss": _logloss(p_model, y),
        "baseline_top_decile": _top_decile(p_base, y),
        "model_top_decile": _top_decile(p_model, y),
        "delta_brier": delta,
        "delta_brier_ci_low": ci_low,
        "delta_brier_ci_high": ci_high,
        "top_decile_point_lift": lift,
        "delta_brier_positive_share": positive_share,
        "alpha": alpha,
        "kept": kept,
        "coefficients": coefficients,
        "center": design["center"],
        "scale": design["scale"],
        "fdr": fdr.to_dict(orient="records"),
    }


def _choose_alpha(
    train: pd.DataFrame,
    x: np.ndarray,
    offset: np.ndarray,
    y: np.ndarray,
    *,
    l2: float,
    damp: float,
) -> float:
    """Pick shrinkage on an inner time split of the training weeks."""

    if "season" not in train.columns or "week" not in train.columns or x.shape[1] == 0:
        return 0.12
    inner_train, inner_valid = _time_split(train)
    if inner_train.empty or inner_valid.empty:
        return 0.12
    train_keys = set(zip(inner_train["season"].astype(int), inner_train["week"].astype(int), strict=True))
    valid_keys = set(zip(inner_valid["season"].astype(int), inner_valid["week"].astype(int), strict=True))
    keys = list(zip(train["season"].astype(int), train["week"].astype(int), strict=True))
    train_mask = np.array([key in train_keys for key in keys])
    valid_mask = np.array([key in valid_keys for key in keys])
    if int(train_mask.sum()) < 30 or int(valid_mask.sum()) < 10:
        return 0.12
    beta = _fit_logit_offset(x[train_mask], y[train_mask], offset[train_mask], l2=l2)
    best_alpha = ALPHA_GRID[0]
    best_score = float("inf")
    for alpha in ALPHA_GRID:
        delta = (alpha * damp) * (x[valid_mask] @ beta)
        score = _brier(_sigmoid(offset[valid_mask] + delta), y[valid_mask])
        if score < best_score - 1e-12:
            best_score = score
            best_alpha = alpha
    return best_alpha


def _ridge_penalty() -> float:
    """Inverse of the logistic C. A small C is a strong L2 penalty."""

    return 1.0 / RIDGE_C


def _collinear_damp(n_features: int) -> float:
    """Shrink a sum of correlated log-odds by the survivor count."""

    return 1.0 / math.sqrt(max(int(n_features), 1))


def _export_gate(metrics: dict[str, Any]) -> bool:
    """Return true when the holdout rule clears a pruned model."""

    if not metrics.get("kept"):
        return False
    if float(metrics["delta_brier"]) <= 0.0:
        return False
    if float(metrics["delta_brier_ci_low"]) > 0.0:
        return True
    small_sample = (
        int(metrics["n_test"]) < SMALL_HOLDOUT
        and float(metrics["top_decile_point_lift"]) >= POINT_LIFT_FLOOR
        and float(metrics["model_top_decile"]) > float(metrics["baseline_top_decile"])
        and float(metrics["delta_brier_positive_share"]) >= POSITIVE_DRAW_FLOOR
    )
    return bool(small_sample)


def _fit_logit_offset(x: np.ndarray, y: np.ndarray, offset: np.ndarray, l2: float = 1.0) -> np.ndarray:
    """Ridge logistic with a fixed baseline-logit offset. Feature betas are penalized."""

    if x.size == 0 or x.shape[1] == 0:
        return np.zeros(0, dtype=float)
    beta = np.zeros(x.shape[1], dtype=float)
    penalty = np.full(x.shape[1], l2)
    for _ in range(40):
        eta = np.clip(offset + x @ beta, -20.0, 20.0)
        mu = 1.0 / (1.0 + np.exp(-eta))
        weight = np.clip(mu * (1.0 - mu), 1e-4, None)
        response = (eta - offset) + (y - mu) / weight
        weighted = x.T * weight
        gram = weighted @ x
        gram.flat[:: x.shape[1] + 1] += penalty
        solved = weighted @ response
        try:
            step = np.linalg.solve(gram, solved)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(gram, solved, rcond=None)[0]
        if float(np.max(np.abs(step - beta))) < 1e-6:
            beta = step
            break
        beta = step
    return beta


def _design(train: pd.DataFrame, test: pd.DataFrame, features: tuple[str, ...]) -> dict[str, Any]:
    usable = []
    for feature in features:
        if feature not in train.columns:
            continue
        values = pd.to_numeric(train[feature], errors="coerce")
        if float(values.notna().mean()) < 0.60:
            continue
        usable.append(feature)
    center = {}
    scale = {}
    train_cols = []
    test_cols = []
    kept_names = []
    for feature in usable:
        train_values = pd.to_numeric(train[feature], errors="coerce")
        fill = float(train_values.median()) if train_values.notna().any() else 0.0
        if not math.isfinite(fill):
            fill = 0.0
        train_filled = train_values.fillna(fill)
        std = float(train_filled.std(ddof=1))
        if not math.isfinite(std) or std < 1e-8:
            continue
        mean = float(train_filled.mean())
        center[feature] = mean
        scale[feature] = std
        test_values = pd.to_numeric(test[feature], errors="coerce").fillna(fill)
        train_cols.append(((train_filled - mean) / std).clip(-3.0, 3.0))
        test_cols.append(((test_values - mean) / std).clip(-3.0, 3.0))
        kept_names.append(feature)
    base_train = _logit(train["p_base"].to_numpy(dtype=float))
    base_test = _logit(test["p_base"].to_numpy(dtype=float))
    ones_train = np.ones(len(train))
    ones_test = np.ones(len(test))
    columns_train = [ones_train, base_train, *train_cols]
    columns_test = [ones_test, base_test, *test_cols]
    return {
        "names": kept_names,
        "x_train": np.column_stack(columns_train),
        "x_test": np.column_stack(columns_test),
        "center": center,
        "scale": scale,
    }


def _with_baseline(frame, actual_col, threshold, mean_col, sigma_map, count_model, weight: float = 1.0):
    out = frame.copy()
    actual = pd.to_numeric(out[actual_col], errors="coerce")
    if count_model:
        out["y"] = (actual >= threshold).astype(float)
        rate = pd.to_numeric(out[mean_col], errors="coerce").clip(lower=0.0)
        out["p_base"] = 1.0 - np.exp(-rate) * (1.0 + rate)
        out["p_base"] = out["p_base"].where(rate.notna(), np.nan)
    else:
        out["y"] = (actual >= threshold).astype(float)
        sigma = out.get("position", pd.Series("UNK", index=out.index)).map(
            lambda position: sigma_map.get(str(position), sigma_map.get("__all__"))
        )
        mean = pd.to_numeric(out[mean_col], errors="coerce")
        out["baseline_mean"] = mean
        out["sigma"] = pd.to_numeric(sigma, errors="coerce")
        out["p_base"] = [
            _one_survival(m, s, threshold, weight) if pd.notna(m) and pd.notna(s) else np.nan
            for m, s in zip(mean, out["sigma"], strict=True)
        ]
    if "fd_points" not in out.columns:
        out["fd_points"] = actual
    return out


def _choose_weight(train: pd.DataFrame, threshold: float) -> float:
    y = train["y"].to_numpy(dtype=float)
    best_weight = 1.0
    best_score = float("inf")
    if "baseline_mean" not in train.columns:
        return 1.0
    raw_mean = pd.to_numeric(train["baseline_mean"], errors="coerce")
    sigma = pd.to_numeric(train.get("sigma"), errors="coerce")
    if raw_mean.notna().sum() == 0 or sigma.notna().sum() == 0:
        return 1.0
    for weight in (0.0, 0.25, 0.5, 0.75, 1.0):
        probabilities = np.array(
            [
                _one_survival(m, s, threshold, weight) if pd.notna(m) and pd.notna(s) else np.nan
                for m, s in zip(raw_mean, sigma, strict=True)
            ]
        )
        valid = np.isfinite(probabilities)
        if int(valid.sum()) < 20:
            continue
        score = _brier(probabilities[valid], y[valid])
        if score < best_score:
            best_score = score
            best_weight = weight
    return best_weight


def _one_survival(mean: float, sigma: float, threshold: float, weight: float) -> float:
    if mean is None or sigma is None or not math.isfinite(mean) or not math.isfinite(sigma):
        return float("nan")
    if mean <= 0 or sigma <= 0 or threshold <= 0:
        return 0.0
    median = mean * math.exp(-0.5 * sigma * sigma)
    p_log = float(lognorm.sf(threshold, s=sigma, scale=median))
    moments_mean = median * math.exp(0.5 * sigma * sigma)
    variance = (math.exp(sigma * sigma) - 1.0) * math.exp(2.0 * math.log(median) + sigma * sigma)
    if variance <= 0 or moments_mean <= 0:
        p_gamma = p_log
    else:
        shape = (moments_mean * moments_mean) / variance
        scale = variance / moments_mean
        p_gamma = float(gamma.sf(threshold, a=shape, scale=scale))
    weight = min(1.0, max(0.0, weight))
    return float(min(1.0, max(0.0, weight * p_log + (1.0 - weight) * p_gamma)))


def _sigma_by_position(train: pd.DataFrame, actual_col: str) -> dict[str, float | None]:
    sigmas: dict[str, float | None] = {}
    if "position" not in train.columns:
        train = train.copy()
        train["position"] = "UNK"
    for position, part in train.groupby(train["position"].astype(str)):
        sigma = fit_log_sigma(pd.to_numeric(part[actual_col], errors="coerce"))
        if sigma is not None:
            sigmas[str(position)] = sigma
    sigmas["__all__"] = fit_log_sigma(pd.to_numeric(train[actual_col], errors="coerce"))
    return sigmas


def _time_split(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    weeks = (
        panel[["season", "week"]]
        .drop_duplicates()
        .sort_values(["season", "week"], kind="mergesort")
        .reset_index(drop=True)
    )
    test_n = max(MIN_TEST_WEEKS, int(math.ceil(len(weeks) * 0.20)))
    test_n = min(test_n, max(1, len(weeks) - MIN_TRAIN_WEEKS))
    if len(weeks) - test_n < MIN_TRAIN_WEEKS:
        return panel.iloc[0:0].copy(), panel.iloc[0:0].copy()
    train_weeks = set(
        zip(weeks.iloc[:-test_n]["season"], weeks.iloc[:-test_n]["week"], strict=True)
    )
    test_weeks = set(zip(weeks.iloc[-test_n:]["season"], weeks.iloc[-test_n:]["week"], strict=True))
    keys = list(zip(panel["season"], panel["week"], strict=True))
    train = panel.loc[[key in train_weeks for key in keys]].copy()
    test = panel.loc[[key in test_weeks for key in keys]].copy()
    return train, test


def _week_outcomes(grains, season: int, week: int) -> pd.DataFrame:
    players = grains.players
    if players.empty:
        return players
    mask = (pd.to_numeric(players["season"]) == season) & (pd.to_numeric(players["week"]) == week)
    rows = players.loc[mask].copy()
    if rows.empty:
        return rows
    rows["player_id"] = rows["player_id"].astype(str)
    rows["fd_points"] = [_skill_points(row) for row in rows.to_dict(orient="records")]
    rows["total_td"] = (
        pd.to_numeric(rows.get("pass_td"), errors="coerce").fillna(0.0)
        + pd.to_numeric(rows.get("rush_td"), errors="coerce").fillna(0.0)
        + pd.to_numeric(rows.get("rec_td"), errors="coerce").fillna(0.0)
    )
    return rows


def _skill_points(row: dict) -> float:
    return float(
        fd_points(
            {
                "pass_yds": row.get("pass_yds", 0.0),
                "pass_td": row.get("pass_td", 0.0),
                "int": row.get("interceptions", 0.0),
                "rush_yds": row.get("rush_yds", 0.0),
                "rush_td": row.get("rush_td", 0.0),
                "rec": row.get("receptions", 0.0),
                "rec_yds": row.get("rec_yds", 0.0),
                "rec_td": row.get("rec_td", 0.0),
                "fumbles_lost": row.get("fumbles_lost", 0.0),
            }
        )
    )


def _dst_points(row: dict) -> float:
    stats = {
        "dst_sacks": row.get("sacks", 0.0),
        "dst_int": row.get("interceptions", 0.0),
        "dst_opp_fumbles_lost": row.get("fumbles", 0.0),
        "dst_td": row.get("dst_td", 0.0),
        "dst_safety": row.get("safeties", 0.0),
    }
    points_allowed = row.get("points_allowed")
    if points_allowed is not None and pd.notna(points_allowed):
        stats["dst_points_allowed"] = points_allowed
    return float(fd_points(stats))


def _eval_weeks(grains) -> list[tuple[int, int]]:
    sizes = grains.slate_sizes
    if sizes is None or sizes.empty:
        return []
    keep = sizes.loc[
        (pd.to_numeric(sizes["games"]) >= MIN_SLATE_GAMES) & (pd.to_numeric(sizes["week"]) <= 18)
    ]
    pairs = []
    for row in keep.sort_values(["season", "week"], kind="mergesort").itertuples(index=False):
        pairs.append((int(row.season), int(row.week)))
    return pairs


def _prefix_defense(defense: pd.DataFrame) -> pd.DataFrame:
    if defense.empty:
        return defense
    rename = {column: f"opp_{column}" for column in defense.columns if column != "team"}
    out = defense.rename(columns={"team": "opp", **rename})
    out["opp"] = out["opp"].astype(str)
    return out


def _add_interactions(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()

    def col(name: str) -> pd.Series:
        if name not in out.columns:
            return pd.Series(np.nan, index=out.index)
        return pd.to_numeric(out[name], errors="coerce")

    out["q3_script"] = col("q3_rz_touch_share") * col("opp_def_q3_slow_start")
    out["q4_bringback"] = col("q4_trail_target_share") * col("avg_yac_above_expectation")
    out["explosive_align"] = col("air_yards_share") * col("opp_def_explosive_comp_rate")
    out["rush_light_box"] = col("ryoe") * col("opp_def_light_box_rate")
    out["rz_funnel"] = col("inside10_target_share") * col("opp_def_rz_td_rate")
    return out


def _lagged_fd(frame: pd.DataFrame) -> pd.Series:
    def col(name: str) -> pd.Series:
        if name not in frame.columns:
            return pd.Series(0.0, index=frame.index)
        return pd.to_numeric(frame[name], errors="coerce").fillna(0.0)

    formula = (
        col("pass_yds_per_game") * 0.04
        + col("pass_td_per_game") * 4.0
        - col("int_per_game") * 1.0
        + col("rush_yds_per_game") * 0.1
        + col("rush_td_per_game") * 6.0
        + col("receptions_per_game") * 0.5
        + col("rec_yds_per_game") * 0.1
        + col("rec_td_per_game") * 6.0
        - col("fumbles_per_game") * 2.0
    )
    if "fd_points_per_game" not in frame.columns:
        return formula
    hist = pd.to_numeric(frame["fd_points_per_game"], errors="coerce")
    return hist.where(hist.notna() & hist.gt(0), formula)


def _train_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "season" not in frame.columns or "week" not in frame.columns:
        return frame.iloc[0:0].copy()
    train, _test = _time_split(frame)
    return train


def _dst_quantile_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    out["position"] = "DST"
    return out


def _baseline_probability(mean: float, sigma: float, threshold: float, weight: float, model: dict[str, Any] | None) -> float:
    if model and model.get("count_model"):
        if mean is None or not math.isfinite(float(mean)) or float(mean) < 0:
            return float("nan")
        return float(poisson_at_least(max(1, int(threshold)), float(mean)))
    return _one_survival(mean, sigma, threshold, weight)


def _offense_opponent(grains, season: int, week: int, teams: pd.Series) -> pd.Series:
    players = grains.players
    if players.empty or "opp" not in players.columns:
        return pd.Series([""] * len(teams), index=teams.index)
    week_rows = players.loc[
        (pd.to_numeric(players["season"]) == season) & (pd.to_numeric(players["week"]) == week)
    ]
    mapping = (
        week_rows.groupby(week_rows["team"].astype(str))["opp"]
        .agg(lambda values: str(values.dropna().iloc[0]) if values.dropna().size else "")
        .to_dict()
    )
    return teams.astype(str).map(mapping).fillna("")


def _opposing_qb(skill: pd.DataFrame, defense: pd.DataFrame) -> pd.DataFrame:
    empty = pd.DataFrame(columns=["season", "week", "team", "opp_avg_time_to_throw", "opp_int_worthy_rate", "opp_qb_fault_sack_rate", "opp_q4_trail_pass_share"])
    if skill.empty or defense.empty:
        return empty
    qbs = skill.loc[skill.get("position", pd.Series(dtype=str)).astype(str).eq("QB")].copy()
    if qbs.empty:
        return empty
    qbs["pass_att_per_game"] = pd.to_numeric(qbs.get("pass_att_per_game"), errors="coerce").fillna(0.0)
    qbs = qbs.sort_values("pass_att_per_game", kind="mergesort").groupby(["season", "week", "team"], as_index=False).tail(1)
    qbs = qbs.drop(columns=["opp"], errors="ignore")
    qbs = qbs.rename(
        columns={
            "team": "opp",
            "avg_time_to_throw": "opp_avg_time_to_throw",
            "int_worthy_rate": "opp_int_worthy_rate",
            "qb_fault_sack_rate": "opp_qb_fault_sack_rate",
            "team_q4_trail_pass_share": "opp_q4_trail_pass_share",
        }
    )
    keep = ["season", "week", "opp", "opp_avg_time_to_throw", "opp_int_worthy_rate", "opp_qb_fault_sack_rate", "opp_q4_trail_pass_share"]
    for column in keep:
        if column not in qbs.columns:
            qbs[column] = np.nan
    merged = defense[["season", "week", "team", "opp"]].merge(qbs[keep], on=["season", "week", "opp"], how="left")
    return merged.drop(columns=["opp"])


def _calibrate_correlations(skill: pd.DataFrame, defense: pd.DataFrame, *, seed: int, n_boot: int) -> dict[str, Any]:
    if skill.empty:
        return {}
    thresholds = _thresholds(skill)
    pairs = {
        "qb_skill": _qb_skill_pairs(skill, thresholds),
        "qb_bringback": _bringback_pairs(skill, thresholds),
        "rb_dst": _rb_dst_pairs(skill, defense, thresholds),
    }
    estimates = {}
    for kind, frame in pairs.items():
        if frame.empty:
            estimates[kind] = {"kind": kind, "boost": 0.0, "train_delta": 0.0, "ci_low": 0.0, "ci_high": 0.0, "test_improved": False, "n_flag_train": 0, "n_base_train": 0}
            continue
        estimate = estimate_pair_boost(frame, kind=kind, seed=seed, n_boot=n_boot)
        estimates[kind] = {
            "kind": estimate.kind,
            "boost": estimate.boost,
            "train_delta": estimate.train_delta,
            "ci_low": estimate.ci_low,
            "ci_high": estimate.ci_high,
            "test_improved": estimate.test_improved,
            "n_flag_train": estimate.n_flag_train,
            "n_base_train": estimate.n_base_train,
        }
    return estimates


def _thresholds(skill: pd.DataFrame) -> dict[str, float]:
    if skill.empty:
        return {}
    train, _test = _time_split(skill)
    source = train if not train.empty else skill

    def p75(column: str) -> float:
        if column not in source.columns:
            return float("nan")
        values = pd.to_numeric(source[column], errors="coerce").dropna()
        if values.empty:
            return float("nan")
        return float(values.quantile(0.75))

    return {
        "q3_rz_touch_share_p75": p75("q3_rz_touch_share"),
        "q4_trail_target_share_p75": p75("q4_trail_target_share"),
        "def_sack_rate_p75": p75("opp_def_sack_rate"),
    }


def _qb_skill_pairs(skill: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    return _same_game_pairs(
        skill,
        skill["position"].astype(str).eq("QB"),
        skill["position"].astype(str).isin(["WR", "TE"]),
        same_team=True,
        flag=_high(skill, "q3_rz_touch_share", thresholds.get("q3_rz_touch_share_p75", np.nan))
        & pd.to_numeric(skill.get("opp_def_q3_slow_start"), errors="coerce").gt(0),
    )


def _bringback_pairs(skill: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    return _same_game_pairs(
        skill,
        skill["position"].astype(str).eq("QB"),
        skill["position"].astype(str).isin(["WR", "RB"]),
        same_team=False,
        flag=_high(skill, "q4_trail_target_share", thresholds.get("q4_trail_target_share_p75", np.nan))
        & pd.to_numeric(skill.get("avg_yac_above_expectation"), errors="coerce").gt(0),
    )


def _rb_dst_pairs(skill: pd.DataFrame, defense: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    if skill.empty or defense.empty or "fd_points" not in defense.columns:
        return pd.DataFrame(columns=["season", "week", "flag", "points_a", "points_b"])
    rbs = skill.loc[skill["position"].astype(str).eq("RB"), ["season", "week", "team", "opp", "fd_points", "opp_def_sack_rate"]].copy()
    dst = defense[["season", "week", "team", "fd_points"]].rename(columns={"team": "opp", "fd_points": "dst_points"})
    merged = rbs.merge(dst, on=["season", "week", "opp"], how="inner")
    cutoff = thresholds.get("def_sack_rate_p75", np.nan)
    merged["flag"] = pd.to_numeric(merged["opp_def_sack_rate"], errors="coerce").ge(cutoff) if math.isfinite(cutoff) else False
    return merged.rename(columns={"fd_points": "points_a", "dst_points": "points_b"})[
        ["season", "week", "flag", "points_a", "points_b"]
    ]


def _same_game_pairs(skill, left_mask, right_mask, *, same_team: bool, flag: pd.Series) -> pd.DataFrame:
    if skill.empty:
        return pd.DataFrame(columns=["season", "week", "flag", "points_a", "points_b"])
    left = skill.loc[left_mask, ["season", "week", "team", "opp", "player_id", "fd_points"]].copy()
    right = skill.loc[right_mask, ["season", "week", "team", "opp", "player_id", "fd_points"]].copy()
    right = right.join(flag.rename("flag"), how="left")
    if left.empty or right.empty:
        return pd.DataFrame(columns=["season", "week", "flag", "points_a", "points_b"])
    if same_team:
        merged = left.merge(right, on=["season", "week", "team"], suffixes=("_a", "_b"))
    else:
        merged = left.merge(
            right,
            left_on=["season", "week", "opp"],
            right_on=["season", "week", "team"],
            suffixes=("_a", "_b"),
        )
    if merged.empty:
        return pd.DataFrame(columns=["season", "week", "flag", "points_a", "points_b"])
    return pd.DataFrame(
        {
            "season": merged["season"],
            "week": merged["week"],
            "flag": merged["flag"].fillna(False).astype(bool),
            "points_a": merged["fd_points_a"],
            "points_b": merged["fd_points_b"],
        }
    )


def _high(frame: pd.DataFrame, column: str, cutoff: float) -> pd.Series:
    if column not in frame.columns or not math.isfinite(cutoff):
        return pd.Series(False, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").ge(cutoff)


def _apply_logit(baseline: float, features: dict[str, float], model: dict[str, Any]) -> float:
    coefficients = model.get("coefficients") or {}
    if not coefficients:
        return baseline
    score = float(coefficients.get("intercept", 0.0))
    score += float(coefficients.get("baseline", 0.0)) * _logit_scalar(baseline)
    center = model.get("center") or {}
    scale = model.get("scale") or {}
    for feature, beta in coefficients.items():
        if feature in {"intercept", "baseline"}:
            continue
        raw = features.get(feature, center.get(feature, 0.0))
        if raw is None or not math.isfinite(float(raw)):
            raw = center.get(feature, 0.0)
        denom = float(scale.get(feature, 1.0)) or 1.0
        z_score = (float(raw) - float(center.get(feature, 0.0))) / denom
        z_score = min(3.0, max(-3.0, z_score))
        score += float(beta) * z_score
    return float(_sigmoid(np.array([score]))[0])


def _fit_logit(x: np.ndarray, y: np.ndarray, l2: float = 1.0):
    beta = np.zeros(x.shape[1], dtype=float)
    penalty = np.full(x.shape[1], l2)
    penalty[0] = 0.0
    matrix = np.eye(x.shape[1])
    for _ in range(40):
        eta = np.clip(x @ beta, -20.0, 20.0)
        mu = 1.0 / (1.0 + np.exp(-eta))
        weight = np.clip(mu * (1.0 - mu), 1e-4, None)
        response = eta + (y - mu) / weight
        weighted = x.T * weight
        gram = weighted @ x
        gram.flat[:: x.shape[1] + 1] += penalty
        solved = weighted @ response
        try:
            step = np.linalg.solve(gram, solved)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(gram, solved, rcond=None)[0]
        if float(np.max(np.abs(step - beta))) < 1e-6:
            beta = step
            matrix = gram
            break
        beta = step
        matrix = gram
    try:
        covariance = np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        covariance = np.linalg.pinv(matrix)
    se = np.sqrt(np.clip(np.diag(covariance), 0.0, None))
    with np.errstate(divide="ignore", invalid="ignore"):
        zstat = np.where(se > 0, beta / se, 0.0)
    p_values = 2.0 * norm.sf(np.abs(zstat))
    return beta, se, p_values


def _bootstrap(y, points, p_base, p_model, *, seed: int, n_boot: int):
    base = _brier(p_base, y)
    model = _brier(p_model, y)
    delta = base - model
    lift = _point_lift(points, p_base, p_model)
    rng = np.random.default_rng(seed)
    n = len(y)
    deltas = np.empty(n_boot, dtype=float)
    for draw in range(n_boot):
        index = rng.integers(0, n, n)
        deltas[draw] = _brier(p_base[index], y[index]) - _brier(p_model[index], y[index])
    ci_low, ci_high = np.quantile(deltas, [0.025, 0.975])
    positive_share = float(np.mean(deltas > 0.0))
    return float(delta), float(ci_low), float(ci_high), float(lift), positive_share


def _point_lift(points, p_base, p_model) -> float:
    return float(_top_mean(points, p_model) - _top_mean(points, p_base))


def _top_mean(values, scores) -> float:
    k = max(1, int(round(0.10 * len(values))))
    order = np.argsort(-np.asarray(scores, dtype=float), kind="mergesort")
    return float(np.mean(np.asarray(values, dtype=float)[order[:k]]))


def _top_decile(scores, y) -> float:
    return _top_mean(y, scores)


def _brier(probability, y) -> float:
    p = np.clip(np.asarray(probability, dtype=float), 0.0, 1.0)
    target = np.asarray(y, dtype=float)
    return float(np.mean((p - target) ** 2))


def _logloss(probability, y) -> float:
    p = np.clip(np.asarray(probability, dtype=float), 1e-6, 1.0 - 1e-6)
    target = np.asarray(y, dtype=float)
    return float(-np.mean(target * np.log(p) + (1.0 - target) * np.log(1.0 - p)))


def _logit(probability: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(probability, dtype=float), 1e-4, 1.0 - 1e-4)
    return np.log(p / (1.0 - p))


def _logit_scalar(probability: float) -> float:
    p = min(1.0 - 1e-4, max(1e-4, float(probability)))
    return math.log(p / (1.0 - p))


def _sigmoid(eta: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(eta, -20.0, 20.0)))


def _rec_mask(frame: pd.DataFrame) -> pd.Series:
    return frame["position"].astype(str).isin(["WR", "TE", "RB"]) & pd.to_numeric(
        frame.get("targets_per_game"), errors="coerce"
    ).fillna(0.0).gt(0)


def _rush_mask(frame: pd.DataFrame) -> pd.Series:
    return frame["position"].astype(str).isin(["RB", "QB"]) & pd.to_numeric(
        frame.get("carries_per_game"), errors="coerce"
    ).fillna(0.0).gt(0)


def _pass_mask(frame: pd.DataFrame) -> pd.Series:
    return frame["position"].astype(str).eq("QB") & pd.to_numeric(
        frame.get("pass_att_per_game"), errors="coerce"
    ).fillna(0.0).gt(0)


def _skill_mask(frame: pd.DataFrame) -> pd.Series:
    return frame["position"].astype(str).isin(["QB", "RB", "WR", "TE"])


def _dst_mask(frame: pd.DataFrame) -> pd.Series:
    return pd.Series(True, index=frame.index)


def _empty_target(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "export": False,
        "alpha": 1.0,
        "kept": [],
        "coefficients": {},
        "center": {},
        "scale": {},
        "sigma": {},
        "mixture_weight": 1.0,
        "threshold": None,
        "mean_column": None,
        "count_model": False,
        "metrics": {
            "n_train": 0,
            "n_test": 0,
            "baseline_brier": float("nan"),
            "model_brier": float("nan"),
            "baseline_logloss": float("nan"),
            "model_logloss": float("nan"),
            "baseline_top_decile": float("nan"),
            "model_top_decile": float("nan"),
            "delta_brier": float("nan"),
            "delta_brier_ci_low": float("nan"),
            "delta_brier_ci_high": float("nan"),
            "top_decile_point_lift": float("nan"),
        },
        "fdr": [],
        "candidate_kept": [],
    }
