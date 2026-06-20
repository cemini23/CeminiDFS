# Phase 5 v2 — Opus 4.8 Execution Plan

> **Goal:** Upgrade distribution layer from v1 stubs to wiki-aligned v2: role-prior Gaussian copula, calibrated ownership from paid labels, sim rerank of pydfs candidates.

## Tracks (GPT 5.5 parallel)

| Track | Deliverable |
|-------|-------------|
| **P5v2-A** | `models/correlation.py` + copula path in `models/simulate.py` |
| **P5v2-B** | `data/ownership_labels.py` + ridge/elastic-net calibration in `models/ownership.py` |
| **P5v2-C** | `export/sim_rerank.py` — 2000 candidates → sim-score → top 150 |

## P5v2-A — Gaussian copula (W-CORR)

**New:** `src/ceminidfs/models/correlation.py`

- `assign_player_roles(df)` → adds `role` column: QB, RB1, RB2, WR1, WR2, WR3, TE1, DEF, OTHER (rank by fd_projection within team+position)
- `ROLE_CORRELATION_PRIORS` from wiki cheat table (QB-WR1 +0.45, QB-TE1 +0.28, QB-RB1 +0.10, same-team skill +0.15 default, QB-opp_DST -0.35, bring-back opp QB +0.20 when same game)
- `build_correlation_matrix(df, site="fanduel")` → PSD matrix via symmetrize + eigenvalue floor
- `nearest_psd(matrix)` helper

**Extend:** `simulate.py`

- `simulate_fd_points_copula(df, n_iterations, seed, method="copula")` using:
  1. Marginal lognormal params from POSITION_CV (reuse v1)
  2. Correlation matrix from correlation.py
  3. Cholesky → uniforms → inverse marginal CDF
- `simulate_fd_points(..., method="team_shock"|"copula")` — default team_shock for backward compat
- Wire `add_simulation_columns` to use copula when `config.simulate.method == "copula"`

**Config:**
```yaml
simulate:
  method: copula  # or team_shock
```

**Tests:** `tests/test_correlation.py`, extend `tests/test_simulate.py` — copula same-team QB-WR1 correlation > QB-other team

## P5v2-B — Calibrated ownership

**New:** `src/ceminidfs/data/ownership_labels.py`

- Reuse benchmark CSV parser pattern; `load_ownership_labels(path) -> list[dict]` with join_key, ownership (float 0-100)
- `OwnershipCalibration` dataclass: per-position intercept/slope or sklearn model

**Extend:** `models/ownership.py`

- `fit_ownership_calibration(labels, heuristic_rows) -> OwnershipCalibration` — numpy ridge fallback (no hard sklearn dep); try sklearn ElasticNet if available
- `project_ownership_calibrated(rows, calibration=None, labels_path=None)` — blend heuristic with fitted calibration when labels provided
- CLI: `ceminidfs ownership calibrate --labels FILE --out artifacts/ownership_calibration.json`

**Config:**
```yaml
ownership:
  calibration_path: null  # optional JSON from calibrate command
```

**Tests:** `tests/test_ownership_labels.py`, extend test_ownership with synthetic label fit

## P5v2-C — Sim rerank

**New:** `src/ceminidfs/export/sim_rerank.py`

```python
def score_lineup(lineup_players, sim_matrix, player_index) -> float  # mean sim pts
def rerank_lineups(candidates, sim_matrix, player_index, final_count=150) -> list
def optimize_with_sim_rerank(csv_path, out_path, sim_matrix, player_index, candidates=2000, final=150, **optimize_kwargs) -> int
```

- Generate `candidates` lineups via pydfs (reuse optimize_lineups internals or call optimize with count=candidates without writing)
- Build `player_index` from normalized CSV names → row index in sim matrix
- Score = mean simulated FD points across iterations per lineup
- Select top `final` unique lineups by score (tie-break by projection sum)
- Optional: `top1_pct` = fraction of sims where lineup beats slate median

**Orchestrator:** when `config.get("sim_rerank", {}).get("enabled")`, run rerank path in `_run_optimize`

**CLI flags on optimize/run:**
```
--sim-rerank --candidates 2000 --final-count 150
```

**Tests:** `tests/test_sim_rerank.py` — synthetic sim matrix + fake lineups, verify ordering

## Exit criteria

- [ ] Copula sim produces higher QB-WR1 correlation than v1 team shock
- [ ] Ownership calibrate CLI + JSON round-trip
- [ ] Sim rerank selects higher-scoring lineups in unit test
- [ ] 95+ tests, ruff clean, PLAN/README updated

## Dependencies

- numpy only for copula (use `scipy.special.ndtr` / `ndtri` if scipy present, else erf approximations)
- sklearn optional for ElasticNet; numpy ridge required fallback
