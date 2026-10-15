"""Next Gen Stats elasticity and Jev coverage-alignment routing (Integration B).

The matchup adjustment is split in two. Python fits a shrinkage-regularized
Ridge multiplier on empirical rolling NGS z-scores and bounds it to
``[-0.12, +0.12]``. Jev routes the receiver into one of three qualitative
alignment states. Python then combines them:

    mu_adj = mu_base * (1.0 + delta_ngs * (1.00 * u1 + 0.50 * u2 + 0.15 * u3))

No NGS frame is required. When the frame is absent the multiplier is neutral
(``delta_ngs == 0``) and only the Jev alignment factor moves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from ceminidfs.jev_client import ALIGNMENT_PRIOR, ChoiceResult, TieredJevClient

ALIGNMENT_ORDER = (
    "heavy_shadow_65pct_plus",
    "base_side_alignment_35_to_65pct",
    "schemed_avoidance_slot_motion_sub_35pct",
)
ALIGNMENT_INTERACTION = {
    "heavy_shadow_65pct_plus": 1.00,
    "base_side_alignment_35_to_65pct": 0.50,
    "schemed_avoidance_slot_motion_sub_35pct": 0.15,
}

ALIGNMENT_QUESTION = (
    "Given the receiver alignment profile and the opponent cornerback room, "
    "which coverage interaction state is most likely this week?"
)

ROLLING_WINDOW = 6
DELTA_BOUND = 0.12
RIDGE_ALPHA = 1.0
DEFAULT_STRICT_POSITIONS = ("WR", "TE", "RB")

PLAYER_FEATURES = ("avg_separation", "avg_cushion", "percent_share_of_intended_air_yards")
DEFENSE_FEATURES = (
    "completion_percentage_above_expectation_allowed",
    "yards_per_attempt_allowed",
)
ALL_FEATURES = PLAYER_FEATURES + DEFENSE_FEATURES

_CACHE_DIR = Path("artifacts/cache")


def rolling_zscore(series: pd.Series, window: int = ROLLING_WINDOW) -> pd.Series:
    """Return a trailing-window z-score with ``min_periods=1``."""

    values = pd.to_numeric(series, errors="coerce")
    mean = values.rolling(window, min_periods=1).mean()
    std = values.rolling(window, min_periods=1).std(ddof=0)
    zscore = (values - mean) / std.replace(0.0, np.nan)
    return zscore.fillna(0.0)


def build_ngs_features(
    receiving: pd.DataFrame,
    defenses: pd.DataFrame | None = None,
    *,
    window: int = ROLLING_WINDOW,
) -> pd.DataFrame:
    """Return one z-scored feature row per ``(player_id, week)``.

    ``receiving`` holds player-side NGS columns. ``defenses`` holds opponent
    defense aggregates keyed by ``opponent``. Missing columns become zeros so the
    Ridge fit still runs.
    """

    frame = receiving.copy()
    for column in ("avg_separation", "avg_cushion", "percent_share_of_intended_air_yards"):
        if column not in frame.columns:
            frame[column] = 0.0

    group_key = "player_id" if "player_id" in frame.columns else "player_name"
    sort_keys = [key for key in (group_key, "week") if key in frame.columns]
    if sort_keys:
        frame = frame.sort_values(sort_keys)

    out = pd.DataFrame(index=frame.index)
    out["player_id"] = frame.get(group_key, "")
    for column in PLAYER_FEATURES:
        grouped = frame.groupby(group_key, sort=False)[column].transform(
            lambda values: rolling_zscore(values, window=window)
        )
        out[f"z_{column}"] = grouped.to_numpy()

    for column in DEFENSE_FEATURES:
        out[f"z_{column}"] = 0.0
    if defenses is not None and not defenses.empty and "opponent" in frame.columns:
        defense_lookup = _defense_lookup(defenses)
        out["z_" + DEFENSE_FEATURES[0]] = frame["opponent"].map(
            lambda opponent: defense_lookup.get(str(opponent).upper(), {}).get(f"z_{DEFENSE_FEATURES[0]}", 0.0)
        )
        out["z_" + DEFENSE_FEATURES[1]] = frame["opponent"].map(
            lambda opponent: defense_lookup.get(str(opponent).upper(), {}).get(f"z_{DEFENSE_FEATURES[1]}", 0.0)
        )
    return out.reset_index(drop=True)


def _defense_lookup(defenses: pd.DataFrame) -> dict[str, dict[str, float]]:
    lookup: dict[str, dict[str, float]] = {}
    for row in defenses.to_dict("records"):
        opponent = str(row.get("opponent") or row.get("team") or "").upper()
        if not opponent:
            continue
        lookup[opponent] = {
            f"z_{DEFENSE_FEATURES[0]}": float(row.get(DEFENSE_FEATURES[0], 0.0) or 0.0),
            f"z_{DEFENSE_FEATURES[1]}": float(row.get(DEFENSE_FEATURES[1], 0.0) or 0.0),
        }
    return lookup


@dataclass
class NgsElasticityModel:
    """A bounded Ridge multiplier over standardized NGS z-scores."""

    coefficients: list[float]
    feature_means: list[float]
    feature_scales: list[float]
    target_mean: float
    target_scale: float
    features: tuple[str, ...] = ALL_FEATURES
    alpha: float = RIDGE_ALPHA
    bound: float = DELTA_BOUND
    sample_size: int = 0
    neutral: bool = False

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Return the bounded ``delta_ngs`` multiplier per row."""

        if self.neutral or not len(features):
            return np.zeros(len(features), dtype=float)
        matrix = _feature_matrix(features, self.features, self.feature_means, self.feature_scales)
        centered = matrix @ np.asarray(self.coefficients, dtype=float)
        deltas = self.target_mean + (self.target_scale * centered)
        return np.clip(deltas, -self.bound, self.bound)

    def to_dict(self) -> dict[str, Any]:
        return {
            "coefficients": list(self.coefficients),
            "features": list(self.features),
            "alpha": self.alpha,
            "bound": self.bound,
            "sample_size": self.sample_size,
            "neutral": self.neutral,
        }


