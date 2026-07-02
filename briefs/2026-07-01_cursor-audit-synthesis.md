# Cursor audit synthesis — CeminiDFS operator readiness

**Date:** 2026-07-01  
**Target:** `/Users/claudiobarone/Projects/CeminiDFS` @ `ccc7171`  
**Mode:** `architecture`  
**Roles → models:** agentic-reasoning → `claude-fable-5-thinking-max`, code-implementation → `gpt-5.3-codex`, third-lens → `gemini-3.1-pro`  
**Tests at audit:** 220 passed, 1 skipped

---

## Consensus (≥2 auditors agree)

| # | Finding | Auditors | Evidence |
|---|---------|----------|----------|
| C1 | **Auto-stub on unknown names corrupts pick/sync flows** — typos, DOM noise, and normalizer mismatches silently create stub players and record them as real picks | Fable, Codex | `ledger.py:862-864`; consumed by `api_server.py:354-377`, `cli.py:218-231`, `/api/sync` |
| C2 | **Two normalizers split-brain hyphenated elites** — registry stores hyphens (`_normalize_merge`), ledger lookup strips them (`normalize_name`), so ARSB/JSN etc. miss and fall through to stub | Fable (verified live), Codex (same root) | `registry.py:68-69` vs `normalize_adp.py:33-44` |
| C3 | **Extension board scan is overly broad** — untested JS scrapes loose DOM strings; server records each as `room_taken`, polluting availability | Fable, Codex | `content.js:108-130`; `api_server.py:285-312`; `board_parse.py` exists but is dead code |
| C4 | **Practice drafts contaminate portfolio exposure** — `practice-*` drafts write to same tables with `status='complete'`; no query excludes them | Fable | `practice.py:93`; exposure queries in `ledger.py` filter only on `status='complete'` |
| C5 | **Seed registry junk FA rows hijack name resolution** — surname-only BUY entries (Kelce, Chase, Hurts…) are separate player rows, recommendable late-round | Fable | `registry.py:185-209` |
| C6 | **Practice resume ignores `room_taken`** — resume cursor uses `all_picks` only; opponent auto-picks live in `room_taken` | Codex | `practice.py:91-92`; `ledger.py:591-615` vs `practice.py:229` |
| C7 | **Hardcoded W17 matchups + duplicate bye logic** — seasonal maintenance risk; `schedule.py` unused | Fable, Gemini | `recommender.py:185-194`; `config.py:58-68` vs `schedule.py:7` |
| C8 | **`combo_pct` SQL diverges from exposure policy** — only counts `complete` drafts; doc says in-progress at 50% weight | Fable, Gemini | `ledger.py:357`; `docs/BBM-EXPOSURE.md` |

---

## Unique (single auditor — still investigate)

| Auditor | Finding |
|---------|---------|
| **Fable** | Tested code ≠ shipped code: `board_parse.py` (538 lines, tested) never called; production uses untested `content.js` |
| **Fable** | GPP run hard-fails on Sleeper outage when `buzz_signal.enabled: true` — no degrade path (`project.py:68-72`, `sleeper.py:33-36`) |
| **Fable** | Dead `.venv` after repo move; pyenv global runs tests; `espn_api` not installed |
| **Fable** | No `/api/undo`; mis-clicked Rec advances round irreversibly from extension |
| **Fable** | GET `/api/recommendations` mutates pivot state (write-on-read); RB-run trigger is stubbed `round_num >= 5` |
| **Codex** | `injury_status` dropped from roster DataFrame before availability filter — out/doubtful players may inflate projections (`engine.py:55-58`, `availability.py:133-139`) |
| **Codex** | Combo cap prefilter uses rounded exposure — values just below cap blocked early (`ledger.py:367`, `recommender.py:248-250`) |
| **Gemini** | Brittle `aria-label` DOM dependency with no structure-change warning |

---

## Conflicts

| Topic | Fable | Codex | Gemini | Resolution |
|-------|-------|-------|--------|------------|
| Overall verdict | FAIL | FAIL | WARN | **FAIL rollup** — three critical BBM identity/state bugs are consensus; Gemini focused on structural debt, not live-db verification |
| Root cause framing | Missing identity/provenance layer | Permissive resolution reused across contexts | Hardcoded seasonal data | Both valid; **P0 = unify normalizer + strict pick resolution**; **P1 = seasonal data abstraction** |
| Practice exposure | Critical (contaminates portfolio) | Not flagged | Not flagged | **Investigate** — Fable verified no practice filter in SQL; treat as P0 if operator runs practice before paid entries |

---

## Recommended fix order

### P0 — before first paid Underdog entry

1. **Unify normalizers** — make `registry._normalize_merge` delegate to `normalize_adp.normalize_name`; re-sync registry
2. **Strict pick resolution** — never auto-stub on `pick`/`Rec`/`/api/pick`; stub allowed only for explicit `taken` with warning
3. **Remove junk FA seed rows** — drop surname-only BUY loop or store as aliases, not `players_dim` rows; exclude `team='FA'` from recommendations
4. **Fix extension sync contract** — narrow DOM scrape to drafted-player container; report unmatched names instead of stubbing; wire or delete `board_parse.py`
5. **Practice draft isolation** — add `is_practice` column or filter `draft_id NOT LIKE 'practice-%'` in all exposure/portfolio/reconcile queries
6. **Fix practice resume** — include `room_taken` count when restoring pick cursor

### P1 — weekly / before GPP slate

7. **Buzz/ESPN degrade gracefully** — wrap network overlays in try/except; warn + continue on outage
8. **Fix `combo_pct` in-progress weighting** — align SQL with `exposure_pct` and `BBM-EXPOSURE.md`
9. **Keep `injury_status` in roster DataFrame** — regression test out/doubtful exclusion
10. **Centralize schedule data** — wire `schedule.py`; fetch W17 via nflreadpy or config file
11. **Recreate `.venv`** at new path; `pip install -e ".[bbm,espn]"`

### P2 — operator UX

12. **`/api/undo` + extension button**; `bbm abandon` for stale in-progress drafts
13. **Advisory pivots only** — stop write-on-read from GET recommendations; implement real RB-run check
14. **Combo cap rounding** — compare raw exposure, round for display only
15. **Localhost POST token** — optional static header on mutating endpoints

---

## Verdict rollup

| Model | Verdict |
|-------|---------|
| claude-fable-5-thinking-max | FAIL |
| gpt-5.3-codex | FAIL |
| gemini-3.1-pro | WARN |

**Overall: REWORK** — DFS pipeline core (nflverse projections, pydfs optimize path) is structurally sound and test-covered, but the **BBM copilot has three verified silent-failure modes** (normalizer split-brain, stub-on-pick, practice/exposure contamination) that would mislead live Underdog picks. Do **not** enter paid BBM drafts until P0 items 1–6 land. GPP runs are usable today with buzz enabled, but add degrade-on-outage (P1 #7) before slate morning.

---

## Next steps (operator choice)

- [x] `/goal` P0 patch sprint (normalizer + strict pick + practice isolation) — **2026-07-01**
- [ ] Re-audit after P0 with third-lens swapped to `grok-4.3` (fresh eyes per reference.md)
- [ ] `super-audit` (5-model) if shipping extension to others
