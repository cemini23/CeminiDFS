"""Week 10 FanDuel 150-lineup book for the 2026-11-15 main slate.

The salary file is the slate. NE@DET (Munich, 9:30 AM ET) is absent from
that file, so it stays out of the book. One starting quarterback is allowed
per team. This module writes CSV files only. It does not submit lineups.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from ceminidfs.data.stadiums import normalize_team_abbr
from ceminidfs.export.mme_portfolio import (
    BOOK_SIZE,
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
    status_token,
    verify_book,
    write_book_files,
    write_optimizer_csv,
)
from ceminidfs.export.recap_guards import (
    RB_PAIR_CAP,
    RB_TE_CAP,
    OpportunityIndex,
    archive_loaded_salary,
    assert_one_qb_per_team,
    build_opportunity_index,
    is_backup_quarterback,
    lookup_opportunity,
    prelock_salary_archive,
    skill_excluded,
    write_lineups_resolved_csv,
    write_qb_starters_csv,
)
from ceminidfs.situational.engine import run_slate

CONTEST_PREFIX = "136490-"
SEASON = 2026
WEEK = 10
MAX_SOURCE_WEEK = 9
BOOK_CAP = {"QB": 36, "RB": 38, "WR": 38, "TE": 38, "DST": 33}
SLATE_DATE = "2026-11-15"
ET = ZoneInfo("America/New_York")
RECAP_ROOT = Path("/workspace/dfs-recap")
CATCHER_FLOOR = 6.0

MAIN_GAMES = frozenset(
    {
        "BUF@NYJ",
        "CAR@NO",
        "HOU@CLE",
        "JAC@TEN",
        "KC@ATL",
        "LAR@ARI",
        "MIA@IND",
        "MIN@GB",
        "SEA@LV",
        "SF@DAL",
    }
)

# Roof class and kickoff-hour wind mph. Tail scales live in adjust_tails_week10.
GAME_ENV = {
    "BUF@NYJ": ("open", 14),
    "CAR@NO": ("dome", 0),
    "HOU@CLE": ("open", 12),
    "JAC@TEN": ("open", 5),
    "KC@ATL": ("retractable", 0),
    "LAR@ARI": ("retractable", 5),
    "MIA@IND": ("retractable", 5),
    "MIN@GB": ("open", 1),
    "SEA@LV": ("dome", 0),
    "SF@DAL": ("retractable", 10),
}

QB_STARTERS = {
    "ARI": "Carson Beck",
    "ATL": "Michael Penix Jr.",
    "BUF": "Josh Allen",
    "CAR": "Bryce Young",
    "CLE": "Deshaun Watson",
    "DAL": "Dak Prescott",
    "GB": "Jordan Love",
    "HOU": "C.J. Stroud",
    "IND": "Daniel Jones",
    "JAX": "Trevor Lawrence",
    "KC": "Patrick Mahomes",
    "LAR": "Matthew Stafford",
    "LV": "Fernando Mendoza",
    "MIA": "Kyle McCord",
    "MIN": "Kirk Cousins",
    "NO": "Tyler Shough",
    "NYJ": "Geno Smith",
    "SEA": "Drew Lock",
    "SF": "Brock Purdy",
    "TEN": "Cam Ward",
}

# Salary FPPG is 0 or a backup sample. The floor keeps the starter in the pool.
STARTER_FLOORS = {
    "carson beck": 14.2,
    "kyle mccord": 14.0,
    "fernando mendoza": 14.5,
    "drew lock": 15.2,
}

# Out, Doubtful, IR, PUP, NFI, practice-squad, and unactivated reserve skill players.
_OUT_DOUBT = (
    "Josh Jacobs",
    "Josh Whyle",
    "Kyler Murray",
    "T.J. Hockenson",
    "Jauan Jennings",
    "Sam Darnold",
    "Mike Evans",
    "Brandon Aiyuk",
    "Marvin Harrison Jr.",
    "Brevin Jordan",
    "Jake Ferguson",
    "Jonathan Mingo",
    "Tyler Goodson",
    "Carnell Tate",
    "Zachariah Branch",
    "Michael Burton",
    "Jared Wayne",
    "Mo Alie-Cox",
    "CJ Donaldson",
    "Terrance Ferguson",
    "Chris Bell",
    "Jonathon Brooks",
)
_RESERVE_NAMES = (
    "Puka Nacua",
    "Davante Adams",
    "Jordan Whittington",
    "Travis Etienne Jr.",
    "Travis Etienne",
    "Chris Brooks",
    "Skyy Moore",
    "Jayden Reed",
    "Luke Musgrave",
    "Xavier Legette",
    "Tyrell Shavers",
    "Joshua Palmer",
    "Hunter Long",
    "Michael Wilson",
    "James Conner",
    "Trey Benson",
    "Jeremiyah Love",
    "Kendrick Bourne",
    "Jalen Brooks",
    "Gardner Minshew II",
    "Brian Robinson Jr.",
    "Brian Robinson",
    "Trey Sermon",
    "De'Von Achane",
    "Malik Willis",
    "Cole Turner",
    "Alec Pierce",
    "D.J. Montgomery",
    "Carson Towt",
    "Raheim Sanders",
    "Joe Royer",
    "Demond Claiborne",
    "Josh Oliver",
    "British Brooks",
    "Jayden Higgins",
    "Jaylin Noel",
    "Graham Mertz",
    "Jeff Caldwell",
    "John Michael Gyllenborg",
    "Jimmy Holiday",
    "Brashard Smith",
    "Tyquan Thornton",
    "Ty Chandler",
    "Moliki Matavao",
    "Mason Tipton",
    "Stone Smartt",
    "Ihmir Smith-Marsette",
    "Chris Brazzell II",
    "Arian Smith",
    "Chip Trayanum",
    "Jaren Kanak",
    "Dean Connors",
    "Matthew Caldwell",
    "Elijah Arroyo",
    "Jake Bobo",
    "Robbie Ouzts",
    "Christian Kirk",
    "Ricky Pearsall",
    "De'Zhaun Stribling",
    "Jake Tonges",
    "Isaac Guerendo",
    "Malik Davis",
    "Princeton Fant",
    "Thomas Yassmin",
    "Chris Collier",
    "Andrew DePaola",
)
RESERVE_VS_HUB = frozenset(fold_name(name) for name in _RESERVE_NAMES)
NAMED_EXCLUDES = frozenset(fold_name(name) for name in (*_OUT_DOUBT, *_RESERVE_NAMES))

# Active injury-vacuum and low-game replacements. G1 and G3 do not drop these names.
TOUCH_WHITELIST = frozenset(
    fold_name(name)
    for name in (
        "Kaleb Johnson",
        "MarShawn Lloyd",
        "Pierre Strong Jr.",
        "Emmett Johnson",
        "Zach Charbonnet",
        "Emanuel Wilson",
        "Deebo Samuel Sr.",
        "Jordan Watkins",
        "Keenan Allen",
        "Luke Schoonmaker",
        "Brevyn Spann-Ford",
        "Ryan Flournoy",
        "Konata Mumpfield",
        "Tutu Atwell",
        "Colby Parkinson",
        "Tyler Higbee",
        "Anthony Gould",
        "Michael Pittman Jr.",
        "Gavin Bartholomew",
    )
)

PLAYER_CAP_NAMES = {
    "kenneth walker iii": 12,
    "donte thornton jr.": 6,
    "jordan addison": 18,
    "david montgomery": 18,
    "garrett wilson": 22,
    "c.j. stroud": 12,
    "kirk cousins": 12,
}

DESKTOP_NOV14 = Path.home() / "Desktop" / "nov14.csv"
WORKSPACE_SALARY = Path("/workspace/dfs-slate/2026-11-15/_src_fd_sun.csv")
SALARY_PATH = Path("data/slates/2026-11-15_fd_sun.csv")
RUN_DIR = Path("runs/2026_week_10")
STARTER_PATH = RUN_DIR / "qb_starters_2026-11-15.csv"
RESOLVED_PATH = RUN_DIR / "lineups_resolved_2026-11-15.csv"
ENV_PATH = RUN_DIR / "environment.csv"
CEILING_PATH = RUN_DIR / "situational" / "ceiling.csv"
CALIBRATION_PATH = RUN_DIR / "situational" / "calibration.json"
OPTIMIZER_PATH = RUN_DIR / "portfolio_optimizer.csv"
UPLOAD_PATH = RUN_DIR / "fanduel_150_upload_2026-11-15.csv"
IDS_PATH = RUN_DIR / "fanduel_150_ids_only.csv"
SHARED_DIR = Path("data/shared_cache/2026_w10")
PBP_PATH = Path("artifacts/cache/pbp_2026.parquet")
ROSTER_PATH = Path("artifacts/cache/rosters_2026.parquet")
AUDIT_DIR = Path("reports/audit")


def adjust_tails_week10(
    game: object,
    team: object,
    position: object,
    display: object,
    p90: float,
    p99: float,
) -> tuple[float, float]:
    """Scale tails for the Week 10 dome, shootout, and wind rules."""

    key = canon_game(game)
    pos = canon_position(position)
    name = fold_name(display)
    club = normalize_team_abbr(str(team or ""))
    scale = 1.0
    if key == "SF@DAL" and (pos in {"QB", "WR", "TE"} or name == "christian mccaffrey"):
        scale = 1.06
    elif key in {"CAR@NO", "SEA@LV"}:
        if name in {"zach charbonnet", "chuba hubbard"}:
            scale = 1.06
        elif pos in {"QB", "WR", "TE"}:
            scale = 1.04
    elif key == "BUF@NYJ":
        if pos == "WR":
            scale = 0.92
        elif name == "james cook iii" or (pos == "DST" and club == "BUF"):
            scale = 1.06
    elif key == "HOU@CLE":
        if pos in {"QB", "WR"}:
            scale = 0.90
        elif pos in {"RB", "TE", "DST"}:
            scale = 1.05
    return p90 * scale, p99 * scale


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


def week10_blocked(
    record: Mapping[str, object],
    index: OpportunityIndex,
    *,
    extra_whitelist: frozenset[str] = frozenset(),
) -> bool:
    """Return True when the Week 10 rules set this salary row to 0 points."""

    display = _display(record)
    team = normalize_team_abbr(str(record.get("Team") or ""))
    position = record.get("Position")
    game = canon_game(record.get("Game"))
    if game not in MAIN_GAMES:
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
    found = lookup_opportunity(index, team, display, str(record.get("Last Name") or ""))
    targets = None if found is None else found.targets
    carries = None if found is None else found.carries
    snaps = None if found is None else found.snaps
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
    return skill_excluded(
        position=position,
        name=display,
        salary=int(_number(record.get("Salary"))),
        played=int(_number(record.get("Played"))),
        fppg=_number(record.get("FPPG")),
        targets=targets,
        carries=carries,
        snaps=snaps,
        roster_status="",
        roster_fresh=False,
        starter_note=False,
        whitelist=TOUCH_WHITELIST | extra_whitelist,
        team_target_share=team_share,
        route_share=route_share,
        snap_share=snap_share,
    )


def score_week10_frame(
    salary: pd.DataFrame,
    ceiling: pd.DataFrame,
    quantiles: Mapping[str, object],
    index: OpportunityIndex,
    *,
    extra_whitelist: frozenset[str] = frozenset(),
    extra_floors: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Join the salary file to the ceiling and apply the Week 10 guards."""

    sal = salary.copy()
    sal["player_id"] = sal["Id"].astype(str)
    ceil = ceiling.copy()
    ceil["player_id"] = ceil["player_id"].astype(str)
    keep = [column for column in ("player_id", "lagged_fd", "p90", "p99") if column in ceil.columns]
    merged = sal.merge(ceil[keep], on="player_id", how="left")
    skill = list(quantiles.get("skill") or [])
    dst_table = list(quantiles.get("dst") or [])
    floors = dict(extra_floors or {})

    def _floor(display: str) -> float | None:
        key = fold_name(display)
        if key in STARTER_FLOORS:
            return STARTER_FLOORS[key]
        return floors.get(key)

    rows = []
    for record in merged.to_dict(orient="records"):
        rows.append(
            score_pool_row(
                record,
                skill,
                dst_table,
                blocked=lambda rec, extra=extra_whitelist: week10_blocked(
                    rec, index, extra_whitelist=extra
                ),
                tails=lambda game, team, position, display, p90, p99: adjust_tails_week10(
                    game, team, position, display, p90, p99
                ),
                floor_lookup=_floor,
            )
        )
    return pd.DataFrame(rows)


