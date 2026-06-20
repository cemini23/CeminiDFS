# CeminiDFS Post-Phase 5 SUPER AUDIT — Auditor 4/6 (gpt-5.5-medium)

### Verdict
WARN — not live-slate ready as-is: default `fetch → project` likely starves DIY projection of historical PBP, then `projection_mode: auto` silently falls back to salary FPPG.

### Findings
| Severity | Finding | Evidence | Fix |
|----------|---------|----------|-----|
| P0 | Week fetch writes week-scoped PBP, projection needs prior weeks → empty historical PBP → FPPG fallback | fetch.py, engine.py, project.py | Preserve season PBP for projection; fail if DIY unavailable |
| P0 | `projection_mode: auto` silently falls back to FPPG | project.py, nfl_dfs.yaml | Default diy; require explicit fallback flag |
| P1 | Backtest zero-player weeks as 0.00 metrics | backtest.py | Minimum joined-player threshold |
| P1 | Benchmark TE join miss (receiving actuals force WR) | backtest.py, benchmark_compare.py | Roster-derived position |
| P1 | Weather forecast-only for historical | weather.py | Archive endpoint |
| P1 | Sim rerank mean + name-only index | sim_rerank.py | Quantile objective; id-based index |
| P1 | Ownership calibration no temporal guard | ownership.py | label week < projection week |
| P1 | DEF/DST FPPG fallback only | stats.py | DST model or manifest flag |
| P2 | Synthetic e2e avoids fetch/PBP bug | test_e2e_run.py | Integration test fetch→project |
| P2 | Tiny-slate relaxations mask constraints | optimize.py | Production fixture |

### Ship Recommendation
- Live slate ready? N · Backtest trustworthy? N · Sim rerank safe? N

### Root cause
Cache contract mismatch: fetch week-filters PBP; engine needs weeks `< target`; auto masks starvation as success.

### Confidence
high
