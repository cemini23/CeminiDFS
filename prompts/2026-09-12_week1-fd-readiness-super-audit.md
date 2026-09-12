# Week 1 FanDuel DFS readiness — super audit council

You are auditor **{{MODEL_SLOT}}** in a **multi-model super audit**.

**Mode:** `prod-ship` · **Readonly** — markdown report only; no edits; no git writes; no contest submit.

---

## Mission (single sharp question)

Is CeminiDFS **ready tonight** to build FanDuel classic GPP lineups for the 2026-09-13 Sunday-afternoon slate (season 2026 week 1, 1 p.m. + 4:25 only), then late-swap after 1 p.m. lock — without silent bugs in salary ingest, projections (incl. weather/volume), pydfs optimize/stacks, sim-rerank, or late-swap?

Deliver:

1. **Verdict** PASS/WARN/FAIL on current posture
2. **What's working** vs **what isn't**
3. **Ranked patch backlog** — every issue, not only critical. Smallest diffs first. P0 before tonight; P1 can wait until after Sunday if it does not change tonight's CSV
4. Tonight operator GO/NO-GO: what must be true before `ceminidfs run --profile gpp`
5. Concrete file:line evidence for every finding

---

## Context

Tonight (Sat 12 Sep 2026 ET) the operator drops:

- Fresh FanDuel contest player-list CSV → `data/slates/2026-09-13_fd_sun.csv` (gitignored)
- Grok bot research CSV → `research/2026-09-13_grok.csv` (gitignored)

There is **no grok-research CSV ingest** in the repo. Operator + agent will map locks/excludes by hand.

Planned commands:

```bash
ceminidfs fetch --season 2026 --week 1
ceminidfs run --season 2026 --week 1 --salary data/slates/2026-09-13_fd_sun.csv --site fanduel --stages all --profile gpp
# then stacks/locks/excludes on optimize or run
ceminidfs late-swap --lineups runs/2026_week_1/lineups.csv --players runs/2026_week_1/normalized_players.csv --lock-team <1pm clubs>
```

Hard gates: no FanDuel passwords; agent does not Enter/Submit/late-swap on the site; no draftfast; no paid-site scrapes; no commit of salary CSVs.

Week 1 engine already uses prior-season PBP when same-season PBP is empty. SoFi (LAC/LAR) is indoor. Retractable HOU/IND stay weather-exposed until a roof decision.

GPP profile (`config/nfl_dfs_gpp.yaml`): copula sim 5000, sim_rerank 2000→150 p85, ownership on, buzz_signal on.

Recent optimizer flags (2026-09-12): `--stack qb:3|CIN3-TB2|3-2`, `--lock`, `--exclude`, `--no-offense-vs-dst`, `--one-rb-per-team`, `--projection-floor`, `--uniques`. Report: `*.report.txt`.

Friday research: Tua OUT; Bowers OUT; Chase no designation; Kamara Q; Odunze Q; Jacobs exempt/IR. Confirm inactives ~90 min before 1 p.m. BUF@HOU line flipped vs July dossier — do not treat HOU −1.5 as live.

---

## Regime boundaries

- Audit **FanDuel classic DFS only**. Skip BBM, ESPN redraft, pick'em, Hard Rock, Discord.
- Do not invent a grok-CSV schema. Flag missing ingest as info/warn, not as a reason to block if manual locks work.
- Do not recommend scraping FanDuel / Stokastic / FantasyLabs.
- Do not treat "make repo private" as a license.
- Strategy findings must name a file/function that implements or fails the idea.
- If evidence is missing, say NO_EVIDENCE and the next file to read.

---

## Data pack files (READ these paths)

```
{pack_index}
```

Also Read/Grep the live repo under `/Users/claudiobarone/Projects/CeminiDFS` for DFS paths listed in PACK_INDEX. Prefer pack snapshots when a file is large.

---

## Prior audit consensus (validate — do not repeat blindly)

- Week 1 PBP fallback and SoFi indoor shipped (commit `9dbe2bd` / later).
- GPP stacks/locks/peer flags shipped (`4782009`); local pytest 362 passed; CI green on 3.11/3.12.
- `qb:2` was a bug (asked for two QBs); current docs say `qb:3`.
- draftfast remains rejected (no LICENSE).
- Grok research CSV is not wired.

---

## Required output format

### Verdict
PASS | WARN | FAIL — one line why

### Findings
| Severity | Finding | Evidence | Fix |
|----------|---------|----------|-----|
| critical/warn/info | ... | file:line or quote | ... |

### Tonight GO/NO-GO
| Gate | Status | Blocker if no |
|------|--------|---------------|
| Fresh FD salary CSV ingest | | |
| Week 1 project without same-season PBP | | |
| Weather/volume/pass-rate | | |
| Optimize + stacks + report | | |
| Late-swap after 1 p.m. lock | | |
| Operator submit only | | |

### Root cause
One paragraph on the likely readiness gap — or "insufficient evidence" + what to inspect next.

### Ranked patch backlog
| P | Patch | Effort | Expected lift |
|---|-------|--------|---------------|

### Unique angle
One thing other auditors might miss

### Confidence
high | medium | low

---

## Constraints

- Readonly. Do not edit files. Do not run destructive git.
- You may run **non-destructive** pytest / ruff / python -c imports.
- Time budget: thorough on DFS path; skip BBM/redraft.
- No secrets in the report. No contest IDs that look like credentials.

---

## Already ruled out

- "Just use draftfast" — rejected K138.
- "Scrape FanDuel player list" — operator exports CSV.
- Pick'em / Hard Rock parlays — out of tonight's scope.
- Federation skill dumps under `.cursor/skills/` — ignore.
