# SIP — CeminiDFS Parlays handoff CSV + README wallets + Recap live

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Success criteria

1. After lineup artifacts are written (`optimize`, `late-swap`, sim rerank) and on `ceminidfs review`, write `ceminidfs_handoff.csv` next to the lineup `--out` (or review `--out` dir).
2. Columns (csv.writer, not DictReader on lineup files): `player,team,projection,lineup_exposure_pct,game,implied_total`. `implied_total` may be blank. No FanDuel contest IDs. No salary.
3. `ceminidfs review` writes the handoff even when the three review flags are off.
4. Tests in `tests/test_review_reports.py` (or `tests/test_handoff.py`): 2 of 4 lineups with Chase → exposure `50.0`; header present; lineup files unchanged.
5. `docs/HANDOFF-PARLAYS.md`: DFS now **writes** this file. Parlays `--from-ceminidfs` is the other repo. Operator copies the file. CLIs stay split. Recap Desk is **live** in Grok Bot.app; it still does not write this repo.
6. `docs/GROK-BOTS.md` and `docs/SUNDAY.md` §7: Recap Desk is live. Do not create a second Bot. Still no repo write. Still no Enter.
7. README Support: remove the wallet address table and referral URLs. Keep project links + “wallets: SUPPORT.md”. Do not delete `SUPPORT.md`.
8. No secrets. No `src/` math retune.

## Verify

- `.venv/bin/python -m pytest tests/test_review_reports.py tests/test_fanduel_upload.py tests/test_late_swap.py -q`
- `grep -q "ceminidfs_handoff.csv" docs/HANDOFF-PARLAYS.md`
- `grep -q "live" docs/GROK-BOTS.md`
- `! grep -q "0x444C5C2eC439E0382aa5a17F70313c536BcC5D58" README.md`
- `grep -q "SUPPORT.md" README.md`
- `test -f SUPPORT.md`
- `.venv/bin/ruff check src/ceminidfs/export/review_reports.py src/ceminidfs/export/optimize.py src/ceminidfs/cli.py tests/test_review_reports.py`
- `.venv/bin/python -m pytest -q`

## NEVER

- Do not implement `--from-ceminidfs` here (that is CeminiParlays).
- Do not Enter FanDuel. Do not scrape. Do not retune FPPG.
- Do not commit salary CSVs, `.env`, or `reports/`.
- Do not delete SUPPORT.md wallets (move off README only).
- Do not rewrite `## Verify`.
- Do not commit.

## Plan

Reuse `parse_lineup_csv` + `load_player_index` in `src/ceminidfs/export/review_reports.py`. Add `write_parlays_handoff(path, lineups, players) -> Path` and call it from `maybe_write_review_reports` **even when all three flags are false** (change the early return: still write handoff). Also call it after `write_lineup_artifacts` in `optimize.py` / `late_swap.py` / `sim_rerank.py` using the same players CSV already on those functions.

Exposure = 100 * (lineups containing the player) / n_lineups, one decimal like leverage matrix.

Docs edits listed in Success. Keep BBM optional. Outlier Weekly stays a link only — do not invent an article URL.
