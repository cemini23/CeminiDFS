# CeminiDFS — K274 projection residuals and rookie prior

Open this folder: `/Users/claudiobarone/Projects/CeminiDFS`

Lane is **hard**. This slice is multi-file code plus tests. The route skill sends that to a premium Plan, then Grok implements. The block below is already the Plan.

Paste the block below as the first message. The agent must route. It must not type the feature in the Cursor session.

```
/route hard: K274 projection residuals and a zero-coefficient rookie prior. WorkDir is /Users/claudiobarone/Projects/CeminiDFS.

Announce the lane. This message is the Plan. Copy it into the handoff ## Plan section. Do not replan. Shell out to route-task. Do not implement in this Cursor session. Hard means Grok CLI implements with always-approve. If Grok usage is out, DeepSeek Flash implements, then OpenCode Zen free. Never Pro. Parent Cursor implements only if the script prints "claude-ds HANG - Cursor parent takeover" or "Cursor Grok fallback". Profile is claudio. Kit is ~/Projects/agent-toolkit.

## Done

Our own projection rows are written as season and week parquet partitions. A public Next Gen Stats column can sit on the passing projection with a live coefficient of zero. Player goal-line share is a column with a live coefficient of zero. Outdoor wind can lower the passing-yards mean without a second pass-rate penalty. A rookie prior accepts draft capital, dominator, breakout age, and career yards per route run, and the default prior is zero. Commit and push. CI on main is green.

Read the current code first. Keep a path that already has a test. Add only the missing piece.

## Read first

- briefs/2026-09-27_k274-ceminidfs.md
- src/ceminidfs/orchestrator/run.py
- src/ceminidfs/pipeline/project.py
- src/ceminidfs/data/ngs_eval.py
- src/ceminidfs/models/usage.py
- src/ceminidfs/models/volume.py
- src/ceminidfs/models/coherence_risk.py
- src/ceminidfs/data/stadiums.py

## Already in this repo

Do not rebuild these.

- usage.py already has target share, air yards share, and WOPR.
- volume.py already projects pace and implied team total, and it already cuts pass rate when wind is at least 10 mph.
- usage.py already stores qb_rush_per_game.
- coherence_risk.py already adjusts team red-zone play-call inside the 20 (yardline_100 <= 20).
- stadiums.py already has roof_type. Dome and semi_open are indoor.
- pipeline/sdv_benchmark.py can already read one nflverse release parquet. Do not clone nflverse-data.

## This slice only

Write the pattern in our code. Do not clone and do not copy upstream files.

1. Parquet. A single player_projection_base.parquet already exists. Add a season/week partition layout for our own projection rows. Do not download a college dump.

2. CPOE residual. ngs_eval.py is a stub. If load_ngs_passing_sample already returns completion_percentage_above_expectation or avg_separation, store the column on the passing row. Leave the live coefficient at zero. A fixture test may pass an explicit test coefficient and must show the default path unchanged. Do not paste a weight from the 4for4 correlation table. That table is not a coefficient. In that public 2018–2023 quarterback study, next-season fantasy points track rush attempts per game (0.47) far above CPOE (0.13). X uses CPOE as an MVP rank. That is the field narrative. Do not raise our coefficient to match it. Do not invent the JorgeAcin closing-speed formula. Do not clone that tree. A public X search for "closing speed" returns athletic highlight clips, not this stat.

3. Goal-line share. From our own play-by-play, add player carry share and target share for yardline_100 <= 5. Keep the existing team red-zone tendency. Leave the new column's live coefficient at zero. A fixture test may set a tiny explicit coefficient and must show that more goal-line carries raise the running-back mean, and that the default path is unchanged. Do not copy the existing 0.06 or 0.08 team boosts onto this column.

4. Wind on the passing-yards mean. volume.py already cuts pass rate. If the passing-yards mean does not also drop for an outdoor game with high wind, add one haircut that reuses stadiums.roof_type and the existing wind field. Dome, indoor, semi_open, and closed retractable roofs get no extra haircut. Do not add a second pass-rate penalty. Do not add a weather vendor.

5. Rookie prior. Add a small module, src/ceminidfs/models/rookie_prior.py. Inputs are draft capital, dominator rating, breakout age, and career yards per route run. Every coefficient defaults to zero, so a player with no college row keeps today's projection. A fixture test shows that an explicit non-zero coefficient moves the prior, and that the default path is unchanged. If a local CSV with those columns is missing, the prior stays zero. Do not add wide-receiver forty time. Do not add RAS. Do not add a CFL column. Do not scrape a recruiting site. Do not download cfbfastR-data.

Public context for the prior, not a formula to paste: Peter Howard's video defines college dominator and breakout age as linked market-share stats for wide-receiver prospects (https://www.youtube.com/watch?v=jqGiYZl0w18). The auto-captions are messy. Do not transcribe a formula from them. Career college yards per route run is the prior. Same-season yards-per-route-run leaderboards on X are a weekly rank, not this input.

## Socials that do not change the build

- r/DynastyFF "Follow the Volume" matches the volume path we already have. Do not add a second volume model.
- Weekly YouTube pick shows and SaberSim's "Adjusting Projections" video are not a data source. Do not copy a paid sim.
- Reddit has no CFL-to-NFL fantasy translation. Leave CFL out.
- A low-score DynastyFF metrics promo lists RAS and target vacancies. Do not add either from that post.

## Deploy — operator already approved this prompt

You may fully deploy when this repo already has that path:

- Bump the kit or package version.
- Notarize, sign, and bake.
- Post LIVE Discord.
- Deploy the site.

Commit and push are required. Wait until GitHub CI on main is green. Do not wait for a second LIVE OK.

Do not add a new public site, a new Discord bot, or a contest-entry client in order to use this permission. This repo's ship path is commit, push, and `.github/workflows/ci.yml`.

## NEVER

- Do not git-clone cfbfastR-cfb-data, cfbfastR-data, nfl-closing-speed-csoe, weathernfl, nfldata, nflverse-data, or any other sports tree.
- Do not copy upstream source.
- Do not log into FanDuel, DraftKings, or Hard Rock.
- Do not enter a contest. Do not auto-submit a lineup. No live order.
- Do not scrape a book site or a recruiting site.
- No secrets in the handoff. Do not swap /route.

## Verify

pytest -q tests/test_ngs_eval.py tests/test_pipeline.py
ruff check src tests
```
