# CeminiDFS v0.1.0 — End-to-End Engineering & Quantitative Audit

* **Project:** `CeminiDFS` (`v0.1.0`, Python 3.11+, MIT License)
* **Date:** 2026-10-13
* **Scope:** Full-stack audit across data ingestion, identity resolution, usage/volume/efficiency/DST modeling, Monte Carlo simulation reranking, schema contracts, `pydfs-lineup-optimizer` export, operator workflow, and legal exposure.
* **Release Verdict:** **DO-NOT-SHIP** (Until P0 Optimizer Injury/FPPG Gate, Defense EPA Sign Bug, Late-Swap Fallback, and Vegas TD Anchoring Are Fixed).

---

## 0. Prior Audit Claim Verification Matrix

| Prior Audit Claim | Audit Verdict | Code Location (`file:line`) | Root Cause / Verification Detail |
| --- | --- | --- | --- |
| **`player_id` is lost in `normalize` (mismatch against `SITE_KEYS`)** | **CONFIRMED (Modified)** | `src/ceminidfs/pipeline/engine.py:252-270`, `src/ceminidfs/export/normalize.py:269-277` | `SITE_KEYS` in `normalize.py` now includes `"fd_id"` and `"dk_id"`, so `fd_id` survives `normalize_csv` when present. However, `build_diy_projections` drops `fd_id` and re-merges onto `salary_rows` via string `join_key = normalize_join_key(name, team, pos)` (`engine.py:252`), losing identity whenever suffixes (`Jr.`, `III`), punctuation, or compound last names (`Amon-Ra St. Brown`) mismatch. |
| **Two different canonical schemas exist** | **CONFIRMED (3 Schemas)** | `src/ceminidfs/export/canonical.py:13-28`, `src/ceminidfs/export/normalize.py:32-43`, `src/ceminidfs/export/review_reports.py:95-107` | `canonical.py` writes `fd_id, fd_position, fd_salary, fd_projection`; `normalize.py` writes `Id, Position, Salary, FPPG`; `review_reports.py` only checks `_POS_KEYS = ("position", "pos", "roster position")` and `_SALARY_KEYS = ("salary",)`, silently reading empty strings when given a canonical CSV. |
| **Stages fail silently (bare `except` / swallowed exceptions)** | **CONFIRMED** | `src/ceminidfs/export/late_swap.py:322-329`, `src/ceminidfs/export/stack_rules.py:216-225`, `src/ceminidfs/data/weather.py:165-169` | `late_swap.py` catches solver `Exception`s and keeps the original un-swapped lineup containing inactive/excluded players. `stack_rules.py` catches `"not found"` on `--exclude` typos and skips exclusion. `weather.py` catches fetch errors and defaults wind to `None` (`1.0` multiplier). |
| **`optimize` without `normalize` produces fake lineups** | **CONFIRMED** | `src/ceminidfs/cli.py:478-493`, `src/ceminidfs/export/optimize.py:463-505, 678-693` | Standalone `ceminidfs optimize --csv` skips `_reject_salary_canonical` (`orchestrator/run.py:195`), loads FanDuel's raw season-average `FPPG`, and sets `pool.with_injured = True` (`optimize.py:688`), forcing `IR` and `OUT` stars into lineups. |
| **Sim rerank is mean-invariant** | **REFUTED (Mean-Invariant) / CONFIRMED (Mathematically Broken)** | `src/ceminidfs/export/sim_rerank.py:106`, `src/ceminidfs/models/simulate.py:55-104` | `score_lineup` ranks by the 85th percentile minus ownership penalty (`sim_rerank.py:106`), not the mean. However, `simulate_fd_points` uses an uncentered log-normal draw $\mu_i \exp(\sigma_i Z_i)$ without $-\frac{1}{2}\sigma_i^2$, inflating means by $\sqrt{1+\text{CV}_i^2}$ and perversely rewarding players flagged with `coherence_risk_flag` / `workload_risk_flag`. |
| **Weather timestamps are misaligned to timezone** | **PARTIALLY FIXED / CONFIRMED IN `research-export`** | `src/ceminidfs/data/weather.py:194-224`, `src/ceminidfs/export/research_export.py:173-191, 341` | `data/weather.py` converts `gametime` (`America/New_York`) to UTC. However, `research_export.py:173-191` tries to parse kickoff times from FanDuel's `Game` string (`"AWAY@HOME"`), which has no timestamp, causing `parse_kickoff` to return `None` and skip NWS weather for every outdoor game. |
| **Correlation model omits opponent and game** | **CONFIRMED** | `src/ceminidfs/models/simulate.py:36`, `src/ceminidfs/models/correlation.py:9-19, 91-116` | Default `method="team_shock"` (`simulate.py:36`) draws independent shocks per team (`0.0` game/opponent correlation). In `copula` mode, `_pair_correlation` omits `("QB", "WR2")`, `("QB", "WR3")`, and opposing `("QB", "WR1")`/`("QB", "TE1")` bring-backs (`0.0`). |
| **`defense_multiplier` is a stub returning `1.0`** | **CONFIRMED (Via EPA Sign Bug)** | `src/ceminidfs/models/defense.py:27-28, 55, 79-91` | `build_defense_ratings` uses PBP `epa` when present (`defense.py:86`) and checks `if league_avg <= 0: continue` (`defense.py:28`). Because league-wide NFL rushing EPA is negative ($\approx -0.06$), `"rush"` is skipped 100% of the time and returns `1.0` for all RBs. |
| **Play-by-play week scoping is wrong** | **CONFIRMED (Week 2 Cliff & Role Gate)** | `src/ceminidfs/pipeline/engine.py:274-288`, `src/ceminidfs/data/fetch.py:148` | `_historical_pbp` strictly filters `week_num < week` (no future leakage), but drops `season - 1` as soon as `week == 2` (`if week <= 1`), leaving Week 2 projections with a 1-game sample for 80% of usage weights. |

