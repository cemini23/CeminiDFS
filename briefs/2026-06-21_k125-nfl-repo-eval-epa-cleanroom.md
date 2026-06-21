## Target

`../projects/CeminiDFS/` — NFL DIY projection pipeline (FanDuel-primary).

## Summary

K125 tool-eval confirms **nflverse** as canonical fetch path; stage **clean-room EPA edge-case audit** inspired by `danmorse314/nfl-stuff` (null license — no R merge). Reject unlicensed Yahoo scrapers and Rust PM sports bot.

## Body

### Tool-eval verdicts (2026-06-21)

| Repo | License (`gh api`) | Action |
|------|---------------------|--------|
| `nflverse/nfl_data_py` | MIT | **Keep** — already canonical |
| `bbenbenek/nfl-fantasy-football` | MIT | REFERENCE only — Yahoo API duplicates fetch stage |
| `hvpkod/NFL-Data` | MIT | REFERENCE — static CSV backtest params |
| `danmorse314/nfl-stuff` | **null** | Clean-room EPA audit (half-sack / tackle exclusions) |
| `thiagocavalheiro/polymarket-sports-trading-bot` | **null** | **Reject** — PM bot surface, not CeminiDFS |

### P0 — EPA edge-case clean-room

1. Document eval claim: R `playmaking_epa_function.R` excludes half-sacks and specific tackle types skewing EPA.
2. Diff against CeminiDFS PBP filters in `src/ceminidfs/data/fetch.py` / scoring layer.
3. If gap found, patch Python filters + add regression fixture (no R code copy).

### P1 — fetch posture

- Do **not** add Yahoo JSON scrapers — nflverse + nflreadpy remain single fetch path.
- Optional: cite MIT repos in gambling-wiki as educational contrast in ARCHITECTURE.md footnote.

### Out of scope

- Installing `MinaDo7a/yfs-api` (TypeScript Yahoo wrapper)
- Porting Rust PM sports bot

## Sources

- [Source: GitHub Repository Evaluation And Classification.docx (retrieved 2026-06-21)]
- @wiki/sources/github-nfl-repo-eval-cemini-2026-06-21.md
- Gambling wiki `concepts/diy-nfl-dfs-model-architecture.md` (canonical CeminiDFS architecture)
- `.local/reports/license-spot-check-2026-06-21-0901.txt`
