# Week 2 Fri env steals — analysis docx (2026-09-19)

**CeminiDFS only.** No auto-lineup. Verify roofs/salaries Sunday.

## Environment export hints

| Game | roof_type | weather_exposed | Notes |
|------|-----------|-----------------|-------|
| LV @ LAC | semi_open | **false** | SoFi canopy — wind 0 |
| WAS @ DAL | retractable | true | 97°F — roof likely closed |
| GB @ NYJ | open | true | 75% precip, gust 15 |
| PHI @ TEN | open | true | 96°F heat advisory |

Use `environment.csv` contract from `@gambling-wiki/concepts/nfl-weekly-slate-hub-workflow.md`.

## GPP stack posture

| Game | MME note |
|------|----------|
| WAS@DAL | Primary game stack — highest total 50.5 |
| CIN@HOU | **Downgrade** — Collins OUT |
| MIN@CHI | **Jefferson solo** leverage; no MIN stack |
| MIA@SF | Avoid correlated stacks — blowout script |
| PIT@NE | Low total 41.5 — fade shootout builds |

## Injury flags for projection layer

- Collins OUT → downgrade HOU pass volume
- Murray OUT → Wentz → Jefferson target consolidation
- Kamara active → NO backfield split with Etienne
- Flowers/Bowers doubtful → fade or zero in sims

Source: `@gambling-wiki/sources/nfl-week2-slate-env-analysis-2026-09-18.md`