---

## PART A — AUDIT THE PROJECT (RANKED FINDINGS)

### 1. Silent Failure Map

Ranked by how convincing the wrong output looks to the operator prior to manual lineup entry.

1. **[P0 | CONFIRMED] Standalone `ceminidfs optimize` Accepts Raw FanDuel Salary CSVs and Rosters `IR`/`OUT` Players at Season-Average `FPPG`** — `src/ceminidfs/cli.py:478-493`, `src/ceminidfs/export/optimize.py:463-505`, `src/ceminidfs/export/optimize.py:678-693`

* **Concrete Failure Scenario:** Operator runs `ceminidfs optimize --csv FanDuel-NFL-2026-10-13.csv --out lineups.csv` directly on a downloaded FanDuel salary file. While `run_pipeline` calls `_reject_salary_canonical` (`src/ceminidfs/orchestrator/run.py:195-202`), `_cmd_optimize` calls `_run_optimize` directly with no input guard. Because FanDuel's raw CSV already contains `Id, First Name, Last Name, Position, Team, Salary, FPPG, Game, Injury Indicator`, `pydfs-lineup-optimizer` ingests FanDuel's stale season-to-date `FPPG` as projections. Next, `keep_injury_tagged_players` (`src/ceminidfs/export/optimize.py:688`) sets `pool.with_injured = True`, which instructs `pydfs` to allow injured players (`IR`, `O`, `D`) into lineups.
* **Why Operator Won't Notice:** The solver outputs 150 legal lineups spending $59,400–$60,000 with normal-looking point totals (125–140 pts) and exits `0`. Furthermore, `questionable_exposure_rows` (`src/ceminidfs/export/lineup_report.py:130-152`) only checks for `"Q"` / `"QUESTIONABLE"`, so `IR` and `O` players do not even trigger a warning in `lineups.report.txt`.
* **Fix:** In `generate_lineups` (`src/ceminidfs/export/optimize.py:463`), verify normalized provenance (or reject raw FanDuel CSVs), and in `keep_injury_tagged_players` (`src/ceminidfs/export/optimize.py:678`), call `pool.remove_player(player)` for any player where `is_unavailable_status(injury)` is `True` before setting `pool.with_injured = True`.

2. **[P0 | CONFIRMED] `build_defense_ratings` Silently No-Ops on Rushing Because League-Average NFL Rush EPA Is Negative** — `src/ceminidfs/models/defense.py:24-34`, `src/ceminidfs/models/defense.py:79-91`

* **Concrete Failure Scenario:** `_play_values` (`src/ceminidfs/models/defense.py:86-87`) returns `frame["epa"]` whenever `"epa" in frame.columns` (which is always true on `nflverse` PBP parquets). `build_defense_ratings` (`src/ceminidfs/models/defense.py:27-28`) computes `league_avg = _league_rate(historical, side)` and executes `if league_avg <= 0: continue`. Because league-wide NFL rushing EPA per play is strictly negative ($\approx -0.05$ to $-0.08$), `league_avg <= 0` is always true for `side == "rush"`, skipping the entire loop. `defense_multiplier(opponent, "rush", ratings)` (`src/ceminidfs/models/defense.py:55`) then returns `1.0` for all 32 teams. Even when passing `league_avg > 0`, `alpha = 0.08` applied to EPA diffs ($\pm 0.15$) moves projections by only $\pm 1\%$.
* **Why Operator Won't Notice:** Projections complete with exit code `0`, and `defense_context_report.csv` prints `1.0000` (or `~0.99–1.01`) without any warning that rush defense ratings were skipped.
* **Fix:** Remove `if league_avg <= 0: continue` in `src/ceminidfs/models/defense.py:28` and calibrate `alpha` for additive EPA deviations ($\alpha \approx 0.60$) or compute yardage/TD multipliers against positive yardage averages.

3. **[P0 | CONFIRMED] `late_swap_lineups` Swallows Solver Exceptions and Silently Retains Original Lineups Containing Inactive/Excluded Players** — `src/ceminidfs/export/late_swap.py:312-338`, `src/ceminidfs/export/late_swap.py:216-286`

* **Concrete Failure Scenario:** A 4:25 PM ET player is ruled inactive after 1:00 PM ET lock. The operator runs `ceminidfs late-swap --lineups lineups.csv --players normalized_players.csv --lock-team KC --exclude "Inactive WR"`. When `optimizer.optimize(n=1)` raises `LineupOptimizerException` on a constrained lineup, `_optimize_existing_lineups` (`src/ceminidfs/export/late_swap.py:322-329`) catches `Exception`, logs a warning, appends the **original un-swapped lineup containing the excluded/inactive WR** (`results.append(original)`), skips `_assert_locks_and_excludes_hold`, writes the upload CSV, and exits `0`.
* **Why Operator Won't Notice:** The CLI prints the output path and exits `0`, handing the operator a FanDuel upload file containing a 0-point inactive player.
* **Fix:** Never fall back to `results.append(original)` when `original` contains an excluded or unavailable player; relax stack constraints and re-solve, or raise `RuntimeError` and exit non-zero.

4. **[P0 | CONFIRMED] `--exclude` Name Mismatch or Typo Logs a Warning and Leaves the Player Active in the Optimizer Pool** — `src/ceminidfs/export/stack_rules.py:216-225`, `src/ceminidfs/export/optimize.py:553`

