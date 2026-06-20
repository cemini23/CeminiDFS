# Architecture

Canonical design doc: [Gambling wiki — DIY NFL DFS model architecture](https://github.com/cemini23/gambling-wiki/blob/main/wiki/concepts/diy-nfl-dfs-model-architecture.md)

## Layer mapping

| Wiki layer | CeminiDFS module | Phase |
|------------|------------------|-------|
| Data + legal | `ceminidfs.data` | 1 |
| Implied totals | `ceminidfs.models.implied_totals` | 1–2 |
| Volume / pace | `ceminidfs.models.volume` | 2 |
| Usage | `ceminidfs.models.usage` | 2 |
| Stat engine | `ceminidfs.models.stats` | 2 |
| Scoring | `ceminidfs.models.scoring` | 0 ✅ |
| Distribution | `ceminidfs.pipeline.simulate` | 5 |
| Export | `ceminidfs.export` | 0 ✅ |
| Orchestration | `ceminidfs.orchestrator` | 0 ✅ |

## v1 paradigm

**Stat-first regression:** volume × usage × efficiency → counting stats → FD/DK scoring.

v2 adds Monte Carlo + copula + ownership field simulation.

## Cross-wiki resources

- Weather APIs: `@osint-wiki` (Open-Meteo, NWS, Visual Crossing)
- Pipeline DAG: `@ccc-wiki` plan-then-execute orchestration
- CLV benchmark: `@gambling-wiki` line-shopping-and-clv

See [PLAN.md](../PLAN.md) for execution phases.
