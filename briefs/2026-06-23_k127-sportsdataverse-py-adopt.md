## Target

`../projects/CeminiDFS/` — NFL DIY projection pipeline (FanDuel-primary).

## Summary

K127 **Cemini Tool Evaluation Plan.docx** sole Adopt: **sportsdataverse-py** (MIT, 104★, active Jun 2026). Evaluate as unified fetch client for sportsdataverse/nflverse-adjacent data before extending stage-2 ingestion.

## Body

### Phase-0 verdict (2026-06-23)

| Signal | Value |
|--------|-------|
| Repo | sportsdataverse/sportsdataverse-py |
| License | **MIT** (`gh api` confirmed) |
| Tier | Adopt |

### P0 — smoke + gap table

1. `pip install sportsdataverse` in CeminiDFS dev venv; fetch current-season PBP sample.
2. Map returned schema columns to existing `engine.py` stage-2 inputs — document gaps vs direct nflverse path.
3. Benchmark fetch latency + row completeness vs incumbent nflverse import on one 2024 slate.

### P1 — adopt or defer

- **Adopt** if schema coverage ≥95% on critical columns (attempts, targets, air yards, team pace) with simpler maintenance.
- **Defer** if redundant with nflverse-only path — keep wiki entity as reference.

### Out of scope

- Unlicensed steal-from rows in same eval (jjesse dashboard, yfs-api, thiagocavalheiro PM bot)
- ClarusC64 coherence features (K126 separate track)

## Sources

- [Source: Cemini Tool Evaluation Plan.docx (retrieved 2026-06-23)]
- @wiki/sources/cemini-tool-evaluation-plan-62url-2026-06-23.md
- @wiki/entities/tools/sportsdataverse-py.md
