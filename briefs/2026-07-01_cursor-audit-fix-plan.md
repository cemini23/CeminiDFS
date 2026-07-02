# Cursor audit fix plan — CeminiDFS patch sprint (all 15 fixes)

**Date:** 2026-07-01
**Status:** ✅ **SHIPPED** — 297 tests pass, extension v1.2.0
**Source audit:** `briefs/2026-07-01_cursor-audit-synthesis.md` (verdict: REWORK — do not enter paid BBM until P0 1–6 land)
**Base:** `main` @ `ccc7171` — tests at audit: 220 passed, 1 skipped
**Executors:** 3 parallel subagents (WS-A, WS-B, WS-C), zero file overlap, merged sequentially A → B → C.

---

## 0. Fix traceability (audit # → workstream)

| # | Fix | Pri | Workstream | Files touched |
|---|-----|-----|-----------|---------------|
| 1 | Unify normalizers | P0 | **A** | `registry.py` |
| 2 | Strict pick resolution (no auto-stub) | P0 | **A** (ledger) + **B** (callers' messaging) | `ledger.py`, `api_server.py`, `cli.py`, `practice.py` |
| 3 | Remove junk FA seed rows | P0 | **A** (registry) + **B** (recommender FA exclusion) | `registry.py`, `config.py`, `recommender.py` |
| 4 | Fix extension sync contract, wire `board_parse.py` | P0 | **B** (server) + **C** (content.js) | `api_server.py`, `content.js` |
| 5 | Practice draft isolation (`is_practice`) | P0 | **A** (schema+queries) + **B** (session/cli/practice) | `ledger.py`, `reconcile.py`, `session.py`, `cli.py`, `practice.py` |
| 6 | Fix practice resume (include `room_taken`) | P0 | **B** | `practice.py` |
| 7 | Buzz/ESPN degrade gracefully | P1 | **C** | `pipeline/project.py` |
| 8 | `combo_pct` in-progress weighting | P1 | **A** | `ledger.py` |
| 9 | Keep `injury_status` in roster DataFrame | P1 | **C** | `pipeline/engine.py` |
| 10 | Centralize schedule data (W17 + byes) | P1 | **A** (schedule/config) + **B** (recommender delegate) | `schedule.py`, `config.py`, `recommender.py` |
| 11 | Recreate `.venv` | P1 | ops (Phase 0, WS-A executor) | none (environment) |
| 12 | `/api/undo` + extension button + `bbm abandon` | P2 | **A** (ledger fn) + **B** (API/CLI) + **C** (button) | `ledger.py`, `api_server.py`, `cli.py`, `content.js` |
| 13 | Advisory pivots + real RB-run check | P2 | **B** | `session.py`, `archetype.py`, `api_server.py` |
| 14 | Combo cap rounding (raw compare) | P2 | **A** | `ledger.py` |
| 15 | Localhost POST token | P2 | **B** (server/CLI) + **C** (extension) | `api_server.py`, `cli.py`, `popup.js`, `popup.html`, `content.js` |

**File ownership (hard rule — no workstream edits another's files):**

- **WS-A:** `src/ceminidfs/bbm/ledger.py`, `src/ceminidfs/bbm/registry.py`, `src/ceminidfs/bbm/reconcile.py`, `src/ceminidfs/bbm/schedule.py`, `src/ceminidfs/bbm/config.py`, `docs/BBM-EXPOSURE.md`, `scripts/migrate_bbm7_20260701.py` (new), `tests/bbm/conftest.py` (new), `tests/bbm/test_identity_exposure.py` (new)
- **WS-B:** `src/ceminidfs/bbm/api_server.py`, `src/ceminidfs/bbm/session.py`, `src/ceminidfs/bbm/cli.py`, `src/ceminidfs/bbm/practice.py`, `src/ceminidfs/bbm/recommender.py`, `src/ceminidfs/bbm/archetype.py`, `tests/bbm/test_api_contracts.py` (new), `tests/bbm/test_practice_and_pivots.py` (new)
- **WS-C:** `extension/bbm-copilot/content.js`, `extension/bbm-copilot/popup.js`, `extension/bbm-copilot/popup.html`, `extension/bbm-copilot/manifest.json`, `src/ceminidfs/pipeline/project.py`, `src/ceminidfs/pipeline/engine.py`, `tests/test_pipeline_resilience.py` (new)

Nobody edits `tests/bbm/test_bbm_core.py` (no existing test in it breaks under these changes; if one does, the owning workstream reports it rather than editing the shared file — see §8).

---

## 1. Interface contracts (agree before coding; B and C build against these)

WS-B and WS-C may start in parallel with WS-A, but their tests only fully pass after rebasing onto A (then B). These contracts are frozen:

1. **`ledger.resolve_player_query(query, index=None, db_path=None)`** — signature unchanged. New behavior: on **zero matches returns `None`** (never stubs). `get_last_ambiguous_matches()` returns `[]` for not-found, `>1` items for ambiguous. Explicit stub creation remains via `ledger.ensure_player_stub(name, ...)` (unchanged).
2. **`ledger.create_draft(draft_id, slot, archetype="A", db_path=None, total_rounds=18, is_practice=False)`** — new keyword arg. Also force-sets `is_practice=1` when `draft_id.startswith("practice-")` regardless of arg.
3. **`ledger.abandon_draft(draft_id, db_path=None, force=False) -> dict`** — deletes the draft and its `picks` / `room_taken` / `action_log` rows. Refuses `status='complete'` drafts unless `force=True` (raises `ValueError`). Returns `{"draft_id", "deleted": True, "picks_removed": int, "taken_removed": int}`.
4. **`schedule.get_week17_matchups() -> list[tuple[str, str]]`** and **`schedule.are_opponents_week17(team_a, team_b) -> bool`** — new functions in `schedule.py`.
5. **`config.get_bye_week` / `config.BYE_WEEKS`** — still importable from `ceminidfs.bbm.config` (re-exported from `schedule`).
6. **HTTP API:**
   - `POST /api/sync` body: `{draft_id, names?: string[], labels?: string[]}`. `labels` are raw aria-label strings, parsed server-side via `board_parse`. Response unchanged plus accurate `unmatched` (no stubs ever created by sync).
   - `POST /api/pick` — unknown name → `404 {"error": "Player not found: <name>"}` (no stub).
   - `POST /api/taken` — unknown name → stub created, response includes `"is_stub": true, "warning": "Unknown player '<name>' recorded as stub — verify spelling"`.
   - `POST /api/undo` body `{draft_id}` → `200 {"undone": "pick"|"taken", "round": int, "player_id": str}` or `404 {"error": "Nothing to undo"}`.
   - `POST /api/pivot` body `{draft_id, archetype}` (A–E) → applies pivot explicitly.
   - `GET /api/recommendations` response gains top-level `"pivot_warning": str|null`. GET **never writes** to the DB.
   - Auth: if server started with a token, all POST endpoints require header `X-BBM-Token: <token>`; missing/wrong → `401 {"error": "Unauthorized"}`. GETs stay open.

---

## 2. Workstream A — “Ledger & identity core” (P0 #1, #2-core, #3-registry, #5-core, #8, #10-data, #12-ledger, #14)

### A1. Unify normalizers (fix #1) — `src/ceminidfs/bbm/registry.py`

Replace the body of `_normalize_merge` (lines 68–69) to delegate:

```python
from ceminidfs.bbm.normalize_adp import normalize_name

def _normalize_merge(name: str) -> str:
    return normalize_name(name)
```

Keep the function (3 internal call sites use it). Consequences to verify in tests: `"Amon-Ra St. Brown"` → `"amon ra st brown"` (hyphen split), `"Brian Thomas Jr."` → `"brian thomas"` (suffix stripped), `"Jaxon Smith-Njigba"` → `"jaxon smith njigba"`. Player IDs (`_slug_id`) are unchanged, so `sync_players_from_registry`'s `INSERT OR REPLACE` updates `merge_name` in place.

**Known bonus fix:** `_seed_combo_pairs_from_config` currently fails to seed the `Trevor Lawrence / Brian Thomas Jr.` pair (`"brian thomas jr"` ≠ `normalize_name(...)` = `"brian thomas"`). After A1, all 5 `STACK_PAIRS` seed. Assert count == 5 in tests.

### A2. Strict pick resolution (fix #2, ledger side) — `src/ceminidfs/bbm/ledger.py`

In `resolve_player_query` (lines 860–864), change the zero-match branch:

```python
    if len(matches) == 0:
        _set_last_ambiguous_matches([])
        return None
```

Delete the `ensure_player_stub(query, db_path=db_path)` call. Update the docstring: "Returns None if not found or ambiguous; never creates stubs. Callers that allow stubs (explicit 'taken') must call ensure_player_stub themselves." `ensure_player_stub` itself is unchanged. Run `rg "get_player_by_name\(" src tests` to confirm no caller depends on the old stub-on-miss behavior of the wrapper (as of `ccc7171` there are none).

### A3. Remove junk FA seed rows + aliases (fix #3, registry side) — `src/ceminidfs/bbm/registry.py`, `src/ceminidfs/bbm/config.py`

1. **Delete** the surname `buy_names` loop and the `FADE_PLAYERS` loop in `build_seed_registry` (lines 185–225 — from `# Ensure named BUY lists appear...` through the end of the fade loop). These currently create ~35 single-token `team="FA"` rows (kelce, hurts, chase, bowers, mcbride, aiyuk, jsn, mcmillan, cooper, boston, …) that hijack exact-merge lookup and are recommendable late-round.
2. **Add** the 4 real players the surname lists covered that are missing from `_SEED_PLAYERS` (append to `_SEED_PLAYERS`; ADP values are placeholders refreshed weekly by `refresh-adp`):

```python
    {"name": "Tetairoa McMillan", "position": "WR", "team": "CAR", "adp": 33.0, "tier": "stack_core", "signal": "BUY", "projection_pts": 186},
    {"name": "Oronde Gadsden II", "position": "TE", "team": "LAC", "adp": 138.0, "tier": "mid_target", "signal": "BUY", "projection_pts": 112},
    {"name": "Brenton Strange", "position": "TE", "team": "JAX", "adp": 142.0, "tier": "late_lottery", "signal": "BUY", "projection_pts": 106},
    {"name": "Chig Okonkwo", "position": "TE", "team": "TEN", "adp": 150.0, "tier": "late_lottery", "signal": "BUY", "projection_pts": 104},
```

3. The rookie-WR watchlist (`Cooper, Boston, Concepcion, Branch, Hurst`) is **dropped from seeding** — ambiguous surnames with no canonical row. They enter the registry via `refresh-adp` CSV (full names + real ADP). Keep the `BUY_ROOKIE_WR_MAY_JUN` list in `config.py` (still referenced by `ROUND_BAND_RULES` docs).
4. **Aliases for initialisms** (surname LIKE-fallback in `get_players_by_name` already handles "kelce" etc. once junk rows are gone; only initialisms need help). In `config.py` add:

```python
# Query aliases: normalized query -> canonical merge_name (applied in ledger.get_players_by_name)
PLAYER_ALIASES: Dict[str, str] = {
    "jsn": "jaxon smith njigba",
    "arsb": "amon ra st brown",
}
```

   In `ledger.get_players_by_name`, after `normalized = normalize_name(name)` add:

```python
    from ceminidfs.bbm.config import PLAYER_ALIASES  # module-top import is fine too
    normalized = PLAYER_ALIASES.get(normalized, normalized)
```

(FA-exclusion from recommendations is WS-B's `recommender.py` change, B3.)

### A4. Practice isolation schema + exposure queries (fix #5, core) — `src/ceminidfs/bbm/ledger.py`, `src/ceminidfs/bbm/reconcile.py`

1. **`init_db`** — after the existing pivot ALTER block (lines 102–110), add the same ALTER-safe pattern:

```python
    try:
        cursor.execute("ALTER TABLE drafts ADD COLUMN is_practice INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    cursor.execute(
        "UPDATE drafts SET is_practice = 1 "
        "WHERE draft_id LIKE 'practice-%' AND (is_practice IS NULL OR is_practice = 0)"
    )
```

2. **`create_draft`** — new signature (contract #2):

```python
def create_draft(
    draft_id: str,
    slot: int,
    archetype: str = "A",
    db_path: Optional[Path] = None,
    total_rounds: int = 18,
    is_practice: bool = False,
) -> dict[str, Any]:
```

INSERT gains the column: `... status, current_round, total_rounds, is_practice) VALUES (?, ?, ?, ?, 'in_progress', 1, ?, ?)` with `1 if (is_practice or draft_id.startswith("practice-")) else 0`. Include `"is_practice"` in the returned dict.

3. **`exposure_pct`** — add `AND d.is_practice = 0` to both COUNT queries (complete at line ~302, in_progress at line ~311).
4. **`combo_pct`** — rewrite the counting query to add practice filter AND in-progress weighting (fix #8) AND drop rounding (fix #14):

```python
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
    weighted = complete_count + (IN_PROGRESS_EXPOSURE_WEIGHT * in_progress_count)
    exposure = weighted / TOTAL_ENTRIES
    return {"current": exposure, "cap": cap, "available": cap - exposure}
```

   No `round()` anywhere — raw floats out (display sites already format with `:.0%`). This unblocks Codex's finding that 0.2495 rounded to 0.25 and got pruned at the cap prematurely.
5. **`list_in_progress_drafts`** — add `is_practice` to the SELECT and returned dicts (used by `bbm abandon --list` in WS-B).
6. **`reconcile.py` `reconcile_from_csv`** — the ledger-count query (lines 417–426) gains `AND d.is_practice = 0` in the WHERE clause.
7. **`docs/BBM-EXPOSURE.md`** — add one line under the policy list: `- Practice drafts (is_practice = 1, draft_id 'practice-*') are excluded from all exposure, combo, portfolio-gap, and reconcile math.`

### A5. Centralize schedule data (fix #10, data side) — `src/ceminidfs/bbm/schedule.py`, `src/ceminidfs/bbm/config.py`

1. **`schedule.py`** — append:

```python
# 2026 Week 17 matchups (BBM championship week). Refresh each season;
# TODO(K-next): fetch from nflreadpy schedules instead of hardcoding.
WEEK17_MATCHUPS_2026: Final[list[tuple[str, str]]] = [
    ("KC", "DEN"), ("CAR", "TB"), ("CIN", "PIT"), ("MIA", "NYJ"),
    ("DET", "SF"), ("MIN", "GB"), ("BUF", "NE"), ("LAC", "LV"),
    ("WAS", "DAL"), ("JAX", "TEN"), ("NYG", "IND"), ("NO", "ARI"),
    ("HOU", "BAL"), ("CHI", "SEA"), ("PHI", "ATL"), ("CLE", "LAR"),
]


def get_week17_matchups() -> list[tuple[str, str]]:
    """Return W17 matchup pairs for bring-back stacking."""
    return list(WEEK17_MATCHUPS_2026)


def are_opponents_week17(team_a: str, team_b: str) -> bool:
    """True if the two teams play each other in Week 17."""
    a, b = team_a.strip().upper(), team_b.strip().upper()
    return any({a, b} == {t1, t2} for t1, t2 in WEEK17_MATCHUPS_2026)
```

2. **`config.py`** — delete the literal `BYE_WEEKS` dict (lines 58–68) and the `get_bye_week` function at the bottom (lines 320–322); replace with re-exports so all existing importers (`registry.py`, `session.py`, tests) keep working:

```python
from ceminidfs.bbm.schedule import BYE_WEEKS_2026 as BYE_WEEKS, get_bye_week
```

   (No circular import: `schedule.py` imports only `typing`.) Verify the two dicts are identical before deleting — they are at `ccc7171` (32 teams, same weeks).

### A6. `abandon_draft` (fix #12, ledger side) — `src/ceminidfs/bbm/ledger.py`

New function (contract #3), placed near `complete_draft`:

```python
def abandon_draft(
    draft_id: str,
    db_path: Optional[Path] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Delete a stale draft and all its rows. Refuses complete drafts unless force."""
```

Implementation: SELECT status; raise `ValueError(f"Draft '{draft_id}' not found")` if missing; raise `ValueError("Refusing to abandon a complete draft (use force=True)")` if complete and not force. Then `DELETE FROM picks / room_taken / action_log / drafts WHERE draft_id = ?` (that order), commit, return counts via `cursor.rowcount` captured per delete.

### A7. Migration script (fix #5 backfill + #1/#3 data cleanup) — `scripts/migrate_bbm7_20260701.py` (new)

One-time, idempotent, run against the live DB after WS-A merges:

```python
"""One-time migration for the 2026-07-01 audit fixes.

1. init_db() — applies is_practice ALTER + practice-% backfill.
2. Registry cleanup: drop single-token team=FA junk rows, rebuild every
   merge_name via normalize_name, upsert the 4 new seed players.
3. players_dim cleanup: delete the same junk rows from SQLite.
4. Re-sync registry -> players_dim (also re-seeds all 5 combo pairs).
5. Report remaining stub:* rows for operator review.

Usage: .venv/bin/python scripts/migrate_bbm7_20260701.py
"""
```

Steps in code:

```python
from ceminidfs.bbm.ledger import connect_db, get_db_path, init_db, sync_players_from_registry
from ceminidfs.bbm.normalize_adp import normalize_name
from ceminidfs.bbm.registry import build_seed_registry, load_registry, save_registry

init_db()
registry = load_registry()
players = registry.get("players", [])

def _is_junk(p):
    return p.get("team") == "FA" and " " not in str(p.get("name", "")).strip()

junk_registry = sum(1 for p in players if _is_junk(p))
kept = [p for p in players if not _is_junk(p)]
for p in kept:
    p["merge_name"] = normalize_name(str(p.get("name", "")))
by_merge = {p["merge_name"] for p in kept}
for seed in build_seed_registry()["players"]:
    if seed["merge_name"] not in by_merge:          # picks up the 4 new adds
        kept.append(seed)
registry["players"] = sorted(kept, key=lambda p: float(p.get("adp", 9999)))
registry.setdefault("meta", {})["player_count"] = len(kept)
save_registry(registry)

conn = connect_db(get_db_path())
cur = conn.cursor()
cur.execute("DELETE FROM players_dim WHERE player_id LIKE 'bbm:%' AND team = 'FA' AND name NOT LIKE '% %'")
junk_deleted = cur.rowcount
conn.commit()
stubs = cur.execute("SELECT player_id, name FROM players_dim WHERE player_id LIKE 'stub:%'").fetchall()
conn.close()

sync_players_from_registry(registry)
print(f"Removed {junk_registry} junk registry rows, {junk_deleted} players_dim rows")
print(f"{len(stubs)} stub rows remain (review):")
for pid, name in stubs:
    print(f"  {pid}  {name}")
```

**Standalone SQL** (equivalent manual path, documented for the operator; the script is preferred):

```sql
-- data/bbm/bbm7.db  (back up first: cp data/bbm/bbm7.db data/bbm/bbm7.db.bak-20260701)
ALTER TABLE drafts ADD COLUMN is_practice INTEGER DEFAULT 0;
UPDATE drafts SET is_practice = 1 WHERE draft_id LIKE 'practice-%';
DELETE FROM players_dim WHERE player_id LIKE 'bbm:%' AND team = 'FA' AND name NOT LIKE '% %';
```

### A8. Shared test fixture — `tests/bbm/conftest.py` (new)

Copy the `bbm_db` fixture from `test_bbm_core.py` verbatim into a new `tests/bbm/conftest.py` (module-level fixture, same name). `test_bbm_core.py` keeps its local copy (pytest prefers the local definition; no conflict, no edit to the shared file). WS-B's new test files use the conftest fixture.

### A9. Tests — `tests/bbm/test_identity_exposure.py` (new)

| Test | Asserts |
|------|---------|
| `test_normalizer_parity_hyphen_suffix` | `registry._normalize_merge(n) == normalize_name(n)` for `"Amon-Ra St. Brown"`, `"Jaxon Smith-Njigba"`, `"Brian Thomas Jr."`, `"De'Von Achane"`, `"C.J. Stroud"` |
| `test_seed_registry_has_no_junk_fa_rows` | `build_seed_registry()` has zero players with `team == "FA"` and single-token name; the 4 new players present with correct teams |
| `test_hyphen_elite_resolves` (uses `bbm_db`) | `resolve_player_query("Jaxon Smith-Njigba")` and `("JSN")` and `("Amon-Ra St. Brown")` each return the canonical player, not `None`, not a stub |
| `test_surname_resolves_after_junk_removal` | `resolve_player_query("Kelce")` returns Travis Kelce (unique LIKE match) |
| `test_resolve_unknown_returns_none_no_stub` | `resolve_player_query("Xyzzy Qwerty")` is `None`; `players_dim` contains no `stub:xyzzy-qwerty` row; `get_last_ambiguous_matches() == []` |
| `test_all_stack_pairs_seed` | after fixture sync, `SELECT COUNT(*) FROM combo_pairs` == 5 |
| `test_exposure_excludes_practice` | complete `practice-x` draft with a pick → `exposure_pct(pid)["current"] == 0.0`; same pick in a real complete draft → `1/150` |
| `test_combo_pct_weights_in_progress` | pair in 1 complete + 1 in-progress real draft → `current == (1 + 0.5) / 150`; practice draft with same pair adds nothing |
| `test_combo_pct_returns_raw` | craft counts so exposure = 37/150 = 0.24666…; assert `combo_pct(...)["current"] == pytest.approx(37/150)` exactly (not 0.247) |
| `test_create_draft_practice_flag` | `create_draft("practice-t", 1, "A", db_path=db)` row has `is_practice = 1`; plain draft has 0 |
| `test_abandon_draft` | create draft + pick + taken; `abandon_draft` removes all rows; complete draft raises `ValueError` without `force` |
| `test_reconcile_excludes_practice` | ledger-count query path: practice complete draft pick absent from `reconcile_from_csv` counts (use a minimal CSV fixture in tmp_path) |
| `test_schedule_w17_and_bye_parity` | `are_opponents_week17("KC","DEN")` True, `("KC","CAR")` False; `config.get_bye_week("KC") == 5`; `config.BYE_WEEKS is schedule.BYE_WEEKS_2026` |

---

## 3. Workstream B — “Server, session & CLI” (P0 #2-callers, #3-recommender, #4-server, #5-consumers, #6; P2 #12-API/CLI, #13, #15-server)

Depends on WS-A contracts (§1). Rebase on A before final test run.

### B1. Strict resolution messaging (fix #2, caller side)

- **`api_server.py` `_handle_pick`** (lines 329–390): no structural change needed — after A2, `resolve_player_query` returns `None` for unknowns and the existing `404 Player not found` branch fires. Add a comment noting stubs are intentionally never created on pick.
- **`api_server.py` `_handle_taken`** (lines 392–458): keep the explicit `ensure_player_stub(name)` fallback, and extend the response dict with `"warning": f"Unknown player '{name}' recorded as stub — verify spelling"` when `is_stub` is true (contract #6).
- **`cli.py` REPL `t` command** (lines 234–254): after `ensure_player_stub`, change the print to `print(f"  -> WARNING: unknown player — created stub for: {arg} (verify spelling)")`.
- **`practice.py` `t` command** (lines 177–198): same warning wording.
- No changes to `p` / `sync` handlers — they already treat `None` as not-found/unmatched; behavior flips automatically from A2.

### B2. Extension sync contract, server side (fix #4) — `src/ceminidfs/bbm/api_server.py`

`_handle_sync(body)` (lines 257–327) gains `labels` support, wiring the tested-but-dead `board_parse.py` into production:

```python
        names = body.get("names", [])
        labels = body.get("labels", [])
        if not isinstance(names, list) or not isinstance(labels, list):
            self._send_error("names/labels must be arrays", status=400)
            return
        if labels:
            board_parse = _get_board_parse()
            parsed = board_parse.extract_names_from_aria_labels(
                [l for l in labels if isinstance(l, str)]
            )
            names = list(names) + board_parse.filter_draft_board_names(parsed)
```

`_get_board_parse()` already exists (line 28). The per-name loop is unchanged — with A2 in place, unknown names land in `unmatched` (never stubbed). Cap processing at 200 names per request (`names = names[:200]`).

### B3. FA + stub exclusion from recommendations (fix #3, recommender side) — `src/ceminidfs/bbm/recommender.py`

In `_prefilter_candidates` (lines 299–302), extend the stub skip:

```python
        # Skip stubs and team-less FA rows (no team/bye data — cannot validate constraints)
        if player.player_id.startswith("stub:"):
            continue
        if not player.team or player.team == "FA":
            continue
```

Documented side effect: unmatched ADP-import rows (team="FA", NEUTRAL) are also excluded until they get a real team via registry refresh — this is the audit's intent.

Also in `recommender.py` (fix #10, delegate side): delete `_get_w17_matchups` (lines 185–194) and `_are_opponents` (lines 197–202), and rewrite `_is_w17_bringback` (lines 165–182) to use WS-A's schedule module — also removing the vestigial `player_week`/`roster_player_week` locals:

```python
from ceminidfs.bbm.schedule import are_opponents_week17


def _is_w17_bringback(player: Player, roster: Roster) -> bool:
    """Check if player is in a W17 bring-back matchup against a roster player."""
    return any(
        are_opponents_week17(player.team, roster_player.team)
        for roster_player in roster.players
        if roster_player.team and player.team
    )
```

`_calculate_stack_mult`'s round-10+ gate is unchanged.

### B4. Practice consumers of `is_practice` (fix #5, consumer side)

- **`practice.py` `run_practice_draft`** (line 94): `create_draft(draft_id, slot, archetype, total_rounds=rounds, is_practice=True)`.
- **`session.py` `archetype_gap_pct`** (lines 249–253): query becomes `SELECT COUNT(*) FROM drafts WHERE archetype = ? AND status = 'complete' AND is_practice = 0`.
- **`cli.py` `_suggest_archetype`** (lines 366–368): add `AND is_practice = 0` to the GROUP BY query.

### B5. Practice resume (fix #6) — `src/ceminidfs/bbm/practice.py`

Extract a pure, testable helper and use it in the resume branch (replacing lines 87–91's broken `total_picks` math, which reduces to `len(all_picks)` and misses all `room_taken` opponent picks):

```python
from ceminidfs.bbm.ledger import count_room_taken
from ceminidfs.bbm.session import get_taken_player_ids


def _resume_state(draft_id: str) -> tuple[int, set[str]]:
    """Return (next overall pick number, taken player ids) for a resumed draft.

    Picks consumed = my/recorded picks rows + room_taken rows (disjoint in practice flow).
    """
    state = get_draft_state(draft_id)
    if state is None:
        raise ValueError(f"Draft '{draft_id}' not found")
    taken_ids = {p["player_id"] for p in state.all_picks} | get_taken_player_ids(draft_id)
    picks_consumed = len(state.all_picks) + count_room_taken(draft_id)
    return picks_consumed + 1, taken_ids
```

In `run_practice_draft`: resume branch sets `current_pick_num, taken_ids = _resume_state(draft_id)`; the fresh-draft branch keeps `current_pick_num = 1`. Delete the now-dead `total_picks` variable and the later `taken_ids` rebuild (lines 104–111) for the resume path (keep it for fresh drafts, or unify through `_resume_state` — either is fine as long as resume includes room_taken).

### B6. `/api/undo`, `/api/pivot`, `bbm abandon` (fixes #12, #13-ack)

- **`api_server.py` `do_POST`** routing (lines 127–137): add `elif path == "/api/undo": self._handle_undo(body)` and `elif path == "/api/pivot": self._handle_pivot(body)`.

```python
    def _handle_undo(self, body: dict[str, Any]) -> None:
        """POST /api/undo JSON {draft_id} -> undo last pick/taken action."""
        draft_id = body.get("draft_id") or self.config.draft_id
        if not draft_id:
            self._send_error("Missing draft_id", status=400)
            return
        result = _get_ledger().undo_last_action(draft_id)
        if result is None:
            self._send_error("Nothing to undo", status=404)
            return
        self._send_json_response({"draft_id": draft_id, **result})

    def _handle_pivot(self, body: dict[str, Any]) -> None:
        """POST /api/pivot JSON {draft_id, archetype} -> explicitly apply archetype pivot."""
        draft_id = body.get("draft_id") or self.config.draft_id
        archetype = str(body.get("archetype", "")).upper()
        if not draft_id:
            self._send_error("Missing draft_id", status=400)
            return
        if archetype not in ("A", "B", "C", "D", "E"):
            self._send_error("archetype must be A-E", status=400)
            return
        result = _get_ledger().apply_pivot(draft_id, archetype, f"manual pivot to {archetype}")
        self._send_json_response(result)
```

- **`cli.py`** — new `abandon` subcommand. `build_bbm_parser` gains:

```python
    abandon_parser = subparsers.add_parser("abandon", help="Delete a stale in-progress draft")
    abandon_parser.add_argument("--draft-id", type=str, default=None, help="Draft to delete (omit to list)")
    abandon_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    abandon_parser.add_argument("--force", action="store_true", help="Allow deleting a complete draft")
```

`handler_map` gains `"abandon": _cmd_abandon`:

```python
def _cmd_abandon(args: argparse.Namespace) -> int:
    ensure_initialized()
    if not args.draft_id:
        drafts = list_in_progress_drafts()
        if not drafts:
            print("No in-progress drafts.")
            return 0
        for d in drafts:
            tag = " [practice]" if d.get("is_practice") else ""
            print(f"  {d['draft_id']}  slot {d['slot']}  R{d['current_round']}/{d['total_rounds']}{tag}")
        print("Re-run with --draft-id <id> to delete one.")
        return 0
    if not args.yes:
        confirm = input(f"Delete draft {args.draft_id} and all its picks? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return 1
    try:
        result = abandon_draft(args.draft_id, force=args.force)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Deleted {args.draft_id} ({result['picks_removed']} picks, {result['taken_removed']} taken)")
    return 0
```

Add `abandon_draft, list_in_progress_drafts` to the `ceminidfs.bbm.ledger` import block, and `abandon` to the "Available:" help string in `handle_bbm_command`.

### B7. Advisory pivots + real RB-run check (fix #13) — `src/ceminidfs/bbm/session.py`, `src/ceminidfs/bbm/archetype.py`, `src/ceminidfs/bbm/api_server.py`

- **`session.get_recommendations`** (lines 191–204): delete the `apply_pivot(...)` call. Keep the in-memory archetype override so the recs shown reflect the suggested pivot, but the DB is never written on a read:

```python
    pivot_warning = None
    if pivot_result.new_archetype and not is_pivot_applied(draft_id):
        pivot_warning = (
            (pivot_result.warning or f"Pivot to {pivot_result.new_archetype.value}")
            + f" — advisory only; confirm with 'archetype {pivot_result.new_archetype.value}' or POST /api/pivot"
        )
        draft_state.archetype = pivot_result.new_archetype
```

  Remove the now-unused `apply_pivot` import. `is_pivot_applied` stays (suppresses the advisory once operator explicitly pivots via `/api/pivot`, which sets `pivot_applied=1`).
- **`api_server._handle_recommendations`** (lines 249–255): include the advisory in the payload: `"pivot_warning": recs[0].get("pivot_warning") if recs else None` (add before `"recommendations"`).
- **`archetype._is_rb_run_happening`** (lines 200–205) — replace the `return round_num >= 5` stub with a board-based check:

```python
def _is_rb_run_happening(board: List[Player], round_num: int) -> bool:
    """RB run = RBs who should still be on the board (by ADP) are nearly exhausted.

    picks_elapsed approximates total picks made so far in a 12-team room.
    """
    picks_elapsed = round_num * 12
    remaining_early_rbs = [
        p for p in board if p.position == "RB" and p.adp <= picks_elapsed
    ]
    return len(remaining_early_rbs) <= 2
```

### B8. POST token (fix #15, server side) — `src/ceminidfs/bbm/api_server.py`, `src/ceminidfs/bbm/cli.py`

- `ServerConfig` gains `token: Optional[str] = None`.
- `do_POST` first lines:

```python
        if self.config.token:
            if self.headers.get("X-BBM-Token") != self.config.token:
                self._send_error("Unauthorized", status=401)
                return
```

- `_set_cors_headers`: `Access-Control-Allow-Headers` becomes `"Content-Type, X-BBM-Token"`.
- `create_server(..., token: Optional[str] = None)` and `run_server(..., token: Optional[str] = None)` thread it through; `__main__` argparse gains `--token`.
- `cli.py` serve parser: `serve_parser.add_argument("--token", type=str, default=None, help="Optional static token required on POST endpoints (X-BBM-Token header)")`; `_cmd_serve` passes it to `run_server` and, when set, prints `  token   = <token>  (set in extension popup)`.

### B9. Tests

**`tests/bbm/test_api_contracts.py`** (new; server-thread pattern from `test_bbm_core.test_api_health`, ports 18770+, one port per test):

| Test | Asserts |
|------|---------|
| `test_pick_unknown_404_no_stub` | POST /api/pick `{"name": "Xyzzy Qwerty"}` → 404; no `stub:` row created |
| `test_taken_unknown_stubs_with_warning` | POST /api/taken unknown → 200, `is_stub` true, `warning` contains "verify spelling"; `room_taken` row exists |
| `test_sync_labels_via_board_parse` | POST /api/sync `{"labels": ["Select Ja'Marr Chase, WR, CIN", "draft pick", "Pick Puka Nacua"]}` → synced_count 2, noise filtered, unmatched empty |
| `test_sync_unknown_reports_unmatched_no_stub` | names `["Ghost Player"]` → unmatched `["ghost player"]`-ish, synced 0, zero stub rows |
| `test_undo_endpoint` | pick then POST /api/undo → 200 undone "pick", round reverted (`/api/state` current_round back to 1); second undo of empty log → 404 |
| `test_recommendations_get_is_readonly` | archetype D draft, round ≥ 6 (record 5 picks), elite RBs marked taken → GET /api/recommendations twice: `pivot_warning` non-null both times, `drafts.pivot_applied` still 0 in SQLite |
| `test_pivot_endpoint_applies` | POST /api/pivot `{archetype: "B"}` → drafts row has archetype B, pivot_applied 1; subsequent GET has `pivot_warning` null |
| `test_post_token_enforced` | server with `token="s3cret"`: POST /api/pick without header → 401; with header → normal flow; GET /api/state without header → 200 |

**`tests/bbm/test_practice_and_pivots.py`** (new):

| Test | Asserts |
|------|---------|
| `test_resume_state_includes_room_taken` | create `practice-r1`: 1 `record_pick` (mine) + 11 `record_taken` → `_resume_state` returns `(13, ids)` with all 12 ids |
| `test_practice_draft_flagged` | `run_practice_draft` not needed — assert via `create_draft(..., is_practice=True)` path used: after B4, `practice-` draft row has `is_practice = 1` (query SQLite) |
| `test_archetype_gap_excludes_practice` | complete practice draft with archetype A → `archetype_gap_pct("A")` unchanged vs empty ledger |
| `test_rb_run_check_real` | round 5, board with 0 RBs of adp ≤ 60 → True; board with 5 such RBs → False; round 2 with plenty → False |
| `test_prefilter_excludes_fa_and_stub` | `_prefilter_candidates` drops `team="FA"` player and `stub:` player, keeps normal player |
| `test_w17_bringback_uses_schedule` | `_is_w17_bringback(Player(team="KC"), Roster([Player(team="DEN")]))` True; vs `Roster([Player(team="CAR")])` False |

### B10. Manual smoke (document in PR description)

`ceminidfs bbm serve --slot 4 --token test123` → curl POST pick without token (401), with token (200); `ceminidfs bbm abandon` lists; `ceminidfs bbm practice --slot 4` quit at R2, resume with `--draft-id`, verify cursor lands on the correct pick.

---

## 4. Workstream C — “Extension & pipeline” (P0 #4-client; P1 #7, #9, #11; P2 #12-button, #15-client)

### C1. Narrowed board scrape + unmatched reporting (fix #4, client side) — `extension/bbm-copilot/content.js`

Replace `extractPlayerNames()` (lines 104–131) with a container-scoped label collector; delete the page-wide `button, div, span` textContent pass entirely (it is the main pollution source):

```javascript
  const BOARD_SELECTORS = [
    '[class*="draft-board"]',
    '[class*="DraftBoard"]',
    '[class*="drafted"]',
    '[class*="pick-list"]',
    '[data-testid*="board"]',
  ];

  function collectBoardLabels() {
    let root = null;
    let usedSelector = null;
    for (const sel of BOARD_SELECTORS) {
      root = document.querySelector(sel);
      if (root) { usedSelector = sel; break; }
    }
    if (!root) {
      return { labels: [], warning: 'Board container not found — Underdog DOM may have changed' };
    }
    const labels = [];
    root.querySelectorAll('[aria-label]').forEach((el) => {
      const label = el.getAttribute('aria-label')?.trim();
      if (label && label.length >= 4 && label.length <= 60) labels.push(label);
    });
    return { labels: labels.slice(0, 200), warning: null, selector: usedSelector };
  }
```

`scanBoard()` changes: call `collectBoardLabels()`; if `warning`, show it in `#bbm-sync-status` and stop. POST `{draft_id: config.draftId, labels}` to `/api/sync` (server parses via `board_parse` — B2). Status line becomes:

```javascript
      statusEl.textContent = `Synced ${data.synced_count ?? 0} — ${data.unmatched_count ?? 0} unmatched`;
      if (data.unmatched?.length) console.warn('BBM unmatched names:', data.unmatched);
```

Keep the 3s auto-clear. Noise filtering (`skipPatterns`) moves server-side into `board_parse`; delete the local regex.

### C2. Undo button (fix #12, client side) — `extension/bbm-copilot/content.js`

In `createPanel()` header controls (line 45–48), add before the refresh button: `<button class="bbm-btn bbm-btn-icon" id="bbm-undo" title="Undo last recorded action">↶</button>`, wire `panel.querySelector('#bbm-undo').addEventListener('click', undoLast);` and:

```javascript
  async function undoLast() {
    const statusEl = panel.querySelector('#bbm-sync-status');
    if (!config.draftId) { statusEl.textContent = 'Set draft ID in popup'; return; }
    try {
      const res = await fetch(`${config.apiBase}/api/undo`, {
        method: 'POST',
        headers: buildPostHeaders(),
        body: JSON.stringify({ draft_id: config.draftId }),
      });
      const data = await res.json();
      statusEl.textContent = (!res.ok || data.error)
        ? (data.error || `Undo failed (${res.status})`)
        : `Undid ${data.undone} (round ${data.round})`;
      fetchRecommendations();
      setTimeout(() => { statusEl.textContent = ''; }, 3000);
    } catch (_e) {
      statusEl.textContent = 'API unreachable — is serve running?';
    }
  }
```

### C3. Token support (fix #15, client side) — `content.js`, `popup.js`, `popup.html`

- `config` gains `token: ''`; `loadConfig()` reads `['apiBase', 'draftId', 'token']`; `chrome.storage.onChanged` handles `changes.token`.
- New helper used by every POST (`scanBoard`, `recordPick`, `undoLast`):

```javascript
  function buildPostHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    if (config.token) headers['X-BBM-Token'] = config.token;
    return headers;
  }
```

- `popup.html`: add below the draft-ID field (match existing markup style): `<label>API token (optional)</label><input id="token" type="text" placeholder="leave blank if serve has no --token">`.
- `popup.js`: save/load `token` alongside `apiBase`/`draftId` in both the `save` click handler and the `DOMContentLoaded` loader.
- `manifest.json`: bump `"version"` to `"1.1.0"`.

### C4. Buzz/ESPN graceful degrade (fix #7) — `src/ceminidfs/pipeline/project.py`

Add `import sys` and a helper; overlays must never kill a GPP run on a network outage:

```python
def _apply_optional_overlay(
    rows: list[dict[str, Any]],
    overlay_fn: Any,
    label: str,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Apply a network-backed overlay; on any failure warn and return rows unchanged."""
    try:
        return overlay_fn(rows, config=config)
    except Exception as exc:
        print(f"WARNING: {label} overlay failed; continuing without it: {exc}", file=sys.stderr)
        return rows
```

Call sites in `project_week` (lines 68–72) become:

```python
    if _buzz_enabled(cfg):
        rows = _apply_optional_overlay(rows, apply_buzz_signal, "buzz signal", cfg)

    if _espn_enabled(cfg):
        rows = _apply_optional_overlay(rows, apply_espn_injury_overlay, "ESPN injury", cfg)
```

This covers Sleeper `urllib` outages (`URLError`/`OSError`), the `RuntimeError` raised when `espn_api` is missing, and malformed API payloads (`ValueError`).

### C5. Keep `injury_status` in roster frame (fix #9) — `src/ceminidfs/pipeline/engine.py`

`salary_rows_to_roster` (line 58) builds the dict with `injury_status` but then drops it via the `columns=` argument. Fix:

```python
    return pd.DataFrame(
        roster_rows,
        columns=["player_id", "player_name", "team", "position", "injury_status"],
    )
```

Downstream `availability.resolve_unavailable_player_ids` (availability.py lines 133–139) already checks `"injury_status" in roster.columns` — it starts working with zero further changes. Verify `_align_roster_to_pbp_ids` preserves the column (it copies the frame and only rewrites `player_id` — it does).

### C6. Recreate `.venv` (fix #11) — ops, no code

Executed once by the WS-A executor as Phase 0 (before anyone runs tests), documented here because WS-C owns pipeline verification:

```bash
cd /Users/claudiobarone/Projects/CeminiDFS
rm -rf .venv
python3.12 -m venv .venv           # or python3.11; must be >= 3.11
.venv/bin/pip install -e ".[all]"  # data, optimize, bbm, espn, dev
.venv/bin/pytest -q                # expect 220 passed, 1 skipped at base
```

All subsequent `pytest`/`ruff` invocations in this plan use `.venv/bin/...`.

### C7. Tests — `tests/test_pipeline_resilience.py` (new)

| Test | Asserts |
|------|---------|
| `test_overlay_degrade_on_network_error` | `_apply_optional_overlay(rows, fn_raising(URLError("offline")), "buzz", {})` returns rows unchanged, no raise |
| `test_overlay_degrade_on_runtime_error` | same with `RuntimeError("espn_api not installed")` |
| `test_overlay_passthrough_on_success` | overlay that appends a column is applied normally |
| `test_roster_keeps_injury_status` | `salary_rows_to_roster([{"name": "A", "team": "KC", "fd_position": "RB", "injury_status": "O"}])` frame has `injury_status` column with `"O"` |
| `test_unavailable_ids_from_roster_injury` | roster frame with `injury_status="O"` → `resolve_unavailable_player_ids(...)` (with empty week cache via tmp monkeypatch) contains that player_id; `"Q"` does not |

### C8. Extension manual test checklist (no JS harness — attach results to PR)

1. `chrome://extensions` → reload unpacked `extension/bbm-copilot` (v1.1.0 shows).
2. `ceminidfs bbm serve --slot 4` (no token): panel loads recs; Scan Board on the Underdog draft page → status shows `Synced N — M unmatched`, console lists unmatched; no stub rows in DB afterwards (`sqlite3 data/bbm/bbm7.db "SELECT COUNT(*) FROM players_dim WHERE player_id LIKE 'stub:%'"` unchanged).
3. On a non-draft page: Scan Board → "Board container not found" warning, nothing posted.
4. Rec a pick → panel refreshes → Undo (↶) → status "Undid pick (round 1)", recs revert.
5. Restart serve with `--token test123`; without token in popup Rec fails with Unauthorized; set token in popup → works.

---

## 5. Order of operations

```
Phase 0 (WS-A executor, before coding):
  - cp data/bbm/bbm7.db data/bbm/bbm7.db.bak-20260701
  - cp data/bbm/player_registry.json data/bbm/player_registry.json.bak-20260701
    (data/bbm/ is NOT git-tracked — file copies are the only backup)
  - Recreate .venv (C6 commands) ; .venv/bin/pytest -q  → confirm 220/1 baseline

Phase 1 (parallel):
  - WS-A on branch fix/audit-a-ledger-identity
  - WS-B on branch fix/audit-b-server-session   (codes against §1 contracts)
  - WS-C on branch fix/audit-c-extension-pipeline
  Each: implement, add tests, run its own test files + ruff on owned paths.
  WS-B note: tests touching new ledger behavior will fail until rebased on A — mark
  nothing xfail; just defer the full-suite run to Phase 2.

Phase 2 (sequential merges into main, operator or lead agent):
  1. Merge WS-A → run .venv/bin/pytest tests/ -q  (full suite green)
  2. WS-B rebase onto main → full suite green → merge
  3. WS-C rebase onto main → full suite green → merge

Phase 3 (post-merge ops, once):
  - .venv/bin/python scripts/migrate_bbm7_20260701.py     # live-db backfill + junk cleanup
  - .venv/bin/pytest tests/ -q && .venv/bin/ruff check src/ceminidfs tests
  - ceminidfs bbm serve --slot 4  → run extension manual checklist (C8)
  - Review printed stub:* rows; delete obviously-bogus ones by hand if desired.
```

Merge order rationale: A defines schema + resolution semantics B depends on; C's extension talks to B's API contract. No workstream ever edits another's files, so rebases are clean; only behavior (not text) conflicts are possible.

---

## 6. Verification matrix (definition of done)

| Gate | Command | Pass criteria |
|------|---------|--------------|
| Unit/integration | `.venv/bin/pytest tests/ -q` | 220 baseline + ~28 new tests, 0 failures, 1 skip |
| Lint | `.venv/bin/ruff check src/ceminidfs tests` | clean |
| Migration | `.venv/bin/python scripts/migrate_bbm7_20260701.py` | prints junk-row counts; rerunnable without error |
| Exposure isolation | `sqlite3 data/bbm/bbm7.db "SELECT COUNT(*) FROM drafts WHERE is_practice=1"` | equals number of `practice-%` drafts |
| No stub-on-pick | curl POST /api/pick unknown name | 404, stub count unchanged |
| Extension | manual checklist C8 | all 5 steps pass |

Re-audit trigger (per synthesis "Next steps"): after Phase 3, re-run the audit with third-lens swapped to `grok-4.3`.

## 7. Rollback

- Code: each workstream is one branch → `git revert -m 1 <merge-commit>` independently (A last, since B/C depend on it).
- Data: `data/bbm/` is not git-tracked — restore the Phase 0 file copies: `data/bbm/bbm7.db.bak-20260701` and `data/bbm/player_registry.json.bak-20260701`.

## 8. Known risks / executor notes

- **`test_bbm_core.py` is frozen.** Expected to stay green: `test_ensure_player_stub` (function kept), `test_registry_coverage_warning` (seed count stays < 120 after junk removal + 4 adds ≈ 58), `test_resolve_player_query_index` (index path untouched), board_parse tests (module untouched by A/B logic changes). If any fails, stop and report — do not edit the file.
- **WS-A** must not change `_slug_id` — player IDs are the join key for the live DB.
- **WS-B** `_handle_sync` labels path: `board_parse.extract_names_from_aria_labels` returns already-normalized lowercase names; `resolve_player_query` re-normalizes idempotently — fine.
- **WS-C** Underdog DOM selectors are best-effort; the server-side `board_parse` noise filter is the real safety net. If no selector matches during live testing, capture the DOM snippet and add one selector — do not restore the page-wide span scrape.
- Broad `except Exception` in `_apply_optional_overlay` is intentional (overlays are optional enrichment); ruff config has no BLE rule enabled.
