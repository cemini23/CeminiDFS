"""Simulation-aware lineup reranking."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .lineup_report import format_lineup_report, write_lineup_report
from .optimize import (
    TEAM_DART_LOG,
    enforce_named_min_counts,
    exposure_hatch_overrides,
    generate_lineups,
    select_with_exposure_caps,
    write_lineup_artifacts,
)
from .pool_guards import TREND_MIN_EXPOSURE
from .review_reports import maybe_write_review_reports, pop_review_kwargs

NAME_KEYS = (
    "name",
    "Name",
    "player",
    "Player",
    "player_name",
    "Player Name",
    "nickname",
    "Nickname",
    "full_name",
    "Full Name",
    "player_key",
    "First Name",
)

ID_KEYS = (
    "Id",
    "id",
    "ID",
    "fd_id",
    "dk_id",
    "player_id",
    "player_key",
)

RERANK_MODES = ("fpts", "ceiling", "leverage")
DEFAULT_RERANK_MODE = "ceiling"
MODE_QUANTILE = {"fpts": 0.5, "ceiling": 0.85}
TOP_FRACTION = 0.01
LEVERAGE_EXPONENT = 0.5


def build_player_index(normalized_csv: str | Path | Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Build player-id and name keys mapped to simulation matrix row order."""

    rows: Iterable[Mapping[str, Any]]
    if isinstance(normalized_csv, (str, Path)):
        path = Path(normalized_csv)
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    else:
        rows = normalized_csv

    index: dict[str, int] = {}
    for row_index, row in enumerate(rows):
        player_id = _row_player_id(row)
        if player_id and player_id not in index:
            index[player_id] = row_index
        name = _row_name(row)
        if name and name not in index:
            index[name] = row_index
    return index


def _core_cap_from_gates(gates: Any) -> int | None:
    """Return the 5-player core cap from a gates mapping, or None when off."""

    if not isinstance(gates, Mapping):
        return None
    core = gates.get("core")
    if not isinstance(core, Mapping) or not core.get("enabled"):
        return None
    value = core.get("max_count")
    return int(value) if value is not None else None


def _csv_player_rows(csv_path: str | Path) -> list[dict[str, str]]:
    """Read a normalized players CSV as plain rows for the gate helpers."""

    path = Path(csv_path)
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def build_ownership_lookup(
    normalized_csv: str | Path | Iterable[Mapping[str, Any]],
) -> dict[str, float]:
    """Map player ids and names to projected ownership percentages."""

    rows: Iterable[Mapping[str, Any]]
    if isinstance(normalized_csv, (str, Path)):
        path = Path(normalized_csv)
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    else:
        rows = normalized_csv

    lookup: dict[str, float] = {}
    for row in rows:
        ownership = _row_ownership(row)
        if ownership is None:
            continue
        player_id = _row_player_id(row)
        name = _row_name(row)
        if player_id:
            lookup[player_id] = ownership
        if name:
            lookup[name] = ownership
    return lookup


