"""Tests for K138 ESPN injury adjunct."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data import espn


class _FakePlayer:
    def __init__(self, name: str, injury_status: str = "") -> None:
        self.name = name
        self.injuryStatus = injury_status


class _FakeTeam:
    def __init__(self, players: list[_FakePlayer]) -> None:
        self.roster = players


class _FakeLeague:
    def __init__(self, teams: list[_FakeTeam]) -> None:
        self.teams = teams


def test_fetch_injury_map_parses_roster():
    football = MagicMock()
    football.League.return_value = _FakeLeague(
        [
            _FakeTeam(
                [
                    _FakePlayer("Patrick Mahomes", "ACTIVE"),
                    _FakePlayer("Travis Kelce", "QUESTIONABLE"),
                ]
            )
        ]
    )
    espn_api = MagicMock()
    espn_api.football = football

    with patch.dict(sys.modules, {"espn_api": espn_api, "espn_api.football": football}):
        mapping = espn.fetch_injury_map(123, 2025)

    assert "travis kelce" in mapping
    assert mapping["travis kelce"] == "QUESTIONABLE"
    assert "patrick mahomes" not in mapping


def test_apply_espn_injury_overlay_fills_empty_status():
    rows = [{"name": "Travis Kelce", "team": "KC", "injury_status": ""}]
    lookup = {"travis kelce": "QUESTIONABLE"}
    config = {"espn_adjunct": {"enabled": True, "league_id": 1, "year": 2025}}

    enriched = espn.apply_espn_injury_overlay(rows, config=config, injury_map=lookup)
    assert enriched[0]["injury_status"] == "QUESTIONABLE"
    assert enriched[0]["injury_source"] == "espn_adjunct"


def test_apply_espn_injury_overlay_skips_existing_status():
    rows = [{"name": "Travis Kelce", "injury_status": "OUT"}]
    lookup = {"travis kelce": "QUESTIONABLE"}
    config = {"espn_adjunct": {"enabled": True}}

    enriched = espn.apply_espn_injury_overlay(rows, config=config, injury_map=lookup)
    assert enriched[0]["injury_status"] == "OUT"
    assert "injury_source" not in enriched[0]


def test_probe_league_summary():
    lookup = {"travis kelce": "QUESTIONABLE", "patrick mahomes": ""}
    with patch.object(espn, "fetch_injury_map", return_value=lookup):
        summary = espn.probe_league(99, 2025)
    assert summary["league_id"] == 99
    assert summary["roster_players"] == 2
    assert summary["injured_or_flagged"] == 1
