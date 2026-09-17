# SIP handoff — Sunday GPP docs (free-audit SHIP-WITH-FIXES)

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Success criteria

Docs/SOP only. Close the unpublished Sunday contract. Do not add optimizer features.

1. `docs/SUNDAY.md` exists: clock-order Sunday GPP (Parlays `SUNDAY.md` **shape** only). Fetch → project/run `--profile gpp` → review flags → upload ID CSV → operator submits → optional late-swap. Agent does not Enter. Three flags named. Point at `GPP-WORKFLOW.md` and `REVIEW-REPORTS.md`.
2. README has a **Sunday GPP** block **above** Status / phase table. Links `docs/SUNDAY.md`, `docs/GPP-WORKFLOW.md`, `docs/REVIEW-REPORTS.md`. Names `--flag-wr-triples`, `--late-swap-audit`, `--ownership-fade-report`.
3. README names the user: self-directed FanDuel GPP operator who exports a salary CSV and runs Python.
4. README has **What is NOT included**: no salary CSVs in git, no contest IDs as product, no `.env`, agent does not Enter / Submit / late-swap.
5. README Quick start and Common invocations use **2026** week examples (keep 2024 only on historical/backtest commands).
6. README command table includes `ceminidfs review`.
7. README intro stays GEO-plain: FanDuel-primary, nflverse, pydfs, MIT, operator submits. No `llms.txt`. No shop NAP. No new product site.
8. `docs/HANDOFF-PARLAYS.md` exists: which CSVs CeminiParlays may read (projection / ITT / weather artifacts). `--from-ceminidfs` is **specified, not built**. CLIs stay split.
9. `docs/REFUSED.md` exists: draftfast, scrapers, Enter, SoFi-as-dome, n=1 CIN/Chase retune, default-on PlayersGroup, `--dst-audit` / `--weather-audit` / `--stadium-audit`.
10. `CONTRIBUTING.md` exists: HITL Enter, no draftfast, no scrapers, no secrets, MIT.
11. `docs/GEO-PROBE.md` exists: 3–5 paraphrase queries, 2 engines, Ds vs Cs columns. **No invented GSC/citation numbers.**
12. README Related links `docs/SUNDAY.md`, `docs/HANDOFF-PARLAYS.md`, `docs/REFUSED.md`, `CONTRIBUTING.md`.
13. BBM stays optional (not the homepage product). Do not merge parlays math.
14. Leave `SUPPORT.md` wallets on README Support (do not move this wave).
15. No `src/` or `tests/` edits.

## Verify

- `test -f docs/SUNDAY.md && test -f docs/HANDOFF-PARLAYS.md && test -f docs/REFUSED.md && test -f CONTRIBUTING.md && test -f docs/GEO-PROBE.md`
- `grep -q "Sunday GPP" README.md`
- `grep -q -- "--flag-wr-triples" README.md`
- `grep -q "ceminidfs review" README.md`
- `grep -q "2026 --week" README.md`
- `grep -q "does not Enter" README.md`
- `grep -q "HANDOFF-PARLAYS" README.md`
- `! grep -R --include='*.md' -n "llms.txt" README.md docs/SUNDAY.md docs/HANDOFF-PARLAYS.md docs/REFUSED.md docs/GEO-PROBE.md CONTRIBUTING.md`
- `test -z "$(git diff --name-only -- src tests)"`
- `.venv/bin/ruff check src tests`
- `.venv/bin/python -m pytest -q`

## NEVER

- Do not edit `src/` or `tests/`.
- Do not implement `--from-ceminidfs`.
- Do not make Recap Desk write the repo.
- Do not add `--dst-audit`, `--weather-audit`, `--stadium-audit`.
- Do not retune FPPG / CIN / Chase / weather from Week 1.
- Do not call SoFi a dome.
- Do not vendor draftfast. Do not scrape. Do not Enter FanDuel.
- Do not add `llms.txt`. Do not invent a product site. Do not invent GEO citation scores.
- Do not edit the Gambling wiki (other repo).
- Do not commit salary CSVs, `.env`, or `reports/`.
- Do not rewrite `## Verify`.
- Do not commit.

## Plan

