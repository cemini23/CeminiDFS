import csv
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.pipeline import backtest, distributions, engine


EXPECTED_HEADER = "player_name,player_key,stat_type,median,sd,family"


def test_parse_season_week():
    assert distributions.parse_season_week("2026_5") == (2026, 5)
    assert distributions.parse_season_week("2025-17") == (2025, 17)
    with pytest.raises(ValueError):
        distributions.parse_season_week("not-a-week")


def test_write_distributions_csv_schema_is_exact(tmp_path: Path):
    frame = pd.DataFrame(
        [
            {
                "player_name": "Patrick Mahomes",
                "player_key": "patrick mahomes|kc|QB",
                "player_id": "gsis_mahomes",
                "team": "KC",
                "stat_type": "pass_yds",
                "median": 271.5,
                "sd": 95.0,
                "family": "lognormal",
            }
        ]
    )

    path = distributions.write_distributions_csv(frame, tmp_path / "dist.csv")
    header = path.read_text(encoding="utf-8").splitlines()[0]

    assert header == EXPECTED_HEADER
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert rows[0]["family"] == "lognormal"
    assert rows[0]["stat_type"] in distributions.STAT_TYPES


def test_build_week_distributions_synthetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pbp = _season_pbp_with_week4()
    week_dir = _write_week_cache(tmp_path)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)
    monkeypatch.setattr(backtest, "load_season_pbp", lambda season: pbp)

    frame = distributions.build_week_distributions(2024, 4)

    assert list(frame.columns) == list(distributions._INTERNAL_COLUMNS)
    assert set(frame["stat_type"]).issubset(set(distributions.STAT_TYPES))
    assert (frame["family"] == "lognormal").all()
    assert (frame["median"] > 0).all()
    assert (frame["sd"] > 0).all()
    # Stat units, not fantasy points: a passing median is on the yards scale.
    assert frame.loc[frame["stat_type"] == "pass_yds", "median"].max() > 50


def test_build_week_distributions_is_reproducible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pbp = _season_pbp_with_week4()
    week_dir = _write_week_cache(tmp_path)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)
    monkeypatch.setattr(backtest, "load_season_pbp", lambda season: pbp)

    first = distributions.build_week_distributions(2024, 4)
    second = distributions.build_week_distributions(2024, 4)

    assert first.equals(second)


def test_export_distributions_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from ceminidfs import cli

    pbp = _season_pbp_with_week4()
    week_dir = _write_week_cache(tmp_path)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)
    monkeypatch.setattr(backtest, "load_season_pbp", lambda season: pbp)

    out = tmp_path / "d.csv"
    exit_code = cli.main(["export-distributions", "--week", "2024_4", "--out", str(out)])

    assert exit_code == 0
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert header == EXPECTED_HEADER


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
    pbp = _season_pbp_with_week4()
    pbp.to_parquet(week_dir / "pbp.parquet", index=False)
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
