# Phase 3-D — Opus 4.8 Execution Plan

> **Goal:** Close Phase 3 exit criteria — **150 FanDuel lineups from DIY projections** on a manual salary slate via `ceminidfs run --stages all`.

## Context

- Phases 0–2, 4 complete. Export layer (canonical, normalize, optimize) exists.
- `run_pipeline()` orchestrates fetch → project → normalize → optimize with RunManifest.
- DIY projections wire through `project_week()` when `projection_mode=diy|auto` and week cache exists.
- **Gap:** No full-slate e2e test; no lineup validation; DEF/DST projections not emitted by stat-first stack; CI lacks `[optimize]` extra.

## Parallel tracks (GPT 5.5)

| Track | Owner | Deliverable |
|-------|-------|-------------|
| **P3-D-A** | Subagent 1 | Synthetic FanDuel slate fixture + week PBP/vegas cache helpers |
| **P3-D-B** | Subagent 1 | `tests/test_e2e_run.py` — full pipeline DIY → 150 lineups (pytest.importorskip pydfs) |
| **P3-D-C** | Subagent 2 | `orchestrator/validate.py` — lineup CSV validation (count, columns, non-empty slots) |
| **P3-D-D** | Subagent 2 | Manifest exit-criteria fields + `run_pipeline` records projection_source, lineup_count |

## P3-D-A — Synthetic fixture

**File:** `tests/fixtures/synthetic_fd_slate.csv`

- Main-slate shape: **2 teams** (KC vs BUF), **≥40 players**
- Positions: 2 QB, 8 RB, 12 WR, 4 TE, 2 DEF (+ FLEX-eligible depth)
- Salaries sum-friendly for FD $60k cap / $59.4k min rule
- Names/teams align with `tests/test_project_engine.py` synthetic PBP ids (`gsis_mahomes`, `gsis_kelce`, etc.)
- Include `FPPG` column for DEF fallback only

**Helper:** `tests/fixtures/synthetic_cache.py`

- `write_synthetic_week_cache(tmp_path, season=2024, week=4)` — vegas.parquet + multi-week pbp.parquet
- Reuse/extend `_synthetic_pbp()` patterns from test_project_engine

## P3-D-B — E2E integration test

**File:** `tests/test_e2e_run.py`

```python
pydfs = pytest.importorskip("pydfs_lineup_optimizer")
```

Flow:
1. Write synthetic salary + week cache to tmp_path
2. Monkeypatch `engine.week_cache_dir` and optionally `fetch._cache_dir` if needed
3. `run_pipeline(2024, 4, salary, stages="project,normalize,optimize", config={projection_mode: "diy", count: 150, work_dir: ...})`
4. Assert manifest stages complete
5. Assert lineups.csv has **150 data rows** + header
6. Assert canonical CSV has DIY projections (Mahomes fd_projection > 0, != salary FPPG if distinct)

**DEF handling in project.py (minimal):**

After DIY merge, fill `fd_projection` for rows where `fd_position` in (`DEF`,`DST`) and projection empty, using `salary_fppg` from parsed salary row (stored in row dict during parse — may need to pass through canonical write or fill before write).

## P3-D-C — Lineup validation

**File:** `src/ceminidfs/orchestrator/validate.py`

```python
def validate_lineups_csv(path, site="fanduel", expected_count=150) -> dict
```

- Check file exists, row count == expected_count
- Header matches `LINEUP_HEADERS` from export/optimize.py
- No empty required slots in any lineup row
- Return summary dict for manifest

## P3-D-D — Orchestrator + CI

**Changes to `orchestrator/run.py`:**
- After optimize, call `validate_lineups_csv`
- Record in manifest: `lineup_count`, `projection_mode`, `projection_source` (`diy`|`fppg`|`hybrid`)
- Fail pipeline if lineup_count < expected count

**CI:** `.github/workflows/ci.yml` → `pip install -e ".[dev,data,optimize]"`

**Docs:** PLAN.md Phase 3-D done; README status Phase 3 complete

## Exit criteria checklist

- [ ] `pytest tests/test_e2e_run.py` passes locally with `[optimize]`
- [ ] 150 lineups written from DIY projections on synthetic slate
- [ ] Manifest JSON includes lineup_count and projection_source
- [ ] CI installs optimize extra and runs e2e test

## Out of scope (Phase 5)

- Monte Carlo, ownership model, late swap
