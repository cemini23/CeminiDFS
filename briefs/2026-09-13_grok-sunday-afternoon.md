# FanDuel Sunday Million — NFL Week 1 Sunday afternoon (1 p.m. + 4 p.m. ET) packet

**Slate:** FanDuel Sunday Million default = NFL Week 1 **full Sunday afternoon** slate: **1 p.m. ET + 4 p.m. ET** (4:05 and 4:25 included). **Not** 1 p.m.-only. **Not** SNF/MNF. Week 1 has no 4:05 window; the late-afternoon games are all 4:25 p.m. ET.
**Slate date:** Sunday, September 13, 2026
**Packet compiled:** Tuesday, September 1, 2026, ~8:30 p.m. ET (America/New_York). Expanded from the first 1 p.m.-only version of this file.
**Packet type:** READ-ONLY injury / IR / weather / salary-CSV path. No lineups, projections, ownership, salaries, or stacks.
**Caveat:** Early Tuesday Sep 1 packet. Official Wednesday practice reports for Week 1 will not exist yet. Do not treat roster IR/PUP/NFI as a Wednesday practice report.

## Retrieved timestamps (America/New_York)

| Source | Retrieved |
|---|---|
| NFL.com Week 1 injury hub (`/injuries/` → `/injuries/league/2026/reg1`) | Tue Sep 1, 2026, 8:16 PM ET (1 p.m. clubs); re-fetched 8:27 PM ET (4:25 clubs also “No Injuries Reported”) |
| NFL.com `/teams/{slug}/injuries` (24 slugs: 16 1 p.m. + 8 4:25) | Tue Sep 1, 2026, 8:16 PM ET (16) and 8:28 PM ET (8) — all HTTP 404 |
| Official club injury-report pages | Tue Sep 1, 2026, 8:16 PM ET (16 1 p.m. clubs); 8:27–8:28 PM ET (8 4:25 clubs) |
| Official club players-roster (IR/PUP/NFI) pages | Tue Sep 1, 2026, 8:16 PM ET (16 1 p.m. clubs); 8:27–8:28 PM ET (8 4:25 clubs) |
| NFL.com team roster pages (`/teams/{slug}/roster`) | Tue Sep 1, 2026, 8:16 PM ET — static HTML has no Reserve/IR table (JS); not used for player statuses |
| CBS Sports 2026 schedule article | Tue Sep 1, 2026, 8:15 PM ET; 4:25 window re-verified 8:27 PM ET |
| NFL.com schedules/2026/REG1 (partial JS render) | Tue Sep 1, 2026, 8:15 PM ET |
| NFL Football Operations 2026 schedule URL | Tue Sep 1, 2026, 8:15 PM ET — HTTP 403, web app stopped |
| NWS api.weather.gov + forecast.weather.gov | Tue Sep 1, 2026, 8:17–8:18 PM ET (5 outdoor 1 p.m. sites); 8:28 PM ET (Philadelphia / Lincoln Financial) |
| FanDuel public CSV/help pages | Tue Sep 1, 2026, 8:17 PM ET |
| Optional X search (`search_posts_all`, 10 posts) | Tue Sep 1, 2026, 8:14–8:20 PM ET (1 p.m. club query only) |
| Spot-check HOU + PIT club rosters (Braden Smith IR; Joey Porter Jr Active) | Tue Sep 1, 2026, 8:22 PM ET |

## Sources used

- https://www.nfl.com/injuries/ (redirects to https://www.nfl.com/injuries/league/2026/reg1 )
- https://www.nfl.com/schedules/2026/REG1/
- https://www.cbssports.com/nfl/news/2026-nfl-schedule-dates-times-tv-streaming-matchups-for-all-272-games/
- https://nfl-ops-prod-umbraco-author.azurewebsites.net/calendar-events/nfl-schedule/2026-regular-season-schedule/ (failed, 403)
- 24 official club injury-report URLs and 24 official club players-roster URLs (listed per club below)
- NWS points + 7-day forecast grids for Charlotte, Cincinnati, Jacksonville, Pittsburgh, Nashville, Philadelphia
- https://www.fanduel.com/csv-edit and https://support.fanduel.com/s/article/How-do-I-edit-with-a-CSV-file (could not verify live click path without login)

## Games list (Sunday afternoon: 1 p.m. ET + 4:25 p.m. ET)

FanDuel Sunday Million default = **full Sunday afternoon** (1 p.m. + 4 p.m.). Week 1 has **no 4:05** games; the four late-afternoon games are all **4:25 p.m. ET**. Verified against CBS Sports Week 1 listing (May 17, 2026 article, re-checked this expansion) and NFL.com injury hub which lists eight Sunday 1:00 PM EDT games **and** four Sunday 4:25 PM EDT games. NFL.com `/schedules/2026/REG1/` HTML scrape only surfaced primetime/international games (JS-incomplete). NFL Football Operations calendar URL returned 403 ("This web app is stopped").

| Away | Home | Time | TV | Venue | Roof |
|---|---|---|---|---|---|
| Chicago Bears | Carolina Panthers | 1:00 p.m. ET | FOX | Bank of America Stadium, Charlotte | Outdoor |
| Tampa Bay Buccaneers | Cincinnati Bengals | 1:00 p.m. ET | FOX | Paycor Stadium, Cincinnati | Outdoor |
| New Orleans Saints | Detroit Lions | 1:00 p.m. ET | FOX | Ford Field, Detroit | Indoor (dome) |
| Buffalo Bills | Houston Texans | 1:00 p.m. ET | CBS | NRG Stadium, Houston | Retractable |
| Baltimore Ravens | Indianapolis Colts | 1:00 p.m. ET | CBS | Lucas Oil Stadium, Indianapolis | Retractable |
| Cleveland Browns | Jacksonville Jaguars | 1:00 p.m. ET | CBS | EverBank Stadium, Jacksonville | Outdoor |
| Atlanta Falcons | Pittsburgh Steelers | 1:00 p.m. ET | FOX | Acrisure Stadium, Pittsburgh | Outdoor |
| New York Jets | Tennessee Titans | 1:00 p.m. ET | CBS | Nissan Stadium, Nashville | Outdoor |
| Arizona Cardinals | Los Angeles Chargers | 4:25 p.m. ET | CBS | SoFi Stadium, Inglewood | Indoor |
| Miami Dolphins | Las Vegas Raiders | 4:25 p.m. ET | FOX | Allegiant Stadium, Las Vegas | Indoor |
| Green Bay Packers | Minnesota Vikings | 4:25 p.m. ET | CBS | U.S. Bank Stadium, Minneapolis | Indoor (dome) |
| Washington Commanders | Philadelphia Eagles | 4:25 p.m. ET | FOX | Lincoln Financial Field, Philadelphia | Outdoor |

