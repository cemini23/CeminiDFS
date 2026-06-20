# Phase 5 — Opus 4.8 Execution Plan (v2 Distribution)

> **Goal:** Add distribution, ownership, and late-swap layers per K125 wiki (W-DIST, W-OWN, W-NEWS).

## Architecture placement

```text
fetch → project → [simulate] → [ownership] → normalize → optimize
                              ↓
                         late_swap (post-lock reruns)
```

## Parallel tracks (GPT 5.5)

| Track | Module | v1 scope |
|-------|--------|----------|
| **P5-A** | `models/simulate.py` | Gaussian copula-lite team shock + idio noise → sim matrix; P20/P90 floor/ceiling |
| **P5-B** | `models/ownership.py` | Value-rank softmax ownership by position (no paid labels) |
| **P5-C** | `export/late_swap.py` | pydfs load lineups + lock teams + re-optimize unlocked slots |

## P5-A — `models/simulate.py`

**Inputs:** DataFrame with `player_id`, `team`, `position`, `fd_projection` (median)

**API:**
- `POSITION_CV` — default coefficient of variation by position (QB 0.35, RB 0.45, WR 0.50, TE 0.45, DEF 0.40)
- `TEAM_CORRELATION` — latent team factor loading (same-team skill players share shock)
- `simulate_fd_points(df, n_iterations=5000, seed=None) -> pd.DataFrame` columns: player_id + `sim_{0..n-1}` OR long format — prefer wide matrix helper + `simulation_summary()`
- `simulation_summary(sim_matrix, quantiles=(0.2, 0.5, 0.9))` → floor/median/ceiling columns
- `add_simulation_columns(stats_df, n_iterations=5000)` → attach `Projection Floor`, `Projection Ceil` to rows

**Method (v1):** For each iteration, draw per-team latent `z_team ~ N(0,1)`. Player outcome:
`max(0, median * exp(beta_team * z_team + beta_pos * z_idio))` where `beta` derived from CV.

**Tests:** `tests/test_simulate.py` — deterministic seed, median ≈ input, ceiling > floor, same-team correlation > cross-team

**Integration:** Optional hook in `pipeline/project.py` when `config.simulate.enabled` or `config["run_simulation"]` is true; write floor/ceil to canonical CSV pass-through fields.

## P5-B — `models/ownership.py`

**API:**
- `project_ownership(rows: list[dict], site="fanduel") -> list[dict]` — adds `Projected Ownership` (0-100 scale, 1 decimal)
- Formula v1: `value = projection / (salary/1000)`; within each position group, softmax with temperature; scale to sum ~100% slot mass per position (QB pool ~100%, RB ~200% for 2 slots, etc.)
- `POSITION_SLOT_MASS` — QB 1.0, RB 2.0, WR 3.0, TE 1.0, DEF 1.0

**Tests:** `tests/test_ownership.py` — higher value → higher own; sums sensible per position

**Integration:** Call from `project_week()` when `config["project_ownership"]` true (default false for backward compat)

## P5-C — `export/late_swap.py`

**API:**
- `late_swap_lineups(lineups_csv, players_csv, locked_teams, out_path, site="fanduel", count=None) -> int`
- Use pydfs: load players CSV, `load_lineups_from_csv` if available, set `player.game_started = True` for players on locked teams, re-optimize

**CLI:** `ceminidfs late-swap --lineups FILE --players FILE --lock-team KC --lock-team BUF --out FILE`

**Tests:** `tests/test_late_swap.py` with pytest.importorskip pydfs; minimal mock if API unavailable — at least test locked team parsing and validation

## Config (`config/nfl_dfs.yaml`)

```yaml
simulate:
  enabled: false
  n_iterations: 5000
ownership:
  enabled: false
```

## CLI additions

- `ceminidfs simulate --season YYYY --week N --in parquet_or_csv` (optional; can skip if wired in project)
- `ceminidfs late-swap ...`

## Exit criteria

- [ ] simulate + ownership modules with tests
- [ ] late_swap module with tests (pydfs optional skip)
- [ ] project_week optionally emits Floor/Ceiling/Ownership
- [ ] PLAN.md Phase 5 tracks marked done (v1)
- [ ] 85+ tests passing, ruff clean

## Out of scope v1

- Full role-prior correlation matrix + Cholesky (P5-A uses team-shock copula-lite)
- Elastic-net ownership with paid labels
- Contest ROI / sim rerank of 2000 candidates
