# Super audit — Week 1 FanDuel Main results (postmortem)

You are a **readonly** auditor. Do **not** edit code. Report only.

**Mode:** `brief-plan` (results GO/NO-GO + next-week process)
**Question:** How did CeminiDFS’s 10 × $5 Sunday-afternoon FanDuel classic entries do on 2026-09-13? What went right, what went wrong, and which **code/process** changes should ship before Week 2?

## Operator facts (do not invent)

- Bankroll: **$50**, 10 entries × **$5** on FanDuel Main (`9/13/26 1:00pm EDT`), contest **133104**.
- Agent does not Enter/Submit. Operator uploaded after an ID-format CSV.
- Source zip on Desktop was named by the operator as GradeDFS; the packet on disk is `2026-09-14-week1-recapdfs.zip` → copied to `briefs/2026-09-14_week1-fd-recap/`.
- Official actuals are **lineup totals from FanDuel History screenshots only**. Per-player FPPG was **not** on the cards. Do **not** back-solve seat scores.
- History has **14 unique Main lineups**; 4 of them are **not** in the CeminiDFS export (`L03, L08, L11, L12`). Score **CeminiDFS CSV1–10** separately from extra History rows.
- Odunze (Q, calf) was swapped to **Ladd McConkey** on CSV6/CSV7. L02 History also shows FLEX **Swift** vs CSV **Monangai**.

## CeminiDFS export → History map

| CSV | History | Total | Won | Notes |
|-----|---------|-------|-----|-------|
| CSV3 | L01 | **169.96** | **$9.00** | Best. Allen + Shakir/Kincaid/Cook + Burden + Hutchinson + Henry + JAX |
| CSV6~ | L02 | **149.34** | **$7.50** | Odunze→McConkey; History FLEX Swift vs CSV Monangai |
| CSV1 | L04 | 143.36 | $0 | Close miss (Allen/St. Brown/Marks/Eagles) |
| CSV2 | L05 | 136.86 | $0 | Allen + Chase, no Burden |
| CSV8 | L06 | 131.34 | $0 | Jones/Jeanty/Bijan/IND WRs |
| CSV10 | L07 | 126.06 | $0 | Burrow/Jeanty/Achane/Iosivas/Olave/Higgins |
| CSV7 | L09 | 116.04 | $0 | Jones + McConkey swap |
| CSV9 | L10 | 115.78 | $0 | Brissett ARI stack |
| CSV4 | L13 | 96.46 | $0 | Burrow+Chase+Higgins (worst-tier) |
| CSV5 | L14 | 91.36 | $0 | Burrow+Chase+Higgins (worst) |

**Our 10:** fees **$50**, won **$16.50**, net **−$33.50**, cashed **2/10**. Best 169.96, worst 91.36.

Not in CSV (do not blame the optimizer for these): L03 148.66 cashed $7.60 (2-entry $5.05); L08/L11/L12 $0.

## Build that produced CSV1–10

```text
ceminidfs run --season 2026 --week 1 --salary data/slates/2026-09-13_fd_sun.csv \
  --site fanduel --stages all --profile gpp \
  --final-count 10 --candidates 400 --min-salary 58500 --max-exposure 0.3 --uniques 2 \
  --stack qb:3 --one-rb-per-team --no-offense-vs-dst
```

- Q players kept in pydfs (`with_injured=True`).
- nflverse `spread_line` negated at extract (positive = home favored).
- GPP default 500 candidates; this run used 400.
- Name-only `lineups.csv` **failed FanDuel upload**; `Name (ID)` / ID-only files were needed.
- CHI 70% team exposure; Chase 30%; Kamara 0/10; Odunze was 2/10 then swapped.

## Tool-gap table (from recap, do_not_auto_apply)

Read `tool-gaps.md` in the pack. Surfaces: stack_rules, injury, projection, ownership, defense_multiplier, weather, stadiums.

## Code you may cite

- `src/ceminidfs/export/optimize.py` — name-only export; no FanDuel ID upload writer
- `src/ceminidfs/export/stack_rules.py` — `qb:3` etc.
- `src/ceminidfs/models/ownership.py`, `volume.py`, `dst.py`
- `docs/GPP-WORKFLOW.md`
- `config/nfl_dfs_gpp.yaml`

## Required output

1. **Verdict:** one of SHIP-PROCESS / REWORK / REJECT for Week 2 readiness.
2. **Scorecard** for our 10 only: cash rate, net, best, worst. Claim + locator.
3. **Went right** (≤5 bullets).
4. **Went wrong** (≤8 bullets) — process vs model vs luck. Do not invent player FPPG.
5. **Patch backlog** — every issue with: ID, severity (P0/P1/P2), file/area, fix, test idea.
6. Must include **FanDuel upload format** (ID cells + template columns) if you agree it is a Week 2 P0.
7. **Week 2 process** — 5 numbered operator steps. Agent still does not Enter.

{pack_index}
