# ESPN PPR ADP source

- **File:** `config/espn-ppr-adp.csv`
- **Source:** FantasyPros PPR Overall ADP (consensus of league hosts; ESPN ADP under PPR)
- **URL:** https://www.fantasypros.com/nfl/adp/ppr-overall.php
- **Fetched:** 2026-07-30
- **Scoring:** PPR (maps to ESPN redraft)
- **Rows:** 410
- **Notes column:** `fp_rank` = FantasyPros display rank; `bye` when present
- Refresh: re-fetch page → regenerate CSV → `ceminidfs redraft refresh --adp config/espn-ppr-adp.csv`
