# Handoff — NFL offseason weekly hub ingest (w29)

**Lane:** mid → hard (research synthesis + file write)  
**WorkDir:** `/Users/claudiobarone/Projects/Gambling wiki`  
**Notification:** macOS “NFL offseason weekly — Week 29 prefetch ready” (LaunchAgent `com.cemini.nfl-offseason-weekly.gambling`, Sun 09:15)

## Goal

Produce the week-29 hub from the prefetch stub. Research only — no slate tools, no pick'em entries, no LIVE bets.

## Inputs

- Prefetch: `briefs/offseason/2026-offseason-w29-prefetch.md` (stub; digest had news disabled → few auto rows)
- Prior hub pattern: `briefs/offseason/2026-offseason-w27-hub.md`
- Digests to mine (manual — news often off):  
  `wiki/sweeps/2026-07-12-daily.md` … `2026-07-19-daily.md`  
  Especially clusters: nfl-preseason-camp, nfl-underdog-bbm, cemini-dfs-*, nfl-hard-rock, cemini-pickem-*
- w28 prefetch still stub-only (`2026-offseason-w28-prefetch.md`) — optionally note “w28 hub skipped/deferred” in w29; do **not** invent a full w28 hub unless time allows a short delta section

## Write

`briefs/offseason/2026-offseason-w29-hub.md` matching w27 structure:

1. Camp standout watchlist (player, team, role, BBM, pick'em/prop later, source)
2. Depth/injury deltas worth tracking into preseason
3. K147 build decisions (no tool run)
4. BBM ADP notes if material
5. Top 3 digest URLs to deep-read this week
6. Hard Rock / book posture (promo only OK; no bet list)

Mark uncertain injury/camp claims **[TENTATIVE]**. Prefer linking existing `@sources/…` wiki pages when present; otherwise use full URLs from digests.

## Also update

- Prefetch frontmatter `status: hub-written` (or similar) once hub exists
- Delete or leave sidecar `.cursor-prompt-offseason-w29.txt` (optional delete after success)

## Out of scope

- CeminiDFS `src/` / extension code
- Committing unless operator asks
- Scraping Underdog / placing wagers
- Inflating hub with affiliate promo spam — one Hard Rock line max

## Fresh web seeds (2026-07-19 Brave) — verify before citing as fact

Injuries / camp:
- https://www.cbssports.com/nfl/news/nfl-injury-updates-2026-patrick-mahomes-malik-nabers-training-camp/
- https://www.fantasypros.com/2026/07/10-fantasy-football-injury-updates-to-know-2026/
- https://www.profootballnetwork.com/fantasy-football/fantasy-football-injury-updates-everything-you-need-to-know-in-july-2026/
- SEA Charbonnet / Jadarian Price notes appear in camp injury roundups [TENTATIVE Week 1]

BBM ADP:
- https://establishtherun.com/market-monday-july-13-how-to-handle-the-biggest-risers-and-fallers-in-best-ball-adp/ (Jul 13)
- SI risers/fallers: Adonai Mitchell / Quentin Johnston up; Nabers / Aiyuk / Hill soft — https://www.si.com/onsi/fantasy/nfl/fantasy-football-adp-risers-fallers-adonai-mitchell-quentin-johnston-jonathon-brooks
- Live UD ADP board: https://www.bestballteambuilder.com/underdog-best-ball-average-draft-position

Digest deep-reads still useful from w28 prefetch: Ourlads depth charts, Bleacher Report camp schedule, FantasyPros injury updates.

## Acceptance

- [ ] Hub file exists at `briefs/offseason/2026-offseason-w29-hub.md`
- [ ] Watchlist table has ≥3 real rows OR explicit “thin week — news lane off” with carry-forward from w27
- [ ] Deep-read list has 3 URLs
- [ ] No tool/slate commands run
