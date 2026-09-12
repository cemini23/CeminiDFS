# Handoff — Underdog board selectors v1.3.4 (WS-A)

**Lane:** hard  
**WorkDir:** `/Users/claudiobarone/Projects/CeminiDFS`  
**Operator green light:** 2026-07-19 — implement from research candidates (YT + public adapter); live DevTools still preferred later but not blocking.

**Briefs:**
- `briefs/2026-07-11_underdog-dom-capture.md` (§5 acceptance, §7–§8 research)
- Parent: `briefs/2026-07-10_underdog-board-selector-fix-plan.md` (v1.3.3 shipped)

## Goal

Ship extension **v1.3.4** so Scan Board prefers real Underdog 2026 draft-room containers over `body-fallback`.

## Required code changes

### 1. `extension/bbm-copilot/content.js`

Prepend high-priority selectors to `UNDERDOG_SELECTORS` (exact / specific **before** broad `*=` patterns):

```js
'[data-testid="player-cell-wrapper"]',  // or closest ancestor strategy — see note
'[role="grid"]',
'[data-testid*="player-cell"]',
'[class*="playerPickCell"]',
'[class*="playerName"]',
'[class*="positionSection"]',
```

Keep existing UNDERDOG_SELECTORS after these. Do **not** remove scoring logic (`collectBoardLabels` / aria-label count). Prefer containers with the most player-name-like aria-labels (len 4–60).

**Important:** `player-cell-wrapper` is a **row**, not the board root. Scoring should still pick the **ancestor container** with the highest player-name aria-label count among candidates. If current logic scores the matching element itself, ensure matching `[role="grid"]` or a parent of many `player-cell-wrapper` rows wins over `body`. Do not break the confirm-gated body fallback.

Contract unchanged: `collectBoardLabels` → `{labels, warning, selector}`; `POST /api/sync` body `{draft_id, labels}`.

### 2. Version bumps + docs

- `extension/bbm-copilot/manifest.json` → `"version": "1.3.4"`
- `extension/bbm-copilot/README.md` → note v1.3.4 selector refresh
- `docs/BBM.md` → troubleshooting / version refs: v1.3.4 (board scan prefers `player-cell-wrapper` / `[role="grid"]` candidates from 2026 research)

### 3. Brief status

Update `briefs/2026-07-11_underdog-dom-capture.md`:
- Status → `SHIPPED — extension v1.3.4 (research-driven selectors; live DevTools still welcome)`
- Check off §5 items that code can satisfy; leave manual draft-room checklist unchecked or note “operator verify on next live draft”
- Do **not** claim live DevTools §4 fields were filled with exact attrs

## Out of scope

- `src/`, `tests/` (brief says out of scope — optional tiny unit fixture for sample visible names is OK only if already easy; prefer no test churn)
- Auto-pick, continuous scraping, React fiber hacks
- OBS/mock boards from YouTube (ignore)

## Acceptance (code)

- [ ] UNDERDOG_SELECTORS includes `[role="grid"]` and `player-cell-wrapper` / `player-cell` patterns early in the list
- [ ] Manifest `1.3.4`; README + `docs/BBM.md` updated
- [ ] Sync contract unchanged
- [ ] Brief status updated
- [ ] No secrets; no `.env` edits

## Cite only (do not copy proprietary code)

Public adapter patterns from heithoffp/bestball `underdog.js` (no SPDX) — selectors only as listed in brief §7.
