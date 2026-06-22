# K126 — Opus 4.8 Execution Plan

> **Goal:** Clean-room steal of ClarusC64 coherence-risk *methodology* (not HF parquet) — feature audit, two PBP-derived stage-2 prototypes, 2024 backtest delta on top-50 FD actuals, P1 sim variance coupling.
>
> **Brief:** `briefs/2026-06-22_k126-nfl-coherence-risk-steal.md`

## Context

- CeminiDFS stage 2 = `volume → usage → stats → scoring` (`pipeline/engine.py`).
- nflverse PBP already cached via nflreadpy; **no Hugging Face runtime dependency**.
- K125 EPA audit pattern: derive proxies in-tree, document gaps, regression tests on synthetic PBP.
- Reject: HF parquet in fetch path, thiagocavalheiro PM sports bot.

## Parallel tracks (GPT 5.5)

| Track | Owner | Deliverable |
|-------|-------|-------------|
| **K126-A** | Subagent 1 | `docs/coherence-risk-audit.md` + gap table in `docs/ARCHITECTURE.md` |
| **K126-B** | Subagent 1 | `models/coherence_risk.py` — PBP derivations + adjustments |
| **K126-C** | Subagent 2 | Wire into `pipeline/engine.py`, `config/nfl_dfs.yaml`, `coherence_settings.py` |
| **K126-D** | Subagent 2 | `tests/test_coherence_risk.py` + synthetic fixture rows |
| **K126-E** | Subagent 2 | `pipeline/coherence_eval.py` — baseline vs enabled backtest + top-50 MAE |
| **K126-F** | Subagent 2 | P1: sim CV multipliers in `models/simulate.py` from coherence flags |

## K126-A — Feature audit (10 dimensions)

**New:** `docs/coherence-risk-audit.md`

Gap table columns: `Signal | HF reference | CeminiDFS stage-2 today | PBP proxy (clean-room) | Status`.

| Signal | Map to existing | Gap | Prototype |
|--------|-----------------|-----|-----------|
| Playcall vs defense coherence | `volume.pass_rate`, `defense_multiplier` | No scheme×coverage interaction | P2 — document only |
| Pass protection breakdown | `volume.sack_rate` (league constant) | No team OL stress history | **P0 prototype** |
| Defense motion adjustment | `defense.build_defense_ratings` | No pre-snap motion proxy | P2 — document only |
| Route timing | `usage.routes_proxy` | Routes proxy unused in scoring | P2 |
| QB read vs coverage | `stats.int_rate`, `defense_multiplier` | No coverage shell read | P2 |
| Drive momentum | `volume` (pace only) | No within-drive state | P2 |
| Workload → injury | `availability.py` exclusions | Binary OUT only, no workload risk | P2 |
| Red-zone playcall | `stats.td_per_*` (global) | No RZ tendency → usage link | **P0 prototype** |
| Fourth-down decision | `volume` implied totals | No 4th-down aggressiveness | P2 |
| Rest/travel spot | — | Not in nflverse fetch | P2 — CC-BY sample reference only |

**Extend:** `docs/ARCHITECTURE.md` — short "Coherence-risk layer (K126)" section linking audit doc.

## K126-B — `models/coherence_risk.py`

Clean-room PBP derivations (walk-forward: `week < through_week`):

### 1. Pass-protection stress (`team_pass_protection_stress`)

Per offensive team (`posteam`):

```text
dropbacks = pass attempts + sacks (pass == 1 or sack == 1 on scrimmage)
stress_raw = (sack_rate + qb_hit_rate) on dropbacks
stress_index = stress_raw / league_avg_stress   # 1.0 = average
```

Return `dict[team, float]` stress index.

**Adjustment** (when `enabled` and `stress_index >= threshold`):

- QB: multiply `pass_yds` projection by `(1 - qb_ypa_penalty * excess_stress)`
- WR/TE: multiply `rec_yds` by `(1 - wr_ypt_penalty * excess_stress)`
- Clamp penalties; attach columns `pass_protection_stress`, `coherence_risk_flag` on stats frame.

Use `epa_eligible_plays()` or same scrimmage mask as `pbp_filters` for consistency.

PBP columns (with fallbacks): `posteam`, `week`, `pass`, `sack`, `qb_hit`, `pass_attempt`.

### 2. Red-zone playcall tendency (`team_red_zone_run_tendency`)

Filter `yardline_100 <= 20` (fallback: `yrdln` parse if needed).

```text
rz_run_share = rz_rushes / (rz_rushes + rz_passes)
rz_run_index = rz_run_share / league_rz_run_share
```

**Adjustment** on `usage_df` before `build_week_stats` when `rz_run_index >= threshold`:

