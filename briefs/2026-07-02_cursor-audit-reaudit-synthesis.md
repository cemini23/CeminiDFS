# Cursor audit re-audit — post-fix verification

**Date:** 2026-07-02  
**Target:** CeminiDFS after 15-fix sprint (uncommitted local)  
**Mode:** `architecture` (post-fix verification)  
**Roles → models:** agentic-reasoning → `glm-5.2-high`, code-implementation → `kimi-k2.7-code`, third-lens → `gemini-3.1-pro`  
**Tests:** 274 passed, 1 skipped

---

## Consensus (≥2 auditors agree)

| Finding | Auditors | Severity |
|---------|----------|----------|
| **All 6 P0 bugs verified fixed** — normalizer parity, no stub-on-pick, `is_practice` filters, junk FA removed, scoped extension sync + `board_parse`, practice resume includes `room_taken` | GLM, Kimi | ✅ resolved |
| **`merge_adp_csv` can reintroduce junk FA rows** — `add_unmatched=True` default inserts `team=FA` on first `refresh-adp` | Kimi (unique), GLM (implicit via registry hygiene) | medium |
| **Hardcoded 2026 season data** — W17 matchups, byes, BUY/FADE/STACK_PAIRS in code | Gemini, GLM | medium (seasonal maintenance) |
| **Underdog DOM selectors are best-effort** — mid-season DOM change → "Board container not found"; CLI `t` is fallback | GLM, Kimi | low |
| **Advisory pivot mutates in-memory archetype on GET** — recs reflect pivoted caps/multipliers before operator confirms via `POST /api/pivot` | GLM (unique) | low–medium |

---

## Unique (single auditor)

| Model | Finding |
|-------|---------|
| **GLM** | `/api/sync` may record picked players as `room_taken`; `undo` then pops taken before pick |
| **GLM** | `pivot_warning` lost when recommendations list is empty |
| **GLM** | `_combo_cap_blocks` opens ~4k SQLite connections per rec request (pre-existing perf) |
| **Kimi** | HTTP sync/pick swallows ambiguous matches — extension can't disambiguate shared surnames |
| **Kimi** | `record_taken` accepts round/pick_num but doesn't persist them |
| **Gemini** | `_is_elite_rb_tier_empty` substring matching (e.g. `"taylor"`) can false-trigger pivot abort |

---

## Conflicts

| Topic | GLM | Kimi | Gemini | Resolution |
|-------|-----|------|--------|------------|
| Overall | WARN | WARN | SHIP-WITH-FIXES (season debt) | **SHIP-WITH-FIXES** — P0 fixed; paid entry OK after one dry-run |
| Paid draft readiness | Yes after dry-run | Yes with ADP refresh caveat | Season hardcoding ≠ block for 2026 | **GO** for 2026 BBM7 with operator checklist below |

---

## Verdict rollup

| Model | Verdict |
|-------|---------|
| glm-5.2-high | WARN |
| kimi-k2.7-code | WARN |
| gemini-3.1-pro | WARN (SHIP-WITH-FIXES) |

**Overall: SHIP-WITH-FIXES** — The original FAIL root causes are fixed in code and tests. Remaining items are maintenance/UX gaps, not silent data-corruption paths. One free practice dry-run recommended before first paid entry.

---

## Recommended follow-up (P1 backlog)

- [x] **`merge_adp_csv`:** default `add_unmatched=False` — **2026-07-02**
- [x] **Advisory pivot:** no archetype mutation on GET — **2026-07-02**
- [x] **Extension disambiguation:** `ambiguous[]` + `player_id` — **2026-07-02**
- [x] **`/api/sync`:** skip names already in picks — **2026-07-02**
- [x] **Elite RB check:** exact `merge_name` — **2026-07-02**
- [x] **Season data:** nflreadpy cache + `refresh-schedule` — **2026-07-02**

See [`briefs/2026-07-02_p1-reaudit-fix-plan.md`](2026-07-02_p1-reaudit-fix-plan.md).

---

## Operator checklist (before paid entry)

- [ ] `ceminidfs bbm practice --slot 4` — full draft, test Rec + Undo + Scan Board
- [ ] Reload extension v1.1.0 in Chrome
- [ ] Confirm `refresh-adp` CSV has full names (not surnames only)
- [ ] `ceminidfs bbm abandon --draft-id` any stale in-progress drafts