### Later windows, not in this Sunday-afternoon packet

**SNF and MNF are excluded** (not named in the Sunday Million afternoon default; not moved into the main list).

- **8:20 p.m. ET SNF:** Dallas Cowboys at New York Giants (NBC) — also shown on NFL.com REG1 page. **Out of this packet.**
- **Monday 8:15 p.m. ET MNF:** Denver Broncos at Kansas City Chiefs (ESPN). **Out of this packet** (not previously named in the main list).

## Week 1 official injury report (practice / game status)

NFL.com league injury hub HTML for Week 1 lists **“No Injuries Reported”** for all 32 clubs, including all **24 clubs** on this Sunday-afternoon (1 p.m. + 4:25) slate. Page `<title>` still says “Week 3 of the 2026 Season”; on-page heading is **Injuries - WEEK 1**. No Out / Doubtful / Questionable / DNP / LP / FP rows exist yet. Re-fetch at 8:27 p.m. ET still empty for the four 4:25 games (ARI/LAC, MIA/LV, GB/MIN, WAS/PHI).

`https://www.nfl.com/teams/{slug}/injuries` returned **HTTP 404** for every 1 p.m. club and every 4:25 club (that URL pattern is dead).

| Club | NFL.com weekly report | Club injury-report page | Retrieved |
|---|---|---|---|
| Chicago Bears | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded. Quote: "Injuries are reported three times each week during the regular season (typically Wednesday, Thursday & Friday) beginning four days before each game." No Week 1 practice/game-status table posted. https://www.chicagobears.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Carolina Panthers | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend only). No Week 1 practice/game-status table posted. https://www.panthers.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Tampa Bay Buccaneers | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded. Quote: "Injury Report to be updated closer to the regular season." No Week 1 practice/game-status table posted. https://www.buccaneers.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Cincinnati Bengals | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend / news widgets only). No Week 1 practice/game-status table posted. https://www.bengals.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| New Orleans Saints | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded. No Week 1 practice/game-status table posted. https://www.neworleanssaints.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Detroit Lions | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | HTTP 404. Alternate paths /injuries, /team/injuries also 404. No official Lions injury-report page found. https://www.detroitlions.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Buffalo Bills | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend only). No Week 1 practice/game-status table posted. https://www.buffalobills.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Houston Texans | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend only). No Week 1 practice/game-status table posted. https://www.houstontexans.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Baltimore Ravens | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend only). No Week 1 practice/game-status table posted. https://www.baltimoreravens.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Indianapolis Colts | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend only). No Week 1 practice/game-status table posted. https://www.colts.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Cleveland Browns | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend only). No Week 1 practice/game-status table posted. https://www.clevelandbrowns.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Jacksonville Jaguars | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend only). No Week 1 practice/game-status table posted. https://www.jaguars.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Atlanta Falcons | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded. Current Week 1 table empty; page also lists 2025-season injury-report news headlines (not used as Week 1 game status). https://www.atlantafalcons.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Pittsburgh Steelers | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded. Quote: "The next official injury report will be available at the start of the 2026 regular season." No Week 1 practice/game-status table posted. https://www.steelers.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| New York Jets | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend only). No Week 1 practice/game-status table posted. https://www.newyorkjets.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Tennessee Titans | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded. No Week 1 practice/game-status table posted. https://www.tennesseetitans.com/team/injury-report/ | Tue Sep 1, 2026, 8:16 PM ET / Tue Sep 1, 2026, 8:16 PM ET |
| Arizona Cardinals | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend only). No Week 1 practice/game-status table posted. https://www.azcardinals.com/team/injury-report/ | Tue Sep 1, 2026, 8:27 PM ET / Tue Sep 1, 2026, 8:27 PM ET |
| Los Angeles Chargers | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded. Quote: "A look at injury reports of the Los Angeles Chargers as we head into the 2025 season." No Week 1 2026 practice/game-status table posted. https://www.chargers.com/team/injury-report/ | Tue Sep 1, 2026, 8:27 PM ET / Tue Sep 1, 2026, 8:27 PM ET |
| Miami Dolphins | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend only). No Week 1 practice/game-status table posted. https://www.miamidolphins.com/team/injury-report/ | Tue Sep 1, 2026, 8:27 PM ET / Tue Sep 1, 2026, 8:27 PM ET |
| Las Vegas Raiders | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded. Quote: "The Las Vegas Raiders injury report will be available in Fall 2026." No Week 1 practice/game-status table posted. https://www.raiders.com/team/injury-report/ | Tue Sep 1, 2026, 8:27 PM ET / Tue Sep 1, 2026, 8:27 PM ET |
| Green Bay Packers | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend only). No Week 1 practice/game-status table posted. https://www.packers.com/team/injury-report/ | Tue Sep 1, 2026, 8:27 PM ET / Tue Sep 1, 2026, 8:27 PM ET |
| Minnesota Vikings | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (heading “INJURY REPORTS” only). No Week 1 practice/game-status table posted. https://www.vikings.com/team/injury-report/ | Tue Sep 1, 2026, 8:27 PM ET / Tue Sep 1, 2026, 8:27 PM ET |
| Washington Commanders | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded (legend only). No Week 1 practice/game-status table posted. https://www.commanders.com/team/injury-report/ | Tue Sep 1, 2026, 8:27 PM ET / Tue Sep 1, 2026, 8:27 PM ET |
| Philadelphia Eagles | No Injuries Reported — https://www.nfl.com/injuries/league/2026/reg1 | Page loaded. Current Week 1 table empty; page also lists 2025-season and Jan 2026 Wild Card injury-report news headlines (not used as Week 1 2026 game status). https://www.philadelphiaeagles.com/team/injury-report/ | Tue Sep 1, 2026, 8:27 PM ET / Tue Sep 1, 2026, 8:27 PM ET |

