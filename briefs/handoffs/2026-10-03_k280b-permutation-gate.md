# SIP handoff — K280b salary-controlled permutation gate

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Lane

mid — Grok CLI plans, cheap executor implements.

## Context

`src/ceminidfs/pipeline/permutation_test.py` tests a projection model against a
null made by shuffling actual points at random. On 2026 week 3 it reports
`observed_spearman: 0.751912`, `p_value: 0.000999`.

That p-value is real but the null is too weak. Salary alone predicts actual
points almost as well as the model does, so "beats random" is a low bar.

Measured in the parent session on the same 550 joined pairs:

| Band | n | rank(model) | rank(salary) | partial(model given salary) | p |
|------|---|-------------|--------------|-----------------------------|---|
| all | 550 | 0.752 | 0.555 | +0.491 | 0.0005 |
| starters >= $6,000 | 131 | 0.783 | 0.785 | +0.387 | 0.0005 |
| premium >= $7,000 | 45 | 0.264 | 0.451 | +0.111 | 0.2389 |
| cheap < $6,000 | 419 | 0.681 | 0.590 | +0.487 | 0.0005 |

The model has no edge that clears the null in the premium band, which is where
DFS lineups are decided. The model's headline number comes from the cheap and
bench mass.

`partial` is the Spearman between rank(actual) and rank(projection) after both
are residualized on rank(salary). The p-value comes from 2,000 permutations of
the actual column.

## Success criteria

Add a salary-controlled permutation gate. Report, do not tune the model.

1. **`src/ceminidfs/pipeline/permutation_gate.py`** exists and runs as
   `.venv/bin/python -m ceminidfs.pipeline.permutation_gate`.

2. **`partial_spearman(projection, salary, actual)`** returns the Spearman
   correlation of rank(actual) and rank(projection) after both are residualized
   on rank(salary). Use the same tie-aware ranking the repo already uses
   (`ceminidfs.pipeline.metrics.spearman_correlation` is the reference; build
   ranks with `numpy` and match its tie handling, or reuse it directly).

3. **`salary_controlled_p(projection, salary, actual, draws, seed)`** returns the
   one-sided p-value: `(count of null partials >= observed, plus one) / (draws + one)`.
   The null shuffles the actual column only. Keep projection and salary fixed.

4. **`band_report(...)`** returns the four bands from the table above:
   `all`, `salary >= 6000`, `salary >= 7000`, `salary < 6000`. Each row carries
   `n`, `model_spearman`, `salary_spearman`, `partial_spearman`, `p_value`,
   and `cleared_null` (p <= 0.05). Skip a band with fewer than 20 pairs and mark
   it `NO_EVIDENCE`.

5. **Report block.** Append a `## Salary-controlled permutation` section to
   `briefs/2026-10-03_k280-measure.md`. Do not clobber the `## Verdict`,
   `## Oracle ceiling`, `## Permutation test`, or `## Leak-free replay` sections.
   List the four band rows and one plain sentence: where the model clears the
   null, and where it does not.

6. **`tests/test_permutation_gate.py`** with at least:
   - A synthetic case where the model is a copy of salary. `partial_spearman`
     must be near zero and `p_value` must be large.
   - A synthetic case where the model is a copy of the actual. `partial_spearman`
     must be near one and `p_value` must be small.
   - `band_report` returns four rows with the right `n` on the default slate.

7. **`PERMUTATION_GATE_DRAWS = 2000`** as a module constant.

## Verify

- `.venv/bin/python -m ceminidfs.pipeline.permutation_gate`
- `.venv/bin/python -m pytest -q tests/test_permutation_gate.py`
- `.venv/bin/ruff check src tests`
- `grep -n "## Salary-controlled permutation" briefs/2026-10-03_k280-measure.md`

## NEVER

- Do not change the projection model to raise the p-value. Report only.
- Do not edit `late_swap_oracle.py` or `late_swap_replay.py`.
- Do not rewrite the four existing report sections.
- Do not claim an edge where `p_value > 0.05`.
- Do not report a band with fewer than 20 pairs as a result.
- No network scrape. No paid-site data. No live order.
- Do not commit. Do not push.

## Plan

Goal: give the repo a permutation gate that controls for salary, so a model edge
is measured against the right null.

1. The existing test (`permutation_test.py`) answers "does the model beat a
   random shuffle." Keep it. Add the harder question: "does the model beat
   salary alone."

2. Implement the partial Spearman. Rank `actual`, `projection`, and `salary`.
   Residualize rank(actual) and rank(projection) on rank(salary). Correlate the
   two residual vectors. This is the rank-space partial correlation. It needs no
   distributional assumption and it matches the repo's existing rank-based style.

3. Permute only the actual column. Recompute the partial each draw. The p-value
   is the one-sided tail count plus one over draws plus one. This is the same
   shape as `permutation_p_value` in `permutation_test.py`; reuse its structure.

4. Reuse the paired-frame builder from `permutation_test.py`
   (`_pairs_from_projections`, `_score_week3_join`) so the gate joins the same
   projection file to the same nflverse actuals. Add the salary column to the
   paired frame. Do not duplicate the join logic.

5. Print the four band rows. Add the note the table above shows: the model
   clears the null on the cheap and all bands, and it does not clear the null in
   the premium band.

6. Boundary: a human reads the verdict. No live order. No auto-submit.
