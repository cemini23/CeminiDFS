"""SQLite ledger for BBM exposure tracking and draft state."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ceminidfs.bbm.config import IN_PROGRESS_EXPOSURE_WEIGHT, TOTAL_ENTRIES
from ceminidfs.bbm.normalize_adp import normalize_name


def connect_db(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    """Create a SQLite connection with WAL mode and busy timeout.

    Args:
        db_path: Path to the database file. If None, uses default path.

    Returns:
        sqlite3.Connection with WAL journal mode and 5s busy timeout.
    """
    path = Path(db_path) if db_path else get_db_path()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# Module-level storage for last ambiguous matches (for CLI disambiguation)
_last_ambiguous_matches: list[dict[str, Any]] = []


def get_last_ambiguous_matches() -> list[dict[str, Any]]:
    """Return the last ambiguous matches from resolve_player_query."""
    return _last_ambiguous_matches.copy()


def _set_last_ambiguous_matches(matches: list[dict[str, Any]]) -> None:
    """Set the last ambiguous matches (internal use)."""
    global _last_ambiguous_matches
    _last_ambiguous_matches = matches


def _stub_player_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_name(name)).strip("-")
    return f"stub:{slug or 'unknown'}"


def get_db_path() -> Path:
    """Return default database path."""
    return Path("data/bbm/bbm7.db")


def init_db(path: Optional[Path | str] = None) -> Path:
    """Initialize SQLite schema; return path."""
    db_path = Path(path) if path else get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect_db(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")

    # Players dimension table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players_dim (
            player_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            merge_name TEXT,
            team TEXT,
            position TEXT,
            bye_week INTEGER,
            tier TEXT,
            cap_pct REAL,
            adp REAL,
            projection_pts REAL,
            signal TEXT,
            injury_fade INTEGER DEFAULT 0,
            notes TEXT
        )
    """)

    # Drafts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            draft_id TEXT PRIMARY KEY,
            draft_date TEXT,
            slot INTEGER,
            archetype TEXT,
            status TEXT CHECK(status IN ('in_progress','complete')),
            underdog_entry_id TEXT,
            current_round INTEGER DEFAULT 1,
            total_rounds INTEGER DEFAULT 18,
            pivot_applied INTEGER DEFAULT 0,
            pivot_warning TEXT
        )
    """)

    # Add pivot columns if they don't exist (ALTER-safe for existing databases)
    try:
        cursor.execute("ALTER TABLE drafts ADD COLUMN pivot_applied INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute("ALTER TABLE drafts ADD COLUMN pivot_warning TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add is_practice column if it doesn't exist (ALTER-safe for existing databases)
    try:
        cursor.execute("ALTER TABLE drafts ADD COLUMN is_practice INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    cursor.execute(
        "UPDATE drafts SET is_practice = 1 "
        "WHERE draft_id LIKE 'practice-%' AND (is_practice IS NULL OR is_practice = 0)"
    )

    # Picks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS picks (
            draft_id TEXT REFERENCES drafts(draft_id),
            round INTEGER,
            pick_num INTEGER,
            player_id TEXT REFERENCES players_dim(player_id),
            is_mine INTEGER DEFAULT 0,
            PRIMARY KEY (draft_id, round)
        )
    """)

    # Combo pairs table for stack tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS combo_pairs (
            player_a TEXT,
            player_b TEXT,
            cap_pct REAL DEFAULT 0.25,
            PRIMARY KEY (player_a, player_b)
        )
    """)

    # Room taken table (players drafted by others — does not advance round)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS room_taken (
            draft_id TEXT REFERENCES drafts(draft_id),
            player_id TEXT,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (draft_id, player_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id TEXT REFERENCES drafts(draft_id),
            action_type TEXT NOT NULL,
            round INTEGER,
            player_id TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

    # Seed combo_pairs from config if players exist in players_dim
    _seed_combo_pairs_from_config(path=db_path)

    return db_path


def _seed_combo_pairs_from_config(
    cap_pct: float = 0.25,
    path: Optional[Path] = None
) -> int:
    """Seed combo_pairs table from config.STACK_PAIRS using merge_name lookup.

    Returns count of pairs seeded.
    """
    from ceminidfs.bbm.config import STACK_PAIRS
    from ceminidfs.bbm.normalize_adp import normalize_name

    db_path = path or get_db_path()
    conn = connect_db(db_path)
    cursor = conn.cursor()

    count = 0
    for qb_name, wr_te_name in STACK_PAIRS:
        # Look up players by merge_name
        qb_normalized = normalize_name(qb_name)
        wr_te_normalized = normalize_name(wr_te_name)

        cursor.execute(
            "SELECT player_id FROM players_dim WHERE LOWER(COALESCE(merge_name, name)) = ?",
            (qb_normalized,)
        )
        qb_row = cursor.fetchone()

        cursor.execute(
            "SELECT player_id FROM players_dim WHERE LOWER(COALESCE(merge_name, name)) = ?",
            (wr_te_normalized,)
        )
        wr_te_row = cursor.fetchone()

        if qb_row and wr_te_row:
            player_a, player_b = sorted([qb_row[0], wr_te_row[0]])
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO combo_pairs (player_a, player_b, cap_pct) VALUES (?, ?, ?)",
                    (player_a, player_b, cap_pct)
                )
                if cursor.rowcount > 0:
                    count += 1
            except sqlite3.IntegrityError:
                pass  # Already exists

    conn.commit()
    conn.close()
    return count


@dataclass
class PlayerDim:
    """Player dimension record."""
    player_id: str
    name: str
    merge_name: Optional[str] = None
    team: Optional[str] = None
    position: Optional[str] = None
    bye_week: Optional[int] = None
    tier: Optional[str] = None
    cap_pct: Optional[float] = None
    adp: Optional[float] = None
    projection_pts: Optional[float] = None
    signal: Optional[str] = None
    injury_fade: bool = False
    notes: Optional[str] = None


@dataclass
class DraftState:
    """Current state of a draft."""
    draft_id: str
    slot: int
    archetype: str
    status: str
    current_round: int
    total_rounds: int
    my_picks: list[dict[str, Any]]
    all_picks: list[dict[str, Any]]


def sync_players_from_registry(registry: dict[str, Any], db_path: Optional[Path] = None) -> int:
    """Sync players from registry dict to database. Returns count inserted/updated."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    players = registry.get("players", [])
    count = 0

    for player in players:
        cursor.execute("""
            INSERT OR REPLACE INTO players_dim (
                player_id, name, merge_name, team, position, bye_week,
                tier, cap_pct, adp, projection_pts, signal, injury_fade, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            player.get("player_id"),
            player.get("name"),
            player.get("merge_name"),
            player.get("team"),
            player.get("position"),
            player.get("bye_week"),
            player.get("tier"),
            player.get("exposure_cap_pct"),
            player.get("adp"),
            player.get("projection_pts"),
            player.get("signal"),
            1 if player.get("injury_fade", False) else 0,
            player.get("notes"),
        ))
        count += cursor.rowcount

    conn.commit()
    conn.close()

    # Seed combo_pairs after syncing players
    _seed_combo_pairs_from_config(path=db)

    return count


def exposure_pct(player_id: str, db_path: Optional[Path] = None) -> dict[str, float]:
    """
    Calculate exposure percentage for a player.
    Complete drafts count at 100%, in_progress at 50% weight.
    Denominator is TOTAL_ENTRIES (150) from config.
    Returns dict with 'current', 'cap', 'available'.
    """
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    # Get player cap
    cursor.execute("SELECT cap_pct FROM players_dim WHERE player_id = ?", (player_id,))
    row = cursor.fetchone()
    cap = row[0] if row else 0.35  # Default 35% cap

    # Count complete drafts (excluding practice drafts)
    cursor.execute("""
        SELECT COUNT(DISTINCT d.draft_id)
        FROM drafts d
        JOIN picks p ON d.draft_id = p.draft_id
        WHERE p.player_id = ? AND d.status = 'complete' AND d.is_practice = 0
    """, (player_id,))
    complete_count = cursor.fetchone()[0] or 0

    # Count in_progress drafts at 50% weight (excluding practice drafts)
    cursor.execute("""
        SELECT COUNT(DISTINCT d.draft_id)
        FROM drafts d
        JOIN picks p ON d.draft_id = p.draft_id
        WHERE p.player_id = ? AND d.status = 'in_progress' AND d.is_practice = 0
    """, (player_id,))
    in_progress_count = cursor.fetchone()[0] or 0

    conn.close()

    # Calculate exposure using TOTAL_ENTRIES as denominator
    weighted = complete_count + (IN_PROGRESS_EXPOSURE_WEIGHT * in_progress_count)
    exposure = weighted / TOTAL_ENTRIES

    return {
        "current": exposure,
        "cap": cap or 0.35,
        "available": (cap or 0.35) - exposure,
    }


def combo_pct(player_a: str, player_b: str, db_path: Optional[Path] = None) -> dict[str, float]:
    """
    Calculate combo pair exposure (e.g., QB-WR stacks).
    Denominator is TOTAL_ENTRIES (150) from config.
    Complete drafts count at 100%, in_progress at 50% weight.
    Returns dict with 'current', 'cap', 'available'.
    """
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    # Get cap for this combo
    a, b = sorted([player_a, player_b])
    cursor.execute(
        "SELECT cap_pct FROM combo_pairs WHERE player_a = ? AND player_b = ?",
        (a, b)
    )
    row = cursor.fetchone()
    cap = row[0] if row else 0.25  # Default 25% combo cap

    # Count drafts where both players appear (excluding practice drafts, with in-progress weighting)
    cursor.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN d.status = 'complete' THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN d.status = 'in_progress' THEN 1 ELSE 0 END), 0)
        FROM (
            SELECT DISTINCT p1.draft_id AS draft_id
            FROM picks p1
            JOIN picks p2 ON p1.draft_id = p2.draft_id
            WHERE p1.player_id = ? AND p2.player_id = ?
        ) joint
        JOIN drafts d ON joint.draft_id = d.draft_id
        WHERE d.is_practice = 0
    """, (player_a, player_b))
    complete_count, in_progress_count = cursor.fetchone()

    conn.close()

    # Calculate exposure using TOTAL_ENTRIES as denominator
    weighted = complete_count + (IN_PROGRESS_EXPOSURE_WEIGHT * in_progress_count)
    exposure = weighted / TOTAL_ENTRIES

    return {"current": exposure, "cap": cap, "available": cap - exposure}