Empty-but-fetched weekly reports (no invented players): **all 24 clubs** (16 1 p.m. + 8 4:25).

## Injury / IR / PUP / NFI table (roster reserve lists)

Statuses below are **exactly** the section headers on each club’s official players-roster page. They are **not** Wednesday practice designations. Practice-squad players are omitted (not IR/PUP/NFI/inactive-reserve). Suspended-by-commissioner names are included because they appear on the same roster reserve modules. **Active/Physically Unable to Perform** is included where the club uses that header (ARI, MIA) — it is PUP, not Reserve/PUP. **Reserve/Retired** (WAS) and **Commissioner Exempt** (GB Josh Jacobs) are omitted (not IR/PUP/NFI).

**Player rows in this table: 194** (133 from the 1 p.m. clubs, unchanged; 61 appended from the eight 4:25 clubs) (plus the weekly-report empty notes above).

| Player | Team | Status | Source URL | Retrieved |
|---|---|---|---|---|
| Beanie Bishop Jr. | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Brittain Brown | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Coby Bryant | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Dallis Flowers | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Dontae Manning | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Hayden Large | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jaylon Jones | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jonathan Garvin | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Nephi Sewell | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Nikola Kalinic | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Ray-Ray McCloud III | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Ruben Hyppolite II | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Tony Fields II | Chicago Bears | Reserve/Injured | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Kyler Gordon | Chicago Bears | Reserve/Physically Unable to Perform | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Noah Sewell | Chicago Bears | Reserve/Physically Unable to Perform | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Shemar Turner | Chicago Bears | Reserve/Physically Unable to Perform | https://www.chicagobears.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Bam Martin-Scott | Carolina Panthers | Reserve/Injured | https://www.panthers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Brady Christensen | Carolina Panthers | Reserve/Injured | https://www.panthers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Chris Brazzell II | Carolina Panthers | Reserve/Injured | https://www.panthers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Nic Scourton | Carolina Panthers | Reserve/Injured | https://www.panthers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Ryan Hayes | Carolina Panthers | Reserve/Injured | https://www.panthers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Trevor Etienne | Carolina Panthers | Reserve/Injured | https://www.panthers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Tyrek Funderburk | Carolina Panthers | Reserve/Injured | https://www.panthers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Ikem Ekwonu | Carolina Panthers | Reserve/Physically Unable to Perform | https://www.panthers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Tershawn Wharton | Carolina Panthers | Reserve/Physically Unable to Perform | https://www.panthers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Taylor Moton | Carolina Panthers | Reserve/Non-Football Illness | https://www.panthers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| David Sills V | Tampa Bay Buccaneers | Reserve/Injured | https://www.buccaneers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Deshawn McKnight | Tampa Bay Buccaneers | Reserve/Injured | https://www.buccaneers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Josh Hayes | Tampa Bay Buccaneers | Reserve/Injured | https://www.buccaneers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Mohamed Kamara | Tampa Bay Buccaneers | Reserve/Injured | https://www.buccaneers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Pepe Williams | Tampa Bay Buccaneers | Reserve/Injured | https://www.buccaneers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Xavier Williams | Tampa Bay Buccaneers | Reserve/Injured | https://www.buccaneers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Brian Parker II | Cincinnati Bengals | Reserve/Injured | https://www.bengals.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Ja'Sir Taylor | Cincinnati Bengals | Reserve/Injured | https://www.bengals.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Barry Wesley | New Orleans Saints | Reserve/Injured | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Bryan Bresee | New Orleans Saints | Reserve/Injured | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Dalys Beanum | New Orleans Saints | Reserve/Injured | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| David Long Jr. | New Orleans Saints | Reserve/Injured | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Devin Neal | New Orleans Saints | Reserve/Injured | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Dillon Radunz | New Orleans Saints | Reserve/Injured | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Lorenzo Styles Jr. | New Orleans Saints | Reserve/Injured | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Michael Heldman | New Orleans Saints | Reserve/Injured | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Moliki Matavao | New Orleans Saints | Reserve/Injured | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Rejzohn Wright | New Orleans Saints | Reserve/Injured | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Ty Chandler | New Orleans Saints | Reserve/Injured | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jaylan Ford | New Orleans Saints | Reserve/Injured; Designated for Return | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jordyn Tyson | New Orleans Saints | Reserve/Injured; Designated for Return | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Mason Tipton | New Orleans Saints | Reserve/Physically Unable to Perform | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Nick Saldiveri | New Orleans Saints | Reserve/Physically Unable to Perform | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Brock Rechsteiner | New Orleans Saints | Reserve/Suspended by Commissioner | https://www.neworleanssaints.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Cade Mays | Detroit Lions | Reserve/Injured | https://www.detroitlions.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Damone Clark | Detroit Lions | Reserve/Injured | https://www.detroitlions.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Isiah Pacheco | Detroit Lions | Reserve/Injured | https://www.detroitlions.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Kendrick Law | Detroit Lions | Reserve/Injured | https://www.detroitlions.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Payton Turner | Detroit Lions | Reserve/Injured | https://www.detroitlions.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Brian Branch | Detroit Lions | Reserve/Physically Unable to Perform | https://www.detroitlions.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Kerby Joseph | Detroit Lions | Reserve/Physically Unable to Perform | https://www.detroitlions.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Giovanni Manu | Detroit Lions | Reserve/Non-Football Injury | https://www.detroitlions.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Demetrius Flannigan-Fowles | Buffalo Bills | Reserve/Injured | https://www.buffalobills.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Zane Durant | Buffalo Bills | Reserve/Injured | https://www.buffalobills.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Tyrell Shavers | Buffalo Bills | Reserve/Physically Unable to Perform | https://www.buffalobills.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Dorian Strong | Buffalo Bills | Reserve/Non-Football Injury | https://www.buffalobills.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Phidarian Mathis | Buffalo Bills | Reserve/Suspended by Commissioner | https://www.buffalobills.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Ali Gaye | Houston Texans | Reserve/Injured | https://www.houstontexans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Braden Smith | Houston Texans | Reserve/Injured | https://www.houstontexans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Dylan Horton | Houston Texans | Reserve/Injured | https://www.houstontexans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Graham Mertz | Houston Texans | Reserve/Injured | https://www.houstontexans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jayden Higgins | Houston Texans | Reserve/Injured | https://www.houstontexans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| K.C. Ossai | Houston Texans | Reserve/Injured | https://www.houstontexans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Sam Hagen | Houston Texans | Reserve/Injured | https://www.houstontexans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Ja'Marcus Ingram | Houston Texans | Reserve/Injured; Designated for Return | https://www.houstontexans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Tank Dell | Houston Texans | Reserve/Injured; Designated for Return | https://www.houstontexans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| E.J. Speed | Houston Texans | Reserve/Physically Unable to Perform | https://www.houstontexans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| M.J. Stewart | Houston Texans | Reserve/Physically Unable to Perform | https://www.houstontexans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Danny Pinter | Baltimore Ravens | Reserve/Injured | https://www.baltimoreravens.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jahquez Robinson | Baltimore Ravens | Reserve/Injured | https://www.baltimoreravens.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Skylar Thompson | Baltimore Ravens | Reserve/Injured | https://www.baltimoreravens.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Adam Randall | Baltimore Ravens | Reserve/Injured; Designated for Return | https://www.baltimoreravens.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Bilhal Kone | Baltimore Ravens | Reserve/Injured; Designated for Return | https://www.baltimoreravens.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Cameron Mitchell | Indianapolis Colts | Reserve/Injured | https://www.colts.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Carson Towt | Indianapolis Colts | Reserve/Injured | https://www.colts.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Coleman Owen | Indianapolis Colts | Reserve/Injured | https://www.colts.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| D.J. Montgomery | Indianapolis Colts | Reserve/Injured | https://www.colts.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Will Mallory | Indianapolis Colts | Reserve/Designated to Return | https://www.colts.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Cam Taylor-Britt | Indianapolis Colts | Reserve/Suspended by Commissioner | https://www.colts.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Alex Wright | Cleveland Browns | Reserve/Injured | https://www.clevelandbrowns.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Damarri Mathis | Cleveland Browns | Reserve/Injured | https://www.clevelandbrowns.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Dillon Gabriel | Cleveland Browns | Reserve/Injured | https://www.clevelandbrowns.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jamari Thrash | Cleveland Browns | Reserve/Injured | https://www.clevelandbrowns.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Kalia Davis | Cleveland Browns | Reserve/Injured | https://www.clevelandbrowns.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Kendrick Green | Cleveland Browns | Reserve/Injured | https://www.clevelandbrowns.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jeremiah Owusu-Koramoah | Cleveland Browns | Reserve/Physically Unable to Perform | https://www.clevelandbrowns.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Joe Royer | Cleveland Browns | Reserve/Non-Football Illness | https://www.clevelandbrowns.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Garrett DiGiorgio | Jacksonville Jaguars | Reserve/Injured | https://www.jaguars.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jared Bartlett | Jacksonville Jaguars | Reserve/Injured | https://www.jaguars.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Parker Hughes | Jacksonville Jaguars | Reserve/Injured | https://www.jaguars.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Sam Mustipher | Jacksonville Jaguars | Reserve/Injured | https://www.jaguars.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Patrick Mekari | Jacksonville Jaguars | Reserve/Injured; Designated for Return | https://www.jaguars.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Zach Durfee | Jacksonville Jaguars | Reserve/Injured; Designated for Return | https://www.jaguars.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Darren Hall | Atlanta Falcons | Reserve/Injured | https://www.atlantafalcons.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| JD Bertrand | Atlanta Falcons | Reserve/Injured | https://www.atlantafalcons.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jalon Walker | Atlanta Falcons | Reserve/Injured | https://www.atlantafalcons.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Keshawn Banks | Atlanta Falcons | Reserve/Injured | https://www.atlantafalcons.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Malik Verdon | Atlanta Falcons | Reserve/Injured | https://www.atlantafalcons.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Trey Sermon | Atlanta Falcons | Reserve/Injured | https://www.atlantafalcons.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Beaux Collins | Atlanta Falcons | Reserve/Injured; Designated for Return | https://www.atlantafalcons.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| DeAngelo Malone | Atlanta Falcons | Reserve/Physically Unable to Perform | https://www.atlantafalcons.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Storm Norton | Atlanta Falcons | Reserve/Physically Unable to Perform | https://www.atlantafalcons.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Anterio Thompson | Atlanta Falcons | Reserve/Non-Football Injury | https://www.atlantafalcons.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| James Pearce Jr. | Atlanta Falcons | Reserve/Suspended by Commissioner | https://www.atlantafalcons.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Daequan Hardy | Pittsburgh Steelers | Reserve/Injured | https://www.steelers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| DeShon Elliott | Pittsburgh Steelers | Reserve/Injured | https://www.steelers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jack Driscoll | Pittsburgh Steelers | Reserve/Injured | https://www.steelers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Logan Lee | Pittsburgh Steelers | Reserve/Injured | https://www.steelers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Donte Kent | Pittsburgh Steelers | Reserve/Physically Unable to Perform | https://www.steelers.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Chase Curtis | New York Jets | Reserve/Injured | https://www.newyorkjets.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Chip Trayanum | New York Jets | Reserve/Injured | https://www.newyorkjets.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Connor Hulstein | New York Jets | Reserve/Injured | https://www.newyorkjets.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Dominic Richardson | New York Jets | Reserve/Injured | https://www.newyorkjets.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Kingsley Jonathan | New York Jets | Reserve/Injured | https://www.newyorkjets.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Mykal Walker | New York Jets | Reserve/Injured | https://www.newyorkjets.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Tre Brown | New York Jets | Reserve/Injured | https://www.newyorkjets.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Anez Cooper | New York Jets | Reserve/Injured; Designated for Return | https://www.newyorkjets.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| VJ Payne | New York Jets | Reserve/Injured; Designated for Return | https://www.newyorkjets.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Tyler Baron | New York Jets | Reserve/Physically Unable to Perform | https://www.newyorkjets.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Andre James | Tennessee Titans | Reserve/Injured | https://www.tennesseetitans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Dominique Hampton | Tennessee Titans | Reserve/Injured | https://www.tennesseetitans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jaren Kanak | Tennessee Titans | Reserve/Injured | https://www.tennesseetitans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Jaylen Harrell | Tennessee Titans | Reserve/Injured | https://www.tennesseetitans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Milo Eifler | Tennessee Titans | Reserve/Injured | https://www.tennesseetitans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Tanoh Kpassagnon | Tennessee Titans | Reserve/Injured | https://www.tennesseetitans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Dorian Mausi | Tennessee Titans | Reserve/Injured; Designated for Return | https://www.tennesseetitans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |
| Joshua Williams | Tennessee Titans | Reserve/Injured; Designated for Return | https://www.tennesseetitans.com/team/players-roster/ | Tue Sep 1, 2026, 8:16 PM ET |

