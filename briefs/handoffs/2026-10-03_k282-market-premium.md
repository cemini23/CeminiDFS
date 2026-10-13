# SIP handoff — K282 market-ordered premium projections

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Lane

hard — Grok CLI implements. Plan below is written in the parent session.

## Context

K281 tested a guard that blended premium projections toward a prior-only salary
baseline. It failed: the premium band got worse in 2 of 3 weeks. The guard is
off. See `reports/audit/k281-premium-guard.md`.

The K281 anchor was too weak. The raw numbers say the live market is the better
premium signal.

2026 weeks 1-3, band `fd_salary >= 7000`, Spearman against actual points:

| Week | n | model | FanDuel salary |
|------|---|-------|----------------|
| 1 | 38 | +0.283 | **+0.368** |
| 2 | 44 | −0.051 | **+0.254** |
| 3 | 45 | +0.264 | **+0.451** |

Salary wins all three weeks, and in week 2 the model is worse than random.

FanDuel salary is the market's implied projection. Where the model is noise, the
market should order the slate. Build that as an optional mode and prove it on
lineups, not only on rank correlation.

## Success criteria

1. **One flag, three modes.** Replace `--premium-guard` (a `store_true` flag)
   with `--premium-mode {off,baseline,market}` on both `ceminidfs project` and
   `ceminidfs run`. Default `off`. `baseline` is the existing K281 behavior
   unchanged. `market` is new. `--premium-guard` may be dropped; it shipped today
   and is off.

2. **`market_premium_projection(rows, *, threshold=7000)`** in
   `src/ceminidfs/models/premium_guard.py`. It is non-parametric and fits nothing.
   - Player rows with `fd_salary < threshold` are returned unchanged.
   - Take the premium rows. Order them by `fd_salary` descending, then by the
     model projection descending to break salary ties.
   - Take the premium rows' model projections. Sort them descending.
   - Assign the sorted projections onto the ordered rows, so the top salary gets
     the top projection and so on.
   - The premium projections keep their multiset. Only their order changes. The
     ordering key is the market; the model only breaks salary ties.

3. **`premium_mode` config.** Carry the chosen mode in the runtime config. The
   guard branch in `src/ceminidfs/pipeline/project.py` dispatches on the mode.
   `off` must be a byte-identical no-op.

4. **Rank report.** Extend `src/ceminidfs/pipeline/premium_guard_backtest.py` to
   report, per week 1, 2, 3: `n`, `partial_off`, `partial_baseline`,
   `partial_market`, and the deltas.

5. **Lineup report — this is the acceptance test.** For 2026 weeks 1, 2, 3, build
   lineups from that week's canonical projections under each mode, score them
   against the week's actual points, and report total points per mode per week.
   Use the repo's own optimizer path and the real FanDuel salary files in
   `data/slates/`. Rank correlation is a proxy; the lineup total is the result.
   Write both reports to `reports/audit/k282-market-premium.md`.

6. **Decision rule, enforced in the report.** Recommend `market` ONLY if its
   lineup total is highest in at least two of the three weeks AND it never loses
   to `off` by more than 2 percent in the remaining week. State the outcome in
   one plain sentence. If `market` does not meet the rule, say it is NOT
   recommended and leave the default at `off`.

7. **`tests/test_premium_market.py`** with at least:
   - Premium rows come out in descending salary order.
   - The premium projection multiset is identical before and after.
   - A salary tie keeps the model's order.
   - Rows below the threshold are untouched.
   - `off` mode is a byte-identical no-op on a small fixture.

## Verify

- `.venv/bin/python -m pytest -q tests/test_premium_market.py tests/test_premium_guard.py`
- `.venv/bin/python -m ceminidfs.pipeline.premium_guard_backtest`
- `.venv/bin/ruff check src tests`
- `grep -n "premium-mode" src/ceminidfs/cli.py`
- `test -f reports/audit/k282-market-premium.md`

## NEVER

- Do not overwrite `runs/2026_week_1`, `runs/2026_week_2`, or `runs/2026_week_3`.
  Write scratch outputs under `reports/audit/` or a temp directory.
- Do not make any mode default-on.
- Do not fit any parameter on the target week or a later week.
- Do not change the salary, ownership, volume, usage, stats, or scoring models.
- Do not edit `late_swap_oracle.py`, `late_swap_replay.py`, `permutation_gate.py`,
  or `permutation_test.py`.
- Do not claim an edge the lineup report does not show.
- Do not rewrite the existing sections of `briefs/2026-10-03_k280-measure.md`.
- No network scrape. No paid-site data. No live order.
- Do not commit. Do not push.

## Plan

Goal: let the market order the premium band, and prove it on lineups.

1. The model adds real signal for cheap players and none for premium players.
   So change only the premium band, and only its order.

2. Use a rank-preserving permutation, not a fitted curve. Order premium rows by
   salary, order their projections by value, and re-attach. This keeps the
   model's premium point distribution, so the optimizer's salary-value trade-off
   still has a sane spread, while the ordering becomes the market's. It fits
   nothing, so it cannot overfit three weeks.

3. Break salary ties with the model. Within one price tier the market has no
   preference, so the model's order is the best available there. This is the one
   place the model keeps its say in the premium band.

4. Keep the mode off by default. Reuse the K281 plumbing: the
   `fd_projection_unguarded` column and the config dispatch already exist.

5. Prove it twice. First the rank report, which should show the premium partial
   rise to the salary number. Then the lineup report, which is the real test:
   the optimizer spends real salary under a real cap, so an order that looks good
   in rank space can still build worse lineups.

6. Apply the decision rule. Three weeks is a small sample. A tie is not a win.
   If `market` does not clearly help, report that and leave the default at `off`.

7. Boundary: a human types the ticket. No live order. No auto-submit.
