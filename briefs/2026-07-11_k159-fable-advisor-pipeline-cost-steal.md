---
title: K159 — fable-advisor pipeline cost steal (CeminiDFS)
type: brief
target: CeminiDFS
created: 2026-07-11
updated: 2026-07-19
status: process-adopted
adopt_date: 2026-07-19
---

## Target

`../projects/CeminiDFS` — NFL projection pipeline cost discipline.

## Summary

K159 pattern steal — architect (Fable) plans pipeline changes; Grok/Codex implement scripts/tests; avoid burning Opus tokens on boilerplate.

## Body

1. Use fable-advisor for projection-layer refactors (nflverse ingest, ownership sim, pydfs hooks).
2. Implementer lane for routine file edits + test fixes only; architect reviews diff.
3. Log token delta on one bounded slice (e.g. single position model calibration script) before wide adopt.
4. **NO-GO** if implementer lane unavailable.

## Process adopted (2026-07-19)

- Documented in `ROADMAP.md` under **K159 — pipeline cost discipline**.
- Added to Shipped tracks as **process/docs only** (not a feature/code ship).
- No `src/`, `tests/`, or `extension/` edits.
- No calibration refactor run; no fabricated token-delta log. Operator logs one bounded slice before wide adopt.

## Sources

- @osint-wiki/entities/tools/fable-advisor.md
- @osint-wiki/sources/eval-multi-wiki-repo-evaluation-strategy-2026-07-11.md
