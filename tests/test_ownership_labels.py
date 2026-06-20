import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data.ownership_labels import load_ownership_labels
from ceminidfs.pipeline.engine import normalize_join_key


def test_load_ownership_labels_uses_benchmark_ownership_headers(tmp_path: Path):
    labels_csv = tmp_path / "labels.csv"
    labels_csv.write_text(
        "Player,Team,Position,Own%\n"
        "Patrick Mahomes,KC,QB,12.5%\n"
        "Travis Kelce,KC,TE,18.0\n",
        encoding="utf-8",
    )

    rows = load_ownership_labels(labels_csv)

    assert rows == [
        {
            "join_key": normalize_join_key("Patrick Mahomes", "KC", "QB"),
            "player_name": "Patrick Mahomes",
            "team": "KC",
            "position": "QB",
            "ownership": pytest.approx(12.5),
        },
        {
            "join_key": normalize_join_key("Travis Kelce", "KC", "TE"),
            "player_name": "Travis Kelce",
            "team": "KC",
            "position": "TE",
            "ownership": pytest.approx(18.0),
        },
    ]


def test_load_ownership_labels_skips_rows_without_ownership(tmp_path: Path):
    labels_csv = tmp_path / "labels.csv"
    labels_csv.write_text(
        "Name,TeamAbbrev,Position,Projected Ownership\n"
        "Patrick Mahomes,KC,QB,\n"
        "Travis Kelce,KC,TE,18.0\n",
        encoding="utf-8",
    )

    rows = load_ownership_labels(labels_csv)

    assert len(rows) == 1
    assert rows[0]["player_name"] == "Travis Kelce"
