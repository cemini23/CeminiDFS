# Architecture

Canonical design reference: [Gambling wiki — DIY NFL DFS model architecture (K125)](https://github.com/cemini23/gambling-wiki/blob/main/wiki/concepts/diy-nfl-dfs-model-architecture.md)

Implementation record: [PLAN.md](../PLAN.md)

## System overview

CeminiDFS is a **stat-first** NFL DFS pipeline. It ingests nflverse data and manual salary exports, produces site-scored player projections, optionally simulates outcome distributions, and feeds [pydfs-lineup-optimizer](https://github.com/DimaKudosh/pydfs-lineup-optimizer) for FanDuel/DraftKings lineup generation.

```text
┌─────────────┐     ┌──────────────────────────────────────┐
│ nflreadpy   │────▶│ fetch → week cache (parquet)         │
│ Open-Meteo  │     └──────────────────────────────────────┘
└─────────────┘                    │
                                   ▼
┌─────────────┐     ┌──────────────────────────────────────┐
│ FD/DK       │────▶│ project                              │
│ salary CSV  │     │  volume → usage → stats → scoring    │
└─────────────┘     │  optional: simulate, ownership       │
                    └──────────────────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────────────┐
                    │ normalize → pydfs CSV              │
                    └──────────────────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────────────┐
                    │ optimize (pydfs)                     │
                    │  optional: sim_rerank                │
                    └──────────────────────────────────────┘
                                   │
                                   ▼
                         lineups.csv + RunManifest

Analytics (parallel): backtest · benchmark · calibrate
Post-lock: late_swap

BBM (optional): ceminidfs bbm — exposure ledger + live draft recommender
```

## BBM (Best Ball Mania extension)

Separate from the weekly DFS pipeline. Activated via `pip install -e ".[bbm]"` and `ceminidfs bbm …`. Operator guide: [BBM.md](BBM.md).

```text
player_registry.json + BBTB ADP CSV
        │
        ▼
  normalize_adp / merge_projections
        │
        ▼
  ledger (SQLite WAL) ── exposure across 150 entries
        │
        ▼
  draft REPL ── session ── recommender (top-3)
        │              │
        │              ├── validator (hard constraints)
        │              └── archetype router + pivot
        ▼
  audit / reconcile / backtest (BBM III replay)
```

| Component | Module | Role |
|-----------|--------|------|
| CLI + REPL | `ceminidfs.bbm.cli` | `draft`, `draft-card`, `refresh-adp`, `refresh-weekly`, `audit`, `reconcile`, `backtest` |
| Session bridge | `ceminidfs.bbm.session` | Draft state, pivot wiring, recommendation bridge |
| Recommender | `ceminidfs.bbm.recommender` | CLV + stack + archetype + exposure scoring |
| Validator | `ceminidfs.bbm.validator` | Bye, roster limits, exposure caps |
| Archetype | `ceminidfs.bbm.archetype` | Portfolio targets A–E, pivot state machine |
| Ledger | `ceminidfs.bbm.ledger` | SQLite drafts, picks, room_taken, combo_pairs |
| Registry | `ceminidfs.bbm.registry` | Seed BUY/FADE players, coverage preflight |
| ADP merge | `ceminidfs.bbm.normalize_adp` | BBTB CSV → registry; projection column merge |
| Reconcile | `ceminidfs.bbm.reconcile` | Underdog exposure CSV diff |
| Audit | `ceminidfs.bbm.audit` | Post-draft checklist + CLV |
| Backtest | `ceminidfs.bbm.backtest` | BBM III pick replay vs recommender |
| Local API | `ceminidfs.bbm.api_server` | `ceminidfs bbm serve` — extension bridge |
| Board parse | `ceminidfs.bbm.board_parse` | aria-label name extraction (shared w/ extension) |
| Extension | `extension/bbm-copilot/` | MV3 read-only overlay (manual scan) |
| Scoring reuse | `models.scoring.score_half_ppr_season` | Optional season half-PPR `projection_pts` |

Runtime artifacts: `data/bbm/bbm7.db`, `data/bbm/player_registry.json` (gitignored).

## Wiki layer → module mapping

| Wiki layer | CeminiDFS module | Notes |
|------------|------------------|-------|
| Data + legal | `ceminidfs.data.fetch`, `data.salary` | nflreadpy; manual salary only |
| Vegas / ITT | `data.vegas`, `models.implied_totals` | Historical spreads/totals from schedules |
| Weather | `data.weather`, `data.stadiums` | Open-Meteo forecast at kickoff |
| Volume / pace | `models.volume` | Plays, pass rate, allocation |
| Usage | `models.usage` | Rolling shares, WOPR, QB starter |
| Stat engine | `models.stats` | Regressed YPA/YPC/YPT → counting stats |
| Scoring | `models.scoring` | FD half-PPR, DK full-PPR |
| Correlation | `models.correlation` | Role-prior matrix (W-CORR) |
| Distribution | `models.simulate` | team_shock or Gaussian copula MC |
| Ownership | `models.ownership`, `data.ownership_labels` | Heuristic + optional ridge calibration |
| Export | `export.canonical`, `export.normalize`, `export.optimize` | pydfs handoff |
| Sim rerank | `export.sim_rerank` | Candidate pool → top-N by sim score |
| Late swap | `export.late_swap` | Locked-team pydfs rerun |
| Backtest | `pipeline.backtest`, `pipeline.metrics` | Walk-forward vs PBP actuals |
| Benchmark | `data.benchmark`, `pipeline.benchmark_compare` | Stokastic/Labs CSV |
| Calibration | `pipeline.calibration` | Wiki brief + JSON |
| Orchestration | `orchestrator.run`, `orchestrator.validate` | Stage DAG, manifest, lineup QA |
| Sleeper buzz (K129) | `data.sleeper`, `models.buzz_signal` | Optional stage-0 trending sentiment |
| Luck metrics (K129) | `pipeline.luck_metrics` | Pythagorean expected wins for calibration context |
| ESPN adjunct (K138) | `data.espn` | Optional roster injury overlay when `league_id` set |

## Projection engine (Phase 2)

Data flow for DIY mode (`projection_mode: diy` or `auto` with cache):

```text
vegas.parquet + pbp.parquet (+ weather.parquet)
        │
        ▼
  build_week_volume()     team plays, pass attempts, rush attempts
        │
        ▼
  build_week_usage()      player targets, carries, pass attempts
        │
        ▼
  build_week_stats()      counting stat projections
        │
        ▼
  add_fantasy_points()    fd_projection, dk_projection
        │
        ▼
  merge → canonical CSV
```

Historical PBP is cut at `week < target` for walk-forward integrity (backtest and live project).

EPA-based defense ratings apply `epa_eligible_plays()` (`data/pbp_filters.py`) before aggregating team pass/rush EPA — see [epa-cleanroom-audit.md](epa-cleanroom-audit.md).

Join key for salary ↔ model: **name + team + position** (`normalize_join_key` in `pipeline/engine.py`).

## Coherence-Risk Layer (K126)

K126 is **on by default** (`coherence_risk.enabled: true`). It sits between usage and stats, then again before scoring:

- `models.coherence_risk` derives walk-forward team stress/tendency indices from nflverse PBP only
- red-zone playcall adjustments tilt `build_week_usage()` outputs before `build_week_stats()` (`red_zone_playcall.enabled`)
- pass-protection penalties trim QB/WR/TE yardage projections after the stats layer (`pass_protection.enabled`)
- `models.simulate` widens player CVs when high-risk coherence flags are present

See [coherence-risk-audit.md](coherence-risk-audit.md) for the full 10-signal gap table and clean-room posture.

## Sleeper sentiment layer (K129)

Optional **stage-0 buzz** from Sleeper public API — does not alter DIY projections.

- `data.sleeper` — stdlib HTTP client for trending add/drop + cached player index
- `models.buzz_signal` — match buzz to slate rows; capped ownership nudge when enabled
- `pipeline.luck_metrics` — team Pythagorean expected wins vs actual (MME calibration context)

See [sleeper-sentiment-eval.md](sleeper-sentiment-eval.md) and [ROADMAP.md](../ROADMAP.md).

## ESPN injury adjunct (K138)

Optional roster injury tokens from ESPN fantasy API (`espn_api` MIT package) when `espn_adjunct.enabled` and `league_id` are set. Fills empty canonical `injury_status` fields only — nflverse remains primary.

See [espn-api-eval.md](espn-api-eval.md).

## Distribution layer (Phase 5)

| Method | Module | When to use |
|--------|--------|-------------|
| `team_shock` | `simulate.simulate_fd_points` | Fast default; shared latent per team |
| `copula` | `simulate` + `correlation` | Role-prior correlations (QB–WR1, bring-back, etc.) |

Simulation outputs **P20 / P50 / P90** as `Projection Floor` / `Projection Ceil` on the canonical CSV.

**Sim rerank** (`export/sim_rerank.py`): pydfs generates `candidates` lineups; each lineup is scored by mean simulated FD points across players; top `final_count` are written.

## Analytics layer (Phase 4)

| Tool | Input | Output |
|------|-------|--------|
| `backtest` | Season PBP cache | JSON MAE/RMSE/Spearman per week |
| `benchmark compare` | Paid export CSV + PBP | DIY vs benchmark accuracy |
| `calibrate` | Week range (+ optional benchmark) | Markdown wiki brief + JSON |

No salary CSV required for backtest — roster is inferred from historical usage on teams in the slate.

## Orchestration and artifacts

`ceminidfs run` executes stages in order: `fetch → project → normalize → optimize`.

Each run writes `runs/{season}_week_{N}/manifest.json` (`RunManifest`) with:

- Git commit and config hash
- Stage completion status
- Artifact paths (canonical, normalized, lineups)
- `lineup_count`, `projection_source`, validation summary

Lineup CSVs are validated for row count and empty slots (`orchestrator/validate.py`).

## Configuration surface

See [`config/nfl_dfs.yaml`](../config/nfl_dfs.yaml):

- `projection_mode` — `auto` | `diy` | `fppg`
- `simulate.*` — Monte Carlo toggles and method
- `ownership.*` — ownership projection and calibration path
- `sim_rerank.*` — candidate pool reranking
- `volume.*`, `usage.*`, `stats.shrinkage.*` — model hyperparameters

## External dependencies

| Package | Extra | Purpose |
|---------|-------|---------|
| `nflreadpy` | `[data]` | nflverse fetch |
| `pyarrow` | `[data]` | Parquet cache |
| `pydfs-lineup-optimizer` | `[optimize]` | Lineup generation + late swap |
| `pytest`, `ruff` | `[dev]` | CI |
| `rapidfuzz`, `nflreadpy` | `[bbm]` | ADP name match; bye-week lookup for registry |

### Data fetch posture

CeminiDFS uses **one canonical ingest path**: [nflreadpy](https://github.com/nflverse/nflreadpy) → nflverse parquet cache (`data/fetch.py`). We do **not** ship Yahoo JSON scrapers or alternate league API clients.

MIT-licensed repos evaluated for contrast only (not integrated):

- [nflverse/nfl_data_py](https://github.com/nflverse/nfl_data_py) — same data lineage as nflreadpy
- [bbenbenek/nfl-fantasy-football](https://github.com/bbenbenek/nfl-fantasy-football) — Yahoo API wrapper; duplicates fetch stage
- [hvpkod/NFL-Data](https://github.com/hvpkod/NFL-Data) — static CSV backtest parameters
- [sportsdataverse/sportsdataverse-py](https://github.com/sportsdataverse/sportsdataverse-py) — unified sports fetch client; **evaluated K127**, **deferred** — see [sportsdataverse-eval.md](sportsdataverse-eval.md). Same nflverse parquet lineage; prod remains nflreadpy.

Unlicensed repos (null `license` on GitHub) are **reference-only** for clean-room audits — e.g. playmaking EPA edge cases documented in [epa-cleanroom-audit.md](epa-cleanroom-audit.md) without R code merge.

### Reference-only DFS tools (K128)

Duplicate optimizers evaluated in the 2026-06-24 metaplan (NBA-DFS-Tools, draftfast, WolverineSportsAnalytics) are **wiki-only** — see [briefs/2026-06-24_k128-metaplan-dfs-tools-reference.md](../briefs/2026-06-24_k128-metaplan-dfs-tools-reference.md). pydfs-lineup-optimizer remains the sole borrowed dependency for lineup generation.

## Cross-wiki resources

- Correlation priors: `@gambling-wiki/concepts/dfs-correlation-stacking.md`
- Distribution design: `@gambling-wiki/concepts/dfs-distribution-layer.md`
- Backtest targets: `@gambling-wiki/concepts/dfs-backtesting-framework.md`
- Ownership spec: `@gambling-wiki/concepts/dfs-ownership-projection.md`
- Injury / late swap ops: `@gambling-wiki/concepts/dfs-injury-and-news-workflow.md`
- Weather: `@osint-wiki/entities/data-sources/open-meteo.md`
- Orchestration pattern: `@ccc-wiki/concepts/plan-then-execute-topological-orchestration.md`
