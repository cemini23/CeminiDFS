# SIP handoff — Week 1 FanDuel pipeline readiness (2026-09-11)

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Success criteria

- Week 1 (`season=2026`, `week=1`) DIY projections can use prior-season PBP, rosters, and usage/stats cutoffs. Empty 2026 PBP must not zero the model.
- FanDuel salary team codes `JAC` / `WSH` / `ARZ` / `LA` map to nflverse keys (`JAX` / `WAS` / `ARI` / `LAR`).
- Injury tokens `NA`, `IR`, `PUP`, `NFI`, `EXEMPT`, `COMMISSIONER EXEMPT`, and `SUSPENDED` exclude players. `Q` stays eligible.
- SoFi (LAC/LAR) is not weather-exposed. `build_week_weather_from_schedules` does not call Open-Meteo for LAC or LAR home games. Retractable HOU/IND stay exposed until a roof decision exists.
- Existing showdown path stays: `fanduel_showdown` / `draftkings_showdown` via pydfs captain mode. No draftfast.
- Tests and ruff in Verify pass. Classic 9-slot FanDuel path is unchanged.
- Docs: ROADMAP notes K175 extract-only (not a live feed) and Week 1 readiness. PLAN session handoff mentions prior-season history for week 1.
- `.gitignore` ignores `data/slates/` so FanDuel player-list CSVs stay local.

## Verify

```bash
cd /Users/claudiobarone/Projects/CeminiDFS
.venv/bin/python -m pytest tests/test_preseason_v2.py tests/test_stadiums.py tests/test_weather.py tests/test_usage.py tests/test_salary.py tests/test_pipeline.py tests/test_project_engine.py tests/test_pipeline_resilience.py tests/test_optimize_showdown.py tests/test_optimize_main_slate.py tests/test_fetch.py -q
.venv/bin/ruff check src/ceminidfs tests/test_preseason_v2.py tests/test_stadiums.py tests/test_weather.py tests/test_usage.py
.venv/bin/python -m pytest -q
```

## NEVER

- Do not `pip install draftfast` or copy BenBrostoff/draftfast.
- Do not scrape FanDuel/DraftKings or auto-enter contests.
- Do not commit `data/slates/*.csv` or any FanDuel/DK salary export.
- Do not add OSINT `scripts/install-hooks.sh` / `pre-commit.sh` / `post-commit.sh` (wrong repo).
- Do not add the 30 new untracked federation skills under `.cursor/skills/` (goal, free-audit, wayfinder, …). Leave them untracked.
- Do not delete `.cursor/rules/cemini-route-outsource.mdc` or `tipdrop-route-outsource.mdc`. Restore them if they are deleted in the working tree.
- Do not change classic `fanduel` / `draftkings` 9-slot headers.
- Do not use `Site.FANDUEL_SINGLE_GAME` for 2026 NFL showdown.
- Do not rewrite `## Verify`. Do not invent token-delta logs.
- No secrets, no LIVE Discord, no `.env` flips, no prod scp.

## Plan

Operator tomorrow: FanDuel Week 1 Sunday-afternoon lineups (contest 133104, 12 games, no SNF/MNF). K257 showdown is already on `main` (`8e034e8`, CI green). Remaining work is week-1 projection wiring that is already drafted in the working tree, plus three brief gaps.

### Already drafted (keep and finish — do not revert)

Working-tree edits exist. Review them. Keep the intent. Fix bugs and add tests.

1. `src/ceminidfs/data/fetch.py` — catch nflreadpy `Season must be between` and return empty. For `pbp` when `week <= 1`, concat prior season.
2. `src/ceminidfs/data/rosters.py` — same season-range catch. Week 1 empty roster falls back to last week of prior season.
3. `src/ceminidfs/models/usage.py` — `history_week_cutoff()` so week 1 uses prior-season max week + 1. Usage/QB helpers use that cutoff.
4. `src/ceminidfs/models/stats.py` — week 1 keeps prior-season PBP; defense and efficiency use `history_week_cutoff`.
5. `src/ceminidfs/pipeline/engine.py` — `_historical_pbp` keeps prior season on week 1; GSIS name/team alignment; `normalize_team_abbr` on join keys.
6. `src/ceminidfs/data/salary.py` + `stadiums.py` — `normalize_team_abbr` with `JAC`/`WSH`/`ARZ`/`LA`.

### Gap 1 — SoFi indoor (overlay brief)

`briefs/2026-09-01_fd-sun-w1-grok-overlay.md`: SoFi is indoor. Current `is_weather_exposed` is `roof_type != "dome"`, so LAC/LAR (`semi_open`) stay exposed.

Change `is_weather_exposed` to return True only for `open` and `retractable`. Keep `roof_type` as `semi_open` on LAC/LAR (honest canopy). Retractable stays exposed (HOU/IND).

Update `tests/test_stadiums.py`: SoFi `semi_open` is **not** weather-exposed. Add alias tests for `JAC`→JAX, `WSH`→WAS, `ARZ`→ARI.

Add a weather test like the DET dome test: home_team `LAC` (or `LAR`) must not call Open-Meteo and `weather_exposed` is False.

### Gap 2 — Exempt / NA / suspended

`availability.py` already adds `NA`. Also exclude `EXEMPT`, `COMMISSIONER EXEMPT`, and `SUSPENDED` (prefix-match `EXEMPT` and `SUSPENDED` in `normalize_injury_status`). Jacobs is IR on FanDuel 133104; this is defense in depth.

Extend `tests/test_preseason_v2.py` `test_is_unavailable_status` for `NA`, `Exempt`, `Commissioner Exempt`, `Suspended`. Keep `Q` eligible.

### Gap 3 — tests for week-1 history

Add focused unit tests (no network):

- `history_week_cutoff` on a two-season frame: week 1 season 2026 with 2025 weeks 1–18 returns 19; week 2 returns 2.
- `_historical_pbp` week 1 keeps prior-season rows and drops current-season week 1 if present.
- Team alias normalize in salary parse or stadiums tests.

Do not add live nflverse fetch tests.

### Docs

- `ROADMAP.md` Shipped tracks: K175 row — FiveThirtyEight tidy CSVs are extract-only backtest fixtures, not a live feed. Week 1 readiness row pointing at this handoff.
- `PLAN.md` Session handoff: week 1 uses prior-season PBP/rosters; SoFi indoor skip; operator still supplies a fresh Sunday-afternoon salary CSV.

### Hygiene (do not commit these)

Leave untracked: `data/slates/`, `scripts/install-hooks.sh`, `scripts/pre-commit.sh`, `scripts/post-commit.sh`, `briefs/handoffs/yt-frames/`, new `.cursor/skills/*` except existing tracked `route` + `super-audit`.

Add `data/slates/` to `.gitignore` next to `salaries/`.

Restore deleted `.cursor/rules/cemini-route-outsource.mdc` and `tipdrop-route-outsource.mdc` (`git checkout --` those two files).

You may keep the already-modified tracked `.cursor/skills/route/SKILL.md` (v2.4.3) and super-audit one-liners. Do not invent new skill files.

Do not git commit. Parent session commits and pushes after Verify.
