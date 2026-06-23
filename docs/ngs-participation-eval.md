# NGS and Participation Data Evaluation (K127 P2)

**Date:** 2026-06-23  
**Scope:** Evaluate Next Gen Stats (NGS) player tracking and play-level participation data as future P2 enhancements for CeminiDFS projection engine.

## Overview

SportsDataVerse-py (`sportsdataverse.nfl`) provides access to NFL Next Gen Stats and play-level participation data. These are **not** integrated into the current CeminiDFS fetch posture but represent high-value P2 features for advanced projection modeling.

## NGS (Next Gen Stats) Data

### Available Endpoints

| Module | Function | Description | Projection Value |
|--------|----------|-------------|----------------|
| `nfl.load_nfl_ngs_passing` | Weekly passing metrics | Aggressiveness, completion probability, expected completion % | **High** — QB decision-making quality, accuracy beyond box score |
| `nfl.load_nfl_ngs_rushing` | Weekly rushing metrics | Efficiency, yards after contact, expected yards | **Medium** — RB tackle-breaking, OL quality proxy |
| `nfl.load_nfl_ngs_receiving` | Weekly receiving metrics | Separation, catch probability, YAC expectation | **High** — route-running quality, QB-independent value |

### Sample Schema (Passing)

```text
player_gsis_id      # GSIS ID for joining
player_display_name # Full name
season              # Season year
week                # Week number
team_abbr           # Team abbreviation
aggressiveness      # % of passes into tight windows
completion_probability # Model-based completion expectation
expected_completion_percentage # xComp%
completion_percentage_above_expectation # CPOE
avg_time_to_throw   # Seconds from snap to throw
avg_completed_air_yards # Depth of target on completions
avg_intended_air_yards # Depth of target on all attempts
max_air_distance    # Maximum throw distance
```

### Integration Path (Future)

1. **QB Quality Score:** Combine CPOE, aggressiveness, time-to-throw into QB efficiency composite beyond YPA/TD rate
2. **WR Separation Premium:** Adjust target share projections based on route-running quality (separation independent of QB)
3. **Pass Protection Proxy:** Time-to-throw correlates with OL quality; faster throws = better protection = lower sack risk

## Play-Level Participation Data

### Available Endpoints

| Module | Function | Description | Projection Value |
|--------|----------|-------------|----------------|
| `nfl.load_nfl_pbp_participation` | Play-level rosters | Who was on the field for every play | **High** — defensive matchup quality, personnel-based tendencies |

### Sample Schema

```text
play_id             # Play identifier
game_id             # Game identifier
season              # Season year
week                # Week number
home_team           # Home team abbreviation
away_team           # Away team abbreviation
home_players        # List of GSIS IDs on field for home
guest_players       # List of GSIS IDs on field for away
home_weighted_agg_rating # Aggregate player rating
visitor_weighted_agg_rating # Aggregate player rating
```

### Integration Path (Future)

1. **Defensive Matchup Quality:** Aggregate opposing defensive ratings by position group (CBs vs WRs, DL vs OL)
2. **Personnel-Based Tendencies:** Team play-calling by offensive personnel grouping (11, 12, 21 personnel)
3. **Injury Impact Modeling:** Real-time participation changes affect snap share projections

## Current Posture

| Aspect | Status |
|--------|--------|
| **Prod Fetch** | Remains `nflreadpy` via `ceminidfs.data.fetch` |
| **NGS Integration** | **P2 only** — stub available at `src/ceminidfs/data/ngs_eval.py` |
| **Participation Integration** | **Not started** — documented for future evaluation |
| **Network in Default Path** | **No** — all stub loaders return None on import failure |

## Stub Implementation

```python
# src/ceminidfs/data/ngs_eval.py
from ceminidfs.data.ngs_eval import load_ngs_passing_sample

# Returns DataFrame or None (no network in default path)
df = load_ngs_passing_sample(season=2024)
```

## Evaluation Verdict

| Criterion | Assessment |
|-----------|------------|
| **License** | MIT (sportsdataverse-py) — cleared for use |
| **Data Quality** | NFL official tracking — highest accuracy |
| **Latency** | CDN-backed nflverse release parquets — acceptable |
| **Integration Effort** | Medium — requires projection model extensions |
| **Priority** | **P2** — valuable but not blocking for live slate use |

## Related Documents

- [sportsdataverse-eval.md](sportsdataverse-eval.md) — K127 full evaluation of sportsdataverse-py
- [epa-cleanroom-audit.md](epa-cleanroom-audit.md) — Clean-room evaluation methodology
- `src/ceminidfs/data/ngs_eval.py` — Stub loader with optional import guard
