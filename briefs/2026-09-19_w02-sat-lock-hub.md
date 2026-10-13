# Week 2 Sat lock → CeminiDFS

**Slate:** Sun 20 Sep 2026, 1 p.m. + 4 p.m. ET. SNF/MNF/TNF out.  
**Hub:** `../Gambling wiki/briefs/2026-w02-slate-hub-sun.md`  
**Scratch file:** `config/2026-w02-sun-scratch.csv` (Pittman + Porter added)  
**Salary:** your new FanDuel Sunday-afternoon CSV only. Do not reuse Week 1.  
**Type:** Saturday lock deltas. Not Enter.

Agent does not Enter.

## Do this now

1. Put this week’s FanDuel Sunday-afternoon CSV at `data/slates/2026-09-20_fd_sun.csv` (no IND@KC).
2. Open this folder in Cursor. Follow `docs/SUNDAY.md` Week 2 Sat card.
3. `--research-csv config/2026-w02-sun-scratch.csv` on probe and full GPP.
4. Stacks stay **hints**: WAS@DAL keep · CIN@HOU fade · Jefferson solo · fade ATL pass · fade MIA@SF · fade PIT@NE. Do not pass `--stack` unless you choose it.
5. Weather: CHI 12–14 mph pass down · NY rain · NE rain · TEN heat · SoFi not a wind fade.
6. Q still in pool: Tua, McConkey. Sunday T-90 only.

```bash
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

Upload `lineups_fanduel_upload.csv`. You type Enter.

## Scratch (in the CSV)

Fri list **plus** Michael Pittman Jr. OUT · Joey Porter Jr. OUT.

Hold: Tee Higgins “IR” — do not add. That is likely Jayden Higgins.

Source: gambling-wiki Sat Gemini lock. No salaries invented.