def _cache_ready(path: Path) -> bool:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file() or not (path / "player_telemetry_pit.parquet").is_file():
        return False
    if not CEILING_PATH.is_file() or not CALIBRATION_PATH.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_week = manifest.get("max_source_week")
    if source_week is None:
        return False
    return int(source_week) <= MAX_SOURCE_WEEK


def refresh_shared_cache(salary_path: Path) -> None:
    """Score the slate when the Week 10 cache is missing. History stops at week 9."""

    if _cache_ready(SHARED_DIR):
        manifest = json.loads((SHARED_DIR / "manifest.json").read_text(encoding="utf-8"))
        print(f"shared cache ready -> {SHARED_DIR} max_source_week={manifest.get('max_source_week')}")
        return
    run_slate(SEASON, WEEK, salary_path=salary_path, out_dir=CEILING_PATH.parent)
    manifest = json.loads((SHARED_DIR / "manifest.json").read_text(encoding="utf-8"))
    source_week = int(manifest.get("max_source_week") or 0)
    if source_week > MAX_SOURCE_WEEK:
        raise AssertionError(f"max_source_week {source_week}")
    print(f"shared cache -> {SHARED_DIR} max_source_week={source_week}")


def load_opportunity_index() -> OpportunityIndex:
    if not PBP_PATH.is_file():
        raise FileNotFoundError(PBP_PATH)
    pbp = pd.read_parquet(PBP_PATH)
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


