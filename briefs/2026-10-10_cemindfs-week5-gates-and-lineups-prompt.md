# CeminiDFS — apply the Week-4 gates, then build the Week-5 lineups

**Paste this whole file into a Grok Build session in `/Users/claudiobarone/Projects/CeminiDFS`.**

Two parts. **Part A** turns the Week-4 recap tool-gaps into review gates. **Part B** builds this week's lineups — the salary CSV is already at `data/slates/2026-10-11_fd_sun.csv`.

**If the Sunday clock is tight, run Part B first.** The slate outranks the tooling.

---

## Read first

- `CLAUDE.md`
- `docs/SUNDAY.md`, `docs/GPP-WORKFLOW.md`, `docs/REVIEW-REPORTS.md`
- **`src/ceminidfs/cli.py`** and **`src/ceminidfs/export/review_reports.py`** — the pattern every Part-A gate must follow
- The Week-4 tool-gaps: `briefs/2026-10-10_k288-dfs-repositories.md` (or the `tool-gaps.md` inside the Week-4 recap pack)

---

## Part A — apply the seven Week-4 tool-gaps

**Every row in the Week-4 recap carried `do_not_auto_apply = true`.** That was the recap desk's rule, not yours — the operator has now authorised these. **But they are still gates, not projection edits.**

**Implement each as a review flag → report CSV → operator reads**, exactly like the existing five (`--flag-wr-triples`, `--late-swap-audit`, `--ownership-fade-report`, `--flag-duplicate-cores`, `--dart-ceiling-report`).

> **Do not change a projection, the projection model, FPPG, CIN, Chase, or weather.** (SUNDAY rule 5.) A gate **reports**; it does not edit. If a gap can only be fixed by retuning a model, **stop and report it** — do not retune.

**Do them one at a time.** Implement a gate, add a test in `tests/`, run the suite, then move to the next.

| # | Gap | Flag to add | Report CSV | What it does |
|---|-----|-------------|------------|--------------|
| **A1** | TG01 injury | `--flag-qb-starter` | `qb_starter_report.csv` | Flag every rostered QB whose **starter status is not confirmed**, or whose projected snap share is **< 90%**, or where a **starter change was announced within 72h**. Week 4 rostered Case Keenum (0.00) while Bagent started. |
| **A2** | TG02 stack_rules | `--flag-stack-concentration` | `stack_concentration_report.csv` | Flag a QB+N stack whose non-QB partners are **low-share / low-aDOT**; show each partner's **prior-3-week target share** next to the stack. Week 4's four-man BUF stack scored 31.2 with 11.7 from the non-Allen catchers. |
| **A3** | TG03 ownership | `--flag-correlated-pairs` | `correlated_pair_report.csv` | Flag **identical TE+DST pairs** across lineups in one slate. Week 4 put Kincaid (1.2) and Raiders (1.0) on both lineups that used them. |
| **A4** | TG04 defense_multiplier | `--defense-context-report` | `defense_context_report.csv` | Show each DST's **opponent implied total**, **opponent sack%**, and **opponent TO%** beside the multiplier. Keep FR = opponent fumblesLost only. |
| **A5** | TG05 projection | `--projection-bands` | `projection_bands.csv` | Add **P85 (ceiling)** and **P15 (bust)** next to every projection. **Flag value plays whose P15 ≈ 0** (backup RB, WR4). Do not change the projection itself. |
| **A6** | TG06 weather | (extend the weather path) | existing weather report | Keep weather as a **pre-lock fade flag only**. **Do not post-hoc attribute a miss to weather** without a pass-rate delta. |
| **A7** | TG07 stadiums | (extend the weather report) | existing weather report | Add a **roof flag beside the game total** — informational only. **Do not auto-boost.** |

**After each gate:** add it to `docs/REVIEW-REPORTS.md` and the README flag table.

**If you run out of room:** finish the gate you are on, run the suite, and report which of A1–A7 remain. Do not leave a half-built flag in `cli.py`.