- RB: `projected_carries *= (1 + rb_carry_boost * excess)`
- TE: `projected_targets *= (1 + te_target_boost * excess)`
- WR: `projected_targets *= (1 - wr_target_trim * excess)` (clamp ≥ 0)

Attach `rz_run_index` column on usage frame.

### API surface

```python
@dataclass(frozen=True)
class CoherenceRiskSettings: ...

def build_team_pass_protection_stress(pbp, through_week, *, settings) -> dict[str, float]
def build_team_red_zone_run_tendency(pbp, through_week, *, settings) -> dict[str, float]
def apply_pass_protection_penalties(stats_df, stress_by_team, settings) -> pd.DataFrame
def apply_red_zone_usage_adjustments(usage_df, rz_by_team, settings) -> pd.DataFrame
def apply_coherence_risk(usage_df, stats_df, pbp, through_week, config) -> tuple[pd.DataFrame, pd.DataFrame]
def coherence_variance_multiplier(row, settings) -> float  # for sim layer
```

**New:** `models/coherence_settings.py` — `CoherenceRiskSettings.from_config(config)`.

## K126-C — Engine + config wiring

**`pipeline/engine.py`** in `build_diy_projections_from_frames`:

```text
usage_df = build_week_usage(...)
if coherence enabled:
    usage_df = apply_red_zone_usage_adjustments(...)  # before stats
stats_df = build_week_stats(usage_df, ...)
if coherence enabled:
    stats_df = apply_pass_protection_penalties(...)
```

Pass `config` through; default **`coherence_risk.enabled: false`** for backward compat.

**`config/nfl_dfs.yaml`:**

```yaml
coherence_risk:
  enabled: false
  pass_protection:
    stress_threshold: 1.12
    max_penalty: 0.10
    qb_yds_penalty: 0.35
    recv_yds_penalty: 0.25
  red_zone_playcall:
    run_tendency_threshold: 1.08
    rb_carry_boost: 0.06
    te_target_boost: 0.08
    wr_target_trim: 0.04
  sim_variance:
    enabled: true
    high_risk_cv_multiplier: 1.25
    stress_flag_threshold: 1.12
```

Penalty semantics: `excess = max(0, index - threshold) / (1 - threshold)` capped at 1.

## K126-D — Tests

**`tests/fixtures/coherence_pbp.py`** — minimal multi-team PBP:

- Team A: high sack+hit rate on dropbacks
- Team B: RZ run-heavy (yardline_100 <= 20)
- Walk-forward week cutoff

**`tests/test_coherence_risk.py`:**

1. Stress index > 1 for leaky OL team
2. Pass protection reduces QB `pass_yds` vs baseline when enabled
3. RZ tendency boosts RB carries / TE targets
4. `coherence_risk.enabled: false` → no-op (identical output)
5. Sim variance multiplier > 1 when `coherence_risk_flag` set

## K126-E — Backtest eval

**New:** `pipeline/coherence_eval.py`

```python
def run_coherence_comparison(season, start_week, end_week, config) -> dict:
    # Run backtest twice: enabled=False vs True
    # Metrics: overall MAE, top50 MAE (per week: players with actual fd in top 50 that week)
```

**CLI hook** (minimal): add `ceminidfs coherence-eval --season 2024 --start-week 5 --end-week 17` in `cli.py` OR document as Python entry only if CLI scope tight.

Output JSON fields: `baseline.mae_fd`, `coherence.mae_fd`, `delta_mae`, `baseline.top50_mae`, `coherence.top50_mae`, `top50_delta`.

Use existing `backtest_week` / projection merge patterns; no network.

## K126-F — P1 sim variance coupling

**Extend `models/simulate.py`:**

- `position_cv_for_row(row, config)` — if `coherence_risk.sim_variance.enabled` and row has `coherence_risk_flag` or `pass_protection_stress >= threshold`, multiply base `POSITION_CV` by `high_risk_cv_multiplier`.
- Apply in both `team_shock` and `copula` paths (replace flat `POSITION_CV.get` lookup).

High breakdown risk → wider simulated distribution → better ownership leverage on contrarian stacks (per brief).

## Exit criteria

- [ ] Gap table in ARCHITECTURE + full audit doc
- [ ] Two prototypes wired behind `coherence_risk.enabled`
- [ ] ≥8 new tests passing; full suite green
- [ ] `coherence-eval` runnable on synthetic cache (unit test mocks) + documented 2024 command
- [ ] No HF imports; ruff clean

## Out of scope

- HF parquet fetch, ClarusC64 dataset loaders
- thiagocavalheiro PM bot
- Rest/travel Karmane integration (document reference only)
- Remaining 8 coherence dimensions beyond audit table (P2 backlog)
