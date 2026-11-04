"""Practice flow and pivot behavior tests for WS-B fixes."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from ceminidfs.bbm.archetype import _is_elite_rb_tier_empty, _is_rb_run_happening
from ceminidfs.bbm.ledger import (
    complete_draft,
    create_draft,
    get_player_by_id,
    get_players_by_name,
    list_available_players,
    record_pick,
    record_taken,
)
from ceminidfs.bbm.models import Archetype, DraftState, DraftStatus, PivotResult, Player, Roster
from ceminidfs.bbm.practice import _resume_state
from ceminidfs.bbm.recommender import _is_w17_bringback, _prefilter_candidates
from ceminidfs.bbm.session import archetype_gap_pct, get_recommendations, get_recommendations_meta


@pytest.fixture(autouse=True)
def _patch_session_db_path(bbm_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ceminidfs.bbm.session.get_db_path", lambda: bbm_db)


def _player(name: str, position: str, team: str, adp: float, player_id: str | None = None) -> Player:
    return Player(
        player_id=player_id or f"bbm:{name.lower().replace(' ', '-')}",
        name=name,
        merge_name=name.lower(),
        position=position,
        team=team,
        bye_week=5,
        adp=adp,
    )


def test_resume_state_includes_room_taken(bbm_db: Path) -> None:
    draft_id = "practice-r1"
    create_draft(draft_id, slot=4, archetype="A", db_path=bbm_db, is_practice=True)

    top_players = list_available_players(limit=20, db_path=bbm_db)
    assert len(top_players) >= 12
    record_pick(draft_id, 1, 4, top_players[0]["player_id"], is_mine=True, db_path=bbm_db)

    for idx, player in enumerate(top_players[1:12], start=1):
        record_taken(draft_id, 1, idx, player["player_id"], db_path=bbm_db)

    next_pick, taken_ids = _resume_state(draft_id)
    assert next_pick == 13
    assert len(taken_ids) == 12


def test_practice_draft_flagged(bbm_db: Path) -> None:
    draft_id = "practice-flagged"
    create_draft(draft_id, slot=3, archetype="B", db_path=bbm_db, is_practice=True)

    conn = sqlite3.connect(bbm_db)
    is_practice = conn.execute(
        "SELECT is_practice FROM drafts WHERE draft_id = ?",
        (draft_id,),
    ).fetchone()[0]
    conn.close()
    assert is_practice == 1


def test_archetype_gap_excludes_practice(bbm_db: Path) -> None:
    baseline_gap = archetype_gap_pct("A")
    draft_id = "practice-gap"
    create_draft(draft_id, slot=1, archetype="A", db_path=bbm_db, is_practice=True)
    complete_draft(draft_id, db_path=bbm_db)
    assert archetype_gap_pct("A") == baseline_gap


def test_rb_run_check_real() -> None:
    round_five_empty = [_player("WR One", "WR", "KC", 20), _player("TE One", "TE", "DEN", 45)]
    assert _is_rb_run_happening(round_five_empty, round_num=5) is True

    round_five_full = [
        _player("RB1", "RB", "KC", 20),
        _player("RB2", "RB", "BUF", 24),
        _player("RB3", "RB", "MIA", 35),
        _player("RB4", "RB", "ATL", 50),
        _player("RB5", "RB", "LAR", 58),
    ]
    assert _is_rb_run_happening(round_five_full, round_num=5) is False

    round_two_full = [
        _player("RB1", "RB", "KC", 20),
        _player("RB2", "RB", "BUF", 22),
        _player("RB3", "RB", "MIA", 24),
    ]
    assert _is_rb_run_happening(round_two_full, round_num=2) is False


def test_prefilter_excludes_fa_and_stub() -> None:
    roster = Roster(players=[], draft_position=4, current_round=8)
    draft_state = DraftState(
        draft_id="prefilter-test",
        slot=4,
        archetype=Archetype.B,
        status=DraftStatus.IN_PROGRESS,
        roster=roster,
        taken_players=set(),
        draft_date=datetime.now(),
    )

    normal = _player("Normal WR", "WR", "KC", 60, "bbm:normal-wr")
    fa_player = _player("FA WR", "WR", "FA", 61, "bbm:fa-wr")
    stub = _player("Stub WR", "WR", "DEN", 62, "stub:stub-wr")

    filtered = _prefilter_candidates([normal, fa_player, stub], draft_state, roster, Archetype.B)
    assert [p.player_id for p in filtered] == ["bbm:normal-wr"]


def test_w17_bringback_uses_schedule() -> None:
    candidate = _player("Candidate", "WR", "KC", 70)
    roster_yes = Roster(players=[_player("Opponent", "WR", "DEN", 80)], draft_position=4, current_round=10)
    roster_no = Roster(players=[_player("Non Opponent", "WR", "CAR", 80)], draft_position=4, current_round=10)

    assert _is_w17_bringback(candidate, roster_yes) is True
    assert _is_w17_bringback(candidate, roster_no) is False


def test_advisory_pivot_keeps_primary_archetype(
    bbm_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft_id = "practice-advisory-primary"
    create_draft(draft_id, slot=4, archetype="D", db_path=bbm_db, is_practice=True)

    captured: dict[str, Archetype | None] = {"archetype": None}

    def forced_pivot(*args: object, **kwargs: object) -> PivotResult:
        del args, kwargs
        return PivotResult(new_archetype=Archetype.B, warning="forced", trigger_reason="test")

    def capture_recs(
        draft_state: DraftState, *args: object, **kwargs: object
    ) -> list[object]:
        del args, kwargs
        captured["archetype"] = draft_state.archetype
        return []

    monkeypatch.setattr("ceminidfs.bbm.session.pivot_state_machine", forced_pivot)
    monkeypatch.setattr("ceminidfs.bbm.session.recommend_top3", capture_recs)

    meta = get_recommendations_meta(6, 64, "", draft_id)
    assert captured["archetype"] == Archetype.D
    assert meta["pivot_warning"] is not None
    assert "advisory only" in meta["pivot_warning"]
    assert meta["pivot_to"] == "B"
    assert meta["recommendations"] == []


def test_get_recommendations_wrapper_attaches_warning(
    bbm_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft_id = "practice-wrapper-warning"
    create_draft(draft_id, slot=4, archetype="D", db_path=bbm_db, is_practice=True)

    top = list_available_players(limit=1, db_path=bbm_db)[0]
    player = _player(top["name"], top["position"], top["team"], top["adp"], top["player_id"])

    def forced_pivot(*args: object, **kwargs: object) -> PivotResult:
        del args, kwargs
        return PivotResult(new_archetype=Archetype.B, warning="forced", trigger_reason="test")

    class _Rec:
        def __init__(self, p: Player) -> None:
            self.player = p
            self.is_stack_opportunity = False
            self.warnings = []
            self.score = 1.0

    monkeypatch.setattr("ceminidfs.bbm.session.pivot_state_machine", forced_pivot)
    monkeypatch.setattr("ceminidfs.bbm.session.recommend_top3", lambda *args, **kwargs: [_Rec(player)])

    results = get_recommendations(6, 64, "", draft_id, limit=1)
    assert len(results) == 1
    assert results[0]["pivot_warning"] is not None


def test_elite_rb_exact_no_substring_false_positive() -> None:
    assert _is_elite_rb_tier_empty([_player("Tyler Taylor", "RB", "CIN", 180)]) is True
    assert _is_elite_rb_tier_empty([_player("Jonathan Taylor", "RB", "IND", 8)]) is False
    assert _is_elite_rb_tier_empty([_player("Jonathan Taylor", "WR", "IND", 8)]) is True


def test_elite_rb_matches_normalized_merge_name() -> None:
    assert _is_elite_rb_tier_empty([_player("De'Von Achane", "RB", "MIA", 12)]) is False


def test_get_player_by_id_roundtrip(bbm_db: Path) -> None:
    puka_id = get_players_by_name("Puka Nacua", db_path=bbm_db)[0]["player_id"]
    puka = get_player_by_id(puka_id, db_path=bbm_db)
    assert puka is not None
    assert puka["name"] == "Puka Nacua"
    assert get_player_by_id("bbm:missing", db_path=bbm_db) is None


def _stub_practice_deps(monkeypatch: pytest.MonkeyPatch, inputs: list[str]) -> dict[str, list]:
    """Replace every ledger call so the interactive loop runs with no DB."""
    import ceminidfs.bbm.practice as practice

    calls: dict[str, list] = {"picks": [], "taken": [], "complete": 0}
    pool = [
        {"player_id": f"bbm:p{i}", "name": f"P{i}", "position": "WR", "team": "KC", "adp": i}
        for i in range(1, 40)
    ]
    fake_player = {"player_id": "bbm:p1", "name": "P1", "position": "WR", "team": "KC"}

    monkeypatch.setattr(practice, "archetype_header", lambda _a: "ARCH")
    monkeypatch.setattr(practice, "create_draft", lambda *a, **k: None)
    monkeypatch.setattr(practice, "get_draft_state", lambda _d: None)
    monkeypatch.setattr(practice, "get_taken_player_ids", lambda _d: set())
    monkeypatch.setattr(practice, "count_room_taken", lambda _d: 0)
    monkeypatch.setattr(practice, "get_recommendations", lambda *a, **k: [])
    monkeypatch.setattr(practice, "list_available_players", lambda **k: list(pool))
    monkeypatch.setattr(practice, "resolve_player_query", lambda _q: dict(fake_player))
    monkeypatch.setattr(practice, "get_last_ambiguous_matches", lambda: [])
    monkeypatch.setattr(
        practice, "ensure_player_stub",
        lambda q: {"player_id": f"stub:{q.lower()}", "name": q, "position": "WR", "team": "FA"},
    )
    monkeypatch.setattr(practice, "record_pick", lambda *a, **k: calls["picks"].append(a))
    monkeypatch.setattr(practice, "record_taken", lambda *a, **k: calls["taken"].append(a))
    monkeypatch.setattr(
        practice, "complete_draft",
        lambda *a, **k: calls.__setitem__("complete", calls["complete"] + 1),
    )
    queue = iter(inputs)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(queue))
    return calls


def test_run_practice_draft_picks_then_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    import ceminidfs.bbm.practice as practice

    calls = _stub_practice_deps(monkeypatch, ["p P1"])

    draft_id = practice.run_practice_draft(slot=1, archetype="A", rounds=1)

    assert draft_id.startswith("practice-")
    assert len(calls["picks"]) == 1
    assert calls["picks"][0][3] == "bbm:p1"
    assert len(calls["taken"]) == 11  # opponents fill picks 2-12
    assert calls["complete"] == 1


def test_run_practice_draft_taken_unknown_creates_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    import ceminidfs.bbm.practice as practice

    calls = _stub_practice_deps(monkeypatch, ["t Ghost"])
    monkeypatch.setattr(practice, "resolve_player_query", lambda _q: None)

    practice.run_practice_draft(slot=1, archetype="A", rounds=1)

    assert calls["taken"][0][3] == "stub:ghost"
    assert len(calls["taken"]) == 12


def test_run_practice_draft_quit_stops_before_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    import ceminidfs.bbm.practice as practice

    calls = _stub_practice_deps(monkeypatch, ["quit"])

    draft_id = practice.run_practice_draft(slot=1, archetype="A", rounds=1)

    assert draft_id.startswith("practice-")
    assert calls["picks"] == []
    assert calls["taken"] == []
    assert calls["complete"] == 0
