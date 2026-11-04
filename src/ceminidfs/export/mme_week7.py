"""Week 7 FanDuel 150-lineup book for the 2026-10-25 main slate.

The Paris game (PIT@NO, 9:30 AM ET) is not in the FanDuel salary file.
The book uses the 10 main-slate games only. One starting quarterback is
allowed per team. A skill player with zero targets and carries in his
team's active weeks inside Weeks 5 and 6 stays out of the pool.
"""

from __future__ import annotations

import json
import math
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
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
    canon_position,
    exposure_table,
    fold_name,
    is_hard_exclude,
    load_quantiles,
    players_from_frame,
    rb_pairs,
    score_pool_row,
    select_book,
    set_nicknames,
    verify_book,
    write_book_files,
    write_optimizer_csv,
)
from ceminidfs.situational.engine import q4_rb_checkdown_score, run_slate
from ceminidfs.situational.shared_cache import write_shared_cache

CONTEST_PREFIX = "135562-"
SEASON = 2026
WEEK = 7
MAX_SOURCE_WEEK = 6
TOUCH_WEEKS = (5, 6)
BOOK_CAP = {
    "QB": 36,
    "RB": 45,
    "WR": 48,
    "TE": 48,
    "DST": 33,
}
RB_PAIR_CAP = 24
WATSON_CAP = 7
LATE_Q_CAP = 12
BANNED_TEAMS: frozenset[str] = frozenset()
SKILL_POSITIONS = frozenset({"RB", "WR", "TE"})
NAME_SUFFIXES = frozenset({"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"})

MAIN_GAMES = frozenset(
    {
        "CIN@BAL",
        "CLE@TEN",
        "DEN@ARI",
        "GB@DET",
        "IND@MIN",
        "LAR@LV",
        "MIA@NYJ",
        "NYG@HOU",
        "SF@ATL",
        "TB@CAR",
    }
)
DOME_GAMES = frozenset({"GB@DET", "LAR@LV", "IND@MIN"})
STRONG_PASS_FADE = frozenset({"SF@ATL"})
MILD_PASS_FADE = frozenset({"TB@CAR", "NYG@HOU"})
RUSH_BOOST_NAMES = frozenset({"christian mccaffrey", "bijan robinson"})
LAR_VOLUME_NAMES = frozenset({"colby parkinson", "tyler higbee", "kyren williams"})
TOUCH_EXCEPTIONS = frozenset({"woody marks"})
PLAYER_CAP_NAMES = {
    "deshaun watson": WATSON_CAP,
    "puka nacua": LATE_Q_CAP,
    "calvin ridley": LATE_Q_CAP,
}
STARTER_FLOORS = {"tyler huntley": 17.0}

# Week 5 max-attempt passer, with the Saturday starter overrides.
# TB was Jalon Daniels in Week 5. Baker Mayfield is the Week 7 starter.
QB_STARTERS = {
    "ARI": "Jacoby Brissett",
    "ATL": "Michael Penix Jr.",
    "BAL": "Tyler Huntley",
    "CAR": "Bryce Young",
    "CIN": "Joe Burrow",
    "CLE": "Deshaun Watson",
    "DEN": "Bo Nix",
    "DET": "Jared Goff",
    "GB": "Jordan Love",
    "HOU": "C.J. Stroud",
    "IND": "Daniel Jones",
    "LAR": "Matthew Stafford",
    "LV": "Kirk Cousins",
    "MIA": "Malik Willis",
    "MIN": "Kyler Murray",
    "NYG": "Jameis Winston",
    "NYJ": "Geno Smith",
    "SF": "Brock Purdy",
    "TB": "Baker Mayfield",
    "TEN": "Cam Ward",
}
QB_STARTER_KEYS = {team: fold_name(name) for team, name in QB_STARTERS.items()}

