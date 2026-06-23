# Edge Sprint — Opus 4.8 Master Plan

> **Goal:** Ship all optional pre-season edge improvements: GPP sim stack, ownership path, RB calibration, K126 P2 prototypes, NGS eval stub, repo hygiene.
>
> **Workspace:** `/Users/claudiobarone/Desktop/projects/CeminiDFS` · **159 tests** · CI green

## Tracks (parallel subagents)

| Track | Agent | Scope |
|-------|-------|-------|
| **EDGE-A** | GPT 5.5 | GPP profile: simulate (copula) + sim_rerank + ownership |
| **EDGE-B** | Kimi K2.5 | RB MAE/bias calibration (mirror QB pass) |
| **EDGE-C** | GPT 5.5 | K126 P2: fourth-down + workload PBP prototypes |
| **EDGE-D** | Kimi K2.5 | Hygiene: gitignore, PLAN.md, NGS eval stub, docs |

---

## EDGE-A — GPP contest stack

**Problem:** `simulate`, `sim_rerank`, `ownership` built but disabled — no GPP edge at runtime.

**Deliverables:**

1. **`config/nfl_dfs_gpp.yaml`** — extends base via deep-merge keys:
   ```yaml
   simulate: { enabled: true, method: copula, n_iterations: 5000 }
   sim_rerank: { enabled: true, candidates: 2000, final_count: 150, quantile: 0.85, ownership_penalty: 0.15 }
   ownership: { enabled: true, calibration_path: null }
   ```
   Base `config/nfl_dfs.yaml` stays conservative (simulate/ownership off) for backtest/research.

2. **`ceminidfs.config.apply_profile(cfg, name)`** + **`load_config(profile="gpp")`**

3. **CLI** — `--profile gpp` on `run`, `optimize`, `project` (merge gpp yaml over base)

4. **`pipeline/project.py`** — ensure sim matrix inputs include `coherence_risk_flag`, `pass_protection_stress` columns when simulate enabled (merge from stats_df)

5. **Tests:** `tests/test_gpp_profile.py` — profile merge, simulate columns present, sim_rerank config enabled

6. **`docs/GPP-WORKFLOW.md`** — when to use `--profile gpp`, ownership calibrate command, late-swap note

---

## EDGE-B — RB calibration

**Problem:** RB MAE ~5.35–5.36, borderline vs wiki target 5.30; slight under-bias possible.

**Deliverables:**

1. Extend **`stats_settings.py`** — `rb_ypc`, `rb_td_per_carry` shrinkage + priors (config keys under `stats.shrinkage` / `stats.priors`)

2. Wire into **`stats.py`** `_rushing_efficiency` for RB position

3. Optional **`usage`** tweak: `rb_carry_priors` or committee size in yaml if backtest improves

4. **`docs/rb-calibration-notes.md`** — what changed, walk-forward expectation

5. **Tests:** config respected, RB projection increases vs defaults on synthetic RB-heavy fixture

6. Run quick bias check on synthetic — no network in CI

**Gate:** must not regress QB fixes; full pytest green

---

## EDGE-C — K126 P2 prototypes (clean-room PBP)

Implement **two** additional coherence-risk signals from audit (no HF):

### 1. Fourth-down aggressiveness (`fourth_down_aggressiveness`)

- Team go-for-it rate on `down == 4` vs league, walk-forward
- Effect: boost `implied_total` / pass_rate slightly for aggressive teams in **`models/volume.py`** or coherence module

### 2. Skill workload index (`skill_workload_index`)

- Rolling target+carry volume z-score per skill player (proxy for workload→injury risk flag)
- Effect: attach `workload_risk_flag` on usage frame; **`simulate.py`** CV multiplier (like coherence flag)

**Deliverables:**

- Extend **`coherence_risk.py`** or new **`coherence_p2.py`** with both builders + optional adjustments
- Config under `coherence_risk.fourth_down` / `coherence_risk.workload` (enabled: true in gpp profile only, false in base)
- **`docs/coherence-risk-audit.md`** — mark P2 items implemented
- **Tests:** synthetic PBP, walk-forward cutoff, disabled no-op

**Out of scope:** rest/travel, NGS, route timing (no PBP columns)

---

## EDGE-D — Hygiene + NGS stub

1. **`.gitignore`** — add `reports/*.json`, `reports/*.md` (keep `reports/audit/` if needed — or ignore all `reports/` except committed eval docs; use `reports/` entirely gitignored except track `reports/sdv_benchmark_2025.json` via force-add pattern — simplest: `reports/` except `reports/.gitkeep` and document local-only)

   Use: `reports/` gitignored entirely; move `sdv_benchmark_2025.json` to `docs/benchmarks/` if needed OR keep in repo under docs

2. **`PLAN.md`** — update test count, DST stat-first, coherence K126, K127, GPP profile, session handoff

3. **`src/ceminidfs/data/ngs_eval.py`** — stub `load_ngs_passing_sample(season)` via sportsdataverse optional import, return empty + docstring; no prod fetch

4. **`docs/ngs-participation-eval.md`** — P2 reference for SDV NGS/participation loaders

5. **Fixture:** `tests/fixtures/sample_ownership_labels.csv` for `ceminidfs ownership calibrate` demo

---

## Exit criteria

- [ ] `ceminidfs run --profile gpp` documented and tested (mock pydfs where needed)
- [ ] RB + QB both config-driven; regression gates pass
- [ ] 2 new K126 P2 signals behind config toggles
- [ ] PLAN.md current; reports gitignored
- [ ] `pytest` + `ruff` green; do NOT commit unless user asks

## Execution order after merge

1. Subagents commit to working tree
2. Parent: merge conflicts, full pytest, fix lints
3. User can commit separately
