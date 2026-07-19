---
title: K163 — maths-cs-ai-compendium MCP extract (CeminiDFS)
type: brief
target: CeminiDFS
created: 2026-07-14
updated: 2026-07-19
status: extract-applied
extract_date: 2026-07-19
---

## Target

CeminiDFS projection pipeline — agent coding assist only.

## Summary

HenryNdubuaku/maths-cs-ai-compendium (**Apache-2.0**): intuition-first math/ML compendium with MCP server. Extract as optional local knowledge MCP for pipeline coding — not a runtime dependency.

## Body

1. Optional clone under `.local/` (~few MB) and mount MCP in Cursor for CeminiDFS folder.
2. Query combinatorial / inference notes on demand; do not paste entire books into prompts.
3. No change to FanDuel slate code paths without human review.

## Extract applied (2026-07-19)

- `.local/` created and gitignored.
- Compendium at `.local/adopts/maths-cs-ai-compendium` (symlink → OSINT WORKSPACE adopt).
- `mcp/` deps installed; Cursor MCP entry `maths-compendium` in `.cursor/mcp.json` (keeps `codebase-memory-mcp`).
- ROADMAP Shipped tracks row for K163.
- **No** FanDuel / `src/` / `tests/` / `extension/` edits.

## Sources

- OSINT `@entities/tools/maths-cs-ai-compendium.md`
