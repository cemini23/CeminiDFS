# SIP handoff — K284 W4 fixes, research-export, premium market, coverage darts

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Lane

hard — Grok CLI implements. The plan below is written in the parent session.

Do the groups in order: A, then B, then C, then D. Stop after each group and run that group's tests. Do not start the next group while the current group fails. Do not run the free audit. The parent runs Group E after this handoff.

## Context

Week 4 was not submitted. The operator built the book by hand. The defect list is `briefs/2026-10-04_w04-build-postmortem.md`. The prose research layer is retired. Do not add Gemini, a weekday prompt, or a new prose writer.

Two open handoffs are in scope:

- `briefs/handoffs/2026-10-03_k282-market-premium.md`
- `briefs/handoffs/2026-10-04_k283-team-coverage-darts.md`

The core failure is in `src/ceminidfs/orchestrator/run.py`. Line 52 sets `canonical_csv = Path(salary_path)`. `normalize` then copies FanDuel `FPPG` into the projection slot. On the Week 4 file, normalized FPPG matched salary FPPG on 531 of 531 rows. Brock Bowers read 25.60. The model says 7.08.

`_parse_stages` inserts `normalize` before `optimize`. A later `ceminidfs run --stages optimize` overwrites a good `normalized_players.csv`.

P2 in the postmortem is a false positive. nflverse play-by-play puts Kenneth Walker III on KC and Isaiah Likely on NYG for 2026 weeks 1–3. The FanDuel export agrees. Close P2 in the postmortem with that sentence. Do not change a team map.

There is no Week 5 salary CSV in `data/slates/`. Do not download one. Do not invent one. Unit tests cover the pipeline. A live Week 5 run waits for the operator's file.

K283 report code already exists. The written reports are the corrected counts, not the earlier bad pass:

| Week | Zero exposure | Faded and produced |
|------|---------------|--------------------|
| 1 | 6 | 3 |
| 2 | 2 | 2 |
| 3 | 10 | 4 |

The figure 7 / 3 / 6 is the pass from before defense rows were mapped to a team name. Do not change the metric to print 6 for week 3. Week 3 faded-and-produced stays 4. Say why in the season report if that sentence is missing: a rostered defense is the team, not the token `__dst__`.

`fade_coverage.py`, `--keep-team-dart`, and `--soft-fade` already exist. Do not rebuild them. Add a missing test only.

## Success criteria

### Group A — P0, blocking

1. `orchestrator/run.py` must not default `canonical_csv` to the salary path. When `project` does not run, resolve `work_dir/canonical_projections_*.csv`. Prefer `canonical_projections_{season}_w{week}.csv`. Raise when the file is missing. Raise when the resolved path is the salary path. `normalize` in the run pipeline must never receive the salary CSV.
2. Do not make `export/normalize.py` `normalize_csv` reject every salary-shaped file. `tests/test_optimize_main_slate.py` calls it on `tests/fixtures/synthetic_fd_slate.csv`. The guard lives in the orchestrator.
3. A test builds a canonical file whose `fd_projection` differs from a salary `FPPG`, writes it under a temp `work_dir`, and runs stages `optimize` only. `normalized_players.csv` FPPG stays equal to `fd_projection`. A second test raises when the canonical file is missing, and it does not write `normalized_players.csv`.
4. Role gate. No QB, RB, WR, or TE with zero participation in nflverse weeks `1..N-1` enters the pool. A participation event is a rush, a target, or a pass attempt. Log the floor and the dropped count: `role gate: floor=1 touch in weeks 1..{N-1}; dropped={n}`. Week 1 has no prior week: log the floor and drop nobody. A DST row stays. A Questionable player with a touch stays. A name with no play row is dropped.
5. Tests inject a tiny play-by-play frame. No network. A 0-touch player is dropped. A Questionable player with a touch stays. The synthetic end-to-end cache still produces 150 lineups in `tests/test_e2e_run.py`. Give those fixture names a touch, or the gate will empty the pool.
6. Close P2 in `briefs/2026-10-04_w04-build-postmortem.md`. One status line. No mapping change. Add a test that a Walker row stays KC and a Likely row stays NYG through normalize.

### Group B — P1

