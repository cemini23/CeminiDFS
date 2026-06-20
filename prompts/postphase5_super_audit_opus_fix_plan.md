# Opus 4.8 fix plan — CeminiDFS super-audit P0/P1

## Goal
Make Phases 0–5 production-safe for FanDuel main slates after 6-model council findings.

## Execution batches (GPT 5.5 subagents / parent)

### Batch A — Simulation & correlation (P0)
1. `export/sim_rerank.py`: `score_lineup(..., quantile=0.85)` default; update tests.
2. `models/correlation.py`: map `opponent`→`opp`; derive `game` when missing.
3. `pipeline/engine.py`: add `opp`, `game` on scored frame; merge into canonical rows.

### Batch B — Data contract (P0)
4. `data/fetch.py`: never week-filter PBP when writing week cache (season scope).
5. `pipeline/project.py` + `config/nfl_dfs.yaml`: default `diy`; `allow_fppg_fallback` for tests only.
6. `export/canonical.py`: pass through FanDuel name columns.

### Batch C — Weather & stadiums (P1)
7. `data/weather.py`: `timezone=America/New_York`; archive API for past dates.
8. `data/stadiums.py` + weather: null wind for `semi_open` canopies.

### Batch D — Backtest & ownership (P1)
9. `pipeline/backtest.py`: roster-derived position for receiving actuals; min-player guard.
10. `models/ownership.py`: skip labels with `week >= target_week`.
11. `models/simulate.py`: cap Cholesky jitter at 1e-6, raise if still singular.
12. `export/late_swap.py`: verify locks applied post-mutation.
13. `orchestrator/run.py`: require name column in saved sim matrix parquet.

## Verification
```bash
cd /Users/claudiobarone/Desktop/projects/CeminiDFS
python -m pytest tests/ -q
python -m ruff check src tests
```

## Out of scope (document only)
- Full `defense_multiplier` EPA implementation
- DST stat-first model
- Ownership/dup in sim rerank objective
- Multi-team production optimizer fixture
