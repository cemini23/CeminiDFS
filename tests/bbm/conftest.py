"""Shared fixtures for BBM tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ceminidfs.bbm.ledger import init_db, sync_players_from_registry
from ceminidfs.bbm.registry import build_seed_registry


@pytest.fixture
def bbm_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a temporary BBM database for testing."""
    db_path = tmp_path / "bbm7.db"
    registry_path = tmp_path / "player_registry.json"
    monkeypatch.setattr("ceminidfs.bbm.ledger.get_db_path", lambda: db_path)
    monkeypatch.setattr(
        "ceminidfs.bbm.registry.get_registry_path",
        lambda data_dir=None: registry_path,
    )
    init_db(db_path)
    registry = build_seed_registry()
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    sync_players_from_registry(registry, db_path)
    return db_path


@pytest.fixture(autouse=True)
def isolated_schedule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Pin schedule lookups to the hardcoded fallback (no real cache leaks into tests)."""
    from ceminidfs.bbm import schedule

    monkeypatch.setattr(
        schedule,
        "get_schedule_cache_path",
        lambda season=schedule.DEFAULT_SEASON: tmp_path / f"schedule_{season}.json",
    )
    schedule.clear_schedule_memo()
    yield tmp_path
    schedule.clear_schedule_memo()
