"""Week 8 FanDuel 150-lineup book for the 2026-11-01 main slate.

The salary file is the slate. Thursday, Sunday night, and Monday games
are absent from that file, so they stay out of the book. One starting
quarterback is allowed per team. The Week 7 recap guards (G1-G4, G8)
remove punt skill players, free agents, and an unstacked same-team
running back plus tight end.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from ceminidfs.data.stadiums import normalize_team_abbr
from ceminidfs.export.mme_portfolio import (
    BOOK_SIZE,
    CHEAP_LIMIT,
    Candidate,
    PoolPlayer,
    build_candidate_pool,
    canon_game,
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
    RB_PAIR_CAP,
    RB_TE_CAP,
    OpportunityIndex,
    MME_PLAYER_CAP,
    archive_loaded_salary,
    assert_one_qb_per_team,
    build_opportunity_index,
    prelock_salary_archive,
    environment_scale,
    is_backup_quarterback,
    lookup_opportunity,
    skill_excluded,
    write_qb_starters_csv,
)
from ceminidfs.situational.engine import run_slate

CONTEST_PREFIX = "135859-"
SEASON = 2026
WEEK = 8
MAX_SOURCE_WEEK = 7
BOOK_CAP = {"QB": 36, "RB": MME_PLAYER_CAP, "WR": MME_PLAYER_CAP, "TE": MME_PLAYER_CAP, "DST": 33}

MAIN_GAMES = frozenset(
    {
        "ARI@DAL",
        "ATL@TB",
        "BAL@BUF",
        "CLE@PIT",
        "IND@JAC",
        "KC@DEN",
        "LAC@LAR",
        "LV@NYJ",
        "MIN@DET",
        "NE@MIA",
        "TEN@CIN",
    }
)

# Roof class and wind mph from the 2026-11-01 packet. A non-open roof is a 0 fade.
GAME_ENV = {
    "ARI@DAL": ("retractable", 5),
    "ATL@TB": ("open", 12),
    "BAL@BUF": ("open", 5),
    "CLE@PIT": ("open", 3),
    "IND@JAC": ("open", 15),
    "KC@DEN": ("open", 8),
    "LAC@LAR": ("canopy", 0),
    "LV@NYJ": ("open", 6),
    "MIN@DET": ("dome", 0),
    "NE@MIA": ("open", 13),
    "TEN@CIN": ("open", 3),
}

QB_STARTERS = {
    "ARI": "Jacoby Brissett",
    "ATL": "Michael Penix Jr.",
    "BAL": "Lamar Jackson",
    "BUF": "Josh Allen",
    "CIN": "Joe Burrow",
    "CLE": "Deshaun Watson",
    "DAL": "Dak Prescott",
    "DEN": "Bo Nix",
    "DET": "Jared Goff",
    "IND": "Daniel Jones",
    "JAX": "Trevor Lawrence",
    "KC": "Patrick Mahomes",
    "LAC": "Justin Herbert",
    "LAR": "Matthew Stafford",
    "LV": "Kirk Cousins",
    "MIA": "Malik Willis",
    "MIN": "Kyler Murray",
    "NE": "Drake Maye",
    "NYJ": "Geno Smith",
    "PIT": "Aaron Rodgers",
    "TB": "Baker Mayfield",
    "TEN": "Cam Ward",
}

# Packet Out / IR / Doubtful / reserve / practice-squad skill players.
NAMED_EXCLUDES = frozenset(
    fold_name(name)
    for name in (
        "Tyrell Shavers",
        "Carnell Tate",
        "Tyjae Spears",
        "KaVontae Turpin",
        "Anthony Gould",
        "Carter Runyon",
        "Brian Robinson",
        "Emeka Egbuka",
        "Brenen Thompson",
        "RJ Harvey",
        "Adam Randall",
        "Beaux Collins",
        "A.J. Brown",
        "TreVeyon Henderson",
        "Durham Smythe",
        "Skylar Thompson",
        "Jaren Kanak",
        "Josh Kattus",
        "Erick All Jr.",
        "Tanner Hudson",
        "Andrei Iosivas",
        "Tip Reiman",
        "Trey Benson",
        "Jalen Brooks",
        "Hunter Long",
        "James Conner",
        "Emari Demercado",
        "DJ Rogers",
        "Malik Davis",
        "Princeton Fant",
        "Michael Briscoe",
        "Josh Oliver",
        "Tom Kennedy",
        "Kendrick Law",
        "Isiah Pacheco",
        "D.J. Montgomery",
        "Alec Pierce",
        "Carson Towt",
        "Chris Collier",
        "Arian Smith",
        "Chip Trayanum",
        "Bub Means",
        "Raheim Sanders",
        "Joe Royer",
        "Max Hurleman",
        "Michael Pittman Jr.",
        "Roman Wilson",
        "Trey Sermon",
        "Jalen McMillan",
        "Evan Svoboda",
        "Alec Ingold",
        "Trey Lance",
        "David Njoku",
        "Davante Adams",
        "Matthew Caldwell",
        "Ronnie Rivers",
        "Jeff Caldwell",
        "John Michael Gyllenborg",
        "Jimmy Holiday",
        "Brashard Smith",
        "Tyquan Thornton",
        "Tyler Badie",
        "Pat Bryant",
        "Caleb Lohner",
        "Romeo Doubs",
        "Reggie Gilliam",
        "Julian Hill",
        "Mack Hollins",
        "Myles Montgomery",
        "De'Von Achane",
        "Cole Turner",
    )
)

DESKTOP_SALARY = Path(
    "/Users/claudiobarone/Desktop/FanDuel-NFL-2026 EST-11 EST-01 EST-135859-players-list.csv"
)
SALARY_PATH = Path("data/slates/2026-11-01_fd_sun.csv")
RUN_DIR = Path("runs/2026_week_8")
STARTER_PATH = RUN_DIR / "qb_starters_2026-11-01.csv"
ENV_PATH = RUN_DIR / "environment.csv"
CEILING_PATH = RUN_DIR / "situational" / "ceiling.csv"
CALIBRATION_PATH = RUN_DIR / "situational" / "calibration.json"
OPTIMIZER_PATH = RUN_DIR / "portfolio_optimizer.csv"
UPLOAD_PATH = RUN_DIR / "fanduel_150_upload_2026-11-01.csv"
IDS_PATH = RUN_DIR / "fanduel_150_ids_only.csv"
SHARED_DIR = Path("data/shared_cache/2026_w08")
PBP_PATH = Path("artifacts/cache/pbp_2026.parquet")
ROSTER_PATH = Path("artifacts/cache/rosters_2026.parquet")


def adjust_tails_week8(game: object, position: object, p90: float, p99: float) -> tuple[float, float]:
    """Scale tails from the packet roof and wind. A dome stays at 1.0."""

    roof, wind = GAME_ENV.get(canon_game(game), ("open", 0))
    scale = environment_scale(roof, wind, position)
    return p90 * scale, p99 * scale


def _number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def week8_blocked(
    record: Mapping[str, object],
    index: OpportunityIndex,
    *,
    roster_fresh: bool = False,
    roster_status: str = "",
) -> bool:
    """Return True when the Week 8 rules set this salary row to 0 points."""

    nickname = str(record.get("Nickname") or "").strip()
    first = str(record.get("First Name") or "").strip()
    last = str(record.get("Last Name") or "").strip()
    display = nickname or f"{first} {last}".strip()
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
    found = lookup_opportunity(index, team, display, last)
    targets = None if found is None else found.targets
    carries = None if found is None else found.carries
    snaps = None if found is None else found.snaps
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
        roster_status=roster_status,
        roster_fresh=roster_fresh,
        starter_note=False,
        whitelist=frozenset(),
        team_target_share=team_share,
        route_share=route_share,
        snap_share=snap_share,
    )


def score_week8_frame(
    salary: pd.DataFrame,
    ceiling: pd.DataFrame,
    quantiles: Mapping[str, object],
    index: OpportunityIndex,
    roster_status: Mapping[tuple[str, str], str] | None = None,
    *,
    roster_fresh: bool = False,
) -> pd.DataFrame:
    """Join the salary file to the ceiling and apply the Week 8 guards."""

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
            _score_week8_row(
                record,
                skill,
                dst_table,
                index,
                roster_status=status_map.get((team, name), ""),
                roster_fresh=roster_fresh,
            )
        )
    return pd.DataFrame(rows)


def _score_week8_row(
    record: Mapping[str, object],
    skill: list[dict],
    dst_table: list[dict],
    index: OpportunityIndex,
    *,
    roster_status: str,
    roster_fresh: bool,
) -> dict[str, object]:
    return score_pool_row(
        record,
        skill,
        dst_table,
        blocked=lambda rec: week8_blocked(
            rec, index, roster_fresh=roster_fresh, roster_status=roster_status
        ),
        tails=lambda game, team, position, display, p90, p99: adjust_tails_week8(
            game, position, p90, p99
        ),
    )


def _cache_ready(path: Path) -> bool:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file() or not (path / "player_telemetry_pit.parquet").is_file():
        return False
    if not CEILING_PATH.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return int(manifest.get("max_source_week", -1)) == MAX_SOURCE_WEEK


def refresh_shared_cache(salary_path: Path) -> dict:
    """Score the slate and write the Week 8 shared cache. Max source week is 7."""

    if not _cache_ready(SHARED_DIR):
        run_slate(SEASON, WEEK, salary_path=salary_path, out_dir=CEILING_PATH.parent)
    manifest = json.loads((SHARED_DIR / "manifest.json").read_text(encoding="utf-8"))
    if int(manifest.get("max_source_week", -1)) != MAX_SOURCE_WEEK:
        raise AssertionError(f"max_source_week {manifest.get('max_source_week')}")
    print(f"shared cache -> {SHARED_DIR} max_source_week={manifest['max_source_week']}")
    return manifest


def load_opportunity_index() -> OpportunityIndex:
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


def _assert_pool_starters(pool: Sequence[PoolPlayer], teams: Sequence[str]) -> None:
    by_team: dict[str, list[str]] = defaultdict(list)
    for player in pool:
        if player.position == "QB":
            by_team[player.team].append(player.nickname)
    missing = [team for team in teams if team not in by_team]
    extra = {team: names for team, names in by_team.items() if len(names) != 1}
    if missing or extra:
        raise AssertionError(f"quarterback whitelist missing={missing} extra={extra}")


def _assert_book(book: Sequence[Candidate], players: Sequence[PoolPlayer]) -> None:
    meta = {player.player_id: player for player in players}
    rostered: dict[str, set[str]] = defaultdict(set)
    for item in book:
        for pid, pos in item.positions:
            player = meta[pid]
            if player.never_enter:
                raise AssertionError(player.nickname)
            if pos == "QB":
                if is_backup_quarterback(player.team, player.nickname, "QB", QB_STARTERS):
                    raise AssertionError(player.nickname)
                rostered[player.team].add(fold_name(player.nickname))
    assert_one_qb_per_team(rostered)
    counts: Counter[str] = Counter()
    for item in book:
        for pid, pos in item.positions:
            if pos in {"WR", "TE", "RB"}:
                counts[pid] += 1
    for pid, used in counts.items():
        player = meta[pid]
        cap = BOOK_CAP[player.position]
        if used > cap:
            raise AssertionError(f"{player.nickname} {used} > {cap}")


def _print_week8(book: Sequence[Candidate], meta: Mapping[str, PoolPlayer], audit: Mapping[str, object]) -> None:
    print(
        f"book {audit['lineups']} unique; min_uniques {9 - int(audit['max_share'])}; "
        f"bring-back {audit['bringback']}; salary {audit['salary_min']}-{audit['salary_max']}"
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
    print("top 10 stacks")
    stacks: Counter[str] = Counter(item.tags for item in book)
    for label, used in stacks.most_common(10):
        print(f"{label} | {used}")
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


def _default_source() -> Path:
    if DESKTOP_SALARY.is_file():
        return DESKTOP_SALARY
    if SALARY_PATH.is_file():
        return SALARY_PATH
    downloads = sorted(Path.home().joinpath("Downloads").glob("FanDuel-NFL-2026*11*01*.csv"))
    if downloads:
        return downloads[-1]
    raise FileNotFoundError("Week 8 FanDuel salary CSV")


def _archive_salary(salary_source: Path) -> None:
    written = archive_loaded_salary(salary_source, [SALARY_PATH])
    archived = prelock_salary_archive(
        salary_source,
        season=SEASON,
        week=WEEK,
        work_dir=RUN_DIR,
        slate_date="2026-11-01",
        fixture_id=CONTEST_PREFIX.rstrip("-"),
    )
    for path in [*written, *archived]:
        print(f"salary copy -> {path}")
    if not any("fd_players_" in path.name for path in archived):
        print("recap copy skipped: /workspace/dfs-recap is not on this machine")


def _validate_games(salary: pd.DataFrame) -> None:
    games = sorted({canon_game(value) for value in salary["Game"].dropna().tolist()})
    if set(games) != MAIN_GAMES:
        raise AssertionError(f"salary games {games}")


def _build_pool(
    salary: pd.DataFrame,
    ceiling: pd.DataFrame,
) -> tuple[list[PoolPlayer], list[PoolPlayer]]:
    index = load_opportunity_index()
    roster_map, roster_fresh = roster_status_index()
    portfolio = score_week8_frame(
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
    blocked = [player for player in all_players if player.never_enter and player.salary >= 5500]
    print(f"eligible pool {len(pool)} of {len(all_players)}; high-salary blocks {len(blocked)}")
    for player in sorted(blocked, key=lambda item: -item.salary)[:25]:
        print(f"blocked {player.position} {player.nickname} {player.team} ${player.salary}")


def _select_with_relaxation(
    candidates: list[Candidate],
    pool: list[PoolPlayer],
) -> list[Candidate]:
    book = select_book(
        candidates,
        caps=BOOK_CAP,
        pair_cap=RB_PAIR_CAP,
        rb_te_cap=RB_TE_CAP,
        player_teams={player.player_id: player.team for player in pool},
        allow_cheap=0,
    )
    if len(book) >= BOOK_SIZE:
        return book
    relaxed = select_book(
        candidates,
        caps=BOOK_CAP,
        pair_cap=RB_PAIR_CAP,
        rb_te_cap=RB_TE_CAP,
        player_teams={player.player_id: player.team for player in pool},
        allow_cheap=CHEAP_LIMIT,
    )
    return relaxed if len(relaxed) > len(book) else book


def run_week8(*, source: Path | None = None) -> list[Candidate]:
    """Archive the salary file, write the cache, and solve the 150-lineup book."""

    salary_source = source or _default_source()
    _archive_salary(salary_source)
    salary_path = SALARY_PATH
    write_qb_starters_csv(STARTER_PATH, QB_STARTERS)
    _write_environment()
    salary = pd.read_csv(salary_path)
    _validate_games(salary)
    refresh_shared_cache(salary_path)
    ceiling = pd.read_csv(CEILING_PATH)
    all_players, pool = _build_pool(salary, ceiling)
    _report_pool(all_players, pool)
    write_optimizer_csv(OPTIMIZER_PATH, pool)
    candidates = build_candidate_pool(
        OPTIMIZER_PATH,
        pool,
        caps=BOOK_CAP,
        banned_teams=frozenset(),
        pair_cap=RB_PAIR_CAP,
        rb_te_cap=RB_TE_CAP,
        max_waves=18,
        wave_size=40,
        seed=20261101,
    )
    book = _select_with_relaxation(candidates, pool)
    audit = verify_book(
        book,
        all_players,
        caps=BOOK_CAP,
        banned_teams=frozenset(),
        contest_prefix=CONTEST_PREFIX,
        pair_cap=RB_PAIR_CAP,
        rb_te_cap=RB_TE_CAP,
    )
    _assert_book(book, all_players)
    write_book_files(book, UPLOAD_PATH, IDS_PATH)
    _print_week8(book, {player.player_id: player for player in all_players}, audit)
    print(f"upload -> {UPLOAD_PATH}")
    print(f"unstacked rb+te {audit['unstacked_rb_te']}")
    return book


def main() -> None:
    run_week8()


if __name__ == "__main__":
    main()
