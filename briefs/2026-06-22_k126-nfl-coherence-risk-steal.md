## Target

`../projects/CeminiDFS/` — NFL DIY projection pipeline (FanDuel-primary).

## Summary

K126 links.docx flags **10 MIT ClarusC64 coherence-risk datasets** + Karmane rest/travel sample — tactical breakdown features missing from nflverse-only stage 2. Steal methodology via clean-room PBP derivation; do not add Hugging Face runtime dependency.

## Body

### Source cluster (links.docx URLs 30–39)

| Signal | HF dataset | License |
|--------|------------|---------|
| Playcall vs defense coherence | ClarusC64/nfl-playcall-defense-coherence-risk-v0.1 | MIT |
| Pass protection breakdown | ClarusC64/nfl-pass-protection-coherence-risk-v0.1 | MIT |
| Defense motion adjustment | ClarusC64/nfl-defense-motion-adjustment-coherence-risk-v0.1 | MIT |
| Route timing | ClarusC64/nfl-route-timing-coherence-risk-v0.1 | MIT |
| QB read vs coverage | ClarusC64/nfl-qb-read-coverage-coherence-risk-v0.1 | MIT |
| Drive momentum | ClarusC64/nfl-drive-momentum-coherence-risk-v0.1 | MIT |
| Workload → injury | ClarusC64/nfl-player-workload-injury-coherence-risk-v0.1 | MIT |
| Red-zone playcall | ClarusC64/nfl-red-zone-playcall-coherence-risk-v0.1 | MIT |
| Fourth-down decision | ClarusC64/nfl-fourth-down-decision-coherence-risk-v0.1 | MIT |
| Rest/travel spot | Karmane/nfl-rest-advantage-travel-spot-research-sample | CC-BY-4.0 |

### P0 — feature audit + two prototypes

1. Map each coherence dimension to existing CeminiDFS stage-2 columns (gap table in ARCHITECTURE.md).
2. Prototype **pass-protection coherence** penalty on QB/WR projections when OL unit stress exceeds threshold.
3. Prototype **red-zone playcall coherence** adjustment on TE/RB RZ usage.
4. Backtest 2024 slates vs K125 baseline; report MAE delta on top-50 FanDuel scores.

### P1 — ownership sim coupling

Feed coherence-risk flags into copula/sim layer as variance multipliers (high breakdown risk → higher ownership leverage on contrarian stacks).

### Out of scope

- HF parquet import in prod fetch path
- thiagocavalheiro PM sports bot (reject in same eval batch)

## Sources

- [Source: links.docx (retrieved 2026-06-22)]
- @wiki/sources/links-6-22-tool-eval.md
- @wiki/concepts/nfl-coherence-risk-features.md
- Gambling wiki `concepts/diy-nfl-dfs-model-architecture.md` (canonical CeminiDFS architecture)
