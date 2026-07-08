"""Tests for 2026-07-08 Golden draft failure fixes (domain, draft_id, QB gate, single-entry)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from ceminidfs.bbm.ledger import create_draft, get_draft_state, sync_players_from_registry
from ceminidfs.bbm.models import Archetype, DraftState, DraftStatus, Player, Roster, Signal
from ceminidfs.bbm.recommender import _prefilter_candidates, score_player
from ceminidfs.bbm.registry import build_seed_registry


def _draft_state(
    *,
    round_num: int = 2,
    roster_players: list[Player] | None = None,
    single_entry: bool = False,
) -> DraftState:
    roster = Roster(
        players=roster_players or [],
        draft_position=3,
        current_round=round_num,
    )
    return DraftState(
        draft_id="golden-test",
        slot=3,
        archetype=Archetype.C,
        status=DraftStatus.IN_PROGRESS,
        roster=roster,
        single_entry=single_entry,
        draft_date=datetime.now(),
    )


def _player(pid: str, name: str, pos: str, team: str = "CIN", adp: float = 50.0) -> Player:
    return Player(
        player_id=pid,
        name=name,
        merge_name=name.lower(),
        position=pos,
        team=team,
        bye_week=7,
        adp=adp,
        projection_pts=200.0,
        signal=Signal.NEUTRAL,
    )


def test_qb_excluded_before_round_6(bbm_db: Path) -> None:
    qb = _player("bbm:joe-burrow", "Joe Burrow", "QB", adp=61.0)
    rb = _player("bbm:test-rb", "Test RB", "RB", adp=22.0)
    state = _draft_state(round_num=2, roster_players=[_player("bbm:chase", "Ja'Marr Chase", "WR")])

    filtered = _prefilter_candidates([qb, rb], state, state.roster, Archetype.C)

    assert any(p.position == "RB" for p in filtered)
    assert not any(p.position == "QB" for p in filtered)


def test_qb_allowed_from_round_6(bbm_db: Path) -> None:
    qb = _player("bbm:joe-burrow", "Joe Burrow", "QB", adp=61.0)
    state = _draft_state(round_num=6)

    filtered = _prefilter_candidates([qb], state, state.roster, Archetype.C)

    assert len(filtered) == 1
    assert filtered[0].position == "QB"


def test_single_entry_skips_combo_cap_filter(
    bbm_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ceminidfs.bbm import ledger

    sync_players_from_registry(build_seed_registry(), bbm_db)
    conn = __import__("sqlite3").connect(bbm_db)
    rows = conn.execute(
        "SELECT player_id FROM players_dim WHERE player_id LIKE 'bbm:%' ORDER BY adp LIMIT 2"
    ).fetchall()
    conn.close()
    player_a, player_b = rows[0][0], rows[1][0]

    for i in range(40):
        draft_id = f"combo-saturate-{i}"
        create_draft(draft_id, slot=1, archetype="A", db_path=bbm_db)
        ledger.record_pick(draft_id, 1, 1, player_a, is_mine=True, db_path=bbm_db)
        ledger.record_pick(draft_id, 2, 24, player_b, is_mine=True, db_path=bbm_db)
        ledger.complete_draft(draft_id, db_path=bbm_db)

    roster_player = Player(
        player_id=player_a,
        name="A",
        merge_name="a",
        position="WR",
        team="CIN",
        bye_week=7,
        adp=10.0,
    )
    candidate = Player(
        player_id=player_b,
        name="B",
        merge_name="b",
        position="WR",
        team="CIN",
        bye_week=7,
        adp=20.0,
    )

    portfolio_state = _draft_state(
        round_num=3,
        roster_players=[roster_player],
        single_entry=False,
    )
    single_state = _draft_state(
        round_num=3,
        roster_players=[roster_player],
        single_entry=True,
    )

    portfolio_filtered = _prefilter_candidates(
        [candidate], portfolio_state, portfolio_state.roster, Archetype.C
    )
    single_filtered = _prefilter_candidates(
        [candidate], single_state, single_state.roster, Archetype.C
    )

    assert portfolio_filtered == []
    assert len(single_filtered) == 1


def test_single_entry_zero_exposure_mult() -> None:
    state = _draft_state(single_entry=True)
    player = _player("bbm:chase", "Ja'Marr Chase", "WR", adp=3.0)

    def saturated(_pid: str) -> float:
        return 0.99

    _, components, _ = score_player(
        player, state, state.roster, Archetype.A, saturated
    )
    assert components.exposure_mult == 1.0


def test_create_draft_single_entry_flag(bbm_db: Path) -> None:
    create_draft("golden-single", slot=3, archetype="C", db_path=bbm_db, is_single_entry=True)
    state = get_draft_state("golden-single", db_path=bbm_db)
    assert state is not None
    assert state.is_single_entry is True


def test_recommend_top3_no_qb_round_2(bbm_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sync_players_from_registry(build_seed_registry(), bbm_db)
    create_draft("rec-qb-gate", slot=3, archetype="C", db_path=bbm_db)

    from ceminidfs.bbm import session

    monkeypatch.setattr(session, "get_db_path", lambda: bbm_db)
    monkeypatch.setattr("ceminidfs.bbm.ledger.get_db_path", lambda: bbm_db)

    meta = session.get_recommendations_meta(2, 22, "C", "rec-qb-gate", limit=5)
    positions = [r["position"] for r in meta["recommendations"]]
    assert "QB" not in positions
