# Research triage — 2026-07-03 sweep — NO-OP (zero adopts)

**Date:** 2026-07-03
**Status:** NO-OP — no code workstreams. One optional one-line ROADMAP edit (exact patch in §3).
**Baseline verified:** `319 passed, 1 skipped` on current tree (`01524b2` + untracked `.cursor/`, `scripts/*-commit.sh`, `scripts/install-hooks.sh` — none touched here).

## 1. Sources triaged

From OSINT `wiki/sweeps/2026-07-03-daily.md` (Q8 ceminidfs-nflverse, Q9 ceminidfs-ownership-calibration, P9 nfl-dfs-projection-paper):

| Hit | Verdict | Rationale |
|-----|---------|-----------|
| FantasyAlarm — NFL DFS Strategy 2026: DK vs FD GPP guide | **Already triaged 2026-07-02** | Cited as "operator reading refs only" in `briefs/2026-07-02_research-backlog-fix-plan.md` sources table; GPP profile + `docs/GPP-WORKFLOW.md` already cover FD tournament posture |
| Establish The Run — Best Ball contest selection 2026 | **Reading → Gambling wiki** | DraftKings best-ball contest selection; BBM copilot targets **Underdog** BBM VII. Principles (field size, rake, payout curve) are operator strategy, not code. Considered a `docs/BBM.md` Further-reading link — **skipped** (platform mismatch) |
| Stokastic — DFS Strategy & Guides landing page | **No action** | Stokastic already in ROADMAP data posture as manual-CSV accuracy/ownership benchmark; a strategy landing page adds no new interface |
| CBS fantasy rankings model article, "Geekiest Fantasy Football Tool" (YouTube) | **Reading → Gambling wiki** | Rankings content, no code/data lineage |
| LineStar pricing, Fantasy Team Advisors | **No action** | Paid-tool marketing pages; ROADMAP posture is manual CSV only |
| DailyFantasyFuel MLB optimizer, FantasyLabs PGA article, RotoGrinders World Cup soccer DFS sim | **Out of sport** | MLB/PGA/soccer — outside NFL scope |

Today's K141 eval files are agent-harness/HF/TipDrop/CCC-targeted — nothing routes here.

## 2. Why no code is warranted

1. **No new repos, datasets, or APIs** in any hit — nothing to adopt, borrow, or clean-room. Data posture (nflreadpy primary, manual salary CSV, manual Stokastic/FantasyLabs benchmarks) is unchanged.
2. **The backlog is gated, not empty-handed:** `sportsdataverse` adopt requires a *proven maintenance win on 2025+ slates* (not present today); Setfive WebSocket is CCC-wiki-routed, explicitly not this repo.
3. **Yesterday's sprint closed the actionable tail** — safe ADP expansion (`expand_verified`), `bbm preflight`, combo batching, extension v1.3.0 (commit `01524b2`). Re-planning against the same FantasyAlarm ref two days running would be forced work.

Per ROADMAP rejects posture: zero new dependencies, no scrapers, no paid-tool integrations.

## 3. Recommended edits (docs only)

**3a. ROADMAP.md — add triage row to "Shipped tracks" table** (keeps the K125→K138 audit trail unbroken; mirrors the K128 zero-adopt precedent):

```markdown
| Sweep 07-03 | Research triage — zero adopts; reading refs → Gambling wiki | `briefs/2026-07-03_research-triage-plan.md` |
```

Insert after the `| BBM7 | ... |` row.

**3b. Wiki routing (outside this repo, operator morning-ingest lane):** ETR contest-selection + FantasyAlarm DK-vs-FD + CBS rankings refs belong in the Gambling wiki (`~/Desktop/projects/Gambling wiki`), per the K128 "reading refs route to wiki, not repo" pattern. Not an executor task here.

## 4. Explicitly not doing

- No `sportsdataverse` adoption (gate unmet), no Setfive WebSocket work (wrong repo)
- No MLB/PGA/soccer branches, no LineStar/DFF/FTA integrations
- No `docs/BBM.md` edit (ETR guide is DK-platform; copilot is Underdog)
- No changes to `src/`, `tests/`, `extension/`, or config

## 5. Executor instructions

No executor subagents required. §3a is a single mechanical one-line table edit — apply directly (parent or operator), no test run needed beyond `git diff` eyeball. Suite remains at 319 passed / 1 skipped.