def empty_opportunity_index() -> OpportunityIndex:
    """Return an index with no prior plays. The touch floor stays off."""

    return OpportunityIndex(by_name={}, active_teams=frozenset())


def _eligible(players: Sequence[PoolPlayer]) -> list[PoolPlayer]:
    return [
        player
        for player in players
        if not player.never_enter
        and player.fpts > 0
        and player.salary > 0
        and player.player_id.startswith(CONTEST_PREFIX)
    ]


def _assert_pool_starters(pool: Sequence[PoolPlayer], teams: Sequence[str]) -> None:
    by_team: dict[str, list[str]] = defaultdict(list)
    for player in pool:
        if player.position == "QB":
            by_team[player.team].append(player.nickname)
    missing = [team for team in teams if team not in by_team]
    extra = {team: names for team, names in by_team.items() if len(names) != 1}
    if missing or extra:
        raise AssertionError(f"quarterback whitelist missing={missing} extra={extra}")
    for team, names in by_team.items():
        starter = QB_STARTERS.get(team)
        if starter and fold_name(names[0]) != fold_name(starter):
            raise AssertionError(f"{team} starter {names[0]}")


def _short_catcher_teams(pool: Sequence[PoolPlayer], teams: Sequence[str]) -> list[str]:
    counts: Counter[str] = Counter(
        player.team for player in pool if player.position in {"WR", "TE"}
    )
    return [team for team in teams if counts[team] < 2]


