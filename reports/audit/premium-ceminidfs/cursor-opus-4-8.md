# CeminiDFS Post-Phase 5 Super Audit — Auditor 1/6

**Slot:** `claude-opus-4-8-thinking-high` (agentic-reasoning role)
**Mode:** architecture + code-debug + prod-ship · Readonly
**Date:** 2026-06-20 · **Tests:** 103 passing (1 pydfs deprecation warning)

---

## Verdict

**WARN** — The pipeline is leakage-safe and the Phase-0 P0s are fixed, but the DIY projection has no opponent-defense adjustment (`defense_multiplier` is a hardcoded `1.0` stub) and no real DST model, the weather snapshot pulls the **wrong clock hour for every non-Eastern venue**, the entire correlation/copula machinery is **inert** in the shipped pipeline, and sim-rerank's mean-of-sum scoring makes the Monte Carlo simulation add **nothing** over a deterministic projection sum. None corrupt lineups in the default (sim/ownership/rerank disabled) path, but several would mislead a backtest or silently no-op the Phase-5 features when enabled.

---

## Findings

| Severity | Finding | Evidence (file:line or behavior) | Fix |
|----------|---------|----------------------------------|-----|
| **P0** | **Sim rerank scores by mean of summed sims → correlation & variance have ZERO effect on lineup ranking.** `E[Σ players] = Σ E[player]`; the mean of a sum is invariant to the covariance, so the copula/team-shock matrix changes nothing. Ranking by "mean sim score" ≡ ranking by Σ `median·exp(σ²/2)`, i.e. a deterministic projection sum. The whole MC pass is wasted compute, and any operator who enables it expecting ceiling/correlation upside gets none. | `export/sim_rerank.py:66` `matrix[indexes,:].sum(axis=0).mean()`; lognormal mean derivation in `models/simulate.py:64-76` | Score lineups by a **ceiling/tail statistic** (e.g. P85–P90 of the lineup-total distribution, or win-rate vs. a sampled field). Only then does correlation matter. |
| **P0** | **Correlation/copula matrix is inert in the real pipeline.** The projection frame carries `opponent` (not `opp`) and has no `game` column, so `correlation.py` reads empty strings for `opp`/`game` → all opponent / same-game / bring-back priors never fire (only same-team pairs survive). Worse, marginals are identical between `team_shock` and `copula` (both lognormal, σ identical), so per-player floor/median/ceiling are also unaffected by the matrix. **Correlation currently changes no persisted output.** | `models/correlation.py:66-67` `assigned.get("opp")`/`get("game")`; projection cols from `models/stats.py:27` (`opponent`) + `scoring.py:123` add no `opp`/`game`; `export/sim_rerank.py:302-315` builds rows with only name/id/proj/team/position | Emit `opp` and `game`/`game_id` onto the scored frame and into `_simulation_rows`; rename `opponent`→`opp` or alias it in `correlation.py`. Then adopt tail-based rerank (above) so the matrix has teeth. |
| **P1** | **Weather snapshot pulls the wrong hour for all non-ET venues (timezone misalignment).** nflverse `gametime` is Eastern, but `fetch_hourly_forecast` requests `timezone=auto` (local stadium time). `kickoff_weather_snapshot` then matches `T{kickoff_hour:02d}:00` against **local** timestamps. A 13:00 ET kickoff in Seattle (10:00 PT local) grabs the 13:00 PT row = 16:00 ET → weather sampled 3h after kickoff (2h Mountain, 1h Central). | `data/weather.py:82` `timezone=auto`; `:140-143` suffix match; `:235-249` `_parse_game_time` parses ET hour | Convert ET kickoff to the venue's local hour before indexing (ship a per-stadium tz, or request `timezone=GMT`/`America/New_York` and align consistently). |
| **P1** | **Benchmark / any join_key merge against PBP-derived actuals drops all TEs and mislabels RB-receivers.** `_aggregate_receiving` hardcodes `position="WR"` for every receiver, so a TE's actuals get `join_key = name|team|WR` while the projection's key is `name|team|TE` → no match. Backtest itself escapes this because `backtest_week` merges on `player_id`, but the paid-benchmark compare (and any name-key join) will silently lose TEs. | `pipeline/backtest.py:359` `"WR"`; same in `_aggregate_passing:316`/`_aggregate_rushing:337` | Derive actuals position from a roster/position map keyed on `player_id`, not from the aggregation branch. |
| **P1** | **Saved sim-matrix row order can desync from the player index → silently scores the wrong players.** When a `simulation.parquet`/`sim_matrix.parquet` lacks a name column, `_load_saved_sim_matrix` builds the index from `normalized_csv`, assuming its row order equals the parquet's matrix-row order. Nothing enforces that; normalize can reorder/filter. Result: `score_lineup` indexes valid rows that belong to different players — no exception, wrong scores. | `orchestrator/run.py:273-277` | Require a name/player_id column in the saved matrix and always build the index from the matrix's own rows; hard-fail if absent. |
| **P1** | **No opponent-defense adjustment (`defense_multiplier` stub).** Always returns `1.0`, so yards/TDs are never adjusted for opponent strength → players vs. elite defenses are systematically over-projected and vs. weak defenses under-projected. This is the single largest mis-ranking source in the DIY engine. | `models/stats.py:59-70`, applied at `:133-139` | Wire opponent EPA/DVOA-style pass/rush multipliers (the hook already threads `week`/`side`). |
| **P1** | **DST/DEF is unprojected by the DIY engine.** No DEF path in volume/usage/stats; `actual_week_fantasy_points` never emits DST rows, so DST silently drops out of every backtest merge and relies entirely on the FPPG fallback at optimize time. Stat-first stacks can't reason about DST. | `pipeline/backtest.py` (no DST aggregation); `models/stats.py` (no DEF branch) | Add a points-allowed/sacks/turnovers DST model + actuals aggregation; until then document DST as FPPG-only. |
| **P1** | **Backtest metrics are inflated by selection bias + cross-position pooling.** Inner join on `player_id` keeps only players who had prior usage AND played the target week — excludes rookies/return-from-injury/zero-snap benders (the hard-to-project tail). And `run_backtest` pools all player-weeks into one Spearman, so the correlation largely reflects QB(20)≫WR(8) position separation, not within-slate skill. | `pipeline/backtest.py:199-203` (player_id inner join), `:251` pooled `accuracy_metrics` | Report per-position and per-slate (within-week, within-position) Spearman; include a "projected-but-DNP = 0" arm to expose miss rate. |
| **P2** | **SoFi (LAC/LAR) `semi_open` is treated as weather-exposed → phantom wind/precip on a covered field.** `is_weather_exposed` only excludes `dome`, so SoFi gets live Open-Meteo wind that can trigger the volume pass-rate wind penalty even though the field is under a fixed canopy. | `data/stadiums.py:55-56, 94-95`; wind penalty `models/volume.py:121-126` | Treat `semi_open`/fixed-canopy like `dome` for wind/precip (keep exposed only for temperature, or zero out wind). |
| **P2** | **Historical weather uses the forecast endpoint, not the archive API.** Fine for current-week live (within forecast horizon) but returns no hourly data for 2024–2025 dates → `kickoff_weather_snapshot` yields `{}` → all-`None` weather. (Backtest passes `weather=None`, so unaffected today.) | `data/weather.py:24, 84` | Wire the Open-Meteo archive endpoint for historical builds; document forecast-only horizon. |
| **P2** | **`validate_lineups_csv` checks shape only — not salary cap, roster legality, or duplicate lineups.** A rectangular, fully-populated but cap-busting or duplicate-heavy CSV passes validation. | `orchestrator/validate.py:32-48` | Add salary-cap, slot-legality, and uniqueness checks. |
| **P2** | **Same-team WR1–WR2 correlation is positive (+0.15) and there is no QB↔opposing-WR bring-back prior.** Game-stack bring-back (the canonical leverage play) is unmodeled; only opp-QB (+0.20) and QB↔opp-DEF (−0.35) exist. WRs competing for the same target pool are usually ~0/slightly negative. | `models/correlation.py:9-18, 119-128` | Add bring-back priors; reconsider intra-team WR sign vs. the K125 W-CORR table. |
| **P2** | **Ownership: heuristic value-softmax shipped; calibrated output not renormalized; no duplication model.** Calibrated ownership is clamped to [0,100] per player without re-normalizing to slot mass, so totals drift; sim rerank ignores ownership entirely. | `models/ownership.py:114-135` (no renorm), wiki "no ownership/dup in rerank" | Renormalize post-calibration; feed ownership/leverage into the (future tail-based) rerank. |