| Chase Bisontis | Arizona Cardinals | Reserve/Injured | https://www.azcardinals.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Jameson Geers | Arizona Cardinals | Reserve/Injured | https://www.azcardinals.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Joey Blount | Arizona Cardinals | Reserve/Injured | https://www.azcardinals.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Kaleb Proctor | Arizona Cardinals | Reserve/Injured | https://www.azcardinals.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Trey Benson | Arizona Cardinals | Reserve/Injured | https://www.azcardinals.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| James Conner | Arizona Cardinals | Reserve/Injured; Designated for Return | https://www.azcardinals.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Zach Carter | Arizona Cardinals | Reserve/Injured; Designated for Return | https://www.azcardinals.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Tip Reiman | Arizona Cardinals | Active/Physically Unable to Perform | https://www.azcardinals.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Dalevon Campbell | Los Angeles Chargers | Reserve/Injured | https://www.chargers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Denzel Perryman | Los Angeles Chargers | Reserve/Injured | https://www.chargers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Kyle Kennard | Los Angeles Chargers | Reserve/Injured | https://www.chargers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Sincere Brown | Los Angeles Chargers | Reserve/Injured | https://www.chargers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Tyler Biadasz | Los Angeles Chargers | Reserve/Injured | https://www.chargers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Branson Taylor | Los Angeles Chargers | Reserve/Injured; Designated for Return | https://www.chargers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Scott Matlock | Los Angeles Chargers | Reserve/Injured; Designated for Return | https://www.chargers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Isaiah World | Los Angeles Chargers | Reserve/Non-Football Injury | https://www.chargers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Carter Warren | Miami Dolphins | Reserve/Injured | https://www.miamidolphins.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Cole Turner | Miami Dolphins | Reserve/Injured | https://www.miamidolphins.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Kenneth Grant | Miami Dolphins | Reserve/Injured | https://www.miamidolphins.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Rene Konga | Miami Dolphins | Reserve/Injured | https://www.miamidolphins.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Trey Moore | Miami Dolphins | Reserve/Injured | https://www.miamidolphins.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Darrell Baker Jr. | Miami Dolphins | Active/Physically Unable to Perform | https://www.miamidolphins.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Storm Duck | Miami Dolphins | Active/Physically Unable to Perform | https://www.miamidolphins.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Brennan Jackson | Las Vegas Raiders | Reserve/Injured | https://www.raiders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Chase Roberts | Las Vegas Raiders | Reserve/Injured | https://www.raiders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Chigozie Anusiem | Las Vegas Raiders | Reserve/Injured | https://www.raiders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Chris Collier | Las Vegas Raiders | Reserve/Injured | https://www.raiders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Corey Rucker | Las Vegas Raiders | Reserve/Injured | https://www.raiders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Dont'e Thornton Jr. | Las Vegas Raiders | Reserve/Injured | https://www.raiders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Justin Pickett | Las Vegas Raiders | Reserve/Injured | https://www.raiders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Justin Shorter | Las Vegas Raiders | Reserve/Injured | https://www.raiders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Keyron Crawford | Las Vegas Raiders | Reserve/Injured | https://www.raiders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Carter Runyon | Las Vegas Raiders | Reserve/Injured; Designated for Return | https://www.raiders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Collin Oliver | Green Bay Packers | Reserve/Injured; Designated for Return | https://www.packers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Savion Williams | Green Bay Packers | Reserve/Injured; Designated for Return | https://www.packers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Jordon Riley | Green Bay Packers | Reserve/Physically Unable to Perform | https://www.packers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Luke Musgrave | Green Bay Packers | Reserve/Physically Unable to Perform | https://www.packers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Micah Parsons | Green Bay Packers | Reserve/Physically Unable to Perform | https://www.packers.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Dontae Fleming | Minnesota Vikings | Reserve/Injured | https://www.vikings.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Jacob Roberts | Minnesota Vikings | Reserve/Injured | https://www.vikings.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Jamal Adams | Minnesota Vikings | Reserve/Injured | https://www.vikings.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Jermar Jefferson | Minnesota Vikings | Reserve/Injured | https://www.vikings.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Kenny Dyson | Minnesota Vikings | Reserve/Injured | https://www.vikings.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Marcus Allen | Minnesota Vikings | Reserve/Injured | https://www.vikings.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Taki Taimani | Minnesota Vikings | Reserve/Injured | https://www.vikings.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Tyler Batty | Minnesota Vikings | Reserve/Injured | https://www.vikings.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Tyreek Chappell | Minnesota Vikings | Reserve/Injured | https://www.vikings.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Michael Jurgens | Minnesota Vikings | Reserve/Designated to Return | https://www.vikings.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Jeshaun Jones | Minnesota Vikings | Reserve/Suspended by Commissioner | https://www.vikings.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Jeremy McNichols | Washington Commanders | Reserve/Injured | https://www.commanders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Jer'Zhan Newton | Washington Commanders | Reserve/Injured | https://www.commanders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Laremy Tunsil | Washington Commanders | Reserve/Injured | https://www.commanders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Malik Spencer | Washington Commanders | Reserve/Injured | https://www.commanders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Trey Amos | Washington Commanders | Reserve/Injured | https://www.commanders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Deatrich Wise Jr. | Washington Commanders | Reserve/Physically Unable to Perform | https://www.commanders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Dorance Armstrong | Washington Commanders | Reserve/Suspended by Commissioner | https://www.commanders.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Andre' Sam | Philadelphia Eagles | Reserve/Injured | https://www.philadelphiaeagles.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Johnny Wilson | Philadelphia Eagles | Reserve/Injured | https://www.philadelphiaeagles.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Grant Calcaterra | Philadelphia Eagles | Reserve/Injured; Designated for Return | https://www.philadelphiaeagles.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Jakorian Bennett | Philadelphia Eagles | Reserve/Injured; Designated for Return | https://www.philadelphiaeagles.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |
| Tucker Large | Philadelphia Eagles | Reserve/Non-Football Injury | https://www.philadelphiaeagles.com/team/players-roster/ | Tue Sep 1, 2026, 8:28 PM ET |

