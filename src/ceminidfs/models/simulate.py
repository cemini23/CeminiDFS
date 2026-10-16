from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
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
    seed = _seed_from_config(config, seed)
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
    seed = _seed_from_config(config, seed)
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


# --------------------------------------------------------------------------- #
# Injury / role regime Gaussian mixture (Integration A).
#
# A unimodal lognormal draw misses the bimodal decoy and re-aggravation tails.
# The mixture keeps the same central mass but moves weight into a low decoy mode
# and a truncated early-exit mode. Weights come from the Jev regime router.
# --------------------------------------------------------------------------- #
GMM_COMPONENT_NAMES = ("full_role", "snap_count_decoy", "in_game_reaggravation_exit")
GMM_FULL_ROLE_SCALE = 1.15
GMM_DECOY_LOC = 0.55
GMM_DECOY_SCALE = 0.75
GMM_EXIT_LOC = 0.22
GMM_EXIT_SCALE = 0.45
# (p85 - p15) of a standard normal is 2 * 1.0364. sigma_eff divides it back out.
SIGMA_EFF_DENOMINATOR = 2.073
_TRUNCATION_EPSILON = 1.0e-9
# Candidate shared scale factors for the median re-centering. Every component
# location is at or below ``mu`` before correction, so the mixture median sits
# at or below ``mu`` and the required ``f`` is ``>= 1``. The upper bound covers a
# certain exit-regime mixture (``1 / GMM_EXIT_LOC`` ~ 4.5) with headroom.
RECENTER_FACTOR_GRID = np.geomspace(1.0, 12.0, 512)


def simulate_fd_points_gmm(
    df: pd.DataFrame,
    regime_weights: Mapping[Any, Sequence[float]],
    n_iterations: int = 10000,
    seed: int | None = None,
    site: str = "fanduel",
    config: Mapping[str, Any] | None = None,
    *,
    dispersion_scale: float = 1.0,
) -> np.ndarray:
    """Return FanDuel points from a conditional 3-component Gaussian mixture.

    ``regime_weights`` maps a player id (or name) to three active weights
    ``(w_full_role, w_decoy, w_exit)`` that sum to one. A player with no entry
    falls back to the healthy prior mixture. ``sigma`` is the position relative
    dispersion times the projection, in FanDuel points. ``dispersion_scale``
    multiplies ``sigma`` and is the single variance-calibration knob the
    walk-forward coverage fit sets.

    The mixture is re-centred on its **median** before sampling: every component
    location is multiplied by a per-player ``f_i`` so ``P(draw > mu_i)`` lands on
    ``0.5``. See :func:`median_recenter_factors`.
    """

    _validate_inputs(df, n_iterations)
    seed = _seed_from_config(config, seed)
    if df.empty:
        return np.empty((0, n_iterations), dtype=float)

    rng = np.random.default_rng(seed)
    medians, sigmas, weights = _gmm_inputs(df, regime_weights, dispersion_scale, config)
    factors = median_recenter_factors(medians, sigmas, weights)
    return sample_regime_gmm(
        medians * factors, sigmas, weights, n_iterations=n_iterations, rng=rng
    )


def gmm_recenter_factors(
    df: pd.DataFrame,
    regime_weights: Mapping[Any, Sequence[float]],
    *,
    dispersion_scale: float = 1.0,
    config: Mapping[str, Any] | None = None,
) -> np.ndarray:
    """Return the per-player median re-centering factors for ``df``.

    Mirrors the mixture inputs :func:`simulate_fd_points_gmm` samples, so a
    caller can report ``mean``/``spread`` of ``f_i`` without resampling.
    """

    medians, sigmas, weights = _gmm_inputs(df, regime_weights, dispersion_scale, config)
    return median_recenter_factors(medians, sigmas, weights)


