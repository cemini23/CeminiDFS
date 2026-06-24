# BBM7 P1 — remaining patches implementation plan

**Date:** 2026-06-24  
**Prerequisite:** P0 super-audit patches shipped (`768a8ee`)  
**Goal:** Live-draft ready for paid entries after 2–3 practice slow drafts

---

## Scope (P1 only — defer Phase 2 backtest)

| ID | Patch | Files | Acceptance |
|----|-------|-------|------------|
| P1-1 | Wire pivot state machine into recommender (once/draft) | `session.py`, `recommender.py`, `ledger.py` | Pivot warning prints; archetype updates in DB; not re-pivot same draft |
| P1-2 | Fix `_is_stack_lane_dead` + stack anchor IDs | `archetype.py` | C→A pivot fires when anchors gone |
| P1-3 | Player disambiguation: `p 2 Name` or numbered list | `ledger.py`, `cli.py` | Ambiguous query shows 1–5 options; `p N` selects |
| P1-4 | Resume shows room_taken count + last pivot warning | `ledger.py`, `cli.py`, `session.py` | Resume prints "N players marked taken" |
| P1-5 | Registry coverage preflight | `registry.py`, `session.py`, `cli.py` | Warn if <120 players or <8 teams |
| P1-6 | `refresh-adp` merge stats (exact/fuzzy/unmatched) | `normalize_adp.py`, `cli.py` | CLI prints breakdown |
| P1-7 | Seed `combo_pairs` from `STACK_PAIRS` on init | `ledger.py`, `config.py` | Burrow+Chase cap row exists |
| P1-8 | Reconcile: position-aware fuzzy match | `reconcile.py` | Match uses name+position when available |
| P1-9 | Regression tests: slot 12, round 18, pivot, refresh stats | `tests/bbm/` | pytest green |

---

## Agent split (parallel)

| Agent | Model | Files |
|-------|-------|-------|
| A | kimi-k2.5 | pivot wiring, archetype fixes, combo_pairs seed, ledger pivot column |
| B | kimi-k2.5 | player disambiguation, resume room_taken, registry preflight, cli UX |
| C | gpt-5.4-mini-medium | refresh-adp stats, reconcile match, tests |

---

## Out of scope (Phase 2 / P2)

- BBM III backtest harness with real data
- Recommender shortlist precompute (latency)
- SQLite WAL / multi-CLI locking
- MV3 browser overlay

---

## Verify

```bash
ruff check src/ceminidfs/bbm tests/bbm
pytest tests/bbm/ -q
pytest -q
```
