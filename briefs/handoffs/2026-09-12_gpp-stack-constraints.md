# SIP handoff — GPP stack constraints + peer steals (2026-09-12)

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Success criteria

- Keep the already-drafted stack / lock / exclude / report path (`stack_rules.py`, `lineup_report.py`, CLI `--stack` `--lock` `--exclude`). Do not revert it.
- Add four build flags, wired through `generate_lineups`, `optimize_lineups`, `ceminidfs optimize`, and `ceminidfs run` (config keys + CLI):
  1. `--no-offense-vs-dst` / `no_offense_vs_dst: true` — a lineup cannot include a DST/DEF and an offensive player from the opposing team.
  2. `--one-rb-per-team` / `one_rb_per_team: true` — at most one RB from any single team.
  3. `--projection-floor N` / `projection_floor` — remove pool players with FPPG below N (default off).
  4. `--uniques N` / `uniques` — set `max_repeating_players` to `slate_size - N` (FanDuel classic slate_size=9, showdown=6). If both `--uniques` and `--max-repeating-players` are set, `--uniques` wins.
- Implement constraints with pydfs groups / `remove_player` only. Clean-room. Do not copy files from chanzer0, nuke-dfs-hub, draftfast, or any no-LICENSE repo.
- Unit tests for the new flag parsers and at least one pydfs integration test (showdown lock already exists; add one for `--one-rb-per-team` or `--projection-floor` on the existing showdown fixture).
- `docs/GPP-WORKFLOW.md` documents the new flags in the stacks section.
- Existing stack/lock tests stay green.

## Verify

- `.venv/bin/python -m pytest tests/test_stack_rules.py tests/test_optimize_showdown.py tests/test_optimize_main_slate.py tests/test_gpp_profile.py -q`
- `.venv/bin/ruff check src/ceminidfs/export src/ceminidfs/cli.py src/ceminidfs/orchestrator/run.py tests/test_stack_rules.py tests/test_optimize_showdown.py`
- `.venv/bin/python -m pytest -q`

## NEVER

- Do not `pip install draftfast` or copy BenBrostoff/draftfast, chanzer0/NFL-DFS-Tools, or nukesim/nuke-dfs-hub source.
- Do not scrape FanDuel / DraftKings / FantasyPros / paid sites.
- Do not auto-enter contests or add Discord LIVE.
- Do not commit `data/slates/*.csv` or salary exports.
- Do not add the untracked federation skills under `.cursor/skills/`.
- Do not delete `.cursor/rules/cemini-route-outsource.mdc`.
- Do not change classic 9-slot FanDuel headers or showdown captain-mode site mapping.
- Do not vendor cbratkovics RF models or add Hugging Face downloads.
- Do not rewrite `## Verify`.
- No secrets, no `.env` flips, no prod scp.

## Plan

Operator wants weekend FanDuel GPP levers, not a new projection model. Stacks/lock/exclude/report are already in the working tree from 2026-09-12. Finish that path if anything is broken, then add four MIT/process constraints on pydfs.

### Keep (do not revert)

- `src/ceminidfs/export/stack_rules.py` — parse `qb:3`, `CIN:3`, `CIN3-TB2`, `3-2`, `game:5`, `wr:2`, `rb+dst`; lock/exclude by name.
- `src/ceminidfs/export/lineup_report.py` — badges + exposure + `*.report.txt`.
- CLI / orchestrator wiring for `stacks`, `locks`, `excludes`, `max_exposure`.
- Tests in `tests/test_stack_rules.py` and showdown lock/exclude test.

### Constraint 1 — no offense vs DST

Inspired by ashhhlynn (MIT) and chanzer0 `num_players_vs_def: 0` (process only).

After the player pool is loaded, for every DST/DEF/D player `d`:

- Find `opp = opponent_team(d)` from `game_info`.
- Collect offensive pool players on `opp` (QB/RB/WR/TE; not DST).
- For each such opponent player `o`, add a pydfs `PlayersGroup([d, o], max_from_group=1)` via `optimizer.add_players_group` (or `Stack`/`PlayersGroup` — use the API that is already imported in this pydfs version).

That is a pairwise mutex. Do not use one giant group of `{DST}+all opp` with `max_from_group=1` (that would also block two opposing skill players when DST is out).

Skip players with no `game_info` / empty opponent.

Flag default: off.

### Constraint 2 — one RB per team

For each team, `PlayersGroup(team_rbs, max_from_group=1)` if that team has 2+ RBs. Default off.

### Constraint 3 — projection floor

If `projection_floor` is set, `remove_player` everyone with `fppg < floor` who is not locked. Default off (None).

### Constraint 4 — uniques alias

`--uniques 3` on FanDuel classic → `max_repeating_players = 6`. Showdown 6-man → `max_repeating_players = 3`. Helper: `slate_size = len(LINEUP_HEADERS[site_key])`.

### Wiring

- `generate_lineups(..., no_offense_vs_dst=False, one_rb_per_team=False, projection_floor=None, uniques=None)`
- Store in orchestrator `_optimize_build_kwargs` from config.
- CLI `_add_optimizer_build_arguments`: `--no-offense-vs-dst`, `--one-rb-per-team`, `--projection-floor`, `--uniques`.
- Report header should list these flags when set.

### Tests

- Parser / helper unit tests (no pydfs): uniques math; skip empty opponent.
- Integration: showdown fixture + `--projection-floor 50` removes everyone (or a high floor that still leaves a legal pool — pick a floor that drops Patriots DST 8.4 but keeps stars). Safer: `--one-rb-per-team` and assert no lineup has two RBs from SEA.
- Keep existing 18 stack/showdown tests green.

### Docs

Append the four flags to `docs/GPP-WORKFLOW.md` stacks section. Do not rewrite PLAN.md history.

### Out of scope this run

cbratkovics RF, nuke Streamlit UI, chanzer0 Monte Carlo field, TheOddsAPI, Discord, wiki lint (briefs already staged).
