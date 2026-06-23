# K127 — Opus 4.8 Execution Plan

> **Goal:** Evaluate **sportsdataverse-py** (MIT) as unified NFL fetch client vs incumbent nflreadpy; smoke test, schema gap table, latency/completeness benchmark, adopt/defer verdict.
>
> **Brief:** `briefs/2026-06-23_k127-sportsdataverse-py-adopt.md`
>
> **K126 status:** Complete (coherence-risk layer enabled). Out of scope for K127.

## Context

- Incumbent: `ceminidfs.data.fetch` → nflreadpy → nflverse parquet cache
- Candidate: `sportsdataverse.nfl.load_nfl_pbp` / `load_pbp` — same nflverse release parquets per upstream docs
- **Do not replace fetch path in this sprint** — evaluation only unless benchmark proves ≥95% critical-column coverage AND simpler maintenance

## Stage-2 critical columns (PBP)

Columns CeminiDFS projection engine reads (directly or via aliases):

| Group | Columns |
|-------|---------|
| Keys | `season`, `week`, `game_id`, `play_id`, `posteam`, `defteam` |
| Play flags | `pass`, `pass_attempt`, `rush`, `rush_attempt`, `sack`, `qb_hit`, `complete_pass` |
| Player IDs | `passer_player_id`, `rusher_player_id`, `receiver_player_id` |
| Player names | `passer_player_name`, `rusher_player_name`, `receiver_player_name` |
| Yards/stats | `air_yards`, `passing_yards`, `rushing_yards`, `receiving_yards`, `yards_gained`, `interception`, `touchdown` |
| Volume/pace | `game_seconds_remaining`, `wp`, `qtr` |
| Defense/coherence | `epa`, `play_type`, `desc`, `yardline_100` |

Schedules/injuries are separate fetchers — benchmark PBP only for P0.

## Parallel tracks

| Track | Agent | Deliverable |
|-------|-------|-------------|
| **K127-A** | GPT 5.5 | `pip install sportsdataverse`; smoke module + tests |
| **K127-B** | Kimi K2.5 | Gap table doc + ARCHITECTURE footnote |
| **K127-C** | GPT 5.5 | Benchmark harness + CLI + JSON report |
| **K127-D** | Kimi K2.5 | Adopt/defer verdict section + brief staging note |

## K127-A — Smoke test

**New:** `src/ceminidfs/data/sportsdataverse_smoke.py`

```python
def load_sdv_pbp_sample(season: int) -> pd.DataFrame  # sportsdataverse.nfl.load_nfl_pbp, return_as_pandas=True
def smoke_fetch_pbp(season: int) -> dict[str, Any]   # rows, cols, elapsed_sec, error
```

**Extend:** `pyproject.toml`

```toml
[project.optional-dependencies]
eval = ["sportsdataverse>=0.0.60", "nflreadpy>=0.1.0", "pyarrow>=14.0"]
```

Keep `data` extra unchanged (nflreadpy only for prod).

**Tests:** `tests/test_sportsdataverse_smoke.py`

- Mock SDV import if unavailable; skip with `pytest.importorskip("sportsdataverse")` for live test
- Unit test critical-column presence checker on synthetic frames

## K127-B — Gap table

**New:** `docs/sportsdataverse-eval.md`

Sections:
1. Tool summary (MIT, nflverse release lineage)
2. Critical-column coverage table (% present, dtype match notes)
3. SDV-only extras (NGS, participation) — future P2 value
4. Rejected tools from same eval batch (jjesse, yfs-api, PM bot) — one line each

**Extend:** `docs/ARCHITECTURE.md` — "Fetch posture" subsection: nflreadpy prod, SDV eval doc link

## K127-C — Benchmark

**New:** `src/ceminidfs/pipeline/sdv_benchmark.py`

```python
STAGE2_CRITICAL_COLUMNS = [...]
def critical_column_coverage(df) -> dict[str, bool]
def coverage_pct(df) -> float
def benchmark_pbp_fetch(season: int, week: int | None) -> dict  # nflreadpy vs sdv timing + rows + coverage
```

Compare on season 2025 (cached nflreadpy OK) or 2024 if available. Week filter optional for slate row count.

**CLI:** `ceminidfs sdv-benchmark --season 2025 [--week N] --out reports/sdv_benchmark_2025.json`

No network in CI — mock or skip.

**Tests:** `tests/test_sdv_benchmark.py` — coverage math on synthetic DataFrames

## K127-D — Adopt/defer verdict

In `docs/sportsdataverse-eval.md`:

| Criterion | Threshold | Result |
|-----------|-----------|--------|
| Critical column coverage | ≥95% | fill from benchmark |
| Row count parity | ±1% vs nflreadpy same season | fill from benchmark |
| Latency | informational only | fill from benchmark |

**Verdict logic:**
- **Adopt** (future sprint): if coverage ≥95% AND same nflverse lineage — document as optional `fetch.backend: sdv` follow-up, do NOT wire prod fetch yet
- **Defer**: if redundant — keep nflreadpy, SDV as reference for NGS/participation only

Run live benchmark locally if network available; otherwise document "pending live run" with smoke structure.

## Exit criteria

- [ ] `docs/sportsdataverse-eval.md` with gap table + verdict
- [ ] Smoke + benchmark modules with tests (mocked CI path)
- [ ] `ceminidfs sdv-benchmark` CLI
- [ ] `eval` optional dependency in pyproject.toml
- [ ] ruff + pytest green; **no prod fetch.py changes**

## Out of scope

- Replacing nflreadpy in `fetch.py`
- K126 coherence features
- Unlicensed repos from eval batch
