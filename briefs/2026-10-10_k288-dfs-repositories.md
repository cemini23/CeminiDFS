# K288 — CeminiDFS: 19 live DFS repositories + Week-4 recap tool-gaps

**Date:** 2026-10-10 · **Batch:** K288 · **Home:** `../CeminiDFS/briefs/`
**Source:** `Evaluating DFS and Betting Repositories.docx` (20 rows) + `dfsrecapweek4.zip` — OSINT K288

## Target

CeminiDFS. `~/Projects/CeminiDFS`.

## Summary

FILE. **The eval docx says all 20 rows are dead. They are not.** Phase-0 (`gh api`) found **every GitHub repo live**. The docx's reachability check is broken. Below is the real list. Plus the Week-4 recap **tool-gaps** (all `do_not_auto_apply`). **No install. No scrape. No auto-submit.**

## Body

### 1. The DFS repos (live — the docx is wrong)

The docx marked 20/20 **UNAVAILABLE**. **All 19 GitHub repos returned metadata.** Stars are 0–1; several were pushed **weeks before** the docx ran, so they cannot have been "not yet created".

| Repo | Stars | Pushed |
|------|-------|--------|
| `nickdemarinis7/dfs-optimizer` | 0 | 10-10 |
| `kel-reid/DFS-Optimizer` | 0 | 10-10 |
| `nexona-dev/NFL-DFS-Simulator` | 0 | 10-07 |
| `dburch19142/NFL_Fanduel` | 0 | 10-08 |
| `carlie4real-beans/fanduel-optimizer` | 0 | 10-06 |
| `Authentic-66/FanDuel-DFS-Model` | 0 | 10-10 |
| `kenepp1031/nfl-prop-board` | 0 | 10-04 |
| `atlantahouseplants/MLBDFSLineupOptimizer` | 0 | 09-30 |
| `johnson-shuffle/fantasy` | 0 | 09-27 |
| `kycoonyatFD/nfl-assets-dashboard` | 0 | 09-23 |
| `everworldlife-netizen/fanduel-pace-totals` | 0 | 09-20 |

(Full list incl. the parlay-side rows in @osint-wiki/sources/eval-dfs-betting-repositories-2026-10-10.md.)

**Operator guidance (2026-10-10): for DFS and parlay evaluations, licence weight is lowered.** Judge on fit and technique. **Read these repos properly against the CeminiDFS solver before judging them** — the docx did not read one of them.

**Do not trust the docx's works-cited.** It synthesised citations from username substrings (an Atlanta plant shop for `atlantahouseplants/…`, a Vans sweatshirt for `Authentic-66/…`). The citations are generated filler.

### 2. Week-4 recap tool-gaps (`do_not_auto_apply = true` on every row)

From `dfsrecapweek4.zip`. **Review only. Do not auto-edit CeminiDFS.**

- **TG01 injury** — L01 rostered **Case Keenum at QB → 0.00** (Bagent started; Keenum took a ceremonial snap). L01 still scored 116; a starting QB (~19–20) would have made it the day's best (~135). → **Pre-lock QB gate:** require confirmed starter status; hard-warn when projected snap share < 90% or a starter change was announced in 72h.
- **TG02 stack_rules** — L03's four-man BUF stack scored 31.2 combined; non-Allen pass catchers 11.7. → **Cap QB+3 stacks to teams with concentrated target trees;** weight stack partners by prior-3-week target share, not team total.
- **TG03 ownership** — identical TE+DST pairs across lineups sank both. → **Exposure board:** limit identical TE+DST pairs in a slate; require ≥1 differentiated TE/DST per entry pair.
- **TG04 defense_multiplier** — Raiders DST 1.00, Bengals 4.00; neither forced a turnover. → **Downweight DSTs facing high implied totals;** surface opponent sack%/TO%; keep FR = opponent fumblesLost only.
- **TG05 projection** — cheap fills (Jaylen Wright 0.7, Palmer 0.8) busted. → **Show ceiling (P85) and bust (P15) bands;** flag value plays whose P15 ≈ 0.
- **TG06 weather / TG07 stadiums** — no evidence weather drove misses; roof games produced the top 3 scores. → **Keep weather as a pre-lock fade flag only;** show the roof flag next to the game total, do not auto-boost.

**Themes:** a **pre-lock QB gate**, **target-share-weighted stacking**, an **exposure board**, and **projection bands**. All are candidate gates, none auto-applied.

### Boundary

**No install. No clone.** **Never scrape sportsbook boards.** No repo edit from a recap desk.

## Sources

- [Source: @osint-wiki/sources/eval-dfs-betting-repositories-2026-10-10.md]
- [Source: @osint-wiki/concepts/k288-eval-wave.md]
