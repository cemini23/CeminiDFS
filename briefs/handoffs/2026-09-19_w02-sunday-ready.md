# SIP handoff — Week 2 Sunday GPP readiness (Sat 19 Sep 2026)

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Success criteria

1. Tracked scratch file `config/2026-w02-sun-scratch.csv` exists. Headers include a name column plus `exclude`. No salary. No contest IDs. No lock rows.
2. Exclude names are the Sat hub scratch list, **full names only**:
   A.J. Brown, Tyler Smith, Isiah Pacheco, Audric Estime, Jayden Higgins, Alfred Collins, Cameron Williams, Michael Penix Jr., Cameron Jordan, Ja'Kobi Lane, Da'Shawn Hand, Sam Darnold, Nico Collins, Kyler Murray, Minkah Fitzpatrick, Omar Cooper Jr., Brock Bowers, Zay Flowers.
3. File does **not** exclude Q / warn names: Tua Tagovailoa, Michael Pittman Jr., Ladd McConkey, Joey Porter Jr., Josh Jacobs, Alvin Kamara.
4. `tests/test_research_locks.py` asserts `parse_research_locks` on that path returns those 18 excludes and zero locks.
5. `docs/SUNDAY.md` has a **Week 2 Sat card** (Sun 20 Sep 2026, 1 p.m. + 4 p.m. ET). It names: new FanDuel CSV (do not reuse Week 1); wipe `artifacts/cache/2026/week_2/` then `ceminidfs fetch --season 2026 --week 2`; `--research-csv config/2026-w02-sun-scratch.csv` on probe and full GPP; Q stay in pool; stacks as **hints** (not default `--stack`): WAS@DAL keep, CIN@HOU fade, Jefferson solo / no MIN stack, fade ATL pass, fade MIA@SF game stacks, fade PIT@NE; weather: MIN@CHI pass downgrade, GB@NYJ rain screen, SoFi `semi_open` not a wind fade, retractable roofs stay exposed until 90-min call; T-90: Pittman, Tua, McConkey, Porter Jr.; late-swap 1 p.m. lock-team list uses nflverse abbr.
6. Salary example paths use a **2026-09-20** (or `2026-w02`) filename, not the Week 1 `2026-09-13` contest file.
7. `docs/GPP-WORKFLOW.md` shows `--research-csv config/2026-w02-sun-scratch.csv` next to `--exclude`.
8. `docs/REVIEW-REPORTS.md` has a short Jev paragraph: `jev_verify` / `jev_find` on review CSV cells only. Jev does not change projections, pydfs, or ownership. No scrape. No Enter.
9. README Sunday GPP block mentions `--research-csv` and the Week 2 scratch file.
10. No `src/` edits unless a test import path requires one (prefer tests + docs + config only).

## Verify

- `test -f config/2026-w02-sun-scratch.csv`
- `.venv/bin/python -c "from pathlib import Path; from ceminidfs.data.research_locks import parse_research_locks; locks, ex = parse_research_locks('config/2026-w02-sun-scratch.csv'); assert locks == []; assert len(ex) == 18; assert 'Nico Collins' in ex; assert 'Kyler Murray' in ex; assert 'Tua Tagovailoa' not in ex"`
- `grep -q "2026-w02-sun-scratch.csv" docs/SUNDAY.md`
- `grep -q "research-csv" docs/SUNDAY.md`
- `grep -q "WAS@DAL" docs/SUNDAY.md`
- `grep -q "semi_open" docs/SUNDAY.md`
- `! grep -n "2026-09-13_fd_sun" docs/SUNDAY.md`
- `grep -q "research-csv" docs/GPP-WORKFLOW.md`
- `grep -q "jev_verify" docs/REVIEW-REPORTS.md`
- `grep -q "research-csv" README.md`
- `.venv/bin/python -m pytest tests/test_research_locks.py -q`
- `.venv/bin/ruff check src tests`
- `.venv/bin/python -m pytest -q`

## NEVER