def score_lineup(
    player_names: Sequence[str],
    sim_matrix: Any,
    player_index: Mapping[str, int],
    *,
    quantile: float = 0.85,
    ownership_lookup: Mapping[str, float] | None = None,
    ownership_penalty: float = 0.0,
    player_ids: Sequence[str] | None = None,
) -> float:
    """Return tail simulated score minus an optional ownership leverage penalty."""

    matrix = np.asarray(sim_matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("sim_matrix must be a 2D array")
    if not 0.0 < quantile < 1.0:
        raise ValueError("quantile must be between 0 and 1")

    indexes = _lineup_indexes(player_names, player_index, player_ids, matrix)
    lineup_totals = matrix[indexes, :].sum(axis=0)
    score = float(np.quantile(lineup_totals, quantile))

    if ownership_lookup and ownership_penalty > 0:
        ownership_values = []
        for idx, name in enumerate(player_names):
            if not str(name).strip():
                continue
            player_id = player_ids[idx] if player_ids and idx < len(player_ids) else None
            ownership_values.append(
                _lookup_ownership(name, ownership_lookup, player_id=player_id)
            )
        if ownership_values:
            score -= float(ownership_penalty) * float(np.mean(ownership_values))

    return score


def leverage_lineup_scores(
    lineups: Sequence[Any],
    sim_matrix: Any,
    player_index: Mapping[str, int],
    ownership_lookup: Mapping[str, float],
    *,
    top_fraction: float = TOP_FRACTION,
    exponent: float = LEVERAGE_EXPONENT,
) -> tuple[list[float], float]:
    """Score each lineup by ``P(score >= top_1pct) / geom_mean_own ** 0.5``.

    The slate threshold is the ``(1 - top_fraction)`` quantile of the pooled
    simulated totals from every candidate lineup, and each lineup is scored
    against those same totals, so the threshold and the scores share one
    population. Ownership values are percentages and are divided by 100 before
    the geometric mean.
    """

    matrix = np.asarray(sim_matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("sim_matrix must be a 2D array")
    if not 0.0 < top_fraction < 1.0:
        raise ValueError("top_fraction must be between 0 and 1")

    totals_by_lineup: list[np.ndarray] = []
    for lineup in lineups:
        totals_by_lineup.append(
            _lineup_total_vector(
                lineup_player_names(lineup),
                matrix,
                player_index,
                lineup_player_ids(lineup),
            )
        )
    pooled = np.concatenate(totals_by_lineup) if totals_by_lineup else np.zeros(1)
    threshold = float(np.quantile(pooled, 1.0 - top_fraction))

    scores: list[float] = []
    for lineup, totals in zip(lineups, totals_by_lineup, strict=True):
        tail_probability = float((totals >= threshold).mean())
        ownership_fraction = _lineup_ownership_fraction(lineup, ownership_lookup)
        scores.append(tail_probability / (ownership_fraction ** float(exponent)))
    return scores, threshold


def _lineup_total_vector(
    player_names: Sequence[str],
    matrix: np.ndarray,
    player_index: Mapping[str, int],
    player_ids: Sequence[str] | None = None,
) -> np.ndarray:
    indexes = _lineup_indexes(player_names, player_index, player_ids, matrix)
    return matrix[indexes, :].sum(axis=0)


def _lineup_indexes(
    player_names: Sequence[str],
    player_index: Mapping[str, int],
    player_ids: Sequence[str] | None,
    matrix: np.ndarray,
) -> list[int]:
    indexes = []
    ids = list(player_ids or [])
    for idx, name in enumerate(player_names):
        if not str(name).strip():
            continue
        player_id = ids[idx] if idx < len(ids) else None
        indexes.append(_lookup_player_index(name, player_index, player_id=player_id))
    if not indexes:
        raise ValueError("lineup has no player names")
    if max(indexes) >= matrix.shape[0]:
        raise ValueError("player_index contains row outside sim_matrix")
    return indexes


def _lineup_ownership_fraction(lineup: Any, ownership_lookup: Mapping[str, float]) -> float:
    names = lineup_player_names(lineup)
    ids = lineup_player_ids(lineup)
    fractions: list[float] = []
    for idx, name in enumerate(names):
        if not str(name).strip():
            continue
        player_id = ids[idx] if idx < len(ids) else None
        percent = _lookup_ownership(name, ownership_lookup, player_id=player_id)
        fractions.append(max(float(percent), 0.0) / 100.0)
    if not fractions:
        return 1.0
    return float(np.exp(np.mean(np.log(np.maximum(fractions, 1.0e-4)))))


def rerank_lineups(
    lineup_rows: Iterable[Any],
    sim_matrix: Any,
    player_index: Mapping[str, int],
    final_count: int = 150,
    *,
    quantile: float = 0.85,
    mode: str = DEFAULT_RERANK_MODE,
    ownership_lookup: Mapping[str, float] | None = None,
    ownership_penalty: float = 0.0,
    max_exposure: float | None = None,
    max_team_exposure: float | None = None,
    exposure_overrides: Mapping[str, float] | None = None,
) -> list[Any]:
    """Score candidates by mode and return the top unique lineups.

    ``mode`` is ``fpts`` (median), ``ceiling`` (tail quantile), or ``leverage``
    (``P(score >= top 1%) / geom_mean_own ** 0.5``). The leverage mode needs an
    ``ownership_lookup``; without one it falls back to the ceiling mode.
    """

    if final_count <= 0:
        raise ValueError("final_count must be positive")
    if mode not in RERANK_MODES:
        raise ValueError(f"mode must be one of {RERANK_MODES}")

    unique: list[Any] = []
    seen: set[tuple[str, ...]] = set()
    for lineup in lineup_rows:
        names = lineup_player_names(lineup)
        key = tuple(sorted(_normalize_name(name) for name in names if str(name).strip()))
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(lineup)

    effective_mode = mode
    if effective_mode == "leverage" and not ownership_lookup:
        effective_mode = "ceiling"

    ranked: list[tuple[float, float, int, Any]] = []
    if effective_mode == "leverage":
        scores, _threshold = leverage_lineup_scores(
            unique, sim_matrix, player_index, ownership_lookup or {}
        )
        for order, (lineup, score) in enumerate(zip(unique, scores, strict=True)):
            ranked.append((score, _projection_sum(lineup), -order, lineup))
    else:
        effective_quantile = MODE_QUANTILE.get(effective_mode, quantile)
        for order, lineup in enumerate(unique):
            ranked.append(
                (
                    score_lineup(
                        lineup_player_names(lineup),
                        sim_matrix,
                        player_index,
                        quantile=effective_quantile,
                        ownership_lookup=ownership_lookup,
                        ownership_penalty=ownership_penalty,
                        player_ids=lineup_player_ids(lineup),
                    ),
                    _projection_sum(lineup),
                    -order,
                    lineup,
                )
            )

    ranked.sort(reverse=True)
    ordered = [lineup for _, _, _, lineup in ranked]
    if max_exposure is None and max_team_exposure is None and not exposure_overrides:
        return ordered[:final_count]
    return _select_with_exposure_cap(
        ordered,
        final_count,
        max_exposure,
        max_team_exposure=max_team_exposure,
        exposure_overrides=exposure_overrides,
    )


def _select_with_exposure_cap(
    lineups: list[Any],
    final_count: int,
    max_exposure: float | None,
    max_team_exposure: float | None = None,
    exposure_overrides: Mapping[str, float] | None = None,
) -> list[Any]:
    """Greedily keep lineups that do not push player or team share above the caps."""

    return select_with_exposure_caps(
        lineups,
        final_count,
        max_exposure=max_exposure,
        max_team_exposure=max_team_exposure,
        exposure_overrides=exposure_overrides,
    )


def optimize_with_sim_rerank(
    csv_path: str | Path,
    out_path: str | Path,
    sim_matrix: Any,
    player_index: Mapping[str, int],
    candidates: int = 2000,
    final: int = 150,
    site: str = "fanduel",
    *,
    quantile: float = 0.85,
    mode: str = DEFAULT_RERANK_MODE,
    ownership_lookup: Mapping[str, float] | None = None,
    ownership_penalty: float = 0.0,
    **kwargs: Any,
) -> int:
    """Generate candidate lineups, rerank by simulated score, and write final CSV."""

    team_exposure = kwargs.pop("max_team_exposure", None)
    kwargs.pop("require_count", None)
    trend_keys = list(kwargs.get("friday_trend_keys") or [])
    review_kwargs = pop_review_kwargs(kwargs)
    review_kwargs["core_cap"] = _core_cap_from_gates(kwargs.get("gates"))
    candidate_lineups = generate_lineups(
        csv_path,
        site=site,
        count=candidates,
        require_count=False,
        **kwargs,
    )
    exposure = kwargs["max_exposure"] if "max_exposure" in kwargs else 0.35
    exposure_overrides = exposure_hatch_overrides(
        _csv_player_rows(csv_path),
        kwargs.get("gates"),
        exposure,
    )
    selected = rerank_lineups(
        candidate_lineups,
        sim_matrix,
        player_index,
        final_count=final,
        quantile=quantile,
        mode=mode,
        ownership_lookup=ownership_lookup,
        ownership_penalty=ownership_penalty,
        max_exposure=exposure,
        max_team_exposure=team_exposure,
        exposure_overrides=exposure_overrides,
    )
    if trend_keys:
        selected = enforce_named_min_counts(
            selected,
            candidate_lineups,
            trend_keys,
            final_count=final,
            exposure=TREND_MIN_EXPOSURE,
            max_exposure=exposure,
        )
    if len(selected) != final:
        raise ValueError(f"optimizer wrote {len(selected)} lineups; requested {final}")
    written = write_lineup_artifacts(selected, out_path, site=site)
    maybe_write_review_reports(out_path, csv_path, site=site, **review_kwargs)
    stacks = kwargs.get("stacks")
    locks = kwargs.get("locks")
    excludes = kwargs.get("excludes")
    keep_team_dart = float(kwargs.get("keep_team_dart") or 0.0)
    soft_fade = kwargs.get("soft_fade")
    report = format_lineup_report(
        selected,
        stacks=stacks,
        locks=locks,
        excludes=excludes,
        no_offense_vs_dst=bool(kwargs.get("no_offense_vs_dst")),
        one_rb_per_team=bool(kwargs.get("one_rb_per_team")),
        projection_floor=kwargs.get("projection_floor"),
        uniques=kwargs.get("uniques"),
        max_team_exposure=team_exposure,
        keep_team_dart=keep_team_dart,
        soft_fade=soft_fade,
        team_dart_log=list(TEAM_DART_LOG),
    )
    write_lineup_report(report, Path(out_path).with_suffix(".report.txt"))
    print(report)
    return written


def lineup_player_names(lineup: Any) -> list[str]:
    """Extract player names from pydfs lineup objects or already-materialized rows."""

    players = getattr(lineup, "players", None)
    if players is not None:
        return [str(getattr(player, "full_name", "")).strip() for player in players]
    if isinstance(lineup, Mapping):
        return [str(value).strip() for value in lineup.values() if str(value).strip()]
    return [str(value).strip() for value in lineup if str(value).strip()]


def lineup_player_ids(lineup: Any) -> list[str]:
    players = getattr(lineup, "players", None)
    if players is None:
        return []
    ids: list[str] = []
    for player in players:
        for attr in ("id", "player_id"):
            value = getattr(player, attr, None)
            if value is not None and str(value).strip():
                ids.append(str(value).strip())
                break
        else:
            ids.append("")
    return ids


def _row_player_id(row: Mapping[str, Any]) -> str:
    for key in ID_KEYS:
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def _row_name(row: Mapping[str, Any]) -> str:
    first = str(row.get("First Name", "") or row.get("first name", "")).strip()
    last = str(row.get("Last Name", "") or row.get("last name", "")).strip()
    if first and last:
        return f"{first} {last}".strip()

    for key in NAME_KEYS:
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def _row_ownership(row: Mapping[str, Any]) -> float | None:
    for key in ("Projected Ownership", "ownership", "Own%"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _lookup_player_index(
    name: str,
    player_index: Mapping[str, int],
    *,
    player_id: str | None = None,
) -> int:
    if player_id and player_id in player_index:
        return int(player_index[player_id])
    if name in player_index:
        return int(player_index[name])
    normalized = _normalize_name(name)
    for candidate, index in player_index.items():
        if _normalize_name(candidate) == normalized:
            return int(index)
    raise KeyError(f"Player not found in sim matrix index: {name}")


def _lookup_ownership(
    name: str,
    ownership_lookup: Mapping[str, float],
    *,
    player_id: str | None = None,
) -> float:
    if player_id and player_id in ownership_lookup:
        return float(ownership_lookup[player_id])
    if name in ownership_lookup:
        return float(ownership_lookup[name])
    normalized = _normalize_name(name)
    for candidate, value in ownership_lookup.items():
        if _normalize_name(candidate) == normalized:
            return float(value)
    return 0.0


def _normalize_name(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def _projection_sum(lineup: Any) -> float:
    projection = getattr(lineup, "fantasy_points_projection", None)
    if projection is not None:
        return float(projection)

    players = getattr(lineup, "players", None)
    if players is None:
        return 0.0

    total = 0.0
    for player in players:
        for attr in ("fppg", "projected_points", "fantasy_points_projection"):
            value = getattr(player, attr, None)
            if value is not None:
                total += float(value)
                break
    return total
