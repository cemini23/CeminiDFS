# BBM7 P4 — pre-entry prep (from 2026-06-24 research synthesis)

**Date:** 2026-06-25  
**Prerequisite:** P0–P3 on `cursor/bbm-serve-startup-ux` (merge before paid entries)  
**Operator context:** No paid Underdog entries until next week — need **free practice** path.

---

## Gap analysis (briefs + super-audit vs codebase)

| Source | Gap | Status |
|--------|-----|--------|
| Brief §9 Phase 0–3 | Core CLI/ledger/recommender | ✅ Shipped |
| Brief §8 | BBM III backtest with real CSV | ⚠️ Fixture only; no download helper |
| Brief §11 Spike 4 | Mock slow draft practice | ❌ Not built |
| Brief §11 Spike 5 | Exposure policy documented | ❌ Not documented |
| Brief §4.7 | Tie-breakers when scores tie | ❌ Functions exist, unused in sort |
| Brief §4.6 / archetype | `should_force_archetype_pick` | ❌ Not wired into recommender |
| Super-audit GLM | Registry ~88 players (need 120+) | ⚠️ Warn only; thin board |
| Brief §10 resume | Pivot warning on resume | ⚠️ Partial (live recs only) |
| P3 extension | Record pick from panel | ⚠️ API exists; extension read-only |
| K129 Sleeper brief | ROADMAP + buzz + luck metrics | ✅ Shipped (`docs/sleeper-sentiment-eval.md`) |

---

## P4 scope (implement now)

| ID | Patch | Files | Acceptance |
|----|-------|-------|------------|
| P4-1 | **Free practice mock draft** (`bbm practice`) | `practice.py`, `cli.py` | 12-team snake sim; opponents auto-pick by ADP; user picks on their clock with top-3 |
| P4-2 | Wire archetype force + tie-breakers | `recommender.py` | Forced-position boost; stable sort with brief tie-break chain |
| P4-3 | Registry expand from ADP CSV | `registry.py`, `normalize_adp.py` | `refresh-adp` adds unknown ADP rows as NEUTRAL players; coverage ≥120 when CSV has 240 |
| P4-4 | Exposure policy doc + resume pivot line | `docs/BBM-EXPOSURE.md`, `cli.py` | Hard 100% / soft 95% documented; resume prints pivot warning |
| P4-5 | BBM III data helper + tests | `backtest.py`, `cli.py`, `tests/bbm/` | `bbm fetch-bbm3` prints URL/validate path; practice + tiebreak tests |

---

## Out of scope

- Sleeper API integration (K129 — main DFS ROADMAP only)
- Underdog scrapers (brief NEVER)
- Paid-entry automation

---

## Agent split

| Agent | Model | Tasks |
|-------|-------|-------|
| A | kimi-k2.5 | P4-1 practice mock draft |
| B | kimi-k2.5 | P4-2 recommender force + tiebreakers; P4-4 resume pivot |
| C | gpt-5.4-mini-medium | P4-3 registry expand; P4-4 exposure doc; P4-5 fetch-bbm3 + tests |

---

## Verify

```bash
pytest tests/bbm/ -q
ceminidfs bbm practice --slot 4 --rounds 3   # smoke: 3 rounds free
ruff check src/ceminidfs/bbm tests/bbm
```
