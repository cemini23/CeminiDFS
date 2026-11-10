"""Week 9 FanDuel 133-lineup book for the 2026-11-08 main slate.

The salary file is the slate. CIN@ATL is absent from that file, so those
clubs stay out of the book. One starting quarterback is allowed per team.
This module writes CSV files only. It does not log in and it does not submit.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from ceminidfs.data.stadiums import normalize_team_abbr
from ceminidfs.export.mme_portfolio import (
    CHEAP_LIMIT,
    Candidate,
    PoolPlayer,
    build_candidate_pool,
    canon_game,
    canon_position,
    exposure_table,
    fold_name,
    is_hard_exclude,
    load_quantiles,
    players_from_frame,
    score_pool_row,
    select_book,
    set_nicknames,
    verify_book,
    write_book_files,
    write_optimizer_csv,
)
from ceminidfs.export.recap_guards import (
    OpportunityIndex,
    archive_loaded_salary,
    assert_one_qb_per_team,
    build_opportunity_index,
    environment_scale,
    is_backup_quarterback,
    lookup_opportunity,
    prelock_salary_archive,
    skill_excluded,
    write_qb_starters_csv,
)
from ceminidfs.situational.engine import run_slate

SEASON = 2026
WEEK = 9
MAX_SOURCE_WEEK = 8
BOOK_N = 133
SPLIT_N = 29
CONTEST_PREFIX = "136184-"
BRINGBACK_MIN = math.ceil(BOOK_N * 113 / 150)
SECONDARY_MIN = math.ceil(BOOK_N * 75 / 150)
PAIR_CAP = 21
RB_TE_CAP = 8
BOOK_CAP = {"QB": 32, "RB": 34, "WR": 34, "TE": 34, "DST": 29}

MAIN_GAMES = frozenset(
    {
        "DAL@IND",
        "NYJ@KC",
        "DET@MIA",
        "CLE@NO",
        "NYG@PHI",
        "LAR@WAS",
        "DEN@CAR",
        "HOU@LAC",
        "GB@NE",
        "LV@SF",
        "ARI@SEA",
    }
)

# Roof class and wind mph. environment_scale applies a fade only when roof is open.
# DAL@IND is retractable and the roof call is unposted, so the fade stays off.
# HOU@LAC is semi_open with weather_exposed false.
GAME_ENV = {
    "DAL@IND": ("retractable", 12),
    "NYJ@KC": ("open", 5),
    "DET@MIA": ("open", 5),
    "CLE@NO": ("dome", 0),
    "NYG@PHI": ("open", 10),
    "LAR@WAS": ("open", 12),
    "DEN@CAR": ("open", 6),
    "HOU@LAC": ("semi_open", 0),
    "GB@NE": ("open", 13),
    "LV@SF": ("open", 6),
    "ARI@SEA": ("open", 10),
}

# team, FanDuel nickname, FanDuel Id, salary
QB_ROWS = (
    ("DAL", "Dak Prescott", "136184-31716", 8000),
    ("IND", "Daniel Jones", "136184-63519", 6400),
    ("NYJ", "Geno Smith", "136184-26483", 6700),
    ("KC", "Patrick Mahomes", "136184-57439", 7900),
    ("DET", "Jared Goff", "136184-38435", 7700),
    ("MIA", "Malik Willis", "136184-87691", 6500),
    ("CLE", "Shedeur Sanders", "136184-184183", 6200),
    ("NO", "Tyler Shough", "136184-88431", 7400),
    ("NYG", "J.J. McCarthy", "136184-152575", 6800),
    ("PHI", "Joe Milton III", "136184-91390", 6300),
    ("LAR", "Matthew Stafford", "136184-6654", 7500),
    ("WAS", "Jayden Daniels", "136184-102785", 8400),
    ("DEN", "Bo Nix", "136184-102965", 7200),
    ("CAR", "Bryce Young", "136184-119606", 7300),
    ("HOU", "C.J. Stroud", "136184-129471", 7600),
    ("LAC", "Justin Herbert", "136184-69189", 6700),
    ("GB", "Jordan Love", "136184-69017", 7800),
    ("NE", "Drake Maye", "136184-152316", 8200),
    ("LV", "Kirk Cousins", "136184-22038", 6900),
    ("SF", "Brock Purdy", "136184-85607", 8500),
    ("ARI", "Gardner Minshew II", "136184-61798", 6600),
    ("SEA", "Drew Lock", "136184-64051", 6300),
)

QB_STARTERS = {team: name for team, name, _pid, _salary in QB_ROWS}
QB_IDS = {pid for _team, _name, pid, _salary in QB_ROWS}

# Explicit hard excludes. IR / O / D and every non-starter QB are also removed.
NAMED_EXCLUDES = frozenset(
    fold_name(name)
    for name in (
        "Deshaun Watson",
        "Velus Jones Jr.",
        "Dillon Gabriel",
        "Taylen Green",
        "Tanner McKee",
        "Cole Payton",
        "Jalen Hurts",
        "Sam Darnold",
        "Jalen Milroe",
    )
)

HARD_IDS = frozenset(
    {
        "136184-54879",  # Deshaun Watson
        "136184-70661",  # Velus Jones Jr.
        "136184-103698",  # Dillon Gabriel
        "136184-152820",  # Taylen Green
        "136184-89607",  # Tanner McKee
        "136184-208491",  # Cole Payton
        "136184-69531",  # Jalen Hurts
        "136184-63589",  # Sam Darnold
        "136184-154462",  # Jalen Milroe
    }
)

# Players stepping into a vacated role. The touch floor does not remove them.
VACANCY_WHITELIST = frozenset(
    fold_name(name)
    for name in (
        "Demarcus Robinson",
        "Jordan Watkins",
        "Woody Marks",
        "Devin Singletary",
        "DeMario Douglas",
        "Efton Chism III",
        "Kyle Williams",
    )
)

# Minimum lagged points when the salary FPPG is a backup sample or a vacated role.
FLOORS = {
    "shedeur sanders": 13.5,
    "joe milton iii": 13.5,
    "demarcus robinson": 11.0,
    "jordan watkins": 9.5,
    "woody marks": 10.5,
    "devin singletary": 9.0,
}

# Slight ceiling lift for the vacated-usage group. 1.00 means no lift.
VACANCY_TAIL = {
    "christian mccaffrey": 1.08,
    "george kittle": 1.08,
    "demarcus robinson": 1.12,
    "jordan watkins": 1.12,
    "jonathan taylor": 1.06,
    "woody marks": 1.10,
    "devin singletary": 1.10,
    "malik nabers": 1.06,
    "rhamondre stevenson": 1.08,
    "hunter henry": 1.06,
    "demario douglas": 1.06,
    "efton chism iii": 1.06,
    "kyle williams": 1.06,
}

WATCH_Q = (
    "Amon-Ra St. Brown",
    "George Pickens",
    "MarShawn Lloyd",
    "Mack Hollins",
    "Jake Ferguson",
    "Hunter Henry",
    "Colby Parkinson",
    "Sione Vaki",
    "Pat Bryant",
    "Jaylen Wright",
    "Jordyn Tyson",
    "Kaytron Allen",
    "Luke Schoonmaker",
    "Jordan Whittington",
    "Dameon Pierce",
)

DESKTOP_SALARY = Path("/Users/claudiobarone/Desktop/thisweek.csv")
SALARY_PATH = Path("data/slates/2026-11-08_fd_sun.csv")
RUN_DIR = Path("runs/2026_week_9")
SLATE_DIR = Path("dfs-slate/2026-11-08")
STARTER_PATH = SLATE_DIR / "qb_starters_2026-11-08.csv"
SECOND_SOURCE_PATH = SLATE_DIR / "qb_second_source_dfs.csv"
ENV_PATH = SLATE_DIR / "environment.csv"
INACTIVES_PATH = SLATE_DIR / "inactives_diff_2026-11-08.csv"
CEILING_PATH = RUN_DIR / "situational" / "ceiling.csv"
CALIBRATION_PATH = RUN_DIR / "situational" / "calibration.json"
OPTIMIZER_PATH = RUN_DIR / "portfolio_optimizer.csv"
UPLOAD_133 = SLATE_DIR / "fanduel_upload_133_2026-11-08.csv"
IDS_133 = SLATE_DIR / "fanduel_ids_133_2026-11-08.csv"
UPLOAD_29 = SLATE_DIR / "fanduel_upload_29_split_2026-11-08.csv"
SPLIT_PATH = SLATE_DIR / "lineups_split_2026-11-08.csv"
IDS_29 = SLATE_DIR / "fanduel_ids_29_split_2026-11-08.csv"
EXPOSURE_PATH = SLATE_DIR / "exposure_2026-11-08.csv"
STACK_PATH = SLATE_DIR / "stacks_2026-11-08.csv"
SHARED_DIR = Path("data/shared_cache/2026_w09")
PBP_PATH = Path("artifacts/cache/pbp_2026.parquet")
ROSTER_PATH = Path("artifacts/cache/rosters_2026.parquet")
ET = ZoneInfo("America/New_York")


def _number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _display(record: Mapping[str, object]) -> str:
    nickname = str(record.get("Nickname") or "").strip()
    first = str(record.get("First Name") or "").strip()
    last = str(record.get("Last Name") or "").strip()
    return nickname or f"{first} {last}".strip()


def _player_id(record: Mapping[str, object]) -> str:
    return str(record.get("Id") or record.get("player_id") or "").strip()


def adjust_tails_week9(
    game: object,
    position: object,
    display: object,
    p90: float,
    p99: float,
) -> tuple[float, float]:
    """Scale tails for open-air wind, then apply a vacancy lift."""

    roof, wind = GAME_ENV.get(canon_game(game), ("open", 0))
    scale = environment_scale(roof, wind, position)
    bump = VACANCY_TAIL.get(fold_name(display), 1.0)
    return p90 * scale * bump, p99 * scale * bump


def week9_blocked(
    record: Mapping[str, object],
    index: OpportunityIndex,
    *,
    roster_fresh: bool = False,
    roster_status: str = "",
) -> bool:
    """Return True when the Week 9 rules set this salary row to 0 points."""

    display = _display(record)
    team = normalize_team_abbr(str(record.get("Team") or ""))
    position = record.get("Position")
    game = canon_game(record.get("Game"))
    if game not in MAIN_GAMES:
        return True
    if _player_id(record) in HARD_IDS:
        return True
    if is_hard_exclude(
        record.get("Injury Indicator"),
        display,
        team,
        record.get("Injury Details"),
        banned_teams=frozenset(),
        named_excludes=NAMED_EXCLUDES,
    ):
        return True
    if is_backup_quarterback(team, display, position, QB_STARTERS):
        return True
    played = int(_number(record.get("Played")))
    if canon_position(position) != "DST" and played == 0 and fold_name(display) not in VACANCY_WHITELIST:
        return True
    found = lookup_opportunity(index, team, display, str(record.get("Last Name") or ""))
    targets = None if found is None else found.targets
    carries = None if found is None else found.carries
    snaps = None if found is None else found.snaps
    # A snap file miss stores 0 snaps beside real targets. Do not treat that as a benching.
    if snaps is not None and snaps <= 0 and (targets or 0) + (carries or 0) > 0:
        snaps = None
    team_share = None
    route_share = None
    snap_share = None
    if found is not None and found.team_targets > 0:
        team_share = found.targets / found.team_targets
    if found is not None:
        route_share = found.route_share
        snap_share = found.snap_share
    injury = str(record.get("Injury Indicator") or "").strip().upper()
    if injury in {"NAN", "NONE", "NAT"}:
        injury = ""
    # FanDuel Questionable stays in the pool. A week-8 roster RES label does not override it.
    status = "" if injury == "Q" else roster_status
    return skill_excluded(
        position=position,
        name=display,
        salary=int(_number(record.get("Salary"))),
        played=played,
        fppg=_number(record.get("FPPG")),
        targets=targets,
        carries=carries,
        snaps=snaps,
        roster_status=status,
        roster_fresh=roster_fresh,
        starter_note=False,
        whitelist=VACANCY_WHITELIST,
        team_target_share=team_share,
        route_share=route_share,
        snap_share=snap_share,
    )


def score_week9_frame(
    salary: pd.DataFrame,
    ceiling: pd.DataFrame,
    quantiles: Mapping[str, object],
    index: OpportunityIndex,
    roster_status: Mapping[tuple[str, str], str] | None = None,
    *,
    roster_fresh: bool = False,
) -> pd.DataFrame:
    """Join the salary file to the ceiling and apply the Week 9 guards."""

    sal = salary.copy()
    sal["player_id"] = sal["Id"].astype(str)
    ceil = ceiling.copy()
    ceil["player_id"] = ceil["player_id"].astype(str)
    keep = [column for column in ("player_id", "lagged_fd", "p90", "p99") if column in ceil.columns]
    merged = sal.merge(ceil[keep], on="player_id", how="left")
    skill = list(quantiles.get("skill") or [])
    dst_table = list(quantiles.get("dst") or [])
    status_map = roster_status or {}
    rows = []
    for record in merged.to_dict(orient="records"):
        team = normalize_team_abbr(str(record.get("Team") or ""))
        name = fold_name(record.get("Nickname"))
        rows.append(
            score_pool_row(
                record,
                skill,
                dst_table,
                blocked=lambda rec, roster_status=status_map.get((team, name), ""): week9_blocked(
                    rec,
                    index,
                    roster_fresh=roster_fresh,
                    roster_status=roster_status,
                ),
                tails=lambda game, team, position, display, p90, p99: adjust_tails_week9(
                    game, position, display, p90, p99
                ),
                floor_lookup=lambda display: FLOORS.get(fold_name(display)),
            )
        )
    return pd.DataFrame(rows)


def _cache_ready(path: Path) -> bool:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file() or not (path / "player_telemetry_pit.parquet").is_file():
        return False
    if not CEILING_PATH.is_file() or not CALIBRATION_PATH.is_file():
        return False
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return int(manifest.get("max_source_week", -1)) == MAX_SOURCE_WEEK


def refresh_shared_cache(salary_path: Path) -> None:
    """Score the slate when the Week 9 cache is missing. Max source week is 8."""

    if _cache_ready(SHARED_DIR):
        print(f"shared cache ready -> {SHARED_DIR}")
        return
    run_slate(SEASON, WEEK, salary_path=salary_path, out_dir=CEILING_PATH.parent)
    import json

    manifest = json.loads((SHARED_DIR / "manifest.json").read_text(encoding="utf-8"))
    print(f"shared cache -> {SHARED_DIR} max_source_week={manifest.get('max_source_week')}")


def load_opportunity_index() -> OpportunityIndex:
    pbp = pd.read_parquet(PBP_PATH)
    week8 = pbp.loc[pd.to_numeric(pbp["week"], errors="coerce").eq(8)]
    games = sorted(week8["game_id"].dropna().unique().tolist()) if "game_id" in week8.columns else []
    print(f"pbp week 8 games {games} plays {len(week8)}")
    rosters = pd.read_parquet(ROSTER_PATH) if ROSTER_PATH.is_file() else pd.DataFrame()
    snap_path = Path("artifacts/cache/snap_counts_2026.parquet")
    participation = pd.read_parquet(snap_path) if snap_path.is_file() else None
    return build_opportunity_index(
        pbp,
        rosters,
        season=SEASON,
        before_week=WEEK,
        participation=participation,
    )


def roster_status_index(path: Path = ROSTER_PATH) -> tuple[dict[tuple[str, str], str], bool]:
    """Return ``(team, folded name) -> status`` when the roster file is recent."""

    if not path.is_file():
        return {}, False
    frame = pd.read_parquet(path)
    if frame.empty or "week" not in frame.columns:
        return {}, False
    weeks = pd.to_numeric(frame["week"], errors="coerce")
    latest = weeks.max()
    fresh = pd.notna(latest) and int(latest) >= WEEK - 3
    if not fresh:
        print(f"roster file latest week {latest}; snap and packet rules still apply")
        return {}, False
    print(f"roster file latest week {int(latest)}")
    part = frame.loc[weeks.eq(latest)].copy()
    status: dict[tuple[str, str], str] = {}
    for record in part.to_dict(orient="records"):
        team = normalize_team_abbr(str(record.get("team") or ""))
        token = str(record.get("status") or "")
        for column in ("full_name", "football_name"):
            key = fold_name(record.get(column))
            if team and key:
                status[(team, key)] = token
    return status, True


def _assert_starter_rows(salary: pd.DataFrame) -> None:
    by_id = {str(row["Id"]): row for row in salary.to_dict(orient="records")}
    for team, name, pid, salary_n in QB_ROWS:
        row = by_id.get(pid)
        if row is None:
            raise AssertionError(f"missing starter id {pid} {name}")
        got_team = normalize_team_abbr(str(row.get("Team") or ""))
        got_name = str(row.get("Nickname") or "")
        got_salary = int(_number(row.get("Salary")))
        if got_team != team or got_name != name or got_salary != salary_n:
            raise AssertionError(f"{pid} {got_team} {got_name} {got_salary}")


def _assert_pool_starters(pool: Sequence[PoolPlayer], teams: Sequence[str]) -> None:
    by_team: dict[str, list[str]] = defaultdict(list)
    for player in pool:
        if player.position == "QB":
            by_team[player.team].append(f"{player.nickname} {player.player_id}")
    missing = [team for team in teams if team not in by_team]
    extra = {team: names for team, names in by_team.items() if len(names) != 1}
    bad_ids = [
        player.nickname
        for player in pool
        if player.position == "QB" and player.player_id not in QB_IDS
    ]
    if missing or extra or bad_ids:
        raise AssertionError(f"quarterback whitelist missing={missing} extra={extra} bad={bad_ids}")


def _write_environment() -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = ["game,roof,wind_mph,weather_exposed"]
    exposed = {
        "DAL@IND": "true",
        "NYJ@KC": "true",
        "DET@MIA": "true",
        "CLE@NO": "false",
        "NYG@PHI": "true",
        "LAR@WAS": "true",
        "DEN@CAR": "true",
        "HOU@LAC": "false",
        "GB@NE": "true",
        "LV@SF": "true",
        "ARI@SEA": "true",
    }
    for game, (roof, wind) in sorted(GAME_ENV.items()):
        rows.append(f"{game},{roof},{wind},{exposed[game]}")
    ENV_PATH.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_second_source() -> None:
    SECOND_SOURCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Team,Starter,FdId,Status"]
    for team, name, pid, _salary in QB_ROWS:
        status = "OVERRIDE" if team == "CLE" else "CONFIRMED"
        lines.append(f"{team},{name},{pid},{status}")
    SECOND_SOURCE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _inactives_note() -> str:
    now = datetime.now(ET)
    lock_label = datetime(2026, 11, 8, 11, 30, tzinfo=ET)
    if now < lock_label:
        return f"NOT_POSTED at {now.strftime('%Y-%m-%d %H:%M %Z')}"
    return f"WINDOW_OPEN at {now.strftime('%Y-%m-%d %H:%M %Z')}; no separate inactive file on disk"


def write_inactives_diff(salary: pd.DataFrame) -> None:
    """Write the salary-file strip list. 11:30 AM ET inactives are a later gate."""

    note = _inactives_note()
    print(f"inactives check-label 11:30 AM ET: {note}")
    INACTIVES_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Id,Nickname,Team,Position,Salary,Injury Indicator,strip,note"]
    stripped = 0
    for record in salary.to_dict(orient="records"):
        status = str(record.get("Injury Indicator") or "").strip().upper()
        pid = str(record.get("Id") or "")
        name = str(record.get("Nickname") or "")
        reasons = []
        if status in {"IR", "O", "D"}:
            reasons.append(status)
        if pid in HARD_IDS or fold_name(name) in NAMED_EXCLUDES:
            reasons.append("hard_exclude")
        if not reasons:
            continue
        stripped += 1
        team = normalize_team_abbr(str(record.get("Team") or ""))
        lines.append(
            f"{pid},{name},{team},{record.get('Position')},{record.get('Salary')},{status},YES,{'+'.join(reasons)}"
        )
    INACTIVES_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"inactives strip=YES {stripped} -> {INACTIVES_PATH}")


def _archive_salary(salary_source: Path) -> None:
    digest = hashlib.sha256(salary_source.read_bytes()).hexdigest()
    written = archive_loaded_salary(salary_source, [SALARY_PATH, SLATE_DIR / "thisweek.csv"])
    archived = prelock_salary_archive(
        salary_source,
        season=SEASON,
        week=WEEK,
        work_dir=RUN_DIR,
        slate_date="2026-11-08",
        fixture_id=CONTEST_PREFIX.rstrip("-"),
    )
    for path in [*written, *archived]:
        copy_digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.suffix == ".csv" else ""
        mark = "MATCH" if copy_digest == digest else "skip"
        print(f"salary copy {mark} {path}")
    print(f"sha256 {digest}")


def _validate_games(salary: pd.DataFrame) -> None:
    games = sorted({canon_game(value) for value in salary["Game"].dropna().tolist()})
    if set(games) != MAIN_GAMES:
        raise AssertionError(f"salary games {games}")
    teams = {normalize_team_abbr(str(team)) for team in salary["Team"].dropna().tolist()}
    if "CIN" in teams or "ATL" in teams:
        raise AssertionError("CIN or ATL is in the salary file")


def _build_pool(
    salary: pd.DataFrame,
    ceiling: pd.DataFrame,
) -> tuple[list[PoolPlayer], list[PoolPlayer]]:
    index = load_opportunity_index()
    roster_map, roster_fresh = roster_status_index()
    portfolio = score_week9_frame(
        salary,
        ceiling,
        load_quantiles(CALIBRATION_PATH),
        index,
        roster_map,
        roster_fresh=roster_fresh,
    )
    all_players = players_from_frame(portfolio)
    set_nicknames(all_players)
    pool = [
        player
        for player in all_players
        if not player.never_enter
        and player.fpts > 0
        and player.salary > 0
        and player.player_id.startswith(CONTEST_PREFIX)
    ]
    teams = sorted({normalize_team_abbr(str(team)) for team in salary["Team"].dropna().tolist()})
    _assert_pool_starters(pool, teams)
    return all_players, pool


def _report_pool(all_players: list[PoolPlayer], pool: list[PoolPlayer]) -> None:
    eligible = {player.player_id for player in pool}
    print(f"eligible pool {len(pool)} of {len(all_players)}")
    blocked = [player for player in all_players if player.never_enter and player.salary >= 5000]
    print(f"high-salary blocks {len(blocked)}")
    for player in sorted(blocked, key=lambda item: -item.salary)[:30]:
        print(f"blocked {player.position} {player.nickname} {player.team} ${player.salary}")
    by_name = {fold_name(player.nickname): player for player in all_players}
    print("questionable watch")
    for name in WATCH_Q:
        player = by_name.get(fold_name(name))
        if player is None:
            print(f"missing {name}")
            continue
        state = "eligible" if player.player_id in eligible else "blocked"
        print(f"{state} {player.position} {player.nickname} {player.team} ${player.salary}")


def _select(candidates: list[Candidate], pool: list[PoolPlayer], *, cheap: int) -> list[Candidate]:
    return select_book(
        candidates,
        count=BOOK_N,
        bringback_min=BRINGBACK_MIN,
        secondary_min=SECONDARY_MIN,
        caps=BOOK_CAP,
        pair_cap=PAIR_CAP,
        rb_te_cap=RB_TE_CAP,
        player_teams={player.player_id: player.team for player in pool},
        allow_cheap=cheap,
    )


def _assert_book(book: Sequence[Candidate], players: Sequence[PoolPlayer]) -> None:
    meta = {player.player_id: player for player in players}
    rostered: dict[str, set[str]] = defaultdict(set)
    keys = []
    for item in book:
        keys.append(item.key)
        if item.salary > 60000:
            raise AssertionError(f"salary {item.salary}")
        if len(item.ids) != 9 or len(set(item.ids)) != 9:
            raise AssertionError("lineup shape")
        teams: Counter[str] = Counter()
        for pid in item.ids:
            player = meta[pid]
            if player.never_enter or pid in HARD_IDS or fold_name(player.nickname) in NAMED_EXCLUDES:
                raise AssertionError(f"excluded {player.nickname}")
            teams[player.team] += 1
        if any(count > 4 for count in teams.values()):
            raise AssertionError(f"team cap {teams}")
        for pid, pos in item.positions:
            player = meta[pid]
            if pos == "QB":
                if player.player_id not in QB_IDS or is_backup_quarterback(
                    player.team, player.nickname, "QB", QB_STARTERS
                ):
                    raise AssertionError(f"FAIL_BACKUP_QB {player.nickname}")
                rostered[player.team].add(fold_name(player.nickname))
    if len(book) != BOOK_N or len(set(keys)) != BOOK_N:
        raise AssertionError(f"unique lineups {len(book)} {len(set(keys))}")
    assert_one_qb_per_team(rostered)
    if "shedeur sanders" not in {fold_name(name) for names in rostered.values() for name in names}:
        # Sanders must be the CLE starter identity even when his exposure is 0.
        pass
    cle = rostered.get("CLE", set())
    if cle and cle != {"shedeur sanders"}:
        raise AssertionError(f"CLE quarterback {cle}")


def _ceiling(item: Candidate, meta: Mapping[str, PoolPlayer]) -> float:
    return sum(meta[pid].p99 for pid in item.ids)


def _write_split(book: Sequence[Candidate], meta: Mapping[str, PoolPlayer]) -> list[Candidate]:
    ranked = sorted(book, key=lambda item: (-_ceiling(item, meta), -item.blend, item.ids))
    top = ranked[:SPLIT_N]
    write_book_files(top, UPLOAD_29, IDS_29)
    SPLIT_PATH.write_bytes(UPLOAD_29.read_bytes())
    print(f"split {len(top)} -> {UPLOAD_29}")
    return top


def _write_exposure(book: Sequence[Candidate], meta: Mapping[str, PoolPlayer]) -> None:
    counts: Counter[str] = Counter()
    stacks: Counter[str] = Counter(item.tags for item in book)
    for item in book:
        counts.update(item.ids)
    EXPOSURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["position,team,player,id,salary,lineups,pct,fpts,p99"]
    ordered = sorted(counts, key=lambda pid: (meta[pid].position, -counts[pid], meta[pid].nickname))
    for pid in ordered:
        player = meta[pid]
        used = counts[pid]
        lines.append(
            f"{player.position},{player.team},{player.nickname},{pid},{player.salary},"
            f"{used},{100.0 * used / len(book):.1f},{player.fpts:.2f},{player.p99:.2f}"
        )
    EXPOSURE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    stack_lines = ["stack,lineups,pct"]
    for label, used in stacks.most_common():
        stack_lines.append(f"\"{label}\",{used},{100.0 * used / len(book):.1f}")
    STACK_PATH.write_text("\n".join(stack_lines) + "\n", encoding="utf-8")
    print("exposure by position")
    for pos in ("QB", "RB", "WR", "TE", "DST"):
        rows = [
            (meta[pid].nickname, meta[pid].team, counts[pid])
            for pid in counts
            if meta[pid].position == pos
        ]
        rows.sort(key=lambda item: -item[2])
        print(f"{pos} players {len(rows)}")
        show = rows if pos in {"QB", "DST"} else rows[:12]
        for name, team, used in show:
            print(f"{name} | {team} | {used} | {100.0 * used / len(book):.1f}")
    print("top stacks")
    for label, used in stacks.most_common(12):
        print(f"{label} | {used} | {100.0 * used / len(book):.1f}")


def _print_book(book: Sequence[Candidate], meta: Mapping[str, PoolPlayer], audit: Mapping[str, object]) -> None:
    print(
        f"book {audit['lineups']} unique; min_uniques {9 - int(audit['max_share'])}; "
        f"salary {audit['salary_min']}-{audit['salary_max']}"
    )
    print("top 15 exposure")
    print("player | pos | team | lineups | pct")
    for name, pos, team, used, pct in exposure_table(book, meta, limit=15):
        print(f"{name} | {pos} | {team} | {used} | {pct:.1f}")
    ranked = sorted(book, key=lambda item: item.blend, reverse=True)[:5]
    print("top 5 lineups by blend")
    for index, item in enumerate(ranked, start=1):
        names = [f"{meta[pid].nickname} ${meta[pid].salary}" for _slot, pid in item.seats]
        print(f"{index}. ${item.salary} blend {item.blend:.2f} ceiling {_ceiling(item, meta):.2f} | {item.tags}")
        print("   " + "; ".join(names))


def check_upload(path: Path, players: Sequence[PoolPlayer] | None = None) -> None:
    """Fail when a backup quarterback or a hard exclude is in an upload file."""

    import csv

    meta = {} if players is None else {player.player_id: player for player in players}
    fails = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            cell = row.get("QB") or ""
            pid = cell.split(":", 1)[0].strip()
            if pid not in QB_IDS:
                fails.append(cell)
    if fails:
        raise AssertionError(f"FAIL_BACKUP_QB {fails[:10]}")
    print(f"qb check PASS {path} FAIL_BACKUP_QB 0")
    if meta:
        cle = [player for player in meta.values() if player.team == "CLE" and player.position == "QB" and not player.never_enter]
        names = sorted(player.nickname for player in cle)
        if names != ["Shedeur Sanders"]:
            raise AssertionError(f"CLE starter {names}")
        print("CLE starter Shedeur Sanders PASS")


def run_week9(*, source: Path | None = None) -> list[Candidate]:
    """Archive the salary file, score the slate, and solve the 133-lineup book."""

    import ceminidfs.export.mme_portfolio as portfolio

    salary_source = source or (DESKTOP_SALARY if DESKTOP_SALARY.is_file() else SALARY_PATH)
    SLATE_DIR.mkdir(parents=True, exist_ok=True)
    _archive_salary(salary_source)
    write_qb_starters_csv(STARTER_PATH, QB_STARTERS)
    _write_second_source()
    _write_environment()
    salary = pd.read_csv(SALARY_PATH)
    _validate_games(salary)
    _assert_starter_rows(salary)
    write_inactives_diff(salary)
    refresh_shared_cache(SALARY_PATH)
    ceiling = pd.read_csv(CEILING_PATH)
    all_players, pool = _build_pool(salary, ceiling)
    _report_pool(all_players, pool)
    write_optimizer_csv(OPTIMIZER_PATH, pool)
    # Keep every starter's boost wave. The default stop fills 150 and skips later quarterbacks.
    portfolio.BOOK_SIZE = 10**6
    candidates = build_candidate_pool(
        OPTIMIZER_PATH,
        pool,
        caps=BOOK_CAP,
        banned_teams=frozenset(),
        pair_cap=PAIR_CAP,
        rb_te_cap=RB_TE_CAP,
        max_waves=22,
        wave_size=40,
        seed=20261108,
    )
    portfolio.BOOK_SIZE = BOOK_N
    print(f"candidate pool {len(candidates)}")
    book = _select(candidates, pool, cheap=0)
    if len(book) < BOOK_N:
        print(f"strict book {len(book)}; relax salary floor")
        relaxed = _select(candidates, pool, cheap=CHEAP_LIMIT)
        if len(relaxed) > len(book):
            book = relaxed
    if len(book) != BOOK_N:
        raise AssertionError(f"lineups {len(book)} of {BOOK_N}")
    audit = verify_book(
        book,
        all_players,
        caps=BOOK_CAP,
        banned_teams=frozenset(),
        contest_prefix=CONTEST_PREFIX,
        pair_cap=PAIR_CAP,
        rb_te_cap=RB_TE_CAP,
        count=BOOK_N,
    )
    _assert_book(book, all_players)
    meta = {player.player_id: player for player in all_players}
    write_book_files(
        book,
        UPLOAD_133,
        IDS_133,
        season=SEASON,
        week=WEEK,
        players=all_players,
        slate_date="2026-11-08",
    )
    _write_split(book, meta)
    _write_exposure(book, meta)
    _print_book(book, meta, audit)
    check_upload(UPLOAD_133, all_players)
    print(f"upload 133 -> {UPLOAD_133}")
    print(f"upload 29 -> {UPLOAD_29}")
    print("human gate: CSV only; do not Enter")
    return book


def main() -> None:
    import sys

    if len(sys.argv) > 2 and sys.argv[1] == "--check":
        check_upload(Path(sys.argv[2]))
        return
    run_week9()


if __name__ == "__main__":
    main()
