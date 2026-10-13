# Week 5 build gates — reports become refusals

**Date:** 2026-10-13
**Scope:** `--profile gpp`. The base profile is unchanged.
**Source:** six-model Week 5 audit (`Gambling wiki/briefs/week5-audit/AUDIT.md`).

## Why

The repo already wrote the right diagnostics. The diagnostics were advisory, so
the Week 5 book shipped the exact patterns the reports named.

The audit's two measured facts:

| Fact | Value |
|------|-------|
| Break-even cash count under $0.30/$0.10 | 73 of 150 (48.7%) |
| Week 5 cash count | 30 of 150 (20%) |

The Addison zero was not the cause. Giving every Addison lineup 8 replacement
points changed the cash count by zero (30 → 30). That cluster was lost on its
own. The cause is concentration, not one inactive player.

## What changed

Five gates. Each one reads a lineup book and refuses it. No gate changes a
projection. Values live in `config/nfl_dfs_gpp.yaml`.

| # | Gate | Rule | Code |
|---|------|------|------|
| 1 | 5-player core | A 5-player core appears on at most 12 lineups. A pydfs rule bans the combination inside the solver. | `export/build_gates.py`, `export/optimize.py` |
| 2 | Exposure | Default player cap is 0.20. One player per position reaches 0.30 when his projection leads the next player at that position by 4.0. | `config/nfl_dfs_gpp.yaml`, `export/optimize.py` |
| 3 | Pre-lock Q/D | `late-swap --prelock` exits 1 when a `Q` or `D` player is over 8% of the book. | `export/late_swap.py`, `cli.py` |
| 4 | Low ceiling | A lineup holds at most 1 skill player under 8.0 projected points. | `export/stack_rules.py`, `export/build_gates.py` |
| 5 | Buckets | `ceminidfs buckets` writes the score range, median, and cash rate per rank bucket. | `export/review_reports.py`, `cli.py` |

The 5-player core gate runs inside the solver, not after it. The solver adds
`sum(subset) <= 4` once a subset reaches the cap. A subset of a legal book is
legal, so the simulation rerank cannot break the gate.

## Week 5 before and after

Rebuild source: `runs/2026_week_5/normalized_players.csv`, 150 lineups, GPP
gate values. Before = the shipped book. After = the gated rebuild.

Both GPP paths were rebuilt. The plain solver path took 48 seconds. The
simulation rerank path — the Sunday default — took 173 seconds. Both returned
150 lineups.

| Measure | Before | After |
|---------|-------:|------:|
| Worst 5-player core | 38 lineups | **12** (the cap) |
| Players above 20% | 22 | 2, both on the hatch at 30.0% |
| Highest exposure | 52 of 150 (34.7%), nine players | 45 of 150 (30.0%), Brock Purdy and Jahmyr Gibbs |
| Lineups with 2+ sub-8 skill players | 38 | **0** |
| Addison / Wright / Allen / Chase / Stevenson exposure | 38 each | 0 each |

The worst core was Chase / Addison / Allen / Wright / Stevenson — the exact
cluster the audit named. The gate holds it at 12.

The simulation rerank path (the Sunday default, `ceminidfs run --stages all
--profile gpp`) returned the same shape: worst core 10 of 150, no player over
the cap once the hatch is applied, and zero low-ceiling lineups.

The two hatch players lead their position by 4 or more projected points:
Purdy (QB, +4.87 over the next QB) and Gibbs (RB, +6.16). No WR or TE leads by
4.0, so no WR or TE was exempted.

### Bucket distribution

`ceminidfs buckets --totals runs/2026_week_5/lineup_totals.csv`:

| Bucket | Count | Score range | Median | Cashes |
|--------|------:|-------------|-------:|-------:|
| 1–20 | 20 | 139.24–192.54 | 145.69 | 20 |
| 21–40 | 20 | 129.14–139.06 | 134.60 | 10 |
| 41–100 | 60 | 106.80–129.02 | **122.03** | 0 |
| 101–150 | 50 | 60.50–105.86 | 92.70 | 0 |

These match the audit's rounded numbers. The actionable target is the 41–100
bucket: 60 lineups, zero cashes, median 122.03. The cash line is about 134.7.
Lift that median by about 13 points and the cash rate roughly doubles.

Rank 30 against rank 31 is noise. The buckets hold.

## Still open

- The pre-lock gate flags a `Q` player. It does not swap him. The gated rebuild
  still holds Carnell Tate (Q). The gated simulation rerank held Ashton Jeanty
  (30), Tee Higgins (27), Carnell Tate (26), and Alvin Kamara (1). All four are
  over the 8% cap. The operator must act on the alert, before 1:00 p.m. ET.
- The 20% cap and the core cap reduce the top end too. The rebuild's best lineup
  is not measured here. The next slate must confirm the top of the book holds.
- `lineup_totals.csv` needs real FanDuel standings. The Week 5 ranks were
  inferred. Read the bucket report with that in mind.

## Scoring has one owner

`src/ceminidfs/models/scoring.py` is the only scorer. Three defects lived in the
un-versioned Recap Desk script, not in the repo:

- a skill player got `6 * (return TD)`. FanDuel pays only the D/ST.
- a 2-point pass credited the passer only, not the receiver.
- no event-id guard on `boxes/`, so a second file for one game doubles a stat.

The repo `fd_points` is already correct on the return TD. The decision and the
three defects are recorded in `docs/GROK-BOTS.md`.

## Verified false — do not "fix"

The audit checked these against the live ESPN API. All three are false. No
change was made.

- D/ST sacks are not always zero. `pl[ab]['defensive']['sacks']` is correct.
- D/ST interceptions and opponent fumbles lost are scored.
- Return-TD keys are correct: `kickReturnTouchdowns`, `puntReturnTouchdowns`.

Do not read `ts[ab]['defensive']['sacks']`. ESPN team stats have no `defensive`
category. That change would set every D/ST sack to zero.

## Tests

`tests/test_dfs_gates.py` — one test per gate. The Week 5 run is the fixture
(`tests/fixtures/week5/`). The suite asserts the 38-lineup core, the 22 players
over 20%, the 38 low-ceiling lineups, the 38-lineup Addison exposure, and the
bucket medians.

Run the suite with the sandbox workaround:

```bash
PYTHONPATH="$TMPDIR" .venv/bin/python -m pytest tests -q -p pytest_env_guard -p no:cacheprovider
```

`pytest_env_guard` skips `.env.example`, which the sandbox denies. Without it,
pytest stops at collection with a `PermissionError`. This is a local sandbox
effect, not a repo defect.
