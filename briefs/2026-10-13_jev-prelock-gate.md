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
| unsupported (the evidence says nothing) | `review` |
| confidence < 0.80 | `review` |
| screen says `block` | `block` |

All 37 Noul questions go in one `verify` call. Jev evaluates questions in
parallel against the same state, so one call holds the whole slate.

## Week 5 run

`ceminidfs review --lineups runs/2026_week_5/lineups.csv --players
runs/2026_week_5/normalized_players.csv --out runs/2026_week_5 --jev`.

```
jev gate: pass=17 flag=0 review=30 block=0 low_confidence=30
```

| Action | Count | What it is |
|--------|------:|------------|
| pass | 17 | the screen row, plus every player the packet supports |
| flag | 0 | no evidence contradicted a claim at 0.80 |
| review | 30 | every Questionable player, every QB, and the 9 late-swap Choice rows |
| block | 0 | |

Jordan Addison was Questionable with a hamstring, was in 38 of 150 lineups,
and scored 0. The gate **routed him to the operator, it did not flag him** —
see "The live run" below for why, and what it would take to flag him.

## Measured effect: no cash impact this week

The counterfactual uses the audit's flagged set — the Questionable players. For
every one, in every lineup, I swapped in the best legal alternative: same game,
same position, healthy.

| Book | Lineups at or above the 134.74 cash line | Median |
|------|-----------------------------------------:|-------:|
| Week 5 as shipped | 30 | 117.78 |
| After every Questionable repaired (best projection) | 29 | 117.99 |
| After every Questionable repaired (best actual, hindsight) | 29 | 117.99 |

**The gate has no cash impact this week.** A blanket repair moves the count by
one, downward. The reason is in the data:

| Questionable player | Mean actual | Lineups with 0 |
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

## The live run

The live gate ran on 2026-10-13 against `api.typesafe.ai` (model
`jev-latest`), from a shell with real egress. The first live run found a defect.

### Defect: silence was read as an accusation

Every rostered QB came back `unsupported noul=0.00` with high confidence. The
status packet holds no depth-chart data, so Jev correctly answered "the
evidence says nothing". The gate mapped a low noul and a high confidence to
`flag`, so it accused nine QBs of not being starters:

```
jev flag: Aaron Rodgers — Aaron Rodgers is the confirmed starter for PIT. [unsupported noul=0.00]
jev flag: Jared Goff — ...            (9 in total)
```

An accusation from silence is worse than no gate. Only a `contradicted` claim
can flag now. `unsupported` routes to the operator.

| Live result | Before the fix | After the fix |
|-------------|---------------:|--------------:|
| pass | 17 | 17 |
| flag | 9 | **0** |
| review | 21 | 30 |

### What the live run says about Week 5

**The gate did not flag Jordan Addison.** Jev returned `contradicted` for him
at noul 0.49 and confidence 0.23. Below the 0.80 floor, the gate routes him to
the operator. That is the specified behavior, and it is the honest result: a
Questionable tag is weak evidence, and Jev said so. Every Questionable player
landed in the same place, at confidence 0.23 to 0.48.

So the gate's measured value this week is a **review list**, not a flag list.
The 30 rows tell the operator where the evidence is thin.

To reach a `flag` the packet must contradict the claim. A real inactive report
does that. Pass one with `--jev-status FILE`. The flag path is covered by
`test_gate_flags_a_player_whose_evidence_contradicts`.

The Choice step is also weak as built. Its candidates are bare player names, so
Jev returned `partial` or `absent` for most rows, with probabilities near 0.5.
It ranks, but it does not decide. That matches its role, and it is not a
reason to trust the ordering.

## Tests and the fixture

The Week 5 fixture is now a **real capture**. `tests/fixtures/jev/week5_gate.json`
holds the verdict, noul, and confidence that the live model returned for all 37
claims and 9 Choice calls. `probabilities.contradicts` and `says_nothing` are
reconstructed, because the CSV report keeps only noul. The gate reads verdict,
`probabilities.supports`, and confidence.

The offline run reproduces the live summary exactly:
`pass=17 flag=0 review=30 block=0 low_confidence=30`.

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