* **Concrete Failure Scenario:** Operator runs `ceminidfs optimize ... --exclude "Hollywood Brown"` (listed as `"Marquise Brown"`) or mistypes a player name. `apply_locks_and_excludes` (`src/ceminidfs/export/stack_rules.py:219`) catches `ValueError("Player not found in pool...")`, prints `WARNING: exclude ... is already out of the pool; skip`, and omits the player from `resolved_excludes`. `_assert_locks_and_excludes_hold` (`src/ceminidfs/export/optimize.py:553`) only checks `resolved_excludes`, so the player is rostered while `lineups.report.txt` lists the raw `--exclude` string in the header as if it was applied.
* **Why Operator Won't Notice:** The `stderr` warning is buried above the 50-line stdout report, and `Excludes:` in the report header shows the player's name.
* **Fix:** Raise `ValueError` on any unresolved `--exclude` token unless `--allow-missing-exclude` is explicitly set.

5. **[P0 | CONFIRMED] Unmatched Salary Players Get Blank `fd_projection` in `project` and Default to `FPPG = "0"` in `normalize`** — `src/ceminidfs/pipeline/engine.py:59-64, 246-270`, `src/ceminidfs/export/normalize.py:274`

* **Concrete Failure Scenario:** A starter whose name/suffix/team fails to match `stats_by_key` in `merge_projections_into_canonical` (`src/ceminidfs/pipeline/engine.py:252`) is written with `fd_projection = ""`. `normalize_csv` (`src/ceminidfs/export/normalize.py:274`) executes `projection = pick(row, keys["projection"]) or "0"`, assigning `FPPG = 0` and exiting `0`.
* **Why Operator Won't Notice:** The player silently disappears from all candidate lineups without halting the build.
* **Fix:** Fail hard in `project_week` whenever any available player with `fd_salary >= 4500` has an empty or zero `fd_projection`.

6. **[P1 | CONFIRMED] `ceminidfs salary` Drops `salary_fppg` and Normalizes to All-Zero Projections** — `src/ceminidfs/data/salary.py:63-74`, `src/ceminidfs/export/canonical.py:13-62`

* **Concrete Failure Scenario:** `write_salary_canonical` (`src/ceminidfs/data/salary.py:63-74`) leaves `fd_projection` empty and drops `salary_fppg` because `salary_fppg` is not in `CANONICAL_FIELDS` or `OPTIONAL_PASS_THROUGH_FIELDS` (`src/ceminidfs/export/canonical.py:13-62`). Running `normalize` then `optimize` on that file assigns `FPPG = "0"` to the entire slate and generates 150 zero-point lineups that pass `validate_lineups_csv` (`src/ceminidfs/orchestrator/validate.py:22-96`).
* **Why Operator Won't Notice:** `validate_lineups_csv` checks slot counts, duplicates, and salary cap ($\le \$60,000$), but never checks whether projected points are $> 0$.
* **Fix:** Raise `ValueError` in `normalize_csv` and `validate_lineups_csv` if all projections are `0`.

7. **[P1 | CONFIRMED] `ceminidfs research-export env` Always Writes Blank Weather Because FanDuel's `Game` Column Has No Kickoff Timestamp** — `src/ceminidfs/export/research_export.py:173-191, 326-344`, `src/ceminidfs/data/salary.py:101`

* **Concrete Failure Scenario:** `write_environment_csv` calls `parse_kickoff(str(row.get("game", "")))` (`src/ceminidfs/export/research_export.py:327`). For FanDuel salary CSVs, `parse_salary_csv` (`src/ceminidfs/data/salary.py:101`) sets `game` to `"AWAY@HOME"` with no date or time. `parse_kickoff` returns `None` for every row, and `_weather_for_home` (`src/ceminidfs/export/research_export.py:341`) returns `""` for every outdoor stadium while exiting `0`.
* **Why Operator Won't Notice:** `environment.csv` is written with `dome` and `indoor` populated for dome teams and blank `weather` for outdoor teams, exiting `0`.
* **Fix:** Look up `gameday` and `gametime` from `schedules.parquet` by `(season, week, home_team)` in `write_environment_csv` when `parse_kickoff(game)` is `None`.

---

### 2. Identity Integrity

#### End-to-End Join Key Trace

| Hop | Stage / Transition | Join Key Used | Code Location (`file:line`) |
| --- | --- | --- | --- |
| **Hop 1** | `pbp.parquet` → `player_game_stats_from_pbp` | `groupby(["season", "week", "team", "game_id", "player_id", "player_name"])` (`player_id` = `gsis_id`, `player_name` = PBP `"J.Chase"`) | `src/ceminidfs/models/usage.py:212-215` |
| **Hop 2** | `salary_rows` → `_align_roster_to_pbp_ids` | 5-step string fallback: `normalize_join_key(name, team, pos)` → `_name_team_key` → `roster_by_name_team` → `roster_by_name` → `f"{parts[0][0]}.{parts[-1]}|{team}"` → `fd_id` | `src/ceminidfs/pipeline/engine.py:285-350` |
| **Hop 3** | `build_diy_projections` → `merge_projections_into_canonical` | `join_key = normalize_join_key(name, team, position)` (`"lower_name|lower_team|POS"`) with `.drop_duplicates(subset=["join_key"], keep="first")` | `src/ceminidfs/pipeline/engine.py:213-253` |
| **Hop 4** | `canonical_projections` → `normalize_csv` + `apply_participation_gate` | Preserves `fd_id` (`SITE_KEYS["fanduel"]["id"]`); role gate filters by team-agnostic PBP abbreviated name (`player_matches_participation`) | `src/ceminidfs/export/normalize.py:269-277`, `src/ceminidfs/export/pool_guards.py:293-321` |
| **Hop 5** | `normalized_players.csv` → `generate_lineups` / `write_merged_upload` | `pydfs` keys on `Id` + `First Name`/`Last Name`; `write_merged_upload` maps back via `_exposure_name_key(name)` → `Id` | `src/ceminidfs/export/optimize.py:86-143, 322-383` |

* **[P0 | CONFIRMED] Unstripped Suffixes/Punctuation in `_normalize_token` and Broken Compound Last Names in `_abbrev_last_name` Cause Identity Misses and Collisions** — `src/ceminidfs/pipeline/engine.py:285-395`, `src/ceminidfs/data/fetch.py:139-143`

