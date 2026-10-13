# SIP handoff — K283 team coverage and the dart rule

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Lane

mid — build the coverage report and the dart rule. Grok plans if the plan below
is unclear; cheap executor implements.

## Context

The operator's read: the research narrows the pool too far, the book hard-fades
whole teams, and most games contain at least one touchdown scorer. For a cheap
dart, one touchdown is enough.

The claim was measured. Each week, count slate teams with **zero book exposure**
and check what their best actual scorer did.

Two measurement errors were made before the numbers settled. Both are easy to
repeat, so guard against them in the code:

1. **Off-slate teams.** Do not use every team that played that week. Thursday,
   Sunday-night, and Monday games are not on the slate. Counting them inflated
   the first pass to 11, 7, 11.
2. **Defenses.** A defense is stored as `__dst__` in the points lookup, not as a
   player name. A team whose only rostered spot was its defense then counts as
   zero exposure. Mapping the defense to its team name cut the second pass from
   7, 3, 6 to the numbers below. The week-1 book rostered five defenses, so this
   error is large.

Corrected result:

| Week | Slate teams | Zero exposure | Zero exposure **and** an 18+ scorer |
|------|-------------|---------------|--------------------------------------|
| 1 | 24 | 7 | **3** |
| 2 | 26 | 2 | **2** |
| 3 | 26 | 10 | **4** |

Repeat offenders, zero exposure and a scored player:
- Week 1: GB (Watson 32.7), MIN (Jefferson 25.2), TB (Irving 18.8).
- Week 2: HOU (Schultz 23.0), CIN (Chase 23.0).
- Week 3: SEA (Smith-Njigba 33.4), SF (Purdy 31.3), PIT (Rodgers 22.9), JAX (Lawrence 20.6).

The `faded_and_produced` counts are the ones that must reproduce. The
zero-exposure counts may differ by one team depending on how a name join is
done; state the difference if it appears.

Week 2 shows the pipeline can cover a slate. So this is unstable behaviour, not
a fixed rule. Find out which it is.

## Success criteria

1. **`src/ceminidfs/pipeline/fade_coverage.py`** exists and runs as
   `.venv/bin/python -m ceminidfs.pipeline.fade_coverage --season 2026 --week 3`.

2. **Slate teams come from the salary CSV**, never from every team in the
   week's play-by-play. This is the bug in the earlier measurement. Make the
   input explicit and log the team list.

3. **`team_coverage(week, salary_path, lineups_path)`** returns one row per
   slate team: `team`, `book_exposure` (players rostered from that team),
   `top_scorer_name`, `top_scorer_points`, `zero_exposure` (bool),
   `faded_and_produced` (bool, true when `zero_exposure` and the top scorer is at
   or above a threshold, default 18.0).

4. **`season_rollup(season, weeks)`** counts, per team, how many weeks it had
   zero exposure **and** a scorer at or above the threshold. Sort by that count
   descending. This shows the repeat offenders.

5. **Report.** Write `reports/audit/fade-coverage-w{week}.md` and a season file
   `reports/audit/fade-coverage-season.md`. Each file lists the per-week table
   and the rollup. State the threshold in the file.

6. **Dart rule.** Add `--keep-team-dart SALARY` (a dollar amount, default 0 =
   off) to `ceminidfs optimize` and `ceminidfs run`. When set, the candidate pool
   must keep at least one player at or below that salary from every slate team,
   unless that player is excluded by injury status (`OUT` / `IR` / `D`). Log every
   team where the rule kept a player that the normal path would have removed.
   The rule changes the candidate pool only; the optimizer still chooses freely.

7. **Soft fade is not removal.** The research scratch file stays OUT / IR / D
   only. Add a separate, optional `--soft-fade TEAM` input that lowers a team's
   weight instead of deleting its players. Document both in `docs/SUNDAY.md`:
   hard fade removes, soft fade discounts.

8. **`tests/test_fade_coverage.py`** with at least:
   - A fixture where a slate team has zero exposure and a 20-point scorer is
     reported as `faded_and_produced`, and a non-slate team with the same scorer
     is not counted.
   - A fixture where a rostered team is not flagged.
   - `--keep-team-dart` keeps the cheapest eligible player on a team whose whole
     roster sits above the normal pool cut.
   - The rollup counts a team twice when it fails in two weeks.

## Verify

- `.venv/bin/python -m ceminidfs.pipeline.fade_coverage --season 2026 --week 1`
- `.venv/bin/python -m ceminidfs.pipeline.fade_coverage --season 2026 --week 2`
- `.venv/bin/python -m ceminidfs.pipeline.fade_coverage --season 2026 --week 3`
- `.venv/bin/python -m pytest -q tests/test_fade_coverage.py`
- `.venv/bin/ruff check src tests`
- `test -f reports/audit/fade-coverage-season.md`

The three weeks must reproduce **3 / 2 / 4** teams flagged as
`faded_and_produced`. If a week shows a different number, state why in the
report.

## NEVER

- Do not count teams that are not on the salary CSV slate.
- Do not score a defense as the literal `__dst__`. Map it to its team name, or
  the team is counted as zero exposure when its defense was rostered.
- Do not change the projection, salary, ownership, or scoring models.
- Do not make `--keep-team-dart` default on.
- Do not put soft fades into the scratch file. It stays OUT / IR / D.
- Do not edit `late_swap_oracle.py`, `late_swap_replay.py`, `permutation_gate.py`,
  `permutation_test.py`, or `premium_guard.py`.
- Do not fix the `run.py:52` defect here. It is tracked in
  `briefs/2026-10-04_w04-build-postmortem.md` and has its own fix.
- Do not claim the dart rule improves results until it is measured. Build it,
  log it, measure it next slate.
- No network scrape. No paid-site data. No live order.
- Do not commit. Do not push.

## Plan

Goal: measure team coverage every week, and stop the pool from losing a whole
team by accident.

1. The report is the feedback loop we never had. Build it first. It runs after
   the games, so it uses actual points. It must use the salary CSV for the slate
   team list, because the first attempt used every team that week and the numbers
   were wrong.

2. Keep the threshold as a named constant, default 18.0. An 18-point game from a
   cheap player is a real hit. Make it easy to change.

3. The rollup is the useful part. One week is noise. A team that is faded and
   produces in three of four weeks is a defect in the research, not a bad break.

4. The dart rule is a pool guard, not a lineup constraint. It keeps one cheap
   candidate per team alive. The optimizer can still ignore it. That keeps the
   rule safe: it widens the pool and cannot force a bad player into a book.

5. Default the dart rule off. Turn it on next slate, log how often it fires, and
   compare coverage week over week with the report.

6. Week 2 covered the slate with only 3 missed teams. Find out why week 2 differed
   from weeks 1 and 3 before changing anything else. The cause is most likely in
   the pool build or the optimizer constraints, not in the research notes.

7. Boundary: a human types the ticket. No live order. No auto-submit.
