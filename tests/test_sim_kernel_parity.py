"""Parity between the Rust scoring kernel and the Python reference."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ceminidfs.export._sim_kernel import (  # noqa: E402
    quantile_linear,
    use_sim_kernel,
)
from ceminidfs.export.sim_rerank import (  # noqa: E402
    _lineup_indexes,
    _lineup_ownership_fraction,
    build_player_index,
    leverage_lineup_scores,
    lineup_player_ids,
    lineup_player_names,
    score_lineup,
)
from ceminidfs.models.simulate import simulate_fd_points  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_fd_slate.csv"
CACHED_SLATE = ROOT / "data" / "slates" / "2026-11-22_fd_sun.csv"
SLOTS = ("QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DEF")
ATOL = 1e-9


def _require_extension() -> None:
    try:
        import ceminidfs._sim_kernel_rust  # noqa: F401
    except ImportError as exc:
        raise AssertionError(
            "ceminidfs._sim_kernel_rust is missing. Run scripts/build_sim_kernel.sh"
        ) from exc


@pytest.fixture(scope="module", autouse=True)
def extension_is_built():
    _require_extension()


def _adapt_slate(frame: pd.DataFrame) -> pd.DataFrame:
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


def _load_slate(path: Path) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    return _adapt_slate(frame), frame.to_dict(orient="records")


def _slot_pools(positions: np.ndarray) -> list[np.ndarray]:
    upper = np.char.upper(np.asarray(positions, dtype=str))

    def rows(labels: tuple[str, ...]) -> np.ndarray:
        return np.flatnonzero(np.isin(upper, list(labels)))

    pools = {
        "QB": rows(("QB",)),
        "RB": rows(("RB",)),
        "WR": rows(("WR",)),
        "TE": rows(("TE",)),
        "DEF": rows(("DEF", "DST", "D")),
        "FLEX": rows(("RB", "WR", "TE")),
    }
    return [pools[slot] for slot in SLOTS]


def make_lineups(player_ids: list[str], positions: np.ndarray, count: int, seed: int) -> list[list[str]]:
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


def python_leverage_reference(
    lineups: list[list[str]],
    matrix: np.ndarray,
    player_index: dict[str, int],
    ownership: dict[str, float],
    top_fraction: float = 0.01,
    exponent: float = 0.5,
) -> tuple[list[float], float]:
    """Numpy copy of the leverage formula. A NaN threshold counts zero hits."""

    totals: list[np.ndarray] = []
    for lineup in lineups:
        indexes = _lineup_indexes(
            lineup_player_names(lineup),
            player_index,
            lineup_player_ids(lineup),
            matrix,
        )
        totals.append(matrix[indexes, :].sum(axis=0))
    if not totals:
        return [], 0.0
    threshold = float(np.quantile(np.concatenate(totals), 1.0 - top_fraction))
    scores: list[float] = []
    for lineup, vector in zip(lineups, totals, strict=True):
        tail = float((vector >= threshold).mean())
        fraction = _lineup_ownership_fraction(lineup, ownership)
        scores.append(tail / (fraction ** float(exponent)))
    return scores, threshold


def _assert_close(actual: list[float], expected: list[float], threshold: float, expected_threshold: float) -> None:
    assert len(actual) == len(expected)
    if expected and np.isnan(expected).all():
        assert np.isnan(actual).all()
        assert np.isnan(threshold)
        assert np.isnan(expected_threshold)
        return
    np.testing.assert_allclose(actual, expected, atol=ATOL, rtol=0)
    assert threshold == pytest.approx(expected_threshold, abs=ATOL, rel=0)


def _ownership_from_salary(records: list[dict[str, str]]) -> dict[str, float]:
    lookup: dict[str, float] = {}
    for record in records:
        player_id = str(record.get("Id") or record.get("player_id") or "")
        salary = float(record.get("Salary") or 0.0)
        if player_id:
            lookup[player_id] = salary / 100.0
    return lookup


def _simulate(path: Path, n_iterations: int, seed: int) -> tuple[np.ndarray, dict[str, int], dict[str, float], list[str], np.ndarray]:
    adapted, records = _load_slate(path)
    matrix = simulate_fd_points(
        adapted,
        method="team_shock",
        n_iterations=n_iterations,
        seed=seed,
    )
    player_index = build_player_index(records)
    ownership = _ownership_from_salary(records)
    player_ids = adapted["player_id"].astype(str).tolist()
    positions = adapted["position"].to_numpy()
    return matrix, player_index, ownership, player_ids, positions


def test_extension_import_message():
    _require_extension()
    assert use_sim_kernel() is True or os.environ.get("FAST_ANYTHING_DISABLE") == "1"


def test_quantile_linear_matches_numpy():
    values = [4.0, 1.0, 3.0, 2.0, 8.0]
    for q in (0.0, 0.25, 0.5, 0.85, 1.0):
        actual = quantile_linear(values, q)
        expected = float(np.quantile(np.asarray(values, dtype=np.float64), q))
        assert actual == pytest.approx(expected, abs=ATOL, rel=0)
    assert np.isnan(quantile_linear([1.0, np.nan, 3.0], 0.5))
    assert np.isnan(quantile_linear([], 0.5))


def test_fixture_slate_parity():
    matrix, player_index, ownership, player_ids, positions = _simulate(FIXTURE, 2000, 1234)
    lineups = make_lineups(player_ids, positions, 40, 7)
    scores, threshold = leverage_lineup_scores(lineups, matrix, player_index, ownership)
    expected, expected_threshold = python_leverage_reference(
        lineups, matrix, player_index, ownership
    )
    _assert_close(scores, expected, threshold, expected_threshold)


def test_cached_slate_parity():
    matrix, player_index, ownership, player_ids, positions = _simulate(CACHED_SLATE, 1000, 20261122)
    lineups = make_lineups(player_ids, positions, 50, 7)
    scores, threshold = leverage_lineup_scores(lineups, matrix, player_index, ownership)
    expected, expected_threshold = python_leverage_reference(
        lineups, matrix, player_index, ownership
    )
    _assert_close(scores, expected, threshold, expected_threshold)


def test_empty_lineup_list():
    matrix = np.ones((2, 4), dtype=np.float64)
    scores, threshold = leverage_lineup_scores([], matrix, {"A": 0}, {})
    assert scores == []
    assert threshold == 0.0


def test_single_lineup():
    matrix = np.array([[1.0, 2.0, 3.0, 4.0], [0.5, 0.5, 0.5, 0.5]], dtype=np.float64)
    player_index = {"A": 0, "B": 1}
    lineups = [["A", "B"]]
    ownership = {"A": 20.0, "B": 10.0}
    scores, threshold = leverage_lineup_scores(lineups, matrix, player_index, ownership)
    expected, expected_threshold = python_leverage_reference(
        lineups, matrix, player_index, ownership
    )
    _assert_close(scores, expected, threshold, expected_threshold)


def test_one_iteration():
    matrix = np.array([[10.0], [3.0], [1.0]], dtype=np.float64)
    player_index = {"A": 0, "B": 1, "C": 2}
    lineups = [["A", "B"], ["C"]]
    ownership = {"A": 12.0, "B": 8.0, "C": 4.0}
    scores, threshold = leverage_lineup_scores(lineups, matrix, player_index, ownership)
    expected, expected_threshold = python_leverage_reference(
        lineups, matrix, player_index, ownership
    )
    _assert_close(scores, expected, threshold, expected_threshold)


def test_duplicate_player_rows():
    matrix = np.array([[2.0, 4.0, 6.0], [10.0, 10.0, 10.0]], dtype=np.float64)
    player_index = {"A": 0, "B": 1}
    lineups = [["A", "A", "B"]]
    ownership = {"A": 25.0, "B": 5.0}
    scores, threshold = leverage_lineup_scores(lineups, matrix, player_index, ownership)
    expected, expected_threshold = python_leverage_reference(
        lineups, matrix, player_index, ownership
    )
    _assert_close(scores, expected, threshold, expected_threshold)


def test_ownership_fraction_floor():
    matrix = np.array([[1.0, 3.0, 5.0, 7.0], [2.0, 2.0, 2.0, 2.0]], dtype=np.float64)
    player_index = {"A": 0, "B": 1}
    lineups = [["A", "B"]]
    ownership = {"A": 0.0, "B": 0.001}
    fraction = _lineup_ownership_fraction(lineups[0], ownership)
    # log/exp of the 1e-4 floor is 1e-4 plus one ulp.
    assert fraction == pytest.approx(1e-4, abs=1e-18, rel=0)
    scores, threshold = leverage_lineup_scores(lineups, matrix, player_index, ownership)
    expected, expected_threshold = python_leverage_reference(
        lineups, matrix, player_index, ownership
    )
    _assert_close(scores, expected, threshold, expected_threshold)


def test_nan_matrix_returns_nan_scores(monkeypatch: pytest.MonkeyPatch):
    matrix = np.array([[1.0, np.nan, 3.0], [4.0, 5.0, 6.0]], dtype=np.float64)
    player_index = {"A": 0, "B": 1}
    lineups = [["A", "B"], ["A"]]
    ownership = {"A": 15.0, "B": 15.0}
    monkeypatch.delenv("FAST_ANYTHING_DISABLE", raising=False)
    assert use_sim_kernel() is True
    scores, threshold = leverage_lineup_scores(lineups, matrix, player_index, ownership)
    assert scores == [0.0, 0.0]
    assert np.isnan(threshold)
    nan_score = score_lineup(["A", "B"], matrix, player_index, quantile=0.5)
    assert np.isnan(nan_score)

    monkeypatch.setenv("FAST_ANYTHING_DISABLE", "1")
    assert use_sim_kernel() is False
    python_scores, python_threshold = leverage_lineup_scores(
        lineups, matrix, player_index, ownership
    )
    assert python_scores == [0.0, 0.0]
    assert np.isnan(python_threshold)
    python_nan_score = score_lineup(["A", "B"], matrix, player_index, quantile=0.5)
    assert np.isnan(python_nan_score)

    expected, expected_threshold = python_leverage_reference(
        lineups, matrix, player_index, ownership
    )
    assert expected == [0.0, 0.0]
    assert np.isnan(expected_threshold)


def test_score_lineup_matches_python_reference():
    matrix, player_index, _ownership, player_ids, positions = _simulate(FIXTURE, 200, 1234)
    lineups = make_lineups(player_ids, positions, 5, 7)
    for lineup in lineups:
        actual = score_lineup(lineup, matrix, player_index, quantile=0.85)
        indexes = _lineup_indexes(lineup, player_index, None, matrix)
        expected = float(np.quantile(matrix[indexes, :].sum(axis=0), 0.85))
        assert actual == pytest.approx(expected, abs=ATOL, rel=0)


def test_kill_switch_uses_python_reference(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FAST_ANYTHING_DISABLE", "1")
    assert use_sim_kernel() is False
    matrix = np.arange(24, dtype=np.float64).reshape(4, 6)
    player_index = {"A": 0, "B": 1, "C": 2, "D": 3}
    lineups = [["A", "B"], ["C", "D"], ["A", "D"]]
    ownership = {"A": 0.0, "B": 40.0, "C": 10.0, "D": 5.0}
    scores, threshold = leverage_lineup_scores(lineups, matrix, player_index, ownership)
    expected, expected_threshold = python_leverage_reference(
        lineups, matrix, player_index, ownership
    )
    _assert_close(scores, expected, threshold, expected_threshold)
    actual = score_lineup(["A", "C"], matrix, player_index, quantile=0.4)
    indexes = _lineup_indexes(["A", "C"], player_index, None, matrix)
    reference = float(np.quantile(matrix[indexes, :].sum(axis=0), 0.4))
    assert actual == pytest.approx(reference, abs=ATOL, rel=0)
