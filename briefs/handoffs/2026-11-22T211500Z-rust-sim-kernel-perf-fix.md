# SIP handoff — fix the Rust sim kernel performance and NaN behaviour

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Context

The first pass landed `rust/sim_kernel/`, `src/ceminidfs/export/_sim_kernel.py`, and the `sim_rerank.py` wiring. Parity is correct and the full suite passes. Two defects remain.

Measured baseline (`briefs/sim_hotloop_baseline.json`, pure Python): `runtime_s = 0.07215`.
Measured after port (`briefs/sim_hotloop_after.json`, Rust): `runtime_s = 0.10825`.
Scores sha256 is identical, so parity holds. The port is about 1.5x SLOWER. That is not acceptable.

## Defect 1 — the kernel copies a 40 MB matrix and fully sorts 5M floats

In `rust/sim_kernel/src/lib.rs`:

- `owned_matrix()` calls `slice.to_vec()`, which copies the whole `(500, 10000)` float64 matrix on every call.
- `quantile_linear()` clones the input and does `sort_unstable_by(total_cmp)` over the pooled 500 x 10000 = 5,000,000 values. numpy uses `np.partition` (introselect), which is O(n), not O(n log n).

Fixes:

1. Delete `to_vec()`. Compute directly from the borrowed `&[f64]` slice while the GIL is held. Remove `py.detach` from `lineup_totals` and `leverage_scores`; the borrow cannot outlive the call safely across detach, and a single-threaded CLI does not need the GIL released.
2. Replace the full sort with partial selection. Add `pub fn quantile_linear_in_place(values: &mut [f64], q: f64) -> f64` that keeps the NaN scan, then uses `select_nth_unstable_by(lo, f64::total_cmp)` and, when `hi != lo`, `select_nth_unstable_by(hi, f64::total_cmp)` on the same buffer. Interpolate exactly as today. `leverage_scores_owned` passes its owned `flat` buffer to the in-place variant. `quantile_linear(&[f64], q)` stays as the public copying wrapper.
3. Keep the `lineup_totals`/`quantile_linear` Python API and signatures unchanged.

## Defect 2 — NaN behaviour changed

The old pure-Python `leverage_lineup_scores` with a NaN in the matrix produced `threshold = nan` and then `(totals >= nan).mean() == 0.0`, so every score was `0.0`. The new code early-returns `NaN` scores, in both branches. That is an unrequested behaviour change.

Fix: remove the `np.isnan(threshold)` early return in `sim_rerank.py`, and remove the `threshold.is_nan()` early return in `leverage_scores_owned`. A NaN threshold must yield 0 hits and therefore `0.0` scores, matching the old behaviour. `quantile_linear` still propagates NaN.

Update `tests/test_sim_kernel_parity.py` so the NaN case asserts scores equal `0.0` and the threshold is `NaN`, on both the kernel and Python paths.

## Success criteria

1. `rust/sim_kernel/src/lib.rs`: no matrix copy; no full sort; in-place partial selection; NaN threshold gives 0.0 scores.
2. `src/ceminidfs/export/sim_rerank.py`: no NaN early return; the Python fallback path is byte-identical to the pre-port behaviour.
3. Rust unit tests add: quantile of a 1-element slice; quantile of a 2-element slice at q=0.5; `quantile_linear_in_place` equals `quantile_linear` on a 1000-element pseudorandom buffer for q in {0.0, 0.01, 0.5, 0.99, 1.0}.
4. Parity tests still pass at `atol=1e-9, rtol=0`, with 0 skipped.
5. `scripts/bench_sim_hotloop.py`: also print `maxrss_kb` from `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` (bytes on macOS; convert to KB) because `tracemalloc` cannot see Rust allocations. Keep the existing keys.
6. The Rust run must be FASTER than `0.07215 s`. If it is not, report the measured number honestly and add a per-phase split (Python index/ownership prep vs kernel call) inside the bench output under `phases_s` so the next iteration can target the right phase.

## Verify

```bash
cargo test --release --manifest-path rust/sim_kernel/Cargo.toml
bash scripts/build_sim_kernel.sh
python3 scripts/check_rust_licenses.py
python3 -m pytest tests/test_sim_kernel_parity.py -vv
python3 -m pytest tests/test_sim_rerank.py tests/test_ownership.py -q
python3 scripts/bench_sim_hotloop.py
FAST_ANYTHING_DISABLE=1 python3 scripts/bench_sim_hotloop.py
```

Gate: cargo tests pass; parity file reports collected > 0 and skipped == 0; both bench runs print one JSON line and the Rust line has the lower `runtime_s`; save them to `briefs/sim_hotloop_after.json` and `briefs/sim_hotloop_baseline.json` respectively.

## NEVER

- Do not change `src/ceminidfs/models/simulate.py`.
- Do not add a dependency.
- Do not use `unsafe` to move a borrow across `py.detach`.
- Do not change public Python signatures.
- Do not modify existing tests other than the NaN case in `tests/test_sim_kernel_parity.py`.
- Do not commit the `.so` or `target/`.
- Do not run `git commit`, `git push`, or `git reset`.
- No network. No site logins. No live contest actions.

## Plan

1. Read `rust/sim_kernel/src/lib.rs`, `scripts/bench_sim_hotloop.py`, and the NaN case in `tests/test_sim_kernel_parity.py`.
2. Apply Defect 1 and Defect 2 fixes.
3. Add the three Rust unit tests.
4. Rebuild, run Verify, and save both bench JSON files.
5. Report: cargo output, pytest counts, both runtime numbers, the speedup ratio, and any remaining overhead you can name from `phases_s`.
