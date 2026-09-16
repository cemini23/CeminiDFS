# CeminiDFS improve brief — Gemini architecture extract (2026-09-15)

**Next action:** Review this brief. Do not ship flags. Do not retune the optimizer. Do not Enter.

**Mode:** markdown only. `do_not_auto_apply: true` on every build row.  
**Retrieved:** 2026-09-15.  
**Lane:** hard (Grok types the brief; no Python).

## Sources

| Kind | Path |
|------|------|
| Parent Plan | gambling-wiki `briefs/handoffs/2026-09-15_gemini-tool-improve-plan.md` |
| Source docx | `NFL DFS Optimization Architecture Research.docx` (archive: `cemini-egress-fi:/opt/cemini-bulk/research/gambling/NFL DFS Optimization Architecture Research.docx`) |
| Extract | gambling-wiki `briefs/deep-research/extracts/NFL-DFS-Optimization-Architecture-Research.md` |
| sha | not hashed this wave (extract only) |
| Week 1 gaps | `briefs/2026-09-14_week1-fd-recap/tool-gaps.md` |
| Stadiums | `src/ceminidfs/data/stadiums.py` (SoFi LAC/LAR = `semi_open`) |

Sibling briefs (names only; not this WorkDir): gambling-wiki hub `briefs/2026-09-15_gemini-tool-improve-hub.md` · CeminiParlays `briefs/2026-09-15_gemini-parlays-improve.md`.

## Wiki consult (do not contradict)

- gambling-wiki `wiki/concepts/dfs-foss-tooling-landscape.md` — nflreadpy MIT GO; nfl_data_py deprecated NO-GO; pydfs MIT GO; draftfast / chanzer0 NO-GO.
- gambling-wiki `wiki/entities/tools/ceminidfs.md` — pick'em is not in this repo; projections may be borrowed.
- gambling-wiki `briefs/2026-w02-slate-hub-sun.md` — `slate_id` shape `2026-w02-sun`; SoFi is not wind-exposed.
- osint-wiki `concepts/cemini-license-posture.md` — GPL/AGPL extract-only; never vendor; MIT/BSD/Apache OK.
- CeminiDFS `src/ceminidfs/data/stadiums.py` — SoFi is `semi_open`, not dome; `is_weather_exposed` is false.
- CeminiDFS `src/ceminidfs/data/weather.py` — already zeros SoFi wind and gusts.
- Week 1 `tool-gaps.md` TG01–TG07 — reports, not silent reweights. n=1 is not a retune.

## Corrections vs Gemini

1. **SoFi is not a dome.** Keep `roof=semi_open` and `weather_exposed=false`. Zero wind/precip values is OK. Do not write `roof=dome`.
2. **Roof enum** stays `open|dome|retractable|semi_open`. Do not adopt Gemini `outdoors/open/closed`.
3. **`slate_id`** stays `2026-wNN-sun` (or thu/snf/mnf). Do not adopt `2024_W08_MAIN`.
4. **`game_id`** stays `AWAY@HOME` unless both tools later agree on nflverse `YYYY_WW_AWAY_HOME`.
5. Gemini steal-table dates `2025-05-18` are stale. Cite **2026-09-15**.
6. n=1 Week 1 is not enough to retune CIN / Chase / weather numbers. No projection haircuts. No new weather coefficients.
7. Gemini `--dst-audit`, `--weather-audit`, and `--stadium-audit` are extra. Do not recommend them this wave.
8. PlayersGroup max-from-group is **opt-in**. Do not default-on a Chase/Higgins cap.
9. Do not treat SoFi as an exposed outdoor field. Do not apply indoor pass-game boosts from one LAC sample.

## KEEP / REJECT / EXTRACT

| Action | Item | License / note | Role |
|--------|------|----------------|------|
| KEEP | nflreadpy | MIT | schedule, roster, injuries |
| KEEP | pydfs-lineup-optimizer | MIT | ILP solver; TeamStack; GameStack; PlayersGroup (opt-in); `optimize_lineups` late-swap |
| KEEP | Open-Meteo | public forecast API | weather fetch; SoFi wind already nulled |
| KEEP | existing GPP flags | in-repo | `--stack`, `--uniques`, `--projection-floor`, `--one-rb-per-team`, `--no-offense-vs-dst`, `--max-exposure`, `CHALK-QB-WR-WR` badge |
| KEEP | copula sim rerank | in-repo | ceiling re-rank after solve |
| KEEP | paid ownership CSV ingest | operator file | `ownership_labels.py` / GPP `ownership.enabled` |
| KEEP | scikit-learn IsotonicRegression | BSD-3-Clause | optional scale align **inside** `--ownership-fade-report` only; never auto-write FPPG |
| REJECT | **draftfast** (BenBrostoff) | NO LICENSE | do not vendor, clone, or wrap |
| REJECT | chanzer0/NFL-DFS-Tools | no license | process notes only |
| REJECT | jmoore87jr/DFS_ownership_projections | NO LICENSE + scrape | do not scrape FanDuel / DK / Underdog / FantasyLabs |
| REJECT | scrapers, clipboard-submit, live browser Enter | — | operator submits; agent does not Enter |
| REJECT | nfl_data_py | deprecated | use nflreadpy |
| REJECT | FantasyFootballAnalytics/ffanalytics | GPL-3.0 | extract-only, never vendor |
| REJECT | OddsJam / Unabated / PickLabs as runtime | proprietary | research desks only |
| REJECT | Polars/DuckDB rewrite | — | out of scope |
| REJECT | silent projection penalties | — | distorts ILP shadow prices |
| EXTRACT | arXiv:1604.01455 (Hunter / Vielma / Zaman) | academic | portfolio correlation bounds; ideas only |
| EXTRACT | arXiv:2309.15253 (Martin / Tsoukalas) | academic | field-ownership framing for the fade report |
| EXTRACT | Rochford stadium scoring notes | educational | venue tagging ideas only; SoFi stays `semi_open` |

