# K128 — Opus 4.8 Master Plan (2026-06-24)

> **Goal:** Close out all CeminiDFS items from today's research ingest + remaining edge-sprint hygiene. No new fetch dependencies; wiki-only posture for duplicate DFS repos.
>
> **Sources:** `OSINT WORKSPACE/wiki/sources/tool-eval-metaplan-81url-2026-06-24.md`, daily sweep `2026-06-24-daily.md`, prior briefs K125–K127 (complete).

## Status audit (pre-sprint)

| Brief | Scope | State |
|-------|-------|-------|
| K125 EPA cleanroom | `pbp_filters.py`, defense ratings | **Done** — `docs/epa-cleanroom-audit.md` |
| K126 coherence-risk | P0 pass-pro + RZ; P1 sim CV; P2 fourth-down + workload | **Done** — 178 tests green |
| K127 sportsdataverse | smoke, benchmark, defer verdict | **Done** — `docs/sportsdataverse-eval.md` |
| Edge sprint | GPP profile, RB cal, P2 coherence, NGS stub | **Done** except fixture + doc counts |
| K128 metaplan (today) | pydfs/draftfast/NBA-DFS duplicates | **Wiki-only** — no prod steal |

Today's **Tool Evaluation Analysis Metaplan** has **zero Adopt rows for CeminiDFS**. Duplicate optimizers (pydfs, draftfast, NBA-DFS-Tools) are reference-only; Setfive/fanduel-api WebSocket routes to CCC-wiki, not this repo.

## Parallel tracks

| Track | Agent | Deliverable |
|-------|-------|-------------|
| **K128-A** | Kimi K2.5 | `briefs/2026-06-24_k128-metaplan-dfs-tools-reference.md` + ARCHITECTURE footnote |
| **K128-B** | GPT 5.4 | `tests/fixtures/sample_ownership_labels.csv` + GPP-WORKFLOW demo path |
| **K128-C** | GPT 5.4 | PLAN.md test count (178), edge_sprint exit criteria checked |
| **K128-D** | Parent | Live `ceminidfs sdv-benchmark --season 2025` if network; refresh `docs/benchmarks/sdv_benchmark_2025.json` |

## K128-A — Brief + architecture footnote

**New:** `briefs/2026-06-24_k128-metaplan-dfs-tools-reference.md`

- Verdict: wiki-only for 5 duplicate DFS repos named in metaplan
- pydfs-lineup-optimizer remains **borrowed** dependency (already integrated)
- Reject GPL fanduel-api fork; defer LongShu MLX game-dev models (out of scope)

**Extend:** `docs/ARCHITECTURE.md` — "Build vs borrow" table row for reference-only duplicates with link to K128 brief.

## K128-B — Ownership calibrate demo fixture

**New:** `tests/fixtures/sample_ownership_labels.csv`

Format matches `ceminidfs ownership calibrate --labels` (Player, Team, Position, Own%).

**Extend:** `docs/GPP-WORKFLOW.md` — example using committed fixture path.

Optional: tiny test asserting fixture parses (reuse existing calibrate CLI test pattern).

## K128-C — Doc hygiene

- `PLAN.md`: **178 tests** (not 194)
- `prompts/edge_sprint_opus_plan.md`: mark exit criteria `[x]`

## K128-D — Live SDV benchmark (optional)

Run only if sportsdataverse import works on host; otherwise keep existing defer JSON.

## Exit criteria

- [x] K128 brief staged
- [x] ARCHITECTURE footnote for reference-only DFS tools
- [x] `sample_ownership_labels.csv` + GPP-WORKFLOW reference
- [x] PLAN.md test count accurate (179)
- [x] `pytest` + `ruff` green

## Out of scope

- Setfive/fanduel-api WebSocket (CCC-wiki)
- BBMOD / castle-sim (game-dev-wiki K128)
- Replacing nflreadpy with sportsdataverse
- Commit unless user asks
