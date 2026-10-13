# Week 1 Sunday-afternoon prefetch → CeminiDFS

**Slate:** Sun 13 Sep 2026, 1 p.m. + 4:25 only. SNF/MNF out.
**Pass:** early (~21h to first kick). Prefetch landed Sat 12 Sep 16:05 ET.
**Hub:** `../Gambling wiki/briefs/2026-w01-slate-hub-sun.md`
**Type:** game environment + injury for `ceminidfs run`. Not lineups. Not salaries.

Verify the FanDuel player list and official inactives before you submit. Agent does not Enter.

## Do this now

1. Delete sticky cache (or use `--force` if it exists):
   - `artifacts/cache/schedules_2026.parquet`
   - `artifacts/cache/2026/week_1/`
2. Drop a **new** FanDuel Sunday-afternoon player-list CSV (12 games). Do not reuse contest `133104`.
3. `ceminidfs fetch --season 2026 --week 1` (after the wipe).
4. Confirm Kamara and Odunze on the inactive list (~90 min before 1 p.m.).
5. `ceminidfs run --season 2026 --week 1 --salary <new.csv> --site fanduel --stages all --profile gpp`
6. Suggested stacks after you see salaries: `--stack qb:3` **or** `--stack CIN3-TB2`. Do not combine `qb:3` + `CIN3-TB2` + `3-2` on one build.
7. `--exclude` Tua, Bowers, Pacheco, Estime. Add Kamara / Odunze / McMillan if they are OUT. Operator submits.

Late-swap stays **NO-GO** until the Saturday readiness P0 patches (`briefs/2026-09-12_week1-fd-readiness-super-audit.md`). If you need a 4:25 swap, rebuild with a regenerated pool that **keeps** OUT rows (zero FPPG) or wait for the patch.

## Vegas / ITT (from 16:05 prefetch)

Prefetch `spread` is nflverse `spread_line` (**+ = home favored**). Your `vegas.py` already negates that column. Numbers below are **betting convention** so you can spot-check `home_implied_total` / `away_implied_total` after fetch.

| Kick | Away | Home | Home spread (bet) | Total | Away ITT | Home ITT |
|------|------|------|-------------------|-------|----------|----------|
| 13:00 | CHI | CAR | CAR +3 | 47.5 | 25.25 | 22.25 |
| 13:00 | TB | CIN | CIN −3.5 | **50.5** | 23.50 | **27.00** |
| 13:00 | NO | DET | DET −7 | **49.5** | 21.25 | **28.25** |
| 13:00 | BUF | HOU | HOU +1.5 | 44.5 | 23.00 | 21.50 |
| 13:00 | BAL | IND | IND +3.5 | 47.5 | **25.50** | 22.00 |
| 13:00 | CLE | JAX | JAX −8.5 | 39.5 | 15.50 | 24.00 |
| 13:00 | ATL | PIT | PIT −6 | 41.5 | 17.75 | 23.75 |
| 13:00 | NYJ | TEN | TEN −1.5 | 38.5 | 18.50 | 20.00 |
| 16:25 | ARI | LAC | LAC −9.5 | 47.5 | 19.00 | **28.50** |
| 16:25 | MIA | LV | LV −3 | 40.5 | 18.75 | 21.75 |
| 16:25 | GB | MIN | MIN −2.5 | 46.5 | 22.00 | 24.50 |
| 16:25 | WAS | PHI | PHI −6 | 44.5 | 19.25 | 25.25 |

Delta vs Friday ESPN/DK (`briefs/2026-09-11_week1-friday-matchup-research.md`): PIT −5.5 → −6; MIN −1.5 → −2.5. BUF stays −1.5 (do not reuse HOU −1.5).

If post-fetch vegas still shows HOU −1.5, the cache wipe failed. Stop and delete again.

## Weather (prefetch vs this repo)

| Flag | Prefetch stub | CeminiDFS rule | Action |
|------|---------------|----------------|--------|
| ARI @ LAC | outdoor 9 mph | SoFi `semi_open` — skip Open-Meteo | Do **not** haircut LAC/ARI pass yards for wind |
| BUF @ HOU | dome | Retractable until roof call | Keep weather-exposed until NFL 90-min roof |
| BAL @ IND | dome | Same retractable rule | Same |
| Other outdoor | 3–7 mph | <10 mph = no pass-rate band | No weather fade this pass |

## Injury → `--exclude` / Q stay in pool

`Q` stays in the optimizer pool. `D` / `OUT` / `IR` / `EXEMPT` drop. Confirm inactives before you lock.

| Player | Token | DFS note |
|--------|-------|----------|
| Tua Tagovailoa | OUT | Rush starts. Fade ATL WR/TE stacks. |
| Brock Bowers | OUT | LV TE vacated. Jeanty plays. |
| Audric Estime | OUT | Kamara/Etienne only. |
| Isiah Pacheco | OUT | Yahoo Sat: DET, back. Scratch. |
| Alvin Kamara | Q | Yahoo: expected to play, timeshare with Etienne. Etienne-lead thesis is **conditional**. |
| Rome Odunze | Q | CHI @ CAR. `--exclude` only after inactive. |
| Jalen McMillan | D | TB WR bump if OUT. |
| Jeremiyah Love | Q | Yahoo: expected to play. |
| Josh Jacobs | Exempt / FD IR | Lloyd still the GB lead note. Ownership risk. |
| Malik Nabers | Q | SNF — not on this CSV. |

Chase / Higgins: no Friday game designation. Do not auto-exclude.

## Stack / fade screen (sanity, not cores)

Use after salaries exist. Do not import ITT as FPPG.

**Priority environments**

1. TB @ CIN 50.5 — `CIN3-TB2` / both QBs.
2. NO @ DET 49.5 — DET ITT 28.25. Kamara gate.
3. CHI @ CAR 47.5 — Odunze gate.
4. BAL @ IND 47.5 — BAL ITT 25.50.
5. ARI @ LAC 47.5 — LAC ITT 28.50 + −9.5 script (RB / DST), not ARI pass volume.

**Fades:** ATL pass (Rush); NYJ @ TEN 38.5; CLE @ JAX 39.5 unless you want JAX RB + DST; MIA @ LV 40.5 without Bowers.

Team alias: lock **`JAX`**, not `JAC`.

## What this brief does not give you

- FanDuel salaries or ownership.
- A lineup CSV.
- Permission to late-swap the current engine.
- Pick'em / Hard Rock lines (those went to CeminiParlays).

Source: `../Gambling wiki/briefs/slate-prefetch/2026-w01-sun-early.md` + Saturday Yahoo injury tracker.
