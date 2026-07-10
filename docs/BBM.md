# CeminiBBM — Best Ball Mania draft copilot

Interactive CLI for **Underdog Best Ball Mania VII** slow drafts. Sits alongside the weekly FanDuel DFS pipeline in the same repo; it does not replace `ceminidfs run` or lineup optimization.

**Design goals:** human-in-the-loop recommendations, exposure tracking across 150 entries, archetype portfolio balance, and post-draft audit — not autopick or Underdog scraping.

## Install

```bash
pip install -e ".[bbm,dev]"
```

Optional extras used by ADP name matching: `rapidfuzz`, `nflreadpy` (bye-week lookup). CI installs `[dev,data,optimize,bbm]`.

## Quick start

```bash
# One-time: generates data/bbm/player_registry.json + SQLite ledger
ceminidfs bbm draft-card --out briefs/bbm7-draft-card-$(date +%F).md

# Live draft (slot 1–12)
ceminidfs bbm draft --slot 4

# Resume an in-progress room
ceminidfs bbm draft --draft-id draft-20260624-143022 --slot 4
```

Runtime data lives under `data/bbm/` (gitignored): `bbm7.db`, `player_registry.json`.

## Operator workflow

**Two-monitor setup**

1. Underdog draft room on the left.
2. `ceminidfs bbm draft --slot N` on the right.
3. Read the printed top-3 → pick in Underdog → `p Player Name`.
4. After each opponent pick: `t Player Name` (or paste a board snapshot with `sync`).

**REPL commands**

| Command | Action |
|---------|--------|
| `p <name>` | Record your pick (advances round) |
| `t <name>` | Mark player taken by room (no round advance) |
| `p 2 <partial>` | Disambiguate when multiple matches (numbered list) |
| `undo` | Undo last pick or taken |
| `sync` | Paste multi-line board snapshot; blank line finishes |
| `exp` | Show players near exposure cap |
| `archetype B` | Override archetype for this draft (persisted) |
| `quit` | Save in-progress state |

Unknown opponents can be stubbed: `t Some Guy` creates a `stub:…` player so the board state stays accurate; stubs are excluded from top-3 recommendations.

**After draft**

```bash
ceminidfs bbm audit --draft-id draft-20260624-143022
```

**Weekly maintenance**

```bash
# ADP only
ceminidfs bbm refresh-adp --csv research/bbtb-adp-YYYY-MM-DD.csv

# ADP + optional CeminiDFS half-PPR projection column
ceminidfs bbm refresh-weekly --adp research/bbtb-adp.csv --projections reports/projections.csv

# Or use the shell wrapper
scripts/bbm_weekly_refresh.sh research/bbtb-adp.csv reports/projections.csv

# Reconcile Underdog exposure email CSV against local ledger
ceminidfs bbm reconcile --csv ~/Downloads/underdog_exposure.csv
```

Exposure policy details: see [BBM-EXPOSURE.md](BBM-EXPOSURE.md).

## CLI reference

| Command | Purpose |
|---------|---------|
| `bbm draft` | Interactive draft REPL (`--slot`, `--archetype`, `--draft-id`) |
| `bbm draft-card` | Markdown cheat sheet (BUY/FADE, stacks, exposure caps) |
| `bbm refresh-adp` | Merge BBTB-style ADP CSV into registry |
| `bbm refresh-weekly` | ADP + optional projections, then DB sync |
| `bbm audit` | Post-draft checklist + CLV estimate |
| `bbm reconcile` | Diff local exposure vs Underdog CSV |
| `bbm backtest` | Replay historical picks vs recommender |
| `bbm serve` | Local HTTP API for Chrome extension (`--slot`, `--draft-id`, `--port`) |

### Chrome extension (Phase 3)

Optional MV3 overlay for Underdog draft rooms — top-3 panel with **manual** board scan and **Rec** button to log picks to the ledger (you still submit picks on Underdog; no auto-pick).

**Underdog URL:** drafts run on **`https://app.underdogsports.com/`** (not legacy `underdogfantasy.com`). Extension v1.3.3+ matches both domains with improved board container detection.

```bash
# Terminal — local API (ledger remains source of truth)
# Golden / 1-max contests: add --single-entry (skips 150-entry exposure/combo caps)
ceminidfs bbm serve --slot 4 --archetype C --single-entry --port 8765

# Chrome: chrome://extensions → Load unpacked → extension/bbm-copilot/
# Popup: API base http://127.0.0.1:8765 → Test Connection → Save
# Reload the underdogsports.com draft tab after installing/updating extension
```

Or: `bash scripts/install-bbm-extension.sh`

