# Refused list

This page names what CeminiDFS refuses, why, and what the project uses instead.
The list is a guardrail. It is not a wish list.

| Refused | Why | What we use instead |
|---------|-----|---------------------|
| **draftfast** (BenBrostoff) | The repository has no LICENSE. | [pydfs-lineup-optimizer](https://github.com/DimaKudosh/pydfs-lineup-optimizer) (MIT) for lineup generation and late swap. |
| Site scrapers (FanDuel, DraftKings, Underdog, FantasyLabs, Stokastic) | Scraping breaks site ToS and paid-site terms. | Manual CSV export by the operator. Paid CSVs are benchmarks only. |
| Agent Enter / Submit / auto-swap | The operator owns the account and the entry. A click is not reversible. | The agent writes CSVs. The operator submits. The agent does not Enter. |
| SoFi as a dome | SoFi Stadium is a `semi_open` roof. The label is wrong. | `RoofType = open \| dome \| retractable \| semi_open`. SoFi (LAC / LAR) is `semi_open`, and `is_weather_exposed` is false. |
| FPPG retune from one Sunday (CIN, Chase, Higgins, weather) | One sample is not a retune. It overfits one slate. | Keep the projection model. Watch a larger sample. KEEP / REJECT lives in [`../briefs/2026-09-15_gemini-dfs-improve.md`](../briefs/2026-09-15_gemini-dfs-improve.md). |
| Default-on PlayersGroup `max_from_group` | A silent projection haircut distorts the ILP shadow prices. | Opt-in `--flag-wr-triples` report plus a later operator `--exclude`. |
| `--dst-audit` | No license-clean data and no retune this wave. | Existing `--no-offense-vs-dst` build flag. |
| `--weather-audit` | No new weather coefficients from one week. | Open-Meteo fields plus the `semi_open` roof rule. |
| `--stadium-audit` | No new stadium flag this wave. | The existing `RoofType` enum, including `semi_open`. |
| A generated summary file for AI answer engines as a Google tactic | It is not a retrieval signal and it adds a second surface to maintain. | Plain README text, one clear first paragraph, and the `docs/` pages. |

## Notes

- Do not vendor a repository that has no license. Process notes are not code.
- Do not commit salary CSVs, `.env`, or `reports/`.
- Do not edit the Gambling wiki from this repo.
- New optimizer flags need an operator decision and a named use case.

See [`GPP-WORKFLOW.md`](GPP-WORKFLOW.md) for the accepted GPP path and
[`REVIEW-REPORTS.md`](REVIEW-REPORTS.md) for the human gate.
