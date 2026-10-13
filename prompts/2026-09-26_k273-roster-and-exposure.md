# CeminiDFS — K273 roster rules and exposure cap

Open this folder: `/Users/claudiobarone/Projects/CeminiDFS`

Paste the block below as the first message. The agent must route. It must not type the feature in the Cursor session.

```
/route mid: K273 roster rules and lineup exposure cap. WorkDir is /Users/claudiobarone/Projects/CeminiDFS.

Announce the lane, then shell out to route-task. Do not implement in this Cursor session. Mid means Grok CLI plans, then OpenCode Zen free, then DeepSeek Flash (deepseek-flash). Never Pro. Always-approve is the default. If Grok usage is out, Flash plans, then OpenCode or Flash writes. Parent Cursor implements only if the script prints "claude-ds HANG - Cursor parent takeover" or "Cursor Grok fallback". Profile is claudio. Kit is ~/Projects/agent-toolkit.

## Done

Classic, showdown, and captain roster rules live in our optimizer and have tests. The exported lineup file honors a per-player exposure cap. Commit and push. CI on main is green.

Read the current code first. Keep a rule that already has a test. Add only the missing rule and its test.

## Read first

- briefs/2026-09-26_k273-ceminidfs.md
- src/ceminidfs/export/optimize.py (LINEUP_HEADERS, generate_lineups, select_with_exposure_caps)
- src/ceminidfs/orchestrator/validate.py (showdown salary, captain 1.5x)
- tests/test_optimize_showdown.py
- tests/test_optimize_main_slate.py

## This slice only

Write the pattern in our code. Do not clone and do not copy upstream files.

1. Roster rules, in our own tables:
   - FanDuel classic: QB, RB, RB, WR, WR, WR, TE, FLEX, DEF.
   - DraftKings classic: QB, RB, RB, WR, WR, WR, TE, FLEX, DST.
   - FanDuel showdown: 1 MVP + 5 FLEX, budget 60000, max 5 from one team.
   - DraftKings captain: 1 CPT + 5 FLEX. The captain seat costs 1.5x salary.
2. Exposure cap: generate_lineups passes player max_exposure into the solver, then applies select_with_exposure_caps only for team exposure. Close that gap. The written CSV must stay under the player cap as well as the team cap. Default player cap stays 0.35 unless a test already pins another number.

## Deploy — operator already approved this prompt

You may fully deploy when this repo already has that path:

- Bump the kit or package version.
- Notarize, sign, and bake.
- Post LIVE Discord.
- Deploy the site.

Commit and push are required. Wait until GitHub CI on main is green. Do not wait for a second LIVE OK.

Do not add a new public site, a new Discord bot, or a contest-entry client in order to use this permission. This repo's ship path is commit, push, and `.github/workflows/ci.yml`.

## NEVER

- Do not git-clone draftfast, nuke-dfs-hub, dfsOptimizer, cfb-dfs-data, or any other sports tree.
- Do not copy upstream source. Paraphrase the constraint into our modules.
- Do not log into FanDuel, DraftKings, or Hard Rock.
- Do not enter a contest. Do not auto-submit a lineup. No live order.
- Do not scrape a book site.
- No secrets in the handoff. Do not swap /route.

## Verify

pytest -q tests/test_optimize_showdown.py tests/test_optimize_main_slate.py
ruff check src tests
```
