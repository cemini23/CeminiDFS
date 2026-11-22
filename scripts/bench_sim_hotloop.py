#!/usr/bin/env python3
"""Time leverage_lineup_scores on the cached Sunday slate.

The script prints one JSON line. It runs the timed call twice and keeps the
second run. The simulation and the lineup list are built once, outside the timer.
"""

from __future__ import annotations

import hashlib
import json
import os
import resource
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ceminidfs.export.sim_rerank import (  # noqa: E402
    build_ownership_lookup,
    build_player_index,
    leverage_lineup_scores,
)
from ceminidfs.models.simulate import simulate_fd_points  # noqa: E402

SLATE_PATH = ROOT / "data" / "slates" / "2026-11-22_fd_sun.csv"
SLOTS = ("QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DEF")
DEF_POSITIONS = ("DEF", "DST", "D")
FLEX_POSITIONS = ("RB", "WR", "TE")


def _adapt_slate(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the columns simulate_fd_points requires, in slate row order."""

    def column(*names: str) -> pd.Series:
        for name in names:
            if name in frame.columns:
                return frame[name]
        raise KeyError(f"slate is missing one of {names}")

    return pd.DataFrame(
        {
            "player_id": column("player_id", "Id").astype(str),
            "fd_projection": pd.to_numeric(column("fd_projection", "FPPG"), errors="coerce"),
            "team": column("team", "Team").astype(str),
            "position": column("position", "Position").astype(str),
        }
    )


def _slot_pools(positions: np.ndarray) -> list[np.ndarray]:
    upper = np.asarray(positions, dtype=str)
    upper = np.char.upper(upper)

    def rows(labels: tuple[str, ...]) -> np.ndarray:
        return np.flatnonzero(np.isin(upper, list(labels)))

    pools = {
        "QB": rows(("QB",)),
        "RB": rows(("RB",)),
        "WR": rows(("WR",)),
        "TE": rows(("TE",)),
        "DEF": rows(DEF_POSITIONS),
        "FLEX": rows(FLEX_POSITIONS),
    }
    return [pools[slot] for slot in SLOTS]


def make_lineups(player_ids: list[str], positions: np.ndarray, count: int, seed: int) -> list[list[str]]:
    """Build count lineups of nine slots from a fixed Generator."""

    rng = np.random.default_rng(seed)
    slot_pools = _slot_pools(positions)
    lineups: list[list[str]] = []
    for _ in range(count):
        used: set[int] = set()
        picks: list[int] = []
        for pool in slot_pools:
            available = [int(index) for index in pool if int(index) not in used]
            source = available if available else [int(index) for index in pool]
            if not source:
                raise RuntimeError("position pool is empty")
            choice = int(rng.choice(np.asarray(source, dtype=np.int64)))
            picks.append(choice)
            used.add(choice)
        lineups.append([player_ids[index] for index in picks])
    return lineups


def _sha256_f64(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype=np.float64)
    return hashlib.sha256(array.tobytes()).hexdigest()


def _maxrss_kb() -> float:
    """Return the process peak resident set in KB.

    macOS reports ``ru_maxrss`` in bytes. Linux reports it in KB.
    """

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return rss / 1024.0
    return float(rss)


def _kernel_name() -> str:
    if os.environ.get("FAST_ANYTHING_DISABLE") == "1":
        return "python"
    try:
        from ceminidfs.export._sim_kernel import use_sim_kernel
    except ImportError:
        return "python"
    return "rust" if use_sim_kernel() else "python"


def main() -> None:
    frame = pd.read_csv(SLATE_PATH, dtype=str, keep_default_na=False)
    adapted = _adapt_slate(frame)
    matrix = simulate_fd_points(
        adapted,
        method="team_shock",
        n_iterations=10000,
        seed=20261122,
    )
    player_ids = adapted["player_id"].astype(str).tolist()
    lineups = make_lineups(player_ids, adapted["position"].to_numpy(), 500, 7)
    player_index = build_player_index(SLATE_PATH)
    ownership = build_ownership_lookup(SLATE_PATH)

    def time_scores() -> tuple[float, int, list[float]]:
        tracemalloc.start()
        started = time.perf_counter()
        scores, _threshold = leverage_lineup_scores(
            lineups,
            matrix,
            player_index,
            ownership,
        )
        runtime_s = time.perf_counter() - started
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return runtime_s, peak, [float(score) for score in scores]

    time_scores()
    runtime_s, peak, scores = time_scores()
    payload = {
        "runtime_s": runtime_s,
        "peak_kb": peak / 1024.0,
        "matrix_sha256": _sha256_f64(matrix),
        "scores_sha256": _sha256_f64(np.asarray(scores, dtype=np.float64)),
        "kernel": _kernel_name(),
        "maxrss_kb": _maxrss_kb(),
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
