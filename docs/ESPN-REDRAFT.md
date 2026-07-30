# ESPN 12-team PPR redraft — Sept draft ready

Season-long **snake** prep for ESPN Fantasy. Produces a cheat sheet + ranked CSV for ESPN’s **native** Pre-Draft Rankings / Auto-Pick — not a browser click-bot.

## Defaults

| Setting | Value |
|---------|--------|
| Format | 12-team snake, full PPR |
| Scoring | 1.0/rec, 4pt pass TD, −2 INT, −2 fumble lost |
| Roster | QB · 2RB · 2WR · TE · FLEX · DST · K · ~6 bench |
| Autopick | ESPN Pre-Draft Rankings + Edit Auto-Pick Strategy only |

## Quick start

```bash
# Cheat sheet (BUY/FADE + Auto-Pick Strategy)
ceminidfs redraft draft-card

# Ranked board from ADP CSV
ceminidfs redraft prerank --adp research/espn-ppr-adp.csv --out artifacts/espn-prerank.csv

# Weekly: card + prerank together
ceminidfs redraft refresh --adp research/espn-ppr-adp.csv
```

## ADP CSV format

Tracked snapshot: [`config/espn-ppr-adp.csv`](../config/espn-ppr-adp.csv)  
Source notes: [`config/espn-ppr-adp.SOURCE.md`](../config/espn-ppr-adp.SOURCE.md)  
Template: [`config/espn-ppr-adp.template.csv`](../config/espn-ppr-adp.template.csv)

```bash
# Weekly refresh from the tracked FantasyPros PPR ADP snapshot
ceminidfs redraft refresh --adp config/espn-ppr-adp.csv

# Or copy into gitignored research/ and edit locally
cp config/espn-ppr-adp.csv research/espn-ppr-adp.csv
ceminidfs redraft refresh --adp research/espn-ppr-adp.csv
```

Required columns (aliases accepted):

| Column | Aliases |
|--------|---------|
| `name` | `player`, `player_name`, `full_name` |
| `pos` | `position` |
| `adp` | `avg_pick`, `average_draft_position`, `rank` |

Optional: `team`, `notes`, `projection_pts` (or counting stats → scored via `score_espn_ppr_season`).

Source ADP manually from FantasyPros / ESPN consensus exports — same posture as BBM (no scrapers).

## Load into ESPN (≥1 hour before draft)

1. Open league → **My Team** → **Edit Draft Strategy** / Pre-Draft Rankings.
2. Reorder ESPN’s list to match `artifacts/espn-prerank.csv` (at least top 60; full top 200 if time).
3. Set **Auto-Pick Strategy** per-round + position min/max from the draft card.
4. **Save** — ESPN locks edits ~1 hour before draft time.
5. Draft night: click live; keep **Player Queue** topped; if disconnected, ESPN uses your ranks + strategy.

## Operator timeline

| When | Action |
|------|--------|
| Weekly Aug | Drop fresh ADP → `ceminidfs redraft refresh --adp …` (~15–20 min) |
| ~Aug 25 | Freeze BUY/FADE in `src/ceminidfs/redraft/config.py`; lock prerank |
| Draft week | Load ESPN Pre-Draft Rankings + Auto-Pick Strategy; save ≥1hr before |
| Draft night | Live click + queue, or full autopick from your ranks |

## CLI

| Command | Purpose |
|---------|---------|
| `redraft draft-card` | Markdown cheat sheet → `briefs/espn-ppr-draft-card-YYYY-MM-DD.md` |
| `redraft prerank --adp` | Ordered CSV for ESPN Pre-Draft Rankings |
| `redraft refresh --adp` | Card + prerank in one shot |

## Non-goals

- Browser auto-click picks on ESPN
- BBM 150-entry exposure / Underdog extension
- Auction drafts
- In-season waiver optimizer (follow-up)

## Related

- Scoring: `ceminidfs.models.scoring.score_espn_ppr_season`
- BBM (different product): [BBM.md](BBM.md)
- ESPN injury overlay only (DFS): [espn-api-eval.md](espn-api-eval.md)
