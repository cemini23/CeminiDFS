"""Zero-default rookie prior from local college features.

Inputs are draft capital, dominator rating, breakout age, and career yards per
route run. Every coefficient defaults to zero, so the prior is zero. A player
with no college row keeps the current projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


FEATURE_FIELDS = (
    "draft_capital",
    "dominator_rating",
    "breakout_age",
    "career_yards_per_route_run",
)

_ID_ALIASES = ("player_id", "gsis_id", "id")
_NAME_ALIASES = ("player_name", "name", "full_name")
_FEATURE_ALIASES: dict[str, tuple[str, ...]] = {
    "draft_capital": ("draft_capital", "draft_pick", "pick"),
    "dominator_rating": ("dominator_rating", "dominator"),
    "breakout_age": ("breakout_age",),
    "career_yards_per_route_run": (
        "career_yards_per_route_run",
        "career_yprr",
        "yards_per_route_run",
        "yprr",
    ),
}


@dataclass(frozen=True)
class RookiePriorSettings:
    enabled: bool = True
    intercept: float = 0.0
    draft_capital_coefficient: float = 0.0
    dominator_coefficient: float = 0.0
    breakout_age_coefficient: float = 0.0
    yards_per_route_run_coefficient: float = 0.0

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> "RookiePriorSettings":
        rookie = dict((config or {}).get("rookie_prior") or {})
        coefficients = dict(rookie.get("coefficients") or {})
        return cls(
            enabled=bool(rookie.get("enabled", True)),
            intercept=float(rookie.get("intercept", 0.0)),
            draft_capital_coefficient=float(coefficients.get("draft_capital", 0.0)),
            dominator_coefficient=float(coefficients.get("dominator_rating", 0.0)),
            breakout_age_coefficient=float(coefficients.get("breakout_age", 0.0)),
            yards_per_route_run_coefficient=float(
                coefficients.get("career_yards_per_route_run", 0.0)
            ),
        )


def compute_rookie_prior(
    features: Mapping[str, Any] | None,
    settings: RookiePriorSettings,
) -> float:
    """Return the rookie prior value. Every default coefficient is zero."""

    if not settings.enabled or features is None:
        return 0.0
    return (
        settings.intercept
        + settings.draft_capital_coefficient * _feature_value(features, "draft_capital")
        + settings.dominator_coefficient * _feature_value(features, "dominator_rating")
        + settings.breakout_age_coefficient * _feature_value(features, "breakout_age")
        + settings.yards_per_route_run_coefficient
        * _feature_value(features, "career_yards_per_route_run")
    )


def build_rookie_priors(
    features_by_player: Mapping[str, Mapping[str, Any]],
    settings: RookiePriorSettings,
) -> dict[str, float]:
    """Return one rookie prior value per player key."""

    return {
        str(player_key): compute_rookie_prior(features, settings)
        for player_key, features in features_by_player.items()
    }


def load_college_features_csv(path: str | Path | None) -> dict[str, dict[str, Any]]:
    """Return player key -> college feature row from a local CSV.

    A missing file, an empty frame, or a frame without an identity column
    returns an empty mapping, so the prior stays zero.
    """

    if path in (None, ""):
        return {}
    csv_path = Path(path)
    if not csv_path.is_file():
        return {}

    frame = pd.read_csv(csv_path)
    if frame.empty:
        return {}

    id_col = _first_present(frame, _ID_ALIASES)
    name_col = _first_present(frame, _NAME_ALIASES)
    if id_col is None and name_col is None:
        return {}

    features_by_player: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        player_key = _row_key(row, id_col, name_col)
        if not player_key:
            continue
        features_by_player[player_key] = {
            field: _feature_value(row, field) for field in FEATURE_FIELDS
        }
    return features_by_player


def apply_rookie_prior(
    rows: list[dict[str, Any]],
    features_by_player: Mapping[str, Mapping[str, Any]],
    settings: RookiePriorSettings,
    *,
    target_field: str = "fd_projection",
) -> list[dict[str, Any]]:
    """Add a ``rookie_prior`` column and add the prior to the target field.

    With the default zero coefficients the prior is zero, so the target field
    does not change. A player with no college row also keeps the current value.
    """

    output: list[dict[str, Any]] = []
    for row in rows:
        mapped = dict(row)
        features = _lookup_player_features(mapped, features_by_player)
        prior = compute_rookie_prior(features, settings)
        mapped["rookie_prior"] = prior
        if prior:
            base = _optional_float(mapped.get(target_field))
            if base is not None:
                mapped[target_field] = base + prior
        output.append(mapped)
    return output


def _lookup_player_features(
    row: Mapping[str, Any],
    features_by_player: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    for key in _ID_ALIASES:
        player_id = str(row.get(key) or "").strip()
        if player_id and player_id in features_by_player:
            return features_by_player[player_id]
    name = _normalize_name(row.get("player_name") or row.get("name"))
    if name and name in features_by_player:
        return features_by_player[name]
    return None


def _row_key(row: Mapping[str, Any], id_col: str | None, name_col: str | None) -> str:
    if id_col is not None:
        player_id = str(row.get(id_col) or "").strip()
        if player_id:
            return player_id
    if name_col is not None:
        return _normalize_name(row.get(name_col))
    return ""


def _feature_value(features: Mapping[str, Any], field: str) -> float:
    for key in (field, *_FEATURE_ALIASES[field]):
        value = features.get(key)
        coerced = _optional_float(value)
        if coerced is not None:
            return coerced
    return 0.0


def _first_present(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _normalize_name(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _optional_float(value: Any) -> float | None:
    coerced = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(coerced) else float(coerced)
