# Audit prompt — CeminiDFS — Week 4 result + build defects

Read only. Do not edit, create, or delete any file. Do not print secrets. Do not read `.env`.

WorkDir: `/Users/claudiobarone/Projects/CeminiDFS`

Keys, if a later run needs them (this audit does not):

- `OPENROUTER_API_KEY` and `DEEPSEEK_API_KEY` live in `~/.cemini/llm-routing.env`.
- Grok auth is `~/.grok/auth.json`. The route scripts inject `XAI_API_KEY`. Do not print it.
- Odds: `THE_ODDS_API_KEY` is in the gitignored OSINT workspace `.env`. This repo reads `ODDS_API_KEY` from the environment. Export it in the shell. Do not cat the file. Do not write the value into a file.

## Played result (2026-10-09)

FanDuel Main, 4 lineups, cash **−$6.95**. One lineup cashed (126.22). The book was built by hand. The optimizer did not submit it.

- L01 scored 116.00 with Case Keenum at 0.00. The Saturday lock left the Chicago quarterback cell open.
- L01/L02 share Henry, Lamb, Gesicki, Bengals. L03/L04 share Allen, Walker, Kincaid, Raiders.
- Kincaid 1.20 and Raiders 1.00 sat on both of the second pair.
- Allen scored 19.52, and 6.00 of that was a rushing touchdown. Palmer 0.80, Kincaid 1.20, Moore 2.20.
- Research excludes plus a snap filter removed so many names that the lineups had too little variance.

## Confirm these build defects are still in the code

Source: `briefs/2026-10-04_w04-build-postmortem.md`.

1. `orchestrator/run.py` defaults `canonical_csv` to the salary path. A later `--stages optimize` overwrites projections with FanDuel FPPG.
2. No role or snap gate. A zero-snap player with a market FPPG can enter. The interim "one touch in weeks 1–3" filter removed 218 of 531 rows.
3. `--count`, `--lock`, `--exclude`, and `--stack` disagree across `run` and `optimize`.
4. `merge-lineups` does not write the FanDuel upload file.
5. `duplicate_core_report`, `stack_fragility_report`, and `dart_ceiling_rank` did not fire on a shared core.
6. Late-swap kickoff set drops a 09:30 Sunday game.

## Rules the code must grow

1. An open quarterback cell cannot be rostered. If status says the starter is unassigned, that name stays out and the run warns.
2. A research exclude is a hard delete today (`data/research_locks.py`, `export/pool_guards.py`). Soft fade already exists and must not delete. Add a pool floor: if hard excludes shrink the eligible skill pool below a logged minimum, refuse the solve. Do not silently return three lineups that share one core.
3. The same tight end and the same defense appear on at most one lineup.
4. A quarterback plus three pass catchers from his team needs a target-share check. Rushing quarterback points must not count as stack correlation.
5. Say whether a bust band (P15) exists. If it does not, say so. Do not invent one in the audit.

## Files to read

- `briefs/2026-10-04_w04-build-postmortem.md`
- `src/ceminidfs/orchestrator/run.py`
- `src/ceminidfs/orchestrator/validate.py`
- `src/ceminidfs/export/pool_guards.py`
- `src/ceminidfs/export/stack_rules.py`
- `src/ceminidfs/export/optimize.py`
- `src/ceminidfs/data/research_locks.py`
- `src/ceminidfs/data/availability.py`
- `src/ceminidfs/pipeline/late_swap_oracle.py` (kickoff filter only)

## Return

A table only, then a numbered fix list. Max 120 lines.

| id | still present | file:line | current behavior | smallest fix | test |

Quote the line. If a defect is already fixed, say fixed and quote the guard. No rewrite of the repo.