def _promote_catchers(
    salary: pd.DataFrame,
    short: Sequence[str],
    pool: Sequence[PoolPlayer],
) -> tuple[frozenset[str], dict[str, float]]:
    """Pick healthy WR and TE names so each short team can reach two catchers."""

    present = {fold_name(player.nickname) for player in pool}
    needed = {team: 2 for team in short}
    counts: Counter[str] = Counter(
        player.team for player in pool if player.position in {"WR", "TE"}
    )
    for team, count in counts.items():
        if team in needed:
            needed[team] = max(0, 2 - count)
    rows = []
    for record in salary.to_dict(orient="records"):
        team = normalize_team_abbr(str(record.get("Team") or ""))
        if team not in needed or needed[team] <= 0:
            continue
        if canon_position(record.get("Position")) not in {"WR", "TE"}:
            continue
        name = fold_name(_display(record))
        if not name or name in NAMED_EXCLUDES or name in present:
            continue
        if status_token(record.get("Injury Indicator")) in {"O", "IR", "D", "SUSP", "NA", "PUP", "NFI"}:
            continue
        rows.append((team, _number(record.get("FPPG")), int(_number(record.get("Salary"))), name))
    rows.sort(key=lambda item: (item[0], -item[1], -item[2], item[3]))
    chosen: list[str] = []
    floors: dict[str, float] = {}
    for team, fppg, _salary, name in rows:
        if needed.get(team, 0) <= 0:
            continue
        chosen.append(name)
        needed[team] -= 1
        if fppg <= 0:
            floors[name] = CATCHER_FLOOR
    still = [team for team, count in needed.items() if count > 0]
    if still:
        raise AssertionError(f"pass catchers short {still}")
    return frozenset(chosen), floors


