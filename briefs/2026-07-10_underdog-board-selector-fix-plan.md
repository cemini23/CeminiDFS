# Underdog board selector fix — WS-A

**Date:** 2026-07-10
**Status:** SHIPPED — extension v1.3.3, host-aware selectors, container scoring, selector surfaced in status
**Trigger:** Frequent false "Board container not found" page-wide fallback on `app.underdogsports.com`.

## Workstreams

| WS | Scope | Files |
|----|-------|-------|
| A | Extension: host-aware selector lists; score containers by player-name `aria-label` count; surface selector; fall back to `body` only after all candidates fail | `extension/bbm-copilot/content.js`, `extension/bbm-copilot/manifest.json`, `extension/bbm-copilot/README.md` |
| B | Docs + troubleshooting | `docs/BBM.md` |
| C | Brief | `briefs/2026-07-10_underdog-board-selector-fix-plan.md` |

## Acceptance

- [x] When `location.hostname` includes `underdogsports.com`, Underdog-specific selectors are tried before generic `BOARD_SELECTORS`.
- [x] Underdog selectors use `data-testid`, draft room, pick ticker, and drafted-player patterns — no React fiber hacks.
- [x] Every matching container is scored by counting `aria-label` values that look like player names (length 4–60); the container with the highest count wins (minimum threshold 1).
- [x] `collectBoardLabels` still returns `{labels, warning, selector}`; `body` fallback remains confirm-gated.
- [x] `scanBoard` status text includes the matched selector; fallback logs a `console.warn` with the selector.
- [x] `POST /api/sync` body contract unchanged: `{draft_id, labels}`.
- [x] Manifest bumped to `1.3.3`; README and `docs/BBM.md` version references updated.

## Out of scope

- Auto-pick / Underdog DOM automation.
- Changes to `src/`, `tests/`, or `api_server.py`.
- Guaranteed Underdog DOM stability; selectors are best-effort and degrade to the page-wide fallback.
