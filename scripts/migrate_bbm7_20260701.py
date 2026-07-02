"""One-time migration for the 2026-07-01 audit fixes.

1. init_db() — applies is_practice ALTER + practice-% backfill.
2. Registry cleanup: drop single-token team=FA junk rows, rebuild every
   merge_name via normalize_name, upsert the 4 new seed players.
3. players_dim cleanup: delete the same junk rows from SQLite.
4. Re-sync registry -> players_dim (also re-seeds all 5 combo pairs).
5. Report remaining stub:* rows for operator review.

Usage: .venv/bin/python scripts/migrate_bbm7_20260701.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ceminidfs.bbm.ledger import (
    connect_db,
    get_db_path,
    init_db,
    sync_players_from_registry,
)
from ceminidfs.bbm.normalize_adp import normalize_name
from ceminidfs.bbm.registry import build_seed_registry, load_registry, save_registry


def _is_junk(p: dict) -> bool:
    """Check if a player is a junk FA row (single token name with team=FA)."""
    return p.get("team") == "FA" and " " not in str(p.get("name", "")).strip()


def main() -> int:
    print("=== BBM7 2026-07-01 Migration ===")
    print()

    # Step 1: Apply schema updates via init_db()
    print("Step 1: Applying schema updates (is_practice column)...")
    init_db()
    print("  ✓ Schema updated")
    print()

    # Step 2: Registry cleanup
    print("Step 2: Cleaning up registry...")
    registry = load_registry()
    players = registry.get("players", [])

    junk_registry = sum(1 for p in players if _is_junk(p))
    kept = [p for p in players if not _is_junk(p)]

    # Rebuild merge_names with unified normalizer
    for p in kept:
        p["merge_name"] = normalize_name(str(p.get("name", "")))

    # Check for new seed players
    by_merge = {p["merge_name"] for p in kept}
    new_seeds = 0
    for seed in build_seed_registry()["players"]:
        if seed["merge_name"] not in by_merge:
            kept.append(seed)
            new_seeds += 1

    registry["players"] = sorted(kept, key=lambda p: float(p.get("adp", 9999)))
    registry.setdefault("meta", {})["player_count"] = len(kept)
    save_registry(registry)
    print(f"  ✓ Removed {junk_registry} junk registry rows")
    print(f"  ✓ Added {new_seeds} new seed players")
    print(f"  ✓ Registry now has {len(kept)} players")
    print()

    # Step 3: players_dim cleanup
    print("Step 3: Cleaning up players_dim...")
    conn = connect_db(get_db_path())
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM players_dim WHERE player_id LIKE 'bbm:%' AND team = 'FA' AND name NOT LIKE '% %'"
    )
    junk_deleted = cur.rowcount
    conn.commit()
    print(f"  ✓ Deleted {junk_deleted} junk rows from players_dim")
    print()

    # Step 4: Re-sync registry -> players_dim
    print("Step 4: Re-syncing registry to players_dim...")
    count = sync_players_from_registry(registry)
    print(f"  ✓ Synced {count} players")
    print()

    # Step 5: Report remaining stubs
    print("Step 5: Remaining stub rows (review recommended)...")
    stubs = cur.execute(
        "SELECT player_id, name FROM players_dim WHERE player_id LIKE 'stub:%'"
    ).fetchall()
    conn.close()

    if stubs:
        print(f"  ! {len(stubs)} stub rows remain:")
        for pid, name in stubs:
            print(f"      {pid}  {name}")
    else:
        print("  ✓ No stub rows found")
    print()

    # Summary
    print("=== Migration Complete ===")
    print(f"  Registry:     -{junk_registry} junk, +{new_seeds} new seeds")
    print(f"  players_dim:  -{junk_deleted} junk, {count} total players")
    print()
    print("Backup commands (run manually if needed):")
    print("  cp data/bbm/bbm7.db data/bbm/bbm7.db.bak-20260701")
    print("  cp data/bbm/player_registry.json data/bbm/player_registry.json.bak-20260701")

    return 0


if __name__ == "__main__":
    sys.exit(main())