---

## Part B — this week's lineups

**Week 5. Slate: Sunday 2026-10-11.** The FanDuel salary CSV is already present: `data/slates/2026-10-11_fd_sun.csv`.

Follow `docs/SUNDAY.md` exactly. Substitute week 5 and this date.

```bash
# 1. Fresh fetch. Clear the week's cache first.
rm -rf artifacts/cache/2026/week_5
ceminidfs fetch --season 2026 --week 5 --force

# 2. Project and normalize.
ceminidfs run --season 2026 --week 5 \
  --salary data/slates/2026-10-11_fd_sun.csv \
  --stages fetch,project,normalize --profile gpp

# 3. THE PROBE — 25 lineups. Always before the full build.
ceminidfs optimize --csv runs/2026_week_5/normalized_players.csv \
  --out runs/2026_week_5/probe.csv --count 25 --min-salary 58500 \
  --research-csv config/2026-w05-sun-scratch.csv

# 4. Full GPP build with the review flags (add the new A-gates once implemented).
ceminidfs run --season 2026 --week 5 \
  --salary data/slates/2026-10-11_fd_sun.csv \
  --stages all --profile gpp --min-salary 58500 \
  --research-csv config/2026-w05-sun-scratch.csv \
  --flag-wr-triples --late-swap-audit --ownership-fade-report \
  --flag-duplicate-cores --dart-ceiling-report
```

**The scratch file** `config/2026-w05-sun-scratch.csv` is already there (91 rows, OUT/IR/status). **Questionable players stay in the pool.** Do not drop a `Q` player.

**Then:**

1. **Read every report.** Each one lists rows the operator may act on with `--exclude`, `--max-exposure`, or a later `late-swap`. **Report what each says, in plain language.**
2. **Build the late-swap lock-team list** from this week's nflverse file, per SUNDAY.md. Do not reuse last week's list.
3. **T-90 watch list** — name the players whose status must be confirmed near the 90-minute call.
4. **Write the handoff** the operator takes to FanDuel: the `lineups_fanduel_ids.csv`, the ID CSV, and the reports.

**Optional Jev HITL:** after the review CSVs exist, call `jev_verify` on **one** injury cell and `jev_find` on the late-swap rows. **Jev does not change projections.**

---

## Hard rules (never break)

- **The probe runs first.** 25 lineups before the full build. Always.
- **The agent does not Enter, Submit, or late-swap.** The operator submits every lineup.
- **Do not rely on the audit trail — the operator's word is not enough.** Name the command and the file for every number you report.
- **Questionable players stay.** A hard fade removes a player; a soft fade discounts a team. Only `out`/`ir`/`inactive`/`doubtful`/`nfi`/`pup`/`suspended` is a hard exclude.
- **Do not retune FPPG, CIN, Chase, or weather from one Sunday.**
- **If a command fails, read the named rows and fix the CSV. Do not guess on a money slate.**
- **Slate guard:** the salary CSV is the **Sunday-afternoon** slate. Do not import a Sunday-night or Monday game.

## Verify

1. `pytest` passes.
2. Each new gate produces its report CSV and appears in `docs/REVIEW-REPORTS.md`.
3. `runs/2026_week_5/probe.csv` holds 25 lineups **before** the full build.
4. `runs/2026_week_5/lineups_fanduel_ids.csv` exists and respects the player cap (0.35) and the team cap.
5. Every number you report names the file it came from.

## NEVER

- Never Enter, Submit, or late-swap.
- Never retune a projection model from one week.
- Never drop a `Q` player.
- Never reuse last week's salary CSV or contest IDs.
- Never sign FanDuel on a shared Bot VM.
- Never paste an API key.

## Report back

One message: which gates you implemented (A1–A7 status), the probe result, the full-build lineup count, what each report said, the T-90 list, and the exact paths of the handoff files. Stop there.
