# Projection MAE campaign — 2026-11-01

## Decisions for the implementer

1. Do not tune projection code in this campaign.
2. Do not tune ownership code in this campaign.
3. Do not score a holdout in this campaign.
4. Call `walk_forward` for every later slate split.
5. Keep a change only when `keep_or_revert` returns `keep`.

## Background

The autoresearch loop keeps a change only when one metric improves on a fixed budget. The source budget is five minutes of wall clock. This campaign uses one block of slates. The source metric is `val_bpb`. This campaign uses projection MAE. Lower is better.

The source splits a human instruction file from agent code. Here the human file is `src/ceminidfs/eval_loop/objective.py`.

## Problem

Contest ROI has a heavy tail. A loop that tunes on one fixed set of slates will fit that set. The holdout must be a later block of dates. A random split shares players across the cut.

A keep has no meaning while the metric is still noise. This file records the noise band before any keep.

## Prior art

karpathy/autoresearch is MIT. This campaign uses the loop contract. It does not copy the training code. This laptop has no NVIDIA GPU, so the source harness cannot run here.

quants.md describes a walk-forward split. The repository and the licence are unresolved. `walk_forward` is a new implementation of that description. No source file was copied.

The design-log methodology is prose. The evaluation report calls the licence MIT. The README states no licence. This file follows the prose rules. No rule file was copied.

## Frozen design

### Why these files exist

`accuracy_metrics` returns MAE for one paired sample. It does not return a required slate count.

`walk_forward_fppg` cuts features before the target week. It does not return train indices and test indices.

`run_backtest` scores every week in a range. It does not hold out a final block of dates.

The permutation test shuffles one week of actual points. It does not answer the slate-count question.

No new projection parameter was added.

### Objective

The metric is projection MAE. Lower is better.

The formula is `src/ceminidfs/pipeline/metrics.py:27`. A slate backtest reads it at `src/ceminidfs/pipeline/backtest.py:266`.

The metric name is `src/ceminidfs/eval_loop/objective.py:11`. The keep threshold is `src/ceminidfs/eval_loop/objective.py:20`. `METRIC_KEY` is `mae`. `MINIMUM_EFFECT` is 0.10 FanDuel points. `BLOCK_COUNT` is `src/ceminidfs/eval_loop/objective.py:24` and the value is 2.

`config/nfl_dfs.yaml:50` sets `regression.max_overall_mae` to 4.85. The measured mean of these slates sits 0.09 below that gate. A tenth of a point is the pass-or-fail scale already in the config.

One evaluation scores one train block. Every candidate in a run uses that same block.

### Train and holdout

This campaign does not cut a train block. This campaign does not cut a holdout. A valid cut needs 20 slates in the train block and 20 slates in the holdout. The history has 13 slates.

The 13 rows below are the measurement sample. They are the full set of slate MAE values in `reports/backtest_2025_w5-17.json`. No holdout score was computed.

| Week | Sunday | Slate MAE |
| --- | --- | --- |
| 5 | 2025-10-05 | 4.906093240160165 |
| 6 | 2025-10-12 | 4.725267869358058 |
| 7 | 2025-10-19 | 5.130120864633976 |
| 8 | 2025-10-26 | 4.901330639460166 |
| 9 | 2025-11-02 | 4.831336899047294 |
| 10 | 2025-11-09 | 4.726220452195701 |
| 11 | 2025-11-16 | 4.65821104168795 |
| 12 | 2025-11-23 | 4.641815857748332 |
| 13 | 2025-11-30 | 4.695692775947899 |
| 14 | 2025-12-07 | 4.621704505263236 |
| 15 | 2025-12-14 | 5.1036558346991745 |
| 16 | 2025-12-21 | 4.511908833994202 |
| 17 | 2025-12-28 | 4.421878050460857 |

The date is the Sunday of that NFL week. The backtest file has no kickoff time. The order key is season, then week. The committed copy is `src/ceminidfs/eval_loop/observed_mae.py:22`.