* **Concrete Failure Scenario:**
  1. `fetch_week_datasets` (`src/ceminidfs/data/fetch.py:139-143`) never fetches `rosters_{season}.parquet`.
  2. `_normalize_token` (`src/ceminidfs/pipeline/engine.py:393-394`) only lowercases and collapses whitespace; it does **not** strip suffixes (`Jr.`, `Sr.`, `II`, `III`) or punctuation (`'`, `.`, `-`). Thus `"Kenneth Walker III"` vs `"Kenneth Walker"` or `"D.J. Moore"` vs `"DJ Moore"` misses `roster_by_name_team` and falls through to `_abbrev_last_name` (`src/ceminidfs/pipeline/engine.py:381-386`).
  3. `_abbrev_last_name` splits on spaces and takes `f"{parts[0][0]}.{parts[-1]}"`. For `"Amon-Ra St. Brown"`, `parts[-1]` is `"Brown"`, producing **`"A.Brown"`** instead of `nflverse`'s `"A.St. Brown"`! If a teammate matches `"A.Brown"`, Amon-Ra St. Brown collides onto that player's `gsis_id`. Similarly, when `nflverse` PBP uses 2-letter first-name prefixes (`"Ja.Williams"`, `"Mi.Wilson"`), 1-letter `_abbrev_last_name` either misses them or collides teammates sharing `FirstInitial.LastName` onto the last-seen `gsis_id` in `id_by_abbrev_team` (`src/ceminidfs/pipeline/engine.py:306`).
* **Fix:** Pre-cache `rosters_{season}.parquet` and `ff_playerids` during `fetch_week_datasets`, normalize names with suffix/punctuation stripping (`normalize_person_name`), and carry `fd_id` directly through `build_diy_projections` so Hop 3 joins on `fd_id` instead of string `join_key`.

* **[P1 | CONFIRMED] `player_game_stats_from_pbp` Can Split One Player Into Multiple Game Rows** — `src/ceminidfs/models/usage.py:212-215`

* **Concrete Failure Scenario:** `player_game_stats_from_pbp` groups by `["season", "week", "team", "game_id", "player_id", "player_name"]`. If `rusher_player_name` and `receiver_player_name` differ in formatting on two plays for the same `player_id` (`gsis_id`), the player splits into two rows for the same game, corrupting `games_played` and per-game averages.
* **Fix:** Group by `["season", "week", "team", "game_id", "player_id"]` and aggregate `player_name=("player_name", "last")`.

* **[P1 | CONFIRMED] Role Gate (`apply_participation_gate`) Deletes Returning Starters and Matches Initials Across All 32 Teams Without Team Scoping** — `src/ceminidfs/export/pool_guards.py:293-321, 400-449`, `src/ceminidfs/orchestrator/run.py:216-243`

* **Concrete Failure Scenario:** `names_with_participation` (`src/ceminidfs/export/pool_guards.py:400-420`) builds a team-agnostic `set[str]` of PBP abbreviated names (`"J.Smith"`, `"B.Robinson"`) with $\ge 1$ touch in weeks `1..week-1`.
  1. Any starter returning from IR/suspension/injury for his first game of the season in Week 2+ has `0` prior-week touches and is **deleted from `normalized_players.csv`**.
  2. Because `known` is not scoped by `team`, any zero-touch backup whose `FirstInitial.LastName` matches a player on *any other NFL team* falsely passes the gate.
* **Fix:** Key participation by `(gsis_id)` or `(abbrev_name, team)`, include prior-season touches through Week 4, and exempt players with `Salary >= $4,800` or confirmed starter status.

---

### 3. Projection Model Quality

* **[P0 | CONFIRMED] Touchdown Projections Ignore Vegas Implied Team Totals (`implied_total`)** — `src/ceminidfs/models/stats.py:100-143`, `src/ceminidfs/models/volume.py:92-103`, `src/ceminidfs/models/usage.py:478-515`

* **Concrete Failure Scenario:** Vegas `game_total` only shifts `projected_plays` by `0.08 * (total - 44.8)` (`models/volume.py:98`, i.e. +0.8 plays for a +10 pt total), and `implied_total` only nudges the starting QB's pass attempts by `+1.4%` per point above `22.0` (`models/usage.py:479-483`). In `models/stats.py:130-137`, `pass_td`, `rush_td`, and `rec_td` are computed purely from historical per-attempt/per-carry/per-target rates with **zero scaling to Vegas `implied_total`**. A team implied by Vegas for 31.0 points and a team implied for 14.5 points receive nearly identical RB, WR, and TE touchdown projections.
* **Fix:** Anchor team skill touchdowns to Vegas implied team total ($\text{Expected Team TDs} \approx \max(0.8, (\text{ITT} - 3.0) / 6.5)$) and scale individual player TD projections to reconcile with team implied TDs.

* **[P0 | CONFIRMED] Week 2 Single-Game Sample Cliff, Missing Vacancy Redistribution, and >125% Team Target Share Sums** — `src/ceminidfs/pipeline/engine.py:274-288`, `src/ceminidfs/models/usage.py:303-336, 453-515, 546-556, 716-719`

* **Concrete Failure Scenario:**
  1. **Week 2 Cliff (`pipeline/engine.py:280`):** `_historical_pbp` includes `season - 1` only when `week <= 1`. In Week 2, all prior-season data is dropped, so 80% of usage weight (`0.5 * L3 + 0.3 * Season`) comes from a 1-game Week 1 sample.
  2. **Missing Vacancy Redistribution (`models/usage.py:546-556, 716-719`):** `rolling_shares` is computed *before* filtering out `excluded_ids` (injured/out players). When an RB1 (65% carry share) or WR1 (30% target share) is ruled `Out`, their share is simply dropped; remaining WRs/TEs are never normalized, and remaining RBs are only normalized `if carry_total > 1.0` (`models/usage.py:717`).
  3. **Target Share Inflation (`models/usage.py:463-475`):** Every depth WR5/WR6/TE3 on the FanDuel CSV with 0 historical targets receives `0.2 * 0.18 = 3.6%` target share, pushing team target share sums to `125%–140%` of team pass attempts.
