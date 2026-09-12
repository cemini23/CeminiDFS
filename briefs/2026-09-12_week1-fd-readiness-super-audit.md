# Super audit — Week 1 FanDuel DFS readiness

**Mode:** `prod-ship` · **Date:** Sat 12 Sep 2026 · **Slate:** Sun 13 Sep afternoon FD classic
**Pack:** `reports/audit/pack-week1-fd-readiness/`
**Question:** Ready tonight to `run --profile gpp` then late-swap after 1 p.m. lock?

## Auditor rollup

| Slot | Channel | Role | Model | Verdict |
|------|---------|------|-------|---------|
| 1 | cursor | agentic-reasoning | Opus (`claude-opus-5-thinking-high`) | **FAIL** (arrived after first implement) |
| 2 | cursor | third-lens | Kimi3 (`kimi-k3-max`) | **WARN** |
| 3 | cursor | code-implementation | GPT-SOL (`gpt-5.6-sol-medium`) | **FAIL** |
| 4 | OpenRouter | api-adversarial | Fusion | Completed late — report under `reports/audit/premium-week1-fd-readiness/` |
| 5 | OpenRouter | api-deep-reasoning | `tencent/hy3` | Completed late — same report dir |
| 6 | Grok CLI | code/ops | Grok 4.6 | **WARN** |
| 7 | claude-ds | deepseek-flash 4.1 | dsh | **FAIL** (spread sign + Q-drop) |
| 8 | OpenCode | Zen free | `deepseek-v4-flash-free` then `x-preview-f-free` then `hy3-free` | SDR — Zen `UnknownError` ×3 |

Ollama down. Local pytest this session: DFS-path **51–70 passed**. CI `4782009` green.

Parent verified: `artifacts/cache/schedules_2026.parquet` mtime **1 Sep 19:45**; week_1 vegas/weather from 1 Sep; `data/slates/FanDuel-NFL-…-133104-players-list.csv` still present. `_fetch_cached` returns any existing season parquet (`fetch.py:35-36`). Late-swap raises if a lineup name is missing from the pool (`late_swap.py:176`). Sim rerank slices top 150 with no second exposure pass (`sim_rerank.py:178-207`).

## Consensus (≥3 of returned auditors)

1. **Late-swap is the tonight risk.** It builds a new optimizer without stacks / exposure / excludes. Docs say “rerun the build” then swap; a regenerated `normalized_players.csv` **drops** newly-OUT names; the parser then **hard-fails**. Using the old pool can swap an OUT 4:25 player **in**.
2. **Season cache has no TTL.** Saturday `fetch` can reuse 1 Sep schedules/vegas (HOU −1.5). Friday brief already flagged that flip.
3. **Fresh FanDuel player-list CSV is required.** Parser is ready. The file on disk is not tonight’s export.
4. **`Q` stays in the pool.** `D`/`OUT`/`IR`/`NA`/`EXEMPT` drop. Kamara/Odunze need `--exclude` after inactives.
5. **`--lock-team` does not alias.** `JAC` ≠ `JAX` can silently lock zero players for that club.
6. **Stack tests parse text; they do not prove pydfs composition** on a classic 9-man slate.

## Unique

| Auditor | Finding |
|---------|---------|
| Grok | On-disk vegas still HOU −1.5; week_1 weather still marks SoFi exposed; `--stack a\|b\|c` is one invalid token |
| Kimi | NaN spread → `projected_pass_rate` clamps to **0.75**; Week-1 new-team QB / rookie RB can project **0**; no coverage print for empty `fd_projection` |
| GPT-SOL | Sim-rerank applies max-exposure to **2000** candidates, not the **final 150**; default min salary $59,400; validate() never gets `players_csv` |

## Conflicts

| Topic | Grok | Kimi | GPT-SOL | Resolution |
|-------|------|------|---------|------------|
| Overall | WARN | WARN | FAIL | **SHIP-WITH-FIXES.** Engine can build tonight after cache delete + new CSV. Late-swap and cache TTL must be patched before 1 p.m. |
| Cache files exist? | Yes, 1 Sep | Warns sticky cache | “0 files found” | **Grok/parent win.** GPT-SOL glob missed `artifacts/cache/`. |
| Late-swap severity | warn/conditional | critical (doc trap) | critical (no GPP reapply) | **Both true.** Patch pool+exclude+aliases **and** reapply stacks/exposure. |

## Live injury (Brave news, Sat 12 Sep ~11:50 a.m. ET)

