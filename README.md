# CeminiDFS

[![CI](https://github.com/cemini23/CeminiDFS/actions/workflows/ci.yml/badge.svg)](https://github.com/cemini23/CeminiDFS/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

DIY **NFL DFS projection pipeline** (FanDuel-primary). Builds player projections from nflverse data, Vegas lines, and weather — then exports canonical CSVs, normalizes for pydfs, and generates lineups.

Architecture and research: [Gambling wiki — DIY NFL DFS model](https://github.com/cemini23/gambling-wiki/blob/main/wiki/concepts/diy-nfl-dfs-model-architecture.md) (K125).

## Status

| Phase | Scope | State |
|-------|--------|-------|
| **0** | Package skeleton, scoring, export adapters, CLI, manifest | Complete |
| **1** | Data backbone — nflverse fetch, Vegas, weather, salary ingest | In progress |
| **2** | Stat-first projection engine (volume → usage → stats → scoring) | Complete |
| **3** | End-to-end lineup generation on DIY projections | Complete |
| **4** | Backtest + calibration vs paid benchmarks | Complete (P4-A/B/C) |
| **5** | Simulation, ownership, late-swap, copula, sim rerank | Complete (v1 + v2) |

See [PLAN.md](PLAN.md) for the full roadmap.

## Quick start

```bash
git clone https://github.com/cemini23/CeminiDFS.git
cd CeminiDFS
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,data,optimize]"

# Unit tests (no network)
pytest

# Fetch nflverse data for a week (requires nflreadpy + network)
ceminidfs fetch --season 2024 --week 1

# Full pipeline on a FanDuel salary CSV
ceminidfs run --season 2024 --week 1 --salary path/to/fanduel_salaries.csv --stages all
```

## Pipeline

```text
fetch → project → normalize → optimize
```

| Stage | Command | Output |
|-------|---------|--------|
| `fetch` | `ceminidfs fetch --season YYYY --week N` | Parquet cache (schedules, pbp, injuries, vegas, weather) + fetch manifest |
| `project` | `ceminidfs project --season YYYY --week N --salary FILE` | Canonical projection CSV with DIY projections when cache exists; salary FPPG fallback in auto mode |
| `salary` | `ceminidfs salary --season YYYY --week N --salary FILE --out FILE` | Canonical CSV from salary only (no projections) |
| `normalize` | `ceminidfs normalize --in FILE --out FILE --site fanduel` | pydfs importer CSV |
| `optimize` | `ceminidfs optimize --csv FILE --out FILE` | Lineup CSV |
| `late-swap` | `ceminidfs late-swap --lineups FILE --players FILE --lock-team KC --out FILE` | Re-optimized lineups with locked-team players preserved |
| `backtest` | `ceminidfs backtest --season YYYY --start-week N --end-week M` | JSON accuracy report (MAE/RMSE/Spearman) |
| `benchmark load` | `ceminidfs benchmark load --csv FILE --out snapshot.json` | Parse Stokastic/Labs export to versioned JSON |
| `benchmark compare` | `ceminidfs benchmark compare --season YYYY --week N --csv FILE` | Benchmark vs actuals (+ DIY side-by-side) |
| `calibrate` | `ceminidfs calibrate --season YYYY --start-week N --end-week M` | Wiki-ready calibration brief (MD + JSON) |

Run all stages: `ceminidfs run --season 2024 --week 1 --salary FILE --stages all`

Simulation rerank generates a larger pydfs candidate pool, scores each lineup against simulated player outcomes, and writes the top final lineups:

```bash
ceminidfs run --season 2024 --week 1 --salary FILE --stages all --sim-rerank --candidates 2000 --final-count 150
ceminidfs optimize --csv runs/2024_week_1/normalized_players.csv --out runs/2024_week_1/lineups.csv --sim-rerank
```

Historical accuracy (no salary CSV required):

```bash
ceminidfs fetch --season 2024 --week 1   # populates season PBP cache
ceminidfs backtest --season 2024 --start-week 5 --end-week 10 --out reports/backtest_2024_w5-10.json

# Compare a manual Stokastic/Labs export against realized points
ceminidfs benchmark compare --season 2024 --week 5 --csv path/to/stokastic-export.csv

# Full calibration brief for gambling wiki (optional benchmark snapshot week)
ceminidfs calibrate --season 2024 --start-week 5 --end-week 10 --benchmark-csv path/to/stokastic-export.csv --benchmark-week 10
```

## Configuration

| File | Tracked | Purpose |
|------|---------|---------|
| `config/nfl_dfs.yaml` | Yes | Seasons, rolling windows, artifact paths |
| `.env` | No (gitignored) | Optional API keys — copy from `.env.example` |

`projection_mode` in `config/nfl_dfs.yaml` controls projection behavior:

- `auto` (default): use cached DIY projections when `fetch` artifacts exist, otherwise fall back to salary-export FPPG.
- `diy`: require cached `vegas.parquet` and `pbp.parquet`; run `ceminidfs fetch --season YYYY --week N` before `project`.
- `fppg`: use salary-export FPPG placeholders.

Optional v2 layers in `config/nfl_dfs.yaml` (default off):

```yaml
simulate:
  enabled: true
  method: copula      # or team_shock (v1 default)
sim_rerank:
  enabled: true
  candidates: 2000
  final_count: 150
ownership:
  enabled: true
  calibration_path: artifacts/ownership_calibration.json  # optional
```

Calibrate ownership from a Stokastic/Labs export:

```bash
ceminidfs ownership calibrate --labels path/to/export.csv --salary path/to/salary.csv \
  --season 2024 --week 5 --out artifacts/ownership_calibration.json
```

**Secrets:** Never commit `.env`. API keys (`ODDS_API_KEY`, etc.) are optional and loaded only from your local environment.

## Data sources

| Source | Role | License |
|--------|------|---------|
| [nflreadpy](https://github.com/nflverse/nflreadpy) | PBP, schedules, injuries | CC-BY 4.0 |
| [Open-Meteo](https://open-meteo.com/) | Weather forecast | Free personal use |
| FanDuel / DraftKings | Salary CSV | Manual export only |
| [pydfs-lineup-optimizer](https://github.com/DimaKudosh/pydfs-lineup-optimizer) | Lineup generation | MIT |

Stokastic / FantasyLabs exports are **benchmark-only** — not required to run.

## Project layout

```text
src/ceminidfs/
  data/          # fetch, vegas, weather
  models/        # scoring, implied totals, volume, usage, stats
  pipeline/      # fetch, project, backtest
  export/        # canonical CSV, normalize, optimize
  orchestrator/  # stage DAG + RunManifest
config/          # nfl_dfs.yaml
tests/           # unit + integration tests
artifacts/       # gitignored — parquet, CSV, manifests
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
```

CI runs on every push to `main` (pytest + ruff, Python 3.11 and 3.12).

## Related

- [PLAN.md](PLAN.md) — implementation phases
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — layer mapping
- [K125 master research plan](https://github.com/cemini23/gambling-wiki/blob/main/wiki/sources/research-diy-dfs-model-master-plan-2026-06-20.md)

## License

MIT — see [LICENSE](LICENSE).