## TG01–TG07 map

Week 1 evidence is in `briefs/2026-09-14_week1-fd-recap/tool-gaps.md`. Map each gap to **already have** / **missing report** / **do not build**. Recommend three flags only.

| id | surface | already have | missing report / flag | do not build | `do_not_auto_apply` |
|----|---------|--------------|------------------------|--------------|---------------------|
| TG01 | stack_rules | `--stack qb:3\|CIN:3\|CIN3-TB2\|3-2\|wr:2`; TeamStack / GameStack; PlayersGroup used for `--no-offense-vs-dst` and `--one-rb-per-team`; report badge `CHALK-QB-WR-WR` | **`--flag-wr-triples`** → `stack_fragility_report.csv` (same-game WR triples + ownership concentration) | Silent FPPG haircut on chalk WR stacks. Default-on PlayersGroup `max_from_group=1`. Force-fade Burrow+Chase+Higgins from n=1. | true |
| TG02 | injury | Q stays in pool (`keep_injury_tagged_players`); Q names in `lineups.report.txt`; `ceminidfs late-swap` via `optimize_lineups` freeze | **`--late-swap-audit`** → `late_swap_alert_report.csv` (Q/D in afternoon/evening windows vs current lineups) | Headless auto-swap. Auto-drop Q. Zero a player without operator confirm. FanDuel Enter. | true |
| TG03 | projection | GPP copula sim rerank; `--projection-floor`; heuristic ownership | none (do not retune FPPG). Related diagnostic is TG04 `--ownership-fade-report` | Recalibrate CIN / Chase / Higgins from Week 1. Isotonic rewrite of projections. New ceiling coefficients from n=1. | true |
| TG04 | ownership | GPP `ownership.enabled`; paid CSV ingest; optional sim `ownership_penalty`; `--max-exposure` | **`--ownership-fade-report`** → `leverage_fade_matrix.csv` (sim exposure vs projected own%; flag negative-leverage chalk) | Ownership scrapers. Fabricated own%. Auto `--max-projected-ownership` from one Sunday. | true |
| TG05 | defense_multiplier | `--no-offense-vs-dst` | none this wave (Gemini `--dst-audit` deferred) | `--dst-audit`. Silent D/ST multiplier retune from Titans/Jets n=1. Scrape DEF tiers. | true |
| TG06 | weather | Open-Meteo; `weather.py` nulls SoFi wind/gusts; `is_weather_exposed` false for dome and `semi_open` | none this wave (Gemini `--weather-audit` deferred) | New weather coefficients from n=1. Linear FP penalties for outdoor games. Auto-punish CIN for Week 1 weather. | true |
| TG07 | stadiums | `RoofType = open\|dome\|retractable\|semi_open`; SoFi LAC/LAR = **`semi_open`**; `is_weather_exposed` false | none this wave (Gemini `--stadium-audit` deferred) | Call SoFi a dome. Indoor projection boost. Gemini roof enum `outdoors/open/closed`. Standalone LAC stack boost from one middling sample. | true |

## Recommend (three flags only)

Names only. Human gate. No CLI shipped from this brief.

| Flag | Artifact | Human gate | `do_not_auto_apply` |
|------|----------|------------|---------------------|
| `--flag-wr-triples` | `stack_fragility_report.csv` | Operator reviews same-game WR triples. May then re-run with **opt-in** PlayersGroup `max_from_group=1`. | true |
| `--late-swap-audit` | `late_swap_alert_report.csv` | Run ~30 min before Main lock. Operator confirms swap or exclude. Then existing `late-swap`. | true |
| `--ownership-fade-report` | `leverage_fade_matrix.csv` | Operator may then pass `--max-exposure` / `--exclude` on a later solve. No silent fade. | true |

PlayersGroup is opt-in after the WR-triples report. It is not a default constraint.

## Do not build (this wave)

1. `--dst-audit` / `dst_pairing_matrix.csv`
2. `--weather-audit` / `environmental_impact_report.csv`
3. `--stadium-audit` / `stadium_structural_tags.csv`
4. Projection haircuts, including isotonic auto-apply onto FPPG
5. New weather or stadium scoring coefficients
6. draftfast, scrapers, clipboard-submit, FanDuel Enter
7. `ceminidfs export-env` (hub / Parlays contract; not a DFS optimizer change)

## Boundary

- Core ILP (pydfs) stays unmodified. Reports sit after solve or before lock.
- Projections stay individual scoring distributions. Stack risk is a constraint or a filter, not a hidden point cut.
- Week 1 (Burrow+Chase+Higgins miss; Allen bring-back + contrarian WR cash; Odunze→McConkey late-swap) is a hypothesis, not a coefficient.
- Agent does not Enter. Operator exports CSV and submits.

## Verify (this file)

```
test -f briefs/2026-09-15_gemini-dfs-improve.md
rg -n "TG01|do_not_auto_apply|semi_open|draftfast" briefs/2026-09-15_gemini-dfs-improve.md
```
