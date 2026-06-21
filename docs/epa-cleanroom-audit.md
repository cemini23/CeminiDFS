# EPA edge-case clean-room audit (K125)

**Date:** 2026-06-21  
**Brief:** `briefs/2026-06-21_k125-nfl-repo-eval-epa-cleanroom.md`  
**Scope:** Team-level EPA used in `models/defense.py` for opponent pass/rush multipliers.

## Tool-eval context

| Repo | License | CeminiDFS action |
|------|---------|------------------|
| `nflverse/nfl_data_py` | MIT | **Canonical fetch** via nflreadpy |
| `bbenbenek/nfl-fantasy-football` | MIT | Reference only (Yahoo API duplicates fetch) |
| `hvpkod/NFL-Data` | MIT | Reference only (static CSV params) |
| `danmorse314/nfl-stuff` | **null** | Clean-room audit only — no R merge |
| `thiagocavalheiro/polymarket-sports-trading-bot` | **null** | Rejected |

## External claim (playmaking EPA)

Retired community code (e.g. early `playmaking_epa_pbp.R` forks) **under-credited** defensive events by omitting:

- **Half-sacks** (`half_sack_1_player_id`, `half_sack_2_player_id`) — split 0.5 sack credit per rusher
- **Several tackle flavors** — solo, assist, tackle-with-assist, TFL, pass breakups, etc.

Dan Morse’s updated `playmaking_epa_function.R` (nfl-stuff, null license) **includes** half-sacks and a wide defender event matrix, then:

1. Filters to `pass == 1 | rush == 1` with non-null `epa`
2. Expands one play row into multiple defender attribution rows
3. Deduplicates `(play_id, player_id)` before summing negative EPA (“playmaking EPA”)

**CeminiDFS does not implement playmaking EPA.** We never attribute EPA to individual defenders. Half-sack *player* credit is irrelevant to our DIY projection path.

## CeminiDFS EPA usage (before patch)

| Layer | Uses EPA? | Filter behavior |
|-------|-----------|-----------------|
| `data/fetch.py` | No | Raw nflverse PBP cached unchanged |
| `models/defense.py` | Yes | Pass/rush flag mask only; no `epa` null drop; no `no_play`/special-teams drop |
| `models/stats.py` | No | Counting stats from pass/rush attempts |
| `models/dst.py` | No | Event flags + points allowed |

### Gap found

`build_defense_ratings()` averaged EPA on all pass/rush flagged rows, including:

- Rows with missing `epa` (coerced to 0.0 — pulls averages toward zero)
- `no_play`, spikes, kneels, special teams when mis-flagged
- Penalty plays (description prefix `Penalty`)

This can skew team defensive multipliers vs nflfastR scrimmage conventions.

## Patch (clean-room)

Module: `src/ceminidfs/data/pbp_filters.py`

- `epa_eligible_plays()` — non-null EPA, scrimmage pass/rush, exclude listed `play_type` values and penalty descriptions
- `models/defense.py` — apply filter before historical week cutoff and rate aggregation

Regression: `tests/test_pbp_filters.py` + `tests/fixtures/epa_edge_cases.py` (synthetic rows, no R fixtures).

## Out of scope (explicit)

- Porting playmaking EPA or player-level half-sack attribution
- Yahoo JSON scrapers (`MinaDo7a/yfs-api`, `bbenbenek/nfl-fantasy-football` fetch)
- Polymarket sports trading bot
- Copying or embedding nfl-stuff R source (null license)

## Fetch posture (P1)

**Single path:** nflreadpy → nflverse parquet cache. No alternate scrapers in-tree.

Optional educational contrast (MIT, not integrated): see footnote in [ARCHITECTURE.md](ARCHITECTURE.md).
