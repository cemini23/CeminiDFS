# Easy — operator cheat sheet for Gemini review reports

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

Add **one new file only**: `docs/REVIEW-REPORTS.md`

Do not edit Python. Do not edit `docs/GPP-WORKFLOW.md` (hard route owns that).

Write short STE-style markdown:

- Title: Review reports (human gate)
- The three flags: `--flag-wr-triples`, `--late-swap-audit`, `--ownership-fade-report`
- Artifacts: `stack_fragility_report.csv`, `late_swap_alert_report.csv`, `leverage_fade_matrix.csv`
- Operator reads CSVs, then may `--exclude` / `--max-exposure` / `late-swap`
- Agent does not Enter
- Do not auto-apply. Do not retune CIN/Chase/weather from Week 1
- SoFi stays `semi_open`, not a dome
- Point to `briefs/2026-09-15_gemini-dfs-improve.md`

No secrets. No salary CSVs.