7. Log the applied locks, excludes, stacks, and requested count at the start of `generate_lineups`. After the solve, raise when the written count is not the requested count. Do not write a short file and warn later. Update `tests/test_validate.py` only if the optimizer now raises before validate. The validator may still allow a short file when it is called alone.
8. One unit test each for `--lock`, `--exclude`, `--stack`, `--count`, `--uniques`, and `--max-exposure`, on a 20-player fixture. Diagnose on that fixture. Do not run a full-slate solve. `run` and `optimize` must put the same flag set on the optimizer. A test compares the two kwargs builders.
9. `merge-lineups` writes the upload files. It currently calls `write_lineup_rows` only (`export/optimize.py` `merge_lineup_csvs`). After the merge, write `lineups_fanduel_upload.csv` and the ids file. Use the players CSV for FanDuel ids (`Name (id)`). Add `--players`. When it is omitted, look for `normalized_players.csv` next to `--out` and raise when it is missing. A test merges two tiny books and checks the upload cells.
10. `stack_fragility_report.csv` lists a known 3-player same-game group, not only a 3-WR group. Keep the current WR-triple rows. Add the same-game group. Update `test_allen_shakir_kincaid_not_chalk` if that lineup now qualifies. Do not delete the WR tests.
11. `duplicate_core_report.csv` already lists a QB plus the same two RB slots when the core appears on more than 2 lineups (`tests/test_review_reports.py`). Keep that threshold. Do not lower it. `test_duplicate_core_writes_header_when_none_exceed_two` must stay empty. If `Name (id)` cells fail to match, fix the name parser and add that fixture.
12. `dart_ceiling_rank.csv` must not print `ceiling_missing` when the cell has a number. Accept `Projection Ceil`, `Ceiling`, `fd_ceiling`, and `ceiling`. An empty cell still prints `ceiling_missing`. Add one fixture row with `Projection Ceil` filled and assert the note is blank. Do not invent a ceiling. `normalize` already copies `Projection Ceil` when the canonical file has it. The Week 4 blanks were the salary-file bug in Group A.
13. `load_sunday_kickoffs` (`pipeline/late_swap_oracle.py`) takes Sunday kickoffs from the schedule. Remove the filter `clock not in AFTERNOON_KICKOFFS`. Keep Thursday, Saturday, and Monday out. A Sunday row with a blank or unparsable `gametime` raises. A Sunday 09:30 game is kept. Do not change `DECISION_CLOCKS` or `decision_times`.

### Group C — research-export

14. Add `ceminidfs research-export env`. It writes `environment.csv` with the CeminiParlays columns: `slate_id,game_id,team,opp,implied_total,spread,roof,weather_exposed,wind_mph,precip_pop`. One row per slate team. A 12-game slate has 24 rows. Do not pad. Slate teams come from the salary CSV. `implied_total` and `spread` come from `data/vegas.py` when the cache has them. Blank when the cache has no number. Roof comes from `data/stadiums.py`. `weather_exposed` uses `roof_type_is_weather_exposed`. A dome or `semi_open` leaves wind and precip blank. Do not write 0.
15. Wind and precip for an exposed stadium come from the NWS hourly forecast at kickoff (`api.weather.gov`). Tests inject a fake URL opener. No network in pytest. Extra columns `wind_source_url`, `wind_retrieved_at`, `precip_source_url`, `precip_retrieved_at` are allowed. Parlays `DictReader` ignores them.
16. Add `ceminidfs research-export status`. One source: the nflverse injuries cache (`injuries.parquet` from the fetch stage). That table is the club injury report. Do not scrape HTML. Do not add a club-page fetcher. Write two files in `--out`:
    - `status_dfs.csv` — `name,team,status,exclude,lock,note,source,retrieved`
    - `status_parlays.csv` — `name,team,status,source,retrieved`
    Never-enter tokens set `exclude` true: `out|ir|inactive|doubtful|nfi|pup|suspended`. Warn tokens leave `exclude` false: `q|questionable|gtd|game-time|limited|dnp`. `lock` stays false. Every row has `source` and `retrieved`. Do not invent a token when the cache status is unknown.
