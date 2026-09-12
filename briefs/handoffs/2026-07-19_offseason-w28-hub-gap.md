# Handoff — NFL offseason weekly hub ingest (w28 — gap fill)

**Lane:** mid/hard  
**WorkDir:** `/Users/claudiobarone/Projects/Gambling wiki`  
**Why:** Operator asked to ingest every week. Inventory: w27 hub ✅ · **w28 hub ❌** · w29 hub ✅

## Goal

Write the missing hub for ISO week 28. Research only — no slate tools / pick'em / LIVE bets.

## Inputs

- Prefetch (rich digest rows): `briefs/offseason/2026-offseason-w28-prefetch.md`
- Prior hub: `briefs/offseason/2026-offseason-w27-hub.md`
- Later hub (already written): `briefs/offseason/2026-offseason-w29-hub.md` — avoid duplicating w29; focus on **Jul 5–12 window** (w28)
- Digests: `wiki/sweeps/2026-07-05-daily.md` … `2026-07-12-daily.md` (and any rows already pasted into the w28 prefetch)

## Write

`briefs/offseason/2026-offseason-w28-hub.md` in the same shape as w27/w29:

1. Camp standout watchlist  
2. Depth/injury deltas  
3. K147 build decisions  
4. BBM ADP notes  
5. Top 3 deep-read URLs  
6. Hard Rock one-liner max  

Mark uncertain claims **[TENTATIVE]**. Prefer prefetch URLs that are real camp/BBM content; skip affiliate PrizePicks/Hard Rock spam beyond one posture line.

## Also

- Prefetch `2026-offseason-w28-prefetch.md` → `status: hub-written`
- Prefetch `2026-offseason-w27-prefetch.md` → `status: hub-written` (hub already exists; status still stub)
- Delete `.cursor-prompt-offseason-w28.txt` if present after success

## Acceptance

- [ ] `briefs/offseason/2026-offseason-w28-hub.md` exists
- [ ] Watchlist ≥3 rows or explicit thin-week + carry-forward
- [ ] Deep-read ×3
- [ ] All three prefetches show `hub-written`
- [ ] No commits unless asked
