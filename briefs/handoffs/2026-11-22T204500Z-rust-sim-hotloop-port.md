# SIP handoff — Rust port of the GPP simulation/ownership scoring hot loop

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Context

Reference pattern: `fast-anything` (MIT) — profile a real run, capture real calls, port ONE hot function, prove parity within 1e-9, keep a kill switch.

Wiki page: `/Users/claudiobarone/Projects/OSINT WORKSPACE/wiki/game-dev/entities/tools/fast-anything.md`

`~/Projects/Game time/docs/fast_anything_spike.md` does NOT exist (checked 2026-11-22). Game time has no Rust crate. Do not block on it: follow the wiki page and the API contract below.

Toolchain present: `cargo 1.95.0`, `rustc 1.95.0`, Python 3.12.5, numpy 2.2.6, pytest 8.4.2. `maturin` is NOT installed and must not be required.

## Problem

The GPP contest loop scores every candidate lineup (500+ per slate) against a simulated score matrix (players x 10k draws). Today that loop is Python: one fancy-index plus one `np.quantile` per lineup in `src/ceminidfs/export/sim_rerank.py`, plus a second pass for the pooled threshold. This is the compute-bound inner loop for a full Sunday main slate. Move it to Rust behind PyO3.

## Scope decisions (do not relitigate)

1. **Port the scoring kernel only.** `leverage_lineup_scores` and `score_lineup` consume a matrix that numpy already produced. Do NOT port `simulate_fd_points` / `sample_regime_gmm` RNG. numpy `default_rng` PCG64 + ziggurat parity in Rust is a separate risk; the random draw is not the Python-level hot loop.
2. **Keep in Python:** nflverse ingestion, Open-Meteo weather, `simulate.py` RNG, ownership lookups, `pydfs-lineup-optimizer` orchestration, CSV/IO.
3. **Pure arithmetic kernel.** No RNG in Rust. This makes exact parity reachable.
4. **Kill switch.** `FAST_ANYTHING_DISABLE=1` forces the Python implementation at import time.

## Success criteria

1. New crate `rust/sim_kernel/` (Cargo.toml, src/lib.rs), `crate-type = ["cdylib"]`, PyO3 with `extension-module` + `abi3-py311`. Dependency allowlist: `pyo3` (MIT/Apache-2.0) and `numpy` (BSD-2-Clause). Nothing else without a license in the allowlist.
2. Kernel functions exposed as `ceminidfs._sim_kernel_rust`:
   - `lineup_totals(matrix, groups) -> (flat: Vec<f64>, lengths: Vec<usize>)` — for each index group, sum matrix rows in the listed order, iteration-major, matching `matrix[indexes, :].sum(axis=0)`.
   - `quantile_linear(values: Vec<f64>, q: f64) -> f64` — numpy default `method="linear"`: `h = q*(n-1)`, interpolate between `floor(h)` and `ceil(h)`. `NaN` anywhere propagates `NaN`. Empty input returns `NaN`.
   - `leverage_scores(matrix, groups, ownership_fractions, top_fraction, exponent) -> (scores: Vec<f64>, threshold: f64)` — fused: per-lineup totals, pooled threshold `quantile_linear(pooled, 1-top_fraction)`, per-lineup `mean(totals >= threshold) / ownership_fraction ** exponent`. Empty `groups` returns `(vec![], 0.0)`.
   `matrix` is a C-contiguous float64 array of shape `(n_players, n_iterations)`.
3. New Python wrapper `src/ceminidfs/export/_sim_kernel.py`:
   - Imports `ceminidfs._sim_kernel_rust` in a `try/except ImportError`.
   - `SIM_KERNEL_AVAILABLE` flag; `use_sim_kernel()` returns `False` when the env var `FAST_ANYTHING_DISABLE` is `1` or the extension is missing.
   - Accepts `numpy.ndarray` and `list[list[int]]`; converts once with `np.ascontiguousarray(..., dtype=np.float64)`.
4. `src/ceminidfs/export/sim_rerank.py` uses the kernel when available:
   - `leverage_lineup_scores` computes ownership fractions exactly as today (per lineup, geometric mean with the 1e-4 floor and `/100`), then calls `leverage_scores` once.
   - `score_lineup` uses `lineup_totals` + `quantile_linear` when available.
   - When unavailable, the existing code path runs unchanged. Public signatures and return types do not change.
5. `scripts/build_sim_kernel.sh` builds with `cargo build --release --manifest-path rust/sim_kernel/Cargo.toml` and copies `target/release/libsim_kernel_rust.dylib` to `src/ceminidfs/_sim_kernel_rust.so`. It is idempotent and prints the destination path.
6. `scripts/bench_sim_hotloop.py`:
   - Loads `data/slates/2026-11-22_fd_sun.csv` (500 rows, cached, no network).
   - Builds a simulated matrix with `simulate_fd_points(method="team_shock", n_iterations=10000, seed=20261122)` after adapting the slate columns to `player_id`, `fd_projection`, `team`, `position`.
   - Generates 500 deterministic 9-player lineups from `numpy.random.default_rng(7)` (QB/RB/RB/WR/WR/WR/TE/FLEX/DEF position counts from the slate; duplicates allowed only if the position pool is too small).
   - Times ONLY `leverage_lineup_scores`, reports `{"runtime_s", "peak_kb" (tracemalloc), "matrix_sha256", "scores_sha256", "kernel": "rust"|"python"}` as one JSON line.
   - Runs the same workload twice and keeps the second run.
