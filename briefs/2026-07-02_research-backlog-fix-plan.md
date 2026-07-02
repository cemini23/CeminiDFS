# Research-backlog fix plan — safe ADP expansion, combo batch perf, preflight, DOM fallback, taken dedupe

**Date:** 2026-07-02
**Status:** ✅ **SHIPPED** — 319 tests pass, extension v1.3.0
**Status:** PLANNED
**Base:** uncommitted re-audit sprint tree (297 tests pass, extension v1.2.0). Phase 0 commits that state first — do not branch off a dirty tree.
**Executors:** 2 parallel subagents (WS-A, WS-B), zero file overlap, any merge order.

**Sources synthesized:**

| Source | What it contributes |
|--------|--------------------|
| `briefs/2026-07-02_cursor-audit-reaudit-synthesis.md` | P2/low leftovers: GLM `_combo_cap_blocks` ~4k SQLite connections per rec request (item 2); `record_taken` dedupe (item 5); Underdog DOM selectors best-effort → "Board container not found" dead-end (item 4) |
| `ROADMAP.md` backlog | "Registry expansion toward top-240 via weekly ADP refresh" (items 1 + 3) |
| OSINT `wiki/sweeps/2026-07-02-daily.md` Q8 ceminidfs-nflverse | Operator reading refs only (FantasyAlarm DK-vs-FD GPP guide, CBS rankings model). **No new repos adopted** — `winsznx/theeleven` (agent prop markets) is out of scope and stays out per ROADMAP rejects posture. Zero new dependencies in this sprint. |
| Kimi re-audit finding | `merge_adp_csv` needs a safe expansion path now that `add_unmatched=False` is the default — otherwise the registry can never grow toward top-240 without re-enabling the junk `team="FA"` path (item 1) |

---

## 0. Item → workstream traceability

| # | Item | Source | Workstream | Files touched |
|---|------|--------|-----------|---------------|
| 1 | Safe ADP expansion (verified team+position rows only) | Kimi + ROADMAP | **WS-A** | `normalize_adp.py`, `cli.py`, `test_adp_and_schedule.py` |
| 2 | Batch `combo_exposures_for_roster` single-query prefilter | GLM (reaudit unique) | **WS-B** | `ledger.py`, `recommender.py`, `test_combo_and_taken.py` (new) |
| 3 | `bbm preflight` CLI readiness checklist | ROADMAP + operator checklist | **WS-A** | `cli.py`, `config.py`, `schedule.py`, `test_preflight.py` (new) |
| 4 | Extension DOM fallback (page-wide aria scan + visible warning) | GLM/Kimi consensus (low) | **WS-B** | `content.js`, `manifest.json` |
| 5 | `record_taken` idempotency regression lock | reaudit P2 leftover | **WS-B** | `test_combo_and_taken.py` (new) — see §3.3 status note |

