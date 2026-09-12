# DFS / fantasy optimizer peer sweep (2026-09-12)

**Type:** license-gated steal board. No vendor of no-LICENSE source.
**Retrieved:** Sat 12 Sep 2026, GitHub API.

## Already shipped in CeminiDFS (this weekend)

`--stack qb:3|CIN:3|CIN3-TB2|3-2|game:5|wr:2|rb+dst`, `--lock`, `--exclude`, `*.report.txt` badges + exposure.

## New peers this sweep

| Repo | License | Steal |
|------|---------|-------|
| jason-r-becker/dfspy | MIT (`License.txt`) | Stale PuLP. Duplicate of pydfs. Pass. |
| mckenjam/Fanduel-Optimizer | MIT | Stale PuLP + scrape helper. Do not copy fetch. Process only. |
| ashhhlynn/custom-fantasy-optimizer | MIT | Lock/exclude (done). Still steal: no offense vs DST, one RB per team. |
| n-roth12/DFSLineupOptimizer | MIT | Game-stack CLI (done). |
| cbratkovics/fantasy-football-ai | MIT | nflverse RF + rolling-origin eval. **Not this weekend.** Wiki only. |
| jnederlo/dfs_optimizers | MIT | Picking Winners / CPLEX. We already have pydfs + sim rerank. Pass this weekend. |
| drmbeledogu/RobustDFS | BSD-3-Clause | Worst-case 50/50 robust MILP (Gurobi). Wiki later. Not GPP. |
| papagorgio23/FantasyFootball | MIT | Stale Yahoo Rglpk. Pass. |
| conorkcorbin/evolve-dfs | MIT | DK genetic search. Stale. Pass. |
| guydotan/nfl-dfs-optimizer | MIT | 2018 DK Shiny. Stale. Pass. |
| derekrbreese/fantasy-football-mcp-public | MIT | Yahoo season-long MCP. Not FanDuel DFS. |
| chanzer0/NFL-DFS-Tools | **None** | Process: `num_players_vs_def: 0`, `projection_minimum`, uniques-N, field sim. Do not clone. |
| BenBrostoff/draftfast | None | Reject (K138). |
| nukesim/nuke-dfs-hub | None | Process only (already noted). |
| Brian-Doucet/nfldfs | (scraper) | Reject scrapers. |

## Integrate next (clean-room on pydfs)

1. `--no-offense-vs-dst` — mutex DST vs opposing skill players.
2. `--one-rb-per-team` — max one RB from a club.
3. `--projection-floor N` — drop low-FPPG noise.
4. `--uniques N` — alias for `max_repeating = slate_size - N` (chanzer0 `opto 1000 3`).

No new pip dependency. No draftfast. Operator submits.
