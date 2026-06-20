# CeminiDFS Post-Phase 5 SUPER AUDIT — Auditor 2/6 (gemini-3.1-pro)

### Verdict
FAIL — Sim rerank defeats simulations by averaging outcomes instead of targeting ceiling quantiles, and canonical schema drops FanDuel names leading to a hard crash.

### Findings
| Severity | Finding | Evidence (file:line or behavior) | Fix |
|----------|---------|----------------------------------|-----|
| **P0** | **Sim rerank optimizes for median, not ceiling** | `export/sim_rerank.py:66` uses `matrix[indexes, :].sum(axis=0).mean()`. | Change scoring metric to a high quantile (e.g., `np.quantile(..., 0.85)`) or win probability. |
| **P0** | **Canonical schema drops FD names, crashing rerank** | `export/canonical.py:31` omits `Nickname`. Canonical CSV drops it; `sim_rerank.py:150` raises `KeyError`. | Add `"Nickname", "First Name", "Last Name"` to `OPTIONAL_DISPLAY_FIELDS`. |
| **P1** | **Timezone mismatch in kickoff weather** | `data/weather.py:143` aligns ET schedule `game_time` to local-time Open-Meteo `timezone="auto"`. | Hardcode Open-Meteo param to `timezone="America/New_York"` to match ET schedules. |
| **P1** | **Ownership calibration leaks in-sample** | `models/ownership.py:85` fits Ridge/ElasticNet on the target dataset without holdout. | Apply cross-validation or fit calibration strictly on historical weeks. |
| **P2** | **SoFi Stadium incorrectly exposed to weather** | `data/stadiums.py:55` tags LAC/LAR as `semi_open`, which `is_weather_exposed` treats as open. | Hardcode `semi_open` as weather-shielded for rain/snow, or change roof type to `dome`. |

### Ship recommendation
- Live slate ready? **N** (sim rerank mathematical flaw and KeyError)
- Backtest trustworthy? **Y** (walk-forward PBP filtering is robustly applied)
- Sim rerank safe? **N** (fails to execute on FanDuel; neuters variance)

### Root cause
Sim rerank mean collapses Monte Carlo to expected value; canonical.py strips Nickname breaking name joins.

### Confidence
high
