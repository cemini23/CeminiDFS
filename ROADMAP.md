# CeminiDFS Roadmap

> **Primary stack:** FanDuel salaries (manual export) + **nflverse** via nflreadpy.  
> **Optional layers:** Sleeper buzz (stage-0 sentiment), sportsdataverse eval, BBM copilot.  
> **Research canon:** Gambling wiki [DIY NFL DFS model (K125)](https://github.com/cemini23/gambling-wiki/blob/main/wiki/concepts/diy-nfl-dfs-model-architecture.md).

## Data posture (non-negotiable)

| Source | Role | Verdict |
|--------|------|---------|
| nflreadpy / nflverse | PBP, schedules, rosters, injuries | **Primary** — single canonical fetch path |
| FanDuel / DK salary CSV | Slate ingest | **Manual** — no live salary API |
| Open-Meteo | Weather at kickoff | **Borrow** |
| The Odds API | Optional live Vegas | **Borrow** (`.env`) |
| Stokastic / FantasyLabs | Accuracy + ownership benchmarks | **Manual CSV** |
| Sleeper public API | Trending add/drop buzz | **Optional** — stage-0 sentiment only; not projections |
| cwendt94/espn-api | Fantasy roster injury overlay | **Optional** — requires `league_id`; see `docs/espn-api-eval.md` |
| sportsdataverse-py | Eval / benchmark | **Defer** — see `docs/sportsdataverse-eval.md` |

## Rejects (do not install)

| Repo / pattern | Reason |
|----------------|--------|
| Underdog / Yahoo scrapers (no license) | Legal risk |
| BenBrostoff/draftfast | No LICENSE file (K138); use pydfs only |
| GPL Sleeper or fanduel-api forks | License incompatible with MIT sale |
| Hugging Face coherence parquet in prod fetch | K126 clean-room only |
| thiagocavaleiro PM sports bot | Out of scope |

## Shipped tracks

| Brief | Deliverable | Doc |
|-------|-------------|-----|
| K125 | EPA clean-room audit | `docs/epa-cleanroom-audit.md` |
| K126 | Coherence-risk prototypes + sim CV | `docs/coherence-risk-audit.md` |
| K127 | sportsdataverse smoke + defer | `docs/sportsdataverse-eval.md` |
| K128 | Duplicate DFS optimizers wiki-only | `briefs/2026-06-24_k128-metaplan-dfs-tools-reference.md` |
| K129 | Sleeper buzz + luck metrics | `docs/sleeper-sentiment-eval.md` |
| K138 | ESPN injury adjunct + draftfast reject | `docs/espn-api-eval.md` |
| BBM7 | Best Ball draft copilot | `docs/BBM.md` |
| Sweep 07-03 | Research triage — zero adopts; reading refs → Gambling wiki | `briefs/2026-07-03_research-triage-plan.md` |
| Sweep 07-05 | Research triage — zero adopts; SFB16 ADP reading ref → docs/BBM.md | `briefs/2026-07-05_research-triage-plan.md` |

## K129 — Sleeper sentiment (2026-06-25)

Clean-room implementation inspired by `dtsong/sleeper-api-wrapper` (MIT). **No pip dependency** on third-party Sleeper wrappers.

| Steal | Implementation | CLI |
|-------|----------------|-----|
| `get_trending_players` | `ceminidfs.data.sleeper` + `models.buzz_signal` | `ceminidfs sleeper trending` |
| Expected-wins / luck (fantasy-football-wrapped) | `pipeline.luck_metrics` | `ceminidfs luck-metrics` |
| sleeper-mini UX | Deferred — reference only for future embedded UI |

Enable buzz on slate project:

```yaml
# config/nfl_dfs.yaml
buzz_signal:
  enabled: true
  lookback_hours: 24
  ownership_boost_per_1k: 0.5
  max_ownership_boost: 8.0
```

## K138 — ESPN adjunct (2026-07-01)

Optional injury fill from MIT `espn_api` when operator configures a fantasy `league_id`.

```yaml
espn_adjunct:
  enabled: false
  league_id: null
  year: null
```

```bash
pip install -e ".[espn]"
ceminidfs espn probe --league-id <id> --year 2025
```

## Backlog

- ~~Registry expansion toward top-240 via weekly ADP refresh~~ — `expand_verified` on `refresh-adp` + `bbm preflight` (2026-07-02)
- Setfive fanduel-api WebSocket → CCC-wiki (not this repo)
- sportsdataverse adopt only if maintenance win is proven on 2025+ slates
