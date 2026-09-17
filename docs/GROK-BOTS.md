# Grok Bots for CeminiDFS

Operator paste for Grok Bot.app. Canon lives in OSINT `briefs/2026-09-01_grok-bot-charters.md`.

| Bot | Charter | When |
|-----|---------|------|
| **DFS Slate Desk** (already exists) | §8 | Before lock: injury, weather, T-90, salary CSV walk. No lineups. |
| **DFS Recap Desk** (new 2026-09-14) | §18 | After the slate: score the lineups you entered; write tool gaps. |

Cursor cannot create the Bots. Paste **Description** into the profile, then send **First skill**. No routine until one clean manual run. Do not sign FanDuel on the Bot VM except, if you already sit in the account, to **export results** — never Enter / Submit / late-swap.

Parlays research is a **different** bot (`Parlays Slate Desk`, §17) in the CeminiParlays repo.

## DFS Recap Desk

**Name:** DFS Recap Desk  
**Title:** Lineup results → tool gaps

Drop `lineups.csv` from `ceminidfs optimize`, a FanDuel entries export, or pasted names. After games, the Bot scores FanDuel half-PPR using the same table as `ceminidfs.models.scoring.fd_points` (0.5 PPR, yardage bonuses, DST stub). If you also drop the week run folder, it diffs projected vs actual.

Outputs on the Bot VM (`/workspace/dfs-recap/YYYY-MM-DD/`):

- `scores.csv` — per player projected / actual / delta
- `recap.md` — lineup totals
- `tool-gaps.md` — weather, stadiums/SoFi, injury, defense multiplier, stack rules, ownership, projection — **HITL only**, no repo write

Paste Description + **Score entered lineups** from OSINT charters §18.

Laptop still owns numbers: `ceminidfs fetch` / `run` / `backtest`. The recap bot does not replace pydfs or invent contest ranks without a screenshot you provide.

## Never

- Enter / Submit / late-swap from the Bot
- Invent projections or ownership
- Replace §8 DFS Slate Desk with this recap bot