def create_draft(
    draft_id: str,
    slot: int,
    archetype: str = "A",
    db_path: Optional[Path] = None,
    total_rounds: int = 18,
    is_practice: bool = False,
) -> dict[str, Any]:
    """Create a new draft record."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    # Force is_practice=1 for practice drafts
    is_practice_flag = 1 if (is_practice or draft_id.startswith("practice-")) else 0

    cursor.execute("""
        INSERT INTO drafts (draft_id, draft_date, slot, archetype, status, current_round, total_rounds, is_practice)
        VALUES (?, ?, ?, ?, 'in_progress', 1, ?, ?)
    """, (
        draft_id,
        datetime.now().isoformat(),
        slot,
        archetype,
        total_rounds,
        is_practice_flag,
    ))

    conn.commit()
    conn.close()

    return {
        "draft_id": draft_id,
        "slot": slot,
        "archetype": archetype,
        "status": "in_progress",
        "current_round": 1,
        "is_practice": bool(is_practice_flag),
    }


def record_pick(
    draft_id: str,
    round_num: int,
    pick_num: int,
    player_id: str,
    is_mine: bool = False,
    db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Record a pick in the draft."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    # Insert or replace pick (allows updating existing picks)
    cursor.execute("""
        INSERT OR REPLACE INTO picks (draft_id, round, pick_num, player_id, is_mine)
        VALUES (?, ?, ?, ?, ?)
    """, (draft_id, round_num, pick_num, player_id, 1 if is_mine else 0))

    # Log action
    cursor.execute("""
        INSERT INTO action_log (draft_id, action_type, round, player_id)
        VALUES (?, 'pick', ?, ?)
    """, (draft_id, round_num, player_id))

    # Update draft round
    cursor.execute("""
        UPDATE drafts SET current_round = ? WHERE draft_id = ?
    """, (round_num + 1, draft_id))

    conn.commit()
    conn.close()

    return {
        "draft_id": draft_id,
        "round": round_num,
        "pick_num": pick_num,
        "player_id": player_id,
        "is_mine": is_mine,
    }


def record_taken(
    draft_id: str,
    round_num: int,
    pick_num: int,
    player_id: str,
    db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Record a player taken by another drafter (does not advance round).
    Only logs action if the player was actually inserted (not a duplicate).
    Returns whether the insert occurred.
    """
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO room_taken (draft_id, player_id)
        VALUES (?, ?)
        """,
        (draft_id, player_id),
    )

    inserted = cursor.rowcount > 0

    # Only log action if actually inserted
    if inserted:
        cursor.execute(
            """
            INSERT INTO action_log (draft_id, action_type, round, player_id)
            VALUES (?, 'taken', ?, ?)
            """,
            (draft_id, round_num, player_id),
        )

    conn.commit()
    conn.close()

    return {
        "draft_id": draft_id,
        "round": round_num,
        "pick_num": pick_num,
        "player_id": player_id,
        "is_mine": False,
        "inserted": inserted,
    }


def undo_last_action(draft_id: str, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Undo the last pick or taken action in a draft."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    # Get last action
    cursor.execute("""
        SELECT id, action_type, round, player_id FROM action_log
        WHERE draft_id = ?
        ORDER BY id DESC LIMIT 1
    """, (draft_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    action_id, action_type, round_num, player_id = row

    if action_type == "pick":
        cursor.execute(
            "DELETE FROM picks WHERE draft_id = ? AND round = ?",
            (draft_id, round_num),
        )
        cursor.execute(
            "UPDATE drafts SET current_round = ? WHERE draft_id = ?",
            (round_num, draft_id),
        )
    elif action_type == "taken":
        cursor.execute(
            "DELETE FROM room_taken WHERE draft_id = ? AND player_id = ?",
            (draft_id, player_id),
        )

    cursor.execute("DELETE FROM action_log WHERE id = ?", (action_id,))

    conn.commit()
    conn.close()

    return {
        "undone": action_type,
        "round": round_num,
        "player_id": player_id,
    }


def get_draft_state(draft_id: str, db_path: Optional[Path] = None) -> Optional[DraftState]:
    """Get current state of a draft including all picks."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    # Get draft info
    cursor.execute("""
        SELECT draft_id, slot, archetype, status, current_round, total_rounds
        FROM drafts WHERE draft_id = ?
    """, (draft_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    draft_id, slot, archetype, status, current_round, total_rounds = row

    # Get my picks with player details (including bye_week, adp, signal, tier, cap_pct)
    cursor.execute("""
        SELECT p.round, p.pick_num, p.player_id, pd.name, pd.position, pd.team,
               pd.bye_week, pd.adp, pd.signal, pd.tier, pd.cap_pct
        FROM picks p
        JOIN players_dim pd ON p.player_id = pd.player_id
        WHERE p.draft_id = ? AND p.is_mine = 1
        ORDER BY p.round
    """, (draft_id,))
    my_picks = [
        {
            "round": r[0],
            "pick_num": r[1],
            "player_id": r[2],
            "name": r[3],
            "position": r[4],
            "team": r[5],
            "bye_week": r[6],
            "adp": r[7],
            "signal": r[8],
            "tier": r[9],
            "cap_pct": r[10],
        }
        for r in cursor.fetchall()
    ]

    # Get all picks (including bye_week, adp, signal, tier, cap_pct)
    cursor.execute("""
        SELECT p.round, p.pick_num, p.player_id, pd.name, pd.position, pd.team, p.is_mine,
               pd.bye_week, pd.adp, pd.signal, pd.tier, pd.cap_pct
        FROM picks p
        JOIN players_dim pd ON p.player_id = pd.player_id
        WHERE p.draft_id = ?
        ORDER BY p.round, p.pick_num
    """, (draft_id,))
    all_picks = [
        {
            "round": r[0],
            "pick_num": r[1],
            "player_id": r[2],
            "name": r[3],
            "position": r[4],
            "team": r[5],
            "is_mine": bool(r[6]),
            "bye_week": r[7],
            "adp": r[8],
            "signal": r[9],
            "tier": r[10],
            "cap_pct": r[11],
        }
        for r in cursor.fetchall()
    ]

    conn.close()

    return DraftState(
        draft_id=draft_id,
        slot=slot,
        archetype=archetype,
        status=status,
        current_round=current_round,
        total_rounds=total_rounds,
        my_picks=my_picks,
        all_picks=all_picks,
    )


def list_in_progress_drafts(db_path: Optional[Path] = None) -> list[dict[str, Any]]:
    """List all in-progress drafts."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT draft_id, slot, archetype, current_round, total_rounds, is_practice
        FROM drafts WHERE status = 'in_progress'
        ORDER BY draft_date DESC
    """)

    results = [
        {
            "draft_id": r[0],
            "slot": r[1],
            "archetype": r[2],
            "current_round": r[3],
            "total_rounds": r[4],
            "is_practice": bool(r[5]),
        }
        for r in cursor.fetchall()
    ]

    conn.close()
    return results




def complete_draft(draft_id: str, db_path: Optional[Path] = None) -> dict[str, Any]:
    """Mark a draft as complete."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE drafts SET status = 'complete' WHERE draft_id = ?",
        (draft_id,)
    )

    conn.commit()
    conn.close()

    return {"draft_id": draft_id, "status": "complete"}


def abandon_draft(
    draft_id: str,
    db_path: Optional[Path] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Delete a stale draft and all its rows. Refuses complete drafts unless force."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    # Check draft exists and status
    cursor.execute("SELECT status FROM drafts WHERE draft_id = ?", (draft_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"Draft '{draft_id}' not found")

    status = row[0]
    if status == 'complete' and not force:
        conn.close()
        raise ValueError("Refusing to abandon a complete draft (use force=True)")

    # Delete in order: picks, room_taken, action_log, drafts
    cursor.execute("DELETE FROM picks WHERE draft_id = ?", (draft_id,))
    picks_removed = cursor.rowcount

    cursor.execute("DELETE FROM room_taken WHERE draft_id = ?", (draft_id,))
    taken_removed = cursor.rowcount

    cursor.execute("DELETE FROM action_log WHERE draft_id = ?", (draft_id,))
    action_removed = cursor.rowcount

    cursor.execute("DELETE FROM drafts WHERE draft_id = ?", (draft_id,))
    drafts_removed = cursor.rowcount

    conn.commit()
    conn.close()

    return {
        "draft_id": draft_id,
        "deleted": drafts_removed > 0,
        "picks_removed": picks_removed,
        "taken_removed": taken_removed,
        "action_log_removed": action_removed,
    }


def update_draft_archetype(draft_id: str, archetype: str, db_path: Optional[Path] = None) -> dict[str, Any]:
    """Update the archetype for a draft."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE drafts SET archetype = ? WHERE draft_id = ?",
        (archetype, draft_id)
    )

    conn.commit()
    conn.close()

    return {"draft_id": draft_id, "archetype": archetype}


