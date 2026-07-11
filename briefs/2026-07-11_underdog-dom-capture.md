# Underdog DOM capture — operator brief (WS-B)

**Date:** 2026-07-11  
**Status:** WAITING ON CAPTURE  
**Unblocks:** Extension v1.3.4 code sprint (`UNDERDOG_SELECTORS` refresh in `extension/bbm-copilot/content.js`)  
**Parent plan:** [2026-07-10_underdog-board-selector-fix-plan.md](2026-07-10_underdog-board-selector-fix-plan.md) (WS-A shipped v1.3.3)

Extension v1.3.3 scores containers by player-name `aria-label` count but still falls back to `body-fallback` on some live Underdog draft rooms. Before we ship v1.3.4, an operator must capture the **current** Underdog DOM tokens from a real draft and paste them into §4 below.

---

## 1. When to capture

Capture **once** when **all** of the following are true:

| Condition | Why |
|-----------|-----|
| You are in an **active BBM VII slow draft** on `https://app.underdogsports.com/` | Draft-room DOM differs from lobby / marketing pages |
| At least **3 picks** are visible on the board (yours or room) | Empty boards lack drafted-player nodes |
| Cemini panel is loaded; **Scan Board** status or console shows `body-fallback` or the confirm dialog *"Board container not found — page-wide scan"* | Confirms v1.3.3 selectors missed the real container |
| Extension is **v1.3.3** (check `chrome://extensions`) | Baseline before v1.3.4 selector patch |

**Do not capture** on `underdogfantasy.com` legacy URLs, mobile viewport, or a finished draft — those DOMs will not match live BBM rooms.

Optional sanity check before DevTools: open the panel status after Scan Board → Cancel on the fallback dialog. Note the selector string if shown (e.g. `body-fallback`).

---

## 2. DevTools capture steps

1. **Open draft room** — full desktop width; zoom 100%.
2. **Open DevTools** — `Cmd+Option+I` (Mac) / `F12` (Windows) → **Elements** tab.
3. **Inspect the draft board container**
   - Use the element picker (top-left of DevTools) and click the **main draft board** — the region listing drafted picks / pick ticker, **not** the Cemini overlay, nav, or chat.
   - In the DOM tree, walk **up** to the nearest ancestor that wraps **all** visible drafted picks (usually 1–3 levels above a single player cell).
4. **Copy selector tokens** from that ancestor (and one drafted pick child):
   - `data-testid` — full attribute value, e.g. `data-testid="draft-board-root"`
   - `class` — copy the **full** `class` string on the container and on one drafted pick row/card
   - `id` — if present (often empty on Underdog)
   - Tag name — e.g. `div`, `section`
5. **Sample `aria-label` strings** from **3 drafted picks** (different teams if possible):
   - Right-click a drafted player cell → Inspect → find the node with `aria-label="…"`
   - Paste the **exact** string (including punctuation, team abbrev, pick number if embedded)
6. **Record what v1.3.3 matched** (if anything):
   - After Scan Board, check panel status for `selector: …` or console `BBM:` warning line
7. **Screenshot** (optional) — redacted crop of Elements panel showing container + one pick node; attach path or paste into §4.

---

## 3. What to paste into this brief (§4)

Fill every field. Use literal values from DevTools — do not paraphrase class fragments.

| Field | Example shape |
|-------|----------------|
| Capture date / operator | `2026-07-11 / cb` |
| Draft URL path | `/pick-em/…` or full path (omit query tokens) |
| Viewport | `1920×1080`, Chrome version |
| Board container `data-testid` | `draft-board-…` or `NONE` |
| Board container `class` | full string |
| Board container tag | `div` |
| Drafted pick child `data-testid` | per pick row |
| Drafted pick child `class` | full string |
| Sample `aria-label` ×3 | exact strings |
| v1.3.3 Scan Board selector | `body-fallback` or matched selector |
| Notes | mobile layout, ad overlay, etc. |

---

## 4. Operator capture (paste below)

```text
CAPTURE_DATE:
OPERATOR:
DRAFT_URL_PATH:
VIEWPORT:
CHROME_VERSION:

BOARD_CONTAINER_TAG:
BOARD_CONTAINER_DATA_TESTID:
BOARD_CONTAINER_CLASS:
BOARD_CONTAINER_ID:

PICK_CHILD_TAG:
PICK_CHILD_DATA_TESTID:
PICK_CHILD_CLASS:

ARIA_LABEL_SAMPLE_1:
ARIA_LABEL_SAMPLE_2:
ARIA_LABEL_SAMPLE_3:

V133_SCAN_SELECTOR:
NOTES:
```

---

## 5. Acceptance — future v1.3.4 code sprint

A follow-up **code-only** sprint (WS-A v1.3.4) may start only when §4 is filled and reviewed. That sprint is **done** when:

- [ ] `UNDERDOG_SELECTORS` in `content.js` includes at least one selector derived from §4 `BOARD_CONTAINER_*` tokens (prefer `data-testid` exact or prefix match before class-only).
- [ ] `collectBoardLabels()` on the captured draft URL scores the real board container **above** `body` fallback (status shows a non–`body-fallback` selector; no confirm dialog on a normal scan).
- [ ] Sample `aria-label` strings from §4 are parsed by `board_parse.extract_names_from_aria_labels` (manual check or unit fixture seeded from capture).
- [ ] `manifest.json` bumped to `1.3.4`; `docs/BBM.md` troubleshooting row updated; `extension/bbm-copilot/README.md` version note updated.
- [ ] Manual checklist on the **same** draft room: Scan Board → synced counts, no `WARN page-wide scan`, status auto-clears after 3s when clean.
- [ ] `POST /api/sync` contract unchanged: `{draft_id, labels}`.

**Out of scope for v1.3.4:** `src/`, `tests/`, auto-pick, continuous scraping, React fiber hacks.

---

## 6. Handoff

When §4 is complete, change **Status** at the top to `CAPTURED — ready for v1.3.4` and ping the implementer. Do not edit `extension/` until the code sprint starts.
