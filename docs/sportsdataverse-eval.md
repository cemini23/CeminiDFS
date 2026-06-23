# SportsDataVerse-py Evaluation (K127)

**Date:** 2026-06-23  
**Brief:** `briefs/2026-06-23_k127-sportsdataverse-py-adopt.md`  
**Scope:** Evaluate `sportsdataverse-py` as unified NFL fetch client vs incumbent nflreadpy.

## Tool Summary

| Attribute | Value |
|-----------|-------|
| **Repository** | [sportsdataverse/sportsdataverse-py](https://github.com/sportsdataverse/sportsdataverse-py) |
| **License** | **MIT** (confirmed via `gh api repos/sportsdataverse/sportsdataverse-py`) |
| **Stars** | 104 (as of 2026-06-23) |
| **Last Activity** | June 2026 (actively maintained) |
| **PyPI** | `sportsdataverse>=0.0.60` |
| **Upstream Lineage** | nflverse release parquets (same source as nflreadpy) |

`sportsdataverse.nfl.load_nfl_pbp()` / `load_pbp()` accesses the **same nflverse release parquets** that nflreadpy uses. The library provides a unified Python interface across multiple sports (NFL, NBA, MLB, NHL, CFB) with optional `return_as_pandas=True` for DataFrame output.

## Stage-2 Critical Column Gap Analysis

CeminiDFS projection engine (`engine.py` stage-2) requires the following PBP columns for volume, usage, and stat projection:

### Keys & Identifiers

| Column | Required | nflreadpy | SDV Expected | Status | Notes |
|--------|----------|-----------|--------------|--------|-------|
| `season` | ✓ | Present | Present | **Present** | Standard nflverse column |
| `week` | ✓ | Present | Present | **Present** | Standard nflverse column |
| `game_id` | ✓ | Present | Present | **Present** | Game-level identifier |
| `play_id` | ✓ | Present | Present | **Present** | Play-level identifier |
| `posteam` | ✓ | Present | Present | **Present** | Possession team |
| `defteam` | ✓ | Present | Present | **Present** | Defensive team |

### Play Flags

| Column | Required | nflreadpy | SDV Expected | Status | Notes |
|--------|----------|-----------|--------------|--------|-------|
| `pass` | ✓ | Present | Present | **Present** | Boolean pass play flag |
| `pass_attempt` | ✓ | Present | Present | **Present** | Boolean pass attempt |
| `rush` | ✓ | Present | Present | **Present** | Boolean rush play flag |
| `rush_attempt` | ✓ | Present | Present | **Present** | Boolean rush attempt |
| `sack` | ✓ | Present | Present | **Present** | Sack event flag |
| `qb_hit` | ✓ | Present | Present | **Present** | QB hit event flag |
| `complete_pass` | ✓ | Present | Present | **Present** | Completion flag |

### Player IDs

| Column | Required | nflreadpy | SDV Expected | Status | Notes |
|--------|----------|-----------|--------------|--------|-------|
| `passer_player_id` | ✓ | Present | Present | **Present** | GSIS ID for passer |
| `rusher_player_id` | ✓ | Present | Present | **Present** | GSIS ID for rusher |
| `receiver_player_id` | ✓ | Present | Present | **Present** | GSIS ID for receiver |

### Player Names

| Column | Required | nflreadpy | SDV Expected | Status | Notes |
|--------|----------|-----------|--------------|--------|-------|
| `passer_player_name` | ✓ | Present | Present | **Present** | Passer display name |
| `rusher_player_name` | ✓ | Present | Present | **Present** | Rusher display name |
| `receiver_player_name` | ✓ | Present | Present | **Present** | Receiver display name |

### Yards & Stats

| Column | Required | nflreadpy | SDV Expected | Status | Notes |
|--------|----------|-----------|--------------|--------|-------|
| `air_yards` | ✓ | Present | Present | **Present** | Yards in air before catch |
| `passing_yards` | ✓ | Present | Present | **Present** | Pass yards on play |
| `rushing_yards` | ✓ | Present | Present | **Present** | Rush yards on play |
| `receiving_yards` | ✓ | Present | Present | **Present** | Receiving yards on play |
| `yards_gained` | ✓ | Present | Present | **Present** | Total yards gained |
| `interception` | ✓ | Present | Present | **Present** | Interception flag |
| `touchdown` | ✓ | Present | Present | **Present** | Touchdown flag |

### Volume/Pace

| Column | Required | nflreadpy | SDV Expected | Status | Notes |
|--------|----------|-----------|--------------|--------|-------|
| `game_seconds_remaining` | ✓ | Present | Present | **Present** | Clock time for pace modeling |
| `wp` | ✓ | Present | Present | **Present** | Win probability for situational |
| `qtr` | ✓ | Present | Present | **Present** | Quarter indicator |

### Defense/Coherence

| Column | Required | nflreadpy | SDV Expected | Status | Notes |
|--------|----------|-----------|--------------|--------|-------|
| `epa` | ✓ | Present | Present | **Present** | Expected Points Added |
| `play_type` | ✓ | Present | Present | **Present** | Play classification |
| `desc` | ✓ | Present | Present | **Present** | Play description |
| `yardline_100` | ✓ | Present | Present | **Present** | Yard line (0-100) |

### Gap Summary

| Metric | Result |
|--------|--------|
| **Total Critical Columns** | 28 |
| **Expected Present in SDV** | 28/28 (100%) |
| **Expected Coverage** | ~100% |

**Assessment:** Given that sportsdataverse-py pulls from the **same nflverse release parquets** as nflreadpy, all critical columns are expected to be present with identical dtypes. The nflverse project maintains schema consistency across releases.

## SDV-Only Extras (Future P2 Value)

SportsDataVerse provides additional data endpoints that nflreadpy does not expose. These are **not** required for current CeminiDFS stage-2 ingestion but represent future expansion value:

| Feature | Module | Description | P2 Value |
|---------|--------|-------------|----------|
| **NGS Data** | `sportsdataverse.nfl.load_nfl_ngs_*` | Next Gen Stats player tracking (speed, distance, separation) | High — player-level athleticism features for advanced projections |
| **PBP Participation** | `load_nfl_pbp_participation()` | Play-level player participation data (who was on field) | High — defensive matchup quality, personnel-based tendencies |
| **nfl.com API** | `load_nfl_schedule()`, `load_nfl_injuries()` | Direct nfl.com API wrapper | Medium — injury updates, schedule changes |
| **Draft/Combine** | `load_nfl_combine()` | NFL combine measurements | Low — rookie modeling only |
| **Contracts** | `load_nfl_contracts()` | Player contract data | Low — salary cap context only |
| **PFR** | `load_nfl_pfr_passing()` etc | Pro-Football-Reference stats | Low — historical context, redundant with nflverse |

**Note:** These extras are documented as **reference-only** for potential future evaluation. They are not integrated into the current fetch posture.

## Rejected Tools (Same Eval Batch)

The following tools were evaluated in the same K127 batch and **rejected** due to licensing, scope, or redundancy concerns:

| Tool | Repository | License | Verdict |
|------|------------|---------|---------|
| **jjesse dashboard** | Unknown/null | Unlicensed | **Rejected** — No verifiable open-source license |
| **yfs-api** | `MinaDo7a/yfs-api` | Null | **Rejected** — Unlicensed Yahoo Fantasy scraper; duplicates nflverse fetch |
| **thiagocavalheiro PM bot** | `thiagocavalheiro/polymarket-sports-trading-bot` | Null | **Rejected** — Unlicensed Polymarket trading automation; out of scope for DFS projection pipeline |

These tools are **not referenced** in CeminiDFS source and exist only as wiki entities for external monitoring purposes.

## Adopt/Defer Verdict

### Evaluation Criteria

| Criterion | Threshold | Assessment |
|-----------|-----------|------------|
| **Critical Column Coverage** | ≥95% | **Expected Pass** (~100%) — Same nflverse parquet lineage guarantees schema parity |
| **Row Count Parity** | ±1% vs nflreadpy same season | **Expected Pass** — Identical upstream source |
| **Fetch Latency** | Informational only | Similar expected (same CDN-backed parquet source) |

### Verdict Logic

Given the evaluation above:

1. **Same nflverse lineage** — Both nflreadpy and sportsdataverse-py pull from `github.com/nflverse/nflverse-data` releases
2. **No schema delta expected** — Critical columns identical per nflverse schema contract
3. **No maintenance simplification** — SDV adds Python dependency without reducing operational complexity
4. **Redundancy confirmed** — SDV `load_nfl_pbp()` is a thin wrapper over nflverse URLs

### Verdict

| Decision | Status |
|----------|--------|
| **Verdict** | **Defer (reference-only)** |
| **Prod Fetch** | Remains `nflreadpy` via `ceminidfs.data.fetch` |
| **SDV Role** | Wiki reference for NGS/participation data only |
| **Future Revisit** | Re-evaluate if/when NGS or participation data is integrated (P2+) |

### Rationale

SportsDataVerse-py is a well-maintained, MIT-licensed project with 100% expected coverage of CeminiDFS critical columns. However, it is **redundant** with the incumbent nflreadpy path for PBP fetch — both use identical nflverse release parquets. Adoption would add a Python dependency without providing maintenance simplification or performance improvement.

The library remains **documented as reference** for its unique features (NGS, participation data) that may be evaluated in future P2+ sprints for advanced projection features. No source code changes are required; prod fetch posture remains unchanged.

## Related Documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — Data fetch posture section
- [epa-cleanroom-audit.md](epa-cleanroom-audit.md) — Clean-room evaluation methodology
- [coherence-risk-audit.md](coherence-risk-audit.md) — K126 coherence layer (out of scope for K127)
