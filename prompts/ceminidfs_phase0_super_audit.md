# CeminiDFS Phase 0 SUPER AUDIT — 5-model council (bootstrap)

You are auditor **{{MODEL_SLOT}}** in a **5-model super audit** of the **CeminiDFS** NFL DFS projection pipeline (Phase 0 bootstrap).

**Mode:** `architecture` + `code-debug` · **Readonly** — markdown report only; no edits.

---

## Mission (single sharp question)

Is the **Phase 0 CeminiDFS bootstrap** structurally sound enough to begin Phase 1 (data backbone) without carrying forward schema drift, silent-failure orchestration, or formula/convention bugs that will compound in the projection engine?

Deliver:

1. **Verdict** PASS/WARN/FAIL on current Phase 0 posture
2. **What's working** vs **what isn't** (code, schema, orchestration, tests, config, wiki alignment)
3. **Ranked patch backlog** (P0 before Phase 1, P1 during Phase 1) — smallest diffs first
4. **Canonical schema alignment** — does `pipeline/project.py` output match `export/canonical.py` + gambling-wiki integration spec?
5. **Phase 1 readiness gates** — explicit checklist before building volume/usage/stats layers
6. **Regime discipline** — Phase 0 placeholder vs Phase 2 projection engine; salary-FPPG stub ≠ DIY model output

---

## Context — project state (2026-06-20)

| Fact | Value |
|------|-------|
| Repo | `github.com/cemini23/CeminiDFS` — Phase 0 bootstrap |
| Workspace | `/Users/claudiobarone/Desktop/projects/CeminiDFS` |
| Wiki hub | `@gambling-wiki/concepts/diy-nfl-dfs-model-architecture.md` (K125) |
| Integration spec | `@gambling-wiki/concepts/dfs-pipeline-integration-spec.md` |
| Pipeline DAG | `fetch → project → normalize → optimize` |
| Tests | 9 passing — `scoring`, `implied_totals` only |
| Optional deps | `nflreadpy`, `pyarrow`, `pydfs-lineup-optimizer` (not required for core install) |

### Phase 0 shipped

- Package layout (`src/ceminidfs/`), `pyproject.toml`, CLI (`ceminidfs fetch|project|normalize|optimize|run`)
- `models/scoring.py` — FD half-PPR + DK full-PPR + yardage bonuses + DST stub
- `models/implied_totals.py` — ITT formulas + game environment z-score placeholder
- `export/normalize.py` + `export/optimize.py` — ported from gambling-wiki scripts
- `export/canonical.py` — canonical schema writer (not wired into pipeline)
- `pipeline/project.py` — **placeholder** projections from salary CSV FPPG
- `orchestrator/run.py` — stage DAG + JSON manifest
- `data/fetch.py` — nflreadpy parquet cache wrapper
- `data/vegas.py` — schedule spread/total → implied team totals
- `data/weather.py` — Open-Meteo hourly fetch stub
- `config/nfl_dfs.yaml` + `config.py` with YAML merge

### Phase 0 NOT shipped (planned Phase 1–2)

- `models/volume.py`, `models/usage.py`, `models/stats.py`
- `data/stadiums.py`, Odds API live Vegas, salary schema parser
- `pipeline/backtest.py`, `RunManifest` integration (`manifest.py` exists but unused)
- End-to-end test with real FanDuel salary CSV + pydfs optimize

---

## Context — canonical schema contract (wiki)

**Required fields** (`dfs-pipeline-integration-spec.md`):

`slate_id`, `player_key`, `fd_id`, `fd_position`, `fd_salary`, `fd_projection`, `dk_id`, `dk_position`, `dk_salary`, `dk_projection`, `team`, `opp`, `game`, `injury_status`

**Current `project.py` output fields:**

`season`, `week`, `player_id`, `name`, `player_name`, `team`, `opponent`, `position`, `salary`, `projection`, `baseline_fppg`, `source`

**Mismatch risk:** normalize layer maps `projection` → FPPG but may not resolve `player_id` → pydfs `Id` (auto-id fallback at 100000).

---

## Context — orchestration hazards

