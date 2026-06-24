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
