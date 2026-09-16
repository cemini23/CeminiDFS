# SIP handoff — Week 2 review reports (Gemini extract, three flags)

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Success criteria

Ship **three human-gate CSV reports**. Do not retune projections. Do not default-on PlayersGroup caps. Do not Enter FanDuel.

1. `--flag-wr-triples` writes `stack_fragility_report.csv` next to the lineup `--out` file.
2. `--late-swap-audit` writes `late_swap_alert_report.csv` next to `--out`.
3. `--ownership-fade-report` writes `leverage_fade_matrix.csv` next to `--out`.
4. Flags default **off**. Reports are empty-header files with 0 data rows when nothing matches (still write the header).
5. `ceminidfs review` reads existing `lineups.csv` + players CSV and can emit the same three files without re-solving.
6. `optimize` / `run` / `late-swap` honor the same flags after they write lineups.
7. Tests in `tests/test_review_reports.py` cover the cases below. Full `pytest -q` and `ruff check src tests` pass.
8. `docs/GPP-WORKFLOW.md` has a **Review reports** section: operator reads CSVs, then may `--exclude` / `--max-exposure` / `late-swap`. Agent does not Enter.

## Verify

- `.venv/bin/python -m pytest tests/test_review_reports.py tests/test_fanduel_upload.py tests/test_late_swap.py tests/test_gpp_profile.py tests/test_stack_rules.py -q`
- `.venv/bin/ruff check src/ceminidfs/export/review_reports.py src/ceminidfs/export/optimize.py src/ceminidfs/export/late_swap.py src/ceminidfs/cli.py src/ceminidfs/orchestrator/run.py tests/test_review_reports.py`
- `.venv/bin/python -m pytest -q`
- `.venv/bin/ruff check src tests`

## NEVER

- Do not change FPPG / projection numbers. No isotonic write-back onto projections.
- Do not default-on PlayersGroup `max_from_group`. Opt-in only remains a later operator step, not this patch.
- Do not add `--dst-audit`, `--weather-audit`, or `--stadium-audit`.
- Do not call SoFi a dome. Do not change `stadiums.py` roof enum.
- Do not vendor draftfast. Do not scrape ownership. Do not Enter FanDuel.
- Do not auto-drop Q players. Do not auto-swap.
- Do not commit salary CSVs, `.env`, or `reports/`.
- Do not rewrite `## Verify`.

## Plan

Canon: `briefs/2026-09-15_gemini-dfs-improve.md`. Week 1 gaps: `briefs/2026-09-14_week1-fd-recap/tool-gaps.md`. Existing badge: `CHALK-QB-WR-WR` in `lineup_report.py`.

Add `src/ceminidfs/export/review_reports.py` with three writers. Use `csv.writer` only (duplicate `RB`/`WR` headers must not use `DictReader` on lineup files). Parse lineups with `csv.reader` + `LINEUP_HEADERS`.

### WR triples (`stack_fragility_report.csv`)

A row when a lineup has **3+ WRs from the same NFL game** (both teams in that game) **or** already has badge `CHALK-QB-WR-WR` (QB + two same-team WRs).

Columns: `lineup_index,game,wr_names,wr_count,chalk_qb_wr_wr,note`

`game` is `AWAY@HOME` when known from `game_info` / players CSV Game column; else blank. `do_not_auto_apply` is process: print a one-line path, do not change lineups.

### Late-swap audit (`late_swap_alert_report.csv`)

Rostered players who are Q or D (Doubtful). Keep Q in the optimizer pool.

Columns: `player,injury,lineup_count,teams,kickoff_hint`

`kickoff_hint` may be the Game / time string from the players CSV if present; else blank. Never call `late_swap_lineups` from this writer.

### Ownership fade (`leverage_fade_matrix.csv`)

Need a name → projected ownership % map. Load from the players / normalized CSV (`Projected Ownership` or similar). If missing, run `project_ownership` on those rows **in memory only**.

Columns: `player,lineup_exposure_pct,projected_own_pct,leverage,flag`

`leverage = lineup_exposure_pct - projected_own_pct`. Flag `NEGATIVE_LEVERAGE` when `projected_own_pct >= 20` and `lineup_exposure_pct >= projected_own_pct`. Do not exclude players.

If a paid calibration JSON exists and is passed as optional `--ownership-calibration`, you may use it to scale **report** own% only. Never write FPPG.

### CLI

- Add `--flag-wr-triples`, `--late-swap-audit`, `--ownership-fade-report` to `_add_optimizer_build_arguments` (or a new `_add_review_report_arguments` used by optimize, run, late-swap, and review).
- `ceminidfs review --lineups PATH --players PATH --out DIR` writes selected CSVs into `--out` (default: lineup parent dir).
- After `write_lineup_artifacts`, if any flag is set, call the matching writer.

### Tests (`tests/test_review_reports.py`)

1. Synthetic lineup with Burrow + Chase + Higgins → one fragility row, `chalk_qb_wr_wr=Y`.
2. Allen + Shakir + Kincaid (WR+TE) → no chalk row from WR+TE alone.
3. Three WRs from the same game (two teams) → one row, `wr_count=3`.
4. Q WR in 2 of 5 lineups → late-swap audit lists that name and `2`. Lineup files unchanged.
5. Player at 50% exposure and 25% own → `NEGATIVE_LEVERAGE`. Player at 10% exposure and 25% own → no flag.
6. CLI help lists the three flags. Review command writes files without calling `optimize_lineups` (assert via `unittest.mock` or by using a name-only lineup file and no pydfs solve).

### Docs

`docs/GPP-WORKFLOW.md`: **Review reports** after Upload. Three flags, three filenames, human gate, `do_not_auto_apply`. Point at `briefs/2026-09-15_gemini-dfs-improve.md` for KEEP/REJECT.

### Out of scope

DST/weather/stadium audits, SoFi roof change, projection haircuts, scrapers, FanDuel submit, BBM.
