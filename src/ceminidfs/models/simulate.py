from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ceminidfs.models.coherence_risk import coherence_variance_multiplier
from ceminidfs.models.coherence_settings import CoherenceRiskSettings
from ceminidfs.models.correlation import build_correlation_matrix

try:  # pragma: no cover - exercised only when scipy is installed.
    from scipy.special import ndtr as _scipy_ndtr
    from scipy.special import ndtri as _scipy_ndtri
except ImportError:  # pragma: no cover - default lightweight dependency path.
    _scipy_ndtr = None
    _scipy_ndtri = None


POSITION_CV = {
    "QB": 0.35,
    "RB": 0.45,
    "WR": 0.50,
    "TE": 0.45,
    "DEF": 0.40,
    "DST": 0.40,
    "D": 0.40,
}
TEAM_CORRELATION = 0.35
DEFAULT_POSITION_CV = 0.45

REQUIRED_COLUMNS = ("player_id", "fd_projection", "team", "position")


def simulate_fd_points(
    df: pd.DataFrame,
    n_iterations: int = 5000,
    seed: int | None = None,
    method: str = "team_shock",
    site: str = "fanduel",
    config: Mapping[str, Any] | None = None,
) -> np.ndarray:
    """Return simulated FanDuel points with shape (n_players, n_iterations)."""

    _validate_inputs(df, n_iterations)
    normalized_method = _normalize_method(method)
    if normalized_method == "copula":
        return simulate_fd_points_copula(
            df,
            n_iterations=n_iterations,
            seed=seed,
            site=site,
            config=config,
        )
    if df.empty:
        return np.empty((0, n_iterations), dtype=float)

    rng = np.random.default_rng(seed)
    projections = pd.to_numeric(df["fd_projection"], errors="coerce").fillna(0.0).clip(lower=0.0)
    medians = projections.to_numpy(dtype=float)

    cv = df.apply(lambda row: position_cv_for_row(row, config=config), axis=1).to_numpy(dtype=float)
    sigma = np.sqrt(np.log1p(cv * cv))
    team_beta = sigma * TEAM_CORRELATION
    idio_beta = sigma * np.sqrt(1.0 - (TEAM_CORRELATION * TEAM_CORRELATION))

    teams = df["team"].fillna("").astype(str).to_numpy()
    unique_teams, team_codes = np.unique(teams, return_inverse=True)
    team_shocks = rng.standard_normal((len(unique_teams), n_iterations))
    idio_shocks = rng.standard_normal((len(df), n_iterations))

    log_multiplier = (team_beta[:, None] * team_shocks[team_codes]) + (
        idio_beta[:, None] * idio_shocks
    )
    return np.maximum(0.0, medians[:, None] * np.exp(log_multiplier))


def simulate_fd_points_copula(
    df: pd.DataFrame,
    n_iterations: int = 5000,
    seed: int | None = None,
    site: str = "fanduel",
    config: Mapping[str, Any] | None = None,
) -> np.ndarray:
    """Return FanDuel point simulations from a Gaussian copula with lognormal marginals."""

    _validate_inputs(df, n_iterations)
    if df.empty:
        return np.empty((0, n_iterations), dtype=float)

    rng = np.random.default_rng(seed)
    projections = pd.to_numeric(df["fd_projection"], errors="coerce").fillna(0.0).clip(lower=0.0)
    medians = projections.to_numpy(dtype=float)

    cv = df.apply(lambda row: position_cv_for_row(row, config=config), axis=1).to_numpy(dtype=float)
    sigma = np.sqrt(np.log1p(cv * cv))

    correlation = build_correlation_matrix(df, site=site)
    cholesky = _cholesky_with_jitter(correlation)
    independent_normals = rng.standard_normal((len(df), n_iterations))
    correlated_normals = np.dot(cholesky, independent_normals)

    uniforms = np.clip(_normal_cdf(correlated_normals), 1e-12, 1.0 - 1e-12)
    marginal_normals = _normal_ppf(uniforms)
    log_multiplier = sigma[:, None] * marginal_normals
    return np.maximum(0.0, medians[:, None] * np.exp(log_multiplier))


def simulation_summary(
    sim_matrix: np.ndarray,
    player_ids: Iterable[Any],
    quantiles: tuple[float, float, float] = (0.2, 0.5, 0.9),
) -> pd.DataFrame:
    """Summarize each player's simulated floor, median, and ceiling."""

    matrix = np.asarray(sim_matrix, dtype=float)
    ids = list(player_ids)
    if matrix.ndim != 2:
        raise ValueError("sim_matrix must be a 2D array")
    if len(ids) != matrix.shape[0]:
        raise ValueError("player_ids length must match sim_matrix rows")
    if len(quantiles) != 3:
        raise ValueError("quantiles must contain floor, median, and ceiling values")

    floor, median, ceiling = np.quantile(matrix, quantiles, axis=1)
    return pd.DataFrame(
        {
            "player_id": ids,
            "floor": floor,
            "median": median,
            "ceiling": ceiling,
        }
    )


