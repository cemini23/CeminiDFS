# Super audit — Week 1 FanDuel Main results (2026-09-13)

**Mode:** `brief-plan`  
**Question:** How did the 10 × $5 CeminiDFS entries do, and what must ship before Week 2?

## Auditor table

| Slot | Channel | Model | Verdict |
|------|---------|-------|---------|
| Parent | Cursor Grok | this session | **REWORK** |
| 1 | Cursor Task | Claude Opus | **REWORK** (export/entry path) |
| 2 | Cursor Task | GPT-SOL | **REWORK** |
| 3 | Cursor Task | Kimi | **SHIP-PROCESS** (P0s required) |
| 4 | OpenRouter | `tencent/hy3` | **SHIP-PROCESS** |
| 5 | OpenRouter | `qwen/qwen3-235b-a22b-2507` (HY3 price band) | **REWORK** |
| 6 | DeepSeek API | `deepseek-flash` (V4.1 Flash) | **REWORK** |
| 7 | Grok CLI | `--reasoning-effort xhigh` | **SHIP-PROCESS** |
| 8 | OpenCode | `muse-spark-1.3-contributor-free` | **REWORK** |

Pack: `reports/audit/pack-week1-recap/` (gitignored). Recap in git: `briefs/2026-09-14_week1-fd-recap/`. Parent write-up: `briefs/2026-09-14_week1-cursor-grok-audit.md`. Grok CLI file: `reports/audit/premium-week1-recap/grok-cli.md`.

## Consensus

**Overall: REWORK the export and Sunday process. Do not rewrite the projection model from one week.**

Scorecard (CSV1–10 only; History totals in `lineup_totals.csv`):

- Fees **$50**, won **$16.50**, net **−$33.50**, cash **2/10**.
- Best CSV3/L01 **169.96** ($9). Worst CSV5/L14 **91.36** ($0).
- Do not score L03/L08/L11/L12 as optimizer results.

**Went right (all auditors):** GPP spike (Allen + bring-back + Burden/Hutchinson + JAX) is real. Player 30% cap held. Q stayed in the pool so Odunze could be swapped. Agent did not Enter.

**Went wrong (consensus ≥5):** name-only `lineups.csv` failed FanDuel upload; CHI 70% team exposure; Burrow+Chase+Higgins were the two worst; Q swap was manual; CSV ≠ History (extra lineups + L02 FLEX drift).

## Conflicts (resolved)

| Topic | Split | Decision |
|-------|-------|----------|
| Default drop Q players | HY3 / Qwen / Flash want `with_injured=False` | **Keep Q in pool.** Odunze→McConkey cashed L02. Report Q names. Do not auto-exclude. |
| Verdict label | 3 SHIP-PROCESS vs 6 REWORK | **REWORK** means “do not run Week 2 on name-only CSV.” Model stays. |
| Fade CIN / Chase / weather | TG01–TG07 | **Flags and docs only.** `do_not_auto_apply=true`. n=10. |
| DST `del team, opponent` | Kimi unique | P1 report flag this week. Do not retune DST numbers from one Sunday. |
| `--uniques 2` clones | Opus unique | P1 warn when overlap is high. Do not change default in this patch unless tests stay green. |

## Patch order for the implementer

P0: FanDuel `Name (ID)` + ID-only writers; late-swap parse those cells; Q block in the report.  
P1: `--max-team-exposure`; `CHALK-QB-WR-WR` badge; print all lineups when count ≤ 20; GPP-WORKFLOW upload step.  
P2: recap/manifest, ownership leverage note, weather hold.

## Week 2 operator (until code lands)

1. Fresh FanDuel player list + `fetch --force`.
2. Upload `lineups_fanduel_upload.csv`, not `lineups.csv`.
3. Swap or exclude rostered Q yourself before lock.
4. Cut chalk QB+both-WR triples and any team over ~4/10.
5. Score History totals vs the export only. Agent does not Enter.