def fit_ngs_elasticity(
    features: pd.DataFrame,
    target_yprr: Sequence[float],
    *,
    alpha: float = RIDGE_ALPHA,
    bound: float = DELTA_BOUND,
    feature_names: Sequence[str] = ALL_FEATURES,
) -> NgsElasticityModel:
    """Fit a shrinkage-regularized Ridge multiplier on receiving YPRR.

    The target is the fractional deviation of YPRR from its sample mean. The
    prediction is clipped to ``[-bound, +bound]``. Fewer than three usable rows,
    or a degenerate feature matrix, returns the neutral model.
    """

    y = pd.to_numeric(pd.Series(list(target_yprr)), errors="coerce").to_numpy(dtype=float)
    if features is None or features.empty or len(y) != len(features) or len(y) < 3:
        return neutral_ngs_model(feature_names)
    if not np.all(np.isfinite(y)):
        mask = np.isfinite(y)
        features = features.loc[mask].reset_index(drop=True)
        y = y[mask]
        if len(y) < 3:
            return neutral_ngs_model(feature_names)

    coarse = pd.DataFrame({name: _series(features, name) for name in feature_names})
    means = coarse.mean().to_numpy(dtype=float)
    scales = coarse.std(ddof=0).replace(0.0, 1.0).to_numpy(dtype=float)
    x = _feature_matrix(coarse, tuple(feature_names), list(means), list(scales))
    y_mean = float(np.mean(y))
    y_scale = float(np.std(y)) or 1.0
    y_centered = (y - y_mean) / y_scale

    gram = x.T @ x
    ridge = gram + (alpha * np.eye(gram.shape[0]))
    try:
        coefficients = np.linalg.solve(ridge, x.T @ y_centered)
    except np.linalg.LinAlgError:
        return neutral_ngs_model(feature_names)

    return NgsElasticityModel(
        coefficients=[float(value) for value in coefficients],
        feature_means=[float(value) for value in means],
        feature_scales=[float(value) for value in scales],
        target_mean=y_mean,
        target_scale=y_scale,
        features=tuple(feature_names),
        alpha=float(alpha),
        bound=float(bound),
        sample_size=int(len(y)),
    )


def neutral_ngs_model(feature_names: Sequence[str] = ALL_FEATURES) -> NgsElasticityModel:
    return NgsElasticityModel(
        coefficients=[0.0] * len(feature_names),
        feature_means=[0.0] * len(feature_names),
        feature_scales=[1.0] * len(feature_names),
        target_mean=0.0,
        target_scale=1.0,
        features=tuple(feature_names),
        sample_size=0,
        neutral=True,
    )