# Packet reserves the salary file must keep at 0 even when the indicator is blank.
NAMED_EXCLUDES = frozenset(
    fold_name(name)
    for name in (
        "Lamar Jackson",
        "Dillon Gabriel",
        "Jaxson Dart",
        "Skylar Thompson",
        "De'Von Achane",
        "David Montgomery",
        "Brian Robinson",
        "Jeremiyah Love",
        "James Conner",
        "Trey Benson",
        "Isiah Pacheco",
        "Tyler Badie",
        "Jonathon Brooks",
        "Raheim Sanders",
        "Ty Chandler",
        "Travis Etienne Jr.",
        "Davante Adams",
        "Mike Evans",
        "Deebo Samuel Sr.",
        "Emeka Egbuka",
        "Jayden Reed",
        "Skyy Moore",
        "Alec Pierce",
        "Anthony Gould",
        "Ricky Pearsall",
        "Demarcus Robinson",
        "Xavier Legette",
        "Michael Pittman Jr.",
        "Roman Wilson",
        "Ben Skowronek",
        "Beaux Collins",
        "Tyler Warren",
        "Theo Johnson",
        "Luke Musgrave",
        "Josh Oliver",
        "Jake Tonges",
        "Tanner Hudson",
        "Carter Runyon",
        "Jalon Daniels",
        "Carson Beck",
        "Tua Tagovailoa",
        "Jake Haener",
        "Tommy DeVito",
    )
)

DESKTOP_SALARY = Path(
    "/Users/claudiobarone/Desktop/FanDuel-NFL-2026 EDT-10 EDT-25 EDT-135562-players-list.csv"
)
SALARY_PATH = Path("data/slates/2026-10-25_fd_sun.csv")
RUN_DIR = Path("runs/2026_week_7")
SRC_COPY = RUN_DIR / "_src_fd_sun.csv"
RECAP_COPY = Path("/workspace/dfs-recap/2026-10-25/_src_fd_sun.csv")
CEILING_PATH = RUN_DIR / "situational" / "ceiling.csv"
CALIBRATION_PATH = RUN_DIR / "situational" / "calibration.json"
OPTIMIZER_PATH = RUN_DIR / "portfolio_optimizer.csv"
UPLOAD_PATH = RUN_DIR / "fanduel_150_upload_2026-10-25.csv"
IDS_PATH = RUN_DIR / "fanduel_150_ids_only.csv"
SHARED_DIR = Path("data/shared_cache/2026_w07")
PBP_PATH = Path("artifacts/cache/pbp_2026.parquet")
ROSTER_PATH = Path("artifacts/cache/rosters_2026.parquet")


@dataclass(frozen=True)
class TouchIndex:
    """Touches inside Weeks 5 and 6, plus the teams that actually played."""

    by_name: Mapping[tuple[str, str], int]
    active_teams: frozenset[str]


def _club(value: object) -> str:
    """Return a team code. Blank and null play rows stay blank."""

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip().upper()
    if text in {"", "NAN", "NONE", "NAT"}:
        return ""
    return normalize_team_abbr(text)


def name_keys(value: object) -> set[str]:
    """Fold a display name into the keys used by the touch index."""

    folded = fold_name(value)
    if not folded:
        return set()
    keys = {folded}
    if "." in folded:
        tail = folded.split(".")[-1].strip()
        if tail:
            keys.add(tail)
    tokens = folded.split()
    if tokens and tokens[-1] in NAME_SUFFIXES:
        stem = " ".join(tokens[:-1]).strip()
        if stem:
            keys.add(stem)
    return keys


