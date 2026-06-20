# Super audit synthesis — CeminiDFS Post-Phase 5

**Mode:** prod-ship + code-debug · **Pack:** `reports/audit/pack-ceminidfs-postphase5` · **Built:** 2026-06-20

| Slot | Channel | Model | Verdict |
|------|---------|-------|---------|
| 1 | cursor | claude-opus-4-8-thinking-high | WARN |
| 2 | cursor | gemini-3.1-pro | FAIL |
| 3 | cursor | kimi-k2.5 | WARN |
| 4 | cursor | gpt-5.5-medium | WARN |
| 5 | api | openrouter/fusion | WARN→FAIL conditional |
| 6 | api | x-ai/grok-4.3 | WARN |

## Strong consensus (≥4 auditors)

- **Sim rerank mean invariance** — `score_lineup` uses `.mean()` on summed sims; correlation/variance do not affect ranking (P0).
- **Weather timezone misalignment** — nflverse gametime is ET; Open-Meteo `timezone=auto` returns local hours (P1).
- **Missing opp/game in correlation pipeline** — `correlation.py` reads `opp`/`game`; stats frame has `opponent` only (P0/P1).
- **`defense_multiplier` stub** — always 1.0; largest DIY mis-ranking gap (P1 design).
- **Historical weather** — forecast API wrong for backtest/archive dates (P1).
- **Fetch PBP week-scope vs projection need** — week-filtered `pbp.parquet` starves historical cutoff; `auto` masks with FPPG (P0).
- **Benchmark/receiving position** — TEs get `WR` in actuals aggregation → join_key mismatch (P1).
- **Synthetic 2-team e2e** — tiny-slate relaxations untested at main-slate scale (P2).

## Unique (single auditor — investigate)

- [Opus] Saved sim-matrix row order can desync from normalized CSV when parquet lacks name column.
- [Kimi] Cholesky jitter grows to 1e-3 without PSD re-check.
- [Fusion] nflverse retroactive stat revisions leak look-ahead if backtest uses current snapshot.
- [GPT 5.5] Backtest zero-player weeks report 0.00 metrics without failing.

## Conflicts

| Topic | Opus | Gemini | Resolution |
|-------|------|--------|------------|
| Walk-forward leakage | Safe (`week < week`) | Backtest trustworthy | Code confirms strict cutoff; trust relative trends only |
| Live slate ready | Qualified Y (plumbing) | N (sim rerank + canonical) | Fix P0 sim/canonical/fetch before live |

## Ranked patch backlog (execution order)

| P | Patch | Effort |
|---|-------|--------|
| P0 | Sim rerank → P90 quantile | 30m |
| P0 | Fetch: season-scope PBP in week cache | 30m |
| P0 | `projection_mode: diy`; explicit `allow_fppg_fallback` | 30m |
| P0 | Correlation: alias `opponent`→`opp`, emit `game` | 1h |
| P0 | Canonical Nickname/First/Last pass-through | 15m |
| P1 | Weather ET timezone + archive for past dates | 1h |
| P1 | Receiving actuals position from PBP roster | 45m |
| P1 | Ownership label week guard | 30m |
| P1 | Cholesky jitter cap + fail loud | 30m |
| P1 | Late-swap lock verification | 30m |
| P1 | Sim matrix requires name column | 30m |
| P1 | SoFi/semi_open wind null | 15m |
| P2 | Backtest min-player threshold | 30m |

**Overall:** SHIP-WITH-FIXES — implement P0/P1 above, re-run tests, then bugbot.
