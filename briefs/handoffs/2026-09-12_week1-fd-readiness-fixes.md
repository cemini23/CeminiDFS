# SIP handoff — Week 1 FanDuel readiness P0+P1 fixes

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Success criteria

- Implement **every** item in the backlog below (P0 and P1). Do not skip “info” items that have a code/docs fix.
- Existing DFS tests stay green. Add tests named in each item.
- `docs/GPP-WORKFLOW.md` late-swap section matches the new behavior.
- No draftfast. No scrapers. No salary CSV commits. No contest submit.

## Verify

- `.venv/bin/python -m pytest tests/test_stack_rules.py tests/test_optimize_showdown.py tests/test_optimize_main_slate.py tests/test_gpp_profile.py tests/test_late_swap.py tests/test_weather.py tests/test_volume.py tests/test_salary.py tests/test_fetch.py tests/test_project_engine.py -q`
- `.venv/bin/ruff check src/ceminidfs/data/fetch.py src/ceminidfs/export/late_swap.py src/ceminidfs/export/sim_rerank.py src/ceminidfs/export/optimize.py src/ceminidfs/export/stack_rules.py src/ceminidfs/models/volume.py src/ceminidfs/orchestrator/run.py src/ceminidfs/cli.py tests/test_late_swap.py tests/test_stack_rules.py tests/test_volume.py tests/test_fetch.py`
- `.venv/bin/python -m pytest -q`

## NEVER

- Do not `pip install draftfast` or copy no-LICENSE DFS repos.
- Do not scrape FanDuel / DraftKings / paid sites.
- Do not commit `data/slates/*.csv`, `salaries/`, `research/`, or `.env`.
- Do not delete the operator’s FanDuel CSV; you may delete **parquet caches** under `artifacts/cache/` (gitignored).
- Do not add pick’em / Hard Rock / BBM changes.
- Do not rewrite `## Verify`.
- No secrets, no LIVE Discord, no prod scp, no federation skill dumps.

## Plan

Parent synthesis: `briefs/2026-09-12_week1-fd-readiness-super-audit.md`. Three returned auditors (Grok 4.6, Kimi3, GPT-SOL) plus parent file reads. Fusion/Hy3/Flash/OpenCode/Opus were SDR.

### Operator first (do this in code comments / docs; executor may delete gitignored parquet)

1. Delete `artifacts/cache/schedules_2026.parquet` and `artifacts/cache/2026/week_1/*.parquet` so the next fetch is live.
2. Do not point `run` at the 4 Sep / 133104 file unless the operator replaces it tonight.

### P0-1 — fetch cache TTL + `--force`

`src/ceminidfs/data/fetch.py` `_fetch_cached`: if cache exists and is older than 12 hours, refetch (or if `config["fetch"]["force"]` / CLI `--force`). Print a one-line warning when a cache is reused (`path`, mtime). Wire `--force` on `ceminidfs fetch` and `ceminidfs run`. Test: tmp parquet older than TTL is not returned.

### P0-2 / P0-3 / P0-4 — late-swap that cannot silently wreck GPP

`src/ceminidfs/export/late_swap.py` + CLI:

- Accept `stacks`, `locks`, `excludes`, `max_exposure`, `no_offense_vs_dst`, `one_rb_per_team`, `projection_floor`, `uniques` (same helpers as `generate_lineups`).
- `--exclude` / `--lock` on `late-swap`. After lineup parse, zero FPPG (or remove from *unlocked* pool only) for excludes. **Never** require the operator to drop OUT rows from the players CSV. If a locked-team player is excluded, keep the row so the imported lineup still parses.
- `_normalize_team` must call `normalize_team_abbr`. If a `--lock-team` matches 0 pool players, **warn** (do not only fail when *all* locks miss).
- Re-apply stack specs and pool constraints before `optimize_lineups`.
- Tests: (1) alias `JAC` locks `JAX`; (2) lineup still parses when that player is OUT and FPPG is 0; (3) exclude on an unlocked 4:25 name.

### P0-5 — final-portfolio exposure

In `rerank_lineups` (or a new helper), after score-sort, **greedily** take lineups that do not push any player above `max_exposure` of `final_count`. If `max_exposure` is None, keep current slice. Test with a tiny matrix where the top-N by score would exceed exposure.

### P0-6 — docs

Rewrite `docs/GPP-WORKFLOW.md` Late Swap: keep all original lineup names in the players file; zero FPPG for new OUTs; list 1 p.m. clubs with `JAX`/`WAS`/`LAR`; `--lock-team` once per 1 p.m. club; re-run project only as a *copy* that does not drop rows. Update examples to season 2026.

### P0-7 — stack pipe

`parse_stack_rules`: if a token contains `|`, split into multiple rules **or** raise `ValueError` that says use repeated `--stack`. Test both `qb:3|CIN3-TB2` behavior (prefer split — matches operator muscle memory from the audit pack).

### P0-8 — NaN vegas

`build_week_volume`: if `spread` or `total` is null/NaN, raise `ValueError` naming the game. `projected_pass_rate`: if `wind_mph` or spread adj would be NaN, treat adj as 0 (belt). Test a NaN spread row raises.

### P1-1 — validate players_csv

`orchestrator/run.py`: pass `players_csv=normalized_csv` into `validate_lineups_csv`. Test if one exists; else add a small unit test.

### P1-2 — projection coverage

After merge in `project`/`engine`, print count + up to 15 names with empty `fd_projection`. No fail (Week 1 rookies). Test the helper.

### P1-3 — Week-1 zero-projection starters

Do **not** invent a new ML model. Add a narrow escape: if a salary-row QB has 0 projected pass attempts and `injury_status` is empty, do not mark `is_qb_starter=False` solely because 2025 attempts are on another team — use current-team pass-attempt leader **or** the highest-salary QB on that team for week<=1. For RB, if committee override would zero the only RB with salary ≥ $7000 on that team in week<=1, keep a minimum share (e.g. 0.35). Tests with a synthetic new-team QB and a lone expensive RB.

### P1-4 — `--min-salary` on optimize/run

Wire through CLI / `_optimize_build_kwargs`. Default stays 59400 for FanDuel. Test the kwarg is passed.

### P1-5 / P1-6 — tests

Classic `qb:3` or `3-2` on the existing main-slate fixture: assert composition. Late-swap: two lineups, two lock teams, locked names unchanged.

### P1-7 — weather fetch resilience

In `_schedule_game_weather` / Open-Meteo call: catch network errors, leave weather columns empty, continue other games. Test with a raising opener.

### P1-8 — grok CSV

Add `src/ceminidfs/data/research_locks.py`: if a CSV has a name column plus a `lock`/`exclude`/`fade` column (case-insensitive), return two string lists. CLI `optimize`/`run` `--research-csv PATH` merges into locks/excludes. If columns are unknown, print headers and skip (no crash). Test with a tiny fixture. Do not scrape.

### P1-9 — seed

`config/nfl_dfs_gpp.yaml`: `simulate.seed: 20260913`. Honor it in `simulate.py` if not already.

### P1-10 / P1-11

Canonicalize D/DEF/DST in `normalize_join_key`. Normalize vegas home/away with `normalize_team_abbr` before pace lookup.

### P1-12

Replace `total_players` deprecation site if we call it; otherwise ignore vendor warn.

### P1-13

GPP-WORKFLOW season examples → 2026 (covered in P0-6).

### Out of scope

BBM, redraft, pick’em, Discord, committing slates, FanDuel submit.