---

## Ship recommendation

- **Live slate ready?** **N (qualified Y for plumbing).** The orchestrator is fail-loud, stage ordering auto-inserts `normalize` before `optimize`, `RunManifest` is wired, and lineup CSVs are validated — wiring is production-shaped. But DIY projections are not production-grade until the opponent-defense stub and DST model land; with `projection_mode: auto` the system can silently fall back to FPPG and still "succeed".
- **Backtest trustworthy?** **Partially.** Walk-forward is genuinely leakage-safe (strict `week < week`, double-filtered in engine+stats; actuals use `week == week`; Vegas uses pre-game closing lines). But absolute MAE/Spearman are optimistic due to player_id selection bias and cross-position pooling — trust *relative/per-position* trends, not headline numbers.
- **Sim rerank safe?** **Y (won't corrupt) but useless + one risky path.** Mean-based ranking can't produce illegal lineups, but it adds no value over projection-sum and the saved-matrix index path (P1) can mis-score silently.

---

## Root cause

The highest-impact issue is that **Phase 5's variance/correlation stack is mathematically inert end-to-end**. Three independent facts compound: (1) `team_shock` and `copula` share identical lognormal marginals, so per-player floor/ceiling don't depend on the matrix; (2) the projection frame never carries `opp`/`game`, so the correlation matrix degenerates to same-team-only even when built; and (3) sim-rerank scores lineups by the **mean of the summed simulations**, which equals the sum of per-player means and is provably invariant to covariance. So the entire copula/PSD/Cholesky apparatus — the headline Phase-5 deliverable — currently changes no persisted projection and no lineup ranking. The simulation only re-weights positions by `exp(σ²/2)` (a deterministic CV tilt toward WR/RB). Fixing this requires both plumbing `opp`/`game` through and switching rerank to a tail/win-rate objective; until then, enabling sim_rerank is a no-op dressed as an edge.

---

## Ranked patch backlog

| P | Patch | Effort | Expected lift |
|---|-------|--------|---------------|
| P0 | Switch `score_lineup` to a lineup-total **P85/P90 (or field win-rate)** statistic instead of the mean | 1–2 hr | Makes simulation/correlation actually affect lineup selection; real GPP edge |
| P0 | Plumb `opp` + `game`/`game_id` onto the scored frame and `_simulation_rows`; alias `opponent`→`opp` in `correlation.py` | 1 hr | Activates opponent/bring-back correlations (prereq for the P0 above) |
| P1 | Convert ET kickoff → venue-local hour before indexing the Open-Meteo hourly series | 1–2 hr | Correct wind/precip at kickoff for ~20 non-ET venues |
| P1 | Derive actuals/benchmark position from a `player_id`→position map, not the receiving="WR" branch | 30 min | Stops TEs vanishing from benchmark/name-key joins |
| P1 | Require name/id column in saved sim matrices; build index from matrix rows; hard-fail otherwise | 30 min | Eliminates silent wrong-player scoring |
| P1 | Implement opponent `defense_multiplier` (pass/rush EPA) | 4–8 hr | Removes the biggest systematic mis-ranking in DIY |
| P1 | Add DST projection + DST actuals aggregation | 4–8 hr | DIY DST stacks; DST included in backtest |
| P1 | Report per-position / within-slate Spearman + a DNP=0 arm | 2 hr | Honest backtest signal |
| P2 | Treat `semi_open`/fixed-canopy as non-wind-exposed (SoFi) | 15 min | Removes phantom wind penalty on LAC/LAR home games |
| P2 | Wire Open-Meteo **archive** endpoint for historical weather | 1–2 hr | Enables real backtest weather features |
| P2 | Extend `validate_lineups_csv` to cap/slot/dupe checks | 1 hr | Catches malformed-but-rectangular lineup CSVs |

---

## Unique angle

**The Phase-5 simulation is a no-op that looks like a feature.** Most auditors will check that the copula matrix is PSD (it is — eigenvalue flooring + renormalization in `correlation.py:87-98,140-146`) and that same-team correlation > cross-team (the tests assert exactly this) and conclude the simulation works. But correctness of the matrix is irrelevant when (a) it's never populated with `opp`/`game` in production, and (b) the consumer collapses the joint distribution to its mean. The green test suite actively masks this: `test_simulate_fd_points_copula_boosts_qb_wr1_correlation` passes only because the **test** injects `opp`/`game` columns that the real pipeline never produces, and no test scores a lineup with vs. without correlation to show rank invariance. A single test asserting that `rerank_lineups` returns the **same order** under two different correlation matrices would have exposed the entire gap.

---

## Confidence

**High** on the inert-correlation / mean-rerank invariance (provable from the code), the weather timezone misalignment, the `defense_multiplier`/DST stubs, and walk-forward being leakage-safe. **Medium** on the saved-sim-matrix desync (depends on whether normalize reorders rows in practice) and on the magnitude of backtest metric inflation (no live numbers in the pack to quantify).
