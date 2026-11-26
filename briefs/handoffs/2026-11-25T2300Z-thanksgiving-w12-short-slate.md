# SIP handoff — Week 12 Thanksgiving 3-game short-slate GPP book

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Problem

The operator needs 150 FanDuel GPP lineups for the Week 12 Thanksgiving slate
(`2026-11-26`, contest `137123`, three games: `CHI@DET`, `PHI@DAL`, `KC@BUF`).
The current GPP profile uses 10-game exposure caps (0.20 flat, 0.35/0.20/0.12
tiers). Those caps make a 150-lineup book impossible on six teams. This change
adds a short-slate profile, the slate exclusion file, a pre-upload validator,
and a richer exposure summary.

## Success criteria

### 1. `config/2026-w12-thu-scratch.csv`

Header exactly: `name,team,status,exclude,lock,note`

Use the FanDuel `Nickname` as `name` and the FanDuel team as `team`.
Write every row below. Set `exclude=1` on every row. Leave `lock` empty.

A. Out / IR rows, keep their status token (26 rows):

| name | team | status |
| --- | --- | --- |
| Kenneth Walker III | KC | O |
| Jake Ferguson | DAL | O |
| Roschon Johnson | CHI | O |
| Jonathan Mingo | DAL | O |
| Jalen Hurts | PHI | IR |
| Dontayvion Wicks | PHI | IR |
| Tank Bigsby | PHI | IR |
| Zavier Scott | CHI | IR |
| Jared Wiley | KC | IR |
| Malik Davis | DAL | IR |
| Brittain Brown | CHI | IR |
| Nikola Kalinic | CHI | IR |
| John Michael Gyllenborg | KC | IR |
| Kendrick Law | DET | IR |
| Joshua Palmer | BUF | IR |
| Brashard Smith | KC | IR |
| Tyquan Thornton | KC | IR |
| Princeton Fant | DAL | IR |
| Isiah Pacheco | DET | IR |
| Cole Kmet | CHI | IR |
| Johnny Wilson | PHI | IR |
| Jeff Caldwell | KC | IR |
| Tyler Goodson | DAL | IR |
| Jimmy Holiday | KC | IR |
| Hayden Large | CHI | IR |
| Tom Kennedy | DET | IR |

B. Backup quarterbacks, blank status (12 unique rows):

| name | team |
| --- | --- |
| Tanner McKee | PHI |
| Cole Payton | PHI |
| Tyson Bagent | CHI |
| Case Keenum | CHI |
| Luke Altmyer | DET |
| Joshua Dobbs | DET |
| Sam Howell | DAL |
| Kyle Trask | DAL |
| Miller Moss | CHI |
| Justin Fields | KC |
| Garrett Nussmeier | KC |
| Kyle Allen | BUF |

C. Practice-squad players with no elevation, blank status. `Luke Altmyer` and
`Kyle Trask` are already in list B. Write them once, with note
`backup QB + practice squad` (21 more rows):

Kendre Miller DAL, Frank Gore Jr. BUF, Brock Lampe BUF, Erik Ezukanma PHI,
Anthony Smith DAL, Stephen Gosnell BUF, Dominic Lovett DET, Scotty Miller CHI,
Ja'Mori Maclin BUF, Thomas Gordon DET, Quentin Skinner PHI, Miles Kitselman DET,
Hayden Rucci PHI, Michael Trigg DAL, JP Richardson CHI, Qadir Ismail CHI,
Lucky Jackson DET, John FitzPatrick KC, Omari Evans KC, Jackson Meeks DET,
Trent Sherfield Sr. BUF

D. Operator overrides (3 rows):

| name | team | status | note |
| --- | --- | --- | --- |
| Elijah Mitchell | PHI | | 0 touches in recent lookback |
| Dalton Kincaid | BUF | Q | thumb; 8:20 PM GTM in rain |
| Noah Gray | KC | Q | ribs; 8:20 PM GTM in rain |
| EJ Smith | KC | | 0 games played; operator exclude |
| Stephen Carlson | CHI | | 0 games played; operator exclude |
| Thomas Odukoya | KC | | 0 games played; operator exclude |

Total: 65 unique rows. `Salvon Ahmed` is NOT in this file. Cap him with
`--exposure-override "Salvon Ahmed=0.05"`.

### 2. `config/2026-11-26-qb-starters.csv`

Header exactly: `Team,Starter,backups_hard_exclude`

```
CHI,Caleb Williams,Tyson Bagent|Case Keenum|Luke Altmyer|Miller Moss
DET,Jared Goff,Joshua Dobbs|Luke Altmyer
PHI,Joe Milton III,Tanner McKee|Cole Payton|Jalen Hurts
DAL,Dak Prescott,Sam Howell|Kyle Trask
KC,Patrick Mahomes,Justin Fields|Garrett Nussmeier
BUF,Josh Allen,Kyle Allen
```

### 3. `config/nfl_dfs_gpp.yaml` — new `short_slate` block

Add one top-level block. Do not change any existing key in this file.

```yaml
# The three-game short slate cannot use the ten-game caps. A CLI flag turns
# this block on. The block replaces max_exposure, min_salary, uniques,
# exposure_tiers, and the core gate.
short_slate:
  enabled: true
  max_teams: 6
  max_exposure: 0.65
  min_salary: 57500
  uniques: 2
  exposure_tiers:
    enabled: true
    stud:
      min_salary: 7000
      cap: 0.65
    mid:
      min_salary: 5500
      max_salary: 7000
      cap: 0.35
    value:
      max_salary: 5500
      cap: 0.20
    skill_positions: [QB, RB, WR, TE]
    bad_game_script_rb:
      spread_threshold: 10.0
      cap: 0.10
    role_cliff_cap: 0.10
    player_overrides: {}
  gates:
    core:
      enabled: false
      size: 5
      max_count: 12
    low_ceiling:
      enabled: true
      projection_floor: 8.0
      max_per_lineup: 1
      skill_only: true
    exposure_hatch:
      enabled: false
      lead_margin: 4.0
      cap: 0.30
```

