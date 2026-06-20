"""Simulation-aware lineup reranking."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .optimize import generate_lineups, lineup_to_row, write_lineup_rows

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

    lineup_totals = matrix[indexes, :].sum(axis=0)
    score = float(np.quantile(lineup_totals, quantile))

    if ownership_lookup and ownership_penalty > 0:
        ownership_values = []
        for idx, name in enumerate(player_names):
            if not str(name).strip():
                continue
            player_id = ids[idx] if idx < len(ids) else None
            ownership_values.append(
                _lookup_ownership(name, ownership_lookup, player_id=player_id)
            )
        if ownership_values:
            score -= float(ownership_penalty) * float(np.mean(ownership_values))

    return score


def rerank_lineups(
    lineup_rows: Iterable[Any],
    sim_matrix: Any,
    player_index: Mapping[str, int],
    final_count: int = 150,
    *,
    quantile: float = 0.85,
    ownership_lookup: Mapping[str, float] | None = None,
    ownership_penalty: float = 0.0,
) -> list[Any]:
    """Score candidates by simulated tail quantile and return the top unique lineups."""

    if final_count <= 0:
        raise ValueError("final_count must be positive")

    ranked: list[tuple[float, float, int, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for order, lineup in enumerate(lineup_rows):
        names = lineup_player_names(lineup)
        key = tuple(sorted(_normalize_name(name) for name in names if str(name).strip()))
        if not key or key in seen:
            continue
        seen.add(key)
        ranked.append(
            (
                score_lineup(
                    names,
                    sim_matrix,
                    player_index,
                    quantile=quantile,
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
    return [lineup for _, _, _, lineup in ranked[:final_count]]


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
    ownership_lookup: Mapping[str, float] | None = None,
    ownership_penalty: float = 0.0,
    **kwargs: Any,
) -> int:
    """Generate candidate lineups, rerank by simulated score, and write final CSV."""

    candidate_lineups = generate_lineups(csv_path, site=site, count=candidates, **kwargs)
    selected = rerank_lineups(
        candidate_lineups,
        sim_matrix,
        player_index,
        final_count=final,
        quantile=quantile,
        ownership_lookup=ownership_lookup,
        ownership_penalty=ownership_penalty,
    )
    rows = [lineup_to_row(lineup, site=site) for lineup in selected]
    return write_lineup_rows(rows, out_path, site=site)


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