* **Fix:** Retain decaying `season - 1` PBP through Week 4; filter to active week players before computing shares; normalize active team `target_share` and `carry_share` to `1.0`.

* **[P1 | CONFIRMED] `neutral_seconds_per_play` Compares ~26s PBP Row Diffs Against `LEAGUE_SEC_PER_PLAY = 36.2`, Inflating Volume by +8.5 Plays/Team** — `src/ceminidfs/models/volume.py:13, 42-67, 92-103`

* **Concrete Failure Scenario:** `neutral_seconds_per_play` (`src/ceminidfs/models/volume.py:55-64`) computes `game_seconds_remaining.diff(-1)` across all consecutive PBP rows (~26s mean) and subtracts it from `LEAGUE_SEC_PER_PLAY = 36.2` (`src/ceminidfs/models/volume.py:97`), adding `0.85 * (36.2 - 26.2) = +8.5` plays to every team with PBP data.
* **Fix:** Compute clock diffs across scrimmage plays only and set `LEAGUE_SEC_PER_PLAY` to the empirical league mean (~26.5s).

* **[P1 | CONFIRMED] Wind Haircut Cuts QB `pass_yds` by 10% While Leaving WR/TE `rec_yds` Unchanged** — `src/ceminidfs/models/stats.py:194-213`

* **Concrete Failure Scenario:** `apply_wind_passing_haircut` multiplies `output["pass_yds"]` by `0.90` in $\ge 15$ mph outdoor wind (`src/ceminidfs/models/stats.py:210-212`) but leaves `output["rec_yds"]` untouched.
* **Fix:** Multiply both `pass_yds` and `rec_yds` by the wind multiplier.

* **[P1 | CONFIRMED] Backtest Ground-Truth Actuals Omit Fumbles Lost and Credit Kick/Punt Return TDs to the Kicking Team's DST** — `src/ceminidfs/pipeline/backtest.py:141, 282-343`, `src/ceminidfs/models/dst.py:219, 259-269`

* **Concrete Failure Scenario:**
  1. `actual_week_fantasy_points` (`src/ceminidfs/pipeline/backtest.py:141`) hardcodes `fumbles_lost = 0.0`.
  2. `_defensive_events` (`src/ceminidfs/models/dst.py:219, 259-269`) filters `pbp["defteam"] == team` and counts `return_touchdown == 1` without checking `td_team == team`. On punts and kickoffs in `nflverse` PBP, `defteam` is the kicking team, so allowing a kick/punt return TD credits the kicking team's DST with `+6.0` points.
* **Fix:** Sum `fumble_lost` by `fumbled_1_player_id` in `backtest.py`, and filter `frame["td_team"] == team` in `models/dst.py:259`.

---

### 4. Rerank Validity

* **[P0 | CONFIRMED] Uncentered Log-Normal Simulation Inflates Means, Rewards High-Risk Players with Higher 85th Percentiles, and Omits `QB-WR2` & Bring-Back Correlations** — `src/ceminidfs/models/simulate.py:36, 49-105`, `src/ceminidfs/models/coherence_risk.py:345-369`, `src/ceminidfs/models/correlation.py:9-19, 91-116`, `src/ceminidfs/export/sim_rerank.py:79-121`

* **Mathematical Verification:**
  1. **Uncentered Log-Normal Draw (`src/ceminidfs/models/simulate.py:55-67, 91-104`):** `simulate_fd_points` sets `medians = projections` ($\mu_i$) and draws:
     $$X_i = \mu_i \exp(\sigma_i Z_i), \quad \sigma_i = \sqrt{\ln(1 + \text{CV}_i^2)}, \quad Z_i \sim \mathcal{N}(0, 1)$$
     Because the $-\frac{1}{2}\sigma_i^2$ correction is omitted, the simulated expectation is inflated by:
     $$\mathbb{E}[X_i] = \mu_i \exp\left(\frac{1}{2}\sigma_i^2\right) = \mu_i \sqrt{1 + \text{CV}_i^2} > \mu_i$$
     inflating high-CV positions (TE $\text{CV}=0.58 \implies +15.6\%$; WR $\text{CV}=0.52 \implies +12.7\%$) relative to QBs ($\text{CV}=0.35 \implies +5.9\%$).
  2. **Perverse Risk Reward (`src/ceminidfs/models/coherence_risk.py:345-369`):** When a player is flagged with `coherence_risk_flag` (high O-line pass-protection stress) or `workload_risk_flag` (fatigue), `coherence_variance_multiplier` multiplies their $\text{CV}_i$ by `1.25` or `1.15`. Because `score_lineup` (`src/ceminidfs/export/sim_rerank.py:106`) ranks lineups by the 85th percentile $P_{85} = \mu_i \exp(z_{0.85}\sigma_i)$, increasing $\sigma_i$ **increases** a 12-point WR's 85th percentile from `19.58` to `21.77` (+11.2%), causing `sim_rerank` to actively prefer stressed/overworked players!
  3. **Missing Correlations (`src/ceminidfs/models/simulate.py:36`, `src/ceminidfs/models/correlation.py:9-19, 91-116`):** Default `method="team_shock"` uses independent team shocks (`0.0` opposing-team correlation), and `copula` mode omits `("QB", "WR2")`, `("QB", "WR3")`, and opposing `("QB", "WR1")`/`("QB", "TE1")` bring-backs (`0.0`).