def trailing_active_touches(
    pbp: pd.DataFrame,
    rosters: pd.DataFrame | None,
    *,
    weeks: Sequence[int] = TOUCH_WEEKS,
) -> TouchIndex:
    """Sum targets and carries on team-weeks that exist in the cache.

    A team with no plays in ``weeks`` is not active. The floor does not
    apply to that team. Week 6 in the local cache is only SEA@DEN, so most
    clubs are judged on Week 5 alone.
    """

    week_set = {int(week) for week in weeks}
    frame = pbp.copy()
    frame["week"] = pd.to_numeric(frame.get("week"), errors="coerce")
    frame = frame.loc[frame["week"].isin(week_set)].copy()
    if frame.empty or "posteam" not in frame.columns:
        return TouchIndex(by_name={}, active_teams=frozenset())
    frame["team"] = frame["posteam"].map(_club)
    frame = frame.loc[frame["team"].ne("")].copy()
    active = frozenset(frame["team"].dropna().astype(str))
    if frame.empty:
        return TouchIndex(by_name={}, active_teams=active)

    names: dict[str, set[str]] = defaultdict(set)
    if rosters is not None and not rosters.empty and "gsis_id" in rosters.columns:
        for record in rosters.to_dict(orient="records"):
            gsis = str(record.get("gsis_id") or "")
            if not gsis:
                continue
            for column in ("full_name", "football_name"):
                names[gsis] |= name_keys(record.get(column))
            full = f"{record.get('first_name') or ''} {record.get('last_name') or ''}".strip()
            names[gsis] |= name_keys(full)

    counts: dict[tuple[str, str], int] = defaultdict(int)

    def add(mask: pd.Series, id_column: str, name_column: str) -> None:
        if id_column not in frame.columns:
            return
        part = frame.loc[mask, ["team", id_column, name_column]].copy() if name_column in frame.columns else frame.loc[mask, ["team", id_column]].copy()
        part = part.dropna(subset=[id_column])
        for record in part.to_dict(orient="records"):
            gsis = str(record.get(id_column) or "")
            team = str(record.get("team") or "")
            if not gsis or not team:
                continue
            counts[(team, gsis)] += 1
            if name_column in record:
                names[gsis] |= name_keys(record.get(name_column))

    passed = pd.to_numeric(frame.get("pass"), errors="coerce").fillna(0).eq(1)
    rushed = pd.to_numeric(frame.get("rush"), errors="coerce").fillna(0).eq(1)
    add(passed, "receiver_player_id", "receiver_player_name")
    add(rushed, "rusher_player_id", "rusher_player_name")

    by_name: dict[tuple[str, str], int] = {}
    for (team, gsis), touches in counts.items():
        for key in names.get(gsis, set()):
            by_name[(team, key)] = by_name.get((team, key), 0) + int(touches)
    return TouchIndex(by_name=by_name, active_teams=active)


def _last_token(name: str) -> str:
    tokens = name.split()
    token = tokens[-1] if tokens else name
    if token in NAME_SUFFIXES and len(tokens) > 1:
        token = tokens[-2]
    if "." in token:
        token = token.split(".")[-1]
    return token


def lookup_touches(index: TouchIndex, team: object, nickname: object, last_name: object) -> int | None:
    """Return touches, or None when the team has no active week in the window."""

    club = normalize_team_abbr(str(team or ""))
    if club not in index.active_teams:
        return None
    for key in name_keys(nickname):
        found = index.by_name.get((club, key))
        if found is not None:
            return int(found)
    last = _last_token(fold_name(last_name))
    hits = [
        value
        for (club_key, name), value in index.by_name.items()
        if club_key == club and _last_token(name) == last
    ]
    if len(hits) == 1:
        return int(hits[0])
    if not hits:
        return 0
    return int(max(hits))


def blocked_by_touch_floor(
    position: object,
    team: object,
    nickname: object,
    last_name: object,
    index: TouchIndex,
) -> bool:
    """True when a skill player has zero touches on an active team-week."""

    if canon_position(position) not in SKILL_POSITIONS:
        return False
    if fold_name(nickname) in TOUCH_EXCEPTIONS:
        return False
    touches = lookup_touches(index, team, nickname, last_name)
    if touches is None:
        return False
    return touches <= 0


def backup_quarterback(team: object, nickname: object, position: object) -> bool:
    """True when this quarterback is not the one starter for his team."""

    if canon_position(position) != "QB":
        return False
    club = normalize_team_abbr(str(team or ""))
    starter = QB_STARTER_KEYS.get(club)
    if starter is None:
        return True
    return fold_name(nickname) != starter


