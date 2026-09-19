## Target

CeminiDFS (`~/Projects/CeminiDFS`). Projection / lineup / sim stay in code. Jev is the human-gate helper only. No scrape.

## Summary

Use jev-mcp on **review CSVs**, not on the solver. `jev_verify` checks an injury or news note against the named player. `jev_find` ranks late-swap notes. Solvers, ownership, and sim stay untouched.

## Body

### Tools

| Tool | DFS use |
|------|---------|
| `jev_verify` | “This note actually names this WR and this status” vs the injury/news cell. |
| `jev_find` | Rank three late-swap blurbs for one player (`start` / `sit` / `ignore`). |
| `jev_screen` | Screen pasted news HTML before it enters a review session. |

### First trial (this folder)

1. Confirm **jev** is On in Cursor Tools & MCP.
2. Open the current human-gate review CSV (`docs/REVIEW-REPORTS.md` path).
3. Pick one WR row with a news/injury string.
4. Call `jev_verify` with claim = player + status, evidence = that string.
5. Keep or drop the row in the human gate. Do not change the projection engine. Do not scrape. Do not submit a lineup to FanDuel.

### Hard gates

- No scrape. No FanDuel Enter. No book submit.
- No Odds API key on a bot VM.
- Jev does not replace pydfs / sim / ownership math.
- Do not swap `/route`.

### Setup (already on this machine)

- Launcher: `~/.local/bin/mcp-jev`.
- Project MCP: `.cursor/mcp.json` server `jev` (`disabled: false`).
- Key: `~/.cemini/typesafe-api-key`.

## Sources

- @osint-wiki/entities/tools/jev-mcp.md
- @osint-wiki/concepts/active-project-research-routing.md
- @osint-wiki/briefs/2026-09-18_k264-ceminidfs.md
