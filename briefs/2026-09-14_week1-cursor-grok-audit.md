# Cursor Grok audit — FanDuel Week 1 Main (2026-09-13)

**Auditor:** parent Cursor Grok (this session)  
**Mode:** `brief-plan`  
**Packet:** `briefs/2026-09-14_week1-fd-recap/` (Desktop zip on disk was `2026-09-14-week1-recapdfs.zip`; operator called it GradeDFS)  
**Official actuals:** FanDuel History lineup **totals** only. Per-player FPPG = `NO_EVIDENCE`. Do not back-solve.

## Verdict

**REWORK** for Week 2 process. The 10-lineup GPP thesis had one real spike, but upload, stack fades, Q-WR swap, and team-exposure gaps are not ship-ready.

## Scorecard (CeminiDFS CSV1–10 only)

Locator: `briefs/2026-09-14_week1-fd-recap/lineup_totals.csv` + `recap.md` + `runs/2026_week_1/lineups.csv`.

| Metric | Value |
|--------|-------|
| Entries | 10 × $5 |
| Fees | **$50.00** |
| Won | **$16.50** (L01 $9.00 + L02 $7.50) |
| Net | **−$33.50** |
| Cash rate | **2/10** |
| Best | CSV3 → L01 **169.96** |
| Worst | CSV5 → L14 **91.36** |
| Close miss | CSV1 → L04 143.36 ($0) |

Do **not** count History L03/L08/L11/L12 in this scorecard. Those four rows are not in the optimizer export.

## Went right

1. The top cash (CSV3/L01) matches the GPP plan: Josh Allen + BUF bring-backs + contrarian WRs (Burden III, Hutchinson) + Jaguars D. Locator: recap L01; `lineups.report.txt` lineup 3.
2. Player `--max-exposure 0.3` held: Chase, Allen, Burrow, Odunze each at 30% in the report, not 100% chalk.
3. Odunze stayed in the pool (`with_injured=True`). The operator could swap. L02 cashed after Odunze → McConkey.
4. Name+ID cells already existed as a **manual** file (`runs/2026_week_1/lineups_fanduel_upload.csv`). Operator got entries in. Agent did not Enter.
5. Build flags `--stack qb:3 --one-rb-per-team --no-offense-vs-dst --uniques 2` produced distinct cores (BUF, CIN, IND, ARI). The field was not 10 copies of one lineup.

## Went wrong

1. **Process / P0.** `write_lineup_rows` writes names only (`optimize.py` `_lineup_row` uses `player.full_name`). FanDuel rejected that CSV. The ID file was a side product, not the default `ceminidfs run` output.
2. **Model / stack.** CSV4 and CSV5 (Burrow + Chase + Higgins) were the two worst History totals (96.46 / 91.36). History L03 cashed **without** Chase/Higgins. `qb:3` does not fade chalk QB + both WRs.
3. **Process / exposure.** Player cap 30% still allowed **CHI 70%** team exposure (Burden, Loveland, Monangai). Report: `lineups.report.txt` team exposure. There is no team-exposure cap in optimize.
4. **Injury / swap.** CSV6 and CSV7 still had Rome Odunze (Q, calf) at lock-file time. L02 also drifted FLEX Swift vs CSV Monangai. Late-swap exists (`late_swap.py`) but there is no Q-WR suggestion list for the operator.
5. **DEF pairing.** Titans D sat on both worst CIN stacks. Jets D sat on several mid/low misses. Jaguars D sat on the top cash. DST module did not stop pairing a weak D with a fragile pass stack.
6. **Projection / ownership.** Heuristic ownership is value-softmax (`ownership.py`). It does not treat Chase as a leverage-fade when the field hammers CIN. CIN pass stacks were over-ranked vs BUF/IND in this one week. **One-week sample — do not auto-punish CIN forever.**
7. **Operator drift.** Four extra Main History lineups were not in the export. Recap CSV vs History is not a closed loop.
8. **Luck vs skill.** 2/10 cash and −$33.50 on a $5 GPP is a normal down week **if** the 169.96 spike is the product we want. The two 90-point CIN triples are process, not luck.

## Patch backlog

| ID | Sev | Area | Fix | Test idea |
|----|-----|------|-----|-----------|
| W1-P0-UPLOAD | P0 | `src/ceminidfs/export/optimize.py` | Default FanDuel write: `Name (contest-id)` per seat, same shape as `lineups_fanduel_upload.csv`. Keep name-only as `--format names`. Emit Instructions/template columns if FanDuel still needs them. | Round-trip fixture: cell matches `Josh Allen (133104-62239)`; `csv.DictReader` with duplicate `RB`/`WR` headers still maps seats. |
| W1-P0-QSWAP | P0 | `late_swap.py` + CLI | When a rostered WR/RB is Questionable, print swap candidates (same salary band, not auto-apply). Diff export vs a History-like CSV. | Fixture: Odunze Q → suggest McConkey; do not rewrite the lineup unless `--apply`. |
| W1-P1-STACK | P1 | `stack_rules.py` + report | Flag or down-weight chalk QB + both primary WRs (e.g. Burrow+Chase+Higgins). Boost report badge for bring-back + contrarian WR. | Unit: a forced CIN triple gets a `CHALK-QB-WR-WR` badge; optional exclude rule is off by default. |
| W1-P1-TEAMCAP | P1 | `optimize.py` / pydfs | `--max-team-exposure` (default 0.4 for 10-lineup GPP). CHI 70% must fail the report check. | 10 lineups, 70% CHI → warning or rebuild. |
| W1-P1-DEF | P1 | `models/dst.py` + optimize | Do not default-pair bottom-tier DST with already-fragile pass stacks. Report DEF vs stack quality. | Titans + Burrow/Chase/Higgins flagged in report. |
| W1-P2-OWN | P2 | `models/ownership.py` | Leverage-fade column for high-own WR1 when stacking a non-that-team QB. | Chase high-own + Allen stack → fade note. |
| W1-P2-RECAP | P2 | docs + recap path | Week recap command: History totals in, CSV match, extra-lineup warning. Player actuals stay blank without per-seat FPPG. | Totals CSV golden vs this recap. |
| W1-P2-WEATHER | P2 | weather/stadiums | Keep as **soft** prior only (TG06/TG07). Do not auto-punish CIN from one outdoor week. | No code auto-apply; doc note in GPP-WORKFLOW. |

## Week 2 process (operator)

1. Download a **fresh** FanDuel player list the day of the slate. Run `ceminidfs fetch --force` then `ceminidfs run … --profile gpp` with `--final-count` matching bankroll ($5 × N).
2. Use the **ID upload CSV** as the file you paste into FanDuel. If upload fails, stop. Do not Enter from a name-only file.
3. Before 1 p.m. lock, run the Q-player report. Swap or exclude Questionable WR/RB yourself. Agent does not Enter.
4. Read `lineups.report.txt`: fade any chalk QB+both-WR triple you did not mean to keep; cap team exposure (CHI-style 70% is too high for 10 entries).
5. After the slate, score **History totals vs the export CSV only**. Leave player `actual` blank unless a card shows per-player FPPG. Do not mix extra History lineups into the CeminiDFS scorecard.

Agent still does **not** click Enter, Submit, or late-swap on FanDuel.