7. `scripts/check_rust_licenses.py` reads `cargo metadata --format-version 1 --manifest-path rust/sim_kernel/Cargo.toml` and exits non-zero unless every package license expression maps to MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, or Unicode-3.0.
8. `tests/test_sim_kernel_parity.py` — NO skips. The test imports the extension and fails hard with a clear message if it is missing (`run scripts/build_sim_kernel.sh`). Cases:
   - Fixture slate from `tests/fixtures/synthetic_fd_slate.csv`, 2000 iterations, seed 1234, 40 deterministic lineups: Rust scores and threshold equal Python within `atol=1e-9, rtol=0`.
   - Cached slate `data/slates/2026-11-22_fd_sun.csv`, 1000 iterations, seed 20261122, 50 lineups: same tolerance.
   - Edge cases vs Python reference: empty lineup list; single lineup; one iteration; duplicate player rows in one lineup; ownership fraction at the 1e-4 floor; a matrix containing `NaN` (both sides return `NaN` scores); quantile `q=0.0` and `q=1.0`.
   - `score_lineup` matches the Python reference within 1e-9.
   - Kill switch: with `FAST_ANYTHING_DISABLE=1`, `use_sim_kernel()` is `False` and results still match the Python reference.
9. `.gitignore` gains `rust/sim_kernel/target/` and `src/ceminidfs/_sim_kernel_rust*.so`.
10. Baseline saved to `briefs/sim_hotloop_baseline.json` BEFORE wiring the kernel, and a post-port record saved to `briefs/sim_hotloop_after.json`. Report the speedup ratio (python runtime / rust runtime) in the final message.

## API contract details

- Summation order: index group order, then iteration index. Group sizes are ~9, so pairwise vs naive summation differs well under 1e-9; assert with `atol=1e-9`.
- `np.quantile` on a pooled vector of 500 x 10000 = 5,000,000 floats: sort a copy in Rust (`sort_unstable_by(f64::total_cmp)`) then interpolate. Do not use partial select; parity is easier to prove on a full sort.
- Tail probability uses `totals >= threshold` on the same float values returned by the kernel; do not round.
- Ownership fraction formula (unchanged): `exp(mean(log(max(pct/100, 1e-4))))`; empty → `1.0`.
- GIL: release it (`py.allow_threads`) for the matrix work when the inputs are already copied into Rust-owned slices.

## Verify

```bash
cargo test --release --manifest-path rust/sim_kernel/Cargo.toml
bash scripts/build_sim_kernel.sh
python3 scripts/check_rust_licenses.py
python3 -m pytest tests/test_sim_kernel_parity.py -vv
python3 -m pytest tests -q
```

Gate: the parity test command must report collected > 0 and skipped == 0. The full suite must have no new failures. Record the exact executed/skipped counts and the before/after runtime in the final report.

## NEVER

- Do not type or read site passwords. No FanDuel/Underdog credentials.
- Do not submit, late-swap, or click anything on a live site.
- Do not run network commands against paid sites (Stokastic, FantasyLabs).
- Do not modify `simulate.py` RNG behavior, seeds, or `_normal_ppf` fallbacks.
- Do not change existing public function signatures or return types.
- Do not modify existing tests except to keep them passing.
- Do not add a dependency with a license outside MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, Unicode-3.0.
- Do not commit the built `.so` or `target/`.
- Do not run `git commit`, `git push`, or `git reset`.
- Do not touch `data/cache/`, `runs/`, `artifacts/`, `outputs/`, or any file with secrets.
- Do not make `maturin` or `pip install` of Rust tooling a build requirement.

## Plan

1. Read `src/ceminidfs/export/sim_rerank.py` (lines 127–252), `src/ceminidfs/models/simulate.py` (for `simulate_fd_points` inputs), `tests/test_sim_rerank.py`, and `tests/fixtures/synthetic_fd_slate.csv`. Note the exact Python math to replicate.
2. Write `scripts/bench_sim_hotloop.py` and run it with `FAST_ANYTHING_DISABLE=1` against the cached 2026-11-22 slate (10k iterations). Save the JSON to `briefs/sim_hotloop_baseline.json`. Record matrix sha256 and runtime.
3. Create `rust/sim_kernel/Cargo.toml` and `rust/sim_kernel/src/lib.rs` with the three functions and Rust unit tests for `quantile_linear` (`[1,2,3,4]` at q=0.5 -> 2.5; q=0 -> 1; q=1 -> 4; NaN propagation).
4. Create `scripts/build_sim_kernel.sh`; build; confirm `src/ceminidfs/_sim_kernel_rust.so` loads from `python3 -c "import ceminidfs._sim_kernel_rust"`.
5. Create `src/ceminidfs/export/_sim_kernel.py` with the availability flag and kill switch.
6. Wire `sim_rerank.py` to call the kernel when available. Keep the Python path byte-identical to today.
7. Write `tests/test_sim_kernel_parity.py` with all listed cases. No `skipif`. No `pytest.importorskip`.
8. Write `scripts/check_rust_licenses.py`; run it.
9. Add `.gitignore` entries.
10. Run the full Verify block. Run `bench_sim_hotloop.py` again with `FAST_ANYTHING_DISABLE` unset, save `briefs/sim_hotloop_after.json`, compute the speedup.
11. Report: files created/changed, cargo test output, pytest executed/skipped counts, license check output, before/after runtime and speedup, and any residual risk (summation order, macOS-only build script, extension not installed on another machine).