def adjust_tails_week7(
    game: object,
    team: object,
    position: object,
    name: object,
    p90: float,
    p99: float,
) -> tuple[float, float]:
    """Scale tails for the Week 7 roof and wind rules.

    SF@ATL is an official open roof. Domes stay indoors and get a small
    pace boost. GB@DET gets the larger pass boost.
    """

    game_key = canon_game(game)
    club = normalize_team_abbr(str(team or ""))
    pos = canon_position(position)
    folded = fold_name(name)
    scale = 1.0
    if game_key in STRONG_PASS_FADE and club in {"SF", "ATL"}:
        if pos in {"QB", "WR"}:
            scale = 0.90
        elif pos == "RB" and folded in RUSH_BOOST_NAMES:
            scale = 1.08
        elif pos == "TE":
            scale = 1.04
    elif game_key in MILD_PASS_FADE:
        if pos == "WR":
            scale = 0.97
        elif pos in {"RB", "TE"}:
            scale = 1.05
        elif pos == "QB":
            scale = 0.99
    elif game_key in DOME_GAMES:
        if game_key == "GB@DET" and pos in {"QB", "WR", "TE"}:
            scale = 1.06
        elif game_key == "GB@DET" and pos == "RB":
            scale = 1.03
        elif pos in {"QB", "RB", "WR", "TE"}:
            scale = 1.04
    if folded in LAR_VOLUME_NAMES:
        scale *= 1.08
    return p90 * scale, p99 * scale


def week7_blocked(
    record: Mapping[str, object],
    index: TouchIndex,
) -> bool:
    """Return True when Week 7 rules set this salary row to 0 points."""

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
        banned_teams=BANNED_TEAMS,
        named_excludes=NAMED_EXCLUDES,
    ):
        return True
    if backup_quarterback(team, display, position):
        return True
    return blocked_by_touch_floor(position, team, display, last, index)


def score_week7_frame(
    salary: pd.DataFrame,
    ceiling: pd.DataFrame,
    quantiles: Mapping[str, object],
    index: TouchIndex,
) -> pd.DataFrame:
    """Join the salary file to the ceiling and apply the Week 7 overlay."""

    sal = salary.copy()
    sal["player_id"] = sal["Id"].astype(str)
    ceil = ceiling.copy()
    ceil["player_id"] = ceil["player_id"].astype(str)
    keep = [column for column in ("player_id", "lagged_fd", "p90", "p99") if column in ceil.columns]
    merged = sal.merge(ceil[keep], on="player_id", how="left")
    skill = list(quantiles.get("skill") or [])
    dst_table = list(quantiles.get("dst") or [])
    rows = [
        _score_week7_row(record, skill, dst_table, index)
        for record in merged.to_dict(orient="records")
    ]
    return pd.DataFrame(rows)


def _score_week7_row(
    record: Mapping[str, object],
    skill: list[dict],
    dst_table: list[dict],
    index: TouchIndex,
) -> dict[str, object]:
    return score_pool_row(
        record,
        skill,
        dst_table,
        blocked=lambda rec: week7_blocked(rec, index),
        tails=lambda game, team, position, display, p90, p99: adjust_tails_week7(
            game, team, position, display, p90, p99
        ),
        floor_lookup=lambda display: STARTER_FLOORS.get(fold_name(display)),
    )


def assert_one_starter(pool: Sequence[PoolPlayer], teams: Sequence[str]) -> None:
    """Raise when a slate team has more than one eligible quarterback."""

    by_team: dict[str, list[str]] = defaultdict(list)
    for player in pool:
        if player.position == "QB":
            by_team[player.team].append(player.nickname)
    missing = [team for team in teams if team not in by_team]
    extra = {team: names for team, names in by_team.items() if len(names) > 1}
    if missing or extra:
        raise AssertionError(f"quarterback whitelist missing={missing} extra={extra}")


def player_cap_map(players: Sequence[PoolPlayer]) -> dict[str, int]:
    caps: dict[str, int] = {}
    for player in players:
        cap = PLAYER_CAP_NAMES.get(fold_name(player.nickname))
        if cap is not None:
            caps[player.player_id] = cap
    return caps


def stamp_open_roof(games: pd.DataFrame) -> pd.DataFrame:
    """Mark SF@ATL as outdoors. The official roof call for Week 7 is open."""

    out = games.copy()
    if "away_team" not in out.columns or "home_team" not in out.columns:
        return out
    away = out["away_team"].map(lambda value: normalize_team_abbr(str(value or "")))
    home = out["home_team"].map(lambda value: normalize_team_abbr(str(value or "")))
    mask = away.eq("SF") & home.eq("ATL")
    if "roof" in out.columns:
        out.loc[mask, "roof"] = "outdoors"
    if "wind" in out.columns:
        out.loc[mask, "wind"] = 15.0
    return out


