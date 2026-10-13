# Grok Bots for CeminiDFS

Operator paste for Grok Bot.app. Canon lives in OSINT `briefs/2026-09-01_grok-bot-charters.md`.

Updated 2026-10-04. Gemini research prompts are retired. The CLI emits `environment.csv` and the status file. The desks verify and write a packet. They do not replace the generator.

| Bot | Charter | When |
|-----|---------|------|
| **DFS Slate Desk** (already exists) | §8 | Before lock: verify the generated status file, T-90, salary CSV walk. No scratch CSV. No lineups. |
| **DFS Recap Desk** | §18 | **Live** in Grok Bot.app. After the slate: consume `reports/audit/fade-coverage-w{week}.md`, score the lineups you entered, write tool gaps. |

DFS Recap Desk is live. Do not create a second Recap Bot. The Recap Desk does not write this repo. Do not sign FanDuel on the Bot VM except, if you already sit in the account, to **export results** — never Enter / Submit / late-swap. Never paste an API key.

§7 is the X Desk. This recap desk is **§18**. Do not send a reader to §7 for it.

Parlays research is a **different** bot (`Parlays Slate Desk`, §17) in the CeminiParlays repo. It does not own `environment.csv`.

## DFS Slate Desk

**Name:** DFS Slate Desk  
**Title:** Injury, T-90, salary CSV walk

The operator passes the generated status file to `ceminidfs`. The desk confirms that list against NFL.com and the club pages and flags a contradiction. It writes `/workspace/dfs-slate/YYYY-MM-DD.md` only. It does not write a scratch CSV.

Take the slate from the current salary CSV or the schedule. Include **09:30 ET** when that window is on the slate. Do not hardcode a week, a date, or the set {13:00, 16:05, 16:25}.

Hard exclude is `out`, `ir`, `inactive`, `doubtful`, `nfi`, `pup`, `suspended` only. Questionable stays. A team-level opinion is a soft fade, never a removal. No source, no field.

Paste Description + **Sunday Million packet** from OSINT charters §8.

## DFS Recap Desk

**Name:** DFS Recap Desk  
**Title:** Lineup results → tool gaps

Drop `lineups.csv` from `ceminidfs optimize`, a FanDuel entries export, or pasted names. Before scoring, consume `reports/audit/fade-coverage-w{week}.md`. Every slate team with zero book exposure goes into `tool-gaps.md`. If the report is missing, write NO_EVIDENCE for coverage and continue. After games, the Bot scores FanDuel half-PPR using the same table as `ceminidfs.models.scoring.fd_points`. If you also drop the week run folder, it diffs projected vs actual.

Outputs on the Bot VM (`/workspace/dfs-recap/YYYY-MM-DD/`):

- `scores.csv` — per player projected / actual / delta
- `recap.md` — lineup totals
- `tool-gaps.md` — coverage gaps plus weather, stadiums, injury, and the other surfaces — **HITL only**, no repo write

Paste Description + **Score entered lineups** from OSINT charters §18.

Laptop still owns numbers: `ceminidfs fetch` / `run` / `backtest`. The recap bot does not replace pydfs or invent contest ranks without a screenshot you provide.

### Scoring has one owner

`src/ceminidfs/models/scoring.py` (`fd_points`) is the only scorer. The Recap
Desk must call it. A second scorer drifts.

The Week 5 Recap Desk script was un-versioned and wrong in three places. Do not
copy those rules:

- It gave a skill player `6 * (kick return TD + punt return TD)`. FanDuel pays
  only the D/ST for a return TD.
- It credited a 2-point conversion to the passer only. FanDuel credits the
  passer and the receiver.
- It read every JSON in `boxes/` with no event-id guard. A second file for one
  game doubles every stat.

None of these fired the week's cash count. Fix them in the repo scorer, not in
the Bot.

## Never

- Enter / Submit / late-swap from the Bot
- Write a scratch status CSV or replace the generated file
- Invent a wind value, a roof call, a spread, a total, a status, or a projection
- Drop a 09:30 game by hardcoding kick times
- Treat Questionable as a hard exclude, or remove a team on an opinion
- Put frequencies, pool guards, or opponent reads in the profile
- Sign a sportsbook or a bank, or paste an API key
- Replace §8 DFS Slate Desk with this recap bot