### Roster-reserve counts by club

| Club | IR | IR-DFR / Designated to Return | PUP | NFI | NFI-illness | Suspended | Total in table | Weekly report |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Chicago Bears | 13 | 0 | 3 | 0 | 0 | 0 | 16 | no report posted |
| Carolina Panthers | 7 | 0 | 2 | 0 | 1 | 0 | 10 | no report posted |
| Tampa Bay Buccaneers | 6 | 0 | 0 | 0 | 0 | 0 | 6 | no report posted |
| Cincinnati Bengals | 2 | 0 | 0 | 0 | 0 | 0 | 2 | no report posted |
| New Orleans Saints | 11 | 2 | 2 | 0 | 0 | 1 | 16 | no report posted |
| Detroit Lions | 5 | 0 | 2 | 1 | 0 | 0 | 8 | no report posted |
| Buffalo Bills | 2 | 0 | 1 | 1 | 0 | 1 | 5 | no report posted |
| Houston Texans | 7 | 2 | 2 | 0 | 0 | 0 | 11 | no report posted |
| Baltimore Ravens | 3 | 2 | 0 | 0 | 0 | 0 | 5 | no report posted |
| Indianapolis Colts | 4 | 1 | 0 | 0 | 0 | 1 | 6 | no report posted |
| Cleveland Browns | 6 | 0 | 1 | 0 | 1 | 0 | 8 | no report posted |
| Jacksonville Jaguars | 4 | 2 | 0 | 0 | 0 | 0 | 6 | no report posted |
| Atlanta Falcons | 6 | 1 | 2 | 1 | 0 | 1 | 11 | no report posted |
| Pittsburgh Steelers | 4 | 0 | 1 | 0 | 0 | 0 | 5 | no report posted |
| New York Jets | 7 | 2 | 1 | 0 | 0 | 0 | 10 | no report posted |
| Tennessee Titans | 6 | 2 | 0 | 0 | 0 | 0 | 8 | no report posted |
| Arizona Cardinals | 5 | 2 | 1 | 0 | 0 | 0 | 8 | no report posted |
| Los Angeles Chargers | 5 | 2 | 0 | 1 | 0 | 0 | 8 | no report posted |
| Miami Dolphins | 5 | 0 | 2 | 0 | 0 | 0 | 7 | no report posted |
| Las Vegas Raiders | 9 | 1 | 0 | 0 | 0 | 0 | 10 | no report posted |
| Green Bay Packers | 0 | 2 | 3 | 0 | 0 | 0 | 5 | no report posted |
| Minnesota Vikings | 9 | 1 | 0 | 0 | 0 | 1 | 11 | no report posted |
| Washington Commanders | 5 | 0 | 1 | 0 | 0 | 1 | 7 | no report posted |
| Philadelphia Eagles | 2 | 2 | 0 | 1 | 0 | 0 | 5 | no report posted |

