# CeminiDFS — Cursor / agent schema

DIY NFL DFS projection pipeline (FanDuel-primary) plus optional Best Ball Mania draft copilot. Open this folder as the Cursor project root.

Canon research: Gambling wiki `concepts/diy-nfl-dfs-model-architecture.md`. Start with `README.md`, `PLAN.md`, `ROADMAP.md`, `docs/ARCHITECTURE.md`.

## Hard gates

- Do not type FanDuel / Underdog / any site passwords into chat or agents.
- Do not click Enter, Submit, or late-swap in a live contest. Export CSVs only; the operator submits.
- Stokastic / FantasyLabs CSVs are accuracy and ownership benchmarks only. Do not scrape paid sites.
- Do not vendor `draftfast` or any no-LICENSE optimizer. Showdown uses pydfs captain mode.
- No mass unattended portal booking. Respect site ToS and rate limits.
- Say **route as recommended** / `/route` / `route this` to outsource. Do not implement in the parent Cursor session except fallback.

## How to work

| Goal | Do this |
|------|---------|
| Orient | Read `README.md` + `PLAN.md` |
| Tests | `.venv` then `pytest` (no network; e2e needs pydfs) |
| Weekly slate | `ceminidfs run --season YYYY --week N --salary <fd.csv> --stages all` |
| BBM | `ceminidfs bbm` — see `docs/BBM.md` |
| Route a task | `route-task` from this repo (`~/Projects/agent-toolkit`) |

## Writing style (ASD-STE100)

Write chat replies, explanations, summaries, commit messages, and PR descriptions in **ASD-STE100 Simplified Technical English** (adapted — not certified STE):

- Use short, direct sentences (~20 words for instructions, ~25 for descriptions).
- Use one plain word per concept; do not use synonyms or jargon.
- Use one instruction per sentence; use imperative mood for steps.
- Use active voice and simple tenses (present, past, future).
- Keep articles (the, a, an). Do not drop words to save space.
- Use one term for one thing every time.

**Do not rewrite:** source code, identifiers, file paths, CLI output, direct quotes, or literal error messages.

Wiki canon: `@osint-wiki/concepts/asd-ste100-writing-style.md`. Optional global copy: `~/.claude/CLAUDE.md`.
