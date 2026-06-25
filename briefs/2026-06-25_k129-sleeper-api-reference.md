## Target

`CeminiDFS/` — NFL projection pipeline (FanDuel-primary). **Reference-only** — no Underdog/Sleeper prod dependency.

## Summary

K129 tool eval **Steal-from** cluster for DFS adjacency: `dtsong/sleeper-api-wrapper` (MIT), `fantasy-football-wrapped` (Apache-2.0), `sleeper-mini` (MIT). Rejects aggregated — GPL/no-license Underdog scrapers are **NO-GO**.

## Body

### Approved steals

| Repo | Steal |
|------|-------|
| dtsong/sleeper-api-wrapper | `get_trending_players` as **stage-0 buzz signal** — not primary projection |
| kt474/fantasy-football-wrapped | Expected-wins / luck metrics for **MME backtest calibration** |
| blitzstudios/sleeper-mini | UX patterns only if embedded mini-app explored later |

### Rejects (do not install)

- aidanhall21/underdog-fantasy-pickem-scraper — NO LICENSE
- fantasydatapros/underdog — NO LICENSE
- GPL-3.0 sleeper forks — IP-sale poison

### P0

1. Document in `ROADMAP.md` that CeminiDFS remains **FanDuel + nflverse** primary; Sleeper APIs optional sentiment layer only.
2. No new pip dependency until Phase-0 wrapper audit in dedicated session.

## Sources

- @osint-wiki/sources/eval-url-cemini-research-2026-06-25.md (URLs 12–30 Sleeper cluster)
- @osint-wiki/briefs/ccc-2026-06-25_k129-harness-loop-headroom-no-mistakes.md (harness only)