ARI PUP cell is **Active/PUP** (Tip Reiman), not Reserve/PUP. MIA PUP cell is **Active/PUP** (Darrell Baker Jr., Storm Duck). GB has no Reserve/Injured (only 2 IR-DFR + 3 Reserve/PUP). MIN “Designated to Return” header is `Reserve/Designated to Return` (Michael Jurgens), same bucket as Colts Will Mallory. Omitted from table (not IR/PUP/NFI): GB **Commissioner Exempt** Josh Jacobs; WAS **Reserve/Retired** Nick Bellore, DJ Davidson, Ahkello Witherspoon.

**Weekly injury-report pages empty vs populated:** all **24** weekly/practice reports empty (NFL.com “No Injuries Reported”; club pages have legend or “not yet” copy). **Roster IR/PUP/NFI pages populated for all 24 clubs** (Bengals fewest among 1 p.m. clubs with 2 IR names; Bears and Saints 16 each; among 4:25 clubs Packers and Eagles fewest with 5 names each, Vikings 11).

## Optional X pass (NOT official status)

Retrieved Tue Sep 1, 2026, ~8:14–8:20 p.m. ET. Query: NFL (`ruled out` OR inactive OR `injury report` OR `placed on IR` OR PUP) plus **1 p.m. club names only**, `-is:retweet lang:en`, `max_results=10`. X credits remaining before this pass were about $29.66. These posts are **not** practice-report rows. Official confirmation is the roster table above.

**4 p.m. clubs were not in that first cheap X query** (ARI/LAC/MIA/LV/GB/MIN/WAS/PHI). Parent may add a 4:25 X pass later. File `_x-pass-2026-09-01.md` later logged a separate 4 p.m. query (~8:26 p.m. ET) that is also **not** official; its Micah Parsons (GB) PUP claim **matches** Packers `Reserve/Physically Unable to Perform` already in the roster table above. No extra X rows invented here.

