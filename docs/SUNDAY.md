# Sunday GPP in 20 minutes

This is the operator path for one FanDuel Sunday GPP slate. You export the salary
CSV. You run Python. The agent builds the lineups and the reports. You submit every
lineup. The agent does not Enter.

**Detail:** [`GPP-WORKFLOW.md`](GPP-WORKFLOW.md) and
[`REVIEW-REPORTS.md`](REVIEW-REPORTS.md).

> **Sunday GPP rules**
>
> 1. Use this week's FanDuel player-list CSV. Do not reuse last week's contest IDs.
> 2. Run the 25-lineup probe before the full GPP build.
> 3. The three review flags default off. Read each report before you solve again.
> 4. Questionable (`Q`) players stay in the pool. Do not drop them.
> 5. Do not retune FPPG, CIN, Chase, or weather from one Sunday.
> 6. The agent does not Enter, Submit, or late-swap.

**Rule for every step:** if a command fails, read the named rows and fix the CSV.
Do not guess on a money slate.

## Week 2 Sat card (Sun 20 Sep 2026)

**Slate:** 1 p.m. + 4 p.m. ET. Export a **new** FanDuel Sunday-afternoon CSV. Do not reuse Week 1.

**Scratch:** `--research-csv config/2026-w02-sun-scratch.csv` on the probe and the full GPP. The file is OUT / IR / D only. Questionable (`Q`) players stay in the pool. Do not exclude Tua, Pittman, McConkey, or Porter Jr.

**Stacks (hints only — do not pass `--stack` by default):** WAS@DAL keep. CIN@HOU fade. Jefferson solo / no MIN stack. Fade ATL pass. Fade MIA@SF game stacks. Fade PIT@NE. Do not lock WAS@DAL stacks in Python.

**Weather:** MIN@CHI pass downgrade. GB@NYJ rain screen. SoFi is `semi_open` — not a wind fade. Retractable roofs stay exposed until the 90-min call.

**T-90 (~11:30 ET for 1 p.m. games):** Pittman, Tua, McConkey, Porter Jr.

- **Slate guard:** the FanDuel salary CSV must be the **Sunday-afternoon** slate only. A full-week export also holds SNF IND@KC. Do not import that game.
- **ATL QB check:** after `fetch`, the nflverse vegas file may still name Tua as the ATL QB. The hub says **Cooper Rush** starts. Keep the fade on the ATL pass game. Do not retune FPPG.
- **Optional Jev HITL:** after the review CSVs exist, call `jev_verify` on one injury cell. Call `jev_find` on the late-swap rows (`late_swap_alert_report.csv`). Jev does not change projections. No scrape. No Enter.

**Late-swap 1 p.m. ET lock teams (nflverse):** `--lock-team CAR --lock-team ATL --lock-team NO --lock-team BAL --lock-team MIN --lock-team CHI --lock-team CIN --lock-team HOU --lock-team PIT --lock-team NE --lock-team GB --lock-team NYJ --lock-team CLE --lock-team TB --lock-team PHI --lock-team TEN`.

Operator exports the CSV. The agent does not Enter.

```bash
# after operator exports THIS week's FanDuel Sunday-afternoon CSV
# data/slates/2026-09-20_fd_sun.csv holds Sunday-afternoon games only (no SNF IND@KC)
rm -rf artifacts/cache/2026/week_2
ceminidfs fetch --season 2026 --week 2 --force

ceminidfs run --season 2026 --week 2 \
  --salary data/slates/2026-09-20_fd_sun.csv \
  --stages fetch,project,normalize --profile gpp

ceminidfs optimize --csv runs/2026_week_2/normalized_players.csv \
  --out runs/2026_week_2/probe.csv --count 25 --min-salary 58500 \
  --research-csv config/2026-w02-sun-scratch.csv

ceminidfs run --season 2026 --week 2 \
  --salary data/slates/2026-09-20_fd_sun.csv \
  --stages all --profile gpp --min-salary 58500 \
  --research-csv config/2026-w02-sun-scratch.csv \
  --flag-wr-triples --late-swap-audit --ownership-fade-report
```

## 0. Install (once)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,data,optimize]"
```

## 1. Export this week's FanDuel player-list CSV (2 min)

Open FanDuel, download the player list for the current week, and save the file.
The file has salaries and player IDs. Do not use last week's contest export.

Name the file so the week is clear, for example `data/slates/2026-09-20_fd_sun.csv`.

## 2. Fetch nflverse data (2 min)

```bash
rm -rf artifacts/cache/2026/week_2
ceminidfs fetch --season 2026 --week 2 --force
```

This writes the week cache under `artifacts/` (schedules, play-by-play, injuries,
Vegas, weather) plus a fetch manifest.

## 3. Build the GPP lineups (10 min)

Probe first. One lineup takes about 1 second. 2,000 candidates can take 35
minutes. Stacks such as `qb:3` plus `3-2` can take hours.

```bash
# Write the normalized player CSV first (probe needs this file)
ceminidfs run --season 2026 --week 2 \
  --salary data/slates/2026-09-20_fd_sun.csv \
  --stages fetch,project,normalize --profile gpp

