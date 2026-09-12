# FanDuel Sunday Million — NFL Week 1 main Sunday 1:00 p.m. ET packet

**Slate:** FanDuel Sunday Million default = NFL Week 1 main Sunday 1:00 p.m. ET games
**Slate date:** Sunday, September 13, 2026
**Packet compiled:** Tuesday, September 1, 2026, ~8:18 p.m. ET (America/New_York)
**Packet type:** READ-ONLY injury / IR / weather / salary-CSV path. No lineups, projections, ownership, salaries, or stacks.
**Caveat:** Early Tuesday Sep 1 packet. Official Wednesday practice reports for Week 1 will not exist yet. Do not treat roster IR/PUP/NFI as a Wednesday practice report.

## Retrieved timestamps (America/New_York)

| Source | Retrieved |
|---|---|
| NFL.com Week 1 injury hub (`/injuries/` → `/injuries/league/2026/reg1`) | Tue Sep 1, 2026, 8:16 PM ET |
| NFL.com ` /teams/{slug}/injuries ` (all 16 slugs) | Tue Sep 1, 2026, 8:16 PM ET — all HTTP 404 |
| Official club injury-report pages | Tue Sep 1, 2026, 8:16 PM ET |
| Official club players-roster (IR/PUP/NFI) pages | Tue Sep 1, 2026, 8:16 PM ET |
| NFL.com team roster pages (`/teams/{slug}/roster`) | Tue Sep 1, 2026, 8:16 PM ET — static HTML has no Reserve/IR table (JS); not used for player statuses |
| CBS Sports 2026 schedule article | Tue Sep 1, 2026, 8:15 PM ET |
| NFL.com schedules/2026/REG1 (partial JS render) | Tue Sep 1, 2026, 8:15 PM ET |
| NFL Football Operations 2026 schedule URL | Tue Sep 1, 2026, 8:15 PM ET — HTTP 403, web app stopped |
| NWS api.weather.gov + forecast.weather.gov | Tue Sep 1, 2026, 8:17–8:18 PM ET |
| FanDuel public CSV/help pages | Tue Sep 1, 2026, 8:17 PM ET |
| Optional X search (`search_posts_all`, 10 posts) | Tue Sep 1, 2026, 8:14–8:20 PM ET |
| Spot-check HOU + PIT club rosters (Braden Smith IR; Joey Porter Jr Active) | Tue Sep 1, 2026, 8:22 PM ET |

## Sources used

- https://www.nfl.com/injuries/ (redirects to https://www.nfl.com/injuries/league/2026/reg1 )
- https://www.nfl.com/schedules/2026/REG1/
- https://www.cbssports.com/nfl/news/2026-nfl-schedule-dates-times-tv-streaming-matchups-for-all-272-games/
- https://nfl-ops-prod-umbraco-author.azurewebsites.net/calendar-events/nfl-schedule/2026-regular-season-schedule/ (failed, 403)
- 16 official club injury-report URLs and 16 official club players-roster URLs (listed per club below)
- NWS points + 7-day forecast grids for Charlotte, Cincinnati, Jacksonville, Pittsburgh, Nashville
- https://www.fanduel.com/csv-edit and https://support.fanduel.com/s/article/How-do-I-edit-with-a-CSV-file (could not verify live click path without login)

## Games list (1 p.m. ET packet slate only)

Verified against CBS Sports Week 1 listing (May 17, 2026 article) and NFL.com injury hub which lists eight Sunday 1:00 PM EDT games. NFL.com `/schedules/2026/REG1/` HTML scrape only surfaced primetime/international games (JS-incomplete). NFL Football Operations calendar URL returned 403 ("This web app is stopped").

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

### Later Sunday windows, not in this 1 p.m. packet

Not treated as FanDuel Sunday Million 1 p.m. default (no public confirmation this run that the Sunday Million includes them). Listed only as a note:

- **4:25 p.m. ET:** Cardinals at Chargers (CBS); Dolphins at Raiders (FOX); Packers at Vikings (CBS); Commanders at Eagles (FOX)
- **8:20 p.m. ET SNF:** Cowboys at Giants (NBC) — also shown on NFL.com REG1 page

## Week 1 official injury report (practice / game status)