* **Recommendation:** **Disable/remove `sim_rerank` from production runs** until `simulate_fd_points` centers the log-normal draw ($\exp(\sigma_i Z_i - \frac{1}{2}\sigma_i^2)$), `coherence_risk` shifts downside tail rather than boosting upper quantiles, and `correlation.py` includes `QB-WR2/3` and opposing bring-back correlations.

---

### 5. Stub Math

| Placeholder / Stub | Location (`file:line`) | Direction of Bias | Most Distorted Players |
| --- | --- | --- | --- |
| **`defense_multiplier = 1.0`** when `league_avg <= 0` on PBP `epa` | `src/ceminidfs/models/defense.py:27-28, 55` | **Upward** vs. top defenses; **Downward** vs. bottom defenses | All RBs (100% of rush defense multipliers equal `1.0`) and all TD projections. |
| **Static DST Priors** (`del team, opponent`; `sacks=2.4, int=0.85, fr=0.55, td=0.12`) | `src/ceminidfs/models/dst.py:11-39` | **Downward** on elite pass-rush DSTs; **Upward** on weak DSTs | High-salary elite DSTs facing sack/turnover-prone QBs (underprojected by 2–4 FD pts). |
| **Step-Function `fd_dst_points_allowed(implied)`** | `src/ceminidfs/models/scoring.py:92-108`, `src/ceminidfs/models/dst.py:29` | **Downward** on DSTs with opponent ITT in `20.1–26.9` (`0.0` PA pts) | DSTs at `ITT = 20.5` (`0.0` PA pts) vs. `ITT = 20.0` (`+1.0` PA pt cliff). |
| **`LEAGUE_SEC_PER_PLAY = 36.2`** vs. ~26s PBP row diff | `src/ceminidfs/models/volume.py:13, 42-67, 92-103` | **Upward** (+8.5 plays / +13% volume) | All teams with PBP history get +8.5 plays; teams missing PBP default to `36.2` (-8.5 plays). |
| **Pocket QB Scramble Floor** (`0.08 * dropbacks`) | `src/ceminidfs/models/usage.py:495-503` | **Upward** (+1.5 to +2.2 FD pts) | Immobile pocket QBs (Goff, Stafford, Cousins) floored at ~3.0 carries/game. |
| **Zero Goal-Line Share Coefficients** (`0.0`) | `src/ceminidfs/models/coherence_settings.py:92-93` | **Downward** on goal-line RBs; **Upward** on between-the-20s RBs | Goal-line backs (Henry, Montgomery, Hurts) whose TD equity comes from inside-the-5 usage. |
| **Zero `fumbles_lost = 0.0`** | `src/ceminidfs/models/stats.py:29, 138` | **Upward** (+0.3 to +0.6 FD pts) | High-volume QBs and workhorse RBs (never penalized `-2.0` pts per fumble lost). |
| **Zero NGS & Rookie Priors** (`0.0`) | `src/ceminidfs/data/ngs_eval.py:26-27`, `src/ceminidfs/models/rookie_prior.py:32-37` | **Downward** on early-season rookies | Week 1–3 rookie starters before NFL PBP sample accumulates. |

---

### 6. Schema Duality

* **[P0 | CONFIRMED] Three Divergent Schemas (`canonical.py` vs. `normalize.py` vs. `engine.py`) Produce Silent Empty Reports in `review_reports.py`** — `src/ceminidfs/export/canonical.py:13-28`, `src/ceminidfs/export/normalize.py:32-43`, `src/ceminidfs/export/review_reports.py:95-107, 409-435`

* **Schema Divergence:**
  1. **Canonical CSV (`src/ceminidfs/export/canonical.py:13-28`, written by `project` and `salary`):** `fd_id, fd_position, fd_salary, fd_projection, player_name, team, opp, game, injury_status`.
  2. **Normalized CSV (`src/ceminidfs/export/normalize.py:32-43`, written by `normalize`):** `Id, First Name, Last Name, Position, Team, Salary, FPPG, Game, Injury Indicator`.
  3. **Engine Base Parquet (`src/ceminidfs/pipeline/engine.py:212-220`):** `player_id` (`gsis_id`), `player_name, position, fd_projection, opponent, opp, game`.
* **Realistic Input Producing a Silent Mismatch (No Error):**
  When the operator runs `ceminidfs review --lineups lineups.csv --players canonical_projections_2026_w5.csv --flag-wr-triples --dart-ceiling-report --flag-qb-starter --flag-stack-concentration --defense-context-report`:
  `load_player_index` (`src/ceminidfs/export/review_reports.py:95-107, 409-435`) checks `_POS_KEYS = ("position", "pos", "roster position")`, `_ID_KEYS = ("id", "player id", "player_id")`, `_SALARY_KEYS = ("salary",)`, and `_PROJ_KEYS = ("fppg", "projection", "avgpointspergame", "avg points per game")`. Because none of `fd_position`, `fd_id`, `fd_salary`, or `fd_projection` are in those tuples, every player loads with `position = ""`, `player_id = ""`, `salary = ""`, and `projection = ""`, producing **0 flagged rows** across `qb_starter_report.csv`, `stack_concentration_report.csv`, `dart_ceiling_rank.csv`, and `defense_context_report.csv` while exiting `0`.
* **Fix:** Add `fd_position`, `dk_position`, `fd_id`, `dk_id`, `fd_salary`, `dk_salary`, `fd_projection`, and `dk_projection` to the key tuples in `src/ceminidfs/export/review_reports.py:95-107`, and assert non-empty `position` and `salary` in `load_player_index`.

---

### 7. Operator Workflow

1. **12-Hour Parquet Cache TTL Traps Sunday 11:30 AM ET Inactives (`src/ceminidfs/data/fetch.py:21, 56-60`):**
   `CACHE_TTL_SECONDS = 12 * 60 * 60`. If the operator runs `fetch` at 8:00 AM ET on Sunday and re-runs `fetch` or `run` at 11:45 AM ET after official NFL inactives drop without passing `--force`, `_fetch_cached` silently reuses the 8:00 AM `injuries_2026.parquet` cache.

