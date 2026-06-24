"""SQLite ledger for BBM exposure tracking and draft state."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def get_db_path() -> Path:
    """Return default database path."""
    return Path("data/bbm/bbm7.db")


def init_db(path: Optional[Path | str] = None) -> Path:
    """Initialize SQLite schema; return path."""
    db_path = Path(path) if path else get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

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
            total_rounds INTEGER DEFAULT 18
        )
    """)

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

    return db_path


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
    conn = sqlite3.connect(db)
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
    return count


def exposure_pct(player_id: str, db_path: Optional[Path] = None) -> dict[str, float]:
    """
    Calculate exposure percentage for a player.
    Complete drafts count at 100%, in_progress at 50% weight.
    Returns dict with 'current', 'cap', 'available'.
    """
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Get player cap
    cursor.execute("SELECT cap_pct FROM players_dim WHERE player_id = ?", (player_id,))
    row = cursor.fetchone()
    cap = row[0] if row else 0.35  # Default 35% cap

    # Count complete drafts
    cursor.execute("""
        SELECT COUNT(DISTINCT d.draft_id)
        FROM drafts d
        JOIN picks p ON d.draft_id = p.draft_id
        WHERE p.player_id = ? AND d.status = 'complete'
    """, (player_id,))
    complete_count = cursor.fetchone()[0] or 0

    # Count in_progress drafts at 50% weight
    cursor.execute("""
        SELECT COUNT(DISTINCT d.draft_id)
        FROM drafts d
        JOIN picks p ON d.draft_id = p.draft_id
        WHERE p.player_id = ? AND d.status = 'in_progress'
    """, (player_id,))
    in_progress_count = cursor.fetchone()[0] or 0

    conn.close()

    # Calculate total drafts and exposure
    weighted = complete_count + (0.5 * in_progress_count)

    # Get total draft count
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM drafts WHERE status IN ('complete', 'in_progress')")
    total = cursor.fetchone()[0] or 1  # Avoid div by zero
    conn.close()

    exposure = weighted / total if total > 0 else 0.0

    return {
        "current": round(exposure, 3),
        "cap": cap or 0.35,
        "available": round((cap or 0.35) - exposure, 3),
    }


def combo_pct(player_a: str, player_b: str, db_path: Optional[Path] = None) -> dict[str, float]:
    """
    Calculate combo pair exposure (e.g., QB-WR stacks).
    Returns dict with 'current', 'cap', 'available'.
    """
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Get cap for this combo
    a, b = sorted([player_a, player_b])
    cursor.execute(
        "SELECT cap_pct FROM combo_pairs WHERE player_a = ? AND player_b = ?",
        (a, b)
    )
    row = cursor.fetchone()
    cap = row[0] if row else 0.25  # Default 25% combo cap

    # Count drafts where both players appear (complete only for combos)
    cursor.execute("""
        SELECT COUNT(DISTINCT p1.draft_id)
        FROM picks p1
        JOIN picks p2 ON p1.draft_id = p2.draft_id
        JOIN drafts d ON p1.draft_id = d.draft_id
        WHERE p1.player_id = ? AND p2.player_id = ? AND d.status = 'complete'
    """, (player_a, player_b))
    combo_count = cursor.fetchone()[0] or 0

    conn.close()

    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM drafts WHERE status = 'complete'")
    total = cursor.fetchone()[0] or 1
    conn.close()

    exposure = combo_count / total if total > 0 else 0.0

    return {
        "current": round(exposure, 3),
        "cap": cap,
        "available": round(cap - exposure, 3),
    }


def create_draft(
    draft_id: str,
    slot: int,
    archetype: str = "A",
    db_path: Optional[Path] = None,
    total_rounds: int = 18,
) -> dict[str, Any]:
    """Create a new draft record."""
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO drafts (draft_id, draft_date, slot, archetype, status, current_round, total_rounds)
        VALUES (?, ?, ?, ?, 'in_progress', 1, ?)
    """, (
        draft_id,
        datetime.now().isoformat(),
        slot,
        archetype,
        total_rounds,
    ))

    conn.commit()
    conn.close()

    return {
        "draft_id": draft_id,
        "slot": slot,
        "archetype": archetype,
        "status": "in_progress",
        "current_round": 1,
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
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Insert pick
    cursor.execute("""
        INSERT INTO picks (draft_id, round, pick_num, player_id, is_mine)
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
    """Record a player taken by another drafter (does not advance round)."""
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO room_taken (draft_id, player_id)
        VALUES (?, ?)
        """,
        (draft_id, player_id),
    )

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
    }


def undo_last_action(draft_id: str, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Undo the last pick or taken action in a draft."""
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
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
    conn = sqlite3.connect(db)
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

    # Get my picks with player details
    cursor.execute("""
        SELECT p.round, p.pick_num, p.player_id, pd.name, pd.position, pd.team
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
        }
        for r in cursor.fetchall()
    ]

    # Get all picks
    cursor.execute("""
        SELECT p.round, p.pick_num, p.player_id, pd.name, pd.position, pd.team, p.is_mine
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
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT draft_id, slot, archetype, current_round, total_rounds
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
        }
        for r in cursor.fetchall()
    ]

    conn.close()
    return results


def complete_draft(draft_id: str, db_path: Optional[Path] = None) -> dict[str, Any]:
    """Mark a draft as complete."""
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE drafts SET status = 'complete' WHERE draft_id = ?",
        (draft_id,)
    )

    conn.commit()
    conn.close()

    return {"draft_id": draft_id, "status": "complete"}


def get_player_by_name(name: str, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Lookup player by name (case-insensitive partial match)."""
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT player_id, name, team, position, bye_week, tier, cap_pct, adp, signal, injury_fade
        FROM players_dim
        WHERE LOWER(name) LIKE LOWER(?) OR LOWER(merge_name) LIKE LOWER(?)
        LIMIT 1
    """, (f"%{name}%", f"%{name}%"))

    row = cursor.fetchone()
    conn.close()

    if not row:
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


def list_available_players(
    limit: int = 50,
    position: Optional[str] = None,
    draft_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """List players from registry, excluding those taken in draft_id if provided."""
    db = db_path or get_db_path()
    conn = sqlite3.connect(db)
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