NFL.com league injury hub HTML for Week 1 lists **“No Injuries Reported”** for all 32 clubs, including all 16 clubs on this 1 p.m. slate. Page `<title>` still says “Week 3 of the 2026 Season”; on-page heading is **Injuries - WEEK 1**. No Out / Doubtful / Questionable / DNP / LP / FP rows exist yet.

`https://www.nfl.com/teams/{slug}/injuries` returned **HTTP 404** for every 1 p.m. club (that URL pattern is dead).

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

Empty-but-fetched weekly reports (no invented players): **all 16 clubs**.

## Injury / IR / PUP / NFI table (roster reserve lists)

Statuses below are **exactly** the section headers on each club’s official players-roster page. They are **not** Wednesday practice designations. Practice-squad players are omitted (not IR/PUP/NFI/inactive-reserve). Suspended-by-commissioner names are included because they appear on the same roster reserve modules.

**Player rows in this table: 133** (plus the weekly-report empty notes above).

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

**Weekly injury-report pages empty vs populated:** all 16 weekly/practice reports empty (NFL.com “No Injuries Reported”; club pages have legend or “not yet” copy). **Roster IR/PUP/NFI pages populated for all 16 clubs** (Bengals fewest with 2 IR names; Bears and Saints 16 each).

## Optional X pass (NOT official status)

Retrieved Tue Sep 1, 2026, ~8:14–8:20 p.m. ET. Query: NFL (`ruled out` OR inactive OR `injury report` OR `placed on IR` OR PUP) plus 1 p.m. club names, `-is:retweet lang:en`, `max_results=10`. X credits remaining before this pass were about $29.66. These posts are **not** practice-report rows. Official confirmation is the roster table above.

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

Re-fetch NWS after ~Wed Sep 9 when a 7-day grid can actually include Sep 13.

## Diff vs last packet

**None — first packet.** `/workspace/dfs-slate/` did not exist before this run. No prior `2026-09-13.md`. No FanDuel or Stokastic salary CSV found under `/workspace` (workspace CSVs are unrelated outreach files).

## T-90 checklist (generic; no locked names or stacks)

Run ~90 minutes before the 1 p.m. ET lock (Sun Sep 13 ~11:30 a.m. ET). This Tuesday packet cannot complete any of these:

1. **Late scratches / inactives:** compare Sunday 90-minute inactive lists vs this roster IR/PUP/NFI table; add any game-day Out not already on IR.
2. **Q → Out (and DNP Friday → Out):** first official Week 1 practice reports should start Wednesday Sep 9 (four days before Sunday games). Track Questionable that flip to Out on Friday/Saturday/Sunday reports.
3. **Weather that changes outdoor games:** re-pull NWS for Charlotte, Cincinnati, Jacksonville, Pittsburgh, Nashville once the 7-day forecast includes Sep 13; watch wind, storms, and field conditions. Ignore indoor Ford Field. For NRG and Lucas Oil, confirm roof open/closed rather than using outdoor weather.
4. **Salary CSV still current:** confirm the FanDuel Sunday Million player-list CSV timestamp/slate ID still matches the 1 p.m. main slate (no extra 4:25/SNF games unless the contest expanded). Re-download if FanDuel posted a new list after inactive news.
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

- All 16 `https://www.nfl.com/teams/{slug}/injuries` URLs: HTTP 404.
- Detroit Lions official injury-report URL: HTTP 404 (roster page used for IR/PUP/NFI).
- NFL Football Operations 2026 schedule page: HTTP 403, Azure web app stopped.
- NFL.com `/schedules/2026/REG1/` scrape incomplete (primetime only); 1 p.m. slate confirmed via CBS Sports + NFL.com injuries hub game list.
- NWS forecast API HTTP 503 on first Charlotte / Cincinnati / Jacksonville calls; retries succeeded. Horizon still ends Sep 8.
- FanDuel csv-edit 404; FanDuel support article body not rendered; help.fanduel.com 500.
- NFL.com team roster pages: 200 OK but no Reserve/IR table in static HTML (JS). Official club roster pages used instead.

## Validation notes

- Every player status has source URL + ET retrieved time.
- Zero contest clicks; no passwords; no Underdog scrape; no bank/FanDuel login.
- No invented projections, ownership, salaries, stacks, or Week 1 practice designations.
- News-roundup headlines on NFL.com injuries page (Kamara, Higgins, etc.) were **not** copied into the status table because they are not official report rows.

