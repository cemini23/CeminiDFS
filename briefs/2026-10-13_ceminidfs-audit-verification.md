# CeminiDFS audit — independent verification

* **Date:** 2026-10-13
* **Audit verified:** `briefs/2026-10-13_ceminidfs-end-to-end-audit.md`
* **Verdict on the audit itself:** Directionally sound, but it overstates several findings, misattributes at least one file, asserts one file that does not exist, and contains one claim that is backwards.

---

## How this was verified

1. **Adversarial code review** by four independent reviewers. Each was told to try to falsify, and to return CONFIRMED / PARTIALLY CONFIRMED / REFUTED / UNVERIFIABLE with quoted code. Line numbers in the audit drift badly, so every claim was located by content.
2. **Empirical measurement** against `artifacts/cache` (2026 season, weeks 1-5) and the Week 5 run output in `runs/2026_week_5/`.

Line-number drift is severe and systematic. Examples: the usage groupby is `usage.py:263-266`, not `212-215`. The scramble floor is `usage.py:678-688`, not `495-503`. `late_swap` fallback is `379-388`, not `322-329`. Treat every audit reference as a hint only.

---

## Confirmed defects, ranked by impact

### 1. `LEAGUE_SEC_PER_PLAY` is wrong — every team gets ~8 extra plays

`models/volume.py` sets `LEAGUE_SEC_PER_PLAY = 36.2`. Measured on the cached 2026 season:

| Measure | Value |
|---|---|
| Constant | 36.2 s/play |
| Actual PBP clock diff | 23.8 s mean, 26.0 s median |
| Real team pace | 26.84 s/play |
| Observed offensive plays per team-game | **61.98** |
| `projected_plays` at real pace | **69.96** |
| `projected_plays` with constant corrected | **62.00** |

The intercept (62.0) is calibrated correctly; the constant is not. Volume is inflated about **8 plays, or 13%, per team**, which propagates into pass attempts, carries, and targets.

Root cause is narrower than "row diffs": `_neutral_script` applies no `play_type` filter, so kickoffs (2927), punts (2042), extra points (1330), field goals (1140) and no-plays (4723) all feed the clock difference. Fix = filter to scrimmage plays and reset the constant to the empirical mean.

### 2. No vacancy redistribution for unavailable players

`rolling_shares` runs at `usage.py:757`; the OUT-player filter runs *after*, at 759-764. Team shares are fractions of the team total, so an excluded player's share is dropped with no reallocation. Nothing renormalizes WR/TE shares. RBs recover partially through committee priors (0.35 / 0.12 / 0.04), so the audit is slightly harsh on RBs specifically.

### 3. `fumbles_lost` is always zero

`usage.PlayerUsageProjection` has no `fumbles_lost` field, and `stats.py` defaults it to 0.0. Measured: **0 of 595** players in the Week 5 output carry a nonzero value. `scoring.py` subtracts `fumbles_lost * 2.0`, so the penalty is never applied.

### 4. Wind haircut is one-sided

`apply_wind_passing_haircut` trims `pass_yds` only, by its own docstring. Measured: QB `pass_yds` 280 → 252 (-10%); the same team's WR `rec_yds` 85 → **85** (unchanged).

### 5. Goal-line adjustment is dead code

`coherence_settings.py:104-105` defaults `carry_share_coefficient` and `target_share_coefficient` to 0.0. `coherence_risk.py:461` guards on truthiness, so the block never runs. `config/nfl_dfs.yaml` has no `goal_line` block, so the defaults stand. The adjustment is unreachable.

### 6. NGS and rookie priors are no-ops

`data/ngs_eval.py` defaults both coefficients to 0.0 and its docstring calls itself "intentionally a no-op". `models/rookie_prior.py` is the same. No config override exists.

### 7. Identity: abbreviation collisions are real

Measured directly against `engine._abbrev_last_name`:

| Name | Produced | nflverse form |
|---|---|---|
| Amon-Ra St. Brown | `A.Brown` | `A.St. Brown` |
| A.J. Brown | `A.Brown` | `A.J. Brown` |
| Michael Wilson | `M.Wilson` | `Mi.Wilson` |
| Mitchell Wilson | `M.Wilson` | `Mi.Wilson` |

**`A.Brown` maps to two different players.** The repo already encodes the correct forms — `tests/test_w04_p0.py:310` lists `{"a.jeanty", "j.chase", "k.walker", "mi.wilson", "a.st. brown"}` — and `pool_guards.py` handles the two-letter prefix correctly. `engine.py` does not.

Also confirmed: `_normalize_token` strips neither suffixes nor punctuation (`kenneth walker iii`, `d.j. moore`).

### 8. `fetch` never pre-warms rosters

`data/fetch.py:162-166` fetches schedules, pbp, and injuries only. Rosters are cached on demand by `data/rosters.py`. The cache is warm today, so the risk is a cold run.

### 9. `salary` writes a projection-less canonical file

