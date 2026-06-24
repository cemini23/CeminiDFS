# CeminiBBM Draft Copilot — super audit (5 auditors)

You are auditor **{{MODEL_SLOT}}** in a **5-model super audit**.

**Mode:** `prod-ship` · **Readonly** — markdown report only; no edits.

---

## Mission (single sharp question)

Is **CeminiBBM** (BBM7 draft copilot CLI) **correct and safe to use for live $25 Underdog drafts** — without logic bugs, exposure miscounts, constraint violations, strategy drift from the brief, or REPL failures that would mislead picks during a 30s fast draft?

Deliver:

1. **Verdict** PASS/WARN/FAIL on live-draft readiness
2. **What's working** vs **what isn't** (code, ledger, recommender, validator, CLI, strategy alignment)
3. **Ranked patch backlog** (P0 before first paid entry, P1 weekly) — smallest diffs first
4. **Strategy gaps** — archetype router, exposure caps, bye/stack rules, CLV scoring vs brief §4
5. **Operator risk** — what breaks mid-draft, silent wrong recommendations, data loss on resume

---

## Context — project state (2026-06-24)

| Fact | Value |
|------|-------|
| Repo | `github.com/cemini23/CeminiDFS` commit on main |
| Package | `src/ceminidfs/bbm/` |
| Brief | `briefs/2026-06-24_bbm7-draft-copilot-implementation-brief.md` |
| Tests | 9 BBM tests + full suite in CI with `bbm` extra |
| CLI | `ceminidfs bbm draft|draft-card|refresh-adp|audit|reconcile|backtest` |

### Key modules (READ ALL)

| Area | Paths |
|------|-------|
| Config/strategy | `src/ceminidfs/bbm/config.py`, `schedule.py` |
| Models | `src/ceminidfs/bbm/models.py` |
| Ledger | `src/ceminidfs/bbm/ledger.py` |
| Recommender | `src/ceminidfs/bbm/recommender.py`, `archetype.py`, `validator.py` |
| Session/CLI | `src/ceminidfs/bbm/session.py`, `cli.py` |
| Data | `src/ceminidfs/bbm/registry.py`, `normalize_adp.py`, `reconcile.py` |
| Tests | `tests/bbm/test_bbm_core.py` |

---

## Regime boundaries

- **Do not** expect BBM III backtest data (stub until download).
- **Do not** require Underdog API (manual sync only — by design).
- **Do not** compare to FanDuel MME pydfs optimize path — BBM is snake draft state machine.
- **Seed registry** (~60 players) is MVP; weekly ADP refresh expands coverage.
- **Strategy source of truth** is embedded brief §4, not gambling-wiki live sync.

---

## Focus areas (must address)

### Logic & bugs
- Snake draft pick_num calculation (odd/even rounds, slot)
- `record_taken` vs `record_pick` — round advancement, room_taken table
- Exposure_pct: complete vs in_progress 50% weight; denominator (total drafts vs 150 entries)
- Recommender exposure_fn signature vs ledger return type
- Archetype assignment vs portfolio gap; pivot state machine triggers
- Validator: QB bye distinct, TE cluster bye, team cap archetype C, bye limits teammates exempt
- Available player filtering (taken ids, FADE exclusion)
- CLI: resume draft, undo, sync board, archetype override persistence
- SQLite schema: picks PK (draft_id, round) — one pick per round limitation

### Strategy alignment (brief §4)
- Exposure cap tiers and soft brake at cap-5%
- Archetype E ignores caps
- Stack mult cap 1.4, clv_delta >= 3 for stack-reach
- Round-band multipliers per archetype A–E
- Combo pair cap 25%
- BUY/FADE lists and round-band FADE enforcement

### Operator / UX
- REPL latency target <200ms
- Missing player in registry during live draft
- refresh-adp merge accuracy
- reconcile CSV column tolerance

---

## Prior audit consensus

None — first super audit of BBM package.

---

## Required output format

### Verdict
PASS | WARN | FAIL — one line why

### Findings
| Severity | Finding | Evidence | Fix |
|----------|---------|----------|-----|

### Live-draft recommendation
- GO / GO-WITH-FIXES / NO-GO for first $25 entry
- Pre-draft checklist (3 bullets)

### Root cause
One paragraph on the highest-risk failure mode.

### Ranked patch backlog
| P | Patch | Effort | Expected lift |
|---|-------|--------|---------------|

### Unique angle
One thing other auditors might miss

### Confidence
high | medium | low

---

## Constraints

- Readonly — cite file paths and line-level behavior
- Smallest safe diffs for fixes
- P0 = would cause wrong pick or lost draft state during live room

---

## Already ruled out

- Underdog scraping / auto-pick (out of scope, ToS)
- Contest sim parity with ETR/Solver (never build per brief)