def archive_salary(source: Path) -> Path:
    """Copy the FanDuel file into the slate folder and the Week 7 run folder."""

    if not source.is_file():
        raise FileNotFoundError(source)
    SALARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SRC_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, SALARY_PATH)
    shutil.copyfile(source, SRC_COPY)
    if RECAP_COPY.parent.parent.is_dir():
        RECAP_COPY.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, RECAP_COPY)
        print(f"recap copy -> {RECAP_COPY}")
    else:
        print("recap copy skipped: /workspace/dfs-recap is not on this machine")
    print(f"salary -> {SALARY_PATH}")
    print(f"src -> {SRC_COPY}")
    return SALARY_PATH


def _cache_ready(path: Path) -> bool:
    manifest_path = path / "manifest.json"
    players_path = path / "player_telemetry_pit.parquet"
    if not manifest_path.is_file() or not players_path.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("max_source_week", -1)) != MAX_SOURCE_WEEK:
        return False
    columns = set(pd.read_parquet(players_path).columns)
    required = {"vacated_target_boost", "vacated_rz_boost", "q4_rb_checkdown_score"}
    return required <= columns


def refresh_shared_cache(salary_path: Path) -> dict:
    """Score the slate and write the Week 7 shared cache. max source week is 6."""

    if not _cache_ready(SHARED_DIR) or not CEILING_PATH.is_file():
        run_slate(SEASON, WEEK, salary_path=salary_path, out_dir=CEILING_PATH.parent)
    manifest = json.loads((SHARED_DIR / "manifest.json").read_text(encoding="utf-8"))
    players = pd.read_parquet(SHARED_DIR / "player_telemetry_pit.parquet")
    defense = pd.read_parquet(SHARED_DIR / "defense_counterpart_pit.parquet")
    games = stamp_open_roof(pd.read_parquet(SHARED_DIR / "game_context_pit.parquet"))
    if "q4_rb_checkdown_score" not in players.columns:
        players["q4_rb_checkdown_score"] = q4_rb_checkdown_score(players)
    written = write_shared_cache(
        SHARED_DIR,
        players=players,
        defense=defense,
        games=games,
        season=SEASON,
        week=WEEK,
        max_source_week=int(manifest["max_source_week"]),
    )
    if int(written["max_source_week"]) != MAX_SOURCE_WEEK:
        raise AssertionError(f"max_source_week {written['max_source_week']}")
    print(f"shared cache -> {SHARED_DIR} max_source_week={written['max_source_week']}")
    return written


def load_touch_index() -> TouchIndex:
    pbp = pd.read_parquet(PBP_PATH)
    rosters = pd.read_parquet(ROSTER_PATH) if ROSTER_PATH.is_file() else pd.DataFrame()
    return trailing_active_touches(pbp, rosters)


def salary_games(salary: pd.DataFrame) -> list[str]:
    return sorted({canon_game(value) for value in salary["Game"].dropna().tolist()})


