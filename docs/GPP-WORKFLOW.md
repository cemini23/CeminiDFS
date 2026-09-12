# GPP Workflow

Use the GPP profile when building tournament lineups where ceiling, correlation,
and ownership leverage matter more than conservative median projections.

## Run With The GPP Profile

The base `config/nfl_dfs.yaml` stays conservative for research and backtests:
simulation, simulation rerank, and ownership projection are disabled by default.

For tournament builds, pass `--profile gpp`:

```bash
ceminidfs project --season 2025 --week 1 --salary slate.csv --profile gpp
ceminidfs optimize --csv normalized_players.csv --out lineups.csv --profile gpp
ceminidfs run --season 2025 --week 1 --salary slate.csv --stages all --profile gpp
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

The profile deep-merges `config/nfl_dfs_gpp.yaml` over the base config and enables:

- `simulate.enabled: true` with the `copula` method.
- `sim_rerank.enabled: true` with 2,000 candidates, 150 final lineups, and p85 scoring.
- `ownership.enabled: true` with heuristic ownership unless a calibration path is supplied.

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

## Late Swap

After lock, rerun the build with updated player statuses and use late swap on the
existing lineup file:

```bash
ceminidfs late-swap \
  --lineups lineups.csv \
  --players normalized_players.csv \
  --lock-team KC \
  --out lineups_late_swap.csv
```

Keep the same profile assumptions for late-swap rebuilds so exposure, ownership,
and simulation columns stay aligned with the original tournament build.