def _gmm_inputs(
    df: pd.DataFrame,
    regime_weights: Mapping[Any, Sequence[float]],
    dispersion_scale: float,
    config: Mapping[str, Any] | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(medians, sigmas, weights)`` for the conditional mixture."""

    projections = pd.to_numeric(df["fd_projection"], errors="coerce").fillna(0.0).clip(lower=0.0)
    medians = projections.to_numpy(dtype=float)
    cv = df.apply(lambda row: position_cv_for_row(row, config=config), axis=1).to_numpy(dtype=float)
    sigmas = np.maximum(cv * medians, 0.0) * max(0.0, float(dispersion_scale))
    weights = _regime_weight_matrix(df, regime_weights)
    return medians, sigmas, weights


def median_recenter_factors(
    medians: np.ndarray,
    sigmas: np.ndarray,
    weights: np.ndarray,
    *,
    factor_grid: np.ndarray | None = None,
) -> np.ndarray:
    """Return per-player scale factors ``f_i`` so the mixture median equals ``mu_i``.

    The component locations are ``f*mu``, ``f*0.55*mu`` and ``f*0.22*mu``, so a
    single shared ``f`` keeps the ratios ``1.0 / 0.55 / 0.22`` while the spreads
    (``1.15``, ``0.75``, ``0.45`` times ``sigma``) are untouched. Because every
    location is at or below ``mu`` before correction, the mixture CDF at ``mu``
    is ``>= 0.5`` and decreases monotonically in ``f``; the factor is where it
    crosses ``0.5``. It is found on a log grid and linearly interpolated.

    Degenerate players (``mu <= 0`` or ``sigma <= 0``) keep ``f = 1``.
    """

    mu = np.asarray(medians, dtype=float).reshape(-1)
    sg = np.asarray(sigmas, dtype=float).reshape(-1)
    weight_matrix = _normalize_weight_matrix(np.asarray(weights, dtype=float))
    n_players = mu.shape[0]
    if sg.shape[0] != n_players or weight_matrix.shape[0] != n_players:
        raise ValueError("medians, sigmas, and weights must share a length")

    grid = RECENTER_FACTOR_GRID if factor_grid is None else np.asarray(factor_grid, dtype=float)
    factors = np.ones(n_players, dtype=float)
    active = (mu > _TRUNCATION_EPSILON) & (sg > _TRUNCATION_EPSILON)
    if not np.any(active):
        return factors

    mu_a = mu[active].reshape(-1, 1)
    sg_a = sg[active].reshape(-1, 1)
    w_a = weight_matrix[active]
    f = grid.reshape(1, -1)

    loc0 = f * mu_a
    loc1 = GMM_DECOY_LOC * f * mu_a
    loc2 = GMM_EXIT_LOC * f * mu_a
    scale0 = GMM_FULL_ROLE_SCALE * sg_a
    scale1 = GMM_DECOY_SCALE * sg_a
    scale2 = GMM_EXIT_SCALE * sg_a

    cdf0 = _normal_cdf((mu_a - loc0) / scale0)
    cdf1 = _normal_cdf((mu_a - loc1) / scale1)
    lower_exit = _normal_cdf((0.0 - loc2) / scale2)
    cdf2 = (_normal_cdf((mu_a - loc2) / scale2) - lower_exit) / (1.0 - lower_exit)
    cdf = (w_a[:, 0:1] * cdf0) + (w_a[:, 1:2] * cdf1) + (w_a[:, 2:3] * cdf2)

    below = cdf <= 0.5
    rows = np.arange(mu_a.shape[0])
    first_below = np.argmax(below, axis=1)
    # Players whose CDF never drops to 0.5 on the grid pin to the top of it;
    # with sigma > 0 the crossing always exists inside the grid.
    no_cross = ~below.any(axis=1)
    upper_index = np.where(no_cross, grid.shape[0] - 1, first_below)
    lower_index = np.maximum(upper_index - 1, 0)

    cdf_upper = cdf[rows, lower_index]
    cdf_lower = cdf[rows, upper_index]
    denominator = cdf_upper - cdf_lower
    safe = np.abs(denominator) > 1e-12
    fraction = np.divide(
        cdf_upper - 0.5,
        denominator,
        out=np.zeros_like(denominator),
        where=safe,
    )
    fraction = np.clip(fraction, 0.0, 1.0)
    interpolated = grid[lower_index] + fraction * (grid[upper_index] - grid[lower_index])
    interpolated = np.where(upper_index == 0, grid[0], interpolated)
    factors[active] = interpolated
    return factors


def sample_regime_gmm(
    medians: np.ndarray,
    sigmas: np.ndarray,
    weights: np.ndarray,
    *,
    n_iterations: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample ``n_players`` rows of ``n_iterations`` draws from the mixture.

    Component 1 is ``N(mu, (1.15 sigma)^2)``. Component 2 is
    ``N(0.55 mu, (0.75 sigma)^2)``. Component 3 is
    ``TruncatedNormal(0.22 mu, (0.45 sigma)^2, low=0)``. Draws are floored at 0.

    This is the raw component geometry. Callers that need the mixture centred on
    its median (see :func:`median_recenter_factors`) pass ``medians`` already
    scaled by that shared factor.
    """

    medians = np.asarray(medians, dtype=float).reshape(-1, 1)
    sigmas = np.asarray(sigmas, dtype=float).reshape(-1, 1)
    weights = _normalize_weight_matrix(np.asarray(weights, dtype=float))
    n_players = medians.shape[0]
    if n_iterations <= 0:
        raise ValueError("n_iterations must be positive")

    uniforms = rng.random((n_players, n_iterations))
    cumulative = np.cumsum(weights, axis=1)
    component = (uniforms[:, :, None] > cumulative[:, None, :]).sum(axis=2)

    standard = rng.standard_normal((n_players, n_iterations))
    full_role = medians + (GMM_FULL_ROLE_SCALE * sigmas * standard)
    decoy = (GMM_DECOY_LOC * medians) + (GMM_DECOY_SCALE * sigmas * standard)
    exit_draws = _truncated_normal_lower(
        loc=GMM_EXIT_LOC * medians,
        scale=GMM_EXIT_SCALE * sigmas,
        low=0.0,
        uniforms=rng.random((n_players, n_iterations)),
    )

    draws = np.where(component == 0, full_role, np.where(component == 1, decoy, exit_draws))
    return np.maximum(0.0, draws)


def gmm_summary(
    draws: np.ndarray,
    player_ids: Iterable[Any],
) -> pd.DataFrame:
    """Return empirical percentile bands and ``sigma_eff`` per player.

    ``p15``, ``p50_median``, ``p85``, and ``p95_ceiling`` come straight from the
    draws. ``sigma_eff = (p85 - p15) / 2.073`` is the effective standard
    deviation implied by the central band.
    """

    matrix = np.asarray(draws, dtype=float)
    ids = list(player_ids)
    if matrix.ndim != 2:
        raise ValueError("draws must be a 2D array")
    if len(ids) != matrix.shape[0]:
        raise ValueError("player_ids length must match draws rows")

    p15, median, p85, p95 = np.quantile(matrix, (0.15, 0.5, 0.85, 0.95), axis=1)
    sigma_eff = (p85 - p15) / SIGMA_EFF_DENOMINATOR
    return pd.DataFrame(
        {
            "player_id": ids,
            "p15": p15,
            "p50_median": median,
            "p85": p85,
            "p95_ceiling": p95,
            "sigma_eff": sigma_eff,
        }
    )


def _regime_weight_matrix(
    df: pd.DataFrame, regime_weights: Mapping[Any, Sequence[float]] | None
) -> np.ndarray:
    n_players = len(df)
    if not regime_weights:
        return _normalize_weight_matrix(np.tile(_healthy_weights(), (n_players, 1)))

    from ceminidfs.models.regime_gmm import HEALTHY_PRIOR

    healthy = np.array(
        [
            HEALTHY_PRIOR["full_role"],
            HEALTHY_PRIOR["snap_count_decoy"],
            HEALTHY_PRIOR["in_game_reaggravation_exit"],
        ],
        dtype=float,
    )
    lookup = dict(regime_weights)
    if "player_id" in df.columns:
        ids = df["player_id"].fillna("").astype(str).to_numpy()
    else:
        ids = np.array([""] * n_players)
    names = df.get("player_name", pd.Series("", index=df.index)).fillna("").astype(str).to_numpy()

    rows = np.empty((n_players, len(GMM_COMPONENT_NAMES)), dtype=float)
    for index in range(n_players):
        weights = lookup.get(ids[index]) or lookup.get(names[index])
        if weights is None:
            rows[index] = healthy
        else:
            rows[index] = np.asarray(list(weights)[: len(GMM_COMPONENT_NAMES)], dtype=float)
    return _normalize_weight_matrix(rows)


def _healthy_weights() -> list[float]:
    from ceminidfs.models.regime_gmm import HEALTHY_PRIOR

    return [
        HEALTHY_PRIOR["full_role"],
        HEALTHY_PRIOR["snap_count_decoy"],
        HEALTHY_PRIOR["in_game_reaggravation_exit"],
    ]


def _normalize_weight_matrix(weights: np.ndarray) -> np.ndarray:
    matrix = np.asarray(weights, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != len(GMM_COMPONENT_NAMES):
        raise ValueError("weights must be a 2D array with three columns")
    matrix = np.clip(matrix, 0.0, None)
    totals = matrix.sum(axis=1, keepdims=True)
    safe = np.where(totals > 0.0, totals, 1.0)
    return matrix / safe


def _truncated_normal_lower(
    *,
    loc: np.ndarray,
    scale: np.ndarray,
    low: float,
    uniforms: np.ndarray,
) -> np.ndarray:
    """Inverse-CDF draw of ``N(loc, scale^2)`` truncated to ``[low, inf)``."""

    loc = np.asarray(loc, dtype=float)
    scale = np.asarray(scale, dtype=float)
    uniforms = np.asarray(uniforms, dtype=float)
    result = np.maximum(loc, low)
    positive = scale > 0.0
    if not np.any(positive):
        return result

    alpha = np.divide(
        low - loc, scale, out=np.full_like(loc, -np.inf), where=positive
    )
    phi_alpha = _normal_cdf(alpha)
    upper = np.clip(phi_alpha + (uniforms * (1.0 - phi_alpha)), _TRUNCATION_EPSILON, 1.0 - _TRUNCATION_EPSILON)
    quantile = _normal_ppf(upper)
    truncated = loc + (scale * quantile)
    return np.where(positive, truncated, result)


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
    p15, p85 = np.quantile(matrix, (0.15, 0.85), axis=1)
    return pd.DataFrame(
        {
            "player_id": ids,
            "floor": floor,
            "median": median,
            "ceiling": ceiling,
            "p15": p15,
            "p85": p85,
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
    output["p15"] = summary["p15"].to_numpy()
    output["p85"] = summary["p85"].to_numpy()
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


def _seed_from_config(config: Mapping[str, Any] | None, seed: int | None) -> int | None:
    if seed is not None:
        return int(seed)
    if not config:
        return None
    simulate_cfg = config.get("simulate", {})
    if isinstance(simulate_cfg, Mapping) and simulate_cfg.get("seed") is not None:
        return int(simulate_cfg["seed"])
    if config.get("simulation_seed") is not None:
        return int(config["simulation_seed"])
    return None


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
