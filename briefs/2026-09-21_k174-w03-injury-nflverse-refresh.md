# K174 — Week 3 injury awareness + nflverse refresh

**From:** `@gambling-wiki/sources/daily-digest-batch-k174-2026-09-21.md`  
**Date:** 2026-09-21  
**Posture:** research only — no auto-lineups, no auto-enter

## nflverse cache refresh (GO)

GitHub releases tagged on 2026-09-21:

| Tag | Action |
|-----|--------|
| `schedules` | Re-pull spread/total columns for W3 slate |
| `stats_team` | Refresh team volume after Week 2 |
| `stats_player` | Refresh player usage after Week 2 |

Run CeminiDFS fetch/cache before any Week 3 projection batch.

## Week 3 injury flags [TENTATIVE — verify Wed practice]

| Player | Team | Note | Model impact |
|--------|------|------|--------------|
| Caleb Williams | CHI | Hamstring — carted W2 | Downgrade CHI pass volume until Fri |
| Jayden Daniels | WAS | Elbow dislocation W2 | Downgrade WAS stacks; wait practice |
| Alec Pierce | IND | OUT heel SNF | Remove from W3 player pool |

## Do not

- Auto-enter FanDuel tickets from RSS titles
- Size stacks off early Week 3 lines before Fri designations
- Import RotoBaller waiver-wire lists (K169 skip)

## Next hub

Wait for Tue Gemini practice docx → update gitignored slate hub → then run `docs/SUNDAY.md` path for Week 3 main.
