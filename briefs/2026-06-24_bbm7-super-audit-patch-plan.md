# BBM7 super-audit — patch implementation plan

**Source:** 5-model super audit 2026-06-24 (3 Cursor + GLM 5.2 + Fusion)

## Agent split (parallel)

| Agent | Files | Tasks |
|-------|-------|-------|
| A (kimi) | `ledger.py`, `session.py` | exposure denominator, draft state metadata, record_taken idempotency, INSERT OR REPLACE |
| B (kimi) | `validator.py`, `recommender.py`, `config.py` | QB/TE bye fix, CRITICAL severities, combo cap, round-band fade |
| C (gpt) | `cli.py`, `registry.py`, `tests/bbm/` | archetype persist, player lookup, tests |

## Verification

```bash
pytest tests/bbm/ -q
ruff check src/ceminidfs/bbm tests/bbm
```
