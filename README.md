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
| **2** | Stat-first projection engine (volume → usage → stats) | Planned |
| **3** | End-to-end lineup generation on DIY projections | Partial (export layer done) |
| **4** | Backtest + calibration vs paid benchmarks | Planned |

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
| `project` | `ceminidfs project --season YYYY --week N --salary FILE` | Canonical projection CSV |
| `normalize` | `ceminidfs normalize --in FILE --out FILE --site fanduel` | pydfs importer CSV |
| `optimize` | `ceminidfs optimize --csv FILE --out FILE` | Lineup CSV |

Run all stages: `ceminidfs run --season 2024 --week 1 --salary FILE --stages all`

## Configuration

| File | Tracked | Purpose |
|------|---------|---------|
| `config/nfl_dfs.yaml` | Yes | Seasons, rolling windows, artifact paths |
| `.env` | No (gitignored) | Optional API keys — copy from `.env.example` |

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
