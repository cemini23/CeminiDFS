# SIP handoff — K281 premium-band guard

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Lane

hard — Grok CLI implements. Plan below is written in the parent session.

## Context

`src/ceminidfs/pipeline/permutation_gate.py` measures the projection model's
Spearman edge after controlling for salary. Run on 2026 weeks 1-3 it shows one
consistent weakness.

Premium band, `fd_salary >= 7000`:

| Week | n | model vs actual | salary vs actual | partial given salary | p | clears |
|------|---|-----------------|------------------|----------------------|---|--------|
| 1 | 38 | +0.283 | +0.368 | +0.229 | 0.071 | no |
| 2 | 44 | −0.051 | +0.254 | −0.076 | 0.688 | no |
| 3 | 45 | +0.264 | +0.451 | +0.114 | 0.223 | no |

Three weeks out of three, the model has no edge over salary for premium players.
In week 2 it ranks premium players worse than random. The band `6000 <= salary
< 7000` still clears its null every week, so the fix targets `>= 7000` only.

Do NOT delete the model. Do NOT retune the whole projection stack. Add a narrow,
optional post-projection guard and prove whether it helps.

## Success criteria

1. **`src/ceminidfs/models/premium_guard.py`** exists.

2. **`salary_implied_baseline(history, season, week)`** returns a mapping from
   salary to an implied point total. Fit it on data strictly before `week`:
   use the same season's earlier weeks and the prior season. A log-linear fit
   (`points ~ a + b * log(salary)`) or a per-salary median are both acceptable.
   The function must never read the target week.

3. **`apply_premium_guard(projections, baseline, *, threshold=7000, weight=0.5)`**
   returns adjusted projections. For a player with `salary >= threshold`, return
   `(1 - weight) * projection + weight * baseline(salary)`. For all other
   players return the projection unchanged. `weight=0` must be an exact no-op.

4. **A flag on the run path.** Add `--premium-guard` to `ceminidfs run` and to
   the project stage. Default OFF. When off, byte-identical output to today.
   When on, the canonical `fd_projection` column carries the guarded value and a
   new column `fd_projection_unguarded` keeps the original.

5. **Walk-forward validation report.** A module `src/ceminidfs/pipeline/premium_guard_backtest.py`
   runs the permutation gate's premium band (`salary >= 7000`) for 2026 weeks 1,
   2, 3 with the guard OFF and ON. It prints, per week: `n`, `partial_off`,
   `partial_on`, and the delta. It writes `reports/audit/k281-premium-guard.md`.

6. **Decision rule, enforced in the report.** The guard is recommended ONLY if
   `partial_on >= partial_off` in every week, or if it wins at least two of
   three weeks and never loses by more than 0.02. State the outcome in one
   plain sentence. If the guard does not meet the rule, say the guard is NOT
   recommended and leave the flag off.

7. **`tests/test_premium_guard.py`** with at least:
   - `weight=0` is an exact no-op.
   - A player below the threshold is unchanged at any weight.
   - A player at or above the threshold moves toward the baseline as weight rises.
   - `salary_implied_baseline` does not read the target week (pass a history
     frame whose target-week rows would change the fit, and assert the fit is
     identical).

## Verify

- `.venv/bin/python -m pytest -q tests/test_premium_guard.py`
- `.venv/bin/python -m ceminidfs.pipeline.premium_guard_backtest`
- `.venv/bin/ruff check src tests`
- `grep -n "premium-guard" src/ceminidfs/cli.py`
- `test -f reports/audit/k281-premium-guard.md`

## NEVER

- Do not change `late_swap_oracle.py`, `late_swap_replay.py`, `permutation_gate.py`, or `permutation_test.py`.
- Do not retune salary, ownership, volume, usage, or stats models.
- Do not make the guard default-on. Leave it off.
- Do not fit the baseline on the target week or on any later week.
- Do not claim an edge the walk-forward does not show.
- Do not rewrite the existing sections of `briefs/2026-10-03_k280-measure.md`.
- No network scrape. No paid-site data. No live order.
- Do not commit. Do not push.

## Plan

Goal: stop the model from overriding salary where the model has no edge.

1. The evidence says the model adds nothing beyond salary at `>= $7,000`, and
   adds real signal below that. So keep the model everywhere and shrink its
   influence only in the premium band.

2. The baseline must be prior-only. Fit it walk-forward, per week, from earlier
   weeks and the prior season. A log-linear fit or a per-salary median both work.
   The point is a stable, salary-driven anchor that carries no target-week data.

3. Blend, do not replace. `(1 - w) * model + w * baseline` with `w = 0.5` at
   `salary >= 7000`. Half weight is a fixed, non-fitted choice. It halves the
   model's influence in a band where the model is noise. A fitted weight on three
   weeks would be overfitting; do not fit it.

4. Keep the raw projection in a second column so the operator can compare and
   the guard is reversible at the lineup stage.

5. Prove it or drop it. Run the gate premium band with the guard off and on
   across 2026 weeks 1-3. Apply the decision rule in item 6 of Success criteria.
   Three weeks is a small sample; a tie is not a win. If the guard does not
   clearly help, report that and leave the flag off.

6. Wire the flag so this week's slate can run either way. Do not turn it on by
   default. The operator decides after reading `reports/audit/k281-premium-guard.md`.

7. Boundary: a human types the ticket. No live order. No auto-submit.
