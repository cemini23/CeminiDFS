# Week 4 Sunday Million build — defect note

**Date:** 2026-10-04 · **Slate:** 2026 W4 Sun 4 Oct (12-game afternoon)
**Status:** The Week 4 book was not submitted. The operator built it by hand.
**Rule:** This note is a defect list. No code was changed.

The Week 4 book went wrong in a way that would repeat every week. This note
records every fault found, with evidence and a line number where one is known.

---

## P0 — the optimizer ran on FanDuel's own FPPG, not our model

**Symptom.** The lineups contained players our model rates at zero. The odds of
that are low if the model actually drove the build.

**Evidence.** The file the optimizer read was
`runs/2026_week_4/normalized_players.csv`. Its `FPPG` column matched FanDuel's
raw FPPG on every row, and our model on almost none.

```
normalized FPPG == FanDuel raw FPPG : 531 / 531
normalized FPPG == our fd_projection:  61 / 531
```

| Player | 2026 games | our `fd_projection` | FanDuel FPPG |
|---|---|---|---|
| Phil Mafah | **0** | **0.00** | 9.90 |
| Theo Wease Jr. | **0** | **1.43** | 7.63 |
| Brock Bowers | 1 | 7.08 | 25.60 |
| Jaxon Smith-Njigba | 3 | 16.67 | 33.19 |

**Root cause.** `src/ceminidfs/orchestrator/run.py:52`

```python
canonical_csv = Path(salary_path)
```

`canonical_csv` starts as the **salary CSV path**. It is only replaced when
`"project"` is in the selected stages (`run.py:64-70`). The normalize stage at
`run.py:72-78` then reads whatever `canonical_csv` holds. When the stage list has
no `project`, normalize reads the FanDuel salary CSV and copies its `FPPG`
column into the projection slot.

**Trigger.** `run.py:140-142` silently inserts `normalize` before `optimize`. So
`ceminidfs run --stages optimize` re-normalizes from the salary CSV and
**overwrites a correct `normalized_players.csv`**. That is what happened: the
full build at 15:24 was correct, then a later `--stages optimize` run clobbered
it at 15:32. Every `optimize` call after that used the bad file.

**Fix.** Do not default `canonical_csv` to the salary path. Resolve the canonical
projections file (`work_dir/canonical_projections_*.csv`) or raise when it is
missing. Never let normalize fall back to the salary CSV.

---

## P0 — no role filter

**Symptom.** Players with no 2026 snaps were selected, because FanDuel's FPPG
rates them above our model's 0.00.

**Evidence.** Names seen in books: Phil Mafah (0 games), Theo Wease Jr. (0 games),
Jawhar Jordan (0 games), Ty Johnson (0 games by model, 16 targets by pbp).

**Cause.** The pool gate uses the salary CSV's `Injury Indicator` and the research
scratch list. Neither carries snap count or game participation. A practice-squad
call-up has a clean injury row and a market FPPG, so it passes.

**Interim workaround (used this week).** Filter the pool to players with at least
one rush, target, or pass attempt in weeks 1-3. That removed 218 of 531 rows.

**Fix.** Add a real role gate: minimum snaps, or minimum touches over a trailing
window. Make the floor explicit and logged.

---

## P1 — optimizer flags behave inconsistently

All of these were observed on the same day, same pool.

1. **`--count N` returns fewer lineups.** `--count 4` wrote 3 lineups, twice.
   The report warns only at the end (`orchestrator/validate.py:55`).
2. **`--lock` applies on one run and not the next.** `--lock "Josh Allen"`
   produced 4 lineups all with Allen, then a later identical run produced a book
   where lineup 2 had a different QB. The report printed `Locks: (none)` on the
   run where the lock *did* work.
3. **`--exclude` is unreliable.** In one run the excludes appeared in the report
   `Excludes:` line but were absent from the output. In another they took effect.
4. **`--stack "BUF:3"` stacks only some lineups.** With `--count 2`, one lineup
   carried 3 BUF players and the other carried none.
5. **`run` and `optimize` disagree.** The same exclude list behaves differently
   between the `run --stages all` path and a direct `optimize` call.

**Fix.** Diagnose each on a 20-player fixture before the next slate. Add a unit
test per flag. Log the applied locks, excludes, stacks, and counts at the start
of the solve, and assert the delivered count equals the requested count.

---

## P1 — `merge-lineups` writes no upload files

**Symptom.** After `merge-lineups`, `lineups_fanduel_upload.csv` still pointed at
the pre-merge book. The operator would have uploaded the wrong lineup set.

**Cause.** `merge-lineups` writes the name CSV only. `write_lineup_artifacts`
(`export/optimize.py:117`) is not called.

**Fix.** Have `merge-lineups` call `write_lineup_artifacts`, or add a small
`ceminidfs seats --lineups X --players Y` command that regenerates all three
files. `docs/SUNDAY.md` already promises the three files next to `--out`.

---

## P1 — review reports return empty or useless data

1. **`dart_ceiling_rank.csv`** shows `ceiling_missing` on every row. The ceiling
   column is empty, so the report cannot rank. Investigate why the ceiling is not
   populated for week 4.
2. **`stack_fragility_report.csv`** was empty, yet three lineups carried 3 or more
   players from one game (KC@LV, NE@BUF). The flag did not fire.
3. **`duplicate_core_report.csv`** was empty while lineups shared the same core.

**Fix.** Add a test with a known triple-stack lineup that must appear in
`stack_fragility_report.csv`.

---

## P1 — the late-swap clock set drops early games

`load_sunday_kickoffs` (`pipeline/late_swap_oracle.py:348`) accepts only kickoffs
equal to 13:00, 16:05, or 16:25. Week 4 had a **09:30 London game (IND@WAS)**.
Both teams were dropped from the replay pool without a warning.

**Fix.** Take the clock set from the schedule, not a constant. Fail loud when a
Sunday game falls outside the set.

---

## P2 — suspected team-code mapping fault

The FanDuel CSV and the normalized pool list **Kenneth Walker III on KC** and
**Phil Mafah on NYG**. Walker is a Seahawks running back. If the team code is
wrong, every stack count and every game count is wrong.

**Fix.** Check the team mapping against `data/stadiums.py` aliases. Add a test
that a known player lands on the right team.

---

## Process errors (agent side)

1. **Re-running instead of diagnosing.** Each solve takes about 5 minutes with
   `--sim-rerank`. Six re-solves burned roughly an hour. Diagnose flags on a tiny
   fixture first; never iterate on a full solve.
2. **zsh does not split unquoted variables.** `EX="--exclude A --exclude B"` then
   `cmd $EX` passes one broken argument and fails with exit 2. Use explicit flags
   or a zsh array.
3. **`--sim-rerank` is the wrong tool for iteration.** The 25-lineup probe is the
   fast loop.
4. **The upload file was regenerated by hand.** That is a sign the pipeline is
   broken, not a step to normalise.

---

## Strategy notes

- **The K280/K281 work stands.** The model has no edge over salary for players at
  or above $7,000, in 3 of 3 weeks. The market beats the model at the top. This
  is consistent with P0: the books that "worked" were following the market.
- **Plan for next week.** Enter the $0.05 contest about 150 times. Cheap volume
  buys real data: realized lineup scoring, model vs market, and whether the role
  filter changes outcomes.

## Fix order for next week

1. P0 `run.py:52` — normalize must never read the salary CSV.
2. P0 role filter — no player with zero recent snaps.
3. P1 `merge-lineups` upload files.
4. P1 optimizer flag consistency, with tests.
5. P1 report flags that do not fire.
6. P1 late-swap clock set from the schedule.
7. P2 team-code check.
