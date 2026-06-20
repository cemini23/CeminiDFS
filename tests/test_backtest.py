import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.pipeline import backtest, engine


def test_actual_week_fantasy_points_from_pbp():
    pbp = _season_pbp_with_week4()
    actuals = backtest.actual_week_fantasy_points(pbp, season=2024, week=4)

    mahomes = actuals.loc[actuals["player_id"] == "gsis_mahomes"].iloc[0]
    kelce = actuals.loc[actuals["player_id"] == "gsis_kelce"].iloc[0]

    assert mahomes["fd_actual"] > 0
    assert kelce["fd_actual"] > 0
    assert mahomes["pass_yds"] > 0


def test_backtest_week_walk_forward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pbp = _season_pbp_with_week4()
    _write_season_cache(tmp_path, pbp)
    week_dir = _write_week_cache(tmp_path)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)
    monkeypatch.setattr(backtest, "load_season_pbp", lambda season: pbp)

    result, merged = backtest.backtest_week(2024, 4, pbp)

    assert result.n_players > 0
    assert result.mae_fd >= 0
    assert not merged.empty
    assert "fd_projection" in merged.columns
    assert "fd_actual" in merged.columns


def test_run_backtest_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pbp = _season_pbp_with_week4()
    _write_season_cache(tmp_path, pbp)
    week_dir = _write_week_cache(tmp_path)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)
    monkeypatch.setattr(backtest, "load_season_pbp", lambda season: pbp)

    summary = backtest.run_backtest(2024, start_week=4, end_week=4)

    assert summary.n_player_weeks > 0
    assert summary.mae_fd >= 0
    assert summary.rmse_fd >= 0
    assert len(summary.weeks) == 1

    report = backtest.write_backtest_report(summary, tmp_path / "backtest.json")
    assert report.is_file()


def test_historical_pbp_excludes_target_week():
    pbp = _season_pbp_with_week4()
    historical = backtest._historical_pbp(pbp, season=2024, week=4)

    assert set(historical["week"]) == {1, 2, 3}


def _write_season_cache(tmp_path: Path, pbp: pd.DataFrame) -> None:
    cache = tmp_path / "cache"
    cache.mkdir(parents=True)
    pbp.to_parquet(cache / "pbp_2024.parquet", index=False)


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
    for idx in range(5):
        rows.append(
            {
                "season": 2024,
                "week": week,
                "game_id": f"kc_{week}",
                "posteam": "KC",
                "wp": 0.5,
                "qtr": 2,
                "game_seconds_remaining": 3200 - (idx * 34),
                "pass": 0,
                "pass_attempt": 0,
                "rush": 1,
                "xpass": 0.45,
                "rusher_player_id": "gsis_rb",
                "rusher_player_name": "KC RB",
                "rushing_yards": 4,
                "rushing_tds": 1 if idx == 0 else 0,
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
