import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data.rosters import enrich_roster_positions, position_lookup_for_week
from ceminidfs.models.usage import refine_skill_position
from ceminidfs.models.usage_settings import UsageSettings
from ceminidfs.pipeline.backtest import resolve_weather_for_week
from ceminidfs.pipeline.benchmark_replay import find_benchmark_csv


def test_usage_settings_from_config():
    cfg = {
        "usage": {
            "share_weights": [0.4, 0.4, 0.2],
            "min_two_week_qb_pass_attempts": 30,
            "rb_committee_size": 2,
        }
    }
    settings = UsageSettings.from_config(cfg)
    assert settings.share_weights == (0.4, 0.4, 0.2)
    assert settings.min_two_week_qb_pass_attempts == 30
    assert settings.rb_committee_size == 2


def test_refine_skill_position_te_heuristic():
    assert refine_skill_position(0, 1, 8, 40.0) == "TE"
    assert refine_skill_position(0, 1, 8, 40.0, roster_position="TE") == "TE"
    assert refine_skill_position(0, 20, 3, 90.0) == "RB"


def test_refine_skill_position_wr_deep():
    assert refine_skill_position(0, 0, 10, 120.0) == "WR"


def test_enrich_roster_positions_from_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    pd.DataFrame(
        [
            {"season": 2024, "week": 4, "gsis_id": "te1", "position": "TE", "team": "KC"},
        ]
    ).to_parquet(cache / "rosters_2024.parquet", index=False)
    monkeypatch.setattr("ceminidfs.data.rosters._cache_dir", lambda: cache)

    roster = pd.DataFrame(
        [{"player_id": "te1", "player_name": "Tight End", "team": "KC", "position": ""}]
    )
    enriched = enrich_roster_positions(roster, season=2024, week=4)
    assert enriched.iloc[0]["position"] == "TE"
    assert position_lookup_for_week(2024, 4)["te1"] == "TE"


def test_resolve_weather_for_week_from_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    week_dir = tmp_path / "2024" / "week_4"
    week_dir.mkdir(parents=True)
    weather = pd.DataFrame([{"home_team": "KC", "wind_speed_10m_mph": 12.0}])
    weather.to_parquet(week_dir / "weather.parquet", index=False)
    monkeypatch.setattr("ceminidfs.pipeline.engine.week_cache_dir", lambda season, week: week_dir)

    frame = resolve_weather_for_week(2024, 4, config={"skip_weather": False})
    assert frame is not None
    assert not frame.empty
    assert float(frame.iloc[0]["wind_speed_10m_mph"]) == 12.0


def test_find_benchmark_csv(tmp_path: Path):
    (tmp_path / "stokastic_w5_export.csv").write_text("name,team\n", encoding="utf-8")
    found = find_benchmark_csv(tmp_path, 5)
    assert found is not None
    assert found.name == "stokastic_w5_export.csv"
    assert find_benchmark_csv(tmp_path, 9) is None