def get_players_by_name(name: str, db_path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Return matches by exact merge_name first, then partial matches."""
    from ceminidfs.bbm.config import PLAYER_ALIASES

    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()
    normalized = normalize_name(name)
    normalized = PLAYER_ALIASES.get(normalized, normalized)

    cursor.execute(
        """
        SELECT player_id, name, team, position, bye_week, tier, cap_pct, adp, signal, injury_fade
        FROM players_dim
        WHERE LOWER(COALESCE(merge_name, '')) = ?
        ORDER BY adp ASC, name ASC
        """,
        (normalized,),
    )
    rows = cursor.fetchall()

    if not rows:
        cursor.execute(
            """
            SELECT player_id, name, team, position, bye_week, tier, cap_pct, adp, signal, injury_fade
            FROM players_dim
            WHERE LOWER(name) LIKE ? OR LOWER(COALESCE(merge_name, '')) LIKE ?
            ORDER BY adp ASC, name ASC
            """,
            (f"%{normalized}%", f"%{normalized}%"),
        )
        rows = cursor.fetchall()

    conn.close()

    return [
        {
            "player_id": row[0],
            "name": row[1],
            "team": row[2],
            "position": row[3],
            "bye_week": row[4],
            "tier": row[5],
            "cap_pct": row[6],
            "adp": row[7],
            "signal": row[8],
            "injury_fade": bool(row[9]),
        }
        for row in rows
    ]


def get_player_by_id(player_id: str, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Fetch one players_dim row by exact player_id."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT player_id, name, team, position, bye_week, tier, cap_pct, adp, signal, injury_fade
        FROM players_dim WHERE player_id = ?
        """,
        (player_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "player_id": row[0],
        "name": row[1],
        "team": row[2],
        "position": row[3],
        "bye_week": row[4],
        "tier": row[5],
        "cap_pct": row[6],
        "adp": row[7],
        "signal": row[8],
        "injury_fade": bool(row[9]),
    }


def get_player_by_name(name: str, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Lookup player by name, preferring exact merge-name matches."""
    return resolve_player_query(name, db_path=db_path)


def ensure_player_stub(
    name: str,
    *,
    position: str | None = None,
    team: str | None = None,
    db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Create or return an idempotent hidden stub player."""

    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()
    normalized = normalize_name(name)
    player_id = _stub_player_id(name)

    cursor.execute(
        """
        SELECT player_id, name, team, position, bye_week, tier, cap_pct, adp, signal, injury_fade
        FROM players_dim
        WHERE player_id = ? OR LOWER(COALESCE(merge_name, '')) = ?
        """,
        (player_id, normalized),
    )
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            """
            INSERT OR IGNORE INTO players_dim (
                player_id, name, merge_name, team, position, bye_week,
                tier, cap_pct, adp, projection_pts, signal, injury_fade, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                player_id,
                name.strip(),
                normalized,
                team or "FA",
                position or "WR",
                0,
                "late_lottery",
                0.0,
                999.0,
                0.0,
                "NEUTRAL",
                1,
                "auto-stub",
            ),
        )
        conn.commit()
        cursor.execute(
            """
            SELECT player_id, name, team, position, bye_week, tier, cap_pct, adp, signal, injury_fade
            FROM players_dim
            WHERE player_id = ?
            """,
            (player_id,),
        )
        row = cursor.fetchone()

    conn.close()
    if row is None:
        raise RuntimeError(f"Failed to create stub player for {name!r}")
    return {
        "player_id": row[0],
        "name": row[1],
        "team": row[2],
        "position": row[3],
        "bye_week": row[4],
        "tier": row[5],
        "cap_pct": row[6],
        "adp": row[7],
        "signal": row[8],
        "injury_fade": bool(row[9]),
    }


def resolve_player_query(
    query: str,
    index: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> dict[str, Any] | None:
    """
    Resolve a player query to a player dict.

    - If query starts with digit + space (e.g. "2 Chase"), use index into get_players_by_name(rest).
      Index is 1-based.
    - Else, call get_players_by_name(query). If 1 match, return it.
      If >1 match, store the list in _last_ambiguous_matches and return None.

    Returns player dict on success, None if ambiguous or not found.
    Returns None if not found or ambiguous; never creates stubs.
    Callers that allow stubs (explicit 'taken') must call ensure_player_stub themselves.
    """
    query = query.strip()

    if index is not None:
        matches = get_players_by_name(query, db_path=db_path)
        if 1 <= index <= len(matches):
            _set_last_ambiguous_matches([])  # Clear ambiguous matches on successful index selection
            return matches[index - 1]
        return None

    # Check for digit prefix pattern: "1 Player Name" or "12 Player Name"
    index_match = re.match(r"^(\d+)\s+(.+)$", query)
    if index_match:
        index = int(index_match.group(1))
        rest = index_match.group(2).strip()
        matches = get_players_by_name(rest, db_path=db_path)
        if 1 <= index <= len(matches):
            _set_last_ambiguous_matches([])  # Clear ambiguous matches on successful index selection
            return matches[index - 1]  # Convert 1-based to 0-based
        return None

    # Normal lookup
    matches = get_players_by_name(query, db_path=db_path)

    if len(matches) == 0:
        _set_last_ambiguous_matches([])
        return None

    if len(matches) == 1:
        _set_last_ambiguous_matches([])
        return matches[0]

    # Multiple matches - store for disambiguation
    _set_last_ambiguous_matches(matches)
    return None


def list_available_players(
    limit: int = 50,
    position: Optional[str] = None,
    draft_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """List players from registry, excluding those taken in draft_id if provided."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    taken_clause = ""
    params: list[Any] = []
    if draft_id:
        taken_clause = """
            AND player_id NOT IN (
                SELECT player_id FROM picks WHERE draft_id = ? AND is_mine = 1
                UNION
                SELECT player_id FROM room_taken WHERE draft_id = ?
            )
        """
        params.extend([draft_id, draft_id])

    if position:
        cursor.execute(
            f"""
            SELECT player_id, name, team, position, bye_week, adp, signal, tier,
                   cap_pct, projection_pts, merge_name, injury_fade
            FROM players_dim
            WHERE position = ? AND injury_fade = 0 {taken_clause}
            ORDER BY adp ASC
            LIMIT ?
            """,
            [position, *params, limit],
        )
    else:
        cursor.execute(
            f"""
            SELECT player_id, name, team, position, bye_week, adp, signal, tier,
                   cap_pct, projection_pts, merge_name, injury_fade
            FROM players_dim
            WHERE injury_fade = 0 {taken_clause}
            ORDER BY adp ASC
            LIMIT ?
            """,
            [*params, limit],
        )

    results = [
        {
            "player_id": r[0],
            "name": r[1],
            "team": r[2],
            "position": r[3],
            "bye_week": r[4],
            "adp": r[5],
            "signal": r[6],
            "tier": r[7],
            "cap_pct": r[8],
            "projection_pts": r[9],
            "merge_name": r[10],
            "injury_fade": bool(r[11]),
        }
        for r in cursor.fetchall()
    ]

    conn.close()
    return results


def count_room_taken(draft_id: str, db_path: Optional[Path] = None) -> int:
    """Count players marked as taken in the draft room."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM room_taken WHERE draft_id = ?",
        (draft_id,),
    )
    count = cursor.fetchone()[0] or 0

    conn.close()
    return count


def list_room_taken_names(
    draft_id: str,
    limit: int = 5,
    db_path: Optional[Path] = None,
) -> list[str]:
    """List names of players marked as taken, up to limit."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT pd.name, pd.position, pd.team
        FROM room_taken rt
        JOIN players_dim pd ON rt.player_id = pd.player_id
        WHERE rt.draft_id = ?
        ORDER BY rt.recorded_at DESC
        LIMIT ?
        """,
        (draft_id, limit),
    )

    results = [
        f"{r[0]} {r[1]} {r[2]}" for r in cursor.fetchall()
    ]

    conn.close()
    return results


def apply_pivot(
    draft_id: str,
    new_archetype: str,
    warning: str,
    db_path: Optional[Path] = None
) -> dict[str, Any]:
    """Apply a pivot to a draft, updating archetype and storing warning."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE drafts
        SET archetype = ?, pivot_applied = 1, pivot_warning = ?
        WHERE draft_id = ?
    """, (new_archetype, warning, draft_id))

    conn.commit()
    conn.close()

    return {
        "draft_id": draft_id,
        "archetype": new_archetype,
        "pivot_applied": True,
        "warning": warning,
    }


def get_pivot_warning(draft_id: str, db_path: Optional[Path] = None) -> Optional[str]:
    """Get the pivot warning message for a draft if one exists."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT pivot_warning FROM drafts WHERE draft_id = ? AND pivot_applied = 1",
        (draft_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if row and row[0]:
        return row[0]
    return None


def is_pivot_applied(draft_id: str, db_path: Optional[Path] = None) -> bool:
    """Check if a pivot has already been applied to this draft."""
    db = db_path or get_db_path()
    conn = connect_db(db)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT pivot_applied FROM drafts WHERE draft_id = ?",
        (draft_id,)
    )
    row = cursor.fetchone()
    conn.close()

    return bool(row and row[0])
