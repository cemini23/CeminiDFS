# SIP — OpenCode check of Sunday docs (readonly unless one SOP bug)

WORKDIR: /Users/claudiobarone/Projects/CeminiDFS

## WorkDir

/Users/claudiobarone/Projects/CeminiDFS

## Success criteria

1. Read `docs/SUNDAY.md`, `README.md` (Sunday GPP + What is NOT included), `docs/HANDOFF-PARLAYS.md`, `docs/REFUSED.md`, `docs/GEO-PROBE.md`, `CONTRIBUTING.md`.
2. Write `reports/audit/free-ceminidfs-growth/opencode-check.md` with Verdict + Findings (docs quality only).
3. If and only if `docs/SUNDAY.md` step 3 runs `optimize` on `normalized_players.csv` **before** any `run`/`normalize` that creates that file, fix step 3 so the probe comes **after** project+normalize (or after `run --stages` that writes the CSV). Do not change `src/`.
4. Do not invent GEO scores. Do not commit.

## Verify

- `test -f reports/audit/free-ceminidfs-growth/opencode-check.md`
- `grep -q "### Verdict" reports/audit/free-ceminidfs-growth/opencode-check.md`
- `test -z "$(git diff --name-only -- src tests)"`

## NEVER

- Do not edit `src/` or `tests/`.
- Do not implement `--from-ceminidfs`.
- Do not commit.
- Do not rewrite `## Verify`.

## Plan

Read the Sunday docs set. Write `reports/audit/free-ceminidfs-growth/opencode-check.md` with Verdict and Findings. If `docs/SUNDAY.md` still probes `optimize` before a `run`/`normalize` that creates `normalized_players.csv`, fix that order only. Do not edit `src/`. Do not commit. Do not invent GEO scores.
