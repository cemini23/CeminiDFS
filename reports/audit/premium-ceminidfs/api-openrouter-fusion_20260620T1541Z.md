I'll run the expert panel on this audit before synthesizing my verdict.# CeminiDFS Post-Phase 5 Super Audit — Slot 5/6 (api-openrouter-fusion)

> **Scope honesty up front:** the data pack paths resolved to specs, not a live source tree I could line-walk. Every verdict below is a high-prior pattern judgment with the concrete grep/probe needed to *confirm* it against the repo. I separate **confirmed-bug-class** (architecturally near-certain in this design) from **design gap / future work**, per your constraint.

---

### Verdict

**WARN → conditional FAIL** for 2024–2025 real-money FanDuel main slates. The modeling is sophisticated and 103 green tests is a real baseline, but ship safety hinges on a handful of *silent-corruption* surfaces (join coverage, walk-forward discipline, historical-weather endpoint, final-lineup validation) that ordinary unit tests don't close. If the three P0 guards below already exist and pass, this upgrades to **WARN**; if any of the FAIL tripwires are present, hold the slate.

---

### Findings

| Severity | Finding | Evidence (probe / behavior) | Fix |
|----------|---------|----------------------------------|-----|
| **P0** | **Walk-forward leakage risk** in volume/usage/stats/sim/backtest. Classic: rolling/expanding/`transform('mean')` computed on the full panel then sliced by week, or `week <= W` instead of `< W`. Inflates backtest metrics silently. | `grep -rn "\.rolling(\|\.ewm(\|\.expanding(\|transform('mean')"`; confirm each is preceded by `.shift(1)` and team-pace PBP filters `game_id/week < W`. `models/volume.py`, `stats.py`, `pipeline/backtest.py`. | Centralize `build_features_for_slate(season, week, lock_time)` with cutoff filter; add `assert_no_future_rows(features, asof_week)` tripwire. |
| **P0** | **Join coverage unguarded** — salary↔DIY on `name+team+position`. Inner join silently drops studs; NaN→0 masks the loss. Suffixes (Jr/II/III), punctuation (D.J./DJ, Amon-Ra St. Brown), team drift (LA/LAR, WSH/WAS, JAC/JAX). | `grep -rn "merge(.*name.*team.*position\|how=\"inner\""`; row-count deltas salary→merged with no failure. | Canonical normalizer + 32-team alias map at every ingest; switch to `how="left"` + assert unmatched-salaried-active rate ≈ 0, **log dropped names**. |
| **P0** | **DST representation mismatch** — FanDuel position `D` + full team name ("Chicago Bears"); nflverse `DST` + abbreviation (`CHI`). If projection layer keys `DEF` while salary keys `DST`, **every defense silently drops**. | `grep -rn "'DST'\|'DEF'\|\bDEF\b\|D/ST"` — confirm one canonical token end-to-end; inspect `data/ownership_labels.py`, `export/normalize.py`. | Synthetic `DST_<ABBR>` id; map FD names→abbr; force single position token. |
| **P0** | **Open-Meteo historical endpoint wrong** for backtests — pack explicitly notes archive API "not wired." `/v1/forecast` holds ~2wk; historical weeks return empty/garbage → silent "no weather" → kills wind adjustment and invalidates wind-tier calibration. | `grep -rn "open-meteo\|/v1/forecast\|/v1/archive"` in `data/weather.py`. | Date-conditional host: `archive-api.open-meteo.com/v1/archive` for past slates; assert hourly array non-empty and spans kickoff. |
| **P0** | **Kickoff-hour timezone alignment** — selecting hourly weather at midnight UTC or fixed offset instead of actual local kickoff reads the wrong conditions (1pm ET ≠ 13:00 UTC). | `grep -rn "hourly\|timezone\|\.iloc\[0\]"` in `weather.py`. | Convert kickoff→UTC, request `timezone=UTC`, match by exact `time == kickoff_hour`; assert a match exists. |
| **P0** | **Copula matrix PSD repair** — patchwork empirical + prior correlations are rarely PSD; raw `cholesky` either crashes (loud) or silent eigen-clip yields wrong dependence. | `grep -rn "cholesky\|eigh\|nearest\|is_pos_def"` in `models/correlation.py`, `simulate.py`. | Higham nearest-correlation / eigen-clip + renorm before factorization; log Frobenius distance (large = inconsistent priors). |
| **P0** | **Final-lineup validation gate** independent of solver. Trusting the optimizer's own constraints is how illegal lineups (DST in FLEX, dup player via FLEX, salary>$60k, <2 games, post-projection OUT) reach a live contest. | `grep -rn "def validate_lineup\|def validate"` in `export/optimize.py`, `orchestrator/validate.py`. | Re-check all FD constraints on the emitted lineup; refuse export on failure. |
| **P0** | **RunManifest built-but-never-written** (flagged open in Phase 0). Partial/successful runs look identical; no provenance; **escalates if late-swap reads manifest to know lock state.** | `grep -rn "RunManifest"` — confirm exactly one `.write()` on the success path AND a downstream reader. `orchestrator/run.py`. | Atomic `manifest.write()` as terminal success step; refuse to emit lineups if unwritten. |
| **P0** | **Silent orchestration failures** — `except Exception: pass/continue` in fetch/join yields partial pools → valid-looking corrupted lineups. (Phase 0 "silent orchestration" — verify fixed.) | `grep -rn "except.*:\s*pass\|except.*:\s*continue"`. | Log-and-fail or quarantine + one completeness gate before optimize. |
| **P0/P1** | **Ownership label leakage** — ridge trained on same-slate actual ownership (only available post-lock) → great backtest, fails live. P0 *once ownership feeds the rerank leverage term*. | `models/ownership.py`, `data/ownership_labels.py`; `grep -rn "KFold\|shuffle=True\|fit_transform"`; check feature list for same-slate actuals. | Walk-forward refit (`train_slate_time < current`); strip non-pre-lock features; report OOF calibration. |
| **P1** | **Correlation sign / role-assignment** — QB↔opp-DST must be ≤0, QB↔WR1 >0, bring-back (QB+opp WR) >0. Sign inversion is a correctness flip; role keyed off stale depth chart attaches WR1 corr to wrong receiver. | `models/correlation.py` sign matrix; sim matrix indexed by raw name (dup-name collision). | Unit test asserting the sign matrix; key sim matrix on canonical IDs. |
| **P1** | **Sim rerank uses mean only** — no ownership/duplication penalty. This is **cash-game EV, not GPP EV**; over-selects chalk. (Confirmed design gap per pack.) | `export/sim_rerank.py` — `grep -rn "mean(\|sim_mean"`. | Rerank on ceiling quantile (P85–P90) − λ·ownership/dup penalty; keep mean as a cash mode. |
| **P1** | **`defense_multiplier` stub returns 1.0** — opponent matchup ignored entirely; misranks players vs strong/weak D. Design gap, but behaves like a bug and drifts from wiki if docs claim matchup-adjusted. | `models/stats.py` — `grep -rn "defense_multiplier\|# TODO"`. | Walk-forward DvP multiplier, clipped 0.85–1.15. **Must be walk-forward or it reintroduces leakage.** |
| **P1** | **FanDuel is 0.5 PPR**, not 1.0. If projections/scoring inherit DK-style full-PPR, volume-catch RBs are overvalued, TD-variance WRs undervalued. | `models/scoring.py` — confirm `receptions * 0.5`. | Verify half-PPR reception weight + FD DST points-allowed tiers. |
| **P1** | **DST projection is heuristic fallback** vs stat-first stack — mean may be fine, **variance/tail wrong** (DST scoring is bimodal; a return/def TD is a step change). Under-represents GPP-winning upside. | `models/stats.py`/`scoring.py` DST branch. | Right-skewed DST marginal + opp pressure/sack/turnover term; sim-distinct variance. |
| **P1** | **Empirical W-CORR vs prior** — thin per-pair samples (~17 gm/yr) make raw empirical noisy; no shrinkage → over/under-correlated stacks. | `correlation.py` empirical blend. | `ρ = w·ρ_emp + (1−w)·ρ_prior`, `w = n/(n+k)`. |
| **P1** | **Retractable/semi-open roofs + international venues** — binary dome/outdoor flag mishandles AT&T/NRG/State Farm/Lucas Oil (default closed in weather) and SoFi (fixed canopy, open sides — *not* a traditional dome). London/Munich/São Paulo missing → KeyError/default-dome. | `data/stadiums.py`, `is_weather_exposed()` in `weather.py`. | Three-state roof enum (dome/retractable/outdoor); retractable→not-exposed default; add intl rows. |
| **Note** | **Backtest measures projection accuracy, not contest ROI.** Defensible design (free nflverse PBP), but "backtest passed" ≠ "makes money" — no duplication/payout/leverage modeled. | Pack regime boundary. | Label metrics honestly; optional synthetic-field/payout layer from *own* ownership model (no paywalled data). |

