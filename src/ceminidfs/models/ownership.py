"""Heuristic ownership projection for canonical DFS rows."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from collections import defaultdict
from pathlib import Path
from typing import Any

POSITION_SLOT_MASS = {
    "QB": 1.0,
    "RB": 2.0,
    "WR": 3.0,
    "TE": 1.0,
    "DEF": 1.0,
}

OWNERSHIP_TEMPERATURE = 1.0
OWNERSHIP_FEATURES = ("heuristic_ownership", "value_score", "projection", "salary_k")
GLOBAL_POSITION = "__global__"


@dataclass
class OwnershipCalibration:
    """Linear ownership calibration coefficients keyed by position."""

    coefficients: dict[str, list[float]]
    feature_names: list[str] = field(default_factory=lambda: list(OWNERSHIP_FEATURES))
    model_type: str = "ridge"
    site: str = "fanduel"
    sample_size: int = 0
    alpha: float = 1.0
    version: int = 1


def project_ownership(rows: list[dict], site: str = "fanduel") -> list[dict]:
    """Add projected ownership percentages to rows and return the same list.

    Ownership is a v1 value-rank softmax: projection per $1k of salary is
    converted to a position-local probability distribution, then scaled by
    roster slot mass so each position group sums to its expected lineup share.
    """

    site_key = _site_key(site)
    position_key = f"{site_key}_position"
    salary_key = f"{site_key}_salary"
    projection_key = f"{site_key}_projection"

    groups: dict[str, list[tuple[dict, float]]] = defaultdict(list)
    unsupported: list[dict] = []
    for row in rows:
        position = _normalize_position(row.get(position_key))
        if position not in POSITION_SLOT_MASS:
            unsupported.append(row)
            continue
        groups[position].append((row, _value_score(row.get(projection_key), row.get(salary_key))))

    for position, entries in groups.items():
        weights = _softmax([value for _, value in entries], OWNERSHIP_TEMPERATURE)
        scale = POSITION_SLOT_MASS[position] * 100.0
        for (row, _), weight in zip(entries, weights, strict=True):
            row["Projected Ownership"] = f"{weight * scale:.1f}"

    for row in unsupported:
        row["Projected Ownership"] = "0.0"

    return rows


def fit_ownership_calibration(
    labels: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    site: str = "fanduel",
    alpha: float = 1.0,
    target_week: int | None = None,
) -> OwnershipCalibration:
    """Fit paid ownership labels against heuristic value features."""

    examples = _matched_training_examples(labels, rows, site, target_week=target_week)
    if not examples:
        raise ValueError("no ownership labels matched projection rows")

    global_coefficients, model_type = _fit_coefficients(
        [features for _, features, _ in examples],
        [target for _, _, target in examples],
        alpha,
    )
    coefficients: dict[str, list[float]] = {GLOBAL_POSITION: global_coefficients}

    by_position: dict[str, list[tuple[list[float], float]]] = defaultdict(list)
    for position, features, target in examples:
        by_position[position].append((features, target))

    for position, position_examples in by_position.items():
        if len(position_examples) < 2:
            continue
        coefficients[position], _ = _fit_coefficients(
            [features for features, _ in position_examples],
            [target for _, target in position_examples],
            alpha,
        )

    return OwnershipCalibration(
        coefficients=coefficients,
        model_type=model_type,
        site=site,
        sample_size=len(examples),
        alpha=alpha,
    )


def project_ownership_calibrated(
    rows: list[dict],
    calibration: OwnershipCalibration | None = None,
    *,
    site: str = "fanduel",
) -> list[dict]:
    """Project ownership using the heuristic baseline plus optional calibration."""

    project_ownership(rows, site=site)
    if calibration is None:
        return rows

    site_key = _site_key(calibration.site or site)
    for row in rows:
        position = _normalize_position(_row_position(row, site_key))
        coeffs = calibration.coefficients.get(position) or calibration.coefficients.get(GLOBAL_POSITION)
        if not coeffs:
            continue
        features = _features(row, site_key)
        projected = coeffs[0] + sum(coef * value for coef, value in zip(coeffs[1:], features, strict=True))
        row["Projected Ownership"] = f"{_clamp_ownership(projected):.1f}"
    return rows


def save_ownership_calibration(calibration: OwnershipCalibration, path: str | Path) -> Path:
    """Write an ownership calibration JSON artifact."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(calibration), indent=2) + "\n", encoding="utf-8")
    return output


