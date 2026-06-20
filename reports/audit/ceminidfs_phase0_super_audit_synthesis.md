# Super audit — CeminiDFS Phase 0 bootstrap

**Mode:** `architecture` + `code-debug` · **Pack:** `prompts/ceminidfs_phase0_super_audit.md` · **Built:** 2026-06-20

| Slot | Channel | Role | Model | Verdict |
|------|---------|------|-------|---------|
| 1 | cursor | agentic-reasoning | parent synthesis | WARN |
| — | — | *(full 5-model council not dispatched — single-pass deep audit)* | — | — |

> Tailored prompt written for future `/super-audit` runs. This synthesis is a **parent-agent pre-council audit** so you can fix P0 items before Phase 1 without waiting on API legs.

---

## Consensus (structural themes)

1. **Schema drift is the #1 compound risk** — `export/canonical.py` + wiki spec disagree with `pipeline/project.py` output; normalize compensates partially but drops player IDs.
2. **Silent failure orchestration will hide broken runs** — fetch/normalize/optimize all swallow exceptions and write stubs or pass-through copies.
3. **Config and manifest infrastructure exists but is not wired** — `load_config()` and `RunManifest` are orphaned; CLI passes `{}` everywhere.
4. **Test coverage is formula-only** — scoring/ITT tested; zero integration tests for the pipeline DAG or normalize ID mapping.
5. **Phase 0 is a valid wiring scaffold** — scoring, normalize, optimize ports are sound; proceed to Phase 1 after P0 fixes.

---

## Findings (ranked by severity)

| Severity | Finding | Evidence | Fix |
|----------|---------|----------|-----|
| **P0** | **Player ID lost in normalize** — salary `Id` → `player_id` in project output, but normalize `SITE_KEYS` looks for `fd_id`/`id` only; auto-id starts at `100000` | `project.py` field `player_id`; `normalize.py` keys `("fd_id", "id", ...)`; live test: Mahomes `Id=1` → pydfs `Id=100000` | Add `player_id` to id keys; or have `project.py` emit `fd_id` per canonical spec |
| **P0** | **Two canonical schemas** — wiki + `canonical.py` vs `project.py` columns | `CANONICAL_FIELDS` vs `project.py` fieldnames | Make `project.py` call `write_canonical_csv()` or emit wiki-required columns |
| **P0** | **Silent stage failures** | `orchestrator/run.py` bare `except Exception` in `_run_fetch`, `_run_normalize`, `_run_optimize` | Fail loud on import errors; log + re-raise on runtime errors; stubs only behind explicit `--allow-stub` flag |
| **P0** | **`optimize` without `normalize` produces fake lineups** | `optimizer_input = normalized_csv if "normalize" in selected_stages else canonical_csv` — canonical is not pydfs format | Enforce stage ordering: require `normalize` before `optimize`, or auto-insert normalize |
| **P1** | **`RunManifest` unused** | `manifest.py` has git_commit/config_sha256; orchestrator writes ad-hoc JSON | Unify on `RunManifest`; record git SHA, config hash, per-stage status |
| **P1** | **Config never loaded in CLI/orchestrator** | `cli.py` passes `config={}`; `load_config()` only used in `data/fetch.py` | Thread `load_config()` through `run_pipeline` and stage handlers |
| **P1** | **Fetch ignores week** | `fetch_schedules/pbp/injuries(season)` only; CLI `--week` discarded except in stub JSON | Phase 1: week-filter schedules; document season-level cache for PBP |
| **P1** | **No integration tests** | Only `test_scoring.py`, `test_implied_totals.py` | Add: salary CSV → project → normalize round-trip; stage-order guard; ID preservation |
| **P1** | **Weather endpoint mislabeled** | `OPEN_METEO_ARCHIVE_URL` constant points to `/v1/forecast` | Rename; add archive/historical endpoint for backtests (Phase 1-D) |
| **P1** | **`pyproject.toml` `all` extra self-reference** | `all = ["ceminidfs[data,optimize,dev]"]` may not resolve on all pip versions | Expand `all` to explicit dependency list |
| **P2** | **ITT spread convention undocumented** | `implied_totals.py` signed spread; `vegas.py` home-perspective `(total±spread)/2` — formulas align but convention not in code comments | Add module-level docstring: home-signed spread convention + link to wiki |
| **P2** | **DST scoring incomplete** | `scoring.py` `_dst_stub_points` — no points-allowed tiers | Defer to Phase 2; document as known gap |
| **P2** | **Tests use sys.path hack** | `sys.path.insert(0, ...)` in test files | Rely on `pip install -e ".[dev]"` + pytest `pythonpath` (already in pyproject) |
| **P2** | **Odds API not implemented** | `vegas.py` schedule-only; `.env.example` has `ODDS_API_KEY` | Phase 1-B deliverable — document as expected |
| **P2** | **No `ruff`/`mypy` in CI** | dev dep present, no workflow | Add when repo pushed to GitHub |