A later campaign must put the holdout on the last dates. It must call `walk_forward` only on the earlier dates. It must write a new file in `design-log/`. It must leave this frozen section unchanged.

### Noise band

Each slate counts once. The player-weighted MAE in the report is 4.751481. The noise band uses the unweighted mean of the 13 slate values. That mean is 4.759634.

The sample standard deviation uses divisor `n - 1`. It is 0.209624.

The half-width is `t_{n-1, 0.975} * s / sqrt(n)`. `scipy.stats.t.ppf` supplies `t`. The code is `src/ceminidfs/eval_loop/noise_band.py:161`.

On these 13 slates the half-width is 0.126674 FanDuel points. The half-width is wider than 0.10.

The required slate count is the smallest `n >= 2` whose half-width is at most 0.10, with this standard deviation held fixed. The code is `src/ceminidfs/eval_loop/noise_band.py:68`. The count is 20.

`campaign_slate_count` at `src/ceminidfs/eval_loop/noise_band.py:109` multiplies that count by `BLOCK_COUNT`. Two blocks need 40 slates.

The history has 13 slates. 13 is below 20, so one block has not left the noise. 13 is below 40, so a train block and a holdout cannot both leave the noise.

`keep_or_revert` at `src/ceminidfs/eval_loop/noise_band.py:133` returns `blocked` for this band. A large drop in MAE does not override that result.

The standard deviation is estimated from 13 slates. The 95% chi-square interval is 0.150318 to 0.346034. The code is `src/ceminidfs/eval_loop/noise_band.py:89`. At the low end, one block needs 12 slates, and two blocks need 24 slates. The history has 13 slates. The loop stays blocked. The gate uses the sample standard deviation.

### Ownership error, cash rate, and ROI

Ownership error has no slate series in this repo. The required slate count is not computed.

Double-up cash rate has no slate series in this repo. The required slate count is not computed.

GPP ROI has one slate with both a fee and a payout. 2026 week 1 fees were $50 and the book won $16.50. The week 2 brief does not state a net. The week 4 book was built by hand. Later entry files have no settled payout in the repo. `tests/fixtures/week5/lineup_totals.csv` stores `cashed_inferred`. That file is not a settled payout. A standard deviation needs two settled slates. The ROI required slate count is not computed. The loop cannot run on ROI.

### Parameters the agent may change

The list is empty. `ALLOWED_PARAMETERS` is `()` at `src/ceminidfs/eval_loop/objective.py:27`.

### Files the agent may not touch

- `src/ceminidfs/eval_loop/objective.py`
- `src/ceminidfs/eval_loop/observed_mae.py`
- `src/ceminidfs/pipeline/metrics.py`
- The frozen section of `design-log/2026-11-01-projection-mae.md`

The same paths are `FORBIDDEN_PATHS` at `src/ceminidfs/eval_loop/objective.py:29`.

### Split function

`walk_forward(slates, n_folds, train_ratio)` is `src/ceminidfs/eval_loop/walk_forward.py:14`.

1. Read a date from each slate.
2. Sort by date. A tie keeps the input order. Do not shuffle.
3. Return indices into the input sequence.
4. Set the first train length to `floor(n * train_ratio)`.
5. Split the later slates into `n_folds` contiguous test blocks. Sizes differ by at most one slate. Earlier blocks take the extra slate.
6. Train fold k on every slate dated before its test block.
7. Raise `ValueError` when the first train block is empty or a test block would be empty.

`walk_forward_fppg` builds a prior-week rate. It is a different function.

---

Frozen section ends. Append implementation results below this line. Do not edit the text above this line.

## Implementation results

The tuning loop did not run. `keep_or_revert` returns `blocked` on the 13 slate MAE values. No projection file changed. No ownership file changed. No holdout was scored. No tuned config was produced.

`pytest -q tests/test_eval_loop.py` passed 13 tests. `pytest -q` passed 802 tests and skipped 1. `ruff check src/ceminidfs/eval_loop tests/test_eval_loop.py` passed.

Departures from the frozen design: none.
