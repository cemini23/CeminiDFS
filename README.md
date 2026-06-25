# CeminiDFS

[![CI](https://github.com/cemini23/CeminiDFS/actions/workflows/ci.yml/badge.svg)](https://github.com/cemini23/CeminiDFS/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

DIY **NFL DFS projection pipeline** (FanDuel-primary) plus a **Best Ball Mania draft copilot** for Underdog slow drafts. The core pipeline builds player projections from nflverse play-by-play, Vegas lines, and weather; exports canonical CSVs; normalizes for [pydfs-lineup-optimizer](https://github.com/DimaKudosh/pydfs-lineup-optimizer); and generates MME lineup pools with optional simulation reranking. The BBM tool (`ceminidfs bbm`) tracks exposure across 150 entries and surfaces top-3 picks during live drafts.

Architecture and research: [Gambling wiki — DIY NFL DFS model (K125)](https://github.com/cemini23/gambling-wiki/blob/main/wiki/concepts/diy-nfl-dfs-model-architecture.md).

## Status

The **weekly DFS pipeline** (phases 0–5) is **complete** — ready for historical backtests and live-slate runs when you supply a FanDuel salary export and cached nflverse data. The **BBM draft copilot** (Best Ball Mania VII) ships as an optional `[bbm]` extra with its own CLI, ledger, and recommender.

| Phase | Scope | State |
|-------|--------|-------|
| **0** | Package skeleton, scoring, export adapters, CLI, manifest | Complete |
| **1** | Data backbone — nflverse fetch, Vegas, weather, salary ingest | Complete |
| **2** | Stat-first projection engine (volume → usage → stats → scoring) | Complete |
| **3** | End-to-end lineup generation on DIY projections | Complete |
| **4** | Backtest + calibration vs paid benchmarks | Complete |
| **5** | Simulation, ownership, late-swap, copula, sim rerank | Complete |
| **BBM** | Underdog best-ball draft copilot — REPL, exposure ledger, recommender, audit | Complete |

See [PLAN.md](PLAN.md) for the execution history, [ROADMAP.md](ROADMAP.md) for data-source posture, [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module mapping, and [docs/BBM.md](docs/BBM.md) for the best-ball operator guide.

## Quick start

```bash
git clone https://github.com/cemini23/CeminiDFS.git
cd CeminiDFS
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,data,optimize]"   # weekly DFS pipeline
pip install -e ".[bbm,dev]"            # + Best Ball Mania draft copilot

# Unit + integration tests (no network; e2e tests need pydfs)
pytest

# Fetch nflverse data for a week (requires nflreadpy + network)
ceminidfs fetch --season 2024 --week 1

# Full pipeline on a FanDuel salary CSV
ceminidfs run --season 2024 --week 1 --salary path/to/fanduel_salaries.csv --stages all
```

Outputs land under `runs/{season}_week_{N}/` (canonical CSV, normalized pydfs CSV, lineups, manifest).

### Best Ball Mania (optional)

```bash
pip install -e ".[bbm,dev]"

ceminidfs bbm draft-card --out briefs/bbm7-draft-card-$(date +%F).md
ceminidfs bbm draft --slot 4          # interactive REPL: p / t / undo / sync / exp
ceminidfs bbm audit --draft-id <id>   # post-draft checklist
```

**Single-monitor (extension):**

```bash
ceminidfs bbm serve --slot 4 --port 8765
# Load extension/bbm-copilot in Chrome; set draft ID in popup; open Underdog draft room
```

Full operator guide: [docs/BBM.md](docs/BBM.md).

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
| `ceminidfs backtest-prepare` | Batch-fetch nflverse caches for a season range (offseason setup) |
| `ceminidfs historical-slate` | Synthetic FanDuel salary CSV from nflverse (no live slate export) |
| `ceminidfs benchmark load` | Parse Stokastic/Labs export → versioned JSON snapshot |
| `ceminidfs benchmark compare` | Paid export vs actuals (+ DIY side-by-side) |
| `ceminidfs calibrate` | Wiki-ready calibration brief (Markdown + JSON) |
| `ceminidfs sleeper trending` | Sleeper add/drop buzz (K129 optional sentiment) |
| `ceminidfs luck-metrics` | Team Pythagorean expected wins vs actual |
| `ceminidfs regression` | One command: optional prepare + backtest + calibrate + lineup backtest |
| `ceminidfs lineup-backtest` | Synthetic slate → pydfs optimize → score vs actuals |
| `ceminidfs benchmark replay` | Replay every paid CSV in a folder across weeks |
| `ceminidfs ownership calibrate` | Fit ownership calibration from paid export labels |

### Best Ball Mania (`ceminidfs bbm`)

Requires `pip install -e ".[bbm]"`. See [docs/BBM.md](docs/BBM.md).

| Command | Purpose |
|---------|---------|
| `ceminidfs bbm draft` | Live draft REPL with top-3 recommendations (`--slot`, `--draft-id`) |
| `ceminidfs bbm draft-card` | Markdown cheat sheet (stacks, fades, exposure caps) |
| `ceminidfs bbm refresh-adp` | Merge BBTB ADP CSV into local registry |
| `ceminidfs bbm refresh-weekly` | ADP + optional projection CSV, sync to SQLite |
| `ceminidfs bbm audit` | Post-draft structural + CLV audit |
| `ceminidfs bbm reconcile` | Diff local exposure vs Underdog email CSV |
| `ceminidfs bbm backtest` | Replay BBM III picks vs recommender (fixture or downloaded CSV) |
| `ceminidfs bbm serve` | Local HTTP API for Chrome extension overlay (`--slot`, `--draft-id`, `--port`) |

**Chrome extension (optional):** load `extension/bbm-copilot/` unpacked — read-only top-3 panel on Underdog with manual board scan. See [docs/BBM.md](docs/BBM.md#chrome-extension-phase-3).

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
# One-time season cache (offseason — no FanDuel export needed)
ceminidfs backtest-prepare --season 2024 --start-week 1 --end-week 18

# Walk-forward projection accuracy vs nflverse actuals
ceminidfs backtest --season 2024 --start-week 5 --end-week 17 \
  --out reports/backtest_2024_w5-17.json

# Wiki brief with DIY vs rolling-FPPG baseline + per-position MAE
ceminidfs calibrate --season 2024 --start-week 5 --end-week 17 \
  --out reports/calibration_2024.md --json-out reports/calibration_2024.json

# Full offseason regression (backtest + calibrate + lineup backtest in one shot)
ceminidfs regression --season 2024 --start-week 5 --end-week 17 --output-dir reports

# Fail when DIY accuracy regresses beyond nfl_dfs.yaml gates
ceminidfs regression --season 2024 --start-week 5 --end-week 17 --fail-on-regression

# Lineup-level validation (requires pydfs-lineup-optimizer)
ceminidfs lineup-backtest --season 2024 --start-week 5 --end-week 17
```

**Full pipeline without a live FanDuel slate (synthetic salary from nflverse):**

```bash
ceminidfs historical-slate --season 2024 --week 10 --out artifacts/slates/2024_w10_fd.csv
ceminidfs run --season 2024 --week 10 --salary artifacts/slates/2024_w10_fd.csv --stages all
```

Synthetic slates use walk-forward rolling FPPG for the `FPPG` column and position-tier salary bands — good for optimizer smoke tests and DIY projection runs, not for contest ROI modeling.

**Compare DIY to a Stokastic/Labs export:**

```bash
ceminidfs benchmark compare --season 2024 --week 5 --csv path/to/stokastic-export.csv
ceminidfs calibrate --season 2024 --start-week 5 --end-week 10 \
  --benchmark-csv path/to/stokastic-export.csv --benchmark-week 10

# Replay a folder of weekly Stokastic/Labs exports (names like *w5*.csv)
ceminidfs benchmark replay --season 2024 --start-week 5 --end-week 10 \
  --dir path/to/benchmark_exports/
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
| `regression.max_overall_mae` | `4.85` | DIY walk-forward MAE gate for `ceminidfs regression --fail-on-regression` |
| `regression.max_qb_mae` | `6.75` | Per-position QB MAE gate |
| `usage.min_backup_start_qb_pass_attempts` | `12` | Detect backup-start weeks from prior-week pass share |
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
  cli.py              # Command-line entrypoint (DFS + bbm subcommand)
  config.py           # YAML config loader
  manifest.py         # RunManifest + artifact tracking
  bbm/                # Best Ball Mania draft copilot (optional [bbm] extra)
  data/               # fetch, vegas, weather, stadiums, salary, benchmark, ownership_labels
  models/             # volume, usage, stats, scoring, simulate, correlation, ownership
  pipeline/           # fetch, project, engine, backtest, calibration, metrics
  export/             # canonical, normalize, optimize, sim_rerank, late_swap
  orchestrator/       # stage DAG, validation
config/nfl_dfs.yaml
scripts/bbm_weekly_refresh.sh   # weekly ADP + projection wrapper
extension/bbm-copilot/          # Chrome MV3 overlay (optional)
tests/                # unit + integration + e2e + tests/bbm/
data/bbm/             # gitignored — SQLite ledger, player registry
artifacts/            # gitignored — parquet cache, reports
runs/                 # gitignored — per-slate outputs + manifests
reports/              # gitignored — backtest/calibration JSON and briefs
prompts/              # Opus execution plans + audit prompts
docs/BBM.md           # Best Ball operator guide
```

## Development

```bash
pip install -e ".[dev,data,optimize,bbm]"
pytest
ruff check src tests
```

CI (`.github/workflows/ci.yml`) runs pytest + ruff on Python 3.11 and 3.12 with `[dev,data,optimize,bbm]` installed.

## Related

- [PLAN.md](PLAN.md) — phased implementation record
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — wiki layer → module map
- [docs/BBM.md](docs/BBM.md) — Best Ball Mania draft copilot guide
- [K125 master research plan](https://github.com/cemini23/gambling-wiki/blob/main/wiki/sources/research-diy-dfs-model-master-plan-2026-06-20.md)

## License

MIT — see [LICENSE](LICENSE).
