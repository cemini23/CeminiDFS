# Underdog DOM capture — operator brief (WS-B)

**Date:** 2026-07-11  
**Updated:** 2026-07-19  
**Status:** SHIPPED — extension v1.3.4 (research-driven selectors; live DevTools still welcome)  
**Unblocks:** — (v1.3.4 shipped from §7–§8 research candidates; live DevTools §4 still preferred for refinement)  
**Parent plan:** [2026-07-10_underdog-board-selector-fix-plan.md](2026-07-10_underdog-board-selector-fix-plan.md) (WS-A shipped v1.3.3; v1.3.4 selector refresh follows)

Extension v1.3.4 prepends high-priority 2026 candidates (`player-cell-wrapper`, `[role="grid"]`, `playerPickCell` / `playerName` / `positionSection`) and scores match + ancestors so row-level hits promote the multi-name board container over `body-fallback`. Exact live DevTools attrs in §4 are still welcome but not blocking.

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
CAPTURE_DATE: 2026-07-19 (YouTube research — not live DevTools)
OPERATOR: agent (YT frames) — operator still needed for exact attrs
DRAFT_URL_PATH: /draft/<uuid>  (inferred; see §8 — confirm on live room)
VIEWPORT: 1280×720 stream capture (not desktop Chrome)
CHROME_VERSION: N/A (YouTube)

BOARD_CONTAINER_TAG: unknown (video cannot expose DOM)
BOARD_CONTAINER_DATA_TESTID: CANDIDATE [role="grid"] / see §7–§8 — UNVERIFIED
BOARD_CONTAINER_CLASS: CANDIDATE [class*="DraftBoard"] etc — UNVERIFIED
BOARD_CONTAINER_ID: NONE observed on stream

PICK_CHILD_TAG: unknown
PICK_CHILD_DATA_TESTID: CANDIDATE player-cell-wrapper — UNVERIFIED (public adapter + UI match)
PICK_CHILD_CLASS: CANDIDATE [class*="playerName"] / playerPickCell — UNVERIFIED

ARIA_LABEL_SAMPLE_1: (visible text only) Ja'Marr Chase CIN  — exact aria-label UNVERIFIED
ARIA_LABEL_SAMPLE_2: (visible text only) Cam Ward QB · TEN · Bye 9 — exact aria-label UNVERIFIED
ARIA_LABEL_SAMPLE_3: (visible text only) Breece Hall NYJ — exact aria-label UNVERIFIED

