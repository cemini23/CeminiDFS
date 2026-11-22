"""Week 11 FanDuel 149-lineup book for the 2026-11-22 main slate.

The salary file is the slate. This module writes CSV files only.
It does not submit lineups.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from ceminidfs.data.availability import (
    build_prelock_gate,
    finish_lineup_outputs,
    format_questionable_warning,
)
from ceminidfs.data.stadiums import normalize_team_abbr
from ceminidfs.export.mme_portfolio import (
    MIN_SALARY,
    Candidate,
    PoolPlayer,
    _noise_map,
    build_candidate_pool,
    candidate_from_lineup,
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
    solve_wave,
    status_token,
    verify_book,
    write_book_files,
    write_optimizer_csv,
)
from ceminidfs.export.recap_guards import (
    OpportunityIndex,
    assert_one_qb_per_team,
    build_opportunity_index,
    is_backup_quarterback,
    lookup_opportunity,
    skill_excluded,
)
from ceminidfs.export.mme_week10 import _display, _number, _promote_catchers

CONTEST_PREFIX = "136799-"
SEASON = 2026
WEEK = 11
BOOK_SIZE = 149
SKILL_CAP = 52
TEAM_CAP = 67
SLATE_DATE = "2026-11-22"
SALARY_PATH = Path("data/slates/2026-11-22_fd_sun.csv")
RUN_DIR = Path("runs/2026_week_11")
SCRATCH_PATH = Path("config/2026-w11-sun-scratch.csv")
STARTER_PATH = RUN_DIR / "qb_starters_2026-11-22.csv"
ENV_PATH = RUN_DIR / "environment.csv"
CEILING_PATH = RUN_DIR / "situational" / "ceiling.csv"
CALIBRATION_PATH = RUN_DIR / "situational" / "calibration.json"
OPTIMIZER_PATH = RUN_DIR / "portfolio_optimizer.csv"
UPLOAD_PATH = RUN_DIR / "fd_lineups_2026-11-22_149.csv"
IDS_PATH = RUN_DIR / "fd_lineups_2026-11-22_149_ids.csv"
PBP_PATH = Path("artifacts/cache/pbp_2026.parquet")
ROSTER_PATH = Path("artifacts/cache/rosters_2026.parquet")
RECAP_DIR = Path("/workspace/dfs-recap/2026-11-22")

BOOK_CAP = {"QB": SKILL_CAP, "RB": SKILL_CAP, "WR": SKILL_CAP, "TE": SKILL_CAP, "DST": SKILL_CAP}
MAIN_GAMES = frozenset(
    {
        "ARI@KC",
        "BAL@CAR",
        "JAC@NYG",
        "LV@DEN",
        "MIA@BUF",
        "NO@CHI",
        "NYJ@LAC",
        "PIT@PHI",
        "TB@DET",
        "TEN@DAL",
    }
)
MUST_HIT_GAMES = ("TEN@DAL", "TB@DET", "MIA@BUF", "NO@CHI", "ARI@KC")
QB_STARTERS = {
    "ARI": "Josh Johnson",
    "BAL": "Jacoby Brissett",
    "BUF": "Josh Allen",
    "CAR": "Bryce Young",
    "CHI": "Caleb Williams",
    "DAL": "Dak Prescott",
    "DEN": "Bo Nix",
    "DET": "Jared Goff",
    "JAX": "Trevor Lawrence",
    "KC": "Patrick Mahomes",
    "LAC": "Justin Herbert",
    "LV": "Fernando Mendoza",
    "MIA": "Kyle McCord",
    "NO": "Tyler Shough",
    "NYG": "J.J. McCarthy",
    "NYJ": "Geno Smith",
    "PHI": "Joe Milton III",
    "PIT": "Aaron Rodgers",
    "TB": "Baker Mayfield",
    "TEN": "Cam Ward",
}
Q_EXCLUDES = (
    "Brock Bowers",
    "Ladd McConkey",
    "Luke Schoonmaker",
    "Will Shipley",
    "Jackson Hawes",
    "Charlie Kolar",
    "Zavion Thomas",
    "Sione Vaki",
)
# Practice squad. FanDuel lists DAL. The last active roster was NO.
ROSTER_EXCLUDES = ("Kendre Miller",)
KEEP_NAMES = (
    "Roman Wilson",
    "Carnell Tate",
    "Isaiah Likely",
    "Darren Waller",
    "Tommy Tremble",
    "Baker Mayfield",
)
PLAYER_CAP_NAMES = {
    "roman wilson": 22,
    "darren waller": 22,
    "tommy tremble": 22,
    "baker mayfield": 14,
}
TOUCH_WHITELIST = frozenset(fold_name(name) for name in KEEP_NAMES)
NAMED_EXCLUDES = frozenset(fold_name(name) for name in (*Q_EXCLUDES, *ROSTER_EXCLUDES))
HARD_TOKENS = frozenset({"O", "IR", "D", "SUSP", "NA", "PUP", "NFI"})


def adjust_tails_week11(
    game: object,
    team: object,
    position: object,
    display: object,
    p90: float,
    p99: float,
) -> tuple[float, float]:
    """Fade the passing tails for the Saturday rain and wind calls."""

    del team, display
    key = canon_game(game)
    pos = canon_position(position)
    scale = 1.0
    if key == "NO@CHI" and pos in {"QB", "WR", "TE"}:
        scale = 0.88
    elif key == "ARI@KC" and pos in {"QB", "WR"}:
        scale = 0.95
    return p90 * scale, p99 * scale


def week11_blocked(
    record: Mapping[str, object],
    index: OpportunityIndex,
    *,
    extra_whitelist: frozenset[str] = frozenset(),
) -> bool:
    """Return True when this salary row stays out of the pool."""

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


def score_week11_frame(
    salary: pd.DataFrame,
    ceiling: pd.DataFrame,
    quantiles: Mapping[str, object],
    index: OpportunityIndex,
    *,
    extra_whitelist: frozenset[str] = frozenset(),
    extra_floors: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Join the salary file to the ceiling and apply the Week 11 guards."""

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
        return floors.get(fold_name(display))

    rows = []
    for record in merged.to_dict(orient="records"):
        rows.append(
            score_pool_row(
                record,
                skill,
                dst_table,
                blocked=lambda rec, extra=extra_whitelist: week11_blocked(
                    rec, index, extra_whitelist=extra
                ),
                tails=adjust_tails_week11,
                floor_lookup=_floor,
            )
        )
    return pd.DataFrame(rows)


