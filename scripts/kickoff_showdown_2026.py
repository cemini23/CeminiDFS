#!/usr/bin/env python3
"""NE @ SEA FanDuel single-game slate — Week 1 2026 kickoff.

Uses CeminiDFS volume/usage/scoring on 2025 nflverse PBP plus the live
Vegas line. FanDuel format (2026): MVP 1.5x points AND 1.5x salary,
5 AnyFLEX, $60k. FLEX salaries are from the FanDuel lobby 2026-09-01
19:30 ET (MVP list / 1.5).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from ceminidfs.models.implied_totals import implied_totals_from_favorite
from ceminidfs.models.scoring import fd_dst_points_allowed, fd_points
from ceminidfs.models.volume import (
    BASE_PASS_RATE,
    DEFAULT_SACK_RATE,
    DEFAULT_SCRAMBLE_RATE,
    PLAYS_INTERCEPT,
    LEAGUE_SEC_PER_PLAY,
    allocate_play_volume,
    neutral_proe,
    neutral_seconds_per_play,
    project_team_volume,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runs" / "2026_week_1_kickoff"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Live consensus as of DFF FanDuel slate 2026-09-01 19:05 ET
TOTAL = 44.5
SEA_SPREAD = -4.5  # home favorite
GAME = "NE@SEA"

# FLEX (1x) salaries from FanDuel lobby MVP list / 1.5. 2026-09-01 19:30 ET.
# MVP slot in-app shows these * 1.5 (JSN $19,500, Maye $18,600, …).
FD_SALARIES: dict[str, int] = {
    "Jaxon Smith-Njigba": 13000,
    "Drake Maye": 12400,
    "Sam Darnold": 11600,
    "A.J. Brown": 10800,
    "Rhamondre Stevenson": 10000,
    "Jadarian Price": 9200,
    "TreVeyon Henderson": 8600,
    "Romeo Doubs": 8200,
    "Hunter Henry": 7600,
    "Rashid Shaheed": 7200,
    "Seahawks": 6800,
    "Patriots": 6600,
    "Jason Myers": 6400,
    "Andy Borregales": 6200,
    "Mack Hollins": 5800,
    "Cooper Kupp": 5400,
    "George Holani": 5000,
    "AJ Barner": 4800,
    "DeMario Douglas": 3800,
}

# Out / questionable — keep in projections, drop from the optimizer.
OPTIMIZE_EXCLUDE = {"TreVeyon Henderson"}

# 2026 Week-1 roster + injury overlay (K169 + ESPN depth 2026-09-01)
POOL = [
    # Seattle
    {"name": "Sam Darnold", "team": "SEA", "pos": "QB", "src_team": "SEA", "role": "qb"},
    {"name": "Jadarian Price", "team": "SEA", "pos": "RB", "src_team": None, "role": "rb1_rookie"},
    {"name": "George Holani", "team": "SEA", "pos": "RB", "src_team": "SEA", "role": "rb2"},
    {"name": "Jaxon Smith-Njigba", "team": "SEA", "pos": "WR", "src_team": "SEA", "role": "wr1"},
    {"name": "Cooper Kupp", "team": "SEA", "pos": "WR", "src_team": "SEA", "role": "wr2"},
    {"name": "Rashid Shaheed", "team": "SEA", "pos": "WR", "src_team": "NO", "role": "wr3"},
    {"name": "AJ Barner", "team": "SEA", "pos": "TE", "src_team": "SEA", "role": "te1"},
    {"name": "Jason Myers", "team": "SEA", "pos": "K", "src_team": "SEA", "role": "k"},
    {"name": "Seahawks", "team": "SEA", "pos": "DST", "src_team": None, "role": "dst"},
    # New England
    {"name": "Drake Maye", "team": "NE", "pos": "QB", "src_team": "NE", "role": "qb"},
    {"name": "Rhamondre Stevenson", "team": "NE", "pos": "RB", "src_team": "NE", "role": "rb1"},
    {"name": "TreVeyon Henderson", "team": "NE", "pos": "RB", "src_team": "NE", "role": "rb2_q"},
    {"name": "A.J. Brown", "team": "NE", "pos": "WR", "src_team": "PHI", "role": "wr1_new"},
    {"name": "Romeo Doubs", "team": "NE", "pos": "WR", "src_team": "GB", "role": "wr2_new"},
    {"name": "DeMario Douglas", "team": "NE", "pos": "WR", "src_team": "NE", "role": "wr3"},
    {"name": "Mack Hollins", "team": "NE", "pos": "WR", "src_team": "NE", "role": "wr4"},
    {"name": "Hunter Henry", "team": "NE", "pos": "TE", "src_team": "NE", "role": "te1"},
    {"name": "Andy Borregales", "team": "NE", "pos": "K", "src_team": "NE", "role": "k"},
    {"name": "Patriots", "team": "NE", "pos": "DST", "src_team": None, "role": "dst"},
]

# Role priors when 2025 usage is missing or the player changed teams.
ROLE_PRIORS = {
    "qb": {"tgt": 0.0, "carry": 0.10, "ypa": 7.3, "ypc": 5.5, "td_rate": 0.048, "int_rate": 0.022},
    "rb1": {"tgt": 0.10, "carry": 0.42, "ypa": 0.0, "ypc": 4.3, "td_rate": 0.035, "int_rate": 0.0},
    "rb1_rookie": {"tgt": 0.08, "carry": 0.48, "ypa": 0.0, "ypc": 4.4, "td_rate": 0.038, "int_rate": 0.0},
    "rb2": {"tgt": 0.06, "carry": 0.22, "ypa": 0.0, "ypc": 4.1, "td_rate": 0.025, "int_rate": 0.0},
    "rb2_q": {"tgt": 0.08, "carry": 0.28, "ypa": 0.0, "ypc": 4.6, "td_rate": 0.030, "int_rate": 0.0},
    "wr1": {"tgt": 0.28, "carry": 0.01, "ypa": 0.0, "ypc": 0.0, "td_rate": 0.07, "int_rate": 0.0},
    "wr1_new": {"tgt": 0.26, "carry": 0.01, "ypa": 0.0, "ypc": 0.0, "td_rate": 0.065, "int_rate": 0.0},
    "wr2": {"tgt": 0.18, "carry": 0.00, "ypa": 0.0, "ypc": 0.0, "td_rate": 0.055, "int_rate": 0.0},
    "wr2_new": {"tgt": 0.17, "carry": 0.00, "ypa": 0.0, "ypc": 0.0, "td_rate": 0.055, "int_rate": 0.0},
    "wr3": {"tgt": 0.12, "carry": 0.01, "ypa": 0.0, "ypc": 0.0, "td_rate": 0.045, "int_rate": 0.0},
    "wr4": {"tgt": 0.07, "carry": 0.00, "ypa": 0.0, "ypc": 0.0, "td_rate": 0.035, "int_rate": 0.0},
    "te1": {"tgt": 0.16, "carry": 0.00, "ypa": 0.0, "ypc": 0.0, "td_rate": 0.07, "int_rate": 0.0},
    "k": {"tgt": 0.0, "carry": 0.0, "ypa": 0.0, "ypc": 0.0, "td_rate": 0.0, "int_rate": 0.0},
    "dst": {"tgt": 0.0, "carry": 0.0, "ypa": 0.0, "ypc": 0.0, "td_rate": 0.0, "int_rate": 0.0},
}


def load_pbp(season: int) -> pd.DataFrame:
    from ceminidfs.data.fetch import fetch_pbp

    return fetch_pbp(season)


def last_n_offense(pbp: pd.DataFrame, team: str, n_games: int = 8) -> pd.DataFrame:
    team_pbp = pbp.loc[pbp["posteam"] == team].copy()
    if team_pbp.empty:
        return team_pbp
    games = (
        team_pbp.groupby("game_id")["week"].max().sort_values()
    )
    keep = set(games.index[-n_games:])
    return team_pbp.loc[team_pbp["game_id"].isin(keep)]


def _col_sum(frame: pd.DataFrame, names: tuple[str, ...]) -> float:
    if frame.empty:
        return 0.0
    for name in names:
        if name in frame.columns:
            return float(pd.to_numeric(frame[name], errors="coerce").fillna(0).sum())
    return 0.0


def player_usage_from_pbp(pbp: pd.DataFrame, name: str) -> dict[str, float] | None:
    if pbp.empty or "receiver_player_name" not in pbp.columns:
        return None
    # nflverse names are often "J.Smith-Njigba"
    last = name.split()[-1].lower()
    first_i = name[0].lower()

    def _match(series: pd.Series) -> pd.Series:
        s = series.fillna("").astype(str)
        return s.str.lower().str.endswith(last) & s.str.lower().str.startswith(first_i)

    rec = pbp.loc[_match(pbp.get("receiver_player_name", pd.Series(dtype=str)))]
    rusher = pbp.loc[_match(pbp.get("rusher_player_name", pd.Series(dtype=str)))]
    passer = pbp.loc[_match(pbp.get("passer_player_name", pd.Series(dtype=str)))]

    games = set(rec["game_id"]).union(rusher["game_id"]).union(passer["game_id"])
    n_games = max(len(games), 1)

    targets = float(rec["pass_attempt"].fillna(0).sum()) if not rec.empty else 0.0
    rec_yds = _col_sum(rec, ("receiving_yards", "yards_gained"))
    rec_td = float(rec["pass_touchdown"].fillna(0).sum()) if not rec.empty else 0.0
    receptions = float(rec["complete_pass"].fillna(0).sum()) if not rec.empty else 0.0

    carries = float(rusher["rush"].fillna(0).sum()) if not rusher.empty else 0.0
    rush_yds = _col_sum(rusher, ("rushing_yards", "yards_gained"))
    rush_td = float(rusher["rush_touchdown"].fillna(0).sum()) if not rusher.empty else 0.0

    pass_att = float(passer["pass_attempt"].fillna(0).sum()) if not passer.empty else 0.0
    pass_yds = _col_sum(passer, ("passing_yards", "yards_gained"))
    pass_td = float(passer["pass_touchdown"].fillna(0).sum()) if not passer.empty else 0.0
    ints = float(passer["interception"].fillna(0).sum()) if not passer.empty else 0.0

    team_plays = pbp
    team_targets = float(team_plays["pass_attempt"].fillna(0).sum()) if not team_plays.empty else 1.0
    team_carries = float(team_plays["rush"].fillna(0).sum()) if not team_plays.empty else 1.0

    if targets + carries + pass_att < 8:
        return None

    return {
        "games": float(n_games),
        "tgt_share": targets / max(team_targets, 1.0),
        "carry_share": carries / max(team_carries, 1.0),
        "ypa": pass_yds / pass_att if pass_att else 0.0,
        "ypc": rush_yds / carries if carries else 0.0,
        "ypr": rec_yds / receptions if receptions else 11.0,
        "catch": receptions / targets if targets else 0.65,
        "td_rec_rate": rec_td / targets if targets else 0.05,
        "td_rush_rate": rush_td / carries if carries else 0.03,
        "td_pass_rate": pass_td / pass_att if pass_att else 0.045,
        "int_rate": ints / pass_att if pass_att else 0.022,
        "qb_rush_share": carries / max(team_carries, 1.0) if pass_att > 20 else 0.0,
    }


def blend(prior: float, observed: float | None, n: float, k: float) -> float:
    if observed is None:
        return prior
    return (k * prior + n * observed) / (k + n)


def kicker_points(itt: float) -> float:
    # ~1.7 FG + 0.35 XP per implied point / 7; FD FG ≈ 3.4 avg
    fg = max(1.4, itt / 10.5)
    xp = max(1.2, itt / 8.5)
    return fg * 3.3 + xp * 1.0


def project_player(row: dict, volume: dict[str, object], usage: dict[str, float] | None) -> dict:
    prior = ROLE_PRIORS[row["role"]]
    itt = float(volume["implied_total"])
    dropbacks = float(volume["dropbacks"])
    pass_att = float(volume["pass_attempts"])
    rush_att = float(volume["rush_attempts"])
    n = float(usage["games"]) if usage else 0.0

    tgt_share = blend(prior["tgt"], usage.get("tgt_share") if usage else None, n, 6.0)
    carry_share = blend(prior["carry"], usage.get("carry_share") if usage else None, n, 6.0)

    if row["pos"] == "DST":
        opp_itt = 44.5 - itt
        favorite = row["team"] == "SEA"
        stats = {
            "pass_yds": 0.0, "pass_td": 0.0, "int": 0.0,
            "rush_yds": 0.0, "rush_td": 0.0, "rec": 0.0, "rec_yds": 0.0,
            "rec_td": 0.0, "fumbles_lost": 0.0,
            "dst_sacks": 2.6 if favorite else 2.2,
            "dst_int": 0.90 if favorite else 0.75,
            "dst_fumbles_recovered": 0.55,
            "dst_td": 0.12 if favorite else 0.08,
            "dst_safety": 0.03,
            "dst_blocked_kick": 0.04,
            "dst_points_allowed": opp_itt,
        }
        fd = (
            stats["dst_sacks"] * 1.0
            + stats["dst_int"] * 2.0
            + stats["dst_fumbles_recovered"] * 2.0
            + stats["dst_td"] * 6.0
            + stats["dst_safety"] * 2.0
            + stats["dst_blocked_kick"] * 2.0
            + fd_dst_points_allowed(opp_itt)
        )
        return {
            **row,
            **{k: 0.0 for k in (
                "pass_yds", "pass_td", "int", "rush_yds", "rush_td",
                "rec", "rec_yds", "rec_td", "fumbles_lost",
            )},
            "fd_projection": round(float(fd), 2),
            "tgt_share": 0.0,
            "carry_share": 0.0,
            "usage_games": 0.0,
        }

    if row["pos"] == "QB":
        qb_carries = blend(0.10, usage.get("qb_rush_share") if usage else None, n, 8.0) * rush_att
        ypa = blend(7.25, usage.get("ypa") if usage else None, n, 8.0)
        ypc = blend(5.4, usage.get("ypc") if usage else None, n, 10.0)
        td_rate = blend(0.048, usage.get("td_pass_rate") if usage else None, n, 8.0)
        int_rate = blend(0.022, usage.get("int_rate") if usage else None, n, 10.0)
        stats = {
            "pass_yds": pass_att * ypa,
            "pass_td": pass_att * td_rate,
            "int": pass_att * int_rate,
            "rush_yds": qb_carries * ypc,
            "rush_td": qb_carries * 0.04,
            "rec": 0.0,
            "rec_yds": 0.0,
            "rec_td": 0.0,
            "fumbles_lost": 0.15,
        }
    elif row["pos"] == "K":
        stats = {k: 0.0 for k in (
            "pass_yds", "pass_td", "int", "rush_yds", "rush_td", "rec", "rec_yds", "rec_td", "fumbles_lost"
        )}
        fd = kicker_points(itt)
        return {
            **row,
            **stats,
            "fd_projection": round(fd, 2),
            "tgt_share": 0.0,
            "carry_share": 0.0,
            "usage_games": 0.0,
        }
    else:
        targets = tgt_share * pass_att
        carries = carry_share * rush_att
        catch = blend(0.66, usage.get("catch") if usage else None, n, 8.0)
        ypr = blend(12.0 if row["pos"] == "WR" else 9.5, usage.get("ypr") if usage else None, n, 8.0)
        ypc = blend(4.4, usage.get("ypc") if usage else None, n, 10.0)
        rec_td_rate = blend(0.06, usage.get("td_rec_rate") if usage else None, n, 10.0)
        rush_td_rate = blend(0.032, usage.get("td_rush_rate") if usage else None, n, 10.0)
        stats = {
            "pass_yds": 0.0,
            "pass_td": 0.0,
            "int": 0.0,
            "rush_yds": carries * ypc,
            "rush_td": carries * rush_td_rate,
            "rec": targets * catch,
            "rec_yds": targets * catch * ypr,
            "rec_td": targets * rec_td_rate,
            "fumbles_lost": 0.08 if row["pos"] == "RB" else 0.04,
        }

    fd = fd_points(stats)
    return {
        **row,
        **stats,
        "fd_projection": round(float(fd), 2),
        "tgt_share": round(tgt_share, 3),
        "carry_share": round(carry_share, 3),
        "usage_games": n,
    }


def apply_live_salaries(rows: list[dict]) -> list[dict]:
    """Attach official FanDuel single-game salaries. Drop anyone without a price."""

    priced = []
    missing = []
    for row in rows:
        salary = FD_SALARIES.get(row["name"])
        if salary is None:
            missing.append(row["name"])
            continue
        priced.append({**row, "salary": salary})
    if missing:
        print("  no live salary (skipped): " + ", ".join(missing))
    return priced


def write_fd_csv(rows: list[dict], path: Path) -> Path:
    """Human-readable FLEX salary sheet (not the optimizer input)."""

    headers = [
        "Id", "First Name", "Last Name", "Position", "Team", "Opponent",
        "Game", "SalaryFlex", "SalaryMVP", "FPPG", "Injury Indicator",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for i, row in enumerate(rows, start=1):
            parts = row["name"].split(" ", 1)
            first, last = parts[0], parts[1] if len(parts) > 1 else ""
            opp = "NE" if row["team"] == "SEA" else "SEA"
            writer.writerow({
                "Id": f"{10000 + i}",
                "First Name": first,
                "Last Name": last,
                "Position": row["pos"],
                "Team": row["team"],
                "Opponent": opp,
                "Game": GAME,
                "SalaryFlex": row["salary"],
                "SalaryMVP": int(round(row["salary"] * 1.5)),
                "FPPG": row["fd_projection"],
                "Injury Indicator": "Q" if row["role"].endswith("_q") else "",
            })
    return path


def write_optimizer_csv(rows: list[dict], path: Path) -> Path:
    """DK captain-mode CSV: CPT row already at 1.5x salary; FPPG is base (importer * 1.5)."""

    headers = [
        "Position", "Name + ID", "Name", "ID", "Roster Position",
        "Salary", "Game Info", "TeamAbbrev", "AvgPointsPerGame",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        pid = 10000
        for row in rows:
            pid += 1
            flex = int(row["salary"])
            mvp = int(round(flex * 1.5))
            fppg = float(row["fd_projection"])
            name = row["name"]
            team = row["team"]
            pos = "DST" if row["pos"] == "DST" else row["pos"]
            game = "NE@SEA 09/09/2026 08:20PM ET"
            for roster, salary in (("CPT", mvp), ("FLEX", flex)):
                writer.writerow({
                    "Position": pos,
                    "Name + ID": f"{name} ({pid})",
                    "Name": name,
                    "ID": str(pid),
                    "Roster Position": roster,
                    "Salary": salary,
                    "Game Info": game,
                    "TeamAbbrev": team,
                    "AvgPointsPerGame": fppg,
                })
    return path


def optimize(csv_path: Path, count: int = 8) -> list[dict]:
    # CeminiDFS library path now exists: ceminidfs export.optimize with
    # site=fanduel_showdown encodes these same rules (see PLAN.md "Build vs borrow").
    from pydfs_lineup_optimizer import Site, Sport, get_optimizer
    from pydfs_lineup_optimizer.stacks import GameStack

    # Current FanDuel single-game == DK captain structure at $60k.
    opt = get_optimizer(Site.DRAFTKINGS_CAPTAIN_MODE, Sport.FOOTBALL)
    opt.settings.budget = 60000
    opt.settings.max_from_one_team = 5
    opt.load_players_from_csv(str(csv_path))
    opt.set_min_salary_cap(56000)
    try:
        opt.add_stack(GameStack(6, min_from_team=1))
    except Exception:
        pass
    lineups = list(opt.optimize(n=count, max_exposure=0.70))
    out = []
    for lu in lineups:
        mvp = next(p for p in lu.players if p.lineup_position == "CPT")
        util = [p for p in lu.players if p.lineup_position != "CPT"]
        out.append({
            "mvp": mvp.full_name,
            "mvp_team": mvp.team,
            "util": [p.full_name for p in util],
            "salary": int(lu.salary_costs),
            "proj": round(float(lu.fantasy_points_projection), 2),
        })
    return out


def main() -> int:
    print("Loading 2025 PBP…")
    pbp = load_pbp(2025)
    print(f"  {len(pbp)} plays")

    itt = implied_totals_from_favorite(TOTAL, SEA_SPREAD)
    print(f"ITT SEA {itt.favorite:.1f} / NE {itt.underdog:.1f}  (total {TOTAL}, SEA {SEA_SPREAD})")

    sea_sec = neutral_seconds_per_play(pbp, "SEA") or LEAGUE_SEC_PER_PLAY
    ne_sec = neutral_seconds_per_play(pbp, "NE") or LEAGUE_SEC_PER_PLAY
    sea_proe = neutral_proe(pbp, "SEA")
    ne_proe = neutral_proe(pbp, "NE")
    volumes = {
        "SEA": project_team_volume(
            2026, 1, "SEA", "NE",
            implied_total=itt.favorite,
            game_total=TOTAL,
            spread_team=SEA_SPREAD,
            team_sec=sea_sec,
            opp_sec=ne_sec,
            neutral_proe=sea_proe,
        ).to_dict(),
        "NE": project_team_volume(
            2026, 1, "NE", "SEA",
            implied_total=itt.underdog,
            game_total=TOTAL,
            spread_team=-SEA_SPREAD,
            team_sec=ne_sec,
            opp_sec=sea_sec,
            neutral_proe=ne_proe,
        ).to_dict(),
    }
    for team, v in volumes.items():
        if not v.get("pass_attempts"):
            alloc = allocate_play_volume(
                float(v.get("plays_projected") or PLAYS_INTERCEPT),
                float(v.get("pass_rate") or BASE_PASS_RATE),
                sack_rate=DEFAULT_SACK_RATE,
                scramble_rate=DEFAULT_SCRAMBLE_RATE,
            )
            v.update(alloc)
        print(
            f"  {team} plays={v['plays_projected']:.1f} pass_att={v['pass_attempts']:.1f} "
            f"rush={v['rush_attempts']:.1f} pass_rate={v['pass_rate']:.3f} "
            f"pace={v['team_sec_per_play']:.1f}s PROE={v['neutral_proe']:.1f}"
        )

    projected = []
    for row in POOL:
        src = row["src_team"]
        hist = last_n_offense(pbp, src, 8) if src else pbp.iloc[0:0]
        usage = player_usage_from_pbp(hist, row["name"]) if src else None
        projected.append(project_player(row, volumes[row["team"]], usage))

    projected = apply_live_salaries(projected)
    projected.sort(key=lambda r: r["fd_projection"], reverse=True)

    proj_path = OUT_DIR / "projections.json"
    proj_path.write_text(json.dumps(projected, indent=2), encoding="utf-8")
    csv_path = write_fd_csv(projected, OUT_DIR / "fd_single_game_live.csv")
    opt_rows = [row for row in projected if row["name"] not in OPTIMIZE_EXCLUDE]
    opt_csv = write_optimizer_csv(opt_rows, OUT_DIR / "fd_single_game_optimize.csv")
    print(f"Wrote {csv_path}")

    print("\nPlayer pool (FLEX $ / MVP $ / CeminiDFS proj)")
    for row in projected:
        mvp_sal = int(round(row["salary"] * 1.5))
        print(
            f"  {row['fd_projection']:5.1f}  FLEX ${row['salary']:>5}  MVP ${mvp_sal:>5}  "
            f"{row['name']:<22} {row['team']} {row['pos']}  "
            f"tgt={row['tgt_share']:.2f} car={row['carry_share']:.2f}  n={row['usage_games']:.0f}"
        )

    lineups = optimize(opt_csv, count=8)
    (OUT_DIR / "lineups.json").write_text(json.dumps(lineups, indent=2), encoding="utf-8")
    print("\nOptimizer lineups")
    for i, lu in enumerate(lineups, start=1):
        print(
            f"  {i:2}  MVP {lu['mvp']:<22} | "
            + ", ".join(lu["util"])
            + f"  ${lu['salary']}  {lu['proj']:.1f}"
        )

    env = {
        "game": "NE @ SEA",
        "kickoff": "2026-09-09T20:20:00-04:00",
        "total": TOTAL,
        "spread_home": SEA_SPREAD,
        "itt_sea": itt.favorite,
        "itt_ne": itt.underdog,
        "salary_note": "FanDuel lobby 2026-09-01 19:30 ET; FLEX=1x, MVP=1.5x salary+points; 6-man $60k",
        "format": {"mvp": 6, "flex": 5, "mvp_salary_mult": 1.5, "cap": 60000},
        "optimize_exclude": sorted(OPTIMIZE_EXCLUDE),
        "sources": [
            "CeminiDFS volume/usage/scoring",
            "nflverse 2025 PBP last 8",
            "K169 week-1 roster brief",
            "ESPN depth 2026-09-01",
            "FanDuel app lobby salaries 2026-09-01 19:30 ET",
            "DFF Vegas SEA -4.5 / 44.5",
        ],
        "volumes": volumes,
    }
    (OUT_DIR / "environment.json").write_text(json.dumps(env, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
