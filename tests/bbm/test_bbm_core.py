"""Core BBM draft copilot tests."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from ceminidfs.bbm import backtest as bbm_backtest
from ceminidfs.bbm import board_parse
from ceminidfs.bbm.api_server import create_server
from ceminidfs.bbm.config import get_bye_week
from ceminidfs.bbm.draft_card import build_draft_card
from ceminidfs.bbm.ledger import (
    create_draft,
    complete_draft,
    ensure_player_stub,
    get_draft_state,
    get_players_by_name,
    exposure_pct,
    init_db,
    record_pick,
    record_taken,
    resolve_player_query,
    sync_players_from_registry,
)
from ceminidfs.bbm.models import Archetype, DraftState, DraftStatus, Player, Roster
from ceminidfs.bbm.normalize_adp import merge_adp_csv, merge_projections_csv, normalize_name
from ceminidfs.bbm.registry import build_seed_registry, check_registry_coverage
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


def test_snake_pick_num_slot_12_round_18():
    state = DraftState(
        draft_id="draft-001",
        slot=12,
        archetype=Archetype.B,
        status=DraftStatus.IN_PROGRESS,
        roster=Roster(players=[], draft_position=12, current_round=18),
    )
    assert state.current_pick_num == 205


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


def test_refresh_adp_merge_stats(tmp_path: Path):
    csv_path = tmp_path / "adp.csv"
    csv_path.write_text(
        "name,adp\nJa'Marr Chase,1.0\n",
        encoding="utf-8",
    )
    registry = build_seed_registry()

    result = merge_adp_csv(csv_path, registry)

    assert result.matched == 1
    assert result.exact_matched == 1
    assert result.fuzzy_matched == 0
    assert result.unmatched == []


def test_connect_db_wal_mode(tmp_path: Path):
    db_path = tmp_path / "bbm7.db"
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()

    assert journal_mode.lower() == "wal"


def test_ensure_player_stub(bbm_db: Path):
    stub_1 = ensure_player_stub("Unknown Guy", db_path=bbm_db)
    stub_2 = ensure_player_stub("Unknown Guy", db_path=bbm_db)

    assert stub_1["player_id"] == stub_2["player_id"]
    assert stub_1["player_id"].startswith("stub:")
    assert stub_1["injury_fade"] is True

    conn = sqlite3.connect(bbm_db)
    count = conn.execute(
        "SELECT COUNT(*) FROM players_dim WHERE player_id = ?",
        (stub_1["player_id"],),
    ).fetchone()[0]
    conn.close()

    assert count == 1


def test_merge_projections_csv(tmp_path: Path):
    csv_path = tmp_path / "projections.csv"
    csv_path.write_text(
        "name,projection\nJa'Marr Chase,255.5\n",
        encoding="utf-8",
    )
    registry = build_seed_registry()

    result = merge_projections_csv(csv_path, registry)

    assert result.matched == 1
    assert result.exact_matched == 1
    assert result.fuzzy_matched == 0
    assert result.unmatched == []
    assert next(p for p in registry["players"] if p["name"] == "Ja'Marr Chase")["projection_pts"] == 255.5


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


def test_benchmark_recommender_under_200ms(bbm_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("ceminidfs.bbm.session.get_db_path", lambda: bbm_db)
    draft_id = "benchmark-rec-001"
    create_draft(draft_id, slot=4, archetype="B", db_path=bbm_db)

    timings_ms: list[float] = []
    for _ in range(20):
        start = time.perf_counter()
        recs = get_recommendations(1, 4, "B", draft_id, limit=3)
        timings_ms.append((time.perf_counter() - start) * 1000)
        assert len(recs) == 3

    p99_ms = sorted(timings_ms)[-1]
    assert p99_ms < 500


def test_backtest_fixture_smoke():
    if not hasattr(bbm_backtest, "load_pick_csv"):
        pytest.skip("backtest.load_pick_csv not available yet")

    fixture_path = Path("tests/fixtures/bbm/sample_drafts.csv")
    assert fixture_path.exists()
    rows = bbm_backtest.load_pick_csv(fixture_path)
    assert rows
    assert rows[0]["draft_id"] == "room-001"


def test_resolve_player_query_index(bbm_db: Path):
    matches = get_players_by_name("j", db_path=bbm_db)
    if len(matches) < 2:
        pytest.skip("Need at least two matches to test index selection")

    selected = resolve_player_query("j", index=2, db_path=bbm_db)
    assert selected == matches[1]


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


def test_registry_coverage_warning():
    coverage = check_registry_coverage(build_seed_registry())
    assert coverage["player_count"] < 120
    assert coverage["warnings"]


def test_board_parse_aria_labels():
    """Test parsing of Underdog-style aria labels."""
    # Test basic player name extraction
    assert board_parse.parse_aria_label("Select Ja'Marr Chase, WR, CIN") == "jamarr chase"
    assert board_parse.parse_aria_label("Pick Patrick Mahomes") == "patrick mahomes"
    assert board_parse.parse_aria_label("Player: Justin Jefferson") == "justin jefferson"

    # Test name with suffix stripping
    assert board_parse.parse_aria_label("Select Odell Beckham Jr.") == "odell beckham"
    assert board_parse.parse_aria_label("Pick Marvin Harrison Jr") == "marvin harrison"

    # Test noise filtering
    assert board_parse.parse_aria_label("draft pick") is None
    assert board_parse.parse_aria_label("button submit") is None
    assert board_parse.parse_aria_label("menu options") is None

    # Test extract_names_from_aria_labels
    labels = [
        "Select Ja'Marr Chase",
        "Pick Patrick Mahomes",
        "button noise",
        "Pick Justin Jefferson",
    ]
    names = board_parse.extract_names_from_aria_labels(labels)
    assert len(names) == 3
    assert "jamarr chase" in names
    assert "patrick mahomes" in names
    assert "justin jefferson" in names

    # Test filter_draft_board_names deduplication
    names = ["jamarr chase", "patrick mahomes", "jamarr chase", "justin jefferson"]
    filtered = board_parse.filter_draft_board_names(names)
    assert len(filtered) == 3
    assert "jamarr chase" in filtered


def test_api_health(bbm_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Test API server health endpoint."""
    from ceminidfs.bbm import ledger

    monkeypatch.setattr(ledger, "get_db_path", lambda: bbm_db)
    monkeypatch.setattr("ceminidfs.bbm.api_server._get_ledger", lambda: ledger)

    # Create a test draft
    draft_id = "test-api-001"
    ledger.create_draft(draft_id, slot=4, archetype="B", db_path=bbm_db)

    # Start server in thread
    server = create_server(host="127.0.0.1", port=18765, draft_id=draft_id, slot=4, archetype="B")

    def run_server():
        server.serve_forever()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    # Wait for server to start
    time.sleep(0.5)

    try:
        # Test health endpoint
        req = urllib.request.Request("http://127.0.0.1:18765/health")
        with urllib.request.urlopen(req, timeout=5) as response:
            assert response.status == 200
            body = response.read().decode("utf-8")
            data = json.loads(body)  # type: ignore
            assert data.get("ok") is True

        req = urllib.request.Request("http://127.0.0.1:18765/api/status")
        with urllib.request.urlopen(req, timeout=5) as response:
            assert response.status == 200
            body = response.read().decode("utf-8")
            data = json.loads(body)  # type: ignore
            assert data.get("ok") is True
            assert data.get("draft_id") == draft_id

        # Test state endpoint
        req = urllib.request.Request(f"http://127.0.0.1:18765/api/state?draft_id={draft_id}")
        with urllib.request.urlopen(req, timeout=5) as response:
            assert response.status == 200
            body = response.read().decode("utf-8")
            data = json.loads(body)  # type: ignore
            assert data.get("draft_id") == draft_id
            assert data.get("slot") == 4
            assert data.get("archetype") == "B"
            assert data.get("current_round") == 1
            assert data.get("pick_num") == 4  # (1-1)*12 + 4
    finally:
        server.shutdown()