### 4. `src/ceminidfs/cli.py`

1. Add `--short-slate` (`action="store_true"`, default `False`) to
   `_add_optimizer_build_arguments` so both `optimize` and `run` accept it.
2. Add `_apply_short_slate(config, args)`. When the flag is set, read the
   `short_slate` block from the loaded config and set these keys on `config`:
   `max_exposure`, `min_salary`, `uniques`, `exposure_tiers`, `gates`.
   Raise `ValueError` when the block is missing or `enabled` is false.
3. Call `_apply_short_slate(config, args)` in `_cmd_run` and `_cmd_optimize`
   after `runtime_config(...)` and before `run_pipeline` / `_run_optimize`.
4. Add `--expected-count` (int, default 0) to `_add_recap_bundle_arguments`.
5. After the pipeline returns, when `config.get("recap_bundle_dir")` is set:
   build the prelock gate with the same paths as the run, then call
   `assert_upload_ready(<bundle>/_src_lineups.csv, gate,
   expected_count=<--expected-count or 0>, min_uniques=<config uniques>)`.
   Catch `PrelockExcludeError` in the existing handler pattern and return 1.

### 5. `src/ceminidfs/data/availability.py`

1. Add `PS` and `PRACTICE SQUAD` to `PRELOCK_HARD_STATUSES`, and normalize a
   token that starts with `PRACTICE` to `PS`.
2. Add `upload_id_prefix(gate) -> str`. Return the most common `Id` prefix
   before the first `-` from the gate players. Return `""` when no player has
   such an id.
3. Add `upload_validation_issues(lineup_csv, gate, *, slate_prefix=None,
   expected_count=0, salary_cap=60000, min_uniques=0) -> list[str]`.
   Collect one message per violation:
   - missing file;
   - row count differs from `expected_count` when `expected_count > 0`;
   - duplicate lineup: two rows hold the same set of player ids;
   - a token id does not start with `<slate_prefix>-` when `slate_prefix` is set;
   - a token id is not a gate player id;
   - the lineup salary sum is above `salary_cap`;
   - any hard-excluded player, via `lineup_exclude_hits`;
   - a pair of lineups with fewer than `min_uniques` different players.
4. Add `assert_upload_ready(...)` that raises `PrelockExcludeError` with the
   joined messages when the list is not empty.
5. Extend `_exposure_text` with four sections after the existing tables. Keep
   every existing section and header unchanged.
   - `## Quarterbacks` — one row per QB in the pool.
   - `## Defenses` — one row per DST in the pool.
   - `## Stacks` — top 5 rows. Use the salary `Game` column to find the
     opponent. Count one row per (QB team, catcher count band) pair. Bands:
     `QB+1`, `QB+2`, `QB+3`. Add a `bring_back_pct` column: the share of those
     lineups that also hold at least one player from the opponent team.
   - `## Salary left` — buckets `<500`, `500-1500`, `1500-2500`, `>2500`, with
     count and percent, plus the median.
6. `format_exposure_summary` prints the same text, then a
   `## Top 20 skill players` table. The table lists QB/RB/WR/TE only.

### 6. Tests (new files only)

- `tests/test_upload_validation.py`: clean book passes; duplicate lineup fails;
  wrong id prefix fails; salary over cap fails; hard-excluded player fails;
  unique-gap violation fails.
- `tests/test_short_slate_profile.py`: `load_config(profile="gpp")` plus the
  short-slate merge gives `max_exposure 0.65`, tier caps `0.65/0.35/0.20`,
  `uniques 2`, `min_salary 57500`, core gate off; plain `gpp` is unchanged.

### 7. Smoke check (not the real slate)

Write a synthetic 6-team CSV in `tmp_path` inside the test or a scratch file.
Run `ceminidfs optimize` with `--short-slate --count 4` and confirm the short
slate config applies and the validator runs. Do not run the full Week 12
pipeline. The operator runs it after handoff.

## Verify

```bash
python3 -m py_compile src/ceminidfs/cli.py src/ceminidfs/data/availability.py
python3 -m pytest tests/test_upload_validation.py tests/test_short_slate_profile.py tests/test_recap_bundle.py tests/test_exposure_tiers.py -q
python3 -m pytest tests -q
```

All three commands must pass. Run pytest with the repo `.venv` when it exists.

## NEVER

- Do not commit, push, or change branches.
- Do not modify an existing test file.
- Do not change `config/nfl_dfs.yaml` or the existing keys in `config/nfl_dfs_gpp.yaml`.
- Do not weaken a gate or a test to make a run green.
- Do not open a browser, log in to FanDuel, or click Enter, Submit, or late-swap.
- Do not scrape a paid site.
- Do not write a secret or a credential to any file.
- Do not run the full Week 12 pipeline or fetch network data.

## Plan

1. Read `src/ceminidfs/data/availability.py` and `src/ceminidfs/export/exposure_tiers.py`.
2. Write `config/2026-w12-thu-scratch.csv` (65 rows) and `config/2026-11-26-qb-starters.csv`.
3. Add the `short_slate` block to `config/nfl_dfs_gpp.yaml`.
4. Add the CLI flag, the merge helper, and the bundle validation call in `cli.py`.
5. Add the prefix helper, the validator, the `PS` token, and the new summary
   sections in `availability.py`.
6. Add the two test files.
7. Run the Verify commands until all pass.