`data/salary.py:113` writes `"fd_projection": ""`, and `salary_fppg` is in neither `CANONICAL_FIELDS` nor `OPTIONAL_PASS_THROUGH_FIELDS`, so it is dropped. `normalize` then applies `or "0"`, giving the whole slate FPPG 0. `validate_lineups_csv` checks slots, duplicates, and cap only — never that points exceed zero.

### 10. `research-export env` writes blank weather

Real salary files carry `Game = "NO@DET"` with no date or clock, so `parse_kickoff` returns `None` and `_weather_for_home` returns blank for every outdoor venue. Exits 0.

### 11. Lower-impact confirmed items

* **12-hour cache TTL** reuses morning injury data past the inactives deadline. Not fully silent — it prints a warning.
* **FLEX assignment** ignores kickoff time; no game time reaches the optimizer.
* **`lineups.report.txt`** omits Team and Kickoff from the hand-entry view.

---

## Refuted claims

### DST return-TD attribution is correct, not inverted

The audit says kick/punt return TDs are credited to the *kicking* team. Measured on all 9 return touchdowns in the cached 2026 season: **`defteam == td_team` in 9 of 9.** One is a punt (TB punted, MIN returned it; `defteam` = MIN = `td_team`). `defteam` is the *returning* team on kicks, so the existing filter credits the correct team. **No bug.**

### `review` can no longer load a canonical CSV empty

Fixed this session in commit `761172d`. The key tuples now carry the `fd_`/`dk_` aliases and `load_player_index` raises when a row has neither position nor salary. The audit's described failure cannot occur.

### There is no Yahoo scraper

`grep -ri yahoo` returns documentation only. `ROADMAP.md` lists it under rejects and `docs/ARCHITECTURE.md` states the repo does not ship one. The audit asserts a file it cannot point to.

### `weather.py` is not timezone-misaligned

It requests hourly data with an `America/New_York` timezone parameter and matches it against ET gametimes — internally consistent. The audit's own summary contradicts its claim here. Only `research_export.py` is genuinely broken.

---

## Overstated claims

| Claim | Audit says | Reality |
|---|---|---|
| Vegas TD anchoring | "zero scaling"; implied totals "nearly identical" | Pass rate swings 0.515 → 0.615 across a ±10 spread; QB attempts get +2.0% per point above a 20.0 baseline. Only `rush_td`/`rec_td` lack a direct term. The audit also cites stale config defaults (0.014 / 22.0) instead of the shipped 0.020 / 20.0 |
| Target-share inflation | 125-140% team sums | Mechanism real, magnitude overstated: ~110% typical. Measured median 1.008, max 1.257 across 30 teams |
| `player_name` groupby | "corrupts `games_played`" | That field does not exist. Downstream re-groups by `player_id` + `(season, week)`. Latent fragility, not active corruption |
| Blank projections | name/team mismatch silently drops players | The merge is a self-join on roster-derived keys, so available players always match. Measured: 90 blanks = IR(69) + O(20) + D(1), and **0** available players blank |
| DST priors | opponent ignored entirely | Opponent implied total drives points-allowed; opponent pass rate scales events. Only the base event priors are fixed constants |
| `lineups.report.txt` | no `$Salary` | `$Salary` is printed per lineup. The 8-lineup cap applies only above 20 lineups. Only Team and Kickoff are missing |
| Underdog scraper file | `bbm/board_parse.py`, ~370 lines | `board_parse.py` is 538 lines of pure regex with no DOM or network. The scraping is `extension/bbm-copilot/content.js` — `querySelectorAll('[aria-label]')` on `underdogsports.com`. The audit never mentions the extension |

---

## Fixed during this verification session

| Commit | Change |
|---|---|
| `761172d` | `--exclude` typos raise; late swap never keeps a lineup with an excluded player; `review` reads the canonical schema; the pool drops unavailable players even from a raw FanDuel CSV |
| `fc32b16` | Rush defense ratings restored (were 0 of 32 teams); alpha 0.08 → 0.35 |
| `57adb6f` | Prior-season window widened from Week 1 to Week 4 at five sites |

---

## Recommended order of work

1. **Fix `LEAGUE_SEC_PER_PLAY`.** Largest single effect, ~13% on every projection. Filter `_neutral_script` to scrimmage plays and reset the constant.
2. **Add vacancy redistribution.** Filter excluded players before `rolling_shares`, then renormalize active-team shares to 1.0.
3. **Fix `_abbrev_last_name`.** Two-player collisions are live. Reuse the `pool_guards.py` logic that already gets it right.
4. **Project fumbles.** Add the field to `PlayerUsageProjection` so `scoring.py` can apply the penalty.
5. **Apply the wind haircut to `rec_yds`.**
6. **Decide the goal-line and NGS/rookie coefficients.** Either wire them up or delete the dead code so it stops implying an adjustment that never runs.
7. **Guard the all-zero path.** Make `salary` carry `salary_fppg`, and fail `normalize`/`validate` when every projection is zero.
8. **Move the live scraping behind an export.** Delete the `extension/` DOM path or swap it for Underdog's own CSV export.