def _score_players(
    salary: pd.DataFrame,
    ceiling: pd.DataFrame,
    index: OpportunityIndex,
    *,
    extra_whitelist: frozenset[str] = frozenset(),
    extra_floors: Mapping[str, float] | None = None,
) -> list[PoolPlayer]:
    quantiles = load_quantiles(CALIBRATION_PATH) if CALIBRATION_PATH.is_file() else {"skill": [], "dst": []}
    frame = score_week10_frame(
        salary,
        ceiling,
        quantiles,
        index,
        extra_whitelist=extra_whitelist,
        extra_floors=extra_floors,
    )
    players = players_from_frame(frame)
    set_nicknames(players)
    return players


def build_week10_pool(
    salary: pd.DataFrame,
    ceiling: pd.DataFrame,
    index: OpportunityIndex,
) -> tuple[list[PoolPlayer], list[PoolPlayer]]:
    """Score the slate and keep two pass catchers on every team."""

    players = _score_players(salary, ceiling, index)
    pool = _eligible(players)
    teams = sorted({normalize_team_abbr(str(team)) for team in salary["Team"].dropna().tolist()})
    short = _short_catcher_teams(pool, teams)
    if short:
        extra, floors = _promote_catchers(salary, short, pool)
        print(f"pass-catcher promote {sorted(extra)}")
        players = _score_players(
            salary,
            ceiling,
            index,
            extra_whitelist=extra,
            extra_floors=floors,
        )
        pool = _eligible(players)
        short = _short_catcher_teams(pool, teams)
        if short:
            raise AssertionError(f"pass catchers short {short}")
    _assert_pool_starters(pool, teams)
    return players, pool


def player_cap_map(players: Sequence[PoolPlayer]) -> dict[str, int]:
    caps: dict[str, int] = {}
    for player in players:
        cap = PLAYER_CAP_NAMES.get(fold_name(player.nickname))
        if cap is not None:
            caps[player.player_id] = cap
    return caps


def _assert_book(book: Sequence[Candidate], players: Sequence[PoolPlayer]) -> None:
    meta = {player.player_id: player for player in players}
    rostered: dict[str, set[str]] = defaultdict(set)
    keys = []
    counts: Counter[str] = Counter()
    for item in book:
        keys.append(item.key)
        for pid in item.ids:
            player = meta[pid]
            counts[pid] += 1
            if player.never_enter or fold_name(player.nickname) in NAMED_EXCLUDES:
                raise AssertionError(player.nickname)
            if not pid.startswith(CONTEST_PREFIX):
                raise AssertionError(pid)
        for pid, pos in item.positions:
            player = meta[pid]
            if pos == "QB":
                if is_backup_quarterback(player.team, player.nickname, "QB", QB_STARTERS):
                    raise AssertionError(player.nickname)
                rostered[player.team].add(fold_name(player.nickname))
    if len(book) != BOOK_SIZE or len(set(keys)) != BOOK_SIZE:
        raise AssertionError(f"unique lineups {len(set(keys))}")
    assert_one_qb_per_team(rostered)
    for pid, used in counts.items():
        player = meta[pid]
        cap = PLAYER_CAP_NAMES.get(fold_name(player.nickname))
        if cap is not None and used > cap:
            raise AssertionError(f"{player.nickname} {used} > {cap}")


