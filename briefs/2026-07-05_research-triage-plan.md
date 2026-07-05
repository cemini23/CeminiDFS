# Research triage — 2026-07-05 sweep — docs-only (zero adopts)

**Date:** 2026-07-05
**Status:** DOCS-ONLY — no code workstreams. Two one-line docs edits (exact patches in §3; applied in this pass).
**Baseline verified:** `319 passed, 1 skipped` on current tree (`3490633` + untracked `.cursor/`, `scripts/*-commit.sh`, `scripts/install-hooks.sh` — none touched here).

## 1. Sources triaged

From OSINT `wiki/sweeps/2026-07-05-daily.md` (Q8 ceminidfs-nflverse, Q9 ceminidfs-ownership-calibration, P9 nfl-dfs-projection-paper) plus the CeminiDFS routing line in `wiki/sources/eval-github-repo-mcp-plan-2026-07-05.md` (K146 MCP stack).

| Hit | Verdict | Rationale |
|-----|---------|-----------|
| RotoWire — Scott Fish Bowl 16 draft strategy, rankings and ADP (Q8/R19, 2026-07-04) | **Reading ref → `docs/BBM.md`** | Season-long charity league, not DFS — but SFB16 drafts run in July and are a known ADP mover while BBM VII slow drafts are live. One Further-reading line (§3b). Strategy context only; **not** an ADP import source — registry refresh stays BBTB CSV via `bbm refresh-adp` |
| FantasyLabs — PickLabs launch: player props + DFS pick'em edges (Q9/R20, 2026-07-05) | **No action** (optional reading → Gambling wiki) | Props/pick'em vertical (PrizePicks-style), not salary-cap NFL DFS; paid-tool launch marketing. ROADMAP posture: FantasyLabs = manual-CSV accuracy/ownership benchmark only |
| FantasyLabs — John Deere Classic PGA DFS picks (Q9/R21, 2026-07-01) | **Out of sport** | PGA; same verdict as the 07-03 FantasyLabs PGA hit |
| FantasyAlarm — NFL DFS Strategy 2026: DK vs FD GPP guide (P9, 2026-07-01) | **Already triaged ×2** | Same URL triaged 07-02 (operator reading ref; GPP posture covered by `docs/GPP-WORKFLOW.md`) and again 07-03. Third consecutive appearance — flagged for OSINT-side query dedup (§3c) |
| Stokastic — DFS Strategy & Guides landing page (P9, 2026-07-04) | **Already triaged** | 07-03 verdict stands: landing page adds no new interface; Stokastic already in ROADMAP data posture as manual-CSV benchmark |
| LineStar — pricing page (P9, 2026-06-30) | **Already triaged** | 07-03 verdict stands: paid-tool marketing page |
| RotoGrinders — homepage (P9, 2026-07-05) | **No action** | Generic homepage; DFS tool landscape already cataloged wiki-only in K128 |
| FantasyLabs — homepage (P9, dated 2016-11-10) | **No action** | Decade-stale generic homepage; already in ROADMAP data posture |
| K146 MCP eval — "CeminiDFS fetch stack brief" routing; tavily-mcp Adopt tagged "xsp-killer + CeminiDFS RAG fetch" | **No repo adoption** | tavily-mcp / firecrawl-mcp-server / mcp-searxng are Cursor-agent-side MCP servers, not pipeline dependencies. CeminiDFS data posture is nflreadpy-primary + manual salary/benchmark CSVs — there is no fetch-stack gap a paid search API fills, and no RAG layer exists in this repo to feed. If the operator wants tavily for agent research sessions it belongs in `.cursor/mcp.json` (already present, untracked), never in `pyproject.toml`. The "CeminiDFS fetch stack brief" routing obligation is closed by this brief |

## 2. Why no code is warranted

1. **No new repos, datasets, or APIs with a license + data-lineage story** in any hit. The only novel item (PickLabs) is a paid props/pick'em product outside NFL salary-cap DFS scope. Data posture (nflreadpy primary, manual salary CSV, manual Stokastic/FantasyLabs benchmarks) is unchanged.
2. **The K146 MCP routing line does not translate to Python dependencies.** Adopt verdicts there are for the Cursor agent harness (browser, fetch, search MCPs). Installing tavily/firecrawl clients into this repo would violate the ROADMAP rejects posture (no scrapers, no paid-tool integrations) without serving `fetch → project → optimize`.
3. **The P9 lane is saturated with repeats** — FantasyAlarm is on its third consecutive appearance, Stokastic/LineStar on their second. Re-planning against already-triaged marketing URLs would be forced work (same reasoning as 07-03 §2.3).
4. **Backlog gates are unchanged:** sportsdataverse adopt still requires a proven maintenance win on 2025+ slates; Setfive WebSocket remains CCC-wiki-routed, not this repo.

## 3. Recommended edits (docs only — applied)

**3a. `ROADMAP.md` — add triage row to "Shipped tracks"** (keeps the K125→K138→Sweep audit trail unbroken), inserted after the `| Sweep 07-03 | ... |` row:

```markdown
| Sweep 07-05 | Research triage — zero adopts; SFB16 ADP reading ref → docs/BBM.md | `briefs/2026-07-05_research-triage-plan.md` |
```

**3b. `docs/BBM.md` — one Further-reading bullet** (the small docs win; unlike the 07-03 ETR skip, this is not platform-mismatched contest selection — it is July draft-market context directly relevant to BBM VII ADP drift):

```markdown
- SFB16 ADP context: [Scott Fish Bowl 16 — draft strategy, rankings and ADP (RotoWire, 2026-07-04)](https://www.rotowire.com/football/article/scott-fish-bowl-16-draft-strategy-rankings-and-adp-121124) — SFB drafts move July ADP while BBM VII slow drafts run; reading only, registry ADP stays BBTB CSV
```

**3c. OSINT-side notes (outside this repo, operator morning-ingest lane):**
- PickLabs launch ref belongs in the Gambling wiki (`~/Desktop/projects/Gambling wiki`) as optional pick'em reading, per the K128 "reading refs route to wiki, not repo" pattern.
- P9 (`nfl-dfs-projection-paper`) keeps resurfacing the same FantasyAlarm/Stokastic/LineStar/homepage URLs — consider an exclude-list or dedup-against-prior-sweeps tweak in `scripts/daily_research_config.yaml`. Not an executor task here.

## 4. Explicitly not doing

- No tavily-mcp / firecrawl-mcp-server / mcp-searxng in `pyproject.toml`, `src/`, or config — MCP stack stays agent-side (`.cursor/mcp.json` at most, operator's call)
- No PickLabs / LineStar / RotoGrinders / Stokastic integrations (paid tools; manual-CSV posture holds)
- No PGA branch, no props/pick'em vertical
- No SFB16 ADP import into the BBM registry — BBTB CSV remains the only ADP source for `bbm refresh-adp`
- No sportsdataverse adoption (gate unmet), no Setfive WebSocket work (wrong repo)
- No changes to `src/`, `tests/`, `extension/`, or config

## 5. Executor instructions

No executor subagents required. §3a and §3b are mechanical one-line docs edits, applied directly in this planning pass — `git diff` eyeball is sufficient review. Suite verified at `319 passed, 1 skipped` before the edits; docs-only changes cannot affect it.