---

### Ship recommendation

- **Live slate ready?** **N** — until join-coverage guard, independent `validate_lineup()`, and the walk-forward tripwire exist and pass.
- **Backtest trustworthy?** **N** — walk-forward leakage risk + confirmed wrong historical-weather endpoint can both inflate metrics. Run the shift-the-target and `week<W` vs `week<=W` ablation before trusting any MAE/Spearman.
- **Sim rerank safe?** **Partially** — safe for *cash* if the correlation matrix is PSD-repaired and indexed by canonical IDs; **not GPP-optimal** (mean-only, no leverage). Verify sign matrix and PSD repair first.

---

### Root cause

The highest-impact issue is the **leakage-and-silence coupling**: the pipeline's confidence comes from a backtest that is itself the most likely place for *silent* corruption. Walk-forward leakage (rolling/aggregation without strict `< W` cutoff or `.shift(1)`) inflates the metrics that authorize bankroll, while the confirmed-wrong Open-Meteo forecast endpoint silently nulls historical weather and breaks wind-tier calibration — and the join layer can drop salaried studs without raising. None of these crash; they all produce plausible-looking output. The fix posture is to convert each silent path into a loud assertion (no-future-rows guard, join-coverage gate, non-empty-hourly check, independent lineup validator) *before* re-running the backtest — only then are the metrics trustworthy enough to ship on. If I'm wrong and these guards already exist with passing tests, the verdict moves to WARN immediately; the probes resolve which world the repo is in.

