"""WS-1 tests: ADP merge default and dynamic season schedule (nflreadpy cache)."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest

from ceminidfs.bbm import cli, schedule
from ceminidfs.bbm.normalize_adp import AdpMergeResult, merge_adp_csv
from ceminidfs.bbm.registry import build_seed_registry
from ceminidfs.bbm.schedule import (
    _active_schedule,
    are_opponents_week17,
    clear_schedule_memo,
    fetch_season_schedule,
    get_bye_week,
    load_schedule_cache,
)


@pytest.fixture
def unmatched_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "adp.csv"
    csv_path.write_text("name,adp,pos\nTest Prospect,145.0,WR\n", encoding="utf-8")
    return csv_path


def test_merge_adp_default_skips_unmatched(unmatched_csv: Path):
    registry = build_seed_registry()
    result = merge_adp_csv(unmatched_csv, registry)

    assert result.added == 0
    assert result.matched == 0
    assert result.unmatched == ["Test Prospect"]
    assert not any(
        p.get("name") == "Test Prospect" and p.get("team") == "FA"
        for p in registry["players"]
    )


def test_merge_adp_opt_in_still_adds(unmatched_csv: Path):
    registry = build_seed_registry()
    result = merge_adp_csv(unmatched_csv, registry, add_unmatched=True)

    assert result.added == 1
    added_player = next(p for p in registry["players"] if p["name"] == "Test Prospect")
    assert added_player["team"] == "FA"
    assert added_player["signal"] == "NEUTRAL"


def test_refresh_registry_threads_add_unmatched(unmatched_csv: Path, monkeypatch):
    captured: dict[str, Any] = {}

    monkeypatch.setattr(cli, "ensure_initialized", lambda: None)
    monkeypatch.setattr(cli, "load_registry", lambda: {"players": []})
    monkeypatch.setattr(cli, "save_registry", lambda _registry: None)
    monkeypatch.setattr(cli, "sync_players_from_registry", lambda _registry: 0)

    def capture_merge(csv_path, registry, *, add_unmatched=False):
        captured["csv_path"] = csv_path
        captured["add_unmatched"] = add_unmatched
        return AdpMergeResult(
            matched=0, exact_matched=0, fuzzy_matched=0, added=0, unmatched=[]
        )

    monkeypatch.setattr(cli, "merge_adp_csv", capture_merge)

    result = cli._refresh_registry(unmatched_csv)
    assert result is not None
    assert captured["add_unmatched"] is False

    captured.clear()
    result = cli._refresh_registry(unmatched_csv, add_unmatched=True)
    assert result is not None
    assert captured["add_unmatched"] is True


def test_schedule_fallback_when_no_cache(isolated_schedule: Path):
    assert get_bye_week("KC") == 5
    assert are_opponents_week17("KC", "DEN") is True
    assert are_opponents_week17("KC", "CAR") is False
    assert _active_schedule()[2] == "hardcoded"


def test_schedule_cache_overrides_hardcoded(isolated_schedule: Path):
    cache_path = isolated_schedule / "schedule_2026.json"
    bye_weeks = {team: 7 for team in schedule.BYE_WEEKS_2026}
    week17_matchups = [["KC", "LV"]] * 14
    cache_data = {
        "season": 2026,
        "bye_weeks": bye_weeks,
        "week17_matchups": week17_matchups,
    }
    cache_path.write_text(__import__("json").dumps(cache_data), encoding="utf-8")
    clear_schedule_memo()

    assert get_bye_week("KC") == 7
    assert are_opponents_week17("KC", "LV") is True
    assert are_opponents_week17("KC", "DEN") is False
    assert _active_schedule()[2] == "cache"


def test_schedule_cache_rejected_when_incomplete(isolated_schedule: Path):
    cache_path = isolated_schedule / "schedule_2026.json"
    cache_data = {
        "season": 2026,
        "bye_weeks": {"KC": 5, "DEN": 6, "CAR": 7},
        "week17_matchups": [["KC", "DEN"]],
    }
    cache_path.write_text(__import__("json").dumps(cache_data), encoding="utf-8")
    clear_schedule_memo()

    assert load_schedule_cache(2026) is None
    assert get_bye_week("KC") == 5  # hardcoded
    assert _active_schedule()[2] == "hardcoded"


def _build_reg_schedule(teams: list[str], season: int = 2026) -> list[dict[str, Any]]:
    """Generate REG rows with exactly one bye per team and no byes in W17."""
    rows: list[dict[str, Any]] = []
    # Cycle through weeks 1-16 and 18 so every team plays in week 17.
    bye_weeks = {
        team: ((idx % 17) + 1) if idx % 17 != 16 else 18
        for idx, team in enumerate(teams)
    }
    for team in teams:
        for week in range(1, 19):
            if week == bye_weeks[team]:
                continue
            rows.append(
                {
                    "game_type": "REG",
                    "season": season,
                    "week": week,
                    "home_team": team,
                    "away_team": f"OPP{week:02d}",
                }
            )
    return rows


def test_fetch_season_schedule_derives_byes_and_w17(monkeypatch):
    teams = [f"T{i:02d}" for i in range(1, 33)]
    bye_weeks = {
        team: ((idx % 17) + 1) if idx % 17 != 16 else 18
        for idx, team in enumerate(teams)
    }
    rows = _build_reg_schedule(teams)
    rows.append(
        {
            "game_type": "POST",
            "season": 2026,
            "week": 18,
            "home_team": "T01",
            "away_team": "T02",
        }
    )

    class FakeModule:
        @staticmethod
        def load_schedules(season=2026, seasons=None):
            assert season == 2026 or seasons == 2026
            return rows

    monkeypatch.setattr(schedule, "_require_nflreadpy", lambda: FakeModule())

    data = fetch_season_schedule(2026)
    assert data["season"] == 2026
    assert data["bye_weeks"] == bye_weeks
    assert len(data["week17_matchups"]) == len(teams)
    assert all(pair[0].startswith("OPP") and pair[1] in teams for pair in data["week17_matchups"])


def test_fetch_season_schedule_rejects_incomplete(monkeypatch):
    teams = ["T01", "T02", "T03", "T04"]
    rows = _build_reg_schedule(teams)

    class FakeModule:
        @staticmethod
        def load_schedules(season=2026, seasons=None):
            return rows

    monkeypatch.setattr(schedule, "_require_nflreadpy", lambda: FakeModule())

    with pytest.raises(ValueError, match="incomplete"):
        fetch_season_schedule(2026)


def test_fetch_missing_nflreadpy_raises_hint(monkeypatch):
    def raise_import():
        raise ImportError("Install nflreadpy with `pip install nflreadpy` to fetch schedule data.")

    monkeypatch.setattr(schedule, "_require_nflreadpy", raise_import)

    with pytest.raises(ImportError, match="pip install nflreadpy"):
        fetch_season_schedule(2026)


def test_refresh_schedule_cli_writes_cache(isolated_schedule: Path, monkeypatch):
    bye_weeks = {team: 7 for team in schedule.BYE_WEEKS_2026}
    week17_matchups = [["KC", "LV"]] * 14
    fake_data = {
        "season": 2026,
        "fetched": "2026-07-01",
        "bye_weeks": bye_weeks,
        "week17_matchups": week17_matchups,
    }
    monkeypatch.setattr(schedule, "fetch_season_schedule", lambda season: fake_data)

    exit_code = cli._cmd_refresh_schedule(Namespace(season=2026))
    assert exit_code == 0

    cache_path = isolated_schedule / "schedule_2026.json"
    assert cache_path.exists()

    clear_schedule_memo()
    assert get_bye_week("KC") == 7