V133_SCAN_SELECTOR: unknown from YT
NOTES: §8 YouTube 2026 streams. Splash Play / Club Fantasy / Fanatics often show OBS board overlays — only Spags native Underdog room frames count for Scan Board. Exact data-testid + aria-label still require one live DevTools paste.
```

---

## 5. Acceptance — v1.3.4 code sprint

Code sprint shipped from §7–§8 research candidates (operator green light 2026-07-19; live §4 DevTools not blocking).

- [x] `UNDERDOG_SELECTORS` in `content.js` includes high-priority research candidates early: exact `player-cell-wrapper`, `[role="grid"]`, `player-cell` / `playerPickCell` / `playerName` / `positionSection` (before broad `*=` patterns). §4 live tokens not claimed as verified attrs.
- [x] `collectBoardLabels()` scores match + ancestors by player-name `aria-label` count (len 4–60) so row hits promote grid/parent over a single cell; confirm-gated `body-fallback` retained when no candidate scores ≥1.
- [ ] Sample `aria-label` strings from live §4 — still UNVERIFIED from YT; operator verify parse on next live draft (`board_parse` fixtures optional).
- [x] `manifest.json` bumped to `1.3.4`; `docs/BBM.md` troubleshooting/version refs updated; `extension/bbm-copilot/README.md` version note updated.
- [ ] Manual checklist on a live draft room: Scan Board → synced counts, no `WARN page-wide scan`, status auto-clears after 3s when clean. **Operator verify on next live draft.**
- [x] `POST /api/sync` contract unchanged: `{draft_id, labels}`.

**Out of scope for v1.3.4:** `src/`, `tests/`, auto-pick, continuous scraping, React fiber hacks.

---

## 6. Handoff

v1.3.4 shipped 2026-07-19 from research candidates (YT + public adapter). Optional: still paste live DevTools into §4 if Scan Board mis-selects; use that for a follow-up selector tweak only.

---

## 7. Public research notes (2026-07-19) — candidates only

Used as the v1.3.4 selector source (operator green light 2026-07-19). Still **unverified on live DevTools** — refine if Scan Board mis-picks.

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

---

## 8. YouTube research — 2026 live drafts (2026-07-19)

Videos cannot expose `data-testid` / class strings. They **do** confirm the live 2026 Underdog draft-room chrome and visible name formats.

### Videos checked

| Video | Why 2026 | What we saw |
|-------|----------|-------------|
| [Spags — My Secret Weapon For Best Ball Drafts in 2026](https://www.youtube.com/watch?v=xc6OdCnoDQs) (streamed ~1 day before search) | Title + mid-stream slide **"July 17, 2026 — NFL Training Camp & Fantasy News Breakdown"** | **Best native Underdog UI** (~18–33 min): top nav Drafts / Pick'em / Live / Results / Rankings / News; horizontal pick ticker; left player pool (ADP + Proj); right My Team by position. Splash Play Monte Carlo overlay often covers center — ignore for selectors. |
| [Professional Fanatics — Underdog Best Ball Drafts LIVE \| 2026](https://www.youtube.com/watch?v=n3QSHt36b44) | Title 2026 | Custom OBS snake-board overlay (FILLED seats, color cells) — **not** native Underdog DOM. |
| [Club Fantasy — Best Ball Draft Strategies LIVE \| Underdog Fantasy Draft 2026](https://www.youtube.com/watch?v=kDNxlCYCCbI) | Title 2026 | "MOCK IT LIKE IT'S HOT" board overlay — **not** native Underdog DOM. |

Frame dumps (local, gitignored via handoffs): `briefs/handoffs/yt-frames/ud-spags*.png`, `ud-fanatics*.png`, `ud-club*.png`.

### Native Underdog chrome (Spags frames ~1100s / 1500s / 2000s)

| Region | Visible structure | Scan Board implication |
|--------|-------------------|------------------------|
| Top nav | Drafts, Pick'em, Live, Results, Rankings, News feed | Confirms `app.underdogsports.com` product shell |
| Pick ticker | Cards: username · `R.P \| overall` · player · on-clock timer | Drafted names may live here **and/or** in a grid — capture both |
| Player pool (left) | Rows: name, POS, team, bye, ADP, Proj P | Aligns with public `[data-testid="player-cell-wrapper"]` + `[role="grid"]` |
| My Team (right) | Position sections with drafted names + team abbrev | Aligns with `[class*="positionSection"]` / `playerPickCell` |

### Visible name strings (for parse fixtures — not proven aria-labels)

From native UI frames (approximate on-screen text):

- `Ja'Marr Chase` / `Ja'Marr Chase CIN`
- `Cam Ward` / `Cam Ward QB · TEN · Bye 9`
- `Breece Hall` / `Breece Hall NYJ`
- `Travis Etienne Jr.` / `Travis Etienne Jr. NO`

Our `board_parse` already expects patterns like `Select Ja'Marr Chase, WR, CIN` — **still need one real `aria-label=` paste** to confirm 2026 wording.

### Verdict

- YouTube **confirms** 2026 Underdog draft room layout and that v1.3.4 should prioritize `player-cell-wrapper` + `[role="grid"]` candidates from §7.
- YouTube **does not** complete §4 acceptance for shipping — one live DevTools capture (or login + active `/draft/...` room) remains the gate.
- Prefer Spags-style **native app screenshare**; skip streams that only show OBS/mock boards.
