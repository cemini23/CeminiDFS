"""Tests for `ceminidfs bbm preflight` readiness checklist."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from ceminidfs.bbm import cli, schedule
from ceminidfs.bbm.ledger import complete_draft, create_draft


def test_preflight_warns_registry_below_target(bbm_db: Path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "ensure_initialized", lambda: None)
    exit_code = cli._cmd_preflight(Namespace())
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "[WARN] Registry:" in captured.out
    assert "target 240" in captured.out
    assert "refresh-adp" in captured.out


def test_preflight_ok_at_target(bbm_db: Path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "ensure_initialized", lambda: None)
    monkeypatch.setattr(cli, "load_registry", lambda: {"players": [{}] * 240})
    cli._cmd_preflight(Namespace())
    captured = capsys.readouterr()

    assert "[ok]   Registry: 240 players (target 240)" in captured.out


def test_preflight_counts_completed_practice_drafts(bbm_db: Path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "ensure_initialized", lambda: None)
    cli._cmd_preflight(Namespace())
    captured = capsys.readouterr()
    assert "[WARN] No completed practice draft" in captured.out

    create_draft("practice-x", 4, is_practice=True)
    complete_draft("practice-x")

    cli._cmd_preflight(Namespace())
    captured = capsys.readouterr()
    assert "[ok]   Practice drafts completed: 1" in captured.out


def test_preflight_lists_stale_in_progress_drafts(bbm_db: Path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "ensure_initialized", lambda: None)
    create_draft("stale-1", 7, is_practice=False)

    exit_code = cli._cmd_preflight(Namespace())
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "stale-1" in captured.out
    assert "[WARN] Stale in-progress drafts (1):" in captured.out
    assert "abandon --draft-id" in captured.out


def test_preflight_reports_schedule_source(bbm_db: Path, monkeypatch, capsys, isolated_schedule: Path):
    monkeypatch.setattr(cli, "ensure_initialized", lambda: None)
    cli._cmd_preflight(Namespace())
    captured = capsys.readouterr()

    assert "hardcoded 2026 fallback" in captured.out
    assert "refresh-schedule" in captured.out

    cache_path = isolated_schedule / "schedule_2026.json"
    cache_data = {
        "season": 2026,
        "bye_weeks": {team: 7 for team in schedule.BYE_WEEKS_2026},
        "week17_matchups": [["KC", "LV"]] * 14,
    }
    cache_path.write_text(json.dumps(cache_data), encoding="utf-8")
    schedule.clear_schedule_memo()

    cli._cmd_preflight(Namespace())
    captured = capsys.readouterr()
    assert "Schedule source: cache" in captured.out


def test_preflight_prints_smoke_hint(bbm_db: Path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "ensure_initialized", lambda: None)
    cli._cmd_preflight(Namespace())
    captured = capsys.readouterr()
    assert "pytest tests/bbm -q" in captured.out


def test_preflight_exit_zero_when_all_green(bbm_db: Path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "ensure_initialized", lambda: None)
    monkeypatch.setattr(cli, "load_registry", lambda: {"players": [{}] * 240})
    create_draft("practice-good", 4, is_practice=True)
    complete_draft("practice-good")

    exit_code = cli._cmd_preflight(Namespace())
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Result: READY" in captured.out
