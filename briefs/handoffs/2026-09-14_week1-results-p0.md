# SIP handoff — Week 1 recap P0/P1 (FanDuel upload + Sunday process)

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Success criteria

- `ceminidfs optimize` and `ceminidfs run` write three lineup files next to `--out` / `lineups.csv`:
  1. name-only (existing) for human review
  2. `*_fanduel_upload.csv` with cells `Full Name (player.id)` e.g. `Josh Allen (133104-62239)`
  3. `*_fanduel_ids.csv` with ID-only cells e.g. `133104-62239`
- If `--out` is `lineups.csv`, the siblings must be named `lineups_fanduel_upload.csv` and `lineups_fanduel_ids.csv` (Week 1 operator names).
- Header stays `QB,RB,RB,WR,WR,WR,TE,FLEX,DEF` for FanDuel classic. Use `csv.reader` / `csv.writer` only. Do **not** use `csv.DictReader` on these files.
- `late-swap` loads name-only **or** `Name (ID)` **or** ID-only, and writes the same three formats.
- `lineups.report.txt` lists every rostered Q player (name + lineup count). Keep `with_injured=True`. Do **not** auto-exclude Q.
- `--max-team-exposure` exists (optional; default None = no cap). When set, final selection must not exceed it. Report warns when any team share is above the cap (or above 0.5 if the flag is unset).
- Report badge `CHALK-QB-WR-WR` when a lineup has QB + two WRs (not TE) from the same team. Informational. No hard ban.
- When lineup count is 20 or fewer, the report prints **all** lineups (not only the first 8).
- `docs/GPP-WORKFLOW.md` has an upload step: paste the ID file, never name-only; operator submits; agent does not Enter.
- Tests named below are green. Full `pytest -q` and `ruff check src tests` are green.

## Verify

- `.venv/bin/python -m pytest tests/test_optimize_main_slate.py tests/test_late_swap.py tests/test_gpp_profile.py tests/test_stack_rules.py tests/test_fanduel_upload.py -q`
- `.venv/bin/ruff check src/ceminidfs/export/optimize.py src/ceminidfs/export/late_swap.py src/ceminidfs/export/sim_rerank.py src/ceminidfs/export/lineup_report.py src/ceminidfs/orchestrator/run.py src/ceminidfs/cli.py tests/test_fanduel_upload.py tests/test_late_swap.py`
- `.venv/bin/python -m pytest -q`
- `.venv/bin/ruff check src tests`

## NEVER

- Do not set `with_injured=False` by default. Do not auto-drop Questionable players.
- Do not retune CIN / Chase / weather / stadium / DST numeric priors from Week 1.
- Do not `pip install draftfast` or copy no-LICENSE DFS code.
- Do not scrape FanDuel / DraftKings / paid sites.
- Do not commit `data/slates/*.csv`, `salaries/`, `research/`, `.env`, or `reports/`.
- Do not Enter, Submit, or late-swap on FanDuel.
- Do not rewrite `## Verify`.
- No secrets, no LIVE Discord, no federation skill dumps.

## Plan

Parent synthesis: `briefs/2026-09-14_week1-results-super-audit.md`. Recap: `briefs/2026-09-14_week1-fd-recap/`. Working ID sample: `runs/2026_week_1/lineups_fanduel_upload.csv` (gitignored; cells are `Name (133104-id)`).

Week 1 name-only `lineups.csv` failed FanDuel upload. `_lineup_row` in `src/ceminidfs/export/optimize.py` writes `player.full_name` only. pydfs players already expose `id` (`sim_rerank.lineup_player_ids`). Normalize already keeps FanDuel `Id`.

### P0-1 — FanDuel ID writers

In `optimize.py`:

