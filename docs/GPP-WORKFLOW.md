# GPP Workflow

Use the GPP profile when building tournament lineups where ceiling, correlation,
and ownership leverage matter more than conservative median projections.

## Run With The GPP Profile

The base `config/nfl_dfs.yaml` stays conservative for research and backtests:
simulation, simulation rerank, and ownership projection are disabled by default.

For tournament builds, pass `--profile gpp`:

```bash
ceminidfs project --season 2026 --week 1 --salary slate.csv --profile gpp
ceminidfs optimize --csv normalized_players.csv --out lineups.csv --profile gpp
ceminidfs run --season 2026 --week 1 --salary slate.csv --stages all --profile gpp
```

## Stacks, locks, and fades

`optimize` and `run` accept the same build flags. The optimizer writes
`lineups.report.txt` next to the CSV (stack badges + exposure).

```bash
ceminidfs optimize --csv normalized_players.csv --out lineups.csv --profile gpp \
  --stack qb:3 \
  --stack CIN3-TB2 \
  --lock "Ja'Marr Chase" \
  --exclude "Alvin Kamara" \
  --max-exposure 0.35
```

Stack text:

- `qb:3` — QB plus two WR/TE teammates
- `CIN:3` — three players from one team
- `CIN3-TB2` — 3/2 game stack
- `3-2` — any game, five players, at least two from each side
- `game:5` — any game, five players
- `wr:2` — two same-team WRs
- `rb+dst` — RB and DST from the same team

FanDuel classic allows at most four from one team. Do not use `CIN:5`.
Do not combine `qb:3`, `CIN3-TB2`, and `3-2` on one build. That set is often infeasible.
Operator still exports the CSV and submits. Agent does not Enter.

Optional build constraints (default off):

```bash
ceminidfs optimize --csv normalized_players.csv --out lineups.csv --profile gpp \
  --no-offense-vs-dst \
  --one-rb-per-team \
  --projection-floor 8 \
  --uniques 3
```

- `--no-offense-vs-dst` — a lineup cannot include a DST and an offensive player from the opposing team
- `--one-rb-per-team` — at most one RB from any single team
- `--projection-floor N` — remove unlocked pool players with FPPG below N
- `--uniques N` — set `max_repeating_players` to slate size minus N (FanDuel classic 9, showdown 6). If both `--uniques` and `--max-repeating-players` are set, `--uniques` wins.

Config keys on `ceminidfs run`: `no_offense_vs_dst`, `one_rb_per_team`, `projection_floor`, `uniques`.

Optional `--max-team-exposure 0.4` caps how many lineups may include any one team.
If the flag is unset, the report still warns when a team is in more than 50% of lineups.

The profile deep-merges `config/nfl_dfs_gpp.yaml` over the base config and enables:

- `simulate.enabled: true` with the `copula` method.
- `sim_rerank.enabled: true` with 500 candidates, 150 final lineups, and p85 scoring.
- `ownership.enabled: true` with heuristic ownership unless a calibration path is supplied.

## Upload

`optimize` and `late-swap` write three files next to `--out` (example: `lineups.csv`):

1. `lineups.csv` — name-only, for human review. Do **not** paste this into FanDuel.
2. `lineups_fanduel_upload.csv` — cells are `Full Name (id)`, e.g. `Josh Allen (133104-62239)`.
3. `lineups_fanduel_ids.csv` — ID-only cells, e.g. `133104-62239`.

**Upload** `lineups_fanduel_upload.csv` (or paste the ID file). Never upload name-only `lineups.csv`.

Operator pastes the ID file and submits. Agent does not Enter.

Do not reuse last week’s contest IDs. Use this week’s FanDuel player-list export.

## Review reports

Human gate. Flags default off. `do_not_auto_apply`. Agent does not Enter.

After Upload (or from an existing `lineups.csv`), opt in to three diagnostic CSVs.
The files sit next to the lineup `--out` file, or in `ceminidfs review --out DIR`
(default: lineup parent dir). Empty match still writes the header and 0 data rows.

