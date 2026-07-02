"""Batch combo exposure and record_taken idempotency tests (WS-B research backlog)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from ceminidfs.bbm import ledger
from ceminidfs.bbm.ledger import (
    combo_exposures_for_roster,
    combo_pct,
    complete_draft,
    create_draft,
    record_pick,
    record_taken,
    sync_players_from_registry,
    undo_last_action,
)
from ceminidfs.bbm.models import Archetype, DraftState, DraftStatus, Player, Roster
from ceminidfs.bbm.recommender import _prefilter_candidates
from ceminidfs.bbm.registry import build_seed_registry


def _pair_players(bbm_db: Path) -> tuple[str, str, str]:
    """Return (player_a, player_b, unpaired) ids from seed registry."""
    sync_players_from_registry(build_seed_registry(), bbm_db)
    conn = sqlite3.connect(bbm_db)
    rows = conn.execute(
        "SELECT player_id FROM players_dim WHERE player_id LIKE 'bbm:%' ORDER BY adp LIMIT 3"
    ).fetchall()
    conn.close()
    assert len(rows) >= 3
    return rows[0][0], rows[1][0], rows[2][0]


def test_combo_exposures_batch_matches_combo_pct(bbm_db: Path) -> None:
    player_a, player_b, unpaired = _pair_players(bbm_db)

    for i in range(3):
        draft_id = f"combo-batch-complete-{i}"
        create_draft(draft_id, slot=1, archetype="A", db_path=bbm_db)
        record_pick(draft_id, 1, 1, player_a, is_mine=True, db_path=bbm_db)
        record_pick(draft_id, 2, 24, player_b, is_mine=True, db_path=bbm_db)
        complete_draft(draft_id, db_path=bbm_db)

    for i in range(2):
        draft_id = f"combo-batch-progress-{i}"
        create_draft(draft_id, slot=1, archetype="A", db_path=bbm_db)
        record_pick(draft_id, 1, 1, player_a, is_mine=True, db_path=bbm_db)
        record_pick(draft_id, 2, 24, player_b, is_mine=True, db_path=bbm_db)

    batch = combo_exposures_for_roster([player_a], [player_b, unpaired], db_path=bbm_db)
    expected = combo_pct(player_a, player_b, db_path=bbm_db)["current"]
    assert batch[(player_a, player_b)] == pytest.approx(expected)
    assert (player_a, unpaired) not in batch


def test_combo_exposures_excludes_practice_drafts(bbm_db: Path) -> None:
    player_a, player_b, _ = _pair_players(bbm_db)

    create_draft("practice-combo-only", slot=1, archetype="A", db_path=bbm_db, is_practice=True)
    record_pick("practice-combo-only", 1, 1, player_a, is_mine=True, db_path=bbm_db)
    record_pick("practice-combo-only", 2, 24, player_b, is_mine=True, db_path=bbm_db)
    complete_draft("practice-combo-only", db_path=bbm_db)

    batch = combo_exposures_for_roster([player_a], [player_b], db_path=bbm_db)
    assert batch.get((player_a, player_b), 0.0) == 0.0


def test_combo_exposures_empty_inputs_no_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> None:
        raise AssertionError("connect_db should not be called for empty inputs")

    monkeypatch.setattr(ledger, "connect_db", _raise)
    assert combo_exposures_for_roster([], ["x"]) == {}
    assert combo_exposures_for_roster(["x"], []) == {}


def test_combo_exposures_dedupes_input_ids(bbm_db: Path) -> None:
    player_a, player_b, _ = _pair_players(bbm_db)
    create_draft("combo-dedupe", slot=1, archetype="A", db_path=bbm_db)
    record_pick("combo-dedupe", 1, 1, player_a, is_mine=True, db_path=bbm_db)
    record_pick("combo-dedupe", 2, 24, player_b, is_mine=True, db_path=bbm_db)
    complete_draft("combo-dedupe", db_path=bbm_db)

    unique = combo_exposures_for_roster([player_a], [player_b], db_path=bbm_db)
    duped = combo_exposures_for_roster([player_a, player_a], [player_b, player_b], db_path=bbm_db)
    assert duped == unique


def test_prefilter_single_connection_for_combo_checks(
    bbm_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connections = {"count": 0}
    real_connect = ledger.connect_db

    def counting_connect(*args: object, **kwargs: object):
        connections["count"] += 1
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(ledger, "connect_db", counting_connect)

    roster_player = Player(
        player_id="bbm:jahmyr-gibbs",
        name="Jahmyr Gibbs",
        merge_name="jahmyr gibbs",
        position="RB",
        team="DET",
        bye_week=5,
        adp=3.5,
    )
    roster = Roster(players=[roster_player], draft_position=4, current_round=8)
    draft_state = DraftState(
        draft_id="combo-conn-test",
        slot=4,
        archetype=Archetype.B,
        status=DraftStatus.IN_PROGRESS,
        roster=roster,
        taken_players=set(),
        draft_date=datetime.now(),
    )
    candidates = [
        Player(
            player_id=f"bbm:candidate-{i}",
            name=f"Candidate {i}",
            merge_name=f"candidate {i}",
            position="WR",
            team="KC",
            bye_week=6,
            adp=50.0 + i,
        )
        for i in range(5)
    ]

    _prefilter_candidates(candidates, draft_state, roster, Archetype.B)
    assert connections["count"] == 1


def test_prefilter_blocks_candidate_at_combo_cap(
    bbm_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    player_a, player_b, control = _pair_players(bbm_db)

    create_draft("combo-cap-block", slot=1, archetype="A", db_path=bbm_db)
    record_pick("combo-cap-block", 1, 1, player_a, is_mine=True, db_path=bbm_db)
    record_pick("combo-cap-block", 2, 24, player_b, is_mine=True, db_path=bbm_db)
    complete_draft("combo-cap-block", db_path=bbm_db)

    create_draft("combo-cap-block-2", slot=1, archetype="A", db_path=bbm_db)
    record_pick("combo-cap-block-2", 1, 1, player_a, is_mine=True, db_path=bbm_db)
    record_pick("combo-cap-block-2", 2, 24, player_b, is_mine=True, db_path=bbm_db)
    complete_draft("combo-cap-block-2", db_path=bbm_db)

    monkeypatch.setattr("ceminidfs.bbm.recommender.COMBO_PAIR_CAP", 0.01)

    roster = Roster(
        players=[
            Player(
                player_id=player_a,
                name="Roster RB",
                merge_name="roster rb",
                position="RB",
                team="DET",
                bye_week=5,
                adp=10.0,
            )
        ],
        draft_position=4,
        current_round=10,
    )
    draft_state = DraftState(
        draft_id="cap-filter",
        slot=4,
        archetype=Archetype.A,
        status=DraftStatus.IN_PROGRESS,
        roster=roster,
        taken_players=set(),
        draft_date=datetime.now(),
    )
    blocked = Player(
        player_id=player_b,
        name="Blocked WR",
        merge_name="blocked wr",
        position="WR",
        team="CIN",
        bye_week=7,
        adp=20.0,
    )
    allowed = Player(
        player_id=control,
        name="Control WR",
        merge_name="control wr",
        position="WR",
        team="MIN",
        bye_week=6,
        adp=80.0,
    )

    filtered = _prefilter_candidates([blocked, allowed], draft_state, roster, Archetype.A)
    assert [p.player_id for p in filtered] == [control]


def test_record_taken_duplicate_returns_inserted_false(bbm_db: Path) -> None:
    player_a, _, _ = _pair_players(bbm_db)
    draft_id = "taken-dedupe"
    create_draft(draft_id, slot=4, archetype="A", db_path=bbm_db)

    first = record_taken(draft_id, 1, 1, player_a, db_path=bbm_db)
    second = record_taken(draft_id, 1, 2, player_a, db_path=bbm_db)
    assert first["inserted"] is True
    assert second["inserted"] is False

    conn = sqlite3.connect(bbm_db)
    count = conn.execute(
        "SELECT COUNT(*) FROM room_taken WHERE draft_id = ? AND player_id = ?",
        (draft_id, player_a),
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_record_taken_duplicate_no_action_log_growth(bbm_db: Path) -> None:
    player_a, _, _ = _pair_players(bbm_db)
    draft_id = "taken-log-dedupe"
    create_draft(draft_id, slot=4, archetype="A", db_path=bbm_db)

    record_taken(draft_id, 1, 1, player_a, db_path=bbm_db)
    record_taken(draft_id, 1, 2, player_a, db_path=bbm_db)

    conn = sqlite3.connect(bbm_db)
    log_count = conn.execute(
        "SELECT COUNT(*) FROM action_log WHERE draft_id = ? AND action_type = 'taken'",
        (draft_id,),
    ).fetchone()[0]
    conn.close()
    assert log_count == 1

    undone = undo_last_action(draft_id, db_path=bbm_db)
    assert undone is not None
    assert undone["undone"] == "taken"

    conn = sqlite3.connect(bbm_db)
    taken_left = conn.execute(
        "SELECT COUNT(*) FROM room_taken WHERE draft_id = ?",
        (draft_id,),
    ).fetchone()[0]
    conn.close()
    assert taken_left == 0
    assert undo_last_action(draft_id, db_path=bbm_db) is None
