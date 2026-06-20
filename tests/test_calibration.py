import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.pipeline import calibration, engine


SAMPLE_STOKASTIC_CSV = """\
Player,Team,Position,Salary,Median,Own%
Patrick Mahomes,KC,QB,8500,22.8,12.5
Travis Kelce,KC,TE,7200,14.2,18.0
"""


def test_build_calibration_report_diy_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pbp = _season_pbp_with_week4()
    week_dir = _write_week_cache(tmp_path)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)
    monkeypatch.setattr(calibration, "load_season_pbp", lambda season: pbp)

    report = calibration.build_calibration_report(2024, start_week=4, end_week=4)

    assert report.season == 2024
    assert len(report.models) == 1
    diy = report.models[0]
    assert diy.model == "diy"
    assert diy.n_player_weeks > 0
    assert any(row.position == "QB" for row in diy.by_position)


def test_build_calibration_report_with_benchmark(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pbp = _season_pbp_with_week4()
    week_dir = _write_week_cache(tmp_path)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)
    monkeypatch.setattr(calibration, "load_season_pbp", lambda season: pbp)

    benchmark_csv = tmp_path / "bench.csv"
    benchmark_csv.write_text(SAMPLE_STOKASTIC_CSV, encoding="utf-8")

    report = calibration.build_calibration_report(
        2024,
        start_week=4,
        end_week=4,
        benchmark_csv=benchmark_csv,
        benchmark_week=4,
    )

    assert len(report.models) == 2
    assert report.benchmark_source == "stokastic"
    assert {model.model for model in report.models} == {"diy", "benchmark"}


def test_render_calibration_brief_contains_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pbp = _season_pbp_with_week4()
    week_dir = _write_week_cache(tmp_path)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)
    monkeypatch.setattr(calibration, "load_season_pbp", lambda season: pbp)

    report = calibration.build_calibration_report(2024, start_week=4, end_week=4)
    brief = calibration.render_calibration_brief(report)

    assert brief.startswith("---")
    assert "Overall accuracy" in brief
    assert "Target (good)" in brief
    assert "Methodology" in brief
    assert "Calibration actions" in brief


def test_write_calibration_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pbp = _season_pbp_with_week4()
    week_dir = _write_week_cache(tmp_path)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)
    monkeypatch.setattr(calibration, "load_season_pbp", lambda season: pbp)

    report = calibration.build_calibration_report(2024, start_week=4, end_week=4)
    brief_path = calibration.write_calibration_brief(report, tmp_path / "brief.md")
    json_path = calibration.write_calibration_json(report, tmp_path / "brief.json")

    assert brief_path.is_file()
    assert json_path.is_file()
    assert "CeminiDFS calibration" in brief_path.read_text(encoding="utf-8")


def test_verdict_against_targets():
    assert calibration._verdict(6.0, 20, calibration.MAE_TARGETS["QB"]) == "very good"
    assert calibration._verdict(6.2, 20, calibration.MAE_TARGETS["QB"]) == "good"
    assert calibration._verdict(7.0, 20, calibration.MAE_TARGETS["QB"]) == "needs work"
    assert calibration._verdict(4.0, 2, calibration.MAE_TARGETS["WR"]) == "insufficient data"


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