---

### Ranked patch backlog

| P | Patch | Effort | Expected lift |
|---|-------|--------|---------------|
| P0 | Higham/eigen-clip **nearest-PSD repair** before copula factorization + logged Frobenius distance | ~4–20 ln | Eliminates crash + silent-wrong-dependence |
| P0 | **Post-join coverage assertion** — fail/WARN + log every dropped salaried-active player | ~15 ln | Stops silent stud-drop (highest single-patch leverage) |
| P0 | **Walk-forward tripwire** `assert_no_future_rows(features, asof_week)` | ~15 ln | Turns leakage into a crash; restores backtest trust |
| P0 | **Open-Meteo archive split** (date-conditional host) + non-empty-hourly assert | ~12 ln | Fixes confirmed historical-weather corruption |
| P0 | **Kickoff-hour UTC timestamp match** (no midnight/positional index) | ~8 ln | Correct wind/precip read |
| P0 | **`validate_lineup()` gate** independent of solver (slots, $60k, FLEX=RB/WR/TE, ≥2 games, no dup) | ~30 ln | Prevents illegal live submission |
| P0 | **Canonical name/team/DST normalizer** at every ingest boundary + `D→DST` map | ~50 ln | Root-cause feed for join guard |
| P0 | **RunManifest.write()** on success path + refuse-emit-if-unwritten | ~5 ln | Provenance; closes Phase-0 open item |
| P0 | **De-swallow fetch/join exceptions** + single completeness gate | ~25 ln | Closes remaining silent-failure surface |
| P1 | **Correlation sign unit test** (QB↔opp-DST ≤0, QB↔WR1 >0, bring-back >0) + canonical-ID sim index | ~20 ln | Catches catastrophic inversions |
| P1 | **Ownership walk-forward refit** + OOF calibration report | refactor | Backtest trust + safe live behavior |
| P1 | **GPP rerank objective** — P85–P90 quantile − λ·ownership/dup penalty (keep mean as cash mode) | ~15 ln | Research model → +EV GPP tool |
| P1 | Verify **FanDuel 0.5 PPR** reception weight | ~2 ln | Fixes systematic RB over / WR under-valuation |
| P1 | **Empirical↔prior correlation shrinkage** by sample size | ~6 ln | Stabilizes early-season sims |
| P1 | **`defense_multiplier`** walk-forward DvP (clip 0.85–1.15) or document no-op | ~30 ln | Recovers matchup edge (no leakage) |
| P1 | **Three-state roof enum** + retractable/international handling | ~20 ln | Calibration + intl-week robustness |
| P1 | **DST right-skewed marginal** + opp-pressure term | ~25 ln | Better GPP sim tails |

---

### Unique angle

Two things peers are likely to miss:

1. **Data-vintage integrity of nflverse itself.** Even with *perfect* `week < W` filtering, nflverse stats are sometimes **retroactively revised** (stat corrections, role re-grades). If the backtest reads today's *current* snapshot rather than the as-of-lock revision, you leak look-ahead that no week filter catches. For 2024–2025 slates, pin/snapshot the data vintage or you can't reproduce — or trust — a backtest.

2. **RNG seeding + Monte Carlo tail stability.** The whole rerank rests on sim quantiles, yet nobody asks whether the sim count gives *stable* P90/P95 estimates or whether runs are seeded. Unseeded sims make backtests non-reproducible and make tail-based rerank decisions noisy run-to-run; and a Gaussian copula understates joint extremes (shootouts) versus a t-copula — exactly the events that win GPPs. Add a seed + a tail-stability check (P90 variance across re-runs) before trusting ceiling-based reranking.

---

### Confidence

**Medium.** High on the bug-*class* priors and the two externally-confirmed items (Open-Meteo endpoint split; FanDuel 0.5 PPR). Lower on specific line-level confirmation, since the pack resolved to specs rather than the source tree — run the grep/probe set above to convert each P0 prior into a confirmed verdict or a downgrade.