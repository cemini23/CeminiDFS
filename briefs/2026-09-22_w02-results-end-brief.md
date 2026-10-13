# Week 2 FanDuel Main results — end brief (2026-09-20)

**Mode:** brief-plan. Jev gate is in this file.  
**Question:** What did the Main lineups do, and what must the next audit refuse to invent?

Jev (`jev_verify` + `jev_find`, 2026-09-22) checked the recap against `lineup_totals.csv`, `scores.csv`, `tool-gaps.md`, and `runs/2026_week_2/lineups.csv`.

## Jev gate (required)

Do not score a cheap dart or a high-salary player from `scores.csv`.

1. **Blank seats (Jev rank 0.89).** History shows lineup totals only. Every `projected`, `actual`, and `delta` cell is blank. A 142.98 total does not name which seat scored the points.
2. **Our file is not the History set (Jev contradicted, confidence 1.0).** `runs/2026_week_2/lineups.csv` has 15 rows. History has 17 unique Main lineups. Our file has Javonte Williams, Jaylen Warren, Jadarian Price, Gunnar Helm, and Garrett Wilson. It does not have Tyler Warren, Jameson Williams, or Michael Wilson.
3. **Club labels in `scores.csv` are not Week 2 facts (Jev: review, confidence 0.35).** The recap says Price, Helm, Warren, and Williams are best-effort expansions. Do not treat Cousins as Atlanta, Kalif Raymond as Detroit, Stefon Diggs as Houston, Wan'Dale Robinson as the Giants, the L01 Warren as Tyler Warren of Indianapolis, or the Williams flex as Jameson Williams of Detroit.

`tool-gaps.md` stays `do_not_auto_apply=true`. Do not retune projections, ownership, defense, or stacks from this one Sunday.

## What the totals support

Source: FanDuel History lineup totals in the 2026-09-20 recap. Ranks are not on the cards. Do not invent them.

| Lineup | Total | Won | Cash |
|--------|------:|----:|:----:|
| L01 Purdy, Hall, Price, Olave, Smith-Njigba, Washington, Helm, Warren, Patriots | 142.98 | $15.60 | Y |
| L02 Purdy, Jeanty, Hall, Metcalf, Smith-Njigba, Concepcion Jr., Helm, Hampton, Jets | 124.18 | $0.50 | Y |
| L03 Purdy, Jeanty, Hall, Metcalf, Smith-Njigba, Robinson, Mayer, Hampton, Titans | 122.88 | $10.50 | Y |
| L04 Purdy, Jeanty, Hall, Metcalf, Smith-Njigba, Williams, Helm, Hampton, Jets | 122.88 | $10.00 | Y |
| L05 Young, Robinson, Henry, Coker, Raymond, Diggs, McBride, Williams, Titans | 113.78 | $10.22 | Y |
| L06 Shough, Swift, Warren, Lamb, Olave, Washington, Goedert, Judkins, Eagles | 112.28 | $0.50 | Y |
| L07 Shough, Swift, Price, Lamb, Olave, Golden, Goedert, Warren, Buccaneers | 109.58 | $0 | N |
| L16 Cousins, Irving, Achane, Jefferson, Diggs, Robinson, Mayer, Barkley, Cardinals | 78.92 | $0 | N |
| L17 Cousins, Irving, Achane, Metcalf, Jefferson, Concepcion Jr., Mayer, Hampton, Commanders | 78.22 | $0 | N |

- Six cashed: L01, L02, L03, L04, L05, L06. Eleven did not.
- Screenshot Won on those six cards sums to **$47.32**.
- The fee column on the 17 unique cards sums to **$78.80** if each card is charged once. Do not multiply by the entries column. This brief does not state a net.
- Best card: L01 **142.98**, won **$15.60**. Olave is on that card.
- Worst cards: L17 **78.22** and L16 **78.92**. Both list Cousins, Irving, and Achane. Both won $0.
- Purdy holds the top four totals and four of the six cashes. Hurts (96.56), Daniels (84.54), Lawrence (82.76), and every Cousins card missed. Young cashed once (L05, 113.78).
- Close miss: L07 **109.58**, won $0.

## What this brief does not say

- Which cheap player boomed inside a cashed lineup.
- Which high-salary player busted inside a missed lineup.
- That a club label in `scores.csv` is the Week 2 team.
- That the 15-lineup solver file equals the 17 History cards. Fees include $0.25, $5.00, $5.25, and $5.30. That is a wider set than the 15 × $5 upload.

## Next audit rule

Use lineup totals and cash results. Refuse seat-level points and the guessed clubs. Map a History card to `lineups.csv` only when the nine names match. Leave Price, Helm, Warren, and Williams unresolved when the card shows a last name only.
