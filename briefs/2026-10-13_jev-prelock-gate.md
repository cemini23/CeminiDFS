# Jev pre-lock gate

**Date:** 2026-10-13
**Source:** `Gambling wiki/briefs/week5-audit/AUDIT.md`
**Scope:** one new gate on the pre-lock path. No lineup, projection, or ownership change.

## Why

`docs/REVIEW-REPORTS.md` made Jev optional and ran it on one injury cell. One
cell is not a check. Week 5 shipped Jordan Addison (Questionable, hamstring) in
38 of 150 lineups. He scored 0.

The gate now asks the whole slate, marks every answer, and fails closed.

## What was added

| Piece | Path |
|-------|------|
| Client seam | `src/ceminidfs/integrations/jev.py` |
| Gate and report | `src/ceminidfs/export/jev_gate.py` |
| CLI | `ceminidfs review --jev` |
| Fixtures | `tests/fixtures/jev/`, `tests/fixtures/week5/` |
| Tests | `tests/test_jev_gate.py` |

Five checks, one Jev primitive each.

| # | Check | Primitive | Question |
|---|-------|-----------|----------|
| 1 | Status | Noul (`verify`) | Is `<player>` expected to be active for `<team>` in `<game>` on `<date>`? |
| 2 | QB starter | Noul (`verify`) | Is `<player>` the confirmed starter for `<team>`? |
| 3 | Injection | Score (`screen`) | Is the status packet safe to follow? |
| 4 | Late swap | Choice (`find`) | Which legal alternative replaces `<player>`? |
| 5 | Cash claim | Noul (`verify`) | Does the recap cash count stand on a standings screenshot? |

Thresholds live in `jev_gate.py`, not in Jev.

| Condition | Action |
|-----------|--------|
| supported and confidence >= 0.80 | `pass` |
| contradicted and confidence >= 0.80 | `flag` |
| confidence < 0.80 | `review` |
| screen says `block` | `block` |

All 37 Noul questions go in one `verify` call. Jev evaluates questions in
parallel against the same state, so one call holds the whole slate.

## Week 5 run

`ceminidfs review --lineups runs/2026_week_5/lineups.csv --players
runs/2026_week_5/normalized_players.csv --out runs/2026_week_5 --jev`.

```
jev gate: pass=29 flag=8 review=10 block=0 low_confidence=10
```

| Action | Count | What it is |
|--------|------:|------------|
| pass | 29 | 1 screen row, 20 healthy over-cap players, 12 QBs, minus overlap |
| flag | 8 | Carnell Tate, Rhamondre Stevenson, Ja'Marr Chase, Jaylen Wright, Jordan Addison, Keenan Allen, Alvin Kamara, Ashton Jeanty |
| review | 10 | Tee Higgins at 0.62 confidence, plus 9 late-swap Choice rows |
| block | 0 | |

Jordan Addison is flagged. He was Questionable with a hamstring, was in 38 of
150 lineups, and scored 0.

## Measured effect: no cash impact this week

I measured the counterfactual. For every flagged player in every lineup, I
swapped in the best legal alternative — same game, same position, healthy.

| Book | Lineups at or above the 134.74 cash line | Median |
|------|-----------------------------------------:|-------:|
| Week 5 as shipped | 30 | 117.78 |
| After every flag repaired (best projection) | 29 | 117.99 |
| After every flag repaired (best actual, hindsight) | 29 | 117.99 |

**The gate has no cash impact this week.** A blanket repair moves the count by
one, downward. The reason is in the data:

| Flagged player | Mean actual | Lineups with 0 |
|----------------|------------:|---------------:|
| Ja'Marr Chase | 16.70 | 0 |
| Rhamondre Stevenson | 16.00 | 0 |
| Ashton Jeanty | 9.20 | 0 |
| Keenan Allen | 7.00 | 0 |
| Alvin Kamara | 1.60 | 0 |
| Carnell Tate | 1.10 | 0 |
| Jaylen Wright | 1.10 | 0 |
| Jordan Addison | **0.00** | **38** |

Only Addison did not play. The other seven played and two of them produced.
A `Q` tag is not proof of inactivity, so `flag` means "candidate inactive",
never "remove".

The gate earns its place by covering a failure class, not by rescuing Week 5.
An inactive player at 25% of the book is a loss the operator cannot see in the
projections.

This agrees with the audit: repairing Addison alone changed the cash count by
zero (30 → 30). That 38-lineup cluster topped out at 112.96 against a 134.74
line, so it was already lost.

## Fail closed

Both failure paths block and exit 1. The report is still written.

```
# no key
jev gate BLOCKED: no TypeSafe key. Set TYPESAFE_API_KEY or write ~/.cemini/typesafe-api-key
jev gate: pass=0 flag=0 review=0 block=1 low_confidence=0

# key present, API unreachable
jev gate BLOCKED: jev screen error: Connection error: fetch failed
jev gate: pass=0 flag=0 review=0 block=1 low_confidence=0
```

A missing key, a missing launcher, a timeout, a JSON-RPC error, a tool error,
or a malformed payload all raise. The gate never reads silence as a pass.

## Limitation of this build

The live TypeSafe call did not run on this machine. The sandbox blocks egress
to `api.typesafe.ai`, so every attempt returned `Connection error: fetch
failed`. That failure is the second fail-closed case above.

The Week 5 report above was produced with `--jev-fixture
tests/fixtures/jev/week5_gate.json`. The fixture follows the response shape in
`mcp-jev` `dist/index.js` and the tool README. It is not a captured live
response. The gate logic, the thresholds, the report, and the fail-closed paths
ran for real. The live path is wired and starts correctly — the MCP handshake
against `~/.local/bin/mcp-jev` succeeds.

Run the live gate from a machine with egress to `api.typesafe.ai`:

```bash
ceminidfs review --lineups <book.csv> --players <normalized.csv> --jev
```

## Tests

`tests/test_jev_gate.py` — 25 tests. No key, no network, no subprocess.

- flags Addison, and asks one question per Q/D or over-cap player (25)
- routes the 0.62-confidence answer to the operator
- checks all 12 rostered QBs and sends every claim in one call
- blocks on an injection `block`, and shows no claim reached Jev
- marks the 9 late-swap Choice rows without touching a lineup
- keeps a cash claim UNKNOWN without a standings screenshot
- blocks on: absent key, absent launcher, tool error, malformed payload
- refuses to reuse a recorded answer

The gate writes one file. A test asserts the lineup CSV is byte-identical after
a run.

## Hard rules kept

- The gate marks. It does not rewrite a lineup, a projection, or an ownership
  number.
- No action is armed from a score. No automatic exclude. No automatic swap.
- Player names and public status strings only.
- `mcp-jev` is not replaced. No `npx github:`.
- No scrape. No Enter.
