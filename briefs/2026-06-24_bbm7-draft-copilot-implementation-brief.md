# CeminiBBM Draft Copilot — Implementation Brief

**Date:** 2026-06-24 (K128)  
**Build workspace:** `CeminiDFS` (this repo)  
**Strategy source of truth:** `@gambling-wiki` (read-only reference for updates)  
**Status:** Research complete → implement here

This document is **self-contained**. You should not need to open gambling-wiki to build Phase 0–2.

---

## 1. Product definition

**CeminiBBM Draft Copilot** — a local, ToS-safe live draft assistant for Underdog **Best Ball Mania VII** (150-max portfolio).

| Build | Buy / integrate | Never build |
|-------|-----------------|-------------|
| Portfolio ledger + exposure caps | BBTB ADP (weekly manual CSV) | Contest sims (ETR/Solver) |
| Archetype router (A–E) | Optional Stokastic/ETR projection CSV | Live ADP scraper |
| Wiki rule engine (bye/stack/TE cluster) | Optional BBTB Pro (combo cross-check) | Auto-pick / auto-click |
| CLI recommender (second screen) | Optional THE SOLVER (overlay UX only) | Underdog API client |

**Core insight:** Snake draft = sequential state machine + constraint filters + scored ranking. **Not** pydfs LP (that's FanDuel MME).

---

## 2. Repo layout (implement in CeminiDFS)

```
CeminiDFS/
  src/ceminidfs/
    bbm/                          # NEW package — BBM draft copilot
      __init__.py
      cli.py                      # `ceminidfs bbm draft` entry
      config.py                   # rules constants (embedded from brief)
      models.py                   # Player, Roster, DraftState dataclasses
      registry.py                 # load/merge player registry
      ledger.py                   # SQLite exposure + combos
      schedule.py                 # bye weeks, W17 matchups
      validator.py                # bye/stack/cap hard constraints
      archetype.py                # router + pivot state machine
      recommender.py              # scoring engine
      normalize_adp.py            # BBTB/FantasyPros/Underdog CSV → registry
      reconcile.py                # Underdog exposure CSV vs ledger
      audit.py                    # post-draft roster audit
      backtest.py                 # BBM III replay harness
      draft_card.py               # markdown cheat sheet generator
    data/                         # nflverse fetch (reuse)
    models/scoring.py             # ADD half-PPR season scoring adapter
  data/bbm/                       # gitignore — runtime data
    bbm7.db                       # SQLite ledger
    player_registry.json
    player_overrides.csv
    adp_snapshots/                # weekly CSV archives
  briefs/
    2026-06-24_bbm7-draft-copilot-implementation-brief.md  # this file
  tests/bbm/                      # unit + replay tests
```

**CLI commands (target):**
```bash
ceminidfs bbm refresh-adp --csv path/to/bbtb.csv
ceminidfs bbm draft-card --out briefs/bbm7-draft-card-2026-06-24.md
ceminidfs bbm draft --slot 4                    # interactive REPL
ceminidfs bbm audit --draft-id local-001
ceminidfs bbm reconcile --csv underdog_exposure.csv
ceminidfs bbm backtest --sample 100             # BBM III replay
```

**New dependencies (add to `pyproject.toml`):**
```toml
# [project.optional-dependencies]
bbm = ["rapidfuzz>=3.0", "nflreadpy>=0.1.0", "typer>=0.12"]
```
Reuse existing: `pandas`, `pyyaml`, `nflreadpy` (data extra).

---

## 3. Tournament & platform facts (embedded)

### BBM7 format [CONFIRMED]

| Field | Value |
|-------|-------|
| Platform | Underdog Fantasy |
| Entry | $25 × max **150** = **$3,750** |
| Draft | 12-team **snake**, **18 rounds** |
| Scoring | **Half-PPR** (0.5/rec, 0.1 rush/rec yd, 4 pass TD, 6 rush/rec TD, -1 INT, -2 fumble) |
| Lineup | Auto-optimal weekly; no waivers/trades |
| Final min-cash | $3,750 (ranks 301–667) |

**Roster slots (18 total):** 1 QB + 2 RB + 3 WR + 1 TE + 1 Flex + 10 bench (tool targets **3 QB / 4–5 RB / 6–7 WR / 2–3 TE** shell).

### Underdog draft room [CONFIRMED — tool builder research 2026-06-24]

| Fact | Implication |
|------|-------------|
| Fast draft **30s** clock | CLI: ≤3 keystrokes per pick (`p Burrow`) |
| Slow draft starts **8h**, compresses toward kickoff | Must `resume` draft by `draft_id` |
| **Autopilot after 2 missed** slow picks | Warn operator; never rely on autopilot |
| Auto-pick order: queue → custom ranks → ADP | Keep 5+ queue players aligned with archetype |
| **No public draft API** | Manual state sync Phase 1 |
| Exposure CSV: desktop only, **once/day**, post-draft | `record-draft` after each completion; daily reconcile |
| In-app ADP: **48h rolling**, daily refresh | External BBTB lags 12–36h |
| ToS bans scraping/auto-pick | CLI MVP default |

Sources: Underdog help center, legal.underdogfantasy.com, fantasylife.com exposure CSV guides.

---

## 4. Strategy constants (embed in `config.py`)

### 4.1 Portfolio targets (150 entries)

**Timing split:**

| Window | Count | % |
|--------|-------|---|
| May–June | 38 | 25% |
| Jul–mid Aug | 82 | 55% |
| Late Aug–Sep | 30 | 20% |

**Archetype split:**

| Code | Name | Count | % |
|------|------|-------|---|
| A | RB-forward (4for4) | 53 | 35% |
| B | Hero RB + WR | 38 | 25% |
| C | Stack-heavy | 30 | 20% |
| D | Zero RB | 23 | 15% |
| E | Contrarian / CLV-only | 6 | 4% |

**Timing × archetype matrix:**

```
           May-Jun  Jul-Aug  Late Aug   TOTAL
A RB-fwd      8      30       15        53
B Hero       10      22        6        38
C Stack       6      18        6        30
D Zero       10       8        5        23
E Contrarian  4       4        2         6
TOTAL        38      82       30       150
```

**Archetype router:** assign draft to archetype furthest below target ratio. User override: `--archetype D`.

### 4.2 Exposure caps (150 entries)

| Tier | Max % | Max count | Examples |
|------|-------|-----------|----------|
| elite | 35% | 53 | Chase, Gibbs, Bijan, ARSB |
| stack_core | 25% | 38 | Burrow, Hurts, Daniels |
| mid_target | 20% | 30 | Ferguson, Strange, Goedert, Lawrence |
| late_lottery | 15% | 23 | Shough, Gadsden, rookie WRs |
| single_dart | 10% | 15 | R17–18 one-offs |

**Combo pair cap:** 25% for defined stack pairs (Burrow+Chase, Hurts+Brown, etc.).

**Enforcement:**
- `exposure >= cap` → multiplier **0.0** (hard prune)
- `exposure >= cap - 5%` → linear soft brake to 0
- Archetype **E** ignores caps

**In-progress drafts:** count at **50% weight** for exposure preview.

### 4.3 Bye week calendar 2026 [CONFIRMED]

Map team abbrev → bye week in `schedule.py`:

| Week | Teams |
|------|-------|
| 5 | KC, CAR |
| 6 | CIN, MIA, DET, MIN |
| 7 | BUF, LAC, WAS, JAX |
| 8 | SF, NYG, NO, HOU |
| 9 | PIT, TEN |
| 10 | CHI, DEN, TB, PHI |
| 11 | CLE, ATL, GB, NE, LAR, SEA |
| 13 | IND, NYJ, LV, BAL |
| 14 | ARI, DAL |

**Hard constraints (validator.py):**
1. All **3 QBs** must have **distinct bye weeks**
2. **3-TE builds:** all TEs distinct bye
3. **≤7 players** on same bye (teammates exempt)
4. **Never 10+** same bye
5. **≤4 players** same NFL team (5 only Archetype C)

### 4.4 Round-band rules

| Rounds | Target | Strong BUY lanes | FADE |
|--------|--------|------------------|------|
| R1–2 | Elite RB/WR | Gibbs, Bijan, Taylor, Henry, Jeanty, Achane, Chase, Nacua, ARSB, Lamb | Bowers, McBride (TE R2) |
| R3–5 | RB2 / WR run | Chase Brown, Hampton, Kyren, Breece; JSN, McMillan, Egbuka | Josh Allen R3 |
| R6–7 | QB1 + WR depth | Hurts, Daniels, Burrow | Ambiguous WR3 in run-heavy O |
| R8–10 | QB2, depth | Lawrence, Purdy, Mahomes, Mayfield | Same-bye QBs as QB1 |
| R11–13 | **TE cluster**, QB3 | Kelce, Ferguson, Andrews, Goedert, Gadsden, Strange | Middle-tier TE R8–10 |
| R14–18 | Late QB/TE/RB lottery | Johnson, Dulcich; Stevenson/Swift/Pollard; rookie WRs | Tyreek Hill, Aiyuk |

**Default shell:** 3 QB · 4–5 RB · 6–7 WR · 2–3 TE

### 4.5 Archetype draft scripts

**A — RB-forward:**
```
R1–2: RB-RB or RB-WR (elite RB)
R3–5: 2–3 WR
R6: QB1 (Hurts/Daniels/Burrow)
R8–10: QB2 + fill
R11–13: TE TE TE
R14–18: QB3, RB depth, lottery
```

**B — Hero RB:**
```
R1: Elite WR
R2: Hero RB (Henry/Jeanty/Taylor)
R3–7: WR heavy (5 WR by R7)
R8–10: QB1 + QB2
R11–13: TE cluster
```

**C — Stack-heavy:**
```
R1–3: Stack anchor (Chase/McConkey)
R4–8: Complete 3–4 man stack
R6–10: Stack QB + bring-backs
R11–13: TE (stack-aligned)
Cap 4 same team (5 if Archetype C + late dart)
```

**D — Zero RB:**
```
R1–6: 0 RB — WR WR WR + elite TE/QB
R7–9: Stevenson/Swift/Pollard/Skattebo
R11–13: TE cluster
R14–18: RB lottery
```

**E — Contrarian:** pure CLV; no structural forcing.

### 4.6 Pivot state machine

When board blocks primary archetype, transition once per draft:

| Primary | Fallback A | Fallback B | Trigger |
|---------|------------|------------|---------|
| D Zero RB | B Hero RB | A RB-forward | 0 RB at R6 and elite RB tier empty |
| C Stack-heavy | A RB-forward | E CLV | Anchor gone + stack lane dead |
| A RB-forward | B Hero RB | — | 0 RB at R5 in RB run |

Emit: `WARN: pivot D→B (Zero RB blocked)`.

### 4.7 Scoring engine (recommender.py)

```python
clv_delta = pick_num - player.adp
clv_bonus = clv_delta * clv_weight(date)  # May 1.5, Jul 1.2, Aug 0.8

score = (player.projection_pts + clv_bonus) * stack_mult * archetype_mult * exposure_mult

# stack_mult: +0.30 QB stack, +0.15 pass stack, +0.10 W17 bring-back (R10+)
# cap stack_mult at 1.4; require clv_delta >= 3 to stack-reach

# Tie-breakers:
# 1. stack / W17 bring-back
# 2. clv_delta >= 3
# 3. positive drift (rookies May-Jun)
# 4. furthest below exposure cap
# 5. route/touch share (F6P filter)
```

**Signal overrides:** `signal=FADE` or `injury_fade=true` → exclude entirely.

### 4.8 Priority BUY / FADE (seed registry — refresh ADP weekly)

**BUY TE cluster:** Kelce, Ferguson, Andrews, Goedert, Gadsden, Strange, Okonkwo, Juwan Johnson, Dulcich  
**BUY QB:** Hurts, Daniels, Burrow, Lawrence, Purdy, Stroud, Shough, Young (late)  
**BUY RB early:** Gibbs, Bijan, Taylor, Henry, Chase Brown, Achane, Jeanty  
**BUY WR:** Chase, Nacua, ARSB, JSN, McMillan, Egbuka  
**BUY rookie WR (May–Jun):** Cooper, Boston, Concepcion, Branch, Hurst  
**FADE:** Allen R3, Bowers/McBride R2, Tyreek Hill, Aiyuk, Bucky Irving

*ADP values in gambling-wiki `bbm7-adp-delta-tracker.md` dated 2026-06-18 — replace on weekly refresh.*

---

## 5. Data schemas

### 5.1 Player registry (`data/bbm/player_registry.json`)

```json
{
  "meta": { "updated": "2026-06-24", "adp_source": "bbtb", "strategy_version": "2026-06-18" },
  "players": [
    {
      "player_id": "gsis:00-0033873",
      "name": "Travis Kelce",
      "merge_name": "travis kelce",
      "position": "TE",
      "team": "KC",
      "bye_week": 5,
      "adp": 120.4,
      "strategy_rank": 110,
      "projection_pts": 131.5,
      "signal": "BUY",
      "tier": "mid_target",
      "exposure_cap_pct": 0.20,
      "drift_coeff": 0.0,
      "injury_fade": false,
      "notes": "TE cluster anchor"
    }
  ]
}
```

### 5.2 SQLite (`data/bbm/bbm7.db`)

```sql
CREATE TABLE players_dim (
  player_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  merge_name TEXT,
  team TEXT,
  position TEXT,
  bye_week INTEGER,
  tier TEXT,
  cap_pct REAL
);

CREATE TABLE drafts (
  draft_id TEXT PRIMARY KEY,
  draft_date TEXT,
  slot INTEGER,
  archetype TEXT,
  status TEXT CHECK(status IN ('in_progress','complete')),
  underdog_entry_id TEXT
);

CREATE TABLE picks (
  draft_id TEXT REFERENCES drafts(draft_id),
  round INTEGER,
  pick_num INTEGER,
  player_id TEXT REFERENCES players_dim(player_id),
  PRIMARY KEY (draft_id, round)
);

CREATE TABLE combo_pairs (
  player_a TEXT,
  player_b TEXT,
  cap_pct REAL DEFAULT 0.25,
  PRIMARY KEY (player_a, player_b)
);
```

Materialized views or Python helpers: `exposure_pct(player_id)`, `combo_pct(a,b)`.

### 5.3 Name normalization pipeline

1. Load nflverse `import_ids()` / DynastyProcess player IDs
2. Normalize: lowercase, strip suffixes (Jr, III), punctuation
3. Merge BBTB ADP CSV on `merge_name`
4. RapidFuzz fallback for unmatched (threshold 90); queue for `player_overrides.csv`
5. Manual overrides win

**Spike 1 acceptance:** <5% unmatched on top-240 ADP.

### 5.4 Underdog exposure CSV (tolerant parser)

Expected columns (alias map — verify in Spike 2):
- `Player`, `Position`, `Team`, `ADP`, `Times Drafted`, `Exposure %`, `Total Entry Fees`

Header aliases: `Draft %`, `Exposure`, `Pos`, etc.

---

## 6. CLI REPL spec (Phase 1 MVP)

**Startup:**
```
$ ceminidfs bbm draft --slot 4
Archetype: B (Hero RB) — portfolio gap +12%
Round 1, Pick 4 — top 3:
  1. Ja'Marr Chase WR CIN  BUY  exp 22%  stack —
  2. Puka Nacua WR LAR     BUY  exp 18%
  3. Amon-Ra St. Brown DET BUY  exp 31%  WARN near cap
> p Chase
```

**Commands:**

| Command | Action |
|---------|--------|
| `p <name>` | Record your pick; advance round |
| `t <name>` | Mark player taken by room (not you) |
| `taken <name>` | Alias for `t` |
| `undo` | Undo last pick/taken |
| `sync` | Paste multi-line board snapshot → parse |
| `exp` | Show top exposure warnings |
| `archetype X` | Force archetype |
| `quit` | Save in_progress draft state |

**Output rules:** max 3 recommendations; one-line WARN for exposure/bye; recompute <200ms.

---

## 7. CeminiDFS reuse map

| Existing module | BBM use | Change |
|-----------------|---------|--------|
| `ceminidfs/data/fetch.py` | Rosters, schedules | None |
| `ceminidfs/data/rosters.py` | Bye weeks, team map | None |
| `ceminidfs/models/implied_totals.py` | W17 stack tiebreaker | None |
| `ceminidfs/models/scoring.py` | Season half-PPR projection | **Add** `score_half_ppr_season()` — 0.5 PPR, no DK bonuses |
| `ceminidfs/export/normalize.py` | CSV column patterns | Reference for ADP normalizer |

**Half-PPR adapter (scoring.py):**
```python
# reception: 0.5 (not 1.0 FanDuel full-PPR)
# no 100/300 yard bonuses
# season total projection, not single-slate
```

---

## 8. Validation & backtesting

**Before live $25 entries:**

1. Download [BBM III pick-by-pick data](https://underdognetwork.com/football/best-ball-research/best-ball-mania-iii-downloadable-pick-by-pick-data)
2. Replay N draft rooms: at each pick, run recommender → compare to actual pick ADP
3. Metrics: structural rule pass rate, median CLV delta, latency p99 <200ms
4. Reference: [fantasydatapros/best-ball-data-bowl](https://github.com/fantasydatapros/best-ball-data-bowl)

**Manual:** 5 free slow drafts with draft-card-only, then with full CLI.

---

## 9. Implementation phases & acceptance criteria

### Phase 0 — Foundation
- [ ] `src/ceminidfs/bbm/` package scaffold
- [ ] `config.py` with all constants from §4
- [ ] Seed `player_registry.json` top-240 from BUY/FADE tables
- [ ] `draft_card.py` → markdown cheat sheet
- [ ] `normalize_adp.py` spike + `player_overrides.csv` template

**Done when:** draft card generates; registry loads; Spike 1 <5% unmatched.

### Phase 1a — Ledger + REPL
- [ ] SQLite schema + migrations
- [ ] `cli.py` draft REPL (`p`, `t`, `undo`)
- [ ] In-progress draft resume

**Done when:** complete mock 18-round draft logged locally.

### Phase 1b — Recommender
- [ ] `validator.py` all hard constraints
- [ ] `archetype.py` router + pivot
- [ ] `recommender.py` scoring + top-3 output
- [ ] Exposure pruning

**Done when:** each archetype mock draft produces sensible top-3; audit passes.

### Phase 1c — Audit + reconcile
- [ ] `audit.py` post-draft checklist + CLV estimate
- [ ] `reconcile.py` Underdog exposure CSV diff

**Done when:** weekly CSV reconcile flags drift.

### Phase 2 — Data pipeline
- [ ] Weekly `bbm refresh-adp` one-liner
- [ ] Optional CeminiDFS projection merge column
- [ ] `backtest.py` BBM III replay harness

### Phase 3 — Extension (optional, post-July)
- [ ] MV3 read-only overlay; manual trigger; aria-label DOM crawl
- [ ] Fork pattern: [draft-co-pilot](https://github.com/howrealizdat/draft-co-pilot)

---

## 10. Operator SOP

**Session start:**
```bash
ceminidfs bbm draft-card --out briefs/bbm7-draft-card-$(date +%F).md
# Review archetype gaps in CLI output
```

**Per draft (desktop + second monitor):**
1. Underdog draft room on left
2. `ceminidfs bbm draft --slot N` on right
3. Read top-3 → pick in Underdog → `p Name`
4. After each room pick not yours: `t Name`

**After draft:**
```bash
ceminidfs bbm audit --draft-id <id>
```

**Daily (if drafting):** record each completion immediately.

**Weekly:**
```bash
ceminidfs bbm refresh-adp --csv research/bbtb-adp-YYYY-MM-DD.csv
# Email Underdog exposure CSV (desktop, once/day)
ceminidfs bbm reconcile --csv ~/Downloads/underdog_exposure.csv
```

**Never:** autopilot in slow drafts; auto-pick; scrape Underdog.

---

## 11. Pre-build spikes (run first)

| # | Spike | Pass criteria |
|---|-------|---------------|
| 1 | BBTB ADP → nflverse merge | <5% unmatched top-240 |
| 2 | Underdog exposure CSV headers | Tolerant parser works |
| 3 | Recommender stub latency | p99 <200ms |
| 4 | Mock slow draft w/ draft card | Operator faster than gut |
| 5 | Exposure policy | Hard 100%, soft 95–100% documented |
| 6 | Half-PPR projection column | Sanity vs Stokastic if available |

---

## 12. Open decisions (operator)

1. **Projection source:** CeminiDFS half-PPR vs Stokastic benchmark vs ranks-only (recommend: ranks + optional CeminiDFS column)
2. **THE SOLVER sub?** Optional overlay; our ledger stays source of truth
3. **BBTB Pro?** Optional combo cross-check until Phase 3
4. **July scope:** CLI + draft card only (recommended)

---

## 13. Cross-repo references (strategy updates only)

When ADP/strategy changes, update gambling-wiki then re-seed registry:

| Topic | Gambling-wiki path |
|-------|-------------------|
| ADP BUY/FADE | `wiki/concepts/bbm7-adp-delta-tracker.md` |
| Portfolio matrix | `wiki/concepts/bbm7-portfolio-construction.md` |
| Bye / W17 | `wiki/concepts/bbm7-playoff-week-construction.md` |
| Platform mechanics | `wiki/entities/platforms/underdog-fantasy.md` |
| Tournament rules | `wiki/entities/tournaments/best-ball-mania-vii.md` |
| Research archive | `briefs/2026-06-24_bbm7-live-draft-tool-master-plan.md` |
| Challenges | `briefs/2026-06-24_bbm7-challenges-and-solutions.md` |

**Do not duplicate strategy edits in two repos.** Implementation lives here; strategy narrative lives in gambling-wiki.

---

## 14. Success criteria

| Milestone | Metric |
|-----------|--------|
| MVP | One live Underdog draft via CLI; roster passes audit |
| Season | 50+ drafts logged; caps enforced; weekly refresh ≤5 min |
| Full | Optional extension; 150 entries without spreadsheet |

---

**Start here:** Phase 0 scaffold + Spike 1 (name normalization).
