# BBM Golden draft failure — fix plan

**Date:** 2026-07-08  
**Status:** SHIPPED — extension v1.3.2, `--single-entry`, QB R6 gate, draft_id auto-sync  
**Trigger:** Golden fast draft — panel never loaded (`underdogsports.com`), terminal 404s (stale `draft_id`), Burrow at pick 22 (no QB round gate).

## Workstreams

| WS | Scope | Files |
|----|-------|-------|
| A | Extension: domain done; draft_id sync; bump v1.3.2 | `manifest.json`, `content.js`, `popup.js`, `README.md` |
| B | API serve UX + `--single-entry` flag | `api_server.py`, `cli.py`, `ServerConfig` |
| C | Recommender: QB before R6 filter; single-entry skips exposure/combo | `recommender.py`, `session.py`, `config.py` |
| D | Docs + install script | `docs/BBM.md`, `scripts/install-bbm-extension.sh` |
| E | Tests | `tests/bbm/test_recommender_rounds.py`, `tests/bbm/test_api_contracts.py` |

## Acceptance

- [x] `syncDraftIdFromServer` overwrites stale storage when server `draft_id` differs
- [x] `serve` prints "Server ready" not "Waiting for extension"
- [x] `--single-entry` on `serve`/`draft`: no exposure prune, no combo cap filter
- [x] QB candidates excluded from recs when `current_round < 6`
- [x] Tests pass; extension v1.3.2

## Out of scope

- Auto-pick / Underdog DOM automation
- Full `underdogsports.com` DOM selector audit (panel inject only)
