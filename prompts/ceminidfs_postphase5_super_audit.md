# CeminiDFS Post-Phase 5 SUPER AUDIT — 6-model council

You are auditor **{{MODEL_SLOT}}** in a **6-model super audit** of **CeminiDFS** (NFL DFS projection pipeline, Phases 0–5 complete).

**Mode:** `architecture` + `code-debug` + `prod-ship` · **Readonly** — markdown report only; no edits.

---

## Mission (single sharp question)

Is the **current CeminiDFS codebase** (DIY projections, backtest, simulation, ownership, sim rerank, late-swap) **correct and production-safe** for FanDuel main-slate use — without logic bugs, data leakage, schema drift, or silent failures that would corrupt lineups or mislead backtests?

Deliver:

1. **Verdict** PASS / WARN / FAIL on ship posture for 2024–2025 season slates
2. **What's working** vs **what isn't** (logic, tests, orchestration, config, wiki alignment)
3. **Ranked patch backlog** (P0 before live slate, P1 research) — smallest diffs first
4. **Strategy gaps** — volume/usage/stats/sim/ownership/backtest assumptions vs K125 wiki; what will mis-rank players or inflate backtest metrics
5. **Domain deep-dive** — weather (stadium lat/lon, kickoff hour, timezone, dome vs open), Vegas join, PBP week cutoff, join keys, DEF/DST handling, copula vs team-shock, sim rerank correctness

---

## Context — project state (2026-06-20)

| Fact | Value |
|------|-------|
| Repo | `github.com/cemini23/CeminiDFS` |
| Workspace | `/Users/claudiobarone/Projects/CeminiDFS` |
| Tests | 103 passing (pytest + ruff CI) |
| Phases | 0–5 complete (DIY engine, backtest, calibration, simulate, ownership, late-swap, sim rerank) |
| Wiki hub | `@gambling-wiki/concepts/diy-nfl-dfs-model-architecture.md` (K125) |

### Pipeline

```text
fetch → project [simulate, ownership] → normalize → optimize [sim_rerank]
         ↑ backtest / benchmark / calibrate
late-swap (post-lock)
```

### Key modules to inspect (absolute paths)

| Area | Paths |
|------|-------|
| Data | `src/ceminidfs/data/fetch.py`, `vegas.py`, `weather.py`, `stadiums.py`, `salary.py`, `benchmark.py`, `ownership_labels.py` |
| Models | `volume.py`, `usage.py`, `stats.py`, `scoring.py`, `simulate.py`, `correlation.py`, `ownership.py`, `implied_totals.py` |
| Pipeline | `pipeline/fetch.py`, `project.py`, `engine.py`, `backtest.py`, `calibration.py`, `metrics.py` |
| Export | `export/canonical.py`, `normalize.py`, `optimize.py`, `sim_rerank.py`, `late_swap.py` |
| Orchestrator | `orchestrator/run.py`, `validate.py` |
| Config | `config/nfl_dfs.yaml`, `src/ceminidfs/config.py` |
| Tests | `tests/test_e2e_run.py`, `test_backtest.py`, `test_simulate.py`, `test_weather.py`, `test_stadiums.py` |

---

## Regime boundaries

- **Do not** treat salary FPPG fallback (`projection_mode: fppg` or auto fallback) as DIY model accuracy — wiring only.
- **Do not** compare backtest MAE to live Stokastic without same-week export snapshot.
- **Historical backtest** uses nflverse PBP actuals — not contest ROI or ownership duplication.
- **Open-Meteo forecast URL** is wrong for historical backtests; archive API not wired.
- **Synthetic e2e slate** (KC/BUF, 44 players) validates plumbing — not full main-slate diversity.

---

## Focus areas (must address)

### Logic & bugs
- Walk-forward leakage in volume/usage/stats/sim/backtest (week boundaries, team pace using future PBP)
- Join key mismatches: salary ↔ DIY (`name+team+position`), benchmark ↔ actuals, sim rerank name index
- DEF/DST projection fallback vs stat-first stack gap
- Orchestrator silent failures, manifest completeness, lineup validation edge cases
- Copula correlation matrix PSD / role assignment errors; sim rerank scoring math

### Weather & stadiums
- Per-team lat/lon accuracy; LAC/LAR SoFi shared venue; timezone for kickoff hour selection
- Dome/retractable/semi_open → `is_weather_exposed()` correctness
- Open-Meteo hourly alignment to **kickoff** (not midnight UTC); game_date/game_time parsing from schedules
- Wind tiers in volume pass-rate adjustment

### Strategy & gaps
- Missing opponent defensive adjustment (stats `defense_multiplier` stub)
- Ownership heuristic vs calibrated ridge — label leakage risk
- Sim rerank uses mean sim score only — no ownership/duplication (wiki gap)
- Paid benchmark compare join on `join_key` — TE/WR position mismatch in actuals
- Phase 5 v2 copula priors vs empirical W-CORR wiki table — over/under correlation?

### Tests & CI
- Coverage holes that would hide regressions on real slates
- pydfs deprecation warnings; tiny-slate relaxations masking production constraints

---

## Data pack files (READ these paths)

```
{pack_index}
```

---

## Prior audit (Phase 0 — validate, do not repeat blindly)

Phase 0 synthesis (`reports/audit/ceminidfs_phase0_super_audit_synthesis.md`): canonical schema drift, silent orchestration, RunManifest unused — **verify fixed or still open**.

---

## Required output format

### Verdict
PASS | WARN | FAIL — one line why

### Findings
| Severity | Finding | Evidence (file:line or behavior) | Fix |
|----------|---------|----------------------------------|-----|

### Ship recommendation
- Live slate ready? Y/N · Backtest trustworthy? Y/N · Sim rerank safe? Y/N

### Root cause
One paragraph on the highest-impact issue — or "insufficient evidence" + what to inspect next.

### Ranked patch backlog
| P | Patch | Effort | Expected lift |
|---|-------|--------|---------------|

### Unique angle
One thing other auditors might miss

### Confidence
high | medium | low

---

## Constraints

- Readonly — no code edits
- Cite evidence with file paths and line numbers when possible
- Separate **confirmed bugs** from **design gaps / future work**
- Do not recommend paywalled data sources as runtime dependencies

---

## Already ruled out

- Repo missing entirely; CI not running; zero tests
- Stokastic API integration (manual CSV only by design)
