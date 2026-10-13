# Review reports (human gate)

This sheet names the review flags and the report files. Flags default off.

The operator reads the CSV files. Then the operator may `--exclude`, `--max-exposure`, or `late-swap` on a later solve.
The agent does not Enter FanDuel. Do not auto-apply a report.

| Flag | Artifact | Operator next step |
|------|----------|--------------------|
| `--flag-wr-triples` | `stack_fragility_report.csv` | Read the same-game WR triples. May later opt in to PlayersGroup `max_from_group=1`. |
| `--late-swap-audit` | `late_swap_alert_report.csv` | Read the Q and D alerts. Confirm a change. Then use the existing `late-swap`. |
| `--ownership-fade-report` | `leverage_fade_matrix.csv` | Read the leverage. May later pass `--max-exposure` or `--exclude`. |
| `--flag-duplicate-cores` | `duplicate_core_report.csv` | Read a QB and the same two RB slots on more than 2 lineups. Do not drop a lineup. |
| `--dart-ceiling-report` | `dart_ceiling_rank.csv` | Read players with salary at or below 5500. The rank uses the existing mean. A blank ceiling means the file had no ceiling. |
| `--flag-qb-starter` | `qb_starter_report.csv` | Read a rostered QB who is not a confirmed starter, whose snap share is below 90%, or whose starter change is inside 72 hours. |
| `--flag-stack-concentration` | `stack_concentration_report.csv` | Read each QB stack partner. The row shows the prior-3-week target share and aDOT. |
| `--flag-correlated-pairs` | `correlated_pair_report.csv` | Read a TE and DST pair that is on more than one lineup. |
| `--defense-context-report` | `defense_context_report.csv` | Read opponent implied total, sack rate, and turnover rate beside the pass multiplier. Fumbles lost stay the fumble recovery input. |
| `--projection-bands` | `projection_bands.csv` | Read P85 and P15 beside the projection. A cheap RB or WR with P15 below 1 is flagged. The projection stays the same. |
| weather path | `environment.csv` and `weather.parquet` | Read `prelock_fade_flag` before lock. A blank `pass_rate_delta` means do not attribute a miss to weather. |
| weather roof | `roof_flag` beside `game_total` | Read the roof. The flag is information only. It does not boost a projection. |

## Human gate

1. The operator reads each CSV.
2. The operator decides. The operator may then `--exclude`, `--max-exposure`, or `late-swap`.
3. The agent does not Enter FanDuel.
4. Do not auto-apply. A report does not change a lineup by itself.

## Jev pre-lock gate (mandatory before upload)

The `jev` server is on the project Cursor MCP (`.cursor/mcp.json`). The gate
runs from the command line, not from Cursor Tools. Run it after the build and
before the 1:00 p.m. ET lock.

```bash
ceminidfs review \
  --lineups runs/2026_week_5/lineups.csv \
  --players runs/2026_week_5/normalized_players.csv \
  --out runs/2026_week_5 \
  --jev --jev-date 2026-10-11
```

The gate writes `jev_gate_report.csv` and prints a one-line summary. It reads
the lineup file and the players file. It **does not read the scratch** CSV
(`--research-csv`). Pass the scratch CSV to `optimize` or `run`, not to
`review`.

| Column | Meaning |
|--------|---------|
| `player` | The roster name, or `(status_packet)`, or `(recap)` |
| `question` | The one atomic question that was asked |
| `primitive` | `verify` (Noul), `screen` (Score), or `find` (Choice) |
| `result` | The verdict, the screen action, or the chosen alternative |
| `confidence` | The Jev confidence, 0 to 1 |
| `action` | `pass`, `flag`, `review`, or `block` |
| `evidence_ref` | Which document the answer rests on |

### The five checks

1. **Status (Noul).** One atomic question for every rostered Q/D player, and
   every player at or above the exposure cap:
   `Is <player> expected to be active for <team> in <game> on <date>?`
2. **QB starter (Noul).** Every rostered QB: `Is <player> the confirmed
   starter for <team>?` This feeds `qb_starter_report.csv`.
3. **Injection screen (Score).** The status packet is screened before it is
   used. A `block` stops the gate.
4. **Late swap (Choice).** Every row of `late_swap_alert_report.csv` gets a
   ranked legal alternative. The gate marks. The operator swaps.
5. **Cash claim (Noul).** Post-slate only. Verify a recap cash count against a
   standings screenshot. **No screenshot means the claim stays UNKNOWN.**

### Thresholds live in our code, not in Jev

| Condition | Action |
|-----------|--------|
| verdict `verified` and confidence >= 0.80 | `pass` |
| verdict `contradicted` and confidence >= 0.80 | `flag` (candidate inactive) |
| verdict `unsupported` | `review` |
| confidence < 0.80 | `review` (route to the operator) |
| screen says `block` | `block` |

**Only a contradicted claim can flag.** `unsupported` means the evidence does
not address the claim. That is silence. A gate that flags every player the
packet is quiet about is worse than no gate.

The Week 5 live run shows why this matters. The QBs returned `unsupported`,
because the status packet holds no depth-chart data. Flagging them would have
accused Rodgers, Goff, Burrow, and Watson of not being starters.

### The evidence sets the ceiling

A `Q` tag alone is weak evidence. Live, Jev contradicted "expected to be
active" for every Questionable player, but never above 0.28 confidence. All of
them landed in `review`. A `flag` needs evidence that actually contradicts the
claim, such as a real inactive report. Pass one with `--jev-status FILE`.

### Fail closed

A missing key, a missing launcher, a network error, or a malformed response
**blocks the gate and exits non-zero**. The gate never reads silence as a pass.
The report is still written, with `action=block` and the reason.

### Hard rules

- The gate **marks**. It does not rewrite a lineup, a projection, an ownership
  number, or a pydfs input.
- Never arm an action from a score. No automatic exclude. No automatic swap.
- Player names and public status strings only. No PII. No vault data.
- Do not replace `mcp-jev`. Never `npx github:`.
- No scrape. No Enter.

### Offline run

`--jev-fixture FILE` replays recorded responses and needs no key and no
network. CI uses this path.

## Corrections

- Do not retune CIN, Chase, or weather from Week 1. One sample is not a retune.
- SoFi stays `semi_open`. SoFi is not a dome.

Canon: `briefs/2026-09-15_gemini-dfs-improve.md` (KEEP / REJECT, TG01-TG07).