def _eligible(players: Sequence[PoolPlayer]) -> list[PoolPlayer]:
    return [
        player
        for player in players
        if not player.never_enter
        and player.fpts > 0
        and player.salary > 0
        and player.player_id.startswith(CONTEST_PREFIX)
    ]


def _score_players(
    salary: pd.DataFrame,
    ceiling: pd.DataFrame,
    index: OpportunityIndex,
    *,
    extra_whitelist: frozenset[str] = frozenset(),
    extra_floors: Mapping[str, float] | None = None,
) -> list[PoolPlayer]:
    quantiles = load_quantiles(CALIBRATION_PATH) if CALIBRATION_PATH.is_file() else {"skill": [], "dst": []}
    frame = score_week11_frame(
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


def build_week11_pool(
    salary: pd.DataFrame,
    ceiling: pd.DataFrame,
    index: OpportunityIndex,
) -> tuple[list[PoolPlayer], list[PoolPlayer]]:
    """Score the slate and keep two pass catchers on every team."""

    players = _score_players(salary, ceiling, index)
    pool = _eligible(players)
    teams = sorted({normalize_team_abbr(str(team)) for team in salary["Team"].dropna().tolist()})
    counts: Counter[str] = Counter(player.team for player in pool if player.position in {"WR", "TE"})
    short = [team for team in teams if counts[team] < 2]
    if short:
        extra, floors = _promote_catchers(salary, short, pool)
        extra = frozenset(name for name in extra if name not in NAMED_EXCLUDES)
        floors = {name: value for name, value in floors.items() if name in extra}
        print(f"pass-catcher promote {sorted(extra)}")
        players = _score_players(
            salary,
            ceiling,
            index,
            extra_whitelist=extra,
            extra_floors=floors,
        )
        pool = _eligible(players)
    _assert_pool_starters(pool, teams)
    return players, pool


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


def player_cap_map(players: Sequence[PoolPlayer]) -> dict[str, int]:
    caps: dict[str, int] = {}
    for player in players:
        cap = PLAYER_CAP_NAMES.get(fold_name(player.nickname))
        if cap is not None:
            caps[player.player_id] = cap
    return caps


def write_desk_files(salary: pd.DataFrame) -> None:
    """Write the scratch file, the QB file, and the weather file."""

    SCRATCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in salary.to_dict(orient="records"):
        name = _display(record)
        key = fold_name(name)
        team = str(record.get("Team") or "").strip()
        status = status_token(record.get("Injury Indicator"))
        details = str(record.get("Injury Details") or "").strip()
        if status in HARD_TOKENS:
            rows.append(_scratch_row(name, team, status, "1", details or "FanDuel salary status"))
            seen.add(key)
    for name in Q_EXCLUDES:
        if fold_name(name) in seen:
            continue
        match = _salary_row(salary, name)
        team = "" if match is None else str(match.get("Team") or "")
        rows.append(_scratch_row(name, team, "Q", "1", "Saturday high-risk exclude"))
        seen.add(fold_name(name))
    for name in ROSTER_EXCLUDES:
        if fold_name(name) in seen:
            continue
        match = _salary_row(salary, name)
        team = "" if match is None else str(match.get("Team") or "")
        note = "FD team DAL; Saints waived him Nov 7; Cowboys practice squad Nov 11"
        rows.append(_scratch_row(name, team, "", "1", note))
        seen.add(fold_name(name))
    for name in KEEP_NAMES:
        if fold_name(name) in seen:
            continue
        match = _salary_row(salary, name)
        team = "" if match is None else str(match.get("Team") or "")
        status = "" if match is None else status_token(match.get("Injury Indicator"))
        rows.append(_scratch_row(name, team, status, "0", "Saturday keep"))
    match = _salary_row(salary, "Keaton Mitchell")
    if match is not None and fold_name("Keaton Mitchell") not in seen:
        rows.append(
            _scratch_row(
                "Keaton Mitchell",
                str(match.get("Team") or ""),
                status_token(match.get("Injury Indicator")),
                "0",
                "ESPN Week 11 roster is LAC. FanDuel team matches.",
            )
        )
    rows.sort(key=lambda item: (item["team"], item["name"]))
    _write_csv(SCRATCH_PATH, ["name", "team", "status", "exclude", "lock", "note"], rows)
    print(f"scratch -> {SCRATCH_PATH} ({len(rows)} rows)")

    backups: dict[str, list[str]] = defaultdict(list)
    for record in salary.to_dict(orient="records"):
        if canon_position(record.get("Position")) != "QB":
            continue
        team = normalize_team_abbr(str(record.get("Team") or ""))
        name = _display(record)
        starter = QB_STARTERS.get(team, "")
        if fold_name(name) == fold_name(starter):
            continue
        backups[team].append(name)
    starter_rows = []
    for team, starter in sorted(QB_STARTERS.items()):
        starter_rows.append(
            {
                "Team": team,
                "Starter": starter,
                "backups_hard_exclude": "|".join(backups.get(team, [])),
            }
        )
    _write_csv(STARTER_PATH, ["Team", "Starter", "backups_hard_exclude"], starter_rows)
    print(f"qb starters -> {STARTER_PATH}")

    env_rows = [
        ("ARI@KC", "open", "15", "0.95", "mild north wind; fade QB and WR tails"),
        ("BAL@CAR", "unposted", "0", "1.00", "no desk weather call"),
        ("JAC@NYG", "open", "0", "1.00", "64% rain note; no projection fade"),
        ("LV@DEN", "unposted", "0", "1.00", "no desk weather call"),
        ("MIA@BUF", "unposted", "0", "1.00", "no desk weather call"),
        ("NO@CHI", "open", "15", "0.88", "84% rain and 15 mph wind; fade QB WR TE tails"),
        ("NYJ@LAC", "dome", "0", "1.00", "SoFi indoor"),
        ("PIT@PHI", "open", "0", "1.00", "74% rain note; no projection fade"),
        ("TB@DET", "dome", "0", "1.00", "Ford Field dome"),
        ("TEN@DAL", "retractable", "0", "1.00", "no wind fade unless the roof is open Sunday"),
    ]
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ENV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["game", "roof", "wind_mph", "pass_scale", "note"])
        writer.writerows(env_rows)
    print(f"environment -> {ENV_PATH}")