def load_ownership_calibration(path: str | Path) -> OwnershipCalibration:
    """Load an ownership calibration JSON artifact."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return OwnershipCalibration(
        coefficients={
            str(position): [float(value) for value in values]
            for position, values in payload["coefficients"].items()
        },
        feature_names=[str(value) for value in payload.get("feature_names", OWNERSHIP_FEATURES)],
        model_type=str(payload.get("model_type", "ridge")),
        site=str(payload.get("site", "fanduel")),
        sample_size=int(payload.get("sample_size", 0)),
        alpha=float(payload.get("alpha", 1.0)),
        version=int(payload.get("version", 1)),
    )


def _matched_training_examples(
    labels: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    site: str,
    *,
    target_week: int | None = None,
) -> list[tuple[str, list[float], float]]:
    site_key = _site_key(site)
    label_by_key = {str(label.get("join_key")): label for label in labels if label.get("join_key")}
    projected_rows = [dict(row) for row in rows]
    project_ownership(projected_rows, site=site)

    resolved_week = target_week if target_week is not None else _target_week_from_rows(projected_rows)

    examples: list[tuple[str, list[float], float]] = []
    for row in projected_rows:
        label = label_by_key.get(_row_join_key(row, site_key))
        if not label:
            continue
        if resolved_week is not None:
            label_week = label.get("week")
            if label_week is not None and int(label_week) >= resolved_week:
                continue
        target = _to_float(label.get("ownership"))
        if not math.isfinite(target):
            continue
        position = _normalize_position(_row_position(row, site_key))
        examples.append((position, _features(row, site_key), _clamp_ownership(target)))
    return examples


def _fit_coefficients(
    features: list[list[float]], targets: list[float], alpha: float
) -> tuple[list[float], str]:
    elastic_net = _fit_elastic_net(features, targets)
    if elastic_net is not None:
        return elastic_net, "elastic_net"
    return _fit_ridge(features, targets, alpha), "ridge"


def _fit_elastic_net(features: list[list[float]], targets: list[float]) -> list[float] | None:
    if len(features) < len(OWNERSHIP_FEATURES) * 2:
        return None
    try:
        from sklearn.linear_model import ElasticNet  # type: ignore
    except ImportError:
        return None

    model = ElasticNet(alpha=0.01, l1_ratio=0.15, fit_intercept=True, max_iter=10000)
    model.fit(features, targets)
    return [float(model.intercept_), *[float(value) for value in model.coef_]]


def _fit_ridge(features: list[list[float]], targets: list[float], alpha: float) -> list[float]:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - pandas normally installs numpy
        raise RuntimeError("numpy is required to fit ownership calibration") from exc

    x = np.asarray(features, dtype=float)
    y = np.asarray(targets, dtype=float)
    x_aug = np.column_stack([np.ones(len(x)), x])
    penalty = np.eye(x_aug.shape[1]) * float(alpha)
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(x_aug.T @ x_aug + penalty, x_aug.T @ y)
    return [float(value) for value in beta]


def _features(row: dict[str, Any], site_key: str) -> list[float]:
    projection = _to_float(_row_projection(row, site_key))
    salary = _to_float(_row_salary(row, site_key))
    return [
        _to_float(row.get("Projected Ownership")),
        _value_score(projection, salary),
        projection,
        salary / 1000.0 if salary > 0.0 else 0.0,
    ]


def _target_week_from_rows(rows: list[dict[str, Any]]) -> int | None:
    for row in rows:
        week = row.get("week")
        if week in (None, ""):
            week = _week_from_slate_id(row.get("slate_id"))
        if week in (None, ""):
            continue
        try:
            return int(week)
        except (TypeError, ValueError):
            continue
    return None


def _week_from_slate_id(value: Any) -> int | None:
    text = str(value or "").strip().lower()
    if "_w" not in text:
        return None
    suffix = text.rsplit("_w", 1)[-1]
    try:
        return int(suffix)
    except ValueError:
        return None


def _row_join_key(row: dict[str, Any], site_key: str) -> str:
    if row.get("join_key"):
        return str(row["join_key"])
    name = row.get("player_name") or row.get("name") or row.get("nickname")
    team = row.get("team") or row.get("Team") or row.get("team_abbrev")
    return _normalize_join_key(str(name or ""), str(team or ""), _row_position(row, site_key))


def _row_position(row: dict[str, Any], site_key: str) -> Any:
    return row.get(f"{site_key}_position") or row.get("position") or row.get("Position")


def _row_salary(row: dict[str, Any], site_key: str) -> Any:
    return row.get(f"{site_key}_salary") or row.get("salary") or row.get("Salary")


def _row_projection(row: dict[str, Any], site_key: str) -> Any:
    return row.get(f"{site_key}_projection") or row.get("projection") or row.get("Projection")


def _site_key(site: str) -> str:
    normalized = str(site or "fanduel").strip().lower()
    if normalized in {"fanduel", "fd"}:
        return "fd"
    if normalized in {"draftkings", "dk"}:
        return "dk"
    raise ValueError("site must be one of: fanduel, draftkings")


def _normalize_position(value: Any) -> str:
    position = str(value or "").strip().upper()
    if position == "DST":
        return "DEF"
    return position


def _value_score(projection: Any, salary: Any) -> float:
    salary_float = _to_float(salary)
    if salary_float <= 0.0:
        return 0.0
    return _to_float(projection) / (salary_float / 1000.0)


def _to_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _softmax(values: list[float], temperature: float) -> list[float]:
    if not values:
        return []
    temp = max(float(temperature), 1e-9)
    max_value = max(values)
    exp_values = [math.exp((value - max_value) / temp) for value in values]
    total = sum(exp_values)
    if total <= 0.0:
        return [1.0 / len(values)] * len(values)
    return [value / total for value in exp_values]


def _clamp_ownership(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(100.0, value))


def _normalize_join_key(name: Any, team: Any, position: Any) -> str:
    return "|".join(
        (
            _normalize_token(name),
            _normalize_token(team),
            _normalize_token(position).upper(),
        )
    )


def _normalize_token(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())