**File ownership (hard rule — no workstream edits another's files):**

- **WS-A "Registry & preflight":** `src/ceminidfs/bbm/normalize_adp.py`, `src/ceminidfs/bbm/cli.py`, `src/ceminidfs/bbm/config.py`, `src/ceminidfs/bbm/schedule.py`, `tests/bbm/test_adp_and_schedule.py` (extend), `tests/bbm/test_preflight.py` (new)
- **WS-B "Ledger perf & extension":** `src/ceminidfs/bbm/ledger.py`, `src/ceminidfs/bbm/recommender.py`, `tests/bbm/test_combo_and_taken.py` (new), `extension/bbm-copilot/content.js`, `extension/bbm-copilot/manifest.json`

Nobody edits `api_server.py`, `session.py`, `registry.py`, `archetype.py`, `practice.py`, `board_parse.py`, `tests/bbm/test_bbm_core.py`, `tests/bbm/test_identity_exposure.py`, `tests/bbm/test_api_contracts.py`, `tests/bbm/test_practice_and_pivots.py`, `tests/bbm/conftest.py`, or `popup.*`/`styles.css`. The existing `/api/sync` labels contract (`board_parse.extract_names_from_aria_labels` + noise filters + `names[:200]` cap + `skipped_existing` dedupe) already supports item 4 unchanged — the fallback is client-side only.

---

## 1. Interface contracts (frozen before coding)

1. **`normalize_adp.merge_adp_csv(csv_path, registry, *, add_unmatched: bool = False, expand_verified: bool = True)`** — new keyword `expand_verified` (default on). Resolution order for an unmatched row: exact/fuzzy match → verified expansion (real team + position) → `add_unmatched` junk fallback (`team="FA"`, old behavior) → reported in `unmatched`.
2. **`AdpMergeResult` gains `added_verified: int = 0`** — appended after `ambiguous` with a default, so existing constructions (e.g. `test_refresh_registry_threads_add_unmatched`) keep working unchanged.
3. **`ledger.combo_exposures_for_roster(roster_player_ids, candidate_ids, db_path=None) -> dict[tuple[str, str], float]`** — new. Single connection, chunked single-query. Value = weighted joint exposure `(complete + 0.5·in_progress) / TOTAL_ENTRIES`, practice drafts excluded (same semantics as `combo_pct(...)["current"]`). Missing pair ⇒ treat as 0.0. Empty roster **or** empty candidates ⇒ returns `{}` **without opening a connection** (keeps `test_prefilter_excludes_fa_and_stub`'s no-DB property for round-1 empty rosters).
4. **`recommender._combo_cap_blocks` is deleted**; `_prefilter_candidates` signature unchanged (only callers: `recommend_top3`, tests). `combo_pct` stays in `ledger.py` untouched (still used by `test_identity_exposure.py`).
5. **`schedule.get_schedule_source() -> str`** — new thin accessor returning `_active_schedule()[2]` (`"cache"` | `"hardcoded"`).
6. **`config.REGISTRY_TARGET: int = 240`** — new constant (ROADMAP top-240 target). `check_registry_coverage`'s 120-floor warning is untouched.
7. **CLI:** new subcommand `ceminidfs bbm preflight` (no args). Exit 0 = all green, exit 1 = ≥1 `[WARN]` line. Handler `_cmd_preflight`; added to `handler_map` and the "Available:" help string.
8. **`ledger.record_taken` return dict keeps `inserted: bool`** — behavior contract (INSERT OR IGNORE; action_log appended only when inserted) is regression-locked, not changed.
9. **Extension:** `collectBoardLabels()` returns `{labels, warning, selector}` and falls back to `document.body` when no board selector matches; `scanBoard()` gates the fallback POST behind a `confirm()` dialog; manifest version → `"1.3.0"`. `/api/sync` request/response shapes unchanged.

---

## 2. Workstream A — "Registry & preflight" (items 1, 3)

### 2.1 Safe ADP expansion (item 1) — `src/ceminidfs/bbm/normalize_adp.py`

New imports (no cycle: `config` → `schedule` → stdlib only): `from ceminidfs.bbm.config import TIER_EXPOSURE_CAPS, get_bye_week`; add `Final` to the `typing` import.

Module constants:

```python
_TEAM_ALIASES: Final[dict[str, str]] = {"JAC": "JAX", "WSH": "WAS", "ARZ": "ARI", "LA": "LAR"}
_VALID_POSITIONS: Final[frozenset[str]] = frozenset({"QB", "RB", "WR", "TE"})
_TEAM_RE = re.compile(r"^[A-Z]{2,3}$")


def _verified_team_and_position(row: dict[str, str]) -> tuple[str, str] | None:
    """(team, position) when the CSV row carries a real NFL team and position, else None."""
    team = _pick(row, ("team", "tm", "nfl_team")).upper().strip()
    team = _TEAM_ALIASES.get(team, team)
    position = _pick(row, ("pos", "position")).upper().strip()
    if not _TEAM_RE.match(team) or team in ("FA", "NA"):
        return None
    if position not in _VALID_POSITIONS:
        return None
    return team, position
```

In `merge_adp_csv`, initialize `added_verified = 0` beside the other counters and restructure the unmatched branch (current lines 281–310). **Verified expansion takes precedence over the junk path** — with `--add-unmatched` passed, verifiable rows still get their real team; only unverifiable rows fall back to `team="FA"` (contract #1 ordering):

```python
            else:
                verified = _verified_team_and_position(row) if expand_verified else None
                if verified is not None:
                    team, position = verified
                    tier = _tier_from_adp(adp_val)
                    new_player = {
                        "player_id": f"bbm:{merge_name.replace(' ', '-')}",
                        "name": raw_name.strip(),
                        "merge_name": merge_name,
                        "position": position,
                        "team": team,
                        "bye_week": get_bye_week(team) or 0,
                        "adp": adp_val,
                        "strategy_rank": int(adp_val),
                        "projection_pts": 100.0,
                        "signal": "NEUTRAL",
                        "tier": tier,
                        "exposure_cap_pct": TIER_EXPOSURE_CAPS.get(tier, 0.20),
                        "drift_coeff": 0.0,
                        "injury_fade": False,
                        "notes": "adp-expansion",
                        "fade_rounds": None,
                    }
                    players.append(new_player)
                    by_merge[merge_name] = new_player
                    candidate_names.append(merge_name)
                    matched += 1
                    added += 1
                    added_verified += 1
                    continue
                if add_unmatched:
                    ...existing junk path body unchanged (team="FA", cap 0.20)...
                    continue
                unmatched.append(raw_name)
                continue
```

Docstring: "Unmatched rows are added only when the CSV carries a real team + position (safe top-240 expansion, 2026-07-02); `add_unmatched=True` restores the legacy team=FA fallback for unverifiable rows." Keep the `players.sort(...)` on `added` and the meta updates as-is; thread `added_verified` into the returned `AdpMergeResult`.

Why the CLI needs no new flag: `expand_verified=True` is the function default, so `refresh-adp`/`refresh-weekly` get the safe expansion automatically; `--add-unmatched` already exists and keeps the junk fallback for unverifiable rows. The **only** `cli.py` change for item 1 is `_print_refresh_summary` line 466–468 → `f"fuzzy {adp_result.fuzzy_matched}, added {adp_result.added} ({adp_result.added_verified} verified-team), unmatched {len(adp_result.unmatched)})"` (use `getattr(adp_result, "added_verified", 0)` so mocked results without the field don't crash).

**Existing tests that must keep passing untouched:** `test_merge_adp_default_skips_unmatched` (its CSV has no team column → still unmatched), `test_merge_adp_opt_in_still_adds` (junk path intact), `test_bbm_core.py::test_merge_adds_unmatched_players`, `test_refresh_adp_merge_stats`.

### 2.2 `bbm preflight` (item 3) — `src/ceminidfs/bbm/cli.py` + `config.py` + `schedule.py`

`config.py`: add `REGISTRY_TARGET = 240  # ROADMAP: registry expansion toward top-240 via weekly ADP refresh` next to the other exposure/portfolio constants.

`schedule.py`: add below `_active_schedule`:

```python
def get_schedule_source() -> str:
    """'cache' when serving data/bbm/schedule_<season>.json, else 'hardcoded'."""
    return _active_schedule()[2]
```

`cli.py` parser (in `build_bbm_parser`) + `handler_map` entry + "Available:" string:

```python
    subparsers.add_parser(
        "preflight", help="Pre-draft readiness checklist (registry, drafts, schedule, smoke)"
    )
```

Handler — imports inside the function so `bbm_db`-style monkeypatching of `ledger.get_db_path` works (same pattern as `_suggest_archetype`):

```python
def _cmd_preflight(args: argparse.Namespace) -> int:
    del args
    import sqlite3
    from ceminidfs.bbm.config import REGISTRY_TARGET
    from ceminidfs.bbm.ledger import get_db_path
    from ceminidfs.bbm.schedule import get_schedule_cache_path, get_schedule_source

    ensure_initialized()
    warnings = 0

    registry = load_registry()
    player_count = len(registry.get("players", []))
    if player_count >= REGISTRY_TARGET:
        print(f"[ok]   Registry: {player_count} players (target {REGISTRY_TARGET})")
    else:
        warnings += 1
        print(
            f"[WARN] Registry: {player_count} players (target {REGISTRY_TARGET}) — "
            "run: ceminidfs bbm refresh-adp --csv <bbtb.csv>"
        )

    conn = sqlite3.connect(get_db_path())
    practice_done = conn.execute(
        "SELECT COUNT(*) FROM drafts WHERE is_practice = 1 AND status = 'complete'"
    ).fetchone()[0] or 0
    conn.close()
    if practice_done:
        print(f"[ok]   Practice drafts completed: {practice_done}")
    else:
        warnings += 1
        print("[WARN] No completed practice draft — run: ceminidfs bbm practice --slot 4")

    stale = list_in_progress_drafts()
    if stale:
        warnings += 1
        print(f"[WARN] Stale in-progress drafts ({len(stale)}):")
        for draft in stale:
            tag = " [practice]" if draft.get("is_practice") else ""
            print(
                f"         {draft['draft_id']}  slot {draft['slot']}  "
                f"R{draft['current_round']}/{draft['total_rounds']}{tag}"
            )
        print("       -> ceminidfs bbm abandon --draft-id <id>")
    else:
        print("[ok]   No stale in-progress drafts")

    source = get_schedule_source()
    if source == "cache":
        print(f"[ok]   Schedule source: cache ({get_schedule_cache_path()})")
    else:
        print(
            "[ok]   Schedule source: hardcoded 2026 fallback — "
            "optional: ceminidfs bbm refresh-schedule"
        )

    print("Smoke: .venv/bin/pytest tests/bbm -q")
    print(f"Result: {'READY' if warnings == 0 else f'{warnings} warning(s)'}")
    return 0 if warnings == 0 else 1
```

Hardcoded schedule is `[ok]` (it *is* the correct 2026 data per the P1 sprint), just hinted. `list_in_progress_drafts` is already imported at module top.

### 2.3 Tests — `tests/bbm/test_adp_and_schedule.py` (extend, WS-A owns it)

CSV header used throughout: `name,adp,pos,team`. All against `build_seed_registry()`.

| Test | Asserts |
|------|---------|
| `test_merge_adp_expands_verified_team_rows` | row `Nick Chubb,52.0,RB,HOU` → `added == 1`, `added_verified == 1`, `unmatched == []`; new player: `team == "HOU"`, `position == "RB"`, `tier == "stack_core"`, `bye_week == 8`, `signal == "NEUTRAL"`, `player_id == "bbm:nick-chubb"`, `exposure_cap_pct == TIER_EXPOSURE_CAPS["stack_core"]`, `notes == "adp-expansion"` |
| `test_merge_adp_rejects_fa_or_missing_team` | rows `Ghost Guy,90.0,WR,FA` and `No Team,95.0,WR,` → `added == 0`, both names in `unmatched`, no new registry rows |
| `test_merge_adp_rejects_missing_position` | row `Some Body,88.0,,KC` → `added == 0`, in `unmatched` |
| `test_merge_adp_team_alias_normalized` | row `Alias Guy,70.0,WR,JAC` → added with `team == "JAX"`, `bye_week == 7` |
| `test_merge_adp_expand_verified_opt_out` | same Chubb CSV with `expand_verified=False` → `added == 0`, name in `unmatched` |
| `test_merge_adp_add_unmatched_flag_keeps_fa_fallback` | CSV with one verified row + one team-less row, `add_unmatched=True` → `added == 2`, `added_verified == 1`; verified row keeps its real team (expansion precedence over junk path), team-less row has `team == "FA"` (legacy fallback preserved) |
| `test_merge_adp_expansion_sorts_and_updates_meta` | after expansion: `registry["players"]` sorted by adp, `meta["player_count"]` grew by 1 |

### 2.4 Tests — `tests/bbm/test_preflight.py` (new)

Pattern: call `cli._cmd_preflight(Namespace())` directly with `monkeypatch.setattr(cli, "ensure_initialized", lambda: None)`, the `bbm_db` fixture (patches `ledger.get_db_path` + `registry.get_registry_path`), and `capsys`. The autouse `isolated_schedule` fixture pins schedule lookups.

| Test | Asserts |
|------|---------|
| `test_preflight_warns_registry_below_target` | seed registry (<240 players) → stdout has `[WARN] Registry:` + `target 240` + `refresh-adp` hint; return 1 |
| `test_preflight_ok_at_target` | `monkeypatch.setattr(cli, "load_registry", lambda: {"players": [{}] * 240})` → registry line is `[ok]` |
| `test_preflight_counts_completed_practice_drafts` | zero → `[WARN] No completed practice draft`; after `create_draft("practice-x", 4, is_practice=True)` + `complete_draft("practice-x")` → `[ok]   Practice drafts completed: 1` |
| `test_preflight_lists_stale_in_progress_drafts` | one in-progress draft → its `draft_id` printed, `abandon --draft-id` hint present, return 1; none → `[ok]   No stale in-progress drafts` |
| `test_preflight_reports_schedule_source` | default (isolated, no cache) → `hardcoded 2026 fallback` + `refresh-schedule` hint; write a valid 28-team/16-pair cache JSON into the `isolated_schedule` tmp path + `clear_schedule_memo()` → `Schedule source: cache` |
| `test_preflight_prints_smoke_hint` | stdout contains `pytest tests/bbm -q` |
| `test_preflight_exit_zero_when_all_green` | 240-player registry monkeypatch + completed practice draft + no in-progress drafts → returns 0 and `Result: READY` |

---

## 3. Workstream B — "Ledger perf & extension" (items 2, 5, 4)

### 3.1 Batch combo exposures (item 2) — `src/ceminidfs/bbm/ledger.py`

New function next to `combo_pct` (which stays untouched):

```python
def combo_exposures_for_roster(
    roster_player_ids: Sequence[str],
    candidate_ids: Sequence[str],
    db_path: Optional[Path | str] = None,
) -> dict[tuple[str, str], float]:
    """Weighted joint-draft exposure for every (roster, candidate) pair in one query.

    Same semantics as combo_pct()["current"]: practice drafts excluded,
    complete counts 1.0, in_progress counts IN_PROGRESS_EXPOSURE_WEIGHT,
    denominator TOTAL_ENTRIES. Pairs with zero joint drafts are omitted
    (callers treat missing as 0.0). Empty inputs return {} without touching
    the DB — fixes the ~4k-connections-per-rec-request GLM finding.
    """
    roster_ids = [pid for pid in dict.fromkeys(roster_player_ids) if pid]
    cand_ids = [pid for pid in dict.fromkeys(candidate_ids) if pid]
    if not roster_ids or not cand_ids:
        return {}

    conn = connect_db(db_path or get_db_path())
    cursor = conn.cursor()
    exposures: dict[tuple[str, str], float] = {}

    chunk_size = 400  # roster ≤ 18 → total placeholders stay well under SQLite's 999
    for start in range(0, len(cand_ids), chunk_size):
        chunk = cand_ids[start:start + chunk_size]
        r_ph = ",".join("?" * len(roster_ids))
        c_ph = ",".join("?" * len(chunk))
        cursor.execute(f"""
            SELECT joint.a, joint.b,
                   COALESCE(SUM(CASE WHEN d.status = 'complete' THEN 1 ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN d.status = 'in_progress' THEN 1 ELSE 0 END), 0)
            FROM (
                SELECT DISTINCT p1.player_id AS a, p2.player_id AS b, p1.draft_id AS draft_id
                FROM picks p1
                JOIN picks p2 ON p1.draft_id = p2.draft_id
                WHERE p1.player_id IN ({r_ph}) AND p2.player_id IN ({c_ph})
            ) joint
            JOIN drafts d ON joint.draft_id = d.draft_id
            WHERE d.is_practice = 0
            GROUP BY joint.a, joint.b
        """, [*roster_ids, *chunk])
        for a, b, complete_count, in_progress_count in cursor.fetchall():
            weighted = complete_count + IN_PROGRESS_EXPOSURE_WEIGHT * in_progress_count
            exposures[(a, b)] = weighted / TOTAL_ENTRIES

    conn.close()
    return exposures
```

(`Sequence` joins the existing `typing` import.) The inner `SELECT DISTINCT … draft_id` mirrors `combo_pct`'s joint-draft subquery exactly, so per-pair counts are identical to N separate `combo_pct` calls.

### 3.2 Prefilter uses the batch (item 2) — `src/ceminidfs/bbm/recommender.py`

- Import swap: `from ceminidfs.bbm.ledger import combo_pct` → `from ceminidfs.bbm.ledger import combo_exposures_for_roster`.
- **Delete `_combo_cap_blocks`** (lines 211–221; no other callers, no test references).
- In `_prefilter_candidates`, before the loop:

```python
    roster_ids = [rp.player_id for rp in roster.players]
    combo_exposures = combo_exposures_for_roster(
        roster_ids, [p.player_id for p in players]
    )
```

- Replace the per-player block (lines 280–282) with:

```python
        # Skip players where any roster-teammate joint exposure meets COMBO_PAIR_CAP
        if any(
            combo_exposures.get((rid, player.player_id), 0.0) >= COMBO_PAIR_CAP
            for rid in roster_ids
        ):
            continue
```

Behavior parity: identical block decisions (same weighted math, same `>= COMBO_PAIR_CAP` threshold against the constant — per-pair caps were never consulted here), 1 connection instead of `len(roster) × len(candidates)`. Empty roster (round 1) opens zero connections, preserving `test_prefilter_excludes_fa_and_stub`'s DB-free operation.

### 3.3 `record_taken` idempotency (item 5) — status note + regression lock

**Already implemented in the uncommitted sprint** (`ledger.py` 470–515): `INSERT OR IGNORE INTO room_taken`, `inserted = cursor.rowcount > 0`, action_log appended only when `inserted`, and the flag returned. `/api/sync` additionally skips already-recorded ids before calling it. WS-B therefore ships **no ledger change for item 5** — it locks the contract with the tests in §3.4 so a future refactor (e.g. persisting round/pick_num per the Kimi note) can't silently regress the dedupe. If any test exposes a gap (it shouldn't), fix inside `record_taken` only.

### 3.4 Tests — `tests/bbm/test_combo_and_taken.py` (new)

Helpers mirror `test_identity_exposure.py`: raw `sqlite3` inserts into `drafts`/`picks` for joint-draft seeding, `bbm_db` fixture for player ids (`bbm:jahmyr-gibbs`, `bbm:ja-marr-chase`, …).

| Test | Asserts |
|------|---------|
| `test_combo_exposures_batch_matches_combo_pct` (`bbm_db`) | seed 3 complete + 2 in-progress non-practice joint drafts for (Gibbs, Chase) → batch value for the pair `== pytest.approx(combo_pct(...)["current"]) == (3 + 0.5*2)/150`; a never-paired candidate id is absent from the dict |
| `test_combo_exposures_excludes_practice_drafts` (`bbm_db`) | joint drafts flagged `is_practice=1` contribute nothing (pair absent or 0.0) |
| `test_combo_exposures_empty_inputs_no_connection` | `monkeypatch.setattr("ceminidfs.bbm.ledger.connect_db", _raise)` → `combo_exposures_for_roster([], ["x"]) == {}` and `(["x"], []) == {}` without raising |
| `test_combo_exposures_dedupes_input_ids` (`bbm_db`) | duplicated ids in both args → same result as unique lists (guards the placeholder math) |
| `test_prefilter_single_connection_for_combo_checks` (`bbm_db`) | counting wrapper around `ceminidfs.bbm.ledger.connect_db`; `_prefilter_candidates` with a 2-player roster and 5 candidates → **exactly 1** connection opened |
| `test_prefilter_blocks_candidate_at_combo_cap` (`bbm_db`) | `monkeypatch.setattr("ceminidfs.bbm.recommender.COMBO_PAIR_CAP", 0.01)`; 2 joint complete drafts for (roster RB, candidate WR) → candidate excluded from `_prefilter_candidates` output while an un-paired control candidate survives |
| `test_record_taken_duplicate_returns_inserted_false` (`bbm_db`) | first call → `inserted is True`; second same `draft_id`+`player_id` → `inserted is False`; `room_taken` count for the draft == 1 |
| `test_record_taken_duplicate_no_action_log_growth` (`bbm_db`) | after the duplicate call, `action_log` has exactly one `taken` row for the draft; `undo_last_action` once → `undone == "taken"` and `room_taken` empty; second undo → `None` (no phantom action left behind) |

### 3.5 Extension DOM fallback (item 4) — `extension/bbm-copilot/content.js` + `manifest.json`

`collectBoardLabels()` (lines 121–137) falls back to `document.body` instead of dead-ending:

```javascript
  function collectBoardLabels() {
    let root = null;
    let usedSelector = null;
    for (const sel of BOARD_SELECTORS) {
      root = document.querySelector(sel);
      if (root) { usedSelector = sel; break; }
    }
    let warning = null;
    if (!root) {
      root = document.body;
      usedSelector = 'body-fallback';
      warning = 'Board container not found — page-wide scan (less precise)';
    }
    const labels = [];
    root.querySelectorAll('[aria-label]').forEach((el) => {
      const label = el.getAttribute('aria-label')?.trim();
      if (label && label.length >= 4 && label.length <= 60) labels.push(label);
    });
    return { labels: labels.slice(0, 200), warning, selector: usedSelector };
  }
```

`scanBoard()` (lines 171–179) replaces the early-return-on-warning with a confirm-gated fallback (a page-wide scan can sweep the *available players* list into `room_taken`, so it must never run silently):

```javascript
    const { labels, warning } = collectBoardLabels();
    if (warning) {
      console.warn('BBM:', warning);
      if (labels.length === 0) {
        statusEl.textContent = `${warning} — no labels found`;
        return;
      }
      if (!window.confirm(`${warning}.\nSync ${labels.length} page-wide labels anyway? (may include undrafted players)`)) {
        statusEl.textContent = `${warning} — sync cancelled`;
        return;
      }
    } else if (labels.length === 0) {
      statusEl.textContent = 'No players found';
      return;
    }
```

On the success path, prefix the status and keep it visible when the fallback was used:

```javascript
      statusEl.textContent =
        (warning ? 'WARN page-wide scan — ' : '') +
        `Synced ${data.synced_count ?? 0} — ${data.skipped_count ?? 0} known — ` +
        `${data.unmatched_count ?? 0} unmatched` +
        (ambiguousCount ? ` — ${ambiguousCount} ambiguous` : '');
      ...
      if (!ambiguousCount && !warning) setTimeout(() => { statusEl.textContent = ''; }, 3000);
```

Server side needs nothing: `/api/sync` already routes `labels` through `board_parse` noise filters, caps at 200 names, skips already-recorded ids, and reports `unmatched`/`ambiguous`. `manifest.json`: `"version": "1.3.0"`.

### 3.6 Manual checklist (item 4 — no JS harness; attach results to PR)

1. `chrome://extensions` → reload unpacked → v1.3.0 shows.
2. Live draft room with intact board → Scan Board unchanged: counts status, no warning, auto-clear after 3s.
3. In DevTools, remove/rename the board container class → Scan Board → confirm dialog appears with label count; **Cancel** → status `… sync cancelled`, no POST (verify in serve log / `room_taken` unchanged).
4. Repeat and **OK** → POST fires; status shows `WARN page-wide scan — Synced …` and persists (no auto-clear); server `unmatched`/noise counts sane; console has the `BBM:` warning.
5. Non-draft Underdog page (no aria-labels of interest) → `… — no labels found`, no dialog, no POST.
6. Undo still pops any wrongly-synced taken rows one at a time (spot-check).

---

## 4. Order of operations

```
Phase 0 (operator, before branching):
  - git add -A && git commit      → land the re-audit sprint currently uncommitted
  - .venv/bin/pytest -q           → confirm 297-pass baseline
  - cp data/bbm/bbm7.db data/bbm/bbm7.db.bak-20260702b        (habit; no migration here)
  - cp data/bbm/player_registry.json data/bbm/player_registry.json.bak-20260702
      (item 1 mutates the registry on the first real refresh-adp run)

Phase 1 (parallel — no shared files):
  - WS-A on branch fix/backlog-a-registry-preflight
  - WS-B on branch fix/backlog-b-combo-extension
  Each: implement, add tests, run own test files + ruff on owned paths.

Phase 2 (sequential merges into main, either order works):
  1. Merge WS-B → .venv/bin/pytest tests/ -q   (green)
  2. Merge WS-A → .venv/bin/pytest tests/ -q && .venv/bin/ruff check src/ceminidfs tests

Phase 3 (post-merge ops, once):
  - ceminidfs bbm preflight                       # expect WARN on registry count (seed < 240)
  - ceminidfs bbm refresh-adp --csv <full BBTB export with team column>
  - ceminidfs bbm refresh-weekly --adp <csv> --projections <csv>
      # expanded rows carry projection_pts=100.0 until projections merge fills them
  - ceminidfs bbm preflight                       # registry line flips to [ok] as CSV coverage allows
  - Reload extension v1.3.0; run manual checklist §3.6
```

---

## 5. Verification matrix (definition of done)

| Gate | Command / scenario | Pass criteria |
|------|-------------------|---------------|
| Unit/integration | `.venv/bin/pytest tests/ -q` | 297 baseline + ~15 new, 0 failures, 1 skip |
| Lint | `.venv/bin/ruff check src/ceminidfs tests` | clean |
| Safe expansion | `merge_adp_csv` with team-column CSV | verified rows added with real team/bye/tier; team-less rows only in `unmatched`; zero new `team="FA"` rows without `--add-unmatched` |
| GLM perf fix | `test_prefilter_single_connection_for_combo_checks` | exactly 1 connection per prefilter call (was roster×candidates) |
| Parity | `test_combo_exposures_batch_matches_combo_pct` | batch values equal `combo_pct` for seeded pairs |
| Preflight | `ceminidfs bbm preflight` on operator machine | all five lines print (registry vs 240, practice count, stale drafts, schedule source, smoke hint); exit code matches warnings |
| Taken dedupe | `test_record_taken_duplicate_no_action_log_growth` | one `taken` action per unique player; undo sequence clean |
| Extension | manual checklist §3.6 | all 6 steps pass |

## 6. Rollback

- Code: one branch per workstream → `git revert -m 1 <merge-commit>` independently; no cross-branch dependencies.
- Data: registry expansion is the only data mutation — restore `player_registry.json.bak-20260702` and re-run `ceminidfs bbm refresh-adp` with the old CSV if expanded rows misbehave. No DB schema changes.
- Extension: reload v1.2.0 unpacked if the fallback dialog misbehaves.

## 7. Known risks / executor notes

- **Expanded rows have flat `projection_pts=100.0` and `signal="NEUTRAL"`** until a projections CSV is merged — the recommender will rank them by ADP/CLV mostly. Phase 3 runs `refresh-weekly --projections` immediately after expansion; tier-based exposure caps bound the damage meanwhile. `notes="adp-expansion"` makes the cohort auditable (`jq` or SQL on `players_dim.notes`).
- **Team alias coverage**: `_TEAM_ALIASES` handles JAC/WSH/ARZ/LA; a genuinely unknown abbreviation still passes the regex and lands with `bye_week=0` (validator treats 0 as unknown). Acceptable — the row is real enough to draft, and reconcile/audit surfaces it.
- **`_TEAM_RE` + FA check runs on the raw CSV row** — rows where the team column contains e.g. `"Free Agent"` fail the regex and stay unmatched (correct).
- **Page-wide scan can include the available-players pool** — that is why the fallback is confirm-gated and the WARN status never auto-clears (§3.5). `/api/sync`'s `skipped_existing` + `INSERT OR IGNORE` keep repeats harmless; `undo` recovers one-off mistakes.
- **`test_prefilter_excludes_fa_and_stub` (frozen file) runs `_prefilter_candidates` with an empty roster and no DB fixture** — the empty-input short-circuit in `combo_exposures_for_roster` is what keeps it green. Do not "simplify" it away.
- **SQLite placeholder budget**: 18 roster + 400-candidate chunks = 418 params max, under the 999 default. If registry limits ever rise past `get_available_models(limit=240)`, chunking already covers it.
- **`_print_refresh_summary` uses `getattr(adp_result, "added_verified", 0)`** because `test_refresh_registry_threads_add_unmatched` (WS-A's own file, but keep it untouched) constructs `AdpMergeResult` without the new field — the default covers it anyway; the `getattr` is belt-and-braces for mocks.
- **Preflight must not import at module top** anything beyond what `cli.py` already imports — function-local imports keep `ledger.get_db_path` monkeypatchable and avoid slowing every CLI invocation.
- **No new dependencies** — Q8 sweep items are operator reading only; `winsznx/theeleven` explicitly not adopted (ROADMAP rejects posture).
