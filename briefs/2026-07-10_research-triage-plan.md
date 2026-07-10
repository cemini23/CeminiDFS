# Research triage — 2026-07-07→10 sweeps — docs-only (zero adopts)

**Date:** 2026-07-10
**Status:** DOCS-ONLY — no code workstreams. Two one-line docs edits (exact patches in §3; applied in this pass).
**Baseline verified:** `325 passed, 1 skipped` on current tree (`73461ba` + untracked `.cursor/`, `scripts/*-commit.sh`, `scripts/install-hooks.sh` — none touched here).

## 1. Sources triaged

From OSINT `wiki/sweeps/2026-07-07-daily.md` through `2026-07-10-daily.md` (Q8 ceminidfs-nflverse, Q9 ceminidfs-ownership-calibration, P9 nfl-dfs-projection-paper).

### 2026-07-07 and 2026-07-08 — empty lanes

| Lane | Hits | Verdict |
|------|------|---------|
| Q8 ceminidfs-nflverse | 0 | **No action** — no CeminiDFS-routed news in either sweep |
| Q9 ceminidfs-ownership-calibration | 0 | **No action** |
| P9 nfl-dfs-projection-paper | 0 | **No action** |

P8 agent-harness papers (arXiv duplicates) and inbox newsletters route to other co-primary projects — not CeminiDFS.

### 2026-07-09 — Q8 hits (3)

| Hit | Verdict | Rationale |
|-----|---------|-----------|
| FantasyLife — Using NFL Player Props To Exploit Fantasy Football Edges: Jared Goff vs Joe Burrow (R18, 2026-07-08) | **Reading → Gambling wiki** | Player-props / season-long fantasy edge framing, not salary-cap NFL DFS projections. ROADMAP pick'em/props lane is wiki-only (K147); no props vertical in this repo |
| CBS — Fantasy football rankings 2026: sleepers, breakouts, busts per model (R19, 2026-07-07) | **Reading → Gambling wiki** | Third-party rankings article; no data lineage, no nflverse interface. Same verdict as 07-03 CBS rankings hit |
| SportsLine — 2026 fantasy football sleepers and busts simulation (R20, 2026-07-02) | **Reading → Gambling wiki** | Season-long sim rankings marketing; not FanDuel slate projections or ownership calibration |

### 2026-07-10 — Q8 hits (3)

| Hit | Verdict | Rationale |
|-----|---------|-----------|
| CBS — Fantasy football rankings 2026 (R16, 2026-07-07) | **Already triaged** | Same URL as 07-09 R19 — dedup within this triage window |
| FantasyLife — Auction Fantasy Football QB Strategy: Patrick Mahomes Is A Value In 2026 (R17, 2026-07-10) | **Reading → Gambling wiki** | Auction/draft strategy, not DFS salary-cap modeling |
| FantasyLife — 3 Fantasy Football 2026 Projections To Target: Judkins, Smith, etc. (R18, 2026-07-04) | **Reading → Gambling wiki** | Season-long projection listicle; no exportable benchmark CSV or ownership labels |

### 2026-07-09 and 2026-07-10 — Q9 hits (NBA, out of sport)

| Hit | Verdict | Rationale |
|-----|---------|-----------|
| Stokastic — NBA DraftKings DFS Strategy (R21/R19, 2026-07-06) | **Out of sport** | NBA; same verdict as 07-03 FantasyLabs PGA and 07-09 P9 NBA DFF optimizer hits |
| Stokastic — How To Use NBA DFS Ownership Projections On DraftKings (R22/R20, 2026-07-07) | **Out of sport** | NBA ownership guide; Stokastic NFL posture (manual-CSV benchmark) unchanged — this article does not add an NFL interface |

### P9 paper-lane repeats (07-09, 07-10 — not routed to repo)

