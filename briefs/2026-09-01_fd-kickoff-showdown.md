# FanDuel single-game — NE @ SEA kickoff (Wed 2026-09-09)

**Contest:** FanDuel $15K Wed NFL Pooch Punt — **1 MVP + 5 AnyFLEX, $60k**. MVP is **1.5x salary and 1.5x points**.
**Kickoff:** Wednesday 2026-09-09, 8:20 p.m. ET, Lumen Field, NBC.
**Pipeline:** `scripts/kickoff_showdown_2026.py` → `runs/2026_week_1_kickoff/`.
**Salaries:** FanDuel app lobby, 2026-09-01 7:30 p.m. ET. FLEX = MVP screen / 1.5.

## Game environment (CeminiDFS volume)

| | SEA | NE |
|---|---:|---:|
| Spread / ITT | −4.5 / **24.5** | +4.5 / **20.0** |
| Plays | 68.5 | 68.5 |
| Pass attempts | **28.3** | **35.8** |
| Rush attempts | **38.2** | 30.2 |
| Pass rate / PROE | 0.481 / −7.7 | 0.607 / +2.5 |

## Builds to enter (tap MVP first, then five FLEX)

**Cash:** MVP **Maye $18,600** · Stevenson · A.J. Brown · Price · Myers · Barner. **$59,800 · 90.4 sim.**

**GPP:** MVP **Stevenson $15,000** · Maye · A.J. Brown · Price · Myers · Borregales. **$60,000 · 90.8 sim.**

**Leverage:** MVP **Price $13,800** · Maye · Stevenson · A.J. Brown · Myers · Borregales. **$59,600 · 90.3 sim.** App FPPG for Price is 0.00; Charbonnet is Out (ACL).

**Do not take JSN** with Maye MVP + both RBs + Brown. He is $13.0k FLEX / $19.5k MVP and busts the cap. Henderson Q — wait T-90.

## Live FanDuel $ vs CeminiDFS proj

| Proj | FLEX $ | MVP $ | Player | Team | Pos |
|-----:|-------:|------:|--------|------|-----|
| 20.5 | 12400 | 18600 | Drake Maye | NE | QB |
| 15.4 | 10000 | 15000 | Rhamondre Stevenson | NE | RB |
| 14.5 | 11600 | 17400 | Sam Darnold | SEA | QB |
| 14.4 | 9200 | 13800 | Jadarian Price | SEA | RB |
| 13.5 | 10800 | 16200 | A.J. Brown | NE | WR |
| 12.5 | 13000 | 19500 | Jaxon Smith-Njigba | SEA | WR |
| 10.6 | 6400 | 9600 | Jason Myers | SEA | K |
| 9.6 | 8600 | 12900 | TreVeyon Henderson | NE | RB |
| 9.2 | 8200 | 12300 | Romeo Doubs | NE | WR |
| 8.6 | 6200 | 9300 | Andy Borregales | NE | K |
| 7.5 | 7600 | 11400 | Hunter Henry | NE | TE |
| 7.4 | 6800 | 10200 | Seahawks | SEA | DST |
| 6.7 | 5400 | 8100 | Cooper Kupp | SEA | WR |
| 5.7 | 4800 | 7200 | AJ Barner | SEA | TE |
| 5.4 | 6600 | 9900 | Patriots | NE | DST |
| 5.3 | 5000 | 7500 | George Holani | SEA | RB |
| 5.2 | 7200 | 10800 | Rashid Shaheed | SEA | WR |
| 4.7 | 3800 | 5700 | DeMario Douglas | NE | WR |
| 4.3 | 5800 | 8700 | Mack Hollins | NE | WR |

Charbonnet Out (ACL) — $14,400 on the MVP screen. Ignore.

## Re-run

```bash
.venv/bin/python scripts/kickoff_showdown_2026.py
```