| Claim (as posted) | Official match (this packet) | X URL | Post time (UTC) |
|---|---|---|---|
| Houston RT Braden Smith to IR, out Week 1 | **Match.** HOU Reserve/Injured on club roster (already listed; not “to be placed”). | https://x.com/offshoreinsider/status/2094931248955228587 | 2026-09-01T23:31:46Z |
| Kyler Gordon opens 2026 on PUP | **Match.** CHI Reserve/Physically Unable to Perform. | https://x.com/ChiSportsTracks/status/2094898652019867970 | 2026-09-01T21:22:14Z |
| Kerby Joseph and Brian Branch on PUP, miss min 4 games | **Match.** Both DET Reserve/Physically Unable to Perform. | https://x.com/ShaanS7_/status/2094911865100853541 | 2026-09-01T22:14:44Z |
| Isiah Pacheco placed on IR (post said Detroit) | **Match.** DET Reserve/Injured. | https://x.com/offshoreinsider/status/2094904294042456295 | 2026-09-01T21:44:39Z |
| Joey Porter Jr. “back on the PUP list” | **No match.** PIT official roster: Porter Jr. is **Active**. Only PIT PUP is Donte Kent. Conflicting McCarthy “coming off PUP / ramp-up” quote: https://x.com/Blitz_Burgh/status/2094921745270481238 | https://x.com/TheSportsPorch1/status/2094931123386097894 | 2026-09-01T23:31:16Z |
| Billy Bowman Jr avoided PUP, made Falcons 53 | Not an injury status. Bowman Jr. is **not** on ATL IR/PUP/NFI in this table. | https://x.com/falcons_hit/status/2094862880373956929 | 2026-09-01T19:00:06Z |

No official Sunday inactives exist this far from Week 1. Spot-check Tue Sep 1 ~8:22 p.m. ET: Texans roster still lists Braden Smith under Reserve/Injured; Steelers roster still lists Joey Porter Jr. under Active.

## Weather (Sunday Sep 13 afternoon)

NWS public 7-day forecasts retrieved Tue Sep 1 evening **do not reach Sunday, September 13**. The last NWS period on every successful grid is **Tuesday, September 8**. Forecast.weather.gov HTML tombstones stop at **Saturday Sep 5**. Any “Sunday” period in the current grid is **Sunday Sep 6**, not game day — not used as a Sep 13 forecast. **No Sep 13 numbers invented.**

| Site | Roof | NWS product | Horizon | Sep 13 afternoon | Retrieved |
|---|---|---|---|---|---|
| Charlotte — Bank of America Stadium (Bears at Panthers) | Outdoor | https://api.weather.gov/gridpoints/GSP/118,65/forecast and https://forecast.weather.gov/MapClick.php?lat=35.2258&lon=-80.8528 (grid GSP 118,65; generated 2026-09-02T00:17:46Z) | Last period Tue Sep 8, high 88°F Mostly Sunny — **not game day** | **Unavailable** (too far out) | Tue Sep 1, 2026, 8:17–8:18 PM ET |
| Cincinnati — Paycor Stadium (Buccaneers at Bengals) | Outdoor | https://api.weather.gov/gridpoints/ILN/35,38/forecast and https://forecast.weather.gov/MapClick.php?lat=39.0954&lon=-84.5160 (grid ILN 35,38; generated 2026-09-02T00:17:52Z) | Last period Tue Sep 8, high 85°F Mostly Sunny — **not game day** | **Unavailable** (too far out) | Tue Sep 1, 2026, 8:17–8:18 PM ET |
| Jacksonville — EverBank Stadium (Browns at Jaguars) | Outdoor | https://api.weather.gov/gridpoints/JAX/66,64/forecast and https://forecast.weather.gov/MapClick.php?lat=30.3239&lon=-81.6373 (grid JAX 66,64; generated 2026-09-01T22:01:46Z). First API call HTTP 503, retry succeeded. | Last period Tue Sep 8, high 89°F Chance Showers And Thunderstorms — **not game day** | **Unavailable** (too far out) | Tue Sep 1, 2026, 8:17–8:18 PM ET |
| Pittsburgh — Acrisure Stadium (Falcons at Steelers) | Outdoor | https://api.weather.gov/gridpoints/PBZ/77,66/forecast and https://forecast.weather.gov/MapClick.php?lat=40.4468&lon=-80.0158 (grid PBZ 77,66; generated 2026-09-02T00:17:20Z) | Last period Tue Sep 8, high 79°F Partly Sunny — **not game day** | **Unavailable** (too far out) | Tue Sep 1, 2026, 8:17–8:18 PM ET |
| Nashville — Nissan Stadium (Jets at Titans) | Outdoor | https://api.weather.gov/gridpoints/OHX/50,57/forecast and https://forecast.weather.gov/MapClick.php?lat=36.1665&lon=-86.7713 (grid OHX 50,57; generated 2026-09-01T23:59:01Z) | Last period Tue Sep 8, high 94°F Mostly Sunny — **not game day** | **Unavailable** (too far out) | Tue Sep 1, 2026, 8:17–8:18 PM ET |
| Detroit — Ford Field (Saints at Lions) | Indoor dome | — | — | Skip; no outdoor forecast | — |
| Houston — NRG Stadium (Bills at Texans) | Retractable | — | — | Skip; no fake open/closed weather. Roof status not posted this far out. | — |
| Indianapolis — Lucas Oil Stadium (Ravens at Colts) | Retractable | — | — | Skip; no fake open/closed weather. Roof status not posted this far out. | — |
| Philadelphia — Lincoln Financial Field (Commanders at Eagles) | Outdoor | https://api.weather.gov/gridpoints/PHI/50,76/forecast and https://forecast.weather.gov/MapClick.php?lat=39.9008&lon=-75.1675 (grid PHI 50,76; generated 2026-09-02T00:28:31Z; forecast valid 8pm EDT Sep 1–6pm EDT Sep 8) | Last period Tue Sep 8, high 81°F Mostly Sunny — **not game day**. Grid “Sunday” is **Sunday Sep 6**, not Sep 13. | **Unavailable** (too far out) | Tue Sep 1, 2026, 8:28 PM ET |
| Inglewood — SoFi Stadium (Cardinals at Chargers) | Indoor | — | — | Skip; no outdoor forecast | — |
| Las Vegas — Allegiant Stadium (Dolphins at Raiders) | Indoor | — | — | Skip; no outdoor forecast | — |
| Minneapolis — U.S. Bank Stadium (Packers at Vikings) | Indoor dome | — | — | Skip; no outdoor forecast | — |