Panel UX follows the [draft-co-pilot](https://github.com/howrealizdat/draft-co-pilot) zero-dependency MV3 pattern; recommendations come from the Cemini recommender via localhost, not ESPN VBD.

**Troubleshooting**

| Symptom | Fix |
|---------|-----|
| No panel | Reload extension; confirm URL is `app.underdogsports.com`; refresh draft tab |
| Terminal 404 spam | Popup → **Test Connection** (overwrites stale `draft_id` after re-running `serve`) |
| QB in early-round recs | Fixed v1.3.2+: QBs gated before round 6 (draft-card R6–7 band) |
| Board scan not found / wrong players | Fixed v1.3.3+: extension picks the Underdog container with the most player-name `aria-label`s. If it still falls back to `body`, confirm the page-wide scan before syncing. |

| Endpoint | Purpose |
|----------|---------|
| `GET /api/status` | Health + `draft_id` for extension auto-sync |
| `GET /api/recommendations` | Top-3 for current draft state |
| `POST /api/sync` | Apply scanned board names to `room_taken` |
| `POST /api/pick` / `POST /api/taken` | Record picks from extension (optional) |

See `extension/bbm-copilot/README.md` for install details.

### Backtest

Replay pick-by-pick data and measure structural rule pass rate, median CLV delta, and recommender latency.

```bash
# CI fixture (no download required)
ceminidfs bbm backtest --fixture tests/fixtures/bbm/sample_drafts.csv --sample 2 \
  --out reports/bbm_backtest.json

# Real BBM III data (manual download)
# Place CSV in data/bbm/bbm3_historical/ then:
ceminidfs bbm backtest --sample 100 --out reports/bbm_backtest.json
```

Data source: [Underdog Network — BBM III pick-by-pick](https://underdognetwork.com/football/best-ball-research/best-ball-mania-iii-downloadable-pick-by-pick-data).

## How recommendations work

At each pick the recommender scores available players:

```text
score = (projection_pts + clv_bonus) × stack_mult × archetype_mult × exposure_mult
```

Hard constraints (bye conflicts, roster limits, exposure caps, combo pair caps) filter candidates before ranking. **QB recommendations begin at round 6** (draft-card R6–7 band). Use `--single-entry` for 1-max contests to disable portfolio exposure/combo caps. Top 3 are printed with exposure warnings and stack flags.

**Archetypes (A–E)** route portfolio balance across 150 entries. The pivot state machine can switch archetype once per draft when the board blocks the primary plan.

## Module layout

```text
src/ceminidfs/bbm/
  cli.py           # REPL + subcommands
  session.py       # Ledger ↔ recommender bridge
  recommender.py   # Scoring + top-3
  validator.py     # Hard constraints
  archetype.py     # Portfolio router + pivot
  ledger.py        # SQLite exposure + draft state (WAL mode)
  registry.py      # Seed player registry + coverage checks
  normalize_adp.py # BBTB ADP / projection CSV merge
  reconcile.py     # Underdog exposure diff
  audit.py         # Post-draft checklist
  backtest.py      # BBM III replay harness
  api_server.py    # Local HTTP API for Chrome extension
  board_parse.py   # aria-label board name extraction
  draft_card.py    # Markdown cheat sheet
  config.py        # Strategy constants (caps, stacks, fades)
```

## CeminiDFS integration

| Existing module | BBM use |
|-----------------|---------|
| `models.scoring.score_half_ppr_season()` | Optional `projection_pts` column (half-PPR, no DK bonuses) |
| `export.normalize` patterns | Reference for ADP name normalization |
| `data/rosters` (via nflreadpy) | Bye-week lookup when syncing registry |

The weekly DFS pipeline (`fetch` → `project` → `optimize`) is unchanged. BBM shares the package and CLI entrypoint only.

## What this tool does not do

- Auto-pick or submit picks to Underdog (extension is read-only)
- Continuous DOM scraping (board scan is manual button only)
- Replace paid research tools (BBTB, Stokastic) — manual CSV import only

## Further reading

- Operator brief: [`briefs/2026-06-24_bbm7-draft-copilot-implementation-brief.md`](../briefs/2026-06-24_bbm7-draft-copilot-implementation-brief.md)
- Architecture map: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md#bbm-best-ball-mania-extension)
- P1/P2 patch plans: `briefs/2026-06-24_bbm7-p*-implementation-plan.md`
- SFB16 ADP context: [Scott Fish Bowl 16 — draft strategy, rankings and ADP (RotoWire, 2026-07-04)](https://www.rotowire.com/football/article/scott-fish-bowl-16-draft-strategy-rankings-and-adp-121124) — SFB drafts move July ADP while BBM VII slow drafts run; reading only, registry ADP stays BBTB CSV
