# SIP handoff — K257 CeminiDFS showdown optimizer

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Success criteria

- `ceminidfs optimize --site fanduel_showdown` and `--site draftkings_showdown` (aliases `fd_showdown`, `dk_captain`, `dk_showdown`) generate 6-man single-game lineups via **pydfs-lineup-optimizer**, not draftfast.
- FanDuel 2026 NFL showdown: 1 MVP + 5 FLEX, $60,000, MVP 1.5x salary and 1.5x points, DST allowed, max 5 from one team. Do **not** use pydfs `Site.FANDUEL_SINGLE_GAME` (that is the old 1 MVP + 4 UTIL, no DST).
- DraftKings captain: 1 CPT + 5 FLEX, $50,000, use `Site.DRAFTKINGS_CAPTAIN_MODE` unchanged except CeminiDFS wrappers.
- Classic `fanduel` / `draftkings` 9-slot main-slate path is unchanged.
- No `draftfast` dependency, clone, or copied source. Contest rules only.
- Tests pass for showdown + existing `tests/test_optimize_main_slate.py`.

## Verify

```bash
cd /Users/claudiobarone/Projects/CeminiDFS
.venv/bin/python -m pytest tests/test_optimize_showdown.py tests/test_optimize_main_slate.py tests/test_validate.py -q
.venv/bin/ruff check src/ceminidfs/export/optimize.py src/ceminidfs/export/normalize.py src/ceminidfs/orchestrator/validate.py src/ceminidfs/cli.py tests/test_optimize_showdown.py
```

## NEVER

- Do not `pip install draftfast` or copy files from BenBrostoff/draftfast (no LICENSE).
- Do not scrape FanDuel/DraftKings or auto-enter contests.
- Do not change classic 9-slot LINEUP_HEADERS for `fanduel` / `draftkings`.
- Do not use `Site.FANDUEL_SINGLE_GAME` for 2026 NFL (wrong roster: 5 slots, no DST).
- No secrets, no LIVE Discord, no `.env` flips.

## Plan

Operational steal is already proven in `scripts/kickoff_showdown_2026.py` (`optimize()`): pydfs `Site.DRAFTKINGS_CAPTAIN_MODE` with `settings.budget = 60000` and `max_from_one_team = 5` for FanDuel 2026 6-man MVP. Lift that into the library. Keep the one-off kickoff script working.

### 1. Site keys — `src/ceminidfs/export/normalize.py`

Extend `SITE_ALIASES` / `SITE_KEYS` / `SITE_FIELDS`:

| alias | canonical |
|-------|-----------|
| fd_showdown, fanduel_showdown, fd_single | fanduel_showdown |
| dk_showdown, dk_captain, draftkings_showdown, draftkings_captain | draftkings_showdown |

`normalize_site()` must accept these.

**fanduel_showdown normalize:** emit a **DraftKings captain-mode CSV** (same columns as kickoff `write_optimizer_csv`): for each eligible player, two rows sharing one `ID`:

- `Roster Position=CPT`, `Salary=round(flex * 1.5)`, `AvgPointsPerGame=base FPPG` (pydfs CPT importer multiplies FPPG by 1.5 when Roster Position is CPT)
- `Roster Position=FLEX`, `Salary=flex`, `AvgPointsPerGame=base FPPG`

FLEX salary is the 1x lobby salary (`Salary`, `SalaryFlex`, or `fd_salary`). DST/DEF → `DST`. Skip injured via `is_unavailable_status`.

**draftkings_showdown normalize:** same two-row CPT/FLEX emission. If the input already has `Roster Position` CPT/FLEX rows, pass through without doubling.

Helper `_emit_captain_rows(...)` shared by both showdown sites.

### 2. Optimizer — `src/ceminidfs/export/optimize.py`

- Add `SHOWDOWN_SITES = {"fanduel_showdown", "draftkings_showdown"}`.
- `LINEUP_HEADERS["fanduel_showdown"] = ["MVP", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"]`
- `LINEUP_HEADERS["draftkings_showdown"] = ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"]`
- `_site_enum`: showdown sites both use `Site.DRAFTKINGS_CAPTAIN_MODE`.
- After `get_optimizer`, if `fanduel_showdown`: `optimizer.settings.budget = 60000` and `optimizer.settings.max_from_one_team = 5`.
- `DEFAULT_MIN_SALARY`: fanduel_showdown 56000, draftkings_showdown 45000 (match kickoff / typical DK).
- `_lineup_row`: CPT maps to MVP when header is MVP. pydfs lineup_position is `CPT` or `FLEX`.
- CLI `--site` choices include the new aliases.
- `_relax_tiny_slate_limits`: for showdown, always allow full team (max_from_one_team already 5). Do not apply classic FD 9-slot tiny-slate logic incorrectly.

Classic `generate_lineups` path stays default for `fanduel`/`draftkings`.

### 3. Validate — `src/ceminidfs/orchestrator/validate.py`

- `SALARY_CAPS`: fanduel_showdown 60000, draftkings_showdown 50000.
- Use `LINEUP_HEADERS[site_key]` (already imported).
- Duplicate-player check: unique **names** in a lineup (CPT and FLEX of the same person must not both appear — pydfs should prevent this; assert it).
- Salary lookup for showdown: if `players_csv` has CPT/FLEX rows, sum the **row salary for the roster slot**. If only FLEX salaries exist, MVP/CPT slot costs `round(flex * 1.5)`. If `players_csv` is omitted, skip salary cap (same as today).

### 4. CLI — `src/ceminidfs/cli.py`

`--site` on `normalize` and `optimize` already takes a string. No enum lock besides optimize.py argparse. If optimize.py main is used, update choices. CLI `optimize` uses `runtime_config(site=args.site)` then `_run_optimize` — pass site through (already `config.get("site")`). Confirm `runtime_config` does not coerce unknown sites to fanduel.

### 5. Tests — `tests/test_optimize_showdown.py`

- Skip if pydfs missing (`pytest.importorskip`).
- Tiny two-team synthetic CSV (8–12 players, DST included, salaries that can fill $60k / $50k).
- `normalize_csv` + `generate_lineups` for both showdown sites, `count=2`.
- Assert 6 names per lineup, header length 6, first slot MVP or CPT, no duplicate names, salary <= cap when validated.
- Assert classic `fanduel` headers still 9 columns (import LINEUP_HEADERS).
- Optional: `ruff` clean.

### 6. Docs

Add 8–12 lines to `PLAN.md` Build vs borrow: pydfs captain-mode for 2026 FD/DK showdown; draftfast remains no-install (no LICENSE). Point at `scripts/kickoff_showdown_2026.py` as the first live user of the same rules.

Do not rewrite the kickoff script unless a one-line comment that library path now exists.

## Context (do not copy code from draftfast)

pydfs already exposes `Site.DRAFTKINGS_CAPTAIN_MODE` and `Site.FANDUEL_SINGLE_GAME`. 2026 FanDuel NFL single-game is **not** FANDUEL_SINGLE_GAME (1+4, no DST). Use DK captain + $60k as in `scripts/kickoff_showdown_2026.py` lines 395–421.

K257 OSINT: Extract draftfast showdown RuleSets; gh SPDX null; CONDITIONAL-GO. Clean-room = contest rules in CeminiDFS wrappers only.