| Hazard | Location | Risk |
|--------|----------|------|
| Bare `except Exception` → stub/placeholder | `orchestrator/run.py` `_run_fetch`, `_run_normalize`, `_run_optimize` | Silent success on failure |
| `optimize` without `normalize` | `run_pipeline` stage DAG | Canonical CSV fed to pydfs → placeholder lineups |
| Empty config `{}` from CLI | `cli.py` all handlers | `load_config()` never applied to runs |
| `RunManifest` vs inline manifest | `manifest.py` vs `orchestrator/run.py` | Two manifest systems; git SHA / config hash not tracked |
| Fetch ignores `--week` | `data/fetch.py`, `_run_fetch` | Week-scoped fetch not implemented |
| ITT spread sign convention | `implied_totals.py` vs `vegas.py` | Must document home-perspective signed spread |

---

## Code / data paths (READ these in workspace)

```
/Users/claudiobarone/Desktop/projects/CeminiDFS/PLAN.md
/Users/claudiobarone/Desktop/projects/CeminiDFS/README.md
/Users/claudiobarone/Desktop/projects/CeminiDFS/docs/ARCHITECTURE.md
/Users/claudiobarone/Desktop/projects/CeminiDFS/config/nfl_dfs.yaml
/Users/claudiobarone/Desktop/projects/CeminiDFS/pyproject.toml
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/cli.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/orchestrator/run.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/pipeline/project.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/export/canonical.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/export/normalize.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/export/optimize.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/models/scoring.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/models/implied_totals.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/data/fetch.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/data/vegas.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/data/weather.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/config.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/src/ceminidfs/manifest.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/tests/test_scoring.py
/Users/claudiobarone/Desktop/projects/CeminiDFS/tests/test_implied_totals.py
```

Wiki cross-read (if available):

```
/Users/claudiobarone/Desktop/projects/Gambling wiki/wiki/concepts/diy-nfl-dfs-model-architecture.md
/Users/claudiobarone/Desktop/projects/Gambling wiki/wiki/concepts/dfs-pipeline-integration-spec.md
```

---

## Data pack files (READ these paths)

```
{pack_index}
```

---

## Prior audit consensus

None — first super-audit of CeminiDFS Phase 0.

---

## Required output format

### Verdict
PASS | WARN | FAIL — one line why

### Findings
| Severity | Finding | Evidence | Fix |
|----------|---------|----------|-----|

### Phase 1 readiness recommendation
- **Schema contract** — single canonical writer path; field rename map
- **Orchestration** — fail-loud vs stub policy per stage
- **Test gates** — minimum integration tests before Phase 2
- **Config wiring** — how `nfl_dfs.yaml` should reach CLI/orchestrator
- **Metrics to avoid** — what NOT to benchmark on salary-FPPG placeholder

### Root cause
One paragraph on the biggest structural risk — or "insufficient evidence" + what to inspect next.

### Ranked patch backlog
| P | Patch | Effort | Expected lift |
|---|-------|--------|---------------|

### Unique angle
One thing other auditors might miss (DFS-specific: ID alignment, site schemas, ITT sign, pydfs importer headers)

### Confidence
high | medium | low

---

## Regime boundaries

- **Phase 0 placeholder** (`source=salary_fppg_placeholder`) is a **wiring test only** — not a projection accuracy benchmark
- **Stokastic/FantasyLabs** = benchmark-only; never a runtime dependency
- **FanDuel-primary** — DK path exists in normalize/optimize but secondary until Phase 3
- **nflverse CC-BY 4.0** — attribution required in docs/outputs when shipping public artifacts
- Do not judge Phase 2 stat-engine quality from Phase 0 FPPG passthrough

---

## Constraints

- Smallest diff wins — avoid premature Monte Carlo / ownership before volume/usage/stats exist
- No paywalled data sources (FantasyLabs routes, PFF, etc.)
- `pydfs-lineup-optimizer` is borrow-only (MIT) — keep normalize headers aligned with importer
- Secrets in `.env` only (`ODDS_API_KEY`) — never commit
- Phase 1 should not fork a second canonical schema

---

## Already ruled out

- Missing projection engine modules (volume/usage/stats) — expected Phase 2, not a Phase 0 defect
- No GitHub push yet — tracked in PLAN.md checklist, not a logic bug
- Weather stadium table not built — Phase 1-C deliverable
