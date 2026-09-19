# SIP handoff — Week 2 readiness gaps (from free-audit auditors)

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Success criteria

1. `.cursor/mcp.json` has a `jev` server: command `/Users/claudiobarone/.local/bin/mcp-jev`, `args: []`, `env: {}`, `disabled: false`. No API keys. Keep existing `codebase-memory-mcp` and `maths-compendium`.
2. `docs/SUNDAY.md` Week 2 card names: (a) FanDuel CSV must be the Sunday-afternoon slate only (do not import SNF IND@KC from a full-week export); (b) after fetch, ATL QB in nflverse vegas may still say Tua — hub is Cooper Rush / fade ATL pass; do not retune FPPG; (c) after review CSVs exist, optional Jev HITL (`jev_verify` on one injury cell, `jev_find` on late-swap rows).
3. `docs/REVIEW-REPORTS.md` states jev is on project + global Cursor MCP; `ceminidfs review` does not read the scratch CSV; Jev does not change projections; write optional notes beside the review CSVs (HITL only).
4. `briefs/2026-09-19_jev-ceminidfs.md` first-trial step 1 matches the project MCP row.
5. No `src/` changes. No new CLI flag. No default-on review flags. No salary CSVs.

## Verify

- `python3 -c "import json; p=json.load(open('.cursor/mcp.json')); j=p['mcpServers']['jev']; assert j['command'].endswith('mcp-jev'); assert j.get('disabled') is False; assert j.get('env',{})=={}"`
- `grep -q "Cooper Rush" docs/SUNDAY.md`
- `grep -q "Sunday-afternoon" docs/SUNDAY.md`
- `grep -q "jev_find" docs/SUNDAY.md`
- `grep -q "does not read the scratch" docs/REVIEW-REPORTS.md`
- `grep -q "mcp-jev" briefs/2026-09-19_jev-ceminidfs.md`
- `.venv/bin/ruff check src tests`
- `.venv/bin/python -m pytest tests/test_research_locks.py -q`

## NEVER

- Do not put API keys, tokens, or `~/.cemini/*` key files into mcp.json.
- Do not add `--jev-review` / `--qb-override` / auto-apply Jev.
- Do not default-on the three review flags.
- Do not retune FPPG or drop Q names.
- Do not scrape. Do not Enter.
- Do not rewrite `## Verify`.
- Do not commit.

## Plan

Auditors (OpenCode, DeepSeek Flash, Hy3, Nemotron free) agree: GO-WITH-GATES. Only operator salary CSV blocks a solve. Grok CLI did not write SYNTHESIS (proxy error).

Ship three documentation/config closes that change Sunday HITL, not the solver.

### 1. Project MCP jev

Copy the global jev block (command only, empty env) into `.cursor/mcp.json`.

### 2. SUNDAY.md Week 2 card

Add three short bullets after the existing T-90 line. Do not change the copy-paste commands except a comment that the salary file is afternoon-only.

### 3. REVIEW-REPORTS.md + Jev brief

Align the Jev paragraph with project MCP. State `review` reads lineups, not `--research-csv`. `jev_find` is for `late_swap_alert_report.csv` after the build.