- Add `cell_format` helper: `"name"` | `"name_id"` | `"id"`. `name_id` = `f"{full_name} ({player_id})"` when id is present; fail the write (raise `ValueError` naming the player) if FanDuel classic/showdown id is missing for a seat.
- Keep `_lineup_row(..., fmt="name")` as today so late-swap name files still work.
- Add `write_lineup_artifacts(lineups, out_path, site)` used by `optimize_lineups` and `optimize_with_sim_rerank`:
  - write name-only to `out_path`
  - write `name_id` to sibling: if stem is `lineups`, use `lineups_fanduel_upload.csv`; else `{stem}_fanduel_upload.csv`
  - write `id` to `lineups_fanduel_ids.csv` / `{stem}_fanduel_ids.csv`
- Record both extra paths in `orchestrator/run.py` manifest when present.
- Optional `--id-format` is **not** required if the three files always write. Prefer always write three files (simpler operator path).

Showdown: still write the three files with showdown headers. Use the same cell formats.

### P0-2 — late-swap round-trip

`late_swap.py`:

- `_normalize_name`: strip a trailing ` (id)` (regex `\s*\([^)]+\)\s*$`) before name match.
- Prefer exact `player.id` match when a cell is digits/`contest-id` or `Name (id)`.
- After rebuild, call the same `write_lineup_artifacts` so swapped output is upload-ready.
- `_load_simple_lineups` must keep using `csv.reader` (already positional). Add a test that `csv.DictReader` would collapse duplicate `RB` headers and that production does **not** use that result.

### P0-3 — Q block in the report

`lineup_report.py` + `keep_injury_tagged_players` / player injury attributes:

- After exposure tables, print `Questionable in book` with each Q name and how many lineups include them.
- If none, print `Questionable in book: none`.
- Do not change optimizer eligibility.

If injury tag is only on the source CSV, pass it through or read `Injury Indicator` from the players CSV when formatting the report. Keep the change small.

### P1-1 — `--max-team-exposure`

Wire CLI on `optimize` / `run` / `late-swap` (same `_add_optimizer_build_arguments`).

In `sim_rerank._select_with_exposure_cap` (and non-sim `generate_lineups` final set if there is no rerank): skip a candidate that would push any **team** above the cap. Player `--max-exposure` stays independent.

If the flag is unset, do not cap; still **warn** in the report when any team is in more than 50% of lineups (CHI 70% must warn on the Week 1 report shape).

### P1-2 — chalk badge

In `format_lineup_report` / stack badges: if a lineup has a QB and two WRs with the same team (TE does not count as the second WR), add `CHALK-QB-WR-WR`. Allen + Shakir + Kincaid (WR+TE) must **not** get this badge. Burrow + Chase + Higgins must.

### P1-3 — print all small books

`lineup_report.py` currently previews first 8. If `len(lineups) <= 20`, print every lineup.

### P1-4 — docs

`docs/GPP-WORKFLOW.md`: add **Upload** after optimize. Operator uploads `lineups_fanduel_upload.csv`. Agent does not Enter. Do not reuse last week’s contest IDs.

### Tests (`tests/test_fanduel_upload.py` plus extend existing)

1. Two FanDuel classic lineups from the synthetic slate: upload cells match `^.+ \(\S+\)$`; IDs exist in the source `Id` column; header has two `RB` columns that survive `csv.reader`.
2. `csv.DictReader` on the same header keeps only one `RB` (document the trap); production parser returns two RBs.
3. Late-swap: load `Josh Allen (fixture-id)` and ID-only; locked team unchanged; output upload file has ID cells.
4. Report: Q WR in 2 of 5 lineups → report contains that name and `2`.
5. Team cap 0.4 on a tiny constructed set: no team in more than 4 of 10 (or the equivalent small fixture).
6. Chalk badge unit: Burrow+two WRs yes; QB+WR+TE no.

### Out of scope

DST numeric rewrite, ownership softmax rewrite, weather/stadium auto-apply, `verify-entries` CLI, BBM, Discord, salary CSV commits, FanDuel submit.
