# ESPN API adjunct — Phase-0 eval (K138)

**Date:** 2026-07-01  
**Verdict:** Optional **injury/status overlay** when operator supplies ESPN fantasy `league_id`. Does not replace nflverse fetch.

## Reference

| Repo | License | Steal |
|------|---------|-------|
| cwendt94/espn-api | MIT (gh verified) | League roster injury tokens → canonical `injury_status` fill |

## Rejects (same batch)

| Repo | Reason |
|------|--------|
| BenBrostoff/draftfast | No LICENSE file on GitHub (K138 downgraded from docx Adopt) |
| statsbomb/open-data | Non-commercial user agreement |
| jokecamp/FootballData | Reference-only static archive; nflverse canonical |

## Wiring

```yaml
espn_adjunct:
  enabled: false
  league_id: null   # required when enabled
  year: null        # defaults to slate season
```

```bash
pip install -e ".[espn,dev]"
ceminidfs espn probe --league-id 123456 --year 2025
```

When enabled during `project_week`, empty salary `injury_status` fields are filled from ESPN roster name match.

## Limits

- Requires a **public or credentialed ESPN fantasy league** the operator controls.
- Name matching is normalized full name; ambiguous matches skipped.
- Does not alter DIY projections — availability / export pass-through only.
