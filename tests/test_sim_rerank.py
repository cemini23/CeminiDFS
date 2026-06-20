import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.export.sim_rerank import build_player_index, rerank_lineups, score_lineup


def test_build_player_index_from_normalized_csv(tmp_path: Path):
    csv_path = tmp_path / "players.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["First Name", "Last Name", "FPPG"])
        writer.writeheader()
        writer.writerow({"First Name": "Patrick", "Last Name": "Mahomes", "FPPG": "22"})
        writer.writerow({"First Name": "Travis", "Last Name": "Kelce", "FPPG": "14"})

    assert build_player_index(csv_path) == {"Patrick Mahomes": 0, "Travis Kelce": 1}


def test_score_lineup_returns_mean_simulated_lineup_score():
    sim_matrix = np.array(
        [
            [10.0, 14.0, 16.0],
            [8.0, 10.0, 12.0],
            [1.0, 1.0, 1.0],
        ]
    )
    player_index = {"QB One": 0, "WR One": 1, "DST One": 2}

    assert score_lineup(["QB One", "WR One"], sim_matrix, player_index) == 70 / 3


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