17. Add `ceminidfs research-export validate --slate <environment.csv>`. Exit non-zero when a team code is unknown to `stadiums.py`, when a `game_id` is not the two teams on that row pair, or when `wind_mph` or `precip_pop` is filled and the matching URL or timestamp is blank. Optional `--salary` also rejects a game that is not on that salary file.
18. Handoff fix in `export/review_reports.py` `write_parlays_handoff`. `projection` is `fd_projection` when that column is present. Never prefer a salary `FPPG` over `fd_projection`. Add column `injury_status`. Drop DST, DEF, and D rows. Fill `implied_total` from an environment file when `--environment` is passed to `review`, `optimize`, and `run`. Blank when no cited total exists. Document the file in `docs/HANDOFF-PARLAYS.md` as the path for `ceminiparlays compose --environment`. Do not edit the CeminiParlays repo.

### Group D — K282 and K283

19. Add `--premium-mode {off,baseline,market}` on `project` and `run`. Default `off`. `off` is a byte-identical no-op. `baseline` calls the existing `apply_premium_guard`. Do not change that function's math or `salary_implied_baseline`. `market` adds `market_premium_projection` in `models/premium_guard.py`. Rows with `fd_salary < 7000` stay unchanged. Premium rows are ordered by salary descending, then by the model projection to break a salary tie. Their projection values are reattached in that order. The premium multiset does not change. You may keep `--premium-guard` as a hidden alias for `baseline`.
20. Extend `pipeline/premium_guard_backtest.py`. Per week 1, 2, and 3 report `n`, `partial_off`, `partial_baseline`, `partial_market`, and the deltas. Also build a small lineup book per mode per week (count 20, no sim-rerank) and report total points. Write `reports/audit/k282-market-premium.md`. Scratch files go under `reports/audit/k282-scratch/` or a temp directory. Do not write `runs/2026_week_1`, `runs/2026_week_2`, or `runs/2026_week_3`.
21. Recommend `market` only when its lineup total is highest in at least two of the three weeks and it never loses to `off` by more than 2 percent in the other week. If it fails the rule, say it is not recommended. Leave the default at `off`. The weekly command may pass `--premium-mode market`. That is not the default.
22. `tests/test_premium_market.py` covers: premium rows come out in descending salary order; the premium projection multiset is unchanged; a salary tie keeps the model order; rows under 7000 stay untouched; `off` is a byte-identical no-op.
23. K283: do not rebuild `pipeline/fade_coverage.py` or the dart guard. Run the week-3 module. It prints faded-and-produced 4. Exit 0. Confirm `tests/test_fade_coverage.py` still has the non-slate, rostered, dart, and two-week rollup cases. Add only a missing case.

## Verify

- `.venv/bin/python -m pytest -q`
- `.venv/bin/ruff check src tests`
- `.venv/bin/python -m ceminidfs.pipeline.fade_coverage --season 2026 --week 3`
- `.venv/bin/python -m ceminidfs.pipeline.premium_guard_backtest`

The parent runs the Week 5 commands after a salary CSV exists. Do not add them here. They have no input file.

## NEVER

- Do not default `canonical_csv` to the salary path.
- Do not let the run-pipeline normalize stage read the salary CSV.
- Do not change `apply_premium_guard` or `salary_implied_baseline` math. Add the market mode beside them.
- Do not make `--premium-mode market` or `--keep-team-dart` the default.
- Do not put a soft fade into the scratch file. The scratch file stays OUT, IR, and D only.
- Do not change Kenneth Walker III off KC. Do not change Isaiah Likely off NYG.
- Do not retune salary, ownership, volume, usage, stats, or scoring.
- Do not change `DECISION_CLOCKS`. Do not edit `permutation_gate.py` or `permutation_test.py`.
- Do not count a team that is not on the salary CSV. Do not score a defense as the literal `__dst__`.
- Do not change the fade metric so week 3 prints 6.
- Do not add a prose research layer. No Gemini. No new weekday prompt. No HTML scrape of a club page.
- Do not invent a weather number, an implied total, an injury token, or a ceiling.
- No network in pytest. No paid-site data. No live order. No auto-submit.
- No secrets in code, tests, logs, or this file. Never print a key.
- Do not write `runs/2026_week_1`, `runs/2026_week_2`, or `runs/2026_week_3`.
- Do not commit. Do not push.
- Do not run the free audit.

## Plan

Goal: the optimizer reads the model. Then the flags, the export, the market order, and the dart report stay honest.

1. Fix the path before any other work. In `run_pipeline`, start `canonical_csv` as `None`. After `project`, set it from `project_week`. Before `normalize`, if it is still `None`, glob `work_dir/canonical_projections_*.csv` and prefer the season-week name. Raise `FileNotFoundError` with the work directory when nothing matches. Compare the resolved path to `Path(salary_path).resolve()` and raise when they are equal. Pass only that path to `_run_normalize`. The auto-inserted `normalize` before `optimize` then refreshes the pool from the model file. It cannot copy FanDuel FPPG.