Canon: `reports/audit/free-ceminidfs-growth/SYNTHESIS.md` (SHIP-WITH-FIXES). Operator agreed set: items 1–2, 4–5 of Recommended fix order, plus REFUSED + CONTRIBUTING + GEO probe **template**. Default on `--from-ceminidfs`: document-first.

### README (`README.md`)

Keep badges and one-sentence identity. Rewrite the first paragraph so a retrieval engine can quote: DIY NFL DFS projections, FanDuel-primary, nflverse + Vegas + weather, pydfs, MIT, operator submits lineups.

Insert **Sunday GPP** immediately after the first paragraph (before Status):

- Who: self-directed FanDuel GPP operator with a salary CSV and Python.
- Clock: `docs/SUNDAY.md` (20-minute path).
- Detail: `docs/GPP-WORKFLOW.md`, `docs/REVIEW-REPORTS.md`.
- Flags (default off): `--flag-wr-triples` → `stack_fragility_report.csv`; `--late-swap-audit` → `late_swap_alert_report.csv`; `--ownership-fade-report` → `leverage_fade_matrix.csv`. Operator reads, then may `--exclude` / `--max-exposure` / `late-swap`. Agent does not Enter.

Add **What is NOT included** (short list).

Quick start live commands: `--season 2026 --week 2` (or week 1) for fetch/run. Historical/backtest blocks stay 2024.

Add `ceminidfs review` to the command table.

Related: SUNDAY, HANDOFF-PARLAYS, REFUSED, CONTRIBUTING. Keep SUPPORT wallets.

Do not promote BBM above Sunday GPP.

### `docs/SUNDAY.md`

Steal clock-order from CeminiParlays `docs/SUNDAY.md`. Do not copy parlays commands.

Suggested steps:

0. Install once (`pip install -e ".[dev,data,optimize]"`).
1. Export this week’s FanDuel player-list CSV (not last week’s contest IDs).
2. `ceminidfs fetch --season 2026 --week N --force`
3. Probe then GPP `run` / `optimize` with `--profile gpp` (cite the 25-lineup probe; do not default 2000 candidates).
4. Review: `--flag-wr-triples --late-swap-audit --ownership-fade-report` or `ceminidfs review`.
5. Upload `*_fanduel_upload.csv`. Operator submits. Agent does not Enter.
6. Optional late-swap after 1 p.m. ET lock (`JAX`/`WAS`/`LAR`).
7. After slate: Recap Desk paste (`docs/GROK-BOTS.md`). Recap does not write the repo.

Q stays in pool. Do not retune from one Sunday. SoFi is `semi_open`. KEEP/REJECT: `briefs/2026-09-15_gemini-dfs-improve.md`.

### `docs/HANDOFF-PARLAYS.md`

CeminiDFS and CeminiParlays stay two CLIs.

Parlays **may** read (operator copy, no live pipe):

- canonical / project CSV (player, team, projection)
- implied team totals / Vegas columns if present
- weather / stadium fields if present

Parlays must **not** read: salary CSVs committed, `.env`, FanDuel contest IDs, lineup upload files as a product.

`--from-ceminidfs` is specified for a later CeminiParlays change. Do not implement it here.

### `docs/REFUSED.md`

Table: reject + why + what we use instead. Cover draftfast, scrapers, Enter, SoFi dome, n=1 retune, default-on PlayersGroup, new DST/weather/stadium audit flags, `llms.txt` as a Google tactic.

### `CONTRIBUTING.md`

PRs must not: add draftfast, scrapers, site passwords, Enter/Submit, commit salary CSVs / `.env`. Tests: `pytest` + `ruff`. Point at REFUSED + GPP-WORKFLOW.

### `docs/GEO-PROBE.md`

Protocol only. Queries such as: “DIY NFL DFS projections nflverse pydfs”, “FanDuel GPP lineup optimizer MIT”, “CeminiDFS Sunday GPP”. Engines: 2 (e.g. Google + one AI answer engine). Columns: query, engine, Ds (retrieved URL y/n), Cs (cited y/n), date, notes. Leave result cells blank or `NO_EVIDENCE`. Do not invent scores.

### Out of scope

`--from-ceminidfs` code, Recap git write, Gambling wiki edits, SUPPORT wallet move, CI regression job, BBM homepage merge, NotebookLM, maths-compendium on Sunday.
