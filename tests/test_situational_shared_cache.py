"""Tests for the situational shared cache writer."""

from __future__ import annotations

import hashlib
import json

import pandas as pd

from ceminidfs.situational.shared_cache import (
    DEFENSE_COUNTERPART_NAME,
    GAME_CONTEXT_NAME,
    PLAYER_TELEMETRY_NAME,
    write_shared_cache,
)

PARQUET_NAMES = (PLAYER_TELEMETRY_NAME, DEFENSE_COUNTERPART_NAME, GAME_CONTEXT_NAME)


def test_write_shared_cache(tmp_path):
    players = pd.DataFrame(
        {"player_id": ["p1", "p2", "p3"], "season": [2026, 2026, 2026], "week": [4, 5, 5]}
    )
    defense = pd.DataFrame(
        {"defense_team": ["A", "B"], "season": [2026, 2026], "week": [4, 5]}
    )
    games = pd.DataFrame({"game_id": ["g1"], "season": [2026], "week": [5]})

    manifest = write_shared_cache(
        tmp_path,
        players=players,
        defense=defense,
        games=games,
        season=2026,
        week=6,
        max_source_week=5,
    )

    assert manifest["max_source_week"] == 5
    assert manifest["season"] == 2026
    assert manifest["week"] == 6

    for name in PARQUET_NAMES:
        path = tmp_path / name
        assert path.exists()
        assert manifest["files"][name]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()

    assert manifest["files"][PLAYER_TELEMETRY_NAME]["rows"] == 3
    assert manifest["files"][DEFENSE_COUNTERPART_NAME]["rows"] == 2
    assert manifest["files"][GAME_CONTEXT_NAME]["rows"] == 1

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest
