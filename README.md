# CeminiDFS

[![CI](https://github.com/cemini23/CeminiDFS/actions/workflows/ci.yml/badge.svg)](https://github.com/cemini23/CeminiDFS/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

DIY **NFL DFS projection pipeline** (FanDuel-primary). Builds player projections from nflverse play-by-play, Vegas lines, and weather; exports canonical CSVs; normalizes for [pydfs-lineup-optimizer](https://github.com/DimaKudosh/pydfs-lineup-optimizer); and generates MME lineup pools with optional simulation reranking.

Architecture and research: [Gambling wiki — DIY NFL DFS model (K125)](https://github.com/cemini23/gambling-wiki/blob/main/wiki/concepts/diy-nfl-dfs-model-architecture.md).

## Status

All implementation phases (0–5) are **complete**. The repo is ready for historical backtests and live-slate runs when you supply a FanDuel salary export and cached nflverse data.

| Phase | Scope | State |
|-------|--------|-------|
| **0** | Package skeleton, scoring, export adapters, CLI, manifest | Complete |
| **1** | Data backbone — nflverse fetch, Vegas, weather, salary ingest | Complete |
| **2** | Stat-first projection engine (volume → usage → stats → scoring) | Complete |
| **3** | End-to-end lineup generation on DIY projections | Complete |
| **4** | Backtest + calibration vs paid benchmarks | Complete |
| **5** | Simulation, ownership, late-swap, copula, sim rerank | Complete |

See [PLAN.md](PLAN.md) for the execution history and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module mapping.

## Quick start

```bash
git clone https://github.com/cemini23/CeminiDFS.git
cd CeminiDFS
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,data,optimize]"

# Unit + integration tests (no network; e2e tests need pydfs)
pytest

# Fetch nflverse data for a week (requires nflreadpy + network)
ceminidfs fetch --season 2024 --week 1

# Full pipeline on a FanDuel salary CSV
ceminidfs run --season 2024 --week 1 --salary path/to/fanduel_salaries.csv --stages all
```

Outputs land under `runs/{season}_week_{N}/` (canonical CSV, normalized pydfs CSV, lineups, manifest).

## Pipeline

```text
                         ┌─ backtest / benchmark / calibrate (analytics)
                         │
fetch → project ─────────┤ optional: simulate (floor/ceil), ownership
         │               │
         ▼               │
     normalize → optimize ─┴─ optional: sim rerank (2000 → 150)
         │
         └── late-swap (post-lock, locked teams preserved)
```

| Command | Purpose |
|---------|---------|
| `ceminidfs fetch` | Week-scoped parquet cache (schedules, PBP, injuries, Vegas, weather) + manifest |
| `ceminidfs project` | Canonical projection CSV (DIY or salary FPPG fallback) |
| `ceminidfs salary` | Salary-only canonical CSV (no projections) |
| `ceminidfs normalize` | Canonical → pydfs site CSV |
| `ceminidfs optimize` | pydfs lineup generation |
| `ceminidfs run` | Orchestrated multi-stage run with `RunManifest` |
| `ceminidfs late-swap` | Re-optimize after teams lock |
| `ceminidfs backtest` | Walk-forward MAE / RMSE / Spearman vs realized PBP points |
| `ceminidfs benchmark load` | Parse Stokastic/Labs export → versioned JSON snapshot |
| `ceminidfs benchmark compare` | Paid export vs actuals (+ DIY side-by-side) |
| `ceminidfs calibrate` | Wiki-ready calibration brief (Markdown + JSON) |
| `ceminidfs ownership calibrate` | Fit ownership calibration from paid export labels |

### Common invocations

**Full slate (DIY projections, 150 lineups):**

```bash
ceminidfs fetch --season 2024 --week 5
ceminidfs run --season 2024 --week 5 --salary path/to/fanduel.csv --stages all
```

**Sim rerank (generate 2000 candidates, keep top 150 by mean sim score):**

```bash
ceminidfs run --season 2024 --week 5 --salary FILE --stages all \
  --sim-rerank --candidates 2000 --final-count 150
```

**Historical accuracy (no salary CSV):**

```bash
ceminidfs fetch --season 2024 --week 1
ceminidfs backtest --season 2024 --start-week 5 --end-week 10 \
  --out reports/backtest_2024_w5-10.json
```

**Compare DIY to a Stokastic/Labs export:**

```bash
ceminidfs benchmark compare --season 2024 --week 5 --csv path/to/stokastic-export.csv
ceminidfs calibrate --season 2024 --start-week 5 --end-week 10 \
  --benchmark-csv path/to/stokastic-export.csv --benchmark-week 10
```

**Late swap after early games lock:**

```bash
ceminidfs late-swap \
  --lineups runs/2024_week_5/lineups.csv \
  --players runs/2024_week_5/normalized_players.csv \
  --lock-team KC --out runs/2024_week_5/lineups_late_swap.csv
```

## Configuration

Primary config: [`config/nfl_dfs.yaml`](config/nfl_dfs.yaml). Optional secrets: copy [`.env.example`](.env.example) to `.env` (gitignored).

| Key | Default | Description |
|-----|---------|-------------|
| `projection_mode` | `auto` | `auto` \| `diy` \| `fppg` — see below |
| `simulate.enabled` | `false` | Attach `Projection Floor` / `Projection Ceil` to canonical CSV |
| `simulate.method` | `team_shock` | `team_shock` \| `copula` (role-prior Gaussian copula) |
| `simulate.n_iterations` | `5000` | Monte Carlo draws per player |
| `ownership.enabled` | `false` | Attach `Projected Ownership` column |
| `ownership.calibration_path` | `null` | JSON from `ceminidfs ownership calibrate` |
| `sim_rerank.enabled` | `false` | Score pydfs candidate pool with sim matrix |
| `sim_rerank.candidates` | `2000` | pydfs pool size before rerank |
| `sim_rerank.final_count` | `150` | Lineups written after rerank |

**Projection modes**

- `auto` — DIY when fetch cache exists; otherwise salary-export FPPG.
- `diy` — Require cached Vegas/PBP; fail if missing.
- `fppg` — Salary FPPG placeholders only (wiring test / no model).

**Enable distribution layers:**

```yaml
simulate:
  enabled: true
  method: copula
ownership:
  enabled: true
  calibration_path: artifacts/ownership_calibration.json
sim_rerank:
  enabled: true
  candidates: 2000
  final_count: 150
```

**Ownership calibration** (optional, uses paid export as label source):

```bash
ceminidfs ownership calibrate \
  --labels path/to/stokastic.csv \
  --salary path/to/salary.csv \
  --season 2024 --week 5 \
  --out artifacts/ownership_calibration.json
```

Never commit `.env`. `ODDS_API_KEY` and `VISUAL_CROSSING_KEY` are optional.

## Data sources

| Source | Role | License |
|--------|------|---------|
| [nflreadpy](https://github.com/nflverse/nflreadpy) | PBP, schedules, injuries | CC-BY 4.0 |
| [Open-Meteo](https://open-meteo.com/) | Kickoff-hour weather | Free personal use |
| FanDuel / DraftKings | Salary CSV | Manual export only |
| [pydfs-lineup-optimizer](https://github.com/DimaKudosh/pydfs-lineup-optimizer) | Lineup generation | MIT |
| Stokastic / FantasyLabs | Benchmark + ownership labels | Paid; manual CSV only |

Paid tools are **benchmark-only** — not a runtime dependency.

## Project layout

```text
src/ceminidfs/
  cli.py              # Command-line entrypoint
  config.py           # YAML config loader
  manifest.py         # RunManifest + artifact tracking
  data/               # fetch, vegas, weather, stadiums, salary, benchmark, ownership_labels
  models/             # volume, usage, stats, scoring, simulate, correlation, ownership
  pipeline/           # fetch, project, engine, backtest, calibration, metrics
  export/             # canonical, normalize, optimize, sim_rerank, late_swap
  orchestrator/       # stage DAG, validation
config/nfl_dfs.yaml
tests/                # unit + integration + e2e (103 tests)
artifacts/            # gitignored — parquet cache, reports
runs/                 # gitignored — per-slate outputs + manifests
reports/              # gitignored — backtest/calibration JSON and briefs
prompts/              # Opus execution plans + audit prompts
```

## Development

```bash
pip install -e ".[dev,data,optimize]"
pytest
ruff check src tests
```

CI (`.github/workflows/ci.yml`) runs pytest + ruff on Python 3.11 and 3.12 with `[dev,data,optimize]` installed.

## Related

- [PLAN.md](PLAN.md) — phased implementation record
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — wiki layer → module map
- [K125 master research plan](https://github.com/cemini23/gambling-wiki/blob/main/wiki/sources/research-diy-dfs-model-master-plan-2026-06-20.md)

## License

MIT — see [LICENSE](LICENSE).