Re-fetch NWS after ~Wed Sep 9 when a 7-day grid can actually include Sep 13.

## Diff vs last packet

**Vs the first version of this same file (1 p.m.-only, compiled ~8:18 p.m. ET):** slate expanded to include the **4:25 window**; added clubs **ARI / LAC / MIA / LV / GB / MIN / WAS / PHI**. New IR/PUP/NFI (and Active/PUP, Suspended) rows appended from those eight club roster pages (61 names). **Not** a Q/Out/Active practice-report flip — those still do not exist. Existing 1 p.m. IR rows were **kept** (not re-fetched; timestamps remain 8:16 p.m. ET). SNF (Cowboys at Giants) still excluded. Philly outdoor weather added (Unavailable, too far out). No FanDuel or Stokastic salary CSV found under `/workspace` (workspace CSVs are unrelated outreach files).

## T-90 checklist (generic; no locked names or stacks)

Sunday Million afternoon slate has two kickoff windows. Primary lock is still ~90 minutes before the **1 p.m. ET** games (Sun Sep 13 ~11:30 a.m. ET); 4:25 games lock later. This Tuesday packet cannot complete any of these:

1. **Late scratches / inactives:** compare Sunday 90-minute inactive lists vs this roster IR/PUP/NFI table; add any game-day Out not already on IR (all 12 afternoon games).
2. **Q → Out (and DNP Friday → Out):** first official Week 1 practice reports should start Wednesday Sep 9 (four days before Sunday games). Track Questionable that flip to Out on Friday/Saturday/Sunday reports.
3. **Weather that changes outdoor games:** re-pull NWS for Charlotte, Cincinnati, Jacksonville, Pittsburgh, Nashville, **Philadelphia** once the 7-day forecast includes Sep 13; watch wind, storms, and field conditions. Ignore indoor Ford Field, **SoFi**, **Allegiant**, and **U.S. Bank**. For NRG and Lucas Oil, confirm roof open/closed rather than using outdoor weather.
4. **Salary CSV still current:** confirm the FanDuel Sunday Million player-list CSV timestamp/slate ID still matches the **Sunday afternoon** slate (1 p.m. + 4 p.m. / 4:25; **no SNF/MNF** unless the contest expanded). Re-download if FanDuel posted a new list after inactive news.
5. **Do not** click Enter/Submit/late-swap in this workflow; user drops the CSV.

## FanDuel salary CSV click path + STOP

**No FanDuel or Stokastic CSV was dropped this run. STOP and wait for the user to drop the file.**

This agent did **not** log into FanDuel, did **not** open a contest, did **not** click Enter/Submit, and did **not** type credentials.

Live public-docs check (Tue Sep 1, 8:17 p.m. ET):

- https://www.fanduel.com/csv-edit → HTTP 404 / bot interstitial (“Press & Hold to confirm you are a human”). Not a usable 2026 salary-list download page.
- https://support.fanduel.com/s/article/How-do-I-edit-with-a-CSV-file → Salesforce shell loaded (“Fanduel Support Custom” / “CSS Error”); article body did not render. That article is about **CSV Edit of already-entered lineups**, not the contest salary list.
- https://help.fanduel.com/ → HTTP 500 (WebFetch).

**Last known public path (UNVERIFIED for 2026 UI; sourced from older public writeups such as Smart Fantasy Baseball’s FanDuel CSV import notes, not a live logged-in lobby):**

1. On a desktop browser, open https://www.fanduel.com (Fantasy / DFS), already signed in as the user — **do not type a password into this agent.**
2. Open the NFL lobby and locate the **Sunday Million** (or the default main-slate NFL contest) for Sun Sep 13, 2026.
3. Historical UI: open the contest’s player pool. Older public docs then say to click **Enter** so the player list loads, scroll to the **bottom of the player salary list**, and click **Download player list** (CSV).
4. **STOP — do not click Enter, Submit, or late-swap in this workflow.** If the current UI still hides the CSV behind Enter, the user downloads it themselves and drops the file into `/workspace` or chat.
5. Expected file is a FanDuel player-list CSV (unique filename from FanDuel). Rename locally if needed; do not re-upload lineups.
6. Alternate historical path (also unverified live): **Upcoming** tab → **CSV Edit** downloads an *entries* template (not a substitute for the salary list if you have no entries).

Mark: **click path unverified on 2026 FanDuel without logging in.** User drop required.

## Fetch failures / thin sources

- All **24** `https://www.nfl.com/teams/{slug}/injuries` URLs: HTTP 404 (16 at 8:16 p.m. ET; ARI/LAC/MIA/LV/GB/MIN/WAS/PHI at 8:28 p.m. ET).
- Detroit Lions official injury-report URL: HTTP 404 (roster page used for IR/PUP/NFI).
- NFL Football Operations 2026 schedule page: HTTP 403, Azure web app stopped.
- NFL.com `/schedules/2026/REG1/` scrape incomplete (primetime only); 1 p.m. **and** 4:25 slate confirmed via CBS Sports + NFL.com injuries hub game list (hub lists both windows; SNF also listed there but kept out of this packet).
- NWS forecast API HTTP 503 on first Charlotte / Cincinnati / Jacksonville calls; retries succeeded. Horizon still ends Sep 8, including Philadelphia (PHI 50,76).
- FanDuel csv-edit 404; FanDuel support article body not rendered; help.fanduel.com 500.
- NFL.com team roster pages: 200 OK but no Reserve/IR table in static HTML (JS). Official club roster pages used instead.

## Validation notes

- Every player status has source URL + ET retrieved time.
- Game list includes **both** Sunday afternoon windows: eight 1:00 p.m. ET games **and** four 4:25 p.m. ET games. **SNF excluded** (Cowboys at Giants, 8:20 p.m. ET). **MNF excluded** (Broncos at Chiefs).
- Zero contest clicks; no passwords; no Underdog scrape; no bank/FanDuel login.
- No invented projections, ownership, salaries, stacks, or Week 1 practice designations.
- News-roundup headlines on NFL.com injuries page (Kamara, Higgins, Biadasz, etc.) were **not** copied into the status table because they are not official report rows. Tyler Biadasz appears only because Chargers roster lists him Reserve/Injured.

