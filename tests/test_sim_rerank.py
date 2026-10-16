import csv
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.export.sim_rerank import (
    TOP_FRACTION,
    build_player_index,
    leverage_lineup_scores,
    rerank_lineups,
    score_lineup,
)


def test_build_player_index_from_normalized_csv(tmp_path: Path):
    csv_path = tmp_path / "players.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["First Name", "Last Name", "FPPG"])
        writer.writeheader()
        writer.writerow({"First Name": "Patrick", "Last Name": "Mahomes", "FPPG": "22"})
        writer.writerow({"First Name": "Travis", "Last Name": "Kelce", "FPPG": "14"})

    assert build_player_index(csv_path) == {"Patrick Mahomes": 0, "Travis Kelce": 1}


def test_build_player_index_prefers_player_id():
    rows = [
        {"Id": "99", "First Name": "Patrick", "Last Name": "Mahomes", "FPPG": "22"},
        {"Id": "100", "First Name": "Travis", "Last Name": "Kelce", "FPPG": "14"},
    ]

    index = build_player_index(rows)

    assert index["99"] == 0
    assert index["Patrick Mahomes"] == 0


def test_score_lineup_returns_p90_simulated_lineup_score():
    sim_matrix = np.array(
        [
            [10.0, 14.0, 16.0],
            [8.0, 10.0, 12.0],
            [1.0, 1.0, 1.0],
        ]
    )
    player_index = {"QB One": 0, "WR One": 1, "DST One": 2}

    assert score_lineup(["QB One", "WR One"], sim_matrix, player_index) == pytest.approx(26.8)


def test_score_lineup_applies_ownership_penalty():
    sim_matrix = np.array([[10.0, 20.0], [8.0, 12.0]])
    player_index = {"QB One": 0, "WR One": 1}
    ownership = {"QB One": 20.0, "WR One": 10.0}

    base = score_lineup(["QB One", "WR One"], sim_matrix, player_index)
    penalized = score_lineup(
        ["QB One", "WR One"],
        sim_matrix,
        player_index,
        ownership_lookup=ownership,
        ownership_penalty=0.5,
    )

    assert penalized == pytest.approx(base - (0.5 * 15.0))


def test_rerank_lineups_selects_top_unique_lineups_by_sim_score():
    sim_matrix = np.array(
        [
            [10.0, 10.0],
            [12.0, 12.0],
            [5.0, 5.0],
            [1.0, 1.0],
        ]
    )
    player_index = {"A": 0, "B": 1, "C": 2, "D": 3}
    lineups = [
        ["C", "D"],
        ["A", "B"],
        ["B", "A"],
        ["A", "C"],
    ]

    assert rerank_lineups(lineups, sim_matrix, player_index, final_count=2) == [
        ["A", "B"],
        ["A", "C"],
    ]


def test_rerank_lineups_greedy_final_portfolio_exposure():
    sim_matrix = np.array(
        [
            [10.0, 10.0],
            [9.0, 9.0],
            [8.0, 8.0],
            [1.0, 1.0],
        ]
    )
    player_index = {"A": 0, "B": 1, "C": 2, "D": 3}
    lineups = [
        ["A", "B"],
        ["A", "C"],
        ["C", "D"],
    ]

    selected = rerank_lineups(
        lineups,
        sim_matrix,
        player_index,
        final_count=2,
        max_exposure=0.5,
    )

    assert selected == [["A", "B"], ["C", "D"]]
    names = [name for lineup in selected for name in lineup]
    assert names.count("A") == 1


def test_leverage_threshold_and_scores_share_one_population():
    """The slate threshold is the quantile over every lineup that is scored.

    With more lineups than the old 256-row threshold sample, a subset threshold
    would diverge from the full-population one; the fix computes one pooled
    population, so they agree.
    """

    n_lineups = 300
    n_iterations = 10
    matrix = np.repeat(np.arange(n_lineups, dtype=float)[:, None], n_iterations, axis=1)
    player_index = {f"p{i}": i for i in range(n_lineups)}
    lineups = [[f"p{i}"] for i in range(n_lineups)]
    ownership = {f"p{i}": 10.0 for i in range(n_lineups)}

    _scores, threshold = leverage_lineup_scores(lineups, matrix, player_index, ownership)

    totals = np.concatenate([matrix[[i], :].sum(axis=0) for i in range(n_lineups)])
    expected = float(np.quantile(totals, 1.0 - TOP_FRACTION))
    subset_expected = float(np.quantile(totals[: 256 * n_iterations], 1.0 - TOP_FRACTION))

    assert threshold == pytest.approx(expected)
    assert threshold != pytest.approx(subset_expected)
