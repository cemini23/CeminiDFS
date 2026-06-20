import csv
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.pipeline import engine
from ceminidfs.pipeline.project import project_week


SAMPLE_SALARY_CSV = """\
Id,Nickname,Position,Team,Opponent,Salary,FPPG,Injury Indicator
1,Patrick Mahomes,QB,KC,BUF,8500,22.5,
2,Travis Kelce,TE,KC,BUF,7200,14.1,Q
"""


def test_build_diy_projections_synthetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    week_dir = _write_week_cache(tmp_path)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)

    stats = engine.build_diy_projections(
        2024,
        4,
        _salary_rows(),
        {"work_dir": tmp_path},
    )

    qb = stats.loc[stats["join_key"] == engine.normalize_join_key("Patrick Mahomes", "KC", "QB")].iloc[
        0
    ]
    assert qb["fd_projection"] > 0
    assert qb["dk_projection"] > 0


def test_project_week_diy_with_fetch_shaped_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Week fetch keeps season PBP; DIY projection must not starve on week filter."""
    from ceminidfs.data import fetch as fetch_module
    from ceminidfs.pipeline import engine

    cache_root = tmp_path / "cache"
    week_dir = cache_root / "2024" / "week_4"
    week_dir.mkdir(parents=True)

    pbp = _synthetic_pbp()
    pbp.loc[pbp["week"] == 4].to_parquet(week_dir / "pbp.parquet", index=False)
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
    pd.DataFrame([{"home_team": "KC"}]).to_parquet(week_dir / "weather.parquet", index=False)

    monkeypatch.setattr(fetch_module, "week_cache_dir", lambda season, week: week_dir)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)

    salary = tmp_path / "salary.csv"
    salary.write_text(SAMPLE_SALARY_CSV, encoding="utf-8")

    with pytest.raises((FileNotFoundError, ValueError)):
        project_week(2024, 4, salary, {"work_dir": tmp_path, "projection_mode": "diy"})

    pbp.to_parquet(week_dir / "pbp.parquet", index=False)
    canonical = project_week(2024, 4, salary, {"work_dir": tmp_path, "projection_mode": "diy"})
    rows = list(csv.DictReader(canonical.open(encoding="utf-8")))
    assert float(rows[0]["fd_projection"]) > 0


def test_project_week_auto_fallback_without_cache(tmp_path: Path):
    salary = tmp_path / "salary.csv"
    salary.write_text(SAMPLE_SALARY_CSV, encoding="utf-8")

    canonical = project_week(
        2024,
        4,
        salary,
        {"work_dir": tmp_path, "projection_mode": "auto", "allow_fppg_fallback": True},
    )
    rows = list(csv.DictReader(canonical.open(encoding="utf-8")))

    assert rows[0]["fd_projection"] == "22.5"


def test_project_week_diy_with_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    week_dir = _write_week_cache(tmp_path)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)
    salary = tmp_path / "salary.csv"
    salary.write_text(SAMPLE_SALARY_CSV, encoding="utf-8")

    canonical = project_week(2024, 4, salary, {"work_dir": tmp_path, "projection_mode": "diy"})
    rows = list(csv.DictReader(canonical.open(encoding="utf-8")))

    assert float(rows[0]["fd_projection"]) > 0
    assert rows[0]["fd_projection"] != "22.5"
    assert (tmp_path / "player_projection_base.parquet").is_file()


def _salary_rows() -> list[dict[str, object]]:
    return [
        {
            "name": "Patrick Mahomes",
            "player_name": "Patrick Mahomes",
            "fd_id": "1",
            "fd_position": "QB",
            "dk_id": "",
            "dk_position": "",
            "team": "KC",
        },
        {
            "name": "Travis Kelce",
            "player_name": "Travis Kelce",
            "fd_id": "2",
            "fd_position": "TE",
            "dk_id": "",
            "dk_position": "",
            "team": "KC",
        },
    ]


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
    pd.DataFrame([{"home_team": "KC", "wind_speed_10m_mph": 4.0}]).to_parquet(
        week_dir / "weather.parquet",
        index=False,
    )
    _synthetic_pbp().to_parquet(week_dir / "pbp.parquet", index=False)
    return week_dir


def _synthetic_pbp() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for week in (1, 2, 3):
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