| Hit | Verdict | Rationale |
|-----|---------|-----------|
| Stokastic NFL DFS / DFS Strategy landing pages | **Already triaged ×2** | 07-03 and 07-05 verdicts stand: landing pages add no new interface |
| FantasyAlarm articles homepage | **Already triaged ×3** | Third+ consecutive P9 appearance — OSINT dedup candidate (§3c) |
| RotoGrinders World Cup soccer DFS sim (07-09 P9) | **Out of sport** | Soccer |
| DailyFantasyFuel NBA optimizer (07-09 P9) | **Out of sport** | NBA |
| RotoWire auction values, Fantasy Footballers podcast homepage (07-10 P9) | **Reading → Gambling wiki** | Draft/auction strategy and podcast marketing; no code lineage |

## 2. Why no code is warranted

1. **No new repos, datasets, or APIs** in any Q8/Q9 hit across four sweeps. FantasyLife content is props/auction/season-long fantasy — outside the `fetch → project → optimize` salary-cap pipeline. Data posture (nflreadpy primary, manual salary CSV, manual Stokastic/FantasyLabs benchmarks) is unchanged.
2. **Two sweeps were empty** (07-07, 07-08). The actionable tail is marketing listicles and duplicate CBS rankings — re-planning against already-triaged patterns would be forced work (same reasoning as 07-03 §2.3 and 07-05 §2.3).
3. **Q9 hits are NBA-only** — outside NFL scope; Stokastic's NFL manual-CSV benchmark role does not warrant importing NBA strategy articles.
4. **Backlog gates are unchanged:** sportsdataverse adopt still requires a proven maintenance win on 2025+ slates; Setfive WebSocket remains CCC-wiki-routed, not this repo.
5. **One stale PLAN.md item resolved without code:** `OPEN_METEO_ARCHIVE_URL` and `_open_meteo_url()` already live in `src/ceminidfs/data/weather.py` — the "Open-Meteo archive API" backlog line is struck in §3b.

Per ROADMAP rejects posture: zero new dependencies, no scrapers, no paid-tool integrations, no pip deps.

## 3. Recommended edits (docs only — applied)

**3a. `ROADMAP.md` — add triage row to "Shipped tracks"** (keeps the K125→K138→Sweep audit trail unbroken), inserted after the `| Sweep 07-05 | ... |` row:

```markdown
| Sweep 07-07→10 | Research triage — zero adopts | `briefs/2026-07-10_research-triage-plan.md` |
```

**3b. `PLAN.md` — strike stale Open-Meteo archive backlog item** in "Future backlog (not started)":

```markdown
- ~~Open-Meteo **archive** API for historical weather in backtests~~ — `data/weather.py` `OPEN_METEO_ARCHIVE_URL` + `_open_meteo_url()` (2026-07-10)
```

**3c. Wiki routing (outside this repo, operator morning-ingest lane):**
- FantasyLife props (Goff/Burrow), auction QB (Mahomes), and season-long projection listicles → Gambling wiki (`~/Desktop/projects/Gambling wiki`), per K128 "reading refs route to wiki, not repo" and K147 props wiki hub.
- CBS rankings + SportsLine sleepers → Gambling wiki (operator reading refs).
- P9 keeps resurfacing Stokastic/FantasyAlarm landing URLs — consider exclude-list or dedup-against-prior-sweeps tweak in `scripts/daily_research_config.yaml`. Not an executor task here.

## 4. Explicitly not doing

- No FantasyLife / CBS / SportsLine integrations — reading refs only; no scrapers, no paid APIs
- No props/pick'em vertical in this repo (K147 wiki hub only)
- No NBA branch, no Stokastic NBA article imports
- No CBS rankings model adoption — third-party listicles, not nflverse calibration inputs
- No sportsdataverse adoption (gate unmet), no Setfive WebSocket work (wrong repo)
- No new pip dependencies of any kind
- No changes to `src/`, `tests/`, `extension/`, or config

## 5. Executor instructions

No executor subagents required. §3a and §3b are mechanical one-line docs edits, applied directly in this planning pass — `git diff` eyeball is sufficient review. Suite verified at `325 passed, 1 skipped` before the edits; docs-only changes cannot affect it.
