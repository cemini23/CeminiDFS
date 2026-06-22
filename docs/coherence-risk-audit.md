# Coherence-Risk Audit

K126 adds a clean-room coherence-risk layer to CeminiDFS without importing ClarusC64 Hugging Face datasets or parquet loaders into the runtime path. The goal is to steal methodology, not integrate third-party artifacts.

## Gap Table

| Signal | HF reference | CeminiDFS stage-2 today | PBP proxy (clean-room) | Status |
|--------|--------------|-------------------------|------------------------|--------|
| Playcall vs defense coherence | `ClarusC64/nfl-playcall-defense-coherence-risk-v0.1` | `models.volume` pass-rate priors and `models.defense` opponent multipliers | No direct scheme or coverage proxy in nflverse PBP; document only | P2 audit only |
| Pass protection breakdown | `ClarusC64/nfl-pass-protection-coherence-risk-v0.1` | Global sack rate in `models.volume`; no team OL stress history in projections | Team dropback stress = `(sack_rate + qb_hit_rate) / league_avg` on walk-forward scrimmage plays | P0 implemented |
| Defense motion adjustment | `ClarusC64/nfl-defense-motion-adjustment-coherence-risk-v0.1` | EPA-based defense ratings only | No motion flag in cached path; cannot derive cleanly from current source columns | P2 audit only |
| Route timing | `ClarusC64/nfl-route-timing-coherence-risk-v0.1` | `usage.routes_proxy` exists but does not feed scoring | Could require participation/route data not present in current walk-forward cache | P2 audit only |
| QB read vs coverage | `ClarusC64/nfl-qb-read-coverage-coherence-risk-v0.1` | QB efficiency shrinkage and defense pass multiplier | No coverage-shell label in current PBP-only model | P2 audit only |
| Drive momentum | `ClarusC64/nfl-drive-momentum-coherence-risk-v0.1` | Pace and volume only | Drive-state sequence features are possible but not yet modeled | P2 audit only |
| Workload -> injury | `ClarusC64/nfl-player-workload-injury-coherence-risk-v0.1` | `data.availability` supports binary availability filtering | No graded workload-risk feature or injury probability layer | P2 audit only |
| Red-zone playcall | `ClarusC64/nfl-red-zone-playcall-coherence-risk-v0.1` | TD rates are global/regressed; no team-level RZ usage feedback | Team RZ rush share index at `yardline_100 <= 20`, used to tilt RB/TE/WR usage | P0 implemented |
| Fourth-down decision | `ClarusC64/nfl-fourth-down-decision-coherence-risk-v0.1` | Indirectly absorbed by team totals and pace | Could derive go-for-it rates from PBP, but not wired into player projections | P2 audit only |
| Rest/travel spot | `Karmane/nfl-rest-advantage-travel-spot-research-sample` | Not modeled in current fetch stack | Requires external schedule/travel enrichment outside nflverse-only runtime | P2 reference only |

## Clean-Room Posture

- No Hugging Face dataset imports, client libraries, parquet loaders, or fetch-path dependencies were added.
- All K126 prototypes derive from in-tree nflverse play-by-play columns already used elsewhere in CeminiDFS.
- Walk-forward integrity is preserved with `week < through_week` filtering before every team-level aggregation.
- Scrimmage filtering follows the same exclusion posture used by `data/pbp_filters.py`: only offensive snaps, no special teams, no kneels/spikes, and no penalty-only rows.
- Remaining coherence dimensions stay documented as gaps until CeminiDFS has a source-backed way to derive them cleanly.

## Implemented Prototypes

### Pass protection stress

- Unit of analysis: offensive `posteam`
- Sample: walk-forward dropbacks (`pass_attempt/pass` or `sack`)
- Metric: `(sacks + qb_hits) / dropbacks`, normalized by league walk-forward average
- Projection effect: penalize QB `pass_yds` and WR/TE `rec_yds` when the stress index clears threshold

### Red-zone run tendency

- Unit of analysis: offensive `posteam`
- Sample: walk-forward red-zone scrimmage plays with `yardline_100 <= 20`
- Metric: `rz_rushes / (rz_rushes + rz_passes)`, normalized by league walk-forward average
- Projection effect: boost RB carries and TE targets, trim WR targets before the stats layer

## Known Limits

- `qb_hit` coverage depends on the cached nflverse columns present for a season; missing values fall back to zero.
- `yardline_100` is preferred; `yrdln` parsing is only a fallback.
- The prototypes intentionally avoid creating new data dependencies or rest-of-world enrichment jobs.
