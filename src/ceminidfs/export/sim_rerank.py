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


def build_player_index(normalized_csv: str | Path | Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Build a name-to-row-index map matching the simulation matrix row order."""

    rows: Iterable[Mapping[str, Any]]
    if isinstance(normalized_csv, (str, Path)):
        path = Path(normalized_csv)
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    else:
        rows = normalized_csv

    index: dict[str, int] = {}
    for row_index, row in enumerate(rows):
        name = _row_name(row)
        if name and name not in index:
            index[name] = row_index
    return index


def score_lineup(
    player_names: Sequence[str],
    sim_matrix: Any,
    player_index: Mapping[str, int],
) -> float:
    """Return the lineup's mean simulated fantasy score."""

    matrix = np.asarray(sim_matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("sim_matrix must be a 2D array")

    indexes = [_lookup_player_index(name, player_index) for name in player_names if str(name).strip()]
    if not indexes:
        raise ValueError("lineup has no player names")
    if max(indexes) >= matrix.shape[0]:
        raise ValueError("player_index contains row outside sim_matrix")

    return float(matrix[indexes, :].sum(axis=0).mean())


def rerank_lineups(
    lineup_rows: Iterable[Any],
    sim_matrix: Any,
    player_index: Mapping[str, int],
    final_count: int = 150,
) -> list[Any]:
    """Score candidates by simulated mean and return the top unique lineups."""

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
                score_lineup(names, sim_matrix, player_index),
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
    **kwargs: Any,
) -> int:
    """Generate candidate lineups, rerank by simulated score, and write final CSV."""

    candidate_lineups = generate_lineups(csv_path, site=site, count=candidates, **kwargs)
    selected = rerank_lineups(candidate_lineups, sim_matrix, player_index, final_count=final)
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


def _lookup_player_index(name: str, player_index: Mapping[str, int]) -> int:
    if name in player_index:
        return int(player_index[name])
    normalized = _normalize_name(name)
    for candidate, index in player_index.items():
        if _normalize_name(candidate) == normalized:
            return int(index)
    raise KeyError(f"Player not found in sim matrix index: {name}")


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
