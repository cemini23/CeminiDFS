# BBM7 P2 — data pipeline, backtest, and performance

**Date:** 2026-06-24  
**Prerequisite:** P0 + P1 shipped (`14803c9`)  
**Goal:** Validate recommender against historical picks; harden multi-CLI ops; weekly data refresh

---

## Scope

| ID | Patch | Files | Acceptance |
|----|-------|-------|------------|
| P2-1 | BBM III replay harness (real CSV + CI fixture) | `backtest.py`, `tests/fixtures/bbm/`, `cli.py` | `ceminidfs bbm backtest --fixture` runs replay; metrics JSON; no stub-only path when fixture present |
| P2-2 | In-memory draft replay engine | `backtest.py`, `session.py` helpers | Per-pick: run recommender, compare top-3 vs actual, CLV delta, structural pass |
| P2-3 | Recommender candidate prefilter + latency benchmark | `recommender.py`, `backtest.py` | p99 <200ms on 240-player pool (test asserts with margin) |
| P2-4 | SQLite WAL + busy_timeout | `ledger.py` | Central `connect_db()`; all ledger ops use it |
| P2-5 | Unknown opponent player stub | `ledger.py`, `cli.py` | `t Unknown Guy` creates `stub-*` player in dim; recommender excludes stubs from top-3 |
| P2-6 | CeminiDFS projection merge column | `normalize_adp.py`, `registry.py`, `cli.py` | `refresh-adp --projections proj.csv` updates `projection_pts` |
| P2-7 | Weekly refresh one-liner | `cli.py`, `scripts/bbm_weekly_refresh.sh` | `bbm refresh-weekly --adp X [--projections Y]` runs ADP + optional proj + sync |
| P2-8 | Tests: backtest fixture, latency, WAL, projection merge, stub | `tests/bbm/` | pytest green |

---

## Out of scope (Phase 3)

- MV3 browser overlay / DOM crawl
- Full registry expansion to 240 players (operator adds via refresh)
- Real BBM III download in CI (use committed fixture only)

---

## Agent split (parallel)

| Agent | Model | Tasks |
|-------|-------|-------|
| A | kimi-k2.5 | P2-1, P2-2 — backtest loader, replay, fixture, CLI `--fixture`/`--csv`/`--out` |
| B | kimi-k2.5 | P2-3, P2-4, P2-5 — WAL connect, unknown stub, recommender prefilter |
| C | gpt-5.4-mini-medium | P2-6, P2-7, P2-8 — projection merge, refresh-weekly, tests |

---

## Fixture format (CI)

```csv
draft_id,round,pick_num,slot,player_name,position,team,adp
room-001,1,1,1,Ja'Marr Chase,WR,CIN,1.8
...
```

Minimum: one 12-team room, 18 rounds (216 picks) or subset ≥36 picks for smoke.

---

## Verify

```bash
ruff check src/ceminidfs/bbm tests/bbm
pytest tests/bbm/ -q
ceminidfs bbm backtest --fixture tests/fixtures/bbm/sample_drafts.csv --sample 1
ceminidfs bbm refresh-weekly --adp research/bbtb-adp.csv  # if paths exist
pytest -q
```