def _scratch_row(name: str, team: str, status: str, exclude: str, note: str) -> dict[str, str]:
    return {
        "name": name,
        "team": team,
        "status": status,
        "exclude": exclude,
        "lock": "",
        "note": note,
    }


def _salary_row(salary: pd.DataFrame, name: str) -> Mapping[str, object] | None:
    for record in salary.to_dict(orient="records"):
        if fold_name(_display(record)) == fold_name(name):
            return record
    return None


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(rows)


def _select(candidates: list[Candidate], pool: list[PoolPlayer], caps: Mapping[str, int]) -> list[Candidate]:
    teams = {player.player_id: player.team for player in pool}
    shared = dict(
        count=BOOK_SIZE,
        caps=BOOK_CAP,
        pair_cap=None,
        rb_te_cap=None,
        player_caps=caps,
        player_teams=teams,
        team_lineup_cap=TEAM_CAP,
        max_shared=8,
        allow_cheap=0,
    )
    book = select_book(candidates, **shared)
    if len(book) >= BOOK_SIZE:
        return book
    relaxed = select_book(
        candidates,
        **{**shared, "allow_cheap": BOOK_SIZE, "min_salary": 0},
    )
    return relaxed if len(relaxed) > len(book) else book


def _gap_remaining(
    book: Sequence[Candidate],
    pool: Sequence[PoolPlayer],
    caps: Mapping[str, int],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    team_hits: Counter[str] = Counter()
    teams = {player.player_id: player.team for player in pool}
    for item in book:
        clubs: set[str] = set()
        for pid, _pos in item.positions:
            counts[pid] += 1
            club = teams.get(pid, "")
            if club:
                clubs.add(club)
        for club in clubs:
            team_hits[club] += 1
    remaining: dict[str, int] = {}
    for player in pool:
        limit = min(BOOK_CAP.get(player.position, SKILL_CAP), caps.get(player.player_id, SKILL_CAP))
        left = limit - counts[player.player_id]
        if team_hits[player.team] >= TEAM_CAP:
            left = 0
        remaining[player.player_id] = max(0, left)
    return remaining


def _print_wall(book: Sequence[Candidate], pool: Sequence[PoolPlayer], caps: Mapping[str, int]) -> None:
    counts: Counter[str] = Counter()
    team_hits: Counter[str] = Counter()
    meta = {player.player_id: player for player in pool}
    for item in book:
        clubs: set[str] = set()
        for pid, _pos in item.positions:
            counts[pid] += 1
            clubs.add(meta[pid].team)
        for club in clubs:
            team_hits[club] += 1
    print("players at cap")
    for pid, used in counts.most_common():
        player = meta[pid]
        limit = min(BOOK_CAP.get(player.position, SKILL_CAP), caps.get(pid, SKILL_CAP))
        if used >= limit:
            print(f"{player.nickname} | {player.position} | {player.team} | {used} | cap {limit}")
    print("teams near cap")
    for club, used in team_hits.most_common():
        if used >= TEAM_CAP - 3:
            print(f"{club} | {used}")


def _fill_short_book(
    candidates: list[Candidate],
    pool: list[PoolPlayer],
    caps: Mapping[str, int],
) -> list[Candidate]:
    """Keep the current book. Add lineups that avoid players who are at a cap."""

    import numpy as np

    book = _select(candidates, pool, caps)
    if len(book) >= BOOK_SIZE:
        return book
    meta = {player.player_id: player for player in pool}
    teams = {player.player_id: player.team for player in pool}
    floors = (MIN_SALARY, MIN_SALARY, 56000, 54000, 0, 0)
    for attempt, floor in enumerate(floors, start=1):
        if len(book) >= BOOK_SIZE:
            break
        remaining = _gap_remaining(book, pool, caps)
        open_pos = Counter(
            player.position for player in pool if remaining.get(player.player_id, 0) > 0
        )
        print(
            f"gap {attempt}: book {len(book)}; min salary {floor}; "
            f"open {dict(open_pos)}"
        )
        rng = np.random.default_rng(20261122 + attempt * 17)
        lineups = solve_wave(
            OPTIMIZER_PATH,
            meta,
            _noise_map(pool, rng, scale=1.2 + 0.25 * attempt),
            count=36,
            stacks=["qb:2"] if attempt <= 3 else [],
            bringback=False,
            repeating=8,
            min_salary=floor,
            remaining=remaining,
            qb_wave_cap=8,
        )
        fresh: list[Candidate] = []
        seen = {item.key for item in book}
        for lineup in lineups:
            item = candidate_from_lineup(lineup, meta, banned_teams=frozenset())
            if item is None or item.key in seen:
                continue
            seen.add(item.key)
            fresh.append(item)
        before = len(book)
        book = select_book(
            [*book, *fresh],
            count=BOOK_SIZE,
            caps=BOOK_CAP,
            pair_cap=None,
            rb_te_cap=None,
            player_caps=caps,
            player_teams=teams,
            team_lineup_cap=TEAM_CAP,
            max_shared=8,
            allow_cheap=BOOK_SIZE,
            min_salary=0,
            locked=book,
        )
        print(f"gap {attempt} new {len(fresh)}; book {before} -> {len(book)}")
    return book


def _game_hits(book: Sequence[Candidate], meta: Mapping[str, PoolPlayer]) -> Counter[str]:
    hits: Counter[str] = Counter()
    for item in book:
        games = {meta[pid].game for pid in item.ids if pid in meta}
        for game in games:
            hits[game] += 1
    return hits


def _assert_book(book: Sequence[Candidate], players: Sequence[PoolPlayer]) -> None:
    meta = {player.player_id: player for player in players}
    counts: Counter[str] = Counter()
    team_hits: Counter[str] = Counter()
    keys = []
    rostered: dict[str, set[str]] = defaultdict(set)
    for item in book:
        keys.append(item.key)
        if item.salary > 60000 or item.salary <= 0:
            raise AssertionError(f"salary {item.salary}")
        clubs = set()
        for pid in item.ids:
            player = meta[pid]
            counts[pid] += 1
            clubs.add(player.team)
            if player.never_enter or fold_name(player.nickname) in NAMED_EXCLUDES:
                raise AssertionError(player.nickname)
            if not pid.startswith(CONTEST_PREFIX):
                raise AssertionError(pid)
        for club in clubs:
            team_hits[club] += 1
        for pid, pos in item.positions:
            player = meta[pid]
            if pos == "QB" and is_backup_quarterback(player.team, player.nickname, "QB", QB_STARTERS):
                raise AssertionError(player.nickname)
            if pos == "QB":
                rostered[player.team].add(fold_name(player.nickname))
    if len(book) != BOOK_SIZE or len(set(keys)) != BOOK_SIZE:
        raise AssertionError(f"unique lineups {len(set(keys))}")
    assert_one_qb_per_team(rostered)
    for pid, used in counts.items():
        player = meta[pid]
        if player.position in {"QB", "RB", "WR", "TE", "DST"} and used > SKILL_CAP:
            raise AssertionError(f"{player.nickname} {used} > {SKILL_CAP}")
        cap = PLAYER_CAP_NAMES.get(fold_name(player.nickname))
        if cap is not None and used > cap:
            raise AssertionError(f"{player.nickname} {used} > {cap}")
    for club, used in team_hits.items():
        if used > TEAM_CAP:
            raise AssertionError(f"{club} {used} > {TEAM_CAP}")
    games = _game_hits(book, meta)
    missing = [game for game in MUST_HIT_GAMES if games[game] <= 0]
    if missing:
        raise AssertionError(f"zero-exposure games {missing}")


def _print_book(
    book: Sequence[Candidate],
    players: Sequence[PoolPlayer],
    audit: Mapping[str, object],
    q_ids: set[str],
) -> None:
    meta = {player.player_id: player for player in players}
    print(
        f"book {audit['lineups']} unique; salary {audit['salary_min']}-{audit['salary_max']}; "
        f"under {MIN_SALARY}: {audit['under_floor']}; "
        f"bring-back {audit['bringback']}; secondary {audit['secondary']}"
    )
    print("top 5 stacks")
    tags: Counter[str] = Counter(item.tags for item in book)
    for tag, used in tags.most_common(5):
        print(f"{used} | {tag}")
    print("top 25 exposure")
    print("player | pos | team | lineups | pct")
    for name, pos, team, used, pct in exposure_table(book, meta, limit=25):
        print(f"{name} | {pos} | {team} | {used} | {pct:.1f}")
    print("required games")
    games = _game_hits(book, meta)
    for game in MUST_HIT_GAMES:
        print(f"{game} | {games[game]} | {100.0 * games[game] / len(book):.1f}%")
    print("Q players in the book")
    q_counts: Counter[str] = Counter()
    q_meta: dict[str, PoolPlayer] = {}
    for item in book:
        for pid in item.ids:
            player = meta[pid]
            if pid in q_ids and not player.never_enter:
                q_counts[pid] += 1
                q_meta[pid] = player
    if not q_counts:
        print("No Q player is in a lineup.")
    for pid, used in q_counts.most_common():
        player = q_meta[pid]
        print(f"{player.nickname} | {player.team} | {player.position} | {used} | check 11:30 AM ET")
    ranked = sorted(book, key=lambda item: item.blend, reverse=True)[:5]
    print("top 5 lineups")
    for index, item in enumerate(ranked, start=1):
        names = [f"{meta[pid].nickname} ${meta[pid].salary}" for _slot, pid in item.seats]
        print(f"{index}. ${item.salary} blend {item.blend:.2f} | {item.tags}")
        print("   " + "; ".join(names))


def _archive(salary_path: Path, projections: Path, report: Path) -> None:
    destination = RECAP_DIR
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        destination = RUN_DIR / "recap"
        destination.mkdir(parents=True, exist_ok=True)
        print(f"recap path failed ({exc}); wrote {destination}")
    for source, name in (
        (salary_path, "_src_fd_sun.csv"),
        (projections, projections.name),
        (report, report.name),
        (UPLOAD_PATH, UPLOAD_PATH.name),
    ):
        target = destination / name
        target.write_bytes(source.read_bytes())
        print(f"archive -> {target}")


def run_week11(*, source: Path | None = None) -> list[Candidate]:
    """Write the desk files and solve the 149-lineup book."""

    salary_path = source or SALARY_PATH
    if not salary_path.is_file():
        raise FileNotFoundError(salary_path)
    salary = pd.read_csv(salary_path)
    games = {canon_game(value) for value in salary["Game"].dropna().tolist()}
    if games != MAIN_GAMES:
        raise AssertionError(f"salary games {sorted(games)}")
    write_desk_files(salary)
    if not CEILING_PATH.is_file():
        from ceminidfs.situational.engine import run_slate

        run_slate(SEASON, WEEK, salary_path=salary_path, out_dir=CEILING_PATH.parent)
    ceiling = pd.read_csv(CEILING_PATH)
    pbp = pd.read_parquet(PBP_PATH)
    rosters = pd.read_parquet(ROSTER_PATH) if ROSTER_PATH.is_file() else pd.DataFrame()
    snap_path = Path("artifacts/cache/snap_counts_2026.parquet")
    participation = pd.read_parquet(snap_path) if snap_path.is_file() else None
    index = build_opportunity_index(
        pbp,
        rosters,
        season=SEASON,
        before_week=WEEK,
        participation=participation,
    )
    gate = build_prelock_gate(
        salary_path,
        scratch_csv=SCRATCH_PATH,
        qb_starters_csv=STARTER_PATH,
        questionable_policy="keep",
        slate_date=SLATE_DATE,
    )
    print(format_questionable_warning(gate))
    all_players, pool = build_week11_pool(salary, ceiling, index)
    print(f"eligible pool {len(pool)} of {len(all_players)}")
    caps = player_cap_map(all_players)
    write_optimizer_csv(OPTIMIZER_PATH, pool)
    candidates = build_candidate_pool(
        OPTIMIZER_PATH,
        pool,
        caps=BOOK_CAP,
        banned_teams=frozenset(),
        pair_cap=None,
        player_caps=caps,
        rb_te_cap=None,
        max_waves=8,
        min_waves=1,
        wave_size=40,
        book_count=BOOK_SIZE,
        team_lineup_cap=TEAM_CAP,
        max_shared=8,
        require_floors=False,
        seed=20261122,
    )
    book = _fill_short_book(candidates, pool, caps)
    if len(book) != BOOK_SIZE:
        _print_wall(book, pool, caps)
        raise AssertionError(f"lineups {len(book)} of {BOOK_SIZE}")
    _assert_book(book, all_players)
    audit = {
        "lineups": len(book),
        "salary_min": min(item.salary for item in book),
        "salary_max": max(item.salary for item in book),
        "bringback": sum(item.bringback for item in book),
        "secondary": sum(item.secondary for item in book),
        "under_floor": sum(1 for item in book if item.salary < MIN_SALARY),
    }
    try:
        verify_book(
            book,
            all_players,
            caps=BOOK_CAP,
            banned_teams=frozenset(),
            contest_prefix=CONTEST_PREFIX,
            player_caps=caps,
            count=BOOK_SIZE,
        )
    except AssertionError as exc:
        print(f"portfolio note: {exc}")
    write_book_files(
        book,
        UPLOAD_PATH,
        IDS_PATH,
        season=SEASON,
        week=WEEK,
        players=all_players,
        slate_date=SLATE_DATE,
        run_dir=RUN_DIR,
        recap_root=RECAP_DIR,
    )
    projections, report, summary = finish_lineup_outputs(
        gate,
        salary_csv=salary_path,
        lineups_csv=UPLOAD_PATH,
        output_dir=RUN_DIR,
        archive_dir=None,
    )
    print(summary)
    q_ids = {
        str(record.get("Id") or "")
        for record in salary.to_dict(orient="records")
        if status_token(record.get("Injury Indicator")) == "Q"
    }
    _print_book(book, all_players, audit, q_ids)
    _archive(salary_path, projections, report)
    print(f"upload -> {UPLOAD_PATH}")
    return book


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build the Week 11 FanDuel 149-lineup book.")
    parser.add_argument("--source", type=Path, default=None)
    args = parser.parse_args()
    run_week11(source=args.source)


if __name__ == "__main__":
    main()
