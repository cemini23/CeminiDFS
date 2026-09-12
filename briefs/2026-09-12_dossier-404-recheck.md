# Dossier 404 recheck — GitHub DFS / optimizer steal board (2026-09-12)

**Source list:** Desktop `DFS Repository Revenue Evaluation.docx` (20 URLs).
**Recheck:** Sat 12 Sep 2026, ~8:20 a.m. ET, GitHub API (authenticated).
**Type:** license-gated research. Do not vendor. Do not scrape. Do not auto-lineup.

## Verdict

The Friday brief called 18 of 20 URLs **404**. That was wrong.

All 18 named owners exist. All 18 named repos are **public today**. Several pushed this morning.

None of those 18 repos has a `LICENSE` file in the repo root. **No clone. No Integrate. Process notes only.**

The earlier 404s were likely unauthenticated curl, a rate-limit, or a brief private window. `nukesim/nuke-dfs-hub` is an NFL DFS hub, not a nuclear-sim false positive.

## The 18 “404” repos (all live)

| Repo | What it is | LICENSE | Steal for Week 1 |
|------|------------|---------|------------------|
| [nukesim/nuke-dfs-hub](https://github.com/nukesim/nuke-dfs-hub) | DK/FD Streamlit hub: stacks, exposure, late-swap, showdown sim, contest import. Live: https://nuke-dfs-app.streamlit.app/ | None | **Process only.** Correlation badges, game-portfolio sort, 3+ team exposure table. We already have late-swap, `--stack qb:2`, `max_exposure`. |
| [nanduniverse/fantasy-lineup-optimizer](https://github.com/nanduniverse/fantasy-lineup-optimizer) | Season-long win-probability lineup (nflverse + ESPN IDs). Week 1 uses 2025–2024 history. Q/D stay eligible with warnings. Workload redistributes on confirmed OUT. | None | Process: warn on Q/D, do not auto-zero. We already use prior-season PBP for Week 1. |
| [dfsstartinglineups/weathernfl](https://github.com/dfsstartinglineups/weathernfl) | Static NFL weather site. CNAME `weathernfl.com`. | None | Human cross-check only. Do not scrape. CeminiDFS already uses Open-Meteo and treats SoFi as indoor. |
| [nickpasternak11/dfs_lineup_optimizer](https://github.com/nickpasternak11/dfs_lineup_optimizer) | DK optimizer + Selenium salary scrape + FantasyPros scrape. | None | **Reject.** Scraper + no LICENSE. |
| [mehpackers13/fanduel-bot](https://github.com/mehpackers13/fanduel-bot) | Sportsbook edge finder. Discord alerts. Action Network + Odds API. Pushed today. | None | **NO-GO.** Not a DFS solver. No auto-enter. No LIVE Discord. |
| [GitAtMike/fantasy-optimizer](https://github.com/GitAtMike/fantasy-optimizer) | ESPN season-long recursive knapsack. | None | Out of scope. |
| [misterplusev/nfl-monitors](https://github.com/misterplusev/nfl-monitors) | TheOddsAPI rotation + Discord charts. | None | Odds watch only. We already take ESPN/DK lines as human notes. |
| [jtmasters3/nfl-news-hub](https://github.com/jtmasters3/nfl-news-hub) | Automated NFL news feed. | None | Human news only. |
| [Kosmo87/football-200-picks](https://github.com/Kosmo87/football-200-picks) | Streamlit +200 moneyline picks. | None | Betting, not DFS. |
| [levine26/nfl-forecast-model](https://github.com/levine26/nfl-forecast-model) | Side-project forecast pipeline. No LICENSE. | None | Wiki-only. Do not import numbers. |
| [GreenMeansGoBetting/nfl-tool](https://github.com/GreenMeansGoBetting/nfl-tool) | JS betting tool. | None | Out of scope. |
| [amercado19/nfl-dashboard](https://github.com/amercado19/nfl-dashboard) | Static Pages dashboard from `nfl-pipeline`. | None | Display only. |
| [ryanapolinar/BattingLineupOptimizer](https://github.com/ryanapolinar/BattingLineupOptimizer) | Baseball batting order. | None | Wrong sport. |
| [Davidebri1/fantasy-grinder-dfs](https://github.com/Davidebri1/fantasy-grinder-dfs) | DK UFC / NBA / PGA. Created yesterday. | None | No NFL. |
| [connerfrock-bit/fantasy-football-ai](https://github.com/connerfrock-bit/fantasy-football-ai) | Season-long draft cockpit + HTML optimizer. | None | BBM-adjacent process only. |
| [atm241/FantasyAnalyzer](https://github.com/atm241/FantasyAnalyzer) | Untested season-long JS site. | None | Pass. |
| [AnT0016/sleeper-ff-tool](https://github.com/AnT0016/sleeper-ff-tool) | Read-only Sleeper draft / waiver / lineup. | None | Season-long. GPL Sleeper forks stay rejected. |
| [savvides/ff](https://github.com/savvides/ff) | Sleeper dynasty CLI. | None | Season-long. |

Already-reachable pair from Friday (unchanged):

| Repo | LICENSE | Note |
|------|---------|------|
| Krool/FantasyFootballAnalyzer | None | Season-long draft room. |
| mrbusche/dfs-optimizer | None | Static CSV LP. CeminiDFS already covers this. |

## Licensed optimizers we can steal ideas from

These have a real MIT `LICENSE` file. Still do **not** scrape. Still operator-submit only.

| Repo | License | Steal |
|------|---------|-------|
| [DimaKudosh/pydfs-lineup-optimizer](https://github.com/DimaKudosh/pydfs-lineup-optimizer) | MIT | **Already in tree.** Keep. Showdown + `--stack qb:2` + `max_exposure`. |
| [n-roth12/DFSLineupOptimizer](https://github.com/n-roth12/DFSLineupOptimizer) | MIT | Game-stack CLI: `KC3-JAX2` or random `3-2`. FD/DK/Yahoo classic + captain/MVP. Offline salary CSV only. **Best licensed idea we do not expose yet.** |
| [ashhhlynn/custom-fantasy-optimizer](https://github.com/ashhhlynn/custom-fantasy-optimizer) | MIT | Lock / exclude. Same-team or opposing QB stack. RB+DST. Exclude players vs our DST. One RB per team. pydfs can do this if we add flags. Uses unofficial DK API — do not copy the fetch path. |
| [aptmac/dfs-helper-nfl](https://github.com/aptmac/dfs-helper-nfl) | MIT | Yahoo / OwnersBox PuLP. Stale. Low value vs pydfs. |

Still reject:

- `BenBrostoff/draftfast` — no LICENSE (K138).
- `jaebradley/draftkings_client` — MIT but unofficial DK API. ROADMAP: no scrapers.
- Any no-LICENSE optimizer, including nuke-dfs-hub.

## What CeminiDFS already has

- `generate_lineups(..., stacks=["qb:2"], max_exposure=0.35)` in `src/ceminidfs/export/optimize.py`
- Late swap: `export/late_swap.py`
- Game-aware correlation matrix: `models/correlation.py`
- Week 1 prior-season PBP / roster fallback (shipped 11 Sep)
- SoFi / retractable roof weather gate
- BBM stack / exposure ledger (season-long, not FanDuel GPP)

## Recommended after Sunday (not mid-slate)

1. **Human-only:** open https://nuke-dfs-app.streamlit.app/ and https://weathernfl.com for process / weather. Do not scrape. Do not copy code.
2. **Optional licensed build:** add stack rules like `BUF3-HOU2` (or random `3-2`) on top of pydfs `TeamStack`, using n-roth12 / ashhhlynn as MIT references. Keep CSV-in / CSV-out.
3. **Do not** vendor nuke-dfs-hub, nickpasternak scrapers, or fanduel-bot.

No new runtime dependency for tomorrow’s Sunday-afternoon FanDuel run.
