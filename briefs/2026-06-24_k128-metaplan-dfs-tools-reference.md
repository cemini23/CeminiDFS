## Target

`../projects/CeminiDFS/` — NFL DIY projection pipeline (FanDuel-primary).

## Summary

K128 **Tool Evaluation Analysis Metaplan** (81 URLs) delivers **zero Adopt rows for CeminiDFS**. Duplicate NBA/DFS optimizers (pydfs, draftfast, NBA-DFS-Tools) are reference-only; Setfive/fanduel-api WebSocket routes to CCC-wiki, not this repo.

## Body

### Source: OSINT wiki tool-eval-metaplan-81url-2026-06-24

| Repo | License | Verdict | Rationale |
|------|---------|---------|-----------|
| chanzer0/NBA-DFS-Tools | MIT | **Reference-only** | NBA-specific; duplicate optimizer logic |
| BenBrostoff/draftfast | MIT | **Reference-only** | DraftKings/NBA focus; overlaps pydfs |
| WolverineSportsAnalytics/basketball | MIT | **Reference-only** | Basketball-specific; no NFL lineage |
| davehensley/fanduel-nba-optimizer | MIT | **Reference-only** | NBA constraints; stale 2017 |
| Setfive/fanduel-api | Apache-2.0 | **CCC-wiki** | WebSocket contest feed; not projection infra |
| *GPL fork of fanduel-api* | GPL | **Reject** | License incompatible with CeminiDFS MIT |

### Pydfs-lineup-optimizer posture

- **Status:** Already integrated (borrowed MIT dependency)
- **Path:** `pyproject.toml` under `[project.optional-dependencies] optimize`
- **Scope:** Lineup generation + late swap only; no projection logic
- **No action required** — dependency already in production

### Data fetch posture unchanged

CeminiDFS retains **single canonical ingest path**: nflreadpy → nflverse parquet cache. No additional fetch clients added.

### Out of scope

- LongShu MLX game-dev models → Game Dev wiki K128
- WebSocket real-time feeds → CCC-wiki (gambling wiki consumption layer)

## Sources

- @wiki/sources/tool-eval-metaplan-81url-2026-06-24.md
- @gambling-wiki/entities/tools/pydfs-lineup-optimizer.md