---

## What's working

- **Scoring module** — FD half-PPR / DK full-PPR, yardage bonuses, fumble penalties match standard rules; 9 unit tests pass.
- **ITT math** — `implied_totals` and `vegas` formulas are consistent for home-perspective signed spread (verified: total=47, spread=-3 → 25/22).
- **Normalize port** — flexible column aliasing, FD/DK site support, pass-through ownership/floor/ceil fields.
- **Optimize port** — pydfs wrapper with min salary cap, exposure, stacks; sensible FD/DK defaults.
- **Data fetch cache** — parquet cache pattern with nflreadpy loader fallbacks is a solid Phase 1 foundation.
- **Config loader** — YAML merge + minimal fallback parser; `PROJECT_ROOT` resolves correctly.
- **Wiki alignment** — README/PLAN/ARCHITECTURE link to K125 gambling-wiki concepts; repo named in architecture hub.

---

## Phase 1 readiness gates (do before volume/usage/stats)

- [ ] Single canonical CSV contract — `project.py` → `canonical.py` fields
- [ ] Player ID preserved end-to-end (salary → canonical → pydfs `Id`)
- [ ] Orchestrator fails loud; no silent placeholder lineups in default path
- [ ] `load_config()` wired into `ceminidfs run`
- [ ] Integration test: sample FD salary CSV through `project → normalize` with ID + projection assertions
- [ ] Stage DAG validates `normalize` precedes `optimize`
- [ ] Document spread sign convention in `vegas.py` + `implied_totals.py`

---

## Ranked patch backlog

| P | Patch | Effort | Expected lift |
|---|-------|--------|---------------|
| P0 | Add `player_id` to normalize id keys; map `opponent`→`opp`, `position`→`fd_position` | 30 min | pydfs optimizer matches salary slate |
| P0 | Route `project.py` through `write_canonical_csv()` with wiki schema | 1–2 hr | Eliminates schema fork before Phase 2 |
| P0 | Replace bare `except` with logged re-raise; gate stubs behind flag | 1 hr | Stops false-success runs |
| P0 | Enforce normalize-before-optimize in `_parse_stages` | 15 min | Prevents placeholder lineup trap |
| P1 | Wire `load_config()` + `RunManifest` into orchestrator | 2 hr | Reproducible runs, audit trail |
| P1 | Integration test suite for pipeline DAG | 2 hr | Catches regressions in Phase 1 parallel tracks |
| P1 | Fix weather URL naming + document forecast vs archive | 30 min | Clear Phase 1 weather track |
| P2 | GitHub Actions: pytest + ruff on push | 1 hr | CI safety net post-initial push |

---

## Recommended fix order

1. ID mapping fix in normalize (immediate — breaks optimizer today)
2. Canonical schema unification in project layer
3. Orchestrator fail-loud + stage ordering guard
4. Config/manifest wiring
5. Integration tests
6. Push to GitHub + CI

---

## Metrics to avoid (regime discipline)

- Do **not** benchmark projection accuracy on `source=salary_fppg_placeholder` — it mirrors FD's baked-in FPPG, not your model.
- Do **not** treat placeholder lineup CSV (`note=optimizer_placeholder`) as optimizer validation.
- Do **not** compare ITT across data sources without confirming spread sign convention (home vs away vs favorite-abs).

---

## Unique angle

The **normalize layer masks schema drift** because it flex-maps generic column names — the pipeline appears to work while **silently renumbering every player ID**. pydfs may still build lineups from auto-IDs, but exposures, late swap, and salary-cap joins against the original slate will break. This is the highest-leverage hidden bug in Phase 0.

---

## Overall

**SHIP-WITH-FIXES** — Phase 0 bootstrap is the right shape (layer map, ports, CLI, tests for core math), but **four P0 issues** (ID mapping, schema fork, silent failures, optimize-without-normalize) will compound badly once Phase 2 writes real projections. Fix P0 before starting Phase 1 parallel tracks; the tailored super-audit prompt at `prompts/ceminidfs_phase0_super_audit.md` is ready for a full 5-model council re-run after patches.

**Confidence:** high on P0 findings (reproduced ID bug live); medium on Phase 2 sequencing recommendations.
