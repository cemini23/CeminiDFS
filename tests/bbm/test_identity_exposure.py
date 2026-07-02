"""Tests for Workstream A - Ledger & identity core.

Tests covering:
- A1: Normalizer parity
- A2: Strict pick resolution (no auto-stub)
- A3: Junk FA removal, PLAYER_ALIASES
- A4: is_practice column, exposure/combo filters
- A5: Schedule W17 functions
- A6: abandon_draft
- A7: Migration script (indirectly via state)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ceminidfs.bbm import config
from ceminidfs.bbm.ledger import (
    abandon_draft,
    complete_draft,
    create_draft,
    exposure_pct,
    combo_pct,
    record_pick,
    record_taken,
    resolve_player_query,
    sync_players_from_registry,
    get_last_ambiguous_matches,
)
from ceminidfs.bbm.normalize_adp import normalize_name
from ceminidfs.bbm.registry import _normalize_merge, build_seed_registry
from ceminidfs.bbm.schedule import (
    get_week17_matchups,
    are_opponents_week17,
    BYE_WEEKS_2026,
    get_bye_week,
)
from ceminidfs.bbm.reconcile import reconcile_from_csv


# A1: Normalizer parity tests
@pytest.mark.parametrize(
    "name",
    [
        "Amon-Ra St. Brown",
        "Jaxon Smith-Njigba",
        "Brian Thomas Jr.",
        "De'Von Achane",
        "C.J. Stroud",
    ],
)
def test_normalizer_parity_hyphen_suffix(name: str) -> None:
    """_normalize_merge must match normalize_name for hyphenated/suffixed names."""
    assert _normalize_merge(name) == normalize_name(name)


def test_normalizer_specific_values() -> None:
    """Test specific normalized values for key players."""
    assert _normalize_merge("Amon-Ra St. Brown") == "amon ra st brown"
    assert _normalize_merge("Brian Thomas Jr.") == "brian thomas"
    assert _normalize_merge("Jaxon Smith-Njigba") == "jaxon smith njigba"


# A3: Seed registry tests
def test_seed_registry_has_no_junk_fa_rows() -> None:
    """Registry should have no single-token team=FA players after A3."""
    registry = build_seed_registry()
    players = registry.get("players", [])

    junk_count = sum(
        1 for p in players
        if p.get("team") == "FA" and " " not in str(p.get("name", "")).strip()
    )
    assert junk_count == 0, f"Found {junk_count} junk FA rows in registry"


def test_seed_registry_has_four_new_players() -> None:
    """Registry should contain the 4 new seed players from A3."""
    registry = build_seed_registry()
    players = registry.get("players", [])

    expected = {
        ("Tetairoa McMillan", "CAR"),
        ("Oronde Gadsden II", "LAC"),
        ("Brenton Strange", "JAX"),
        ("Chig Okonkwo", "TEN"),
    }

    found = set()
    for p in players:
        name = p.get("name", "")
        team = p.get("team", "")
        if (name, team) in expected:
            found.add((name, team))

    assert found == expected, f"Missing new players: {expected - found}"


def test_seed_registry_no_team_fa() -> None:
    """All players in registry should have real teams (no 'FA')."""
    registry = build_seed_registry()
    players = registry.get("players", [])

    fa_players = [p.get("name") for p in players if p.get("team") == "FA"]
    assert fa_players == [], f"Found players with team=FA: {fa_players}"


# A2: Strict pick resolution tests
def test_hyphen_elite_resolves(bbm_db: Path) -> None:
    """Jaxon Smith-Njigba, JSN alias, and Amon-Ra St. Brown should resolve."""
    # Sync registry first
    registry = build_seed_registry()
    sync_players_from_registry(registry, bbm_db)

    # Test full name
    result = resolve_player_query("Jaxon Smith-Njigba", db_path=bbm_db)
    assert result is not None
    assert "jaxon" in result["player_id"].lower() or "jsn" in result["player_id"].lower()
    assert not result["player_id"].startswith("stub:")

    # Test alias (JSN)
    result = resolve_player_query("JSN", db_path=bbm_db)
    assert result is not None
    assert not result["player_id"].startswith("stub:")

    # Test Amon-Ra St. Brown
    result = resolve_player_query("Amon-Ra St. Brown", db_path=bbm_db)
    assert result is not None
    assert not result["player_id"].startswith("stub:")


def test_surname_resolves_after_junk_removal(bbm_db: Path) -> None:
    """Kelce should resolve to Travis Kelce via LIKE match after junk removal."""
    registry = build_seed_registry()
    sync_players_from_registry(registry, bbm_db)

    result = resolve_player_query("Kelce", db_path=bbm_db)
    assert result is not None
    assert "kelce" in result["player_id"].lower()
    assert not result["player_id"].startswith("stub:")


def test_resolve_unknown_returns_none_no_stub(bbm_db: Path) -> None:
    """Unknown player should return None and not create stub via resolve_player_query."""
    registry = build_seed_registry()
    sync_players_from_registry(registry, bbm_db)

    # Try to resolve unknown player
    result = resolve_player_query("Xyzzy Qwerty", db_path=bbm_db)
    assert result is None

    # Verify get_last_ambiguous_matches returns empty list
    assert get_last_ambiguous_matches() == []

    # Verify no stub was created
    conn = sqlite3.connect(bbm_db)
    stubs = conn.execute(
        "SELECT COUNT(*) FROM players_dim WHERE player_id LIKE 'stub:xyzzy%'"
    ).fetchone()[0]
    conn.close()
    assert stubs == 0, "Stub was created for unknown player"


# A3: Combo pairs test
def test_all_stack_pairs_seed(bbm_db: Path) -> None:
    """All 5 STACK_PAIRS should be seeded in combo_pairs table after sync."""
    registry = build_seed_registry()
    sync_players_from_registry(registry, bbm_db)

    conn = sqlite3.connect(bbm_db)
    count = conn.execute("SELECT COUNT(*) FROM combo_pairs").fetchone()[0]
    conn.close()

    assert count == 5, f"Expected 5 combo_pairs, got {count}"


# A4: Practice draft isolation tests
def test_exposure_excludes_practice(bbm_db: Path) -> None:
    """Practice drafts should not count toward exposure."""
    registry = build_seed_registry()
    sync_players_from_registry(registry, bbm_db)

    # Get a real player ID
    conn = sqlite3.connect(bbm_db)
    row = conn.execute(
        "SELECT player_id FROM players_dim WHERE player_id LIKE 'bbm:%' LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    player_id = row[0]

    # Create a practice draft with a pick
    create_draft("practice-test", slot=1, archetype="A", db_path=bbm_db)
    record_pick("practice-test", 1, 1, player_id, is_mine=True, db_path=bbm_db)
    complete_draft("practice-test", db_path=bbm_db)

    # Exposure should be 0 (practice draft excluded)
    exp = exposure_pct(player_id, db_path=bbm_db)
    assert exp["current"] == 0.0

    # Create a real draft with same pick
    create_draft("real-draft-001", slot=1, archetype="A", db_path=bbm_db)
    record_pick("real-draft-001", 1, 1, player_id, is_mine=True, db_path=bbm_db)
    complete_draft("real-draft-001", db_path=bbm_db)

    # Now exposure should be 1/150
    exp = exposure_pct(player_id, db_path=bbm_db)
    assert exp["current"] == pytest.approx(1 / 150)


def test_combo_pct_weights_in_progress(bbm_db: Path) -> None:
    """Combo pair should weight in-progress drafts at 50%."""
    registry = build_seed_registry()
    sync_players_from_registry(registry, bbm_db)

    # Get two players
    conn = sqlite3.connect(bbm_db)
    rows = conn.execute(
        "SELECT player_id FROM players_dim WHERE player_id LIKE 'bbm:%' LIMIT 2"
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    player_a, player_b = rows[0][0], rows[1][0]

    # Create 1 complete draft with both players
    create_draft("combo-complete", slot=1, archetype="A", db_path=bbm_db)
    record_pick("combo-complete", 1, 1, player_a, is_mine=True, db_path=bbm_db)
    record_pick("combo-complete", 2, 24, player_b, is_mine=True, db_path=bbm_db)
    complete_draft("combo-complete", db_path=bbm_db)

    # Create 1 in-progress draft with both players
    create_draft("combo-progress", slot=1, archetype="A", db_path=bbm_db)
    record_pick("combo-progress", 1, 1, player_a, is_mine=True, db_path=bbm_db)
    record_pick("combo-progress", 2, 24, player_b, is_mine=True, db_path=bbm_db)
    # Not completed - stays in_progress

    # Combo exposure should be (1 + 0.5) / 150
    combo = combo_pct(player_a, player_b, db_path=bbm_db)
    assert combo["current"] == pytest.approx(1.5 / 150)


def test_combo_pct_excludes_practice(bbm_db: Path) -> None:
    """Practice drafts should not count toward combo exposure."""
    registry = build_seed_registry()
    sync_players_from_registry(registry, bbm_db)

    # Get two players
    conn = sqlite3.connect(bbm_db)
    rows = conn.execute(
        "SELECT player_id FROM players_dim WHERE player_id LIKE 'bbm:%' LIMIT 2"
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    player_a, player_b = rows[0][0], rows[1][0]

    # Create 1 complete real draft
    create_draft("combo-real", slot=1, archetype="A", db_path=bbm_db)
    record_pick("combo-real", 1, 1, player_a, is_mine=True, db_path=bbm_db)
    record_pick("combo-real", 2, 24, player_b, is_mine=True, db_path=bbm_db)
    complete_draft("combo-real", db_path=bbm_db)

    # Create 1 complete practice draft with same pair
    create_draft("practice-combo", slot=1, archetype="A", db_path=bbm_db)
    record_pick("practice-combo", 1, 1, player_a, is_mine=True, db_path=bbm_db)
    record_pick("practice-combo", 2, 24, player_b, is_mine=True, db_path=bbm_db)
    complete_draft("practice-combo", db_path=bbm_db)

    # Combo exposure should be 1/150 (practice excluded)
    combo = combo_pct(player_a, player_b, db_path=bbm_db)
    assert combo["current"] == pytest.approx(1 / 150)


def test_combo_pct_returns_raw(bbm_db: Path) -> None:
    """combo_pct should return raw float, not rounded."""
    registry = build_seed_registry()
    sync_players_from_registry(registry, bbm_db)

    # Get two players
    conn = sqlite3.connect(bbm_db)
    rows = conn.execute(
        "SELECT player_id FROM players_dim WHERE player_id LIKE 'bbm:%' LIMIT 2"
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    player_a, player_b = rows[0][0], rows[1][0]

    # Create exactly 37 complete drafts to get 37/150 = 0.24666...
    for i in range(37):
        draft_id = f"raw-test-{i:03d}"
        create_draft(draft_id, slot=1, archetype="A", db_path=bbm_db)
        record_pick(draft_id, 1, 1, player_a, is_mine=True, db_path=bbm_db)
        record_pick(draft_id, 2, 24, player_b, is_mine=True, db_path=bbm_db)
        complete_draft(draft_id, db_path=bbm_db)

    combo = combo_pct(player_a, player_b, db_path=bbm_db)
    # Should be exactly 37/150, not rounded to 0.247
    assert combo["current"] == pytest.approx(37 / 150)


def test_create_draft_practice_flag(bbm_db: Path) -> None:
    """create_draft should set is_practice=1 for practice drafts."""
    # Test explicit is_practice=True
    result = create_draft("practice-explicit", slot=1, is_practice=True, db_path=bbm_db)
    assert result["is_practice"] is True

    conn = sqlite3.connect(bbm_db)
    flag = conn.execute(
        "SELECT is_practice FROM drafts WHERE draft_id = 'practice-explicit'"
    ).fetchone()[0]
    conn.close()
    assert flag == 1

    # Test practice- prefix auto-detection
    result = create_draft("practice-auto-001", slot=1, db_path=bbm_db)
    assert result["is_practice"] is True

    conn = sqlite3.connect(bbm_db)
    flag = conn.execute(
        "SELECT is_practice FROM drafts WHERE draft_id = 'practice-auto-001'"
    ).fetchone()[0]
    conn.close()
    assert flag == 1

    # Test regular draft
    result = create_draft("real-draft-xyz", slot=1, db_path=bbm_db)
    assert result["is_practice"] is False

    conn = sqlite3.connect(bbm_db)
    flag = conn.execute(
        "SELECT is_practice FROM drafts WHERE draft_id = 'real-draft-xyz'"
    ).fetchone()[0]
    conn.close()
    assert flag == 0


# A6: abandon_draft tests
def test_abandon_draft(bbm_db: Path) -> None:
    """abandon_draft should delete draft and all related rows."""
    registry = build_seed_registry()
    sync_players_from_registry(registry, bbm_db)

    # Get a player
    conn = sqlite3.connect(bbm_db)
    row = conn.execute(
        "SELECT player_id FROM players_dim WHERE player_id LIKE 'bbm:%' LIMIT 1"
    ).fetchone()
    conn.close()
    player_id = row[0]

    # Create draft with pick and taken
    create_draft("abandon-me", slot=1, archetype="A", db_path=bbm_db)
    record_pick("abandon-me", 1, 1, player_id, is_mine=True, db_path=bbm_db)
    record_taken("abandon-me", 1, 2, "bbm:bijan-robinson", db_path=bbm_db)

    # Verify draft exists
    conn = sqlite3.connect(bbm_db)
    count = conn.execute(
        "SELECT COUNT(*) FROM drafts WHERE draft_id = 'abandon-me'"
    ).fetchone()[0]
    assert count == 1
    conn.close()

    # Abandon the draft
    result = abandon_draft("abandon-me", db_path=bbm_db)
    assert result["deleted"] is True
    assert result["picks_removed"] >= 1
    assert result["taken_removed"] >= 1

    # Verify draft is gone
    conn = sqlite3.connect(bbm_db)
    count = conn.execute(
        "SELECT COUNT(*) FROM drafts WHERE draft_id = 'abandon-me'"
    ).fetchone()[0]
    assert count == 0

    # Verify picks are gone
    count = conn.execute(
        "SELECT COUNT(*) FROM picks WHERE draft_id = 'abandon-me'"
    ).fetchone()[0]
    assert count == 0

    # Verify room_taken is gone
    count = conn.execute(
        "SELECT COUNT(*) FROM room_taken WHERE draft_id = 'abandon-me'"
    ).fetchone()[0]
    assert count == 0
    conn.close()


def test_abandon_complete_draft_requires_force(bbm_db: Path) -> None:
    """abandon_draft should refuse complete drafts without force=True."""
    registry = build_seed_registry()
    sync_players_from_registry(registry, bbm_db)

    # Get a player
    conn = sqlite3.connect(bbm_db)
    row = conn.execute(
        "SELECT player_id FROM players_dim WHERE player_id LIKE 'bbm:%' LIMIT 1"
    ).fetchone()
    conn.close()
    player_id = row[0]

    # Create and complete a draft
    create_draft("complete-draft", slot=1, archetype="A", db_path=bbm_db)
    record_pick("complete-draft", 1, 1, player_id, is_mine=True, db_path=bbm_db)
    complete_draft("complete-draft", db_path=bbm_db)

    # Should raise without force
    with pytest.raises(ValueError, match="force"):
        abandon_draft("complete-draft", db_path=bbm_db)

    # Should succeed with force=True
    result = abandon_draft("complete-draft", db_path=bbm_db, force=True)
    assert result["deleted"] is True


def test_abandon_missing_draft_raises(bbm_db: Path) -> None:
    """abandon_draft should raise ValueError for non-existent draft."""
    with pytest.raises(ValueError, match="not found"):
        abandon_draft("non-existent-draft", db_path=bbm_db)


# A4: Reconcile filter test
def test_reconcile_excludes_practice(bbm_db: Path, tmp_path: Path) -> None:
    """reconcile_from_csv should exclude practice drafts from counts."""
    registry = build_seed_registry()
    sync_players_from_registry(registry, bbm_db)

    # Get a player
    conn = sqlite3.connect(bbm_db)
    row = conn.execute(
        "SELECT player_id, name FROM players_dim WHERE player_id LIKE 'bbm:%' LIMIT 1"
    ).fetchone()
    conn.close()
    player_id, player_name = row

    # Create practice draft with pick
    create_draft("practice-recon", slot=1, archetype="A", db_path=bbm_db)
    record_pick("practice-recon", 1, 1, player_id, is_mine=True, db_path=bbm_db)
    complete_draft("practice-recon", db_path=bbm_db)

    # Create minimal CSV with 0% exposure for the player
    csv_path = tmp_path / "exposure.csv"
    csv_path.write_text(
        f"player,position,team,times drafted,exposure %\n{player_name},WR,KC,0,0.0\n"
    )

    # Reconcile - should show ledger_ahead since practice draft is excluded from reconcile
    result = reconcile_from_csv(csv_path)

    # The ledger count should be 0 (practice excluded), matching CSV count of 0
    # So there should be no ledger_ahead entries for this player
    player_diffs = [d for d in result.ledger_ahead if player_name in d.player_name]
    assert len(player_diffs) == 0


# A5: Schedule tests
def test_schedule_w17_and_bye_parity() -> None:
    """W17 matchups and BYE_WEEKS should be correctly defined and exported."""
    # Test W17 matchups
    assert are_opponents_week17("KC", "DEN") is True
    assert are_opponents_week17("DEN", "KC") is True  # Order shouldn't matter
    assert are_opponents_week17("KC", "CAR") is False  # Not opponents

    # Test get_week17_matchups returns list of tuples
    matchups = get_week17_matchups()
    assert len(matchups) == 16  # 16 games in a 32-team league
    assert all(isinstance(m, tuple) and len(m) == 2 for m in matchups)

    # Test BYE_WEEKS exported from schedule
    assert config.BYE_WEEKS is BYE_WEEKS_2026
    assert config.get_bye_week("KC") == 5
    assert config.get_bye_week is get_bye_week


def test_config_bye_week_lookup() -> None:
    """config.get_bye_week and BYE_WEEKS should work correctly."""
    # Test via re-exported functions
    assert config.get_bye_week("PHI") == 10
    assert config.get_bye_week("DAL") == 14
    assert config.get_bye_week("UNKNOWN") is None

    # Test BYE_WEEKS dict
    assert "KC" in config.BYE_WEEKS
    assert config.BYE_WEEKS["KC"] == 5


# A3: PLAYER_ALIASES tests
def test_player_aliases_defined() -> None:
    """PLAYER_ALIASES should contain expected entries."""
    assert "jsn" in config.PLAYER_ALIASES
    assert config.PLAYER_ALIASES["jsn"] == "jaxon smith njigba"
    assert "arsb" in config.PLAYER_ALIASES
    assert config.PLAYER_ALIASES["arsb"] == "amon ra st brown"


def test_alias_lookup_in_get_players_by_name(bbm_db: Path) -> None:
    """Alias lookup should work via get_players_by_name."""
    from ceminidfs.bbm.ledger import get_players_by_name

    registry = build_seed_registry()
    sync_players_from_registry(registry, bbm_db)

    # Test JSN alias resolves to Jaxon Smith-Njigba
    results = get_players_by_name("jsn", db_path=bbm_db)
    assert len(results) >= 1
    assert any("jaxon" in r["name"].lower() for r in results)

    # Test ARSB alias resolves to Amon-Ra St. Brown
    results = get_players_by_name("arsb", db_path=bbm_db)
    assert len(results) >= 1
    assert any("amon" in r["name"].lower() for r in results)


# A6: list_in_progress_drafts includes is_practice
def test_list_in_progress_drafts_includes_practice(bbm_db: Path) -> None:
    """list_in_progress_drafts should include is_practice flag."""
    from ceminidfs.bbm.ledger import list_in_progress_drafts

    # Create drafts
    create_draft("practice-list", slot=1, db_path=bbm_db)
    create_draft("real-list", slot=2, is_practice=False, db_path=bbm_db)

    drafts = list_in_progress_drafts(db_path=bbm_db)

    practice_drafts = [d for d in drafts if d["draft_id"] == "practice-list"]
    real_drafts = [d for d in drafts if d["draft_id"] == "real-list"]

    assert len(practice_drafts) == 1
    assert practice_drafts[0]["is_practice"] is True

    assert len(real_drafts) == 1
    assert real_drafts[0]["is_practice"] is False