def _print_week10(
    book: Sequence[Candidate],
    meta: Mapping[str, PoolPlayer],
    audit: Mapping[str, object],
) -> None:
    print(
        f"book {audit['lineups']} unique; min_uniques {9 - int(audit['max_share'])}; "
        f"bring-back {audit['bringback']}; secondary {audit['secondary']}; "
        f"salary {audit['salary_min']}-{audit['salary_max']}"
    )
    print("top 25 exposure")
    print("player | pos | team | lineups | pct")
    for name, pos, team, used, pct in exposure_table(book, meta, limit=25):
        print(f"{name} | {pos} | {team} | {used} | {pct:.1f}")
    print("qb starter exposure")
    qb_counts: Counter[str] = Counter()
    for item in book:
        for pid, pos in item.positions:
            if pos == "QB":
                qb_counts[pid] += 1
    for pid, used in qb_counts.most_common():
        player = meta[pid]
        print(f"{player.nickname} | {player.team} | {used} | {100.0 * used / len(book):.1f}")
    print("game stacks")
    games: Counter[str] = audit["games"]  # type: ignore[assignment]
    for game, used in games.most_common():
        print(f"{game} | {used}")
    ranked = sorted(book, key=lambda item: item.blend, reverse=True)[:5]
    print("top 5 lineups")
    for index, item in enumerate(ranked, start=1):
        names = [f"{meta[pid].nickname} ${meta[pid].salary}" for _slot, pid in item.seats]
        print(f"{index}. ${item.salary} blend {item.blend:.2f} | {item.tags}")
        print("   " + "; ".join(names))


def _write_environment() -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = ["game,roof,wind_mph"]
    for game, (roof, wind) in sorted(GAME_ENV.items()):
        rows.append(f"{game},{roof},{wind}")
    ENV_PATH.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _glob_salary() -> Path | None:
    patterns = ("*2026*11*15*.csv", "*136490*.csv")
    found: list[Path] = []
    for folder in (Path.home() / "Desktop", Path.home() / "Downloads"):
        if not folder.is_dir():
            continue
        for pattern in patterns:
            found.extend(folder.glob(pattern))
    found = [path for path in found if path.is_file()]
    if not found:
        return None
    return sorted(found)[-1]


def default_salary_source() -> Path:
    """Return the first Week 10 salary file that is on disk."""

    for path in (DESKTOP_NOV14, Path("nov14.csv"), WORKSPACE_SALARY, SALARY_PATH):
        if path.is_file():
            return path
    found = _glob_salary()
    if found is not None:
        return found
    raise FileNotFoundError("Week 10 FanDuel salary CSV")


def _archive_salary(salary_source: Path) -> None:
    written = archive_loaded_salary(salary_source, [SALARY_PATH])
    archived = prelock_salary_archive(
        salary_source,
        season=SEASON,
        week=WEEK,
        work_dir=RUN_DIR,
        slate_date=SLATE_DATE,
        fixture_id=CONTEST_PREFIX.rstrip("-"),
        audit_dir=AUDIT_DIR,
    )
    for path in [*written, *archived]:
        print(f"salary copy -> {path}")
    if not any("fd_players_" in path.name for path in archived):
        print("recap copy skipped: /workspace/dfs-recap is not on this machine")


def _validate_games(salary: pd.DataFrame) -> None:
    games = sorted({canon_game(value) for value in salary["Game"].dropna().tolist()})
    if "NE@DET" in games or "DET@NE" in games:
        raise AssertionError("Munich game is in the salary file")
    if set(games) != MAIN_GAMES:
        raise AssertionError(f"salary games {games}")


