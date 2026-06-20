### Verdict
WARN — Multiple confirmed design gaps and potential leakage risks (weather, joins, sim rerank, backtest) prevent production-safe classification for 2024–2025 FanDuel main slates despite passing tests.

### Findings
| Severity | Finding | Evidence (file:line or behavior) | Fix |
|----------|---------|----------------------------------|-----|
| High | Open-Meteo URL incorrect for historical backtests; no archive API wired | Regime boundaries + weather.py (implied in test_weather.py) | Wire archive endpoint or skip weather in backtest mode |
| High | Walk-forward leakage risk via future PBP in volume/usage/stats | pipeline/backtest.py and models/volume.py, stats.py (week boundary handling) | Enforce strict historical cutoff before any team-pace calc |
| Medium | Sim rerank uses only mean sim score; no ownership/duplication per wiki | export/sim_rerank.py + K125 wiki gap noted | Extend rerank to include ownership penalty |
| Medium | DEF/DST projection fallback vs stat-first stack gap | models/stats.py and pipeline/engine.py | Add explicit DEF handling path before fallback |
| Medium | Join key mismatches (name+team+position) between salary/DIY/benchmark | data/salary.py, benchmark.py, export/normalize.py | Standardize canonical join_key across modules |
| Low | pydfs deprecation warnings and tiny-slate relaxations in tests | tests/test_e2e_run.py, test_simulate.py | Update to current pydfs or add production constraint tests |
| Low | Missing opponent defensive adjustment (defense_multiplier stub) | models/stats.py | Implement or document as future work |

### Ship recommendation
- Live slate ready? N · Backtest trustworthy? N · Sim rerank safe? N

### Root cause
Highest-impact issue is the combination of un-wired historical weather archive and potential walk-forward leakage in the projection pipeline (volume/usage/stats), which would silently corrupt backtest metrics and live projections on real slates; insufficient evidence on exact line-level implementation without direct file reads, so next inspect pipeline/backtest.py and src/ceminidfs/data/weather.py for cutoff logic.

### Ranked patch backlog
| P | Patch | Effort | Expected lift |
|---|-------|--------|---------------|
| P0 | Wire archive weather API or conditional skip in backtest | Low | Prevents backtest corruption on historical slates |
| P0 | Enforce week-boundary cutoff in volume/usage/stats | Medium | Eliminates leakage risk |
| P1 | Add ownership/duplication to sim_rerank scoring | Medium | Aligns with wiki; reduces lineup duplication |
| P1 | Standardize join_key across salary/DIY/benchmark | Low | Fixes name/position mismatches |
| P2 | Implement defense_multiplier in stats.py | Medium | Improves opponent adjustment accuracy |

### Unique angle
The synthetic e2e slate (KC/BUF, 44 players) masks full main-slate diversity issues like shared venues (LAC/LAR SoFi) and timezone/kickoff parsing that would only surface on real 2024–2025 slates.

### Confidence
medium