Still treat as **human-gated** until official inactives: Tua OUT; Bowers OUT; Kamara/Odunze Q; Chase no designation in Friday notes. Sources: [Yahoo tracker](https://sports.yahoo.com/fantasy/live/nfl-injury-tracker-week-1-latest-news-fantasy-implications-as-tua-tagovailoa-oblique-ruled-out-brock-bowers-knee-expected-to-miss-time-154233236.html) (~25 min before this brief), [CBS](https://cbssports.com/nfl/news/nfl-week-1-injuries-tracker-rome-odunze-alvin-kamara), [NFL.com](https://www.nfl.com/news/nfl-week-1-injury-report-2026-season).

## Tonight GO/NO-GO (parent)

| Gate | Status |
|------|--------|
| Code can ingest a standard FD player list | GO |
| Week 1 prior-season PBP fallback | GO (tested) |
| Weather/volume | GO **after** cache delete + fetch |
| Optimize + stacks + report | GO if repeated `--stack` and `--profile gpp` |
| Late-swap | **NO-GO until P0 patches** (or hand-zero FPPG and keep rows) |
| Operator submit | GO — agent does not Enter |

**Do not `fetch` until** `artifacts/cache/schedules_2026.parquet` and `artifacts/cache/2026/week_1/` are deleted (or `--force` ships).

## Full patch backlog (every issue)

### P0 — tonight

| ID | Issue | Evidence | Fix |
|----|-------|----------|-----|
| P0-1 | Season cache never refreshes | `fetch.py:33-36`; parquet 1 Sep | `--force` / TTL; warn if cache >12h |
| P0-2 | Late-swap drops GPP constraints | `late_swap.py:59-84` | Reapply stacks, locks, excludes, max_exposure, pool constraints |
| P0-3 | Regenerated pool removes OUT names → swap crash | `normalize.py:373-375`; `late_swap.py:176` | Keep rows; zero FPPG; add `--exclude` |
| P0-4 | `--lock-team` no aliases | `late_swap.py:21-31` | `normalize_team_abbr`; warn if 0 players |
| P0-5 | Rerank ignores final-portfolio exposure | `sim_rerank.py:178-207` | Greedy cap on the selected 150 |
| P0-6 | Docs tell the broken swap path | `GPP-WORKFLOW.md:88-98` | Rewrite late-swap runbook (2026; `JAX` not `JAC`) |
| P0-7 | Pipe stacks / AND too many stacks | `parse_stack_rule` | Split `\|` or raise a clear error |
| P0-8 | NaN spread → 75% pass rate | `volume.py:119-128,227-228` | Raise if spread/total null |

### P1 — after Sunday if time, else next week

| ID | Issue | Fix |
|----|-------|-----|
| P1-1 | Validate skips salary-cap check | Pass `players_csv=normalized_csv` |
| P1-2 | No projection-coverage print | Print empty `fd_projection` names |
| P1-3 | New-team QB / rookie RB can project 0 | Starter override / rookie floor (or `--lock` tonight) |
| P1-4 | $59,400 min salary not on `run` CLI | Expose `--min-salary` |
| P1-5 | Classic stack composition untested | pydfs integration asserts |
| P1-6 | Late-swap tests too thin | Multi-lineup 1 p.m./4:25 fixture |
| P1-7 | Open-Meteo one timeout fails fetch | Per-game try/except |
| P1-8 | Grok research CSV ingest | After Sunday; manual locks tonight |
| P1-9 | `simulate.seed` missing | Set in GPP yaml |
| P1-10 | DST join key vs D | Canonicalize D/DEF/DST |
| P1-11 | LA vs LAR pace lookup | Normalize vegas teams |
| P1-12 | pydfs `total_players` deprecation | Use `player_pool.total_players` |
| P1-13 | GPP-WORKFLOW still shows 2025 | Update examples |

## Overall

**SHIP-WITH-FIXES.** Do not treat the current tree as late-swap ready. Do not fetch on the 1 Sep cache. Patch P0, then build lineups from a **new** FanDuel CSV.

Reports: `reports/audit/cursor-kimi.md`, `reports/audit/cursor-gptsol.md`, Grok log in terminal 112545.

## Follow-up after first implement + late auditors

First implement (Grok CLI via `route-task`, 2026-09-12T16:24Z) covered the original P0/P1 SIP. Opus and Flash then reproduced two more tonight blockers that were not in that SIP.

| ID | Issue | Status after this follow-up |
|----|-------|-----------------------------|
| P0-Q | pydfs drops every non-empty Injury Indicator, including `Q` | `with_injured=True` after load; lock error is a ValueError; pool census prints |
| P0-spread | nflverse `spread_line` is **positive when home is favored** | Negate `spread_line` at extract; internal `spread` stays betting convention |
| P0-swap-abort | One failed `optimize_lineups(all)` aborts the file | Rebuild one lineup at a time; keep original on failure |
| P0-validate | Exposure cap can write <150 then validate fails | Validate allows fewer than requested and warns |
| P0-candidates | 2000 candidates ~35 min | GPP profile default is now 500; CLI `--candidates` no longer overrides yaml unless set |

Tonight still needs a **new** FanDuel CSV, `fetch --force`, live BUF@HOU confirmation, and operator upload only.