def _select_with_relaxation(
    candidates: list[Candidate],
    pool: list[PoolPlayer],
    caps: Mapping[str, int],
) -> list[Candidate]:
    teams = {player.player_id: player.team for player in pool}
    book = select_book(
        candidates,
        caps=BOOK_CAP,
        pair_cap=RB_PAIR_CAP,
        rb_te_cap=RB_TE_CAP,
        player_caps=caps,
        player_teams=teams,
        allow_cheap=0,
    )
    if len(book) >= BOOK_SIZE:
        return book
    relaxed = select_book(
        candidates,
        caps=BOOK_CAP,
        pair_cap=RB_PAIR_CAP,
        rb_te_cap=RB_TE_CAP,
        player_caps=caps,
        player_teams=teams,
        allow_cheap=CHEAP_LIMIT,
    )
    return relaxed if len(relaxed) > len(book) else book


def run_week10(*, source: Path | None = None) -> list[Candidate]:
    """Archive the salary file, write the cache, and solve the 150-lineup book."""

    salary_source = source or default_salary_source()
    _archive_salary(salary_source)
    write_qb_starters_csv(STARTER_PATH, QB_STARTERS)
    _write_environment()
    salary = pd.read_csv(SALARY_PATH)
    _validate_games(salary)
    refresh_shared_cache(SALARY_PATH)
    ceiling = pd.read_csv(CEILING_PATH)
    index = load_opportunity_index()
    all_players, pool = build_week10_pool(salary, ceiling, index)
    print(f"eligible pool {len(pool)} of {len(all_players)}")
    caps = player_cap_map(all_players)
    write_optimizer_csv(OPTIMIZER_PATH, pool)
    candidates = build_candidate_pool(
        OPTIMIZER_PATH,
        pool,
        caps=BOOK_CAP,
        banned_teams=frozenset(),
        pair_cap=RB_PAIR_CAP,
        player_caps=caps,
        rb_te_cap=RB_TE_CAP,
        max_waves=22,
        wave_size=40,
        seed=20261115,
    )
    book = _select_with_relaxation(candidates, pool, caps)
    if len(book) != BOOK_SIZE:
        raise AssertionError(f"lineups {len(book)} of {BOOK_SIZE}")
    audit = verify_book(
        book,
        all_players,
        caps=BOOK_CAP,
        banned_teams=frozenset(),
        contest_prefix=CONTEST_PREFIX,
        pair_cap=RB_PAIR_CAP,
        player_caps=caps,
        rb_te_cap=RB_TE_CAP,
    )
    _assert_book(book, all_players)
    if int(audit["bringback"]) < 113 or int(audit["secondary"]) < 75:
        raise AssertionError(f"floors {audit['bringback']} {audit['secondary']}")
    if int(audit["unstacked_rb_te"]) != 0:
        raise AssertionError("unstacked rb+te")
    write_book_files(
        book,
        UPLOAD_PATH,
        IDS_PATH,
        season=SEASON,
        week=WEEK,
        players=all_players,
        slate_date=SLATE_DATE,
        audit_dir=AUDIT_DIR,
        recap_root=RECAP_ROOT,
        run_dir=RUN_DIR,
    )
    retrieved = datetime.now(ET).isoformat(timespec="seconds")
    write_lineups_resolved_csv(
        RESOLVED_PATH,
        book,
        all_players,
        source_file=str(salary_source),
        fixture_id=CONTEST_PREFIX.rstrip("-"),
        retrieved_et=retrieved,
    )
    _print_week10(book, {player.player_id: player for player in all_players}, audit)
    print(f"upload -> {UPLOAD_PATH}")
    print(f"resolved -> {RESOLVED_PATH}")
    print(f"unstacked rb+te {audit['unstacked_rb_te']}")
    return book


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build the Week 10 FanDuel 150-lineup book.")
    parser.add_argument("--source", type=Path, default=None)
    args = parser.parse_args()
    run_week10(source=args.source)


if __name__ == "__main__":
    main()
