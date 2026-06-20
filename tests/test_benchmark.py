import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data import benchmark
from ceminidfs.pipeline import benchmark_compare, engine


SAMPLE_STOKASTIC_CSV = """\
Player,Team,Position,Salary,Median,Own%
Patrick Mahomes,KC,QB,8500,22.8,12.5
Travis Kelce,KC,TE,7200,14.2,18.0
"""

SAMPLE_LABS_CSV = """\
Name,TeamAbbrev,Position,Salary,Labs Projection,Projected Ownership
Patrick Mahomes,KC,QB,8500,23.1,11.0
Travis Kelce,KC,TE,7200,13.9,17.5
"""


def test_detect_benchmark_source_stokastic():
    assert benchmark.detect_benchmark_source(["Player", "Median", "Own%"]) == "stokastic"


def test_detect_benchmark_source_fantasylabs():
    assert benchmark.detect_benchmark_source(["Name", "Labs Projection"]) == "fantasylabs"


def test_parse_stokastic_csv(tmp_path: Path):
    path = tmp_path / "stokastic.csv"
    path.write_text(SAMPLE_STOKASTIC_CSV, encoding="utf-8")

    rows = benchmark.parse_benchmark_csv(path, season=2024, week=4, source="stokastic")

    assert len(rows) == 2
    mahomes = rows[0]
    assert mahomes["source"] == "stokastic"
    assert mahomes["player_name"] == "Patrick Mahomes"
    assert mahomes["projection"] == pytest.approx(22.8)
    assert mahomes["ownership"] == pytest.approx(12.5)
    assert mahomes["join_key"] == engine.normalize_join_key("Patrick Mahomes", "KC", "QB")
    assert "Median" in mahomes["raw"]


def test_parse_fantasylabs_csv(tmp_path: Path):
    path = tmp_path / "labs.csv"
    path.write_text(SAMPLE_LABS_CSV, encoding="utf-8")

    rows = benchmark.parse_benchmark_csv(path, season=2024, week=4)

    assert len(rows) == 2
    assert rows[0]["source"] == "fantasylabs"
    assert rows[0]["projection"] == pytest.approx(23.1)


def test_write_benchmark_snapshot(tmp_path: Path):
    path = tmp_path / "stokastic.csv"
    path.write_text(SAMPLE_STOKASTIC_CSV, encoding="utf-8")
    rows = benchmark.parse_benchmark_csv(path, season=2024, week=4)

    out = benchmark.write_benchmark_snapshot(rows, tmp_path / "snapshot.json")
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert len(payload) == 2
    assert payload[0]["raw"]["Player"] == "Patrick Mahomes"


def test_compare_benchmark_week(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    benchmark_csv = tmp_path / "bench.csv"
    benchmark_csv.write_text(SAMPLE_STOKASTIC_CSV, encoding="utf-8")

    pbp = _season_pbp_with_week4()
    monkeypatch.setattr(benchmark_compare, "load_season_pbp", lambda season: pbp)
    week_dir = _write_week_cache(tmp_path)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)

    result = benchmark_compare.compare_benchmark_week(2024, 4, benchmark_csv, include_diy=True)

    assert result.season == 2024
    assert result.week == 4
    assert result.benchmark_source == "stokastic"
    assert len(result.models) == 2
    assert {model.model for model in result.models} == {"benchmark", "diy"}
    assert all(model.n_players > 0 for model in result.models)


def _write_week_cache(tmp_path: Path) -> Path:
    week_dir = tmp_path / "cache" / "2024" / "week_4"
    week_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "game_id": "2024_04_BUF_KC",
                "home_team": "KC",
                "away_team": "BUF",
                "total": 48.0,
                "spread": -3.0,
                "home_implied_total": 25.5,
                "away_implied_total": 22.5,
            }
        ]
    ).to_parquet(week_dir / "vegas.parquet", index=False)
    _season_pbp_with_week4().to_parquet(week_dir / "pbp.parquet", index=False)
    return week_dir


def _season_pbp_with_week4() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for week in (1, 2, 3, 4):
        rows.extend(_kc_game_rows(week))
        rows.extend(_buf_game_rows(week))
    return pd.DataFrame(rows)


def _kc_game_rows(week: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx in range(10):
        target_kelce = idx < 4
        complete = idx < 7
        yards = 12 if complete else 0
        rows.append(
            {
                "season": 2024,
                "week": week,
                "game_id": f"kc_{week}",
                "posteam": "KC",
                "wp": 0.5,
                "qtr": 1,
                "game_seconds_remaining": 3600 - (idx * 34),
                "pass": 1,
                "pass_attempt": 1,
                "rush": 0,
                "xpass": 0.62,
                "passer_player_id": "gsis_mahomes",
                "passer_player_name": "Patrick Mahomes",
                "receiver_player_id": "gsis_kelce" if target_kelce else "gsis_wr",
                "receiver_player_name": "Travis Kelce" if target_kelce else "KC WR",
                "passing_yards": yards,
                "receiving_yards": yards,
                "passing_tds": 1 if idx == 0 else 0,
                "receiving_tds": 1 if idx == 0 and target_kelce else 0,
                "interceptions": 1 if idx == 9 and week == 2 else 0,
                "complete_pass": 1 if complete else 0,
                "air_yards": 10,
            }
        )
    return rows


def _buf_game_rows(week: int) -> list[dict[str, object]]:
    return [
        {
            "season": 2024,
            "week": week,
            "game_id": f"buf_{week}",
            "posteam": "BUF",
            "wp": 0.5,
            "qtr": 1,
            "game_seconds_remaining": 3600 - (idx * 36),
            "pass": 1 if idx % 2 == 0 else 0,
            "pass_attempt": 1 if idx % 2 == 0 else 0,
            "rush": 0 if idx % 2 == 0 else 1,
            "xpass": 0.58,
            "passer_player_id": "gsis_buf_qb" if idx % 2 == 0 else None,
            "passer_player_name": "BUF QB" if idx % 2 == 0 else None,
            "receiver_player_id": "gsis_buf_wr" if idx % 2 == 0 else None,
            "receiver_player_name": "BUF WR" if idx % 2 == 0 else None,
            "rusher_player_id": "gsis_buf_rb" if idx % 2 else None,
            "rusher_player_name": "BUF RB" if idx % 2 else None,
            "passing_yards": 8 if idx % 2 == 0 else 0,
            "receiving_yards": 8 if idx % 2 == 0 else 0,
            "complete_pass": 1 if idx % 2 == 0 else 0,
            "air_yards": 8 if idx % 2 == 0 else 0,
        }
        for idx in range(8)
    ]