- Do not retune FPPG, CIN, Chase, Higgins, or weather from Week 1.
- Do not add `--dst-audit`, `--weather-audit`, `--stadium-audit`.
- Do not default-on PlayersGroup `max_from_group`.
- Do not exclude Q names (Tua, Pittman, McConkey, Porter Jr.).
- Do not exclude Josh Jacobs (held exempt).
- Do not invent salaries or contest IDs. Do not commit `data/slates/`, `salaries/`, `.env`, `reports/`.
- Do not write files under gitignored `research/`.
- Do not call SoFi a dome.
- Do not scrape. Do not Enter / Submit / auto late-swap.
- Do not replace pydfs / sim / ownership with Jev.
- Do not edit the Gambling wiki.
- Do not rewrite `## Verify`.
- Do not commit.

## Plan

Canon: Gambling wiki `briefs/2026-w02-slate-hub-sun.md` (updated 2026-09-19) plus CeminiDFS `briefs/2026-09-19_w02-sat-prefetch.md`. Week 1 TG01–TG07 stay reports-only (`briefs/2026-09-15_gemini-dfs-improve.md`). K265/K266/Jev stay on the review CSV, not the solver.

### 1. Scratch CSV (`config/2026-w02-sun-scratch.csv`)

Use headers `name,team,status,exclude,lock,note`. Set `exclude=1` and `lock=` empty on every row. One row per scratch name (18). Status tokens: IR / OUT / D. Notes may be short (HOU fade, Wentz starts, treat out). No salary column.

### 2. Test

Add `test_week2_scratch_csv_is_exclude_only` in `tests/test_research_locks.py`. Load the committed path from the repo root (`Path(__file__).resolve().parents[1] / "config" / "2026-w02-sun-scratch.csv"`). Assert 18 excludes, 0 locks, and the four Q names are absent.

### 3. `docs/SUNDAY.md`

Keep the 20-minute clock. Insert a **Week 2 Sat card** after the Sunday GPP rules block (before §0 Install), or as a short §1b after the salary-export step.

Must include copy-paste:

```bash
# after operator exports THIS week's FanDuel Sunday-afternoon CSV
rm -rf artifacts/cache/2026/week_2
ceminidfs fetch --season 2026 --week 2 --force

ceminidfs run --season 2026 --week 2 \
  --salary data/slates/2026-09-20_fd_sun.csv \
  --stages fetch,project,normalize --profile gpp

ceminidfs optimize --csv runs/2026_week_2/normalized_players.csv \
  --out runs/2026_week_2/probe.csv --count 25 --min-salary 58500 \
  --research-csv config/2026-w02-sun-scratch.csv

ceminidfs run --season 2026 --week 2 \
  --salary data/slates/2026-09-20_fd_sun.csv \
  --stages all --profile gpp --min-salary 58500 \
  --research-csv config/2026-w02-sun-scratch.csv \
  --flag-wr-triples --late-swap-audit --ownership-fade-report
```

Replace every `2026-09-13_fd_sun.csv` example in this file with `2026-09-20_fd_sun.csv`.

Late-swap 1 p.m. ET lock teams (nflverse): `--lock-team CAR --lock-team ATL --lock-team NO --lock-team BAL --lock-team MIN --lock-team CHI --lock-team CIN --lock-team HOU --lock-team PIT --lock-team NE --lock-team GB --lock-team NYJ --lock-team CLE --lock-team TB --lock-team PHI --lock-team TEN`.

State: operator exports the CSV; agent does not Enter; do not lock WAS@DAL stacks in Python (hint only).

### 4. `docs/GPP-WORKFLOW.md`

Add `--research-csv config/2026-w02-sun-scratch.csv` to the stacks/locks/fades example. One sentence: Q stay in the pool; scratch file is OUT/IR/D only.

### 5. `docs/REVIEW-REPORTS.md`

After Human gate, add **Jev (optional)**: confirm jev MCP is on; pick one review-CSV injury/news cell; `jev_verify` claim = player + status, evidence = that string; keep or drop the row in HITL. `jev_find` may rank late-swap notes. Do not change the projection engine.

### 6. README

In the Sunday GPP block, one line: Week 2 scratch = `--research-csv config/2026-w02-sun-scratch.csv`.
