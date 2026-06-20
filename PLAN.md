# CeminiDFS — Implementation Plan

> **Source:** `@gambling-wiki/concepts/diy-nfl-dfs-model-architecture.md` (K125, 2026-06-20)  
> **Research:** 18 workstreams · 38 subagents · 6 execution waves (complete)  
> **This doc:** Opus 4.8 execution plan → GPT 5.5 parallel build

## Mission

Build a **from-scratch NFL DFS projection pipeline** (FanDuel-primary) that emits normalized player CSVs → pydfs lineup optimizer. Stokastic/FantasyLabs = accuracy benchmark only. Every layer backtest-justified; every source license-cleared.

## Architecture (v1 target)

```text
fetch → project → [sim v2] → normalize → optimize
         ↑ backtest loop (v1.1)
```

### Layer stack

| Layer | Module | v1 scope |
|-------|--------|----------|
| Data | `ceminidfs.data.*` | nflreadpy PBP/schedules/injuries; manual salary CSV |
| Vegas | `data.vegas` | `load_schedules` historical; Odds API live (optional) |
| Weather | `data.weather` | Open-Meteo + stadium table |
| Environment | `models.implied_totals` | ITT + game environment score |
| Volume | `models.volume` | Team plays, pass/run split, PROE stub |
| Usage | `models.usage` | Snap share proxy (no paywalled routes) |
| Stats | `models.stats` | Stat-first regression → counting stats |
| Scoring | `models.scoring` | FD half-PPR + DK full-PPR |
| Export | `export.*` | Canonical CSV → pydfs normalize → optimize |
| Orchestration | `orchestrator.run` | Manifest, parquet cache, stage DAG |

## Execution phases

### Phase 0 — Bootstrap ✅ complete

- [x] Public repo `cemini23/CeminiDFS`
- [x] `pyproject.toml` + package layout
- [x] `PLAN.md`, `README.md`, `config/nfl_dfs.yaml`
- [x] Core: `scoring`, `implied_totals`, `manifest`, `config`
- [x] Port: `normalize` + `optimize` from gambling-wiki scripts
- [x] CLI: `ceminidfs run --stages fetch|project|normalize|optimize|all`
- [x] Unit + integration tests (scoring, ITT, pipeline DAG)
- [x] P0 audit fixes: canonical schema, fail-loud orchestration, RunManifest wiring
- [x] GitHub CI (pytest + ruff)
- [x] Push to GitHub

### Phase 1 — Data backbone (Week 1) 🔄 in progress

**Parallel tracks:**

| Track | Deliverable | Dependency | Status |
|-------|-------------|------------|--------|
| P1-A | `pipeline/fetch.py` + week-scoped parquet + fetch manifest | none | done |
| P1-B | `data/vegas.py` — schedules spread/total join + `vegas.parquet` | P1-A | done |
| P1-C | `data/stadiums.py` — roof type + lat/lon | none | done |
| P1-D | `data/weather.py` — Open-Meteo hourly | P1-C | pending |
| P1-E | Salary ingest — FD/DK CSV parser → canonical schema | none | partial (`project.py`) |

**Exit criteria:** `ceminidfs fetch --season 2024 --week 1` writes week-scoped parquet + fetch manifest.

### Phase 2 — Projection engine v1 (Week 2–3)

| Track | Deliverable |
|-------|-------------|
| P2-A | `models/volume.py` — team plays from ITT + pace prior |
| P2-B | `models/usage.py` — target/carry/snap shares from rolling PBP |
| P2-C | `models/stats.py` — efficiency regressions → counting stats |
| P2-D | `models/scoring.py` — integrate bonuses, emit fd/dk columns |
| P2-E | `pipeline/project.py` — wire layers → `player_projection_base.parquet` |

**Exit criteria:** Canonical CSV with `fd_projection` per player for a historical week.

### Phase 3 — Integration + optimize (Week 3) — partial

| Track | Deliverable | Status |
|-------|-------------|--------|
| P3-A | `export/canonical.py` — schema from integration spec | done |
| P3-B | `export/normalize.py` — `--site fanduel\|draftkings` | done |
| P3-C | `export/optimize.py` — pydfs wrapper | done |
| P3-D | End-to-end `ceminidfs run --week N` on manual salary slate | needs Phase 2 projections |

**Exit criteria:** 150 FD lineups from DIY projections on a real slate CSV.

### Phase 4 — Backtest + calibration (Week 4)

| Track | Deliverable |
|-------|-------------|
| P4-A | `pipeline/backtest.py` — walk-forward, MAE/RMSE/Spearman |
| P4-B | Paid CSV benchmark loader (Stokastic/Labs manual export) |
| P4-C | Calibration report → wiki brief |

### Phase 5 — v2 distribution (future)

- Monte Carlo + copula (`models/simulate.py`)
- Ownership model (`models/ownership.py`)
- Late swap (`export/late_swap.py`)

## Canonical CSV schema

From `@gambling-wiki/concepts/dfs-pipeline-integration-spec.md`:

**Required:** `slate_id`, `player_key`, `fd_id`, `fd_position`, `fd_salary`, `fd_projection`, `dk_*`, `team`, `opp`, `game`, `injury_status`

**Optional pass-through:** `Projected Ownership`, `Projection Floor`, `Projection Ceil`, exposure/deviation columns

## Config + secrets

| File | Tracked | Contents |
|------|---------|----------|
| `config/nfl_dfs.yaml` | yes | seasons, rolling windows, paths, stack defaults |
| `.env` | no | `ODDS_API_KEY`, optional Visual Crossing |

## Directory layout

```text
CeminiDFS/
├── PLAN.md
├── README.md
├── pyproject.toml
├── config/nfl_dfs.yaml
├── src/ceminidfs/
│   ├── cli.py
│   ├── config.py
│   ├── manifest.py
│   ├── data/
│   ├── models/
│   ├── pipeline/
│   ├── export/
│   └── orchestrator/
├── tests/
└── artifacts/          # gitignored — parquet, CSV, manifests
```

## Build vs borrow

| Component | Verdict |
|-----------|---------|
| nflreadpy | **Borrow** |
| pydfs-lineup-optimizer | **Borrow** (MIT) |
| The Odds API | **Borrow** (CONDITIONAL quota) |
| Open-Meteo | **Borrow** (free personal) |
| Projections v1 | **Build** |
| Ownership | **Build** (v2) |
| Salaries | **Manual** FD/DK export |

## Cross-wiki references

| Need | Wiki |
|------|------|
| Architecture hub | `@gambling-wiki/concepts/diy-nfl-dfs-model-architecture.md` |
| Weather APIs | `@osint-wiki/entities/data-sources/open-meteo.md` |
| Pipeline DAG | `@ccc-wiki/concepts/plan-then-execute-topological-orchestration.md` |
| CLV benchmark | `@gambling-wiki/concepts/line-shopping-and-clv.md` |

## Session handoff

**Current workspace:** `/Users/claudiobarone/Desktop/projects/CeminiDFS`

**Active:** Phase 1-D — Open-Meteo weather join (requires stadiums ✅). Next: P1-E salary parser.