# Probe: 25 lineups
ceminidfs optimize --csv runs/2026_week_2/normalized_players.csv \
  --out runs/2026_week_2/probe.csv --count 25 --min-salary 58500 \
  --research-csv config/2026-w02-sun-scratch.csv

# Full GPP build
ceminidfs run --season 2026 --week 2 \
  --salary data/slates/2026-09-20_fd_sun.csv \
  --stages all --profile gpp --min-salary 58500 \
  --research-csv config/2026-w02-sun-scratch.csv
```

The `gpp` profile enables the copula simulation, the simulation rerank, and
heuristic ownership. Pass `--candidates 2000` only if you have extra time.

## 4. Review the human gate (3 min)

Run the GPP build with the three review flags, or read an existing lineup file
with `ceminidfs review`. The flags default off. `review` does not re-solve.

```bash
ceminidfs run --season 2026 --week 2 \
  --salary data/slates/2026-09-20_fd_sun.csv \
  --stages all --profile gpp \
  --research-csv config/2026-w02-sun-scratch.csv \
  --flag-wr-triples --late-swap-audit --ownership-fade-report

ceminidfs review --lineups runs/2026_week_2/lineups.csv \
  --players runs/2026_week_2/normalized_players.csv \
  --flag-wr-triples --late-swap-audit --ownership-fade-report
```

| Flag | Report CSV | Operator next step |
|------|------------|--------------------|
| `--flag-wr-triples` | `stack_fragility_report.csv` | Read the same-game WR triples. May then `--exclude`. |
| `--late-swap-audit` | `late_swap_alert_report.csv` | Read the `Q` and `D` alerts. Confirm, then use `late-swap`. |
| `--ownership-fade-report` | `leverage_fade_matrix.csv` | Read the leverage. May then `--max-exposure` or `--exclude`. |

Read the CSVs. Then you may `--exclude`, `--max-exposure`, or `late-swap`. Do not
auto-apply a report. Do not auto-drop a `Q` player.

## 5. Upload the ID file, then submit (3 min)

`optimize` and `late-swap` write three files next to `--out`:

1. `lineups.csv` — name-only, for review. Do **not** paste this into FanDuel.
2. `lineups_fanduel_upload.csv` — `Full Name (id)` cells.
3. `lineups_fanduel_ids.csv` — ID-only cells.

Upload `lineups_fanduel_upload.csv`, or paste `lineups_fanduel_ids.csv`.

**You** press Submit in FanDuel. The agent does not Enter.

## 6. Optional late swap after the 1 p.m. ET lock

Lock each 1 p.m. ET club once. Use nflverse abbreviations, not FanDuel aliases:
`JAX` (not `JAC`), `WAS` (not `WSH`), `LAR` (not `LA`).

```bash
ceminidfs late-swap \
  --lineups runs/2026_week_2/lineups.csv \
  --players runs/2026_week_2/normalized_players.csv \
  --lock-team CAR --lock-team ATL --lock-team NO --lock-team BAL \
  --lock-team MIN --lock-team CHI --lock-team CIN --lock-team HOU \
  --lock-team PIT --lock-team NE --lock-team GB --lock-team NYJ \
  --lock-team CLE --lock-team TB --lock-team PHI --lock-team TEN \
  --out runs/2026_week_2/lineups_late_swap.csv
```

A failed swap keeps the original row. Keep every original lineup name in the
players file.

## 7. After the slate: Recap Desk paste

Paste the scored lineups and the tool gaps into the DFS Recap Desk. The protocol
is in [`GROK-BOTS.md`](GROK-BOTS.md). The Recap Desk is live in Grok Bot.app; it
still does not write this repo. Still no Enter.

## Keep and refuse

- Questionable (`Q`) players stay in the optimizer pool. OUT / IR / D drop in normalize.
- Do not retune FPPG, CIN, Chase, or weather from one Sunday. One sample is not a retune.
- SoFi stays `semi_open`. SoFi is not a dome.
- KEEP / REJECT and TG01–TG07: [`../briefs/2026-09-15_gemini-dfs-improve.md`](../briefs/2026-09-15_gemini-dfs-improve.md).

Operator exports the CSV and submits. Agent does not Enter.