@dataclass
class AlignmentRouting:
    player_id: str
    weights: dict[str, float]
    interaction: float
    top_state: str
    confidence: float
    provider_used: str
    state: dict[str, Any] = field(default_factory=dict)


def route_alignment(
    client: TieredJevClient | None,
    profiles: Sequence[Mapping[str, Any]],
    *,
    id_key: str = "player_id",
) -> dict[str, AlignmentRouting]:
    """Route each receiver across the three alignment states."""

    routings: dict[str, AlignmentRouting] = {}
    for profile in profiles:
        player_id = str(profile.get(id_key) or profile.get("player_name") or "").strip()
        if not player_id:
            continue
        state = build_alignment_state(profile)
        if client is None:
            routings[player_id] = _alignment_routing(player_id, dict(ALIGNMENT_PRIOR), "prior", 0.55, state)
            continue
        result: ChoiceResult = client.jev_choice(state, ALIGNMENT_QUESTION, list(ALIGNMENT_ORDER))
        routings[player_id] = _alignment_routing(
            player_id, dict(result.probabilities), result.provider_used, result.confidence, state,
            top_state=result.top_choice,
        )
    return routings


def build_alignment_state(profile: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "position": str(profile.get("position") or "").upper(),
        "slot_rate": _number(profile.get("slot_rate")),
        "wide_left_rate": _number(profile.get("wide_left_rate")),
        "wide_right_rate": _number(profile.get("wide_right_rate")),
        "aDOT": _number(profile.get("aDOT")),
        "cb1_shadow_history": str(profile.get("cb1_shadow_history") or "")[:120],
        "coordinator_shell_notes": str(profile.get("coordinator_shell_notes") or "")[:120],
    }


def combine_receiving_adjustment(
    mu_base: float,
    delta_ngs: float,
    routing: AlignmentRouting | Mapping[str, float],
) -> float:
    """Apply ``mu_adj = mu_base * (1 + delta_ngs * interaction)``."""

    interaction = alignment_interaction(routing)
    return float(mu_base) * (1.0 + float(delta_ngs) * interaction)


def alignment_interaction(routing: AlignmentRouting | Mapping[str, float]) -> float:
    weights = routing.weights if isinstance(routing, AlignmentRouting) else routing
    return sum(
        float(weights.get(state, 0.0)) * factor for state, factor in ALIGNMENT_INTERACTION.items()
    )


def load_ngs_frames(season: int, cache_dir: str | Path | None = None) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Load NGS receiving and passing frames from the cache, or return ``(None, None)``."""

    root = Path(cache_dir) if cache_dir is not None else _CACHE_DIR
    receiving = _read_parquet(root / f"ngs_receiving_{season}.parquet")
    passing = _read_parquet(root / f"ngs_passing_{season}.parquet")
    return receiving, passing


def _read_parquet(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    try:
        return pd.read_parquet(path)
    except (OSError, ValueError):  # pragma: no cover - corrupt cache is a miss.
        return None


def _alignment_routing(
    player_id: str,
    weights: Mapping[str, float],
    provider_used: str,
    confidence: float,
    state: Mapping[str, Any],
    *,
    top_state: str | None = None,
) -> AlignmentRouting:
    normalized = {state_name: float(weights.get(state_name, 0.0)) for state_name in ALIGNMENT_ORDER}
    total = sum(normalized.values()) or 1.0
    normalized = {key: value / total for key, value in normalized.items()}
    return AlignmentRouting(
        player_id=player_id,
        weights=normalized,
        interaction=sum(normalized[key] * ALIGNMENT_INTERACTION[key] for key in ALIGNMENT_ORDER),
        top_state=top_state or max(normalized, key=normalized.get),
        confidence=float(confidence),
        provider_used=provider_used,
        state=dict(state),
    )


def _feature_matrix(
    features: pd.DataFrame,
    names: Sequence[str],
    means: Sequence[float],
    scales: Sequence[float],
) -> np.ndarray:
    columns = [_series(features, name).to_numpy(dtype=float) for name in names]
    matrix = np.column_stack(columns) if columns else np.zeros((len(features), 0))
    means_array = np.asarray(means, dtype=float)
    scales_array = np.asarray(scales, dtype=float)
    scales_array = np.where(scales_array == 0.0, 1.0, scales_array)
    return (matrix - means_array) / scales_array


def _series(features: pd.DataFrame, name: str) -> pd.Series:
    if name in features.columns:
        return pd.to_numeric(features[name], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=features.index)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