2. Put the role gate in `export/pool_guards.py` as `apply_participation_gate`. The orchestrator loads play-by-play for weeks `1..week-1` through the existing `load_season_pbp` helper and passes the name set in. Call the gate from the normalize stage so a later `optimize` cannot put a 0-touch name back. Skill positions only. DST stays. Week 1 is a no-op with a log line. Tests build a three-row frame. Update the synthetic cache used by `test_e2e_run.py` so each fixture skill player has one touch. Missing play-by-play in a real run raises. `allow_stub` may skip the gate and must log that skip.

3. Flag work stays on a 20-player CSV. Log locks, excludes, stacks, and count in `generate_lineups` before `load_players_from_csv` returns into the solve. After `_optimize_or_raise` and the exposure selector, raise `ValueError` when `len(lineups) != count`. That is the `--count 4` wrote 3 defect. Read `apply_locks_and_excludes` and the `run` kwargs in `_optimize_build_kwargs`. Both CLI commands already share `_optimizer_build_overrides`. A test builds one namespace and asserts the key set from the run path equals the key set from the optimize path. Each flag test uses count 1 or 2. Lock: every lineup contains the locked name. Exclude: the name is absent. Stack: a `TEAM:3` rule puts 3 players from that team on every lineup. Uniques and max-exposure: the written book obeys the cap. If pydfs cannot satisfy the constraint, the test expects the raise, not a short file.

4. Merge cannot call `write_lineup_artifacts` directly. That function wants pydfs lineup objects. Add `write_merged_upload(name_csv, players_csv)` next to it. It reads the merged name rows, joins ids from the players file, and writes the upload file and the ids file beside `--out` via `fanduel_artifact_paths`. `merge-lineups` calls it before it returns. The test uses two 1-lineup CSVs and a players file with ids.

5. Same-game fragility is a second row builder inside `_fragility_rows_for_lineup`. Group every skill player by `game_id`. When a group has 3 or more names, write a row. Keep the WR-triple rows. The new fixture is three teammates in one game who are not three WRs. Read `test_allen_shakir_kincaid_not_chalk` before you edit. If Allen, Shakir, and Kincaid share a game, expect the new row and stop expecting an empty file.

6. Duplicate-core and ceiling behavior are already tested. Keep the "more than 2 lineups" rule. Widen `_CEILING_KEYS` with `fd_ceiling` if it is missing. `Projection Ceil` already matches `projection ceil`. Add the filled-cell fixture. Do not flip empty cells to a rank.

7. Sunday kickoffs: delete the `AFTERNOON_KICKOFFS` membership test inside `load_sunday_kickoffs` only. Parse every Sunday `gametime`. Raise on a Sunday row whose clock is missing. The test builds a one-game frame at 09:30 and asserts both teams are in the dict. A blank `gametime` raises. Night games stay out because `weekday` is not Sunday.

8. Research export is a new module `src/ceminidfs/export/research_export.py` plus a `research-export` subparser with `env`, `status`, and `validate`. Env reads the salary file for teams, games, and kickoff. Vegas cache fills implied total and spread, or the cells stay blank. Stadium roof is a lookup, not a guess. NWS is called only for an exposed roof, through an opener argument so tests pass a fake hourly payload. Status reads `injuries.parquet` only. Map `report_status` and practice fields onto the two token lists. Write both CSVs from that one frame. Validate is pure and local. The handoff writer prefers `fd_projection`, drops a defense row, adds `injury_status`, and copies `implied_total` when `--environment` points at the CSV from step 8.

9. Premium market is a permutation, not a fit. Add the function. Dispatch in `pipeline/project.py` on `premium_mode`. `off` returns the same rows object. The backtest reuses `partial_spearman` and a 20-lineup scratch solve. Apply the decision sentence from the K282 handoff. Three weeks is a small sample. A tie is not a win.

10. K283 is already on disk. Read `reports/audit/fade-coverage-w3.md` before you edit that module. If the faded count is 4, leave the math. Run the module to refresh the file. Do not "fix" 4 into 6.

11. Boundary: a human types the ticket. No live order. No auto-submit. No commit.