def add_simulation_columns(
    df: pd.DataFrame,
    n_iterations: int = 5000,
    seed: int | None = None,
    method: str = "team_shock",
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Attach floor and ceiling projection columns to a copy of a projection frame."""

    simulation_method = _method_from_config(config, method)
    sim_matrix = simulate_fd_points(
        df,
        n_iterations=n_iterations,
        seed=seed,
        method=simulation_method,
        config=config,
    )
    summary = simulation_summary(sim_matrix, df["player_id"])

    output = df.copy()
    output["Projection Floor"] = summary["floor"].to_numpy()
    output["sim_median"] = summary["median"].to_numpy()
    output["Projection Ceil"] = summary["ceiling"].to_numpy()
    return output


def _validate_inputs(df: pd.DataFrame, n_iterations: int) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"simulate_fd_points requires columns: {', '.join(missing)}")
    if n_iterations <= 0:
        raise ValueError("n_iterations must be positive")


def position_cv_for_row(row: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> float:
    position = _normalize_position(row.get("position", ""))
    base_cv = float(POSITION_CV.get(position, DEFAULT_POSITION_CV))
    settings = CoherenceRiskSettings.from_config(config)
    return base_cv * coherence_variance_multiplier(row, settings)


def _method_from_config(config: Mapping[str, Any] | None, fallback: str) -> str:
    if not config:
        return fallback
    simulate_cfg = config.get("simulate", {})
    if isinstance(simulate_cfg, Mapping):
        return str(simulate_cfg.get("method", fallback))
    return fallback


def _normalize_method(method: str) -> str:
    normalized = str(method or "team_shock").strip().lower()
    if normalized not in {"team_shock", "copula"}:
        raise ValueError("method must be one of: team_shock, copula")
    return normalized


def _normalize_position(value: Any) -> str:
    position = str(value or "").strip().upper()
    if position == "DST":
        return "DEF"
    return position


def _cholesky_with_jitter(correlation: np.ndarray, *, max_jitter: float = 1e-6) -> np.ndarray:
    identity = np.eye(correlation.shape[0])
    jitter = 0.0
    for _ in range(6):
        try:
            return np.linalg.cholesky(correlation + (identity * jitter))
        except np.linalg.LinAlgError:
            jitter = 1e-8 if jitter == 0.0 else min(jitter * 10.0, max_jitter)
    raise np.linalg.LinAlgError(
        f"correlation matrix is not positive definite even with jitter={max_jitter}"
    )


def _normal_cdf(values: np.ndarray) -> np.ndarray:
    if _scipy_ndtr is not None:
        return _scipy_ndtr(values)
    erf = np.vectorize(math.erf)
    return 0.5 * (1.0 + erf(values / math.sqrt(2.0)))


def _normal_ppf(probabilities: np.ndarray) -> np.ndarray:
    if _scipy_ndtri is not None:
        return _scipy_ndtri(probabilities)
    return _normal_ppf_acklam(probabilities)


def _normal_ppf_acklam(probabilities: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1.0 - 1e-12)
    output = np.empty_like(p)

    a = np.array(
        [
            -3.969683028665376e01,
            2.209460984245205e02,
            -2.759285104469687e02,
            1.383577518672690e02,
            -3.066479806614716e01,
            2.506628277459239e00,
        ]
    )
    b = np.array(
        [
            -5.447609879822406e01,
            1.615858368580409e02,
            -1.556989798598866e02,
            6.680131188771972e01,
            -1.328068155288572e01,
        ]
    )
    c = np.array(
        [
            -7.784894002430293e-03,
            -3.223964580411365e-01,
            -2.400758277161838e00,
            -2.549732539343734e00,
            4.374664141464968e00,
            2.938163982698783e00,
        ]
    )
    d = np.array(
        [
            7.784695709041462e-03,
            3.224671290700398e-01,
            2.445134137142996e00,
            3.754408661907416e00,
        ]
    )

    lower_bound = 0.02425
    upper_bound = 1.0 - lower_bound
    lower = p < lower_bound
    upper = p > upper_bound
    central = ~(lower | upper)

    q = np.sqrt(-2.0 * np.log(p[lower]))
    output[lower] = _polyval(c, q) / _polyval(np.append(d, 1.0), q)

    q = np.sqrt(-2.0 * np.log1p(-p[upper]))
    output[upper] = -_polyval(c, q) / _polyval(np.append(d, 1.0), q)

    q = p[central] - 0.5
    r = q * q
    output[central] = (_polyval(a, r) * q) / _polyval(np.append(b, 1.0), r)
    return output


def _polyval(coefficients: np.ndarray, values: np.ndarray) -> np.ndarray:
    result = np.zeros_like(values, dtype=float)
    for coefficient in coefficients:
        result = (result * values) + coefficient
    return result
