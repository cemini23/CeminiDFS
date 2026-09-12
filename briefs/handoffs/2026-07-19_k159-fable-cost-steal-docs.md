# Handoff — K159 fable-advisor pipeline cost steal (docs only)

**Lane:** easy  
**WorkDir:** `/Users/claudiobarone/Projects/CeminiDFS`  
**Brief:** `briefs/2026-07-11_k159-fable-advisor-pipeline-cost-steal.md`

## Goal

Document the K159 cost-discipline pattern for this repo (docs only — no `src/` code).

## Pattern to capture

1. Use **fable-advisor** for projection-layer refactors (nflverse ingest, ownership sim, pydfs hooks).
2. Use implementer lane (Grok / Codex / grok-implementer) for routine file edits + test fixes only; architect reviews the diff.
3. Log token delta on one bounded slice before wide adopt.
4. **NO-GO** if implementer lane unavailable (Grok must be authenticated).

## Acceptance

1. Add a short section to `ROADMAP.md` (or a `docs/` note linked from ROADMAP) titled something like "K159 — pipeline cost discipline" describing the pattern above.
2. Mark the brief as applied / process-adopted (date 2026-07-19); note that this is process guidance, not a code ship.
3. Add K159 to Shipped tracks as process/docs (not a feature).
4. Do **not** edit `src/`, `tests/`, or `extension/`.
5. Do **not** invent a token-delta log file with fake numbers — just document that the operator should log one bounded slice before wide adopt.

## Out of scope

- Actually running a calibration refactor
- Underdog DOM / K163
