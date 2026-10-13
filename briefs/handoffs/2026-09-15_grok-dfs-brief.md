# Routed handoff - 2026-09-15 gemini DFS brief

LANE: hard
WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Target

Write the CeminiDFS improve brief from the parent Plan. Markdown only.

## Summary

Read `/Users/claudiobarone/Projects/Gambling wiki/briefs/handoffs/2026-09-15_gemini-tool-improve-plan.md` and `/Users/claudiobarone/Projects/Gambling wiki/briefs/deep-research/extracts/NFL-DFS-Optimization-Architecture-Research.md`. Also skim `briefs/2026-09-14_week1-fd-recap/tool-gaps.md` and `src/ceminidfs/data/stadiums.py`. Write `briefs/2026-09-15_gemini-dfs-improve.md`.

## Plan

Follow the Plan file section B. Map TG01–07 to already-have vs missing report vs do-not-build. Recommend only `--flag-wr-triples`, `--late-swap-audit`, `--ownership-fade-report`. All do_not_auto_apply. SoFi is `semi_open` already in stadiums.py. No projection haircuts. No new weather coefficients from n=1.

## Success criteria

1. `briefs/2026-09-15_gemini-dfs-improve.md` exists.
2. Contains TG01–TG07 and do_not_auto_apply.
3. Rejects draftfast and scrapers.
4. Does not call SoFi a dome.

## Verify

- `test -f briefs/2026-09-15_gemini-dfs-improve.md`
- `rg -n "TG01|do_not_auto_apply|semi_open|draftfast" briefs/2026-09-15_gemini-dfs-improve.md`

## NEVER

- Do not print or commit secrets.
- Stay inside WORKDIR except reading the gambling-wiki Plan/extract (read-only).
- No Python edits. No optimizer retune. No FanDuel Enter.
