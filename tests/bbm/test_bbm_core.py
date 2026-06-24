"""Core BBM draft copilot tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ceminidfs.bbm.config import get_bye_week
from ceminidfs.bbm.draft_card import build_draft_card
from ceminidfs.bbm.ledger import (
    create_draft,
    complete_draft,
    get_draft_state,
    exposure_pct,
    init_db,
    record_pick,
    record_taken,
    sync_players_from_registry,
)
from ceminidfs.bbm.models import Archetype, Player, Roster
from ceminidfs.bbm.normalize_adp import normalize_name
from ceminidfs.bbm.registry import build_seed_registry
from ceminidfs.bbm.session import get_recommendations
from ceminidfs.bbm.validator import validate_pick
from ceminidfs.models.scoring import score_half_ppr_season


@pytest.fixture
def bbm_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "bbm7.db"
    registry_path = tmp_path / "player_registry.json"
    monkeypatch.setattr("ceminidfs.bbm.ledger.get_db_path", lambda: db_path)
    monkeypatch.setattr(
        "ceminidfs.bbm.registry.get_registry_path",
        lambda data_dir=None: registry_path,
    )
    init_db(db_path)
    registry = build_seed_registry()
    registry_path.write_text(__import__("json").dumps(registry), encoding="utf-8")
    sync_players_from_registry(registry, db_path)
    return db_path


def test_normalize_name():
    assert normalize_name("Ja'Marr Chase Jr.") == "jamarr chase"


def test_seed_registry_has_players():
    registry = build_seed_registry()
    assert len(registry["players"]) >= 40


def test_bye_week_lookup():
    assert get_bye_week("KC") == 5
    assert get_bye_week("PHI") == 10


def test_draft_card_markdown():
    card = build_draft_card()
    assert "CeminiBBM" in card
    assert "Exposure caps" in card


def test_half_ppr_scoring():
    pts = score_half_ppr_season(
        {"rec": 80, "rec_yds": 1000, "rec_td": 8, "rush_yds": 0, "rush_td": 0}
    )
    assert pts == 80 * 0.5 + 1000 * 0.1 + 8 * 6  # 40 + 100 + 48 = 188


def test_mock_draft_flow(bbm_db: Path):
    draft_id = "test-draft-001"
    create_draft(draft_id, slot=4, archetype="B", db_path=bbm_db)

    picks = [
        ("bbm:ja-marr-chase", 1, 4),
        ("bbm:puka-nacua", 2, 21),
        ("bbm:derrick-henry", 3, 28),
    ]
    for player_id, round_num, pick_num in picks:
        record_pick(draft_id, round_num, pick_num, player_id, is_mine=True, db_path=bbm_db)

    state = get_draft_state(draft_id, db_path=bbm_db)
    assert state is not None
    assert len(state.my_picks) == 3
    assert state.archetype == "B"


def test_exposure_uses_total_entries(bbm_db: Path):
    draft_id = "test-exposure-001"
    player_id = "bbm:ja-marr-chase"
    create_draft(draft_id, slot=4, archetype="B", db_path=bbm_db)
    record_pick(draft_id, 1, 4, player_id, is_mine=True, db_path=bbm_db)
    complete_draft(draft_id, db_path=bbm_db)

    exp = exposure_pct(player_id, db_path=bbm_db)
    assert exp["current"] == pytest.approx(1 / 150, rel=1e-3)


def test_qb_bye_second_qb_duplicate_blocked():
    roster = Roster(
        players=[
            Player(
                player_id="1",
                name="QB1",
                merge_name="qb1",
                position="QB",
                team="KC",
                bye_week=5,
                adp=50,
            )
        ],
        draft_position=4,
        current_round=8,
    )
    candidate = Player(
        player_id="2",
        name="QB2",
        merge_name="qb2",
        position="QB",
        team="PHI",
        bye_week=5,
        adp=80,
    )
    violations = validate_pick(candidate, roster, Archetype.B)
    assert any("QB_BYE_DUPLICATE" in v for v in violations)


def test_archetype_override_in_recommendations(bbm_db: Path, monkeypatch: pytest.MonkeyPatch):
    draft_id = "test-archetype-override-001"
    create_draft(draft_id, slot=4, archetype="A", db_path=bbm_db)

    captured: dict[str, Archetype] = {}

    def fake_recommend_top3(draft_state, available_players, exposure_pct_fn, max_recommendations=3):
        captured["archetype"] = draft_state.archetype
        return []

    monkeypatch.setattr("ceminidfs.bbm.session.recommend_top3", fake_recommend_top3)
    monkeypatch.setattr("ceminidfs.bbm.session.get_db_path", lambda: bbm_db)

    recs = get_recommendations(1, 4, "C", draft_id, limit=3)
    assert recs == []
    assert captured["archetype"] == Archetype.C


def test_get_draft_state_includes_bye_week(bbm_db: Path):
    draft_id = "test-bye-week-001"
    create_draft(draft_id, slot=4, archetype="B", db_path=bbm_db)
    record_pick(draft_id, 1, 4, "bbm:ja-marr-chase", is_mine=True, db_path=bbm_db)

    state = get_draft_state(draft_id, db_path=bbm_db)
    assert state is not None
    assert state.my_picks[0]["bye_week"] == get_bye_week("CIN")
    assert state.all_picks[0]["bye_week"] == get_bye_week("CIN")


def test_record_taken_does_not_advance_round(bbm_db: Path):
    draft_id = "test-taken-001"
    create_draft(draft_id, slot=1, archetype="A", db_path=bbm_db)
    record_taken(draft_id, 1, 2, "bbm:bijan-robinson", db_path=bbm_db)
    state = get_draft_state(draft_id, db_path=bbm_db)
    assert state is not None
    assert state.current_round == 1


def test_recommender_returns_top3(bbm_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ceminidfs.bbm.ledger.get_db_path", lambda: bbm_db)
    monkeypatch.setattr("ceminidfs.bbm.session.get_db_path", lambda: bbm_db)
    draft_id = "test-rec-001"
    create_draft(draft_id, slot=4, archetype="B", db_path=bbm_db)

    recs = get_recommendations(1, 4, "B", draft_id, limit=3)
    assert len(recs) == 3
    assert all("name" in r for r in recs)


def test_validator_qb_bye_constraint():
    roster = Roster(
        players=[
            Player(
                player_id="1",
                name="QB1",
                merge_name="qb1",
                position="QB",
                team="KC",
                bye_week=5,
                adp=50,
            ),
            Player(
                player_id="2",
                name="QB2",
                merge_name="qb2",
                position="QB",
                team="PHI",
                bye_week=10,
                adp=80,
            ),
        ],
        draft_position=4,
        current_round=8,
    )
    candidate = Player(
        player_id="3",
        name="QB3",
        merge_name="qb3",
        position="QB",
        team="BUF",
        bye_week=5,
        adp=100,
    )
    violations = validate_pick(candidate, roster, Archetype.B)
    assert any("QB_BYE" in v for v in violations)