2. **Suboptimal `FLEX` Slot Assignment Locks Late-Swap Optionality (`src/ceminidfs/export/optimize.py:92-106`):**
   In `_lineup_row` (`src/ceminidfs/export/optimize.py:92-106`), the 3rd RB, 4th WR, or 2nd TE is placed into `FLEX` in whatever order `pydfs` returns them, rather than sorting by latest kickoff time. Putting a 1:00 PM ET player in `FLEX` and a 4:25 PM ET player in `RB1`/`WR1` locks the `FLEX` slot at 1:00 PM ET, preventing a cross-position late swap at 4:00 PM ET.

3. **Manual Entry Friction on `lineups.report.txt` (`src/ceminidfs/export/lineup_report.py:195-219`):**
   Because the operator enters lineups by hand on FanDuel, `format_lineup_report` printing only the first 8 lineups (`preview: int = 8`) as bare comma-separated names without `$Salary`, `Team`, or `Kickoff` forces manual cross-referencing across CSVs during pre-lock entry.

---

### 8. Legal Exposure

| Unlicensed Scraper / Risk Surface | Code Location (`file:line`) | Exposure Type | Least-Risk Replacement & License Position |
| --- | --- | --- | --- |
| **Underdog Live Draft Board DOM Scraper** | `src/ceminidfs/bbm/board_parse.py:1-370`, `src/ceminidfs/bbm/api_server.py:239-330`, `ROADMAP.md:24` | Violates Underdog Fantasy ToS (automated DOM extraction / live draft overlay); risks account ban and fund forfeiture. | **Underdog Native CSV Exports** (ADP & Exposure CSV downloads, already parsed by `bbm/reconcile.py` and `bbm/normalize_adp.py`) + manual CLI `p`/`t` commands (Permitted User Export). |
| **ESPN Authenticated Cookie Scraper (`espn_api`) & Yahoo Scraper** | `src/ceminidfs/data/espn.py:28-59`, `ROADMAP.md:24` | Uses private `espn_s2`/`swid` session cookies (`espn.py:31-45`) and unlicensed Yahoo scraping. | **`nflreadpy` (`load_injuries`, `load_rosters_weekly`)** (CC-BY-4.0 / MIT) + **Sleeper Public API** (`src/ceminidfs/data/sleeper.py`, documented public read-only API). |
| **Open-Meteo Free Tier Endpoint** | `src/ceminidfs/data/weather.py:22-23` | `api.open-meteo.com` free tier is CC-BY-4.0 **Non-Commercial only**. | **US National Weather Service API (`api.weather.gov`)** (already implemented in `src/ceminidfs/export/research_export.py:345`; **US Public Domain**, unrestricted commercial & personal use). |

---

## PART B — RANKED IMPROVEMENTS & REBUILD PLAN

### Ranked Improvements (By Impact on Lineup Quality & Safety)

1. **[Accuracy & Safety — P0] Fix `build_defense_ratings` EPA Sign Bug & Apply Defense Multipliers to TDs**
   * **Target:** `src/ceminidfs/models/defense.py:24-34, 79-91`, `src/ceminidfs/models/stats.py:130-137`.
   * **Change:** Remove `if league_avg <= 0: continue` in `defense.py:28`, compute additive EPA multipliers `1.0 + alpha * (team_rate - league_avg)` with $\alpha = 0.60$, and apply `pass_mult`/`rush_mult` to `pass_td`, `rec_td`, and `rush_td` in `stats.py`.
   * **Effort:** 2 hours (~30 LoC) | **Expected Gain:** Restores rush defense adjustments across all 32 teams (~0.8–1.5 FD pts accuracy gain on RB/QB matchup extremes).

2. **[Accuracy — P0] Anchor Team Touchdowns to Vegas Implied Team Totals (`implied_total`)**
   * **Target:** `src/ceminidfs/models/stats.py:100-143`, `src/ceminidfs/models/usage.py:453-515`.
   * **Change:** Pass `implied_total` from `volume_df` into `build_week_stats`, compute $\text{TD}_{\text{implied}} = \max(0.8, (\text{implied\_total} - 3.0) / 6.5)$, and scale team skill TDs (`rush_td + rec_td`) and `pass_td` toward $\text{TD}_{\text{implied}}$.
   * **Effort:** 0.5 days (~60 LoC) | **Expected Gain:** Aligns player scoring with Vegas team totals across high-total shootouts and low-total slogs.

3. **[Accuracy — P0] Normalize Active-Roster Target/Carry Shares (Vacancy Redistribution) & Keep Prior-Season PBP Through Week 4**
   * **Target:** `src/ceminidfs/models/usage.py:453-588, 716-719`, `src/ceminidfs/pipeline/engine.py:274-288`, `src/ceminidfs/data/fetch.py:148`.
   * **Change:** Extend `season - 1` PBP inclusion from `week <= 1` to `week <= 4` with decaying weight; filter out `excluded_ids` (`Out`/`IR`/`Doubtful`) *before* computing `rolling_shares`; normalize active team `target_share` and `carry_share` to sum to `1.0`.
   * **Effort:** 1 day (~120 LoC) | **Expected Gain:** +3 to +6 FD pts accuracy on promoted backup RBs and WR2/3s stepping into vacated volume; eliminates 125–140% team target-share inflation.

