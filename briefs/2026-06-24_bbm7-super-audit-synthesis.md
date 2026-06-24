# Super audit — CeminiBBM Draft Copilot

**Mode:** prod-ship · **Pack:** `reports/audit/pack-bbm7` · **Built:** 2026-06-24

| Slot | Channel | Role | Model | Verdict |
|------|---------|------|-------|---------|
| 1 | cursor | agentic-reasoning | gemini-3.1-pro | FAIL |
| 2 | cursor | code-implementation | kimi-k2.5 | WARN |
| 3 | cursor | third-lens | gpt-5.4-medium | FAIL |
| 4 | api | api-adversarial | z-ai/glm-5.2 | WARN |
| 5 | api | api-deep-reasoning | openrouter/fusion | FAIL |

## Strong consensus (≥4 auditors)

1. **Exposure denominator wrong** — `exposure_pct` divides by draft count, not `TOTAL_ENTRIES` (150); caps fire too early.
2. **Archetype REPL override is cosmetic** — `archetype X` does not change recommender or persist to DB.
3. **Resume/audit loses player metadata** — `get_draft_state()` omits `bye_week`/`adp`; validator runs blind after pick 1.
4. **Combo pair cap (25%) never enforced** in recommender despite `combo_pct()` in ledger.
5. **Global FADE vs round-band FADE** — Josh Allen etc. excluded all rounds, not just fade bands per brief §4.4.

## Consensus (≥3 auditors)

6. **QB bye validator gap** — duplicate bye only checked when adding 3rd QB, not 2nd.
7. **Hard violations filtered as WARNING** — illegal picks can appear in top-3 recommendations.
8. **`record_taken` + `undo` idempotency** — duplicate taken logs still append action_log; undo can resurrect players.
9. **Player name lookup** — `LIKE %name% LIMIT 1` risks wrong-player under clock pressure.

## Unique angles

- [GLM] Registry coverage cliff (~60 players) collapses archetype routing by data, not strategy.
- [Fusion] Bulk-entry SQLite concurrency + 50% in-progress weight race during multi-CLI weekends.

## Ranked patch backlog (implementation order)

| P | Patch | Effort |
|---|-------|--------|
| P0 | Exposure + combo_pct denominator → `TOTAL_ENTRIES` | S |
| P0 | QB/TE bye check on every add; CRITICAL severity for hard limits | S |
| P0 | `get_draft_state` full metadata; thread archetype override end-to-end | S |
| P0 | `record_taken` log only on insert; `INSERT OR REPLACE` picks | S |
| P0 | Round-band FADE (`fade_rounds` metadata + recommender check) | M |
| P0 | Combo pair cap in recommender | M |
| P1 | `assign_archetype` use `(target-current)/target` ratio | S |
| P1 | Player lookup: exact match first, multi-match disambiguation | M |
| P1 | Regression tests: exposure math, archetype override, slot 12 round 18 | M |

**Overall:** SHIP-WITH-FIXES — implement P0 patch set below before first $25 entry.