def run_week7(*, source: Path | None = None) -> list[Candidate]:
    """Archive the salary file, write the cache, and solve the 150-lineup book."""

    salary_path = archive_salary(source or _default_source())
    salary = pd.read_csv(salary_path)
    games = salary_games(salary)
    if "PIT@NO" in games or "NO@PIT" in games:
        raise AssertionError("Paris game is in the salary file; this build expects it to be absent")
    if set(games) != MAIN_GAMES:
        raise AssertionError(f"salary games {games}")
    refresh_shared_cache(salary_path)
    if not CEILING_PATH.is_file():
        raise FileNotFoundError(CEILING_PATH)
    ceiling = pd.read_csv(CEILING_PATH)
    index = load_touch_index()
    portfolio = score_week7_frame(salary, ceiling, load_quantiles(CALIBRATION_PATH), index)
    all_players = players_from_frame(portfolio)
    set_nicknames(all_players)
    pool = [
        player
        for player in all_players
        if not player.never_enter and player.fpts > 0 and player.salary > 0 and player.player_id.startswith(CONTEST_PREFIX)
    ]
    teams = sorted({normalize_team_abbr(str(team)) for team in salary["Team"].dropna().tolist()})
    assert_one_starter(pool, teams)
    print(f"eligible pool {len(pool)} of {len(all_players)}; active touch teams {sorted(index.active_teams)}")
    caps = player_cap_map(all_players)
    write_optimizer_csv(OPTIMIZER_PATH, pool)
    candidates = build_candidate_pool(
        OPTIMIZER_PATH,
        pool,
        caps=BOOK_CAP,
        banned_teams=BANNED_TEAMS,
        pair_cap=RB_PAIR_CAP,
        player_caps=caps,
        max_waves=16,
        wave_size=36,
        seed=20261025,
    )
    book = select_book(
        candidates,
        caps=BOOK_CAP,
        pair_cap=RB_PAIR_CAP,
        player_caps=caps,
        allow_cheap=0,
    )
    if len(book) < BOOK_SIZE:
        relaxed = select_book(
            candidates,
            caps=BOOK_CAP,
            pair_cap=RB_PAIR_CAP,
            player_caps=caps,
            allow_cheap=CHEAP_LIMIT,
        )
        if len(relaxed) > len(book):
            book = relaxed
    audit = verify_book(
        book,
        all_players,
        caps=BOOK_CAP,
        banned_teams=BANNED_TEAMS,
        contest_prefix=CONTEST_PREFIX,
        pair_cap=RB_PAIR_CAP,
        player_caps=caps,
    )
    _assert_book_hygiene(book, all_players)
    write_book_files(book, UPLOAD_PATH, IDS_PATH)
    _print_week7(book, {player.player_id: player for player in all_players}, audit)
    print(f"upload -> {UPLOAD_PATH}")
    return book


def _assert_book_hygiene(book: Sequence[Candidate], players: Sequence[PoolPlayer]) -> None:
    meta = {player.player_id: player for player in players}
    backups = 0
    for item in book:
        for pid, pos in item.positions:
            player = meta[pid]
            if pos == "QB" and backup_quarterback(player.team, player.nickname, "QB"):
                backups += 1
            if player.never_enter:
                raise AssertionError(player.nickname)
    if backups:
        raise AssertionError(f"backup quarterbacks {backups}")
    pair_counts: Counter[tuple[str, str]] = Counter()
    rb_counts: Counter[str] = Counter()
    for item in book:
        runners = [pid for pid, pos in item.positions if pos == "RB"]
        rb_counts.update(runners)
        pair_counts.update(rb_pairs(item))
    if rb_counts and max(rb_counts.values()) > BOOK_CAP["RB"]:
        raise AssertionError("rb exposure")
    if pair_counts and max(pair_counts.values()) > RB_PAIR_CAP:
        raise AssertionError("rb pair exposure")


def _print_week7(
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
    print("top 10 rb pairs")
    pairs: Counter[tuple[str, str]] = audit["rb_pairs"]  # type: ignore[assignment]
    for (left, right), used in pairs.most_common(10):
        print(f"{meta[left].nickname} + {meta[right].nickname} | {used}")
    print("game stacks")
    games: Counter[str] = audit["games"]  # type: ignore[assignment]
    for game, used in games.most_common():
        print(f"{game} {used}")
    ranked = sorted(book, key=lambda item: item.blend, reverse=True)[:5]
    print("top 5 lineups")
    for index, item in enumerate(ranked, start=1):
        names = [f"{meta[pid].nickname} ${meta[pid].salary}" for _slot, pid in item.seats]
        print(f"{index}. ${item.salary} blend {item.blend:.2f} | {item.tags}")
        print("   " + "; ".join(names))


def _default_source() -> Path:
    if DESKTOP_SALARY.is_file():
        return DESKTOP_SALARY
    if SALARY_PATH.is_file():
        return SALARY_PATH
    downloads = sorted(Path.home().joinpath("Downloads").glob("FanDuel-NFL-2026*10*25*.csv"))
    if downloads:
        return downloads[-1]
    raise FileNotFoundError("Week 7 FanDuel salary CSV")


def main() -> None:
    run_week7()


if __name__ == "__main__":
    main()