4. **[Safety — P0] Enforce Hard Pre-Solve Pool Gates in `optimize.py`, `late_swap.py`, and `review_reports.py`**
   * **Target:** `src/ceminidfs/export/optimize.py:463-505, 678-693`, `src/ceminidfs/export/late_swap.py:322-329`, `src/ceminidfs/export/stack_rules.py:216-225`, `src/ceminidfs/export/review_reports.py:95-107`.
   * **Change:**
     1. In `keep_injury_tagged_players` (`optimize.py:678`), remove all players matching `is_unavailable_status` before setting `pool.with_injured = True`, and reject unnormalized salary CSVs.
     2. In `stack_rules.py:219`, raise `ValueError` on unresolved `--exclude` names.
     3. In `late_swap.py:322`, never fall back to `original` when `original` contains an excluded/inactive player.
     4. In `review_reports.py:95-107`, add `fd_position`, `fd_id`, `fd_salary`, and `fd_projection` to lookup keys.
   * **Effort:** 0.5 days (~90 LoC) | **Expected Gain:** Eliminates 100% of silent `IR`/`OUT` rostering, missed `--exclude` typos, and empty review reports.

5. **[Safety & Workflow — P1] Auto-Place Latest-Kickoff Player in `FLEX` & Generate Full Operator Hand-Entry Cards**
   * **Target:** `src/ceminidfs/export/optimize.py:92-122`, `src/ceminidfs/export/lineup_report.py:155-248`.
   * **Change:** Sort the 3 RBs / 4 WRs / 2 TEs in `_lineup_row` by scheduled kickoff time so the latest-kickoff player occupies `FLEX`, and print all lineups with `[Slot | Player | Team | Kickoff | $Salary | Cap Left]` for manual FanDuel entry.
   * **Effort:** 0.5 days (~80 LoC) | **Expected Gain:** Preserves late-swap optionality on every multi-wave lineup and eliminates manual entry transcription errors.

6. **[Accuracy — P1] Center Log-Normal Draws & Add `QB-WR2/3` and Opposing Bring-Back Correlations**
   * **Target:** `src/ceminidfs/models/simulate.py:55-105`, `src/ceminidfs/models/correlation.py:9-19, 91-116`, `src/ceminidfs/models/coherence_risk.py:345-369`.
   * **Change:** Subtract `0.5 * (sigma[:, None] ** 2)` inside `np.exp(...)` in `simulate.py:66, 103`; apply a downside mean penalty instead of a variance boost on `coherence_risk_flag`; add `("QB", "WR2"): 0.32`, `("QB", "WR3"): 0.20`, and opposing bring-back correlations (`("QB", "OPP_WR1"): 0.18`, `("RB1", "OPP_DEF"): -0.25`) in `correlation.py`.
   * **Effort:** 0.5 days (~60 LoC) | **Expected Gain:** Removes variance-driven mean inflation and perverse risk-flag rewards in `sim_rerank`.

7. **[Accuracy — P1] Wire Opponent Sack/Turnover Rates into `dst.py` and Fix Return-TD Attribution**
   * **Target:** `src/ceminidfs/models/dst.py:19-48, 259-269`, `src/ceminidfs/export/review_gates.py:193-233`.
   * **Change:** Replace `del team, opponent` in `project_dst_fantasy_points` (`dst.py:25`) with team sack/takeaway rates × opponent `sack_pct`/`to_pct` (`review_gates.py:193`), smooth `fd_dst_points_allowed` across a score distribution, and require `td_team == team` in `_sum_def_touchdowns` (`dst.py:259`).
   * **Effort:** 0.5 days (~75 LoC) | **Expected Gain:** Differentiates elite pass-rush DSTs against sack-prone QBs and fixes backtest DST scoring.

8. **[Safety & Speed — P1] Shorten Game-Day Cache TTL for `injuries.parquet` and Pre-Cache `rosters_{season}.parquet`**
   * **Target:** `src/ceminidfs/data/fetch.py:21, 56-60, 139-143`, `src/ceminidfs/pipeline/engine.py:285-350`.
   * **Change:** Reduce `CACHE_TTL_SECONDS` for `injuries` from 12 hours to 15 minutes on game days, add `rosters` to `fetch_week_datasets`, and carry `fd_id` directly through `build_diy_projections`.
   * **Effort:** 2 hours (~45 LoC) | **Expected Gain:** Prevents stale 8:00 AM caches from hiding 11:30 AM ET inactives and eliminates string-join identity misses.

---

### Deletions & Simplifications Checklist

* **Disable/Delete `sim_rerank` by default (`src/ceminidfs/export/sim_rerank.py`, `config/nfl_dfs_gpp.yaml`)** until log-normal centering and correlation matrix fixes are verified.
* **Delete `src/ceminidfs/bbm/board_parse.py` (370 lines)** and decouple `src/ceminidfs/bbm/` and `src/ceminidfs/redraft/` into separate offseason packages so the weekly FanDuel DFS repo has zero unlicensed DOM scraping code.
* **Remove or archive dead zero-coefficient and hardcoded postmortem modules:** `src/ceminidfs/data/ngs_eval.py`, `src/ceminidfs/models/rookie_prior.py`, `src/ceminidfs/pipeline/late_swap_oracle.py` (hardcoded to `SEASON = 2026, WEEK = 3` at lines 38–39), and `src/ceminidfs/pipeline/late_swap_replay.py`.

---

### Single Highest-Impact Change Before Next Slate Lock

In `src/ceminidfs/export/optimize.py` (`generate_lineups` at line 463 and `keep_injury_tagged_players` at line 678), enforce a **mandatory pre-solve pool gate** that:

1. Removes every player matching `is_unavailable_status` (`O`, `OUT`, `IR`, `D`, `DOUBTFUL`, `SUSPENDED`, `INACTIVE`) *before* setting `pool.with_injured = True`;
2. Rejects any CSV that did not pass through `normalize_csv` or contains zero/blank starter projections; and
3. Raises a hard error on any unmatched `--exclude` name (`src/ceminidfs/export/stack_rules.py:219`) or un-swapped excluded player in `late_swap` (`src/ceminidfs/export/late_swap.py:322`).