```bash
ceminidfs optimize --csv normalized_players.csv --out lineups.csv --profile gpp \
  --flag-wr-triples --late-swap-audit --ownership-fade-report

ceminidfs review --lineups lineups.csv --players normalized_players.csv --out . \
  --flag-wr-triples --late-swap-audit --ownership-fade-report
```

`optimize`, `run`, and `late-swap` honor the same flags after they write lineups.
`review` reads the CSVs and does not re-solve.

| Flag | File | Operator next step |
|------|------|--------------------|
| `--flag-wr-triples` | `stack_fragility_report.csv` | Same-game WR triples and `CHALK-QB-WR-WR`. May then `--exclude` or opt-in PlayersGroup `max_from_group`. |
| `--late-swap-audit` | `late_swap_alert_report.csv` | Rostered Q/D. Q stays in the pool. Confirm, then existing `late-swap`. Do not auto-swap. |
| `--ownership-fade-report` | `leverage_fade_matrix.csv` | Exposure vs projected own%. `NEGATIVE_LEVERAGE` is a flag only. May then `--max-exposure` / `--exclude`. |

Read the CSVs. Then you may `--exclude` / `--max-exposure` / `late-swap`. Do not auto-drop Q.
Do not retune FPPG. Optional `--ownership-calibration` scales report own% only.

KEEP/REJECT and TG01–TG07: `briefs/2026-09-15_gemini-dfs-improve.md`.

## Ownership Calibration

Heuristic ownership works without paid labels, but a calibrated file is preferred
when you have contest-specific projections:

```bash
ceminidfs ownership calibrate \
  --labels tests/fixtures/sample_ownership_labels.csv \
  --salary tests/fixtures/synthetic_fd_slate.csv \
  --season 2024 \
  --week 1 \
  --out artifacts/ownership/demo_w1.json
```

Then set `ownership.calibration_path` in a local copy of the GPP profile or pass it
through a runtime config wrapper before projection. The calibrated ownership column
feeds the rerank ownership penalty.

## Tonight build (Week 1 2026)

Do not use 2,000 candidates on the Sunday-afternoon FanDuel slate. One
lineup takes about 1 second. 2,000 candidates can take 35 minutes. Stacks
such as `qb:3` plus `3-2` can take hours.

1. Time a probe: `ceminidfs optimize --csv normalized_players.csv --out probe.csv --count 25 --min-salary 58500`
2. Full GPP: `ceminidfs run --season 2026 --week 1 --salary data/slates/2026-09-13_fd_sun.csv --site fanduel --stages all --profile gpp --min-salary 58500`
3. Pass `--candidates 2000` only if you have extra time.
4. Run `ceminidfs fetch --season 2026 --week 1 --force` before project.
5. Use tonight’s FanDuel player-list CSV. Do not reuse an old contest export.
6. Questionable (`Q`) players stay in the optimizer pool. OUT / IR / D drop in normalize.
7. Late swap rebuilds one lineup at a time. A failed swap keeps the original row.

Operator submits. Agent does not Enter.

## Late Swap

Keep every original lineup name in the players file. Do not drop OUT rows.
Zero FPPG for new OUTs. Use `--exclude` for unlocked names that must not
enter a swapped lineup. A locked-team OUT stays in the file so the imported
lineup still parses.

Do not point `run` at an old FanDuel salary CSV. If you re-run `project`,
write a *copy* that does not drop rows.

Lock each 1 p.m. ET club once. Use nflverse abbreviations, not FanDuel aliases:

- `JAX` (not `JAC`)
- `WAS` (not `WSH`)
- `LAR` (not `LA`)

```bash
ceminidfs late-swap \
  --lineups lineups.csv \
  --players normalized_players.csv \
  --lock-team JAX \
  --lock-team WAS \
  --lock-team LAR \
  --exclude "Alvin Kamara" \
  --stack qb:3 \
  --max-exposure 0.35 \
  --out lineups_late_swap.csv
```

`--lock-team JAC` aliases to `JAX`. If a lock team matches 0 pool players,
the command prints a warning.

Keep the same stack, exposure, and fade flags as the original GPP build.
