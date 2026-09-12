# Grok Sunday-afternoon packet overlay — FanDuel Week 1

**Current Grok packet:** `briefs/2026-09-13_grok-sunday-afternoon.md` (copy of `~/Downloads/2026-09-13.md`, compiled Tue Sep 1 ~8:30 p.m. ET).
**Prior packet:** `briefs/2026-09-13_grok-sunday-million-1pm-v1.md` (1 p.m.-only, ~8:18 p.m. ET).
**Our salary run:** contest `133104`, 12 Sunday games, `artifacts/slates/2026_w1_fd_sun.csv` → `runs/2026_week_1/`.
**Packet type:** read-only injury / IR / weather / CSV path. No Grok lineups or projections.

## Diff vs 8:18 p.m. packet

| | v1 (8:18 p.m.) | v2 (8:30 p.m.) |
|---|---|---|
| Sunday Million default | 1 p.m. only (8 games) | **1 p.m. + 4:25** (12 games) |
| 4:25 clubs | Note only | ARI / LAC / MIA / LV / GB / MIN / WAS / PHI fetched |
| IR/PUP/NFI rows | 133 | **194** (133 kept + 61 new) |
| Practice reports | Empty (16 clubs) | Empty (**24 clubs**) |
| Weather | 5 outdoor 1 p.m. sites; Sep 13 unavailable | + Philadelphia; SoFi/Allegiant/U.S. Bank indoor skip |
| SNF / MNF | SNF noted | Both **out** (DAL@NYG, DEN@KC) |

CSV `133104` now **matches** the Grok Sunday-afternoon slate. Do not mix with SNF/MNF.

## Official report vs FanDuel tags

NFL.com Week 1 hub: **“No Injuries Reported”** for all 32 clubs. First practice tables ~Wed Sep 9. Roster reserve is the only official status.

**1 p.m. skill IR (unchanged, still match FD IR):** Jayden Higgins, Tank Dell, Dillon Gabriel, Isiah Pacheco, Devin Neal, Ty Chandler, Trevor Etienne (CAR — not Travis Etienne Jr.).

**New 4:25 skill names vs FD 133104:**

| Player | Official (Grok) | FanDuel 133104 |
|---|---|---|
| James Conner | ARI IR-DFR | $5,400 IR foot |
| Trey Benson | ARI IR | $4,300 IR knee |
| Tip Reiman | ARI Active/PUP | $4,000 NA ankle |
| Dont'e Thornton Jr. | LV IR | $4,600 IR |
| Justin Shorter | LV IR | $4,000 IR |
| Chase Roberts | LV IR | $4,000 IR |
| Savion Williams | GB IR-DFR | $4,500 IR ankle |
| Luke Musgrave | GB Reserve/PUP | $4,200 NA neck |
| Johnny Wilson | PHI IR | $4,300 IR knee |
| Grant Calcaterra | PHI IR-DFR | $4,100 IR back |
| Jeremy McNichols | WAS IR | $4,200 IR quad |
| Josh Jacobs | **Commissioner Exempt** (omitted from Grok IR table) | $7,200 IR Personal |

Jacobs is not in the Grok IR/PUP/NFI table by design. FanDuel already has him IR — keep him out. Laremy Tunsil is WAS IR (OL, not on the FD skill list). Tyler Biadasz is LAC IR (center). Micah Parsons is GB PUP.

FanDuel **Q**, still no official practice row: Chase, Tee Higgins, Kamara, Jeanty. Grok did not copy NFL.com headlines.

## Weather

NWS 7-day grids **stop at Tue Sep 8** (including PHI). No Sep 13 numbers. Indoor skip: Ford Field, **SoFi**, **Allegiant**, U.S. Bank. Retractable HOU/IND: wait for roof. CeminiDFS Open-Meteo Sep 13 rows stay early-model only. SoFi is indoor in this packet (our stadiums file still tags LAC semi-open / weather-exposed).

## Morning-of (primary lock ~11:30 a.m. ET Sep 13; 4:25 locks later)

1. Drop a **new** FanDuel Sunday afternoon player-list CSV (12 games, no SNF/MNF).
2. Drop the **rerun** Grok `2026-09-13.md` (practice report + inactives + NWS Sep 13).
3. `ceminidfs run --season 2026 --week 1 --salary <new.csv> --site fanduel --stages fetch,project,normalize,optimize`
4. Rebuild cash/GPP. Do not Enter/Submit from the agent.
