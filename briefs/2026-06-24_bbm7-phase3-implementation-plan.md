# BBM7 Phase 3 — browser overlay + draft-co-pilot pattern

**Date:** 2026-06-24  
**Prerequisite:** P0–P2 + docs shipped (`f99d8ec`)  
**Verdict:** **Ship** — reduces two-monitor friction; manual-only crawl stays ToS-safe per brief §10.

---

## Scope (2 brief items)

| ID | Brief item | Deliverable | Acceptance |
|----|------------|-------------|------------|
| P3-1 | MV3 read-only overlay; manual trigger; aria-label DOM crawl | `extension/bbm-copilot/` | Load unpacked; panel shows top-3; Scan Board POSTs names to local API |
| P3-2 | Fork pattern: [draft-co-pilot](https://github.com/howrealizdat/draft-co-pilot) | Same extension + `bbm/api_server.py` | MV3 zero-dep panel UX; **Cemini recommender via localhost**, not ESPN VBD |

**Not shipping:** auto-pick, continuous polling, Underdog API client, cloud sync.

---

## Architecture

```text
Underdog tab (MV3 content script)
  ├─ manual "Scan board" → aria-label crawl → player names[]
  └─ poll GET /api/recommendations → render top-3 overlay

Terminal: ceminidfs bbm serve --slot 4 [--draft-id ID] --port 8765
  └─ stdlib HTTP JSON API → session.get_recommendations + ledger sync
```

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness |
| `/api/state` | GET | draft_id, slot, round, pick_num, archetype |
| `/api/recommendations` | GET | Top-3 JSON |
| `/api/sync` | POST | `{names:[]}` → record_taken for new names |
| `/api/pick` | POST | `{name}` → record_pick |
| `/api/taken` | POST | `{name}` → record_taken |

CORS: `Access-Control-Allow-Origin: *` (localhost-only bind).

---

## Agent split

| Agent | Model | Files |
|-------|-------|-------|
| A | kimi-k2.5 | `api_server.py`, `board_parse.py`, `cli serve`, tests |
| B | kimi-k2.5 | `extension/bbm-copilot/*` (manifest, content, popup, styles, README) |

---

## Verify

```bash
pytest tests/bbm/ -q
ruff check src/ceminidfs/bbm tests/bbm extension/bbm-copilot  # JS excluded from ruff
# Manual: serve + load extension on Underdog draft page
```
