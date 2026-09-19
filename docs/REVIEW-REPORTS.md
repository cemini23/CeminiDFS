# Review reports (human gate)

This sheet names three review flags and three report files. Flags default off.

The operator reads the CSV files. Then the operator may `--exclude`, `--max-exposure`, or `late-swap` on a later solve.
The agent does not Enter FanDuel. Do not auto-apply a report.

| Flag | Artifact | Operator next step |
|------|----------|--------------------|
| `--flag-wr-triples` | `stack_fragility_report.csv` | Read the same-game WR triples. May later opt in to PlayersGroup `max_from_group=1`. |
| `--late-swap-audit` | `late_swap_alert_report.csv` | Read the Q and D alerts. Confirm a change. Then use the existing `late-swap`. |
| `--ownership-fade-report` | `leverage_fade_matrix.csv` | Read the leverage. May later pass `--max-exposure` or `--exclude`. |

## Human gate

1. The operator reads each CSV.
2. The operator decides. The operator may then `--exclude`, `--max-exposure`, or `late-swap`.
3. The agent does not Enter FanDuel.
4. Do not auto-apply. A report does not change a lineup by itself.

## Jev (optional)

Confirm the jev MCP is on. Pick one review-CSV injury or news cell. Call `jev_verify` with claim = player + status and evidence = that string. Keep or drop the row in HITL. `jev_find` may rank late-swap notes. Jev does not change projections, pydfs, or ownership. No scrape. No Enter.

## Corrections

- Do not retune CIN, Chase, or weather from Week 1. One sample is not a retune.
- SoFi stays `semi_open`. SoFi is not a dome.

Canon: `briefs/2026-09-15_gemini-dfs-improve.md` (KEEP / REJECT, TG01-TG07).
