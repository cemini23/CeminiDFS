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

---

## 7. Public research notes (2026-07-19) — candidates only

Live §4 capture is still required before shipping v1.3.4. These are **unverified candidates** from open web + GitHub (not a substitute for DevTools on a live BBM room).

### Sources

| Source | What it adds |
|--------|----------------|
| [heithoffp/bestball](https://github.com/heithoffp/bestball) `chrome-extension/src/adapters/underdog.js` (no SPDX license on repo; cite only) | Live draft URL + concrete `data-testid` / class fragment selectors |
| Reddit r/BestBall — [Bag Manager](https://www.reddit.com/r/BestBall/comments/1sda3k2/i_built_a_free_chrome_extension_for_tracking_best/) / [update](https://www.reddit.com/r/BestBall/comments/1szwu39/my_free_best_ball_exposure_tracker_the_bag/) | Confirms May 2025 domain move `underdogfantasy.com` → `underdogsports.com` breaks host-scoped extensions until hosts updated |
| Draft Caddy Firefox listing | Declares host perms for both `underdogfantasy.com` and `underdogsports.com` |
| Brave web search | No public dump of full draft-room DOM; overlays/trackers are the useful trail |
| opencli Reddit / X | Reddit adapter returned empty for these queries; X “live” search was noisy on the word “extension” — not useful for selectors |

### Candidate tokens (verify in §4)

From `underdog.js` adapter (player **queue/grid**, not necessarily the drafted-picks ticker):

| Role | Candidate selector |
|------|--------------------|
| Draft URL path | `/draft/<uuid>` (`isDraftPage`: `^/draft/[a-f0-9-]+`) |
| Grid / inject root | `[role="grid"]` |
| Player row | `[data-testid="player-cell-wrapper"]` |
| Name cell | `[class*="playerName"]` |
| My pick cell | `[class*="playerPickCell"]` |
| Position chrome | `[class*="positionSection"]`, `[class*="positionHeader"]`, `[class*="playerPosition"]` |
| Row chrome | `[class*="rightSide"]`, `[class*="statCell"]`, `[class*="playerListSortButtons"]` |

**Gap vs our v1.3.3 list:** we try `data-testid*="draft-board|draft-room|pick-ticker|drafted|player"` and class `*DraftBoard*` / `*pick-ticker*` — we do **not** yet try exact `player-cell-wrapper` or `[role="grid"]`. Those are high-priority §4 checks and likely v1.3.4 selector adds **if** a live capture confirms they wrap drafted names (or that Scan Board should score the player grid instead of a separate “board” container).

### Operator focus when capturing

1. Confirm pathname is `/draft/...` on `app.underdogsports.com`.
2. Check whether drafted picks live under `[role="grid"]` / `player-cell-wrapper`, or a separate ticker — capture **both** if present.
3. Prefer exact `data-testid` values over hashed `styles__*__XXXX` classes (those break on rebuilds; see hashed `styles__active__A5wMB` in the public adapter).
