# Handoff — K163 maths-cs-ai-compendium MCP extract (CeminiDFS)

**Lane:** hard  
**WorkDir:** `/Users/claudiobarone/Projects/CeminiDFS`  
**Brief:** `briefs/2026-07-14_k163-maths-compendium-mcp-extract.md`  
**Do not** change FanDuel slate / `src/` projection code paths.

## Goal

Mount HenryNdubuaku/maths-cs-ai-compendium as an **optional local knowledge MCP** for agent coding assist only (not a runtime dependency).

## Already available

OSINT already cloned the repo at:

`/Users/claudiobarone/Projects/OSINT WORKSPACE/.local/adopts/maths-cs-ai-compendium`

Prefer a **symlink** (or shallow clone) under CeminiDFS `.local/` rather than a second full copy if the OSINT path exists.

MCP package: `.local/.../maths-cs-ai-compendium/mcp/` (`npm run setup` / `npm install`; start via `npm start` / `tsx src/index.ts`).  
Env: `COMPENDIUM_ROOT` may point at the repo root (defaults to parent of `mcp/`).

## Acceptance

1. `.local/` exists under CeminiDFS and is **gitignored**.
2. Compendium available at e.g. `.local/adopts/maths-cs-ai-compendium` (symlink OK).
3. `mcp/` deps installed (`node_modules` present under the mcp dir).
4. `.cursor/mcp.json` adds a `maths-compendium` (or similar) stdio server that runs the local MCP (npx/tsx/node — match package scripts). Keep existing `codebase-memory-mcp` entry.
5. `ROADMAP.md` Shipped tracks: add row for K163 pointing at the brief.
6. Update brief frontmatter/status to note extract applied (date 2026-07-19); still **no** FanDuel/`src/` edits.
7. Do **not** commit secrets. Do **not** paste entire books into prompts/docs.

## Out of scope

- Underdog extension / DOM capture
- K159 process docs (separate easy task)
- Any change under `src/`, `tests/`, `extension/`
