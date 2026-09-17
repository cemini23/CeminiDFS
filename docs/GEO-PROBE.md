# GEO probe template

This page is a protocol. It is a template for a real check. It holds no results.
Do not invent a score, a rank, or a citation count.

## Purpose

A GEO probe records what a retrieval engine returns for a few plain-language
queries. The probe shows whether the README and the wiki page are retrieved and
cited for DIY DFS queries. The probe is measurement, not a site change.

## Metrics

Two metrics per row:

- **Ds** — the engine retrieved the target URL in the result set. `y` or `n`.
- **Cs** — the engine cited the target URL in the answer text or the answer
  links. `y` or `n`.

Ds and Cs are separate. A retrieved URL can stay uncited.

Record only what you observe. Do not estimate. Do not backfill from memory.

## Fixed inputs

- Target URL 1: the CeminiDFS README on GitHub.
- Target URL 2: the Gambling wiki page for the DIY NFL DFS model (K125).
- Engines: 2. Use Google plus one AI answer engine. Name the engine in the row.
- Date: the local date of the check (`YYYY-MM-DD`).
- Region and language: record them in the notes if they differ from the default.

## Queries

Use 3 to 5 paraphrase queries. These five are a starting set. Change the wording
if you want a different paraphrase.

1. `DIY NFL DFS projections nflverse pydfs`
2. `FanDuel GPP lineup optimizer MIT`
3. `CeminiDFS Sunday GPP`
4. `open source NFL DFS projection pipeline weather Vegas`
5. `self-directed FanDuel GPP operator Python salary CSV`

## Result table

Copy this table for each probe run. Leave a result cell blank, or write
`NO_EVIDENCE`, when you did not observe the signal. Do not write a number you
did not see.

| Query | Engine | Ds (retrieved URL y/n) | Cs (cited y/n) | Date | Notes |
|-------|--------|------------------------|----------------|------|-------|
| 1 | Google | | | | |
| 1 | AI answer engine | | | | |
| 2 | Google | | | | |
| 2 | AI answer engine | | | | |
| 3 | Google | | | | |
| 3 | AI answer engine | | | | |
| 4 | Google | | | | |
| 4 | AI answer engine | | | | |
| 5 | Google | | | | |
| 5 | AI answer engine | | | | |

## How to run one row

1. Open the engine in a clean session. Turn off personalization when the engine allows it.
2. Enter the query exactly as written above.
3. Look for target URL 1 and target URL 2 in the results and in the answer.
4. Set Ds to `y` when the URL appears in the result set. Set Cs to `y` when the
   engine cites the URL in the answer.
5. Write the date. Write a short note when the result is odd.

## Rules

- Do not invent a Google Search Console number, an impression count, a rank, or a citation score.
- Do not write a total or an average across rows unless you ran every row.
- Do not add a machine-readable summary file for answer engines as a shortcut.
  Plain README text and the `docs/` pages are the surface.
- Keep one table per probe date. Do not overwrite an older table.

## Where results go

Paste the filled table into a local brief under `briefs/`. Do not commit a
result table with invented cells. `reports/` stays gitignored.
