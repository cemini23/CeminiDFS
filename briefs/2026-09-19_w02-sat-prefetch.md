# Week 2 Sat prefetch → CeminiDFS

**Slate:** Sun 20 Sep 2026, 1 p.m. + 4 p.m. ET (4:05 / 4:25). SNF/MNF/TNF out.  
**Pass:** early (~28h). Prefetch landed Sat 19 Sep ~08:25 ET.  
**Hub:** `../Gambling wiki/briefs/2026-w02-slate-hub-sun.md`  
**Prefetch:** `../Gambling wiki/briefs/slate-prefetch/2026-w02-sun-early.md`  
**Type:** Saturday env + injury gate. Not lineups. Not salaries.

Agent does not Enter.

## Do this now

1. Export a **new** FanDuel Sunday-afternoon player-list CSV (13 games). Do not reuse Week 1.
2. Wipe stale cache: `artifacts/cache/2026/week_2/` (and schedules parquet if lines look wrong).
3. `ceminidfs fetch --season 2026 --week 2`
4. `--exclude` scratch list below (unchanged from Fri except confirm Sunday inactives).
5. Stacks unchanged: WAS@DAL **keep** · CIN@HOU **fade** · Jefferson **solo** · fade ATL pass · MIA@SF game stacks · PIT@NE.
6. Weather: **MIN@CHI** pass downgrade (14 mph G23, 47% pop). **GB@NYJ** rain screen. SoFi **not** a wind fade.
7. Run Grok **DFS Slate Desk** after salaries land. Operator submits.

Sunday T-90 (~11:30 ET 1 p.m. games): Pittman, Tua, McConkey, Porter Jr.

## Scratch (`--exclude`)

Brown IR · Tyler Smith IR · Pacheco IR · Estime IR · Higgins IR · Penix OUT · Jordan OUT · Lane IR · Hand OUT · **Darnold OUT** · **Collins OUT** · **Murray OUT** · **Fitzpatrick OUT** · **Omar Cooper Jr. OUT** · **Bowers D** · **Flowers D**

## Warn (pool OK until OUT)

Tua Q (Rush starts) · Pittman Q · McConkey Q · Porter Jr. Q

## Vegas / ITT

Use hub Fri Sports Interaction table until post-fetch vegas matches. Key keep game: **WAS@DAL 50.5, DAL −4**.

## Weather (Sat Open-Meteo vs Fri)

| Game | Sat flag | DFS action |
|------|----------|------------|
| MIN @ CHI | 14 mph G23, 47% pop | Lean under; no MIN stack (Wentz anyway) |
| GB @ NYJ | G21, 53% pop | Screen QBs / bring-back caution |
| LV @ LAC | semi_open | No wind haircut |
| PHI @ TEN | 96°F | Heat note — no auto-fade |
| Retractable | HOU ATL ARI DAL uncalled | Keep `weather_exposed=true` until roof call |

Source: gambling-wiki Sat prefetch. No salaries invented.
