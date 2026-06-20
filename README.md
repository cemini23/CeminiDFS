# CeminiDFS

DIY **NFL DFS projection pipeline** (FanDuel-primary). Builds from-scratch player projections from nflverse data, Vegas lines, and weather — then normalizes to pydfs format and generates lineups.

Research and architecture live in the [Gambling wiki](https://github.com/cemini23/gambling-wiki) (`concepts/diy-nfl-dfs-model-architecture.md`, K125).

## Status

**Phase 0 (bootstrap)** — package skeleton, scoring/ITT modules, export adapters, CLI orchestrator. Full stat projection engine is Phase 2.

## Quick start

```bash
git clone https://github.com/cemini23/CeminiDFS.git
cd CeminiDFS
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,data,optimize]"

# Run unit tests
pytest

# Fetch nflverse data (requires nflreadpy)
ceminidfs fetch --season 2024

# Full pipeline stub on a FanDuel salary CSV
ceminidfs run --season 2024 --week 1 --salary path/to/fanduel_salaries.csv --stages all
```

## Pipeline

```text
fetch → project → normalize → optimize
```

| Stage | Output |
|-------|--------|
| `fetch` | Parquet cache (schedules, PBP, injuries) |
| `project` | Canonical projection CSV |
| `normalize` | Site-specific pydfs CSV (FanDuel / DraftKings) |
| `optimize` | Lineup CSV via pydfs-lineup-optimizer |

See [PLAN.md](PLAN.md) for phased implementation roadmap.

## Configuration

- `config/nfl_dfs.yaml` — seasons, rolling windows, artifact paths (tracked)
- `.env` — `ODDS_API_KEY` for live Vegas (optional, gitignored)

Copy `.env.example` to `.env` when using The Odds API.

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
  pipeline/      # project, backtest (future)
  export/        # canonical CSV, normalize, optimize
  orchestrator/  # weekly run + manifest
```

## Related

- [Gambling wiki — DIY NFL DFS architecture](https://github.com/cemini23/gambling-wiki/blob/main/wiki/concepts/diy-nfl-dfs-model-architecture.md)
- [K125 master research plan](https://github.com/cemini23/gambling-wiki/blob/main/wiki/sources/research-diy-dfs-model-master-plan-2026-06-20.md)

## License

MIT
