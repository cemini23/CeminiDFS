# Sleeper sentiment layer — Phase-0 audit (K129)

**Date:** 2026-06-25  
**Verdict:** Adopt as **optional stage-0 buzz signal** — not a projection source.

## Reference repos (steal methodology, not code)

| Repo | License | What we took |
|------|---------|--------------|
| dtsong/sleeper-api-wrapper | MIT | `GET /players/nfl/trending/{add\|drop}` pattern |
| kt474/fantasy-football-wrapped | Apache-2.0 | Pythagorean expected wins + luck delta for calibration context |
| blitzstudios/sleeper-mini | MIT | UX patterns only — not implemented |

## Rejects

- aidanhall21/underdog-fantasy-pickem-scraper — no license
- fantasydatapros/underdog — no license
- GPL Sleeper forks — incompatible with MIT IP posture

## Implementation

| Module | Role |
|--------|------|
| `ceminidfs.data.sleeper` | Stdlib HTTP client; trending + optional player index cache |
| `ceminidfs.models.buzz_signal` | Match trending counts to canonical rows; optional ownership nudge |
| `ceminidfs.pipeline.luck_metrics` | Team Pythagorean expected wins vs actual (MME calibration context) |

## API surface

```bash
# Fetch trending adds (stdout table or JSON)
ceminidfs sleeper trending --direction add --limit 25

# Season luck table through week N (needs schedules cache)
ceminidfs luck-metrics --season 2024 --through-week 10
```

## Wiring

When `buzz_signal.enabled: true` in config, `pipeline.project.project_week` attaches `sleeper_buzz_add` / `sleeper_buzz_drop` columns and applies a capped ownership boost on trending adds.

Buzz does **not** alter `fd_projection` or DIY stat engine outputs.

## Limits

- Player index JSON is ~5MB; cached under `artifacts/cache/sleeper_players_nfl.json` with 7-day TTL.
- Name matching is fuzzy (normalized full name + team); ambiguous matches are skipped.
- Network required for live trending; tests mock HTTP.
