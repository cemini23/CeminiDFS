# CeminiDFS — Implementation Plan

> **Source:** [Gambling wiki — DIY NFL DFS model architecture (K125)](https://github.com/cemini23/gambling-wiki/blob/main/wiki/concepts/diy-nfl-dfs-model-architecture.md)  
> **Research:** 18 workstreams · 38 subagents · 6 execution waves (complete)  
> **Build method:** Opus 4.8 plan → GPT 5.5 parallel execution

## Mission

Build a **from-scratch NFL DFS projection pipeline** (FanDuel-primary) that emits normalized player CSVs → pydfs lineup optimizer. Stokastic/FantasyLabs are **accuracy and ownership benchmarks only** (manual CSV). Every modeling layer is backtest-justified; every data source is license-cleared.

## Architecture

```text
fetch → project → normalize → optimize [sim rerank]
          ↑ simulate, ownership (optional)
          ↑ backtest / benchmark / calibrate (analytics)
late-swap (post-lock)
```

### Layer stack

| Layer | Module | Status |
|-------|--------|--------|
| Data | `ceminidfs.data.*` | ✅ nflreadpy PBP/schedules/injuries; manual salary CSV |
| Vegas | `data.vegas` | ✅ schedules spread/total → implied totals |
| Weather | `data.weather` + `data.stadiums` | ✅ Open-Meteo + stadium lat/lon/roof |
| Environment | `models.implied_totals` | ✅ ITT |
| Volume | `models.volume` | ✅ pace, PROE, pass rate, play allocation |
| Usage | `models.usage` | ✅ rolling target/carry/air-yards shares, WOPR |
| Stats | `models.stats` | ✅ regressed efficiency → counting stats |
| Scoring | `models.scoring` | ✅ FD half-PPR + DK full-PPR |
| Simulation | `models.simulate` + `models.correlation` | ✅ team-shock + Gaussian copula |
| Ownership | `models.ownership` + `data.ownership_labels` | ✅ heuristic + ridge calibration |
| Export | `export.*` | ✅ canonical → pydfs → optimize → sim_rerank → late_swap |
| Analytics | `pipeline.backtest`, `pipeline.calibration`, `data.benchmark` | ✅ walk-forward + wiki brief |
| Orchestration | `orchestrator.run` + `orchestrator.validate` | ✅ manifest, lineup validation |

### v1 paradigm

**Stat-first regression:** team volume × player usage × regressed efficiency → counting stats → site scoring.

### v2 additions

Monte Carlo distributions (floor/ceiling), role-prior copula correlation, calibrated ownership from paid labels, pydfs candidate reranking by simulated lineup score, late-swap re-optimization.

## Execution phases (all complete)

### Phase 0 — Bootstrap ✅

Package skeleton, scoring, export adapters, CLI, RunManifest, CI, P0 audit fixes.

### Phase 1 — Data backbone ✅

| Track | Deliverable |
|-------|-------------|
| P1-A | Week-scoped fetch + parquet cache + manifest |
| P1-B | Vegas join → `vegas.parquet` |
| P1-C | Stadium table (roof, lat/lon) |
| P1-D | Open-Meteo weather → `weather.parquet` |
| P1-E | FD/DK salary → canonical parser |

**Exit:** `ceminidfs fetch --season 2024 --week 1` ✅

### Phase 2 — Projection engine ✅

Volume → usage → stats → scoring → `pipeline/engine.py` DIY stack.

**Exit:** Canonical CSV with DIY `fd_projection` for a cached week ✅

### Phase 3 — Integration + optimize ✅

| Track | Deliverable |
|-------|-------------|
| P3-A–C | canonical, normalize, optimize |
| P3-D | E2E `ceminidfs run` → 150 lineups + validation |

**Exit:** 150 FD lineups from DIY projections on synthetic slate ✅

### Phase 4 — Backtest + calibration ✅

| Track | Deliverable |
|-------|-------------|
| P4-A | Walk-forward backtest (MAE, RMSE, Spearman) |
| P4-B | Stokastic/Labs benchmark loader |
| P4-C | Calibration wiki brief generator |

### Phase 5 — Distribution ✅

| Track | Deliverable |
|-------|-------------|
| P5-A | Monte Carlo (`models/simulate.py`) |
| P5-B | Ownership heuristic (`models/ownership.py`) |
| P5-C | Late swap (`export/late_swap.py`) |
| P5v2-A | Role-prior Gaussian copula (`models/correlation.py`) |
| P5v2-B | Ownership calibration from paid labels |
| P5v2-C | Sim rerank — 2000 candidates → top 150 |

## Canonical CSV schema

From `@gambling-wiki/concepts/dfs-pipeline-integration-spec.md`:

**Required:** `slate_id`, `player_key`, `fd_id`, `fd_position`, `fd_salary`, `fd_projection`, `dk_*`, `team`, `opp`, `game`, `injury_status`

**Optional pass-through:** `Projected Ownership`, `Projection Floor`, `Projection Ceil`, exposure/deviation columns

## Config + secrets

| File | Tracked | Contents |
|------|---------|----------|
| `config/nfl_dfs.yaml` | yes | paths, projection_mode, simulate, ownership, sim_rerank, model hyperparams |
| `.env` | no | `ODDS_API_KEY`, `VISUAL_CROSSING_KEY` (see `.env.example`) |

## Directory layout

```text
CeminiDFS/
├── PLAN.md
├── README.md
├── docs/ARCHITECTURE.md
├── config/nfl_dfs.yaml
├── prompts/                 # Opus plans, audit prompts
├── src/ceminidfs/
│   ├── cli.py
│   ├── data/
│   ├── models/
│   ├── pipeline/
│   ├── export/
│   └── orchestrator/
├── tests/
│   └── fixtures/            # synthetic slate + cache helpers
├── artifacts/               # gitignored
├── runs/                    # gitignored
└── reports/                 # gitignored
```

## Build vs borrow

| Component | Verdict |
|-----------|---------|
| nflreadpy | **Borrow** |
| pydfs-lineup-optimizer | **Borrow** (MIT) |
| The Odds API | **Borrow** (optional live Vegas) |
| Open-Meteo | **Borrow** (free personal) |
| Projections + sim + ownership | **Build** |
| Salaries | **Manual** FD/DK export |
| Stokastic / FantasyLabs | **Benchmark** (manual CSV) |

## Cross-wiki references

| Need | Wiki |
|------|------|
| Architecture hub | `@gambling-wiki/concepts/diy-nfl-dfs-model-architecture.md` |
| Correlation / copula | `@gambling-wiki/concepts/dfs-correlation-stacking.md` |
| Distribution layer | `@gambling-wiki/concepts/dfs-distribution-layer.md` |
| Backtesting | `@gambling-wiki/concepts/dfs-backtesting-framework.md` |
| Ownership | `@gambling-wiki/concepts/dfs-ownership-projection.md` |
| Weather APIs | `@osint-wiki/entities/data-sources/open-meteo.md` |
| Pipeline DAG | `@ccc-wiki/concepts/plan-then-execute-topological-orchestration.md` |

## Future backlog (not started)

Operational and v3 enhancements — not blockers for live slate use:

- Contest ROI / dup-adjusted reranking (full field sim)
- Defense EPA opponent adjustments in stats layer
- Open-Meteo **archive** API for historical weather in backtests
- Injury play-probability redistribution in usage model
- DST stat-first projections (currently salary FPPG fallback)
- Automated GitHub release / PyPI publish

## Session handoff

**Workspace:** `/Users/claudiobarone/Desktop/projects/CeminiDFS`

**State:** Phases 0–5 complete. **103 tests**, CI green on `main`.

**Typical live workflow:**

1. `ceminidfs fetch --season YYYY --week N`
2. Export FanDuel salary CSV manually
3. `ceminidfs run --season YYYY --week N --salary FILE --stages all`
4. Optional: `--sim-rerank`, enable simulate/ownership in yaml
5. Upload lineups; use `late-swap` after early locks

**Typical research workflow:**

1. `ceminidfs backtest --season 2024 --start-week 5 --end-week 10`
2. `ceminidfs calibrate ...` → paste brief into Gambling wiki
3. `ceminidfs benchmark compare ...` when Stokastic/Labs export available
