"""Week-6 FanDuel 150-lineup portfolio.

The scientific ceiling stays in place. This module applies the Saturday
slate overlay, then builds a diverse GPP book. It does not submit lineups.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from ceminidfs.data.stadiums import normalize_team_abbr
from ceminidfs.export.optimize import (
    LINEUP_HEADERS,
    _apply_fppg_overrides,
    _load_pydfs,
    _optimize_or_raise,
    keep_injury_tagged_players,
)
from ceminidfs.export.stack_rules import apply_stack_specs, attach_csv_original_positions, parse_stack_rules
from ceminidfs.situational.quantiles import DST_CAP, SKILL_CAP, apply_ceiling

BOOK_SIZE = 150
MIN_SALARY = 59200
MAX_SALARY = 60000
BRINGBACK_MIN = 113
SECONDARY_MIN = 75
MIN_UNIQUES = 3
MAX_SHARED = 9 - MIN_UNIQUES
BLEND_LAG = 0.35
BLEND_P90 = 0.45
BLEND_P99 = 0.20
SIGMA_SCALE = 0.18
SEED = 20261017
CONTEST_PREFIX = "135326-"
CHEAP_LIMIT = 15

# One player stays at or under 38 of 150 lineups (25%).
EXPOSURE_CAPS = {"QB": 38, "RB": 38, "WR": 38, "TE": 38, "DST": 38}
HARD_STATUS = frozenset({"O", "IR", "D", "SUSP", "NA", "PUP", "NFI"})
BANNED_TEAMS = frozenset({"HOU", "JAX"})
CATCHER_POSITIONS = frozenset({"WR", "TE"})
BRINGBACK_POSITIONS = frozenset({"WR", "RB", "TE"})
ZERO_WIND_GAMES = frozenset({"CHI@ATL", "ARI@LAR", "BUF@LV"})

# Named reserves and backup quarterbacks. Match the folded nickname.
NAMED_EXCLUDES = frozenset(
    {
        "kyle allen",
        "shane buechele",
        "cole payton",
        "gardner minshew ii",
        "carson beck",
        "will levis",
        "cade klubnik",
        "garrett nussmeier",
        "justin fields",
        "tyson bagent",
        "case keenum",
        "miller moss",
        "joe fagnano",
        "easton stick",
        "brett rypien",
        "jakobi lane",
        "alec ingold",
        "keagen trost",
    }
)

STARTER_FLOORS = {
    "tanner mckee": 15.8,
    "tyler huntley": 17.2,
    "jalon daniels": 15.4,
}

SALARY_PATH = Path("data/slates/2026-10-18_fd_sun.csv")
CEILING_PATH = Path("runs/2026_week_6/situational/ceiling.csv")
CALIBRATION_PATH = Path("runs/2026_week_6/situational/calibration.json")
OPTIMIZER_PATH = Path("runs/2026_week_6/portfolio_optimizer.csv")
UPLOAD_PATH = Path("runs/2026_week_6/fanduel_150_upload_2026-10-18.csv")
IDS_PATH = Path("runs/2026_week_6/fanduel_150_ids_only.csv")


def fold_name(value: object) -> str:
    """Fold a display name. Apostrophes and case do not change the key."""

    text = str(value or "")
    for src in ("\u2019", "\u2018", "`"):
        text = text.replace(src, "'")
    text = text.replace("'", "")
    return " ".join(text.casefold().split())


def canon_game(value: object) -> str:
    return str(value or "").replace(" ", "").upper()


def canon_position(value: object) -> str:
    token = str(value or "").strip().upper()
    if token in {"D", "DEF", "DST"}:
        return "DST"
    return token


def status_token(value: object) -> str:
    token = str(value or "").strip().upper()
    if token in {"", "NAN", "NONE", "NAT"}:
        return ""
    if token in {"OUT", "O"}:
        return "O"
    if token in {"DOUBTFUL", "D"}:
        return "D"
    if token in {"SUSPENDED", "SUSP"}:
        return "SUSP"
    if token in {"PUP", "PHYSICALLY UNABLE TO PERFORM"} or "PUP" in token:
        return "PUP"
    if token in {"NFI", "NON-FOOTBALL INJURY", "NONFOOTBALL INJURY"} or "NFI" in token:
        return "NFI"
    return token


def is_hard_exclude(
    status: object,
    name: object,
    team: object,
    details: object = "",
    *,
    banned_teams: frozenset[str] | None = None,
    named_excludes: frozenset[str] | None = None,
) -> bool:
    """Return True when the portfolio must keep this player at 0 points."""

    banned = BANNED_TEAMS if banned_teams is None else banned_teams
    named = NAMED_EXCLUDES if named_excludes is None else named_excludes
    if status_token(status) in HARD_STATUS:
        return True
    detail_text = str(details or "").upper()
    if "SUSPEND" in detail_text or "PUP" in detail_text or "NFI" in detail_text:
        return True
    if normalize_team_abbr(str(team or "")) in banned:
        return True
    return fold_name(name) in named


def blend_points(lagged: float, p90: float, p99: float) -> float:
    """Return ``0.35 * lag + 0.45 * p90 + 0.20 * p99``."""

    return BLEND_LAG * lagged + BLEND_P90 * p90 + BLEND_P99 * p99


def noise_sigma(p90: float, lagged: float) -> float:
    """Return ``0.18 * max(p90 - lagged, 0)``."""

    gap = p90 - lagged
    if not math.isfinite(gap) or gap <= 0:
        return 0.0
    return SIGMA_SCALE * gap


def adjust_tails(
    game: object,
    team: object,
    position: object,
    name: object,
    p90: float,
    p99: float,
) -> tuple[float, float]:
    """Scale p90 and p99 for the Saturday wind rules.

    Closed roofs, SoFi, and the Las Vegas dome stay flat. The Daniels 15.4
    floor is applied before this scale, so the wind cut hits only the tails.
    """

    game_key = canon_game(game)
    team_key = normalize_team_abbr(str(team or ""))
    pos = canon_position(position)
    if game_key in ZERO_WIND_GAMES:
        return p90, p99
    if game_key == "PIT@TB" and team_key in {"PIT", "TB"}:
        if pos in {"QB", "WR"}:
            return p90 * 0.90, p99 * 0.90
        if fold_name(name) == "bucky irving" or (pos == "DST" and team_key == "PIT"):
            return p90 * 1.06, p99 * 1.06
    if game_key == "LAC@KC" and team_key in {"LAC", "KC"}:
        if pos == "WR":
            return p90 * 0.97, p99 * 0.97
        if pos in {"RB", "TE"}:
            return p90 * 1.04, p99 * 1.04
    return p90, p99


def upload_cell(player_id: object, nickname: object) -> str:
    return f"{player_id}:{nickname}"


def shares_ok(left: Iterable[str], right: Iterable[str], max_shared: int = MAX_SHARED) -> bool:
    """Return True when two lineups share at most ``max_shared`` players."""

    return len(set(left) & set(right)) <= max_shared


@dataclass(frozen=True)
class PoolPlayer:
    player_id: str
    nickname: str
    team: str
    opp: str
    game: str
    position: str
    salary: int
    fpts: float
    lagged: float = 0.0
    p90: float = 0.0
    p99: float = 0.0
    sigma: float = 0.0
    never_enter: bool = False
    first_name: str = ""
    last_name: str = ""
    fd_position: str = ""


def _qb(players: Sequence[PoolPlayer]) -> PoolPlayer | None:
    for player in players:
        if player.position == "QB":
            return player
    return None


def catcher_count(players: Sequence[PoolPlayer]) -> int:
    """Count WR and TE teammates of the quarterback."""

    qb = _qb(players)
    if qb is None:
        return 0
    return sum(
        1
        for player in players
        if player.team == qb.team and player.position in CATCHER_POSITIONS
    )


def has_bringback(players: Sequence[PoolPlayer]) -> bool:
    """Return True when a WR, RB, or TE from the quarterback's opponent is in."""

    qb = _qb(players)
    if qb is None:
        return False
    return any(
        player.team == qb.opp and player.position in BRINGBACK_POSITIONS for player in players
    )


def has_rb_own_dst(players: Sequence[PoolPlayer]) -> bool:
    dst_teams = {player.team for player in players if player.position == "DST"}
    return any(player.position == "RB" and player.team in dst_teams for player in players)


def has_second_game(players: Sequence[PoolPlayer]) -> bool:
    """Return True for a WR plus an opposing WR or RB in a non-QB game."""

    qb = _qb(players)
    if qb is None:
        return False
    by_game: dict[str, list[PoolPlayer]] = defaultdict(list)
    for player in players:
        if player.game == qb.game or player.position not in {"WR", "RB"}:
            continue
        by_game[player.game].append(player)
    for group in by_game.values():
        sides: dict[str, set[str]] = defaultdict(set)
        for player in group:
            sides[player.team].add(player.position)
        if len(sides) < 2:
            continue
        left, right = list(sides.values())[:2]
        if ("WR" in left and ({"WR", "RB"} & right)) or ("WR" in right and ({"WR", "RB"} & left)):
            return True
    return False


def has_secondary(players: Sequence[PoolPlayer]) -> bool:
    return has_rb_own_dst(players) or has_second_game(players)


def primary_rb(players: Sequence[PoolPlayer]) -> PoolPlayer | None:
    rbs = [player for player in players if player.position == "RB"]
    if not rbs:
        return None
    return max(rbs, key=lambda player: (player.salary, player.player_id))


def dst_faces_qb_or_primary_rb(players: Sequence[PoolPlayer]) -> bool:
    """Return True when the DST faces the QB or the highest-salary RB.

    A defense on the quarterback's own team is allowed. A bring-back receiver
    from the defense's team is allowed when the defense is not opposing the
    quarterback or the primary running back.
    """

    dsts = [player for player in players if player.position == "DST"]
    if not dsts:
        return False
    dst = dsts[0]
    qb = _qb(players)
    if qb is not None and dst.team == qb.opp:
        return True
    runner = primary_rb(players)
    return runner is not None and dst.team == runner.opp


def stack_tags(players: Sequence[PoolPlayer]) -> str:
    qb = _qb(players)
    if qb is None:
        return ""
    parts = [f"QB+{catcher_count(players)} {qb.team}"]
    backs = [
        player
        for player in players
        if player.team == qb.opp and player.position in BRINGBACK_POSITIONS
    ]
    if backs:
        positions = "+".join(dict.fromkeys(player.position for player in backs))
        parts.append(f"bring-back {qb.opp} {positions}")
    if has_rb_own_dst(players):
        parts.append("RB+DST")
    if has_second_game(players):
        parts.append("second-game")
    return " | ".join(parts)


def _cap_tail(position: str, p90: float, p99: float) -> tuple[float, float]:
    cap = DST_CAP if position == "DST" else SKILL_CAP
    p90 = min(cap, max(0.0, p90))
    p99 = min(cap, max(p90, p99))
    return p90, p99


def _finite(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("nan")
    if not math.isfinite(number):
        return float("nan")
    return number


def _identity_fields(record: Mapping[str, object]) -> dict[str, str]:
    nickname = str(record.get("Nickname") or "").strip()
    first = str(record.get("First Name") or "").strip()
    last = str(record.get("Last Name") or "").strip()
    fd_position = str(record.get("Position") or "").strip().upper()
    return {
        "first": first,
        "last": last,
        "display": nickname or f"{first} {last}".strip(),
        "team": normalize_team_abbr(str(record.get("Team") or "")),
        "opp": normalize_team_abbr(str(record.get("Opponent") or "")),
        "fd_position": fd_position,
        "position": canon_position(fd_position),
        "game": canon_game(record.get("Game")),
    }


def _resolve_lagged(record: Mapping[str, object], floor: float | None) -> tuple[float, bool]:
    lagged = _finite(record.get("lagged_fd"))
    fppg = _finite(record.get("FPPG"))
    if (not math.isfinite(lagged) or lagged <= 0) and math.isfinite(fppg) and fppg > 0:
        lagged = fppg
    if floor is None:
        return lagged, False
    if math.isfinite(lagged) and lagged >= float(floor):
        return lagged, False
    return float(floor), True


def _resolve_tails(
    record: Mapping[str, object],
    lagged: float,
    position: str,
    table: list[dict],
    binds: bool,
    tails: Callable[[str, str, str, str, float, float], tuple[float, float]],
    fields: Mapping[str, str],
) -> tuple[float, float]:
    p90 = _finite(record.get("p90"))
    p99 = _finite(record.get("p99"))
    if binds or not (math.isfinite(p90) and math.isfinite(p99)):
        p90, p99 = apply_ceiling(lagged, position, table, 0.0)
    if math.isfinite(p90) and math.isfinite(p99):
        p90, p99 = tails(fields["game"], fields["team"], position, fields["display"], p90, p99)
        p90, p99 = _cap_tail(position, p90, p99)
    return p90, p99


def _resolve_playable(
    hard: bool,
    lagged: float,
    p90: float,
    p99: float,
) -> tuple[bool, float, float, float, float, float]:
    playable = all(
        (
            not hard,
            math.isfinite(lagged),
            lagged > 0,
            math.isfinite(p90),
            math.isfinite(p99),
        )
    )
    if playable:
        return True, blend_points(lagged, p90, p99), noise_sigma(p90, lagged), lagged, p90, p99
    zero = 0.0
    kept = lagged if math.isfinite(lagged) and not hard else zero
    return False, zero, zero, kept, zero, zero


def _salary_value(record: Mapping[str, object]) -> int:
    try:
        return int(float(record.get("Salary") or 0))
    except (TypeError, ValueError):
        return 0


def _value_or_zero(playable: bool, value: float) -> float:
    return float(value) if playable else 0.0


def _injury_indicator(hard: bool, indicator: str) -> str:
    return "Q" if (not hard and indicator == "Q") else ""


def _output_row(
    record: Mapping[str, object],
    fields: Mapping[str, str],
    *,
    hard: bool,
    indicator: str,
    playable: bool,
    lagged: float,
    p90: float,
    p99: float,
    fpts: float,
    sigma: float,
) -> dict[str, object]:
    return {
        "player_id": str(record.get("player_id") or ""),
        "first_name": fields["first"],
        "last_name": fields["last"],
        "nickname": fields["display"],
        "fd_position": fields["fd_position"],
        "position": fields["position"],
        "team": fields["team"],
        "opp": fields["opp"],
        "game": fields["game"],
        "salary": _salary_value(record),
        "injury_indicator": _injury_indicator(hard, indicator),
        "portfolio_lagged": _value_or_zero(playable, lagged),
        "portfolio_p90": _value_or_zero(playable, p90),
        "portfolio_p99": _value_or_zero(playable, p99),
        "portfolio_fpts": _value_or_zero(playable, fpts),
        "sigma": _value_or_zero(playable, sigma),
        "never_enter": int(hard),
    }


def score_pool_row(
    record: Mapping[str, object],
    skill: list[dict],
    dst_table: list[dict],
    *,
    blocked: Callable[[Mapping[str, object]], bool],
    tails: Callable[[str, str, str, str, float, float], tuple[float, float]],
    floor_lookup: Callable[[str], float | None] | None = None,
) -> dict[str, object]:
    """Score one salary row for a weekly 150-lineup book."""
    fields = _identity_fields(record)
    hard = blocked(record)
    floor = floor_lookup(fields["display"]) if floor_lookup else None
    lagged, binds = _resolve_lagged(record, floor)
    table = dst_table if fields["position"] == "DST" else skill
    p90, p99 = _resolve_tails(record, lagged, fields["position"], table, binds, tails, fields)
    playable, fpts, sigma, lagged, p90, p99 = _resolve_playable(hard, lagged, p90, p99)
    return _output_row(
        record,
        fields,
        hard=hard,
        indicator=status_token(record.get("Injury Indicator")),
        playable=playable,
        lagged=lagged,
        p90=p90,
        p99=p99,
        fpts=fpts,
        sigma=sigma,
    )


def build_portfolio_frame(
    salary: pd.DataFrame,
    ceiling: pd.DataFrame,
    quantiles: Mapping[str, Any],
) -> pd.DataFrame:
    """Join the salary file to the ceiling and apply the slate overlay."""

    sal = salary.copy()
    sal["player_id"] = sal["Id"].astype(str)
    ceil = ceiling.copy()
    ceil["player_id"] = ceil["player_id"].astype(str)
    keep = [column for column in ("player_id", "lagged_fd", "p90", "p99") if column in ceil.columns]
    merged = sal.merge(ceil[keep], on="player_id", how="left")
    skill = list(quantiles.get("skill") or [])
    dst_table = list(quantiles.get("dst") or [])
    rows: list[dict[str, Any]] = []
    for record in merged.to_dict(orient="records"):
        rows.append(_score_salary_row(record, skill, dst_table))
    return pd.DataFrame(rows)


def _score_salary_row(
    record: Mapping[str, Any],
    skill: list[dict],
    dst_table: list[dict],
) -> dict[str, Any]:
    nickname = str(record.get("Nickname") or "").strip()
    first = str(record.get("First Name") or "").strip()
    last = str(record.get("Last Name") or "").strip()
    team = normalize_team_abbr(str(record.get("Team") or ""))
    opp = normalize_team_abbr(str(record.get("Opponent") or ""))
    fd_position = str(record.get("Position") or "").strip().upper()
    position = canon_position(fd_position)
    game = canon_game(record.get("Game"))
    status = record.get("Injury Indicator")
    details = record.get("Injury Details")
    display = nickname or f"{first} {last}".strip()
    hard = is_hard_exclude(status, display, team, details)
    floor = STARTER_FLOORS.get(fold_name(display))
    lagged = _finite(record.get("lagged_fd"))
    table = dst_table if position == "DST" else skill
    if floor is not None:
        lagged = float(floor)
        p90, p99 = apply_ceiling(lagged, position, table, 0.0)
        if not math.isfinite(p90) or not math.isfinite(p99):
            p90 = min(SKILL_CAP, lagged * 1.45)
            p99 = min(SKILL_CAP, max(p90, lagged * 1.8))
    else:
        p90 = _finite(record.get("p90"))
        p99 = _finite(record.get("p99"))
        if not math.isfinite(p90) or not math.isfinite(p99):
            p90, p99 = apply_ceiling(lagged, position, table, 0.0)
    if math.isfinite(p90) and math.isfinite(p99):
        p90, p99 = adjust_tails(game, team, position, nickname, p90, p99)
        p90, p99 = _cap_tail(position, p90, p99)
    playable = (
        not hard
        and math.isfinite(lagged)
        and lagged > 0
        and math.isfinite(p90)
        and math.isfinite(p99)
    )
    if playable:
        fpts = blend_points(lagged, p90, p99)
        sigma = noise_sigma(p90, lagged)
    else:
        lagged = 0.0 if hard or not math.isfinite(lagged) else lagged
        p90 = 0.0
        p99 = 0.0
        fpts = 0.0
        sigma = 0.0
    try:
        salary = int(float(record.get("Salary") or 0))
    except (TypeError, ValueError):
        salary = 0
    return {
        "player_id": str(record.get("player_id") or ""),
        "first_name": first,
        "last_name": last,
        "nickname": display,
        "fd_position": fd_position,
        "position": position,
        "team": team,
        "opp": opp,
        "game": game,
        "salary": salary,
        "injury_indicator": "Q" if (not hard and status_token(status) == "Q") else "",
        "portfolio_lagged": float(lagged) if playable else 0.0,
        "portfolio_p90": float(p90) if playable else 0.0,
        "portfolio_p99": float(p99) if playable else 0.0,
        "portfolio_fpts": float(fpts) if playable else 0.0,
        "sigma": float(sigma) if playable else 0.0,
        "never_enter": 1 if hard else 0,
    }


def attach_portfolio_columns(ceiling: pd.DataFrame, portfolio: pd.DataFrame) -> pd.DataFrame:
    """Add the portfolio columns. Leave the scientific ceiling columns in place."""

    out = ceiling.copy()
    out["player_id"] = out["player_id"].astype(str)
    extra_cols = [
        "player_id",
        "portfolio_lagged",
        "portfolio_p90",
        "portfolio_p99",
        "portfolio_fpts",
        "never_enter",
    ]
    extra = portfolio[extra_cols].copy()
    extra["player_id"] = extra["player_id"].astype(str)
    drop = [column for column in extra_cols[1:] if column in out.columns]
    if drop:
        out = out.drop(columns=drop)
    return out.merge(extra, on="player_id", how="left")


def players_from_frame(frame: pd.DataFrame) -> list[PoolPlayer]:
    players: list[PoolPlayer] = []
    for record in frame.to_dict(orient="records"):
        players.append(
            PoolPlayer(
                player_id=str(record["player_id"]),
                nickname=str(record["nickname"]),
                team=str(record["team"]),
                opp=str(record["opp"]),
                game=str(record["game"]),
                position=str(record["position"]),
                salary=int(record["salary"]),
                fpts=float(record["portfolio_fpts"]),
                lagged=float(record["portfolio_lagged"]),
                p90=float(record["portfolio_p90"]),
                p99=float(record["portfolio_p99"]),
                sigma=float(record["sigma"]),
                never_enter=bool(int(record["never_enter"])),
                first_name=str(record.get("first_name") or ""),
                last_name=str(record.get("last_name") or ""),
                fd_position=str(record.get("fd_position") or record["position"]),
            )
        )
    return players


def eligible_players(
    players: Sequence[PoolPlayer],
    *,
    banned_teams: frozenset[str] | None = None,
    contest_prefix: str | None = None,
) -> list[PoolPlayer]:
    banned = BANNED_TEAMS if banned_teams is None else banned_teams
    prefix = CONTEST_PREFIX if contest_prefix is None else contest_prefix
    return [
        player
        for player in players
        if not player.never_enter
        and player.team not in banned
        and player.fpts > 0
        and player.salary > 0
        and (not prefix or player.player_id.startswith(prefix))
    ]


@dataclass(frozen=True)
class Candidate:
    ids: tuple[str, ...]
    key: frozenset[str]
    salary: int
    blend: float
    bringback: bool
    secondary: bool
    catchers: int
    dst_conflict: bool
    positions: tuple[tuple[str, str], ...]
    game: str
    tags: str
    seats: tuple[tuple[str, str], ...] = ()


def rb_pairs(item: Candidate) -> list[tuple[str, str]]:
    """Sorted running-back id pairs inside one lineup."""

    runners = sorted(pid for pid, pos in item.positions if pos == "RB")
    return [(left, right) for index, left in enumerate(runners) for right in runners[index + 1 :]]


def same_team_rb_te(
    item: Candidate,
    teams: Mapping[str, str],
) -> list[tuple[tuple[str, str], bool]]:
    """Return each same-team ``(RB, TE)`` pair and whether that team's QB is in the lineup."""

    grouped: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"QB": [], "RB": [], "TE": []})
    for pid, pos in item.positions:
        if pos not in {"QB", "RB", "TE"}:
            continue
        club = str(teams.get(pid) or "")
        if club:
            grouped[club][pos].append(pid)
    found: list[tuple[tuple[str, str], bool]] = []
    for slots in grouped.values():
        stacked = bool(slots["QB"])
        for runner in slots["RB"]:
            for tight in slots["TE"]:
                found.append((tuple(sorted((runner, tight))), stacked))
    return found


def select_book(
    candidates: Sequence[Candidate],
    *,
    count: int = BOOK_SIZE,
    bringback_min: int = BRINGBACK_MIN,
    secondary_min: int = SECONDARY_MIN,
    min_salary: int = MIN_SALARY,
    max_salary: int = MAX_SALARY,
    caps: Mapping[str, int] | None = None,
    max_shared: int = MAX_SHARED,
    allow_cheap: int = 0,
    pair_cap: int | None = None,
    player_caps: Mapping[str, int] | None = None,
    rb_te_cap: int | None = None,
    player_teams: Mapping[str, str] | None = None,
) -> list[Candidate]:
    """Greedy book. Bring-backs fill first. The position caps own exposure.

    ``pair_cap`` limits how often the same two running backs share a lineup.
    ``player_caps`` is a tighter per-player limit. It does not raise the
    position cap. ``rb_te_cap`` blocks an unstacked same-team running back
    and tight end, and caps a stacked pair.
    """

    limits = dict(EXPOSURE_CAPS if caps is None else caps)
    person_caps = dict(player_caps or {})
    team_of = dict(player_teams or {})
    ordered = sorted(candidates, key=lambda item: (-item.blend, -item.salary, item.ids))
    book: list[Candidate] = []
    counts: dict[str, int] = {}
    pair_counts: Counter[tuple[str, str]] = Counter()
    rb_te_counts: Counter[tuple[str, str]] = Counter()
    keys: list[frozenset[str]] = []
    cheap = 0

    def player_limit(pid: str, pos: str) -> int:
        position_cap = limits.get(pos, 10**9)
        if pid in person_caps:
            return min(position_cap, person_caps[pid])
        return position_cap

    def legal(item: Candidate) -> bool:
        if item.dst_conflict or item.catchers < 1:
            return False
        if len(item.ids) != 9 or len(set(item.ids)) != 9:
            return False
        if item.salary > max_salary:
            return False
        if item.salary < min_salary and cheap >= allow_cheap:
            return False
        for pid, pos in item.positions:
            if counts.get(pid, 0) + 1 > player_limit(pid, pos):
                return False
        if pair_cap is not None:
            for pair in rb_pairs(item):
                if pair_counts[pair] + 1 > pair_cap:
                    return False
        if rb_te_cap is not None and team_of:
            for pair, stacked in same_team_rb_te(item, team_of):
                if not stacked or rb_te_counts[pair] + 1 > rb_te_cap:
                    return False
        for prev in keys:
            if not shares_ok(item.key, prev, max_shared):
                return False
        return True

    def add(item: Candidate) -> None:
        nonlocal cheap
        book.append(item)
        keys.append(item.key)
        if item.salary < min_salary:
            cheap += 1
        for pid, _pos in item.positions:
            counts[pid] = counts.get(pid, 0) + 1
        if pair_cap is not None:
            pair_counts.update(rb_pairs(item))
        if rb_te_cap is not None and team_of:
            for pair, stacked in same_team_rb_te(item, team_of):
                if stacked:
                    rb_te_counts[pair] += 1

    def take(pred, stop) -> None:
        for item in ordered:
            if stop():
                return
            if item.key in keys:
                continue
            if pred(item) and legal(item):
                add(item)

    take(
        lambda item: item.bringback,
        lambda: sum(item.bringback for item in book) >= bringback_min or len(book) >= count,
    )
    take(
        lambda item: item.secondary and item.bringback,
        lambda: sum(item.secondary for item in book) >= secondary_min or len(book) >= count,
    )
    take(
        lambda item: item.secondary,
        lambda: sum(item.secondary for item in book) >= secondary_min or len(book) >= count,
    )
    take(lambda _item: True, lambda: len(book) >= count)
    return book[:count]


def _seat_rows(lineup: Any) -> list[tuple[str, str]]:
    by_pos: dict[str, list[Any]] = {}
    for player in getattr(lineup, "players", []) or []:
        slot = str(getattr(player, "lineup_position", "") or "")
        if slot in {"D", "DST"}:
            slot = "DEF"
        by_pos.setdefault(slot, []).append(player)
    seats: list[tuple[str, str]] = []
    for column in LINEUP_HEADERS["fanduel"]:
        bucket = by_pos.get(column) or []
        if not bucket:
            seats.append((column, ""))
            continue
        player = bucket.pop(0)
        seats.append((column, str(getattr(player, "id", "") or "")))
    return seats


def candidate_from_players(
    players: Sequence[PoolPlayer],
    seats: Sequence[tuple[str, str]] | None = None,
    *,
    banned_teams: frozenset[str] | None = None,
) -> Candidate | None:
    banned = BANNED_TEAMS if banned_teams is None else banned_teams
    if len(players) != 9:
        return None
    ids = tuple(player.player_id for player in players)
    if len(set(ids)) != 9:
        return None
    if any(player.never_enter or player.team in banned for player in players):
        return None
    qb = _qb(players)
    game = qb.game if qb is not None else ""
    seat_rows = tuple(seats) if seats is not None else tuple(
        (player.position if player.position != "DST" else "DEF", player.player_id)
        for player in players
    )
    return Candidate(
        ids=ids,
        key=frozenset(ids),
        salary=sum(player.salary for player in players),
        blend=sum(player.fpts for player in players),
        bringback=has_bringback(players),
        secondary=has_secondary(players),
        catchers=catcher_count(players),
        dst_conflict=dst_faces_qb_or_primary_rb(players),
        positions=tuple((player.player_id, player.position) for player in players),
        game=game,
        tags=stack_tags(players),
        seats=seat_rows,
    )


def candidate_from_lineup(
    lineup: Any,
    meta: Mapping[str, PoolPlayer],
    *,
    banned_teams: frozenset[str] | None = None,
) -> Candidate | None:
    seats = _seat_rows(lineup)
    ids = [pid for _slot, pid in seats]
    if len(ids) != 9 or any(not pid for pid in ids):
        return None
    players: list[PoolPlayer] = []
    for pid in ids:
        player = meta.get(pid)
        if player is None:
            return None
        players.append(player)
    return candidate_from_players(players, seats, banned_teams=banned_teams)


def write_optimizer_csv(path: Path, players: Sequence[PoolPlayer]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "Id",
        "Position",
        "First Name",
        "Nickname",
        "Last Name",
        "FPPG",
        "Played",
        "Salary",
        "Game",
        "Team",
        "Opponent",
        "Injury Indicator",
        "Injury Details",
        "Roster Position",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for player in players:
            position = "D" if player.position == "DST" else player.fd_position or player.position
            writer.writerow(
                {
                    "Id": player.player_id,
                    "Position": position,
                    "First Name": player.first_name or player.nickname.split(" ")[0],
                    "Nickname": player.nickname,
                    "Last Name": player.last_name or player.nickname.split(" ")[-1],
                    "FPPG": f"{player.fpts:.4f}",
                    "Played": 0,
                    "Salary": player.salary,
                    "Game": player.game,
                    "Team": player.team,
                    "Opponent": player.opp,
                    "Injury Indicator": "",
                    "Injury Details": "",
                    "Roster Position": position,
                }
            )


def _noise_map(
    players: Sequence[PoolPlayer],
    rng: Any,
    *,
    scale: float = 1.0,
    qb_boost_id: str = "",
    qb_boost: float = 0.0,
) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for player in players:
        shock = float(rng.normal(0.0, player.sigma * scale)) if player.sigma > 0 else 0.0
        value = player.fpts + shock
        if player.player_id == qb_boost_id:
            value += qb_boost
        overrides[player.player_id] = max(0.05, value)
    return overrides


def _install_portfolio_rules(optimizer: Any, meta: Mapping[str, PoolPlayer], *, bringback: bool) -> None:
    from pydfs_lineup_optimizer.rules import OptimizerRule
    from pydfs_lineup_optimizer.solvers import SolverSign

    class PortfolioRule(OptimizerRule):
        def apply(self, solver):
            variables = self.players_dict
            qbs = []
            rbs = []
            dst_by_team: dict[str, Any] = {}
            skill_by_team: dict[str, list[Any]] = defaultdict(list)
            for player in variables:
                info = meta.get(str(player.id))
                if info is None:
                    continue
                if info.position == "QB":
                    qbs.append(player)
                elif info.position == "RB":
                    rbs.append(player)
                elif info.position == "DST":
                    dst_by_team[info.team] = player
                if info.position in BRINGBACK_POSITIONS:
                    skill_by_team[info.team].append(player)
            for qb in qbs:
                info = meta[str(qb.id)]
                dst = dst_by_team.get(info.opp)
                if dst is not None and dst in variables and qb in variables:
                    solver.add_constraint(
                        [variables[qb], variables[dst]],
                        None,
                        SolverSign.LTE,
                        1,
                    )
                if bringback:
                    mates = [mate for mate in skill_by_team.get(info.opp, []) if mate in variables]
                    if mates and qb in variables:
                        solver.add_constraint(
                            [variables[mate] for mate in mates] + [variables[qb]],
                            [1.0] * len(mates) + [-1.0],
                            SolverSign.GTE,
                            0,
                        )
            for rb in rbs:
                info = meta[str(rb.id)]
                dst = dst_by_team.get(info.opp)
                if dst is None or rb not in variables or dst not in variables:
                    continue
                higher = [
                    other
                    for other in rbs
                    if other in variables and float(other.salary) > float(rb.salary)
                ]
                solver.add_constraint(
                    [variables[dst], variables[rb]] + [variables[other] for other in higher],
                    [1.0, 1.0] + [-1.0] * len(higher),
                    SolverSign.LTE,
                    1,
                )

    # The book filter owns exposure. This rule blocks a DST against the
    # quarterback or the primary running back, and it requires a bring-back.
    optimizer.add_new_rule(PortfolioRule)


def _apply_wave_exposure(
    optimizer: Any,
    remaining: Mapping[str, int],
    wave_n: int,
    meta: Mapping[str, PoolPlayer],
    *,
    qb_wave_cap: int | None = None,
) -> None:
    if wave_n <= 0:
        return
    for player in getattr(optimizer.player_pool, "all_players", []) or []:
        pid = str(player.id)
        left = remaining.get(pid)
        if left is None:
            continue
        if left <= 0:
            player.max_exposure = 0
            continue
        fraction = left / wave_n
        info = meta.get(pid)
        if info is not None and info.position == "QB" and qb_wave_cap is not None:
            fraction = min(fraction, qb_wave_cap / wave_n)
        player.max_exposure = fraction


def solve_wave(
    csv_path: Path,
    meta: Mapping[str, PoolPlayer],
    overrides: Mapping[str, float],
    *,
    count: int,
    stacks: list[str],
    bringback: bool,
    repeating: int,
    min_salary: int,
    remaining: Mapping[str, int],
    qb_wave_cap: int | None = None,
) -> list[Any]:
    """Solve one noisy wave. Return a short list when the model stops early."""

    Site, Sport, get_optimizer, _team_stack = _load_pydfs()
    optimizer = get_optimizer(Site.FANDUEL, Sport.FOOTBALL)
    optimizer.load_players_from_csv(str(csv_path))
    _apply_fppg_overrides(optimizer, overrides)
    attach_csv_original_positions(optimizer, csv_path)
    keep_injury_tagged_players(optimizer, csv_path)
    _apply_wave_exposure(optimizer, remaining, count, meta, qb_wave_cap=qb_wave_cap)
    apply_stack_specs(optimizer, parse_stack_rules(stacks))
    _install_portfolio_rules(optimizer, meta, bringback=bringback)
    optimizer.set_max_repeating_players(repeating)
    if min_salary:
        optimizer.set_min_salary_cap(min_salary)
    try:
        return _optimize_or_raise(
            optimizer,
            n=count,
            max_exposure=None,
            allow_short=True,
        )
    except ValueError as exc:
        print(f"wave skipped: {exc}")
        return []


def _remaining_caps(book: Sequence[Candidate], caps: Mapping[str, int]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    positions: dict[str, str] = {}
    for item in book:
        for pid, pos in item.positions:
            counts[pid] += 1
            positions[pid] = pos
    remaining: dict[str, int] = {}
    for pid, pos in positions.items():
        remaining[pid] = caps.get(pos, 0) - counts[pid]
    return remaining


def _stamp_player_caps(
    remaining: dict[str, int],
    book: Sequence[Candidate],
    player_caps: Mapping[str, int] | None,
) -> dict[str, int]:
    """Lower remaining exposure when a player has a tighter personal cap."""

    if not player_caps:
        return remaining
    used: Counter[str] = Counter()
    for item in book:
        for pid, _pos in item.positions:
            used[pid] += 1
    for pid, cap in player_caps.items():
        if pid in remaining:
            remaining[pid] = min(remaining[pid], int(cap) - used[pid])
    return remaining


def build_candidate_pool(
    csv_path: Path,
    players: Sequence[PoolPlayer],
    *,
    seed: int = SEED,
    wave_size: int = 30,
    max_waves: int = 12,
    caps: Mapping[str, int] | None = None,
    banned_teams: frozenset[str] | None = None,
    pair_cap: int | None = None,
    player_caps: Mapping[str, int] | None = None,
    rb_te_cap: int | None = None,
) -> list[Candidate]:
    """Build a diverse candidate pool. Each wave uses one noise draw."""

    import numpy as np

    limits = dict(EXPOSURE_CAPS if caps is None else caps)
    meta = {player.player_id: player for player in players}
    team_of = {player.player_id: player.team for player in players}
    rng = np.random.default_rng(seed)
    qbs = [player for player in players if player.position == "QB"]
    found: dict[frozenset[str], Candidate] = {}
    book: list[Candidate] = []

    def remaining_for(current: Sequence[Candidate]) -> dict[str, int]:
        remaining = _remaining_caps(current, limits)
        for player in players:
            remaining.setdefault(player.player_id, limits.get(player.position, BOOK_SIZE))
        return _stamp_player_caps(remaining, current, player_caps)

    def absorb(lineups: Sequence[Any]) -> int:
        added = 0
        for lineup in lineups:
            item = candidate_from_lineup(lineup, meta, banned_teams=banned_teams)
            if item is None or item.key in found:
                continue
            found[item.key] = item
            added += 1
        return added

    for index in range(max_waves):
        if _book_ready(book):
            break
        boost = qbs[index % len(qbs)].player_id if qbs else ""
        overrides = _noise_map(
            players,
            rng,
            scale=1.0 if index < 4 else 1.6,
            qb_boost_id=boost,
            qb_boost=3.0,
        )
        stacks = ["qb:3", "rb+dst"] if index % 2 else ["qb:3"]
        remaining = remaining_for(book)
        print(f"wave {index + 1}: stacks={stacks} boost={boost}")
        lineups = solve_wave(
            csv_path,
            meta,
            overrides,
            count=wave_size,
            stacks=stacks,
            bringback=True,
            repeating=6,
            min_salary=MIN_SALARY,
            remaining=remaining,
            qb_wave_cap=max(4, wave_size // 4),
        )
        if len(lineups) < 8:
            print(f"wave {index + 1} short ({len(lineups)}); retry qb:2")
            lineups = solve_wave(
                csv_path,
                meta,
                overrides,
                count=wave_size,
                stacks=["qb:2"] if "rb+dst" not in stacks else ["qb:2", "rb+dst"],
                bringback=True,
                repeating=7,
                min_salary=MIN_SALARY,
                remaining=remaining,
                qb_wave_cap=max(4, wave_size // 3),
            )
        added = absorb(lineups)
        book = select_book(
            list(found.values()),
            caps=limits,
            pair_cap=pair_cap,
            player_caps=player_caps,
            rb_te_cap=rb_te_cap,
            player_teams=team_of,
        )
        print(
            f"wave {index + 1} added {added}; pool {len(found)}; "
            f"book {len(book)}; bring-back {sum(item.bringback for item in book)}; "
            f"secondary {sum(item.secondary for item in book)}"
        )
    if not _book_ready(book):
        print("salary floor retry")
        for index in range(2):
            overrides = _noise_map(players, rng, scale=1.8)
            lineups = solve_wave(
                csv_path,
                meta,
                overrides,
                count=wave_size,
                stacks=["qb:2"],
                bringback=False,
                repeating=7,
                min_salary=0,
                remaining=remaining_for(book),
            )
            absorb(lineups)
            print(f"floor retry {index + 1}: pool {len(found)}")
    return list(found.values())


def _book_ready(book: Sequence[Candidate]) -> bool:
    if len(book) < BOOK_SIZE:
        return False
    bring = sum(item.bringback for item in book)
    secondary = sum(item.secondary for item in book)
    return bring >= BRINGBACK_MIN and secondary >= SECONDARY_MIN


def choose_book(candidates: Sequence[Candidate]) -> list[Candidate]:
    book = select_book(candidates, allow_cheap=0)
    if _book_ready(book):
        return book
    relaxed = select_book(candidates, allow_cheap=CHEAP_LIMIT)
    if len(relaxed) > len(book):
        return relaxed
    return book


def write_book_files(
    book: Sequence[Candidate],
    upload_path: Path,
    ids_path: Path,
) -> None:
    header = LINEUP_HEADERS["fanduel"]
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    ids_path.parent.mkdir(parents=True, exist_ok=True)
    with upload_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for item in book:
            writer.writerow([upload_cell(pid, _nickname_for(item, pid)) for _slot, pid in item.seats])
    with ids_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for item in book:
            writer.writerow([pid for _slot, pid in item.seats])


_NICKNAMES: dict[str, str] = {}


def _nickname_for(item: Candidate, player_id: str) -> str:
    return _NICKNAMES.get(player_id, player_id)


def set_nicknames(players: Sequence[PoolPlayer]) -> None:
    _NICKNAMES.clear()
    for player in players:
        _NICKNAMES[player.player_id] = player.nickname


def verify_book(
    book: Sequence[Candidate],
    players: Sequence[PoolPlayer],
    *,
    caps: Mapping[str, int] | None = None,
    banned_teams: frozenset[str] | None = None,
    contest_prefix: str | None = None,
    pair_cap: int | None = None,
    player_caps: Mapping[str, int] | None = None,
    rb_te_cap: int | None = None,
    count: int | None = None,
) -> dict[str, Any]:
    """Raise AssertionError when the book breaks a portfolio rule."""

    limits = dict(EXPOSURE_CAPS if caps is None else caps)
    banned_clubs = BANNED_TEAMS if banned_teams is None else banned_teams
    prefix = CONTEST_PREFIX if contest_prefix is None else contest_prefix
    person_caps = dict(player_caps or {})
    target = BOOK_SIZE if count is None else count
    meta = {player.player_id: player for player in players}
    banned = {player.player_id for player in players if player.never_enter}
    assert len(book) == target, f"lineups {len(book)}"
    keys = [item.key for item in book]
    assert len(set(keys)) == target, "duplicate lineups"
    max_share = 0
    for index, left in enumerate(keys):
        for right in keys[index + 1 :]:
            max_share = max(max_share, len(left & right))
    assert max_share <= MAX_SHARED, f"max share {max_share}"
    counts: Counter[str] = Counter()
    games: Counter[str] = Counter()
    pair_counts: Counter[tuple[str, str]] = Counter()
    bring = 0
    secondary = 0
    under_floor = 0
    for item in book:
        assert len(item.ids) == 9
        assert item.salary <= MAX_SALARY
        assert item.catchers >= 1
        assert not item.dst_conflict
        if item.salary < MIN_SALARY:
            under_floor += 1
        bring += int(item.bringback)
        secondary += int(item.secondary)
        games[item.game] += 1
        pair_counts.update(rb_pairs(item))
        for pid in item.ids:
            if prefix:
                assert pid.startswith(prefix), pid
            assert pid not in banned, pid
            player = meta[pid]
            assert player.team not in banned_clubs
            counts[pid] += 1
    assert under_floor <= CHEAP_LIMIT
    assert bring >= BRINGBACK_MIN, f"bring-back {bring}"
    assert secondary >= SECONDARY_MIN, f"secondary {secondary}"
    for pid, used in counts.items():
        cap = limits[meta[pid].position]
        if pid in person_caps:
            cap = min(cap, person_caps[pid])
        assert used <= cap, f"{meta[pid].nickname} {used} > {cap}"
    if pair_cap is not None:
        for pair, used in pair_counts.items():
            assert used <= pair_cap, f"rb pair {pair} {used} > {pair_cap}"
    teams = {pid: player.team for pid, player in meta.items()}
    rb_te_counts: Counter[tuple[str, str]] = Counter()
    unstacked_rb_te = 0
    for item in book:
        for pair, stacked in same_team_rb_te(item, teams):
            if stacked:
                rb_te_counts[pair] += 1
            else:
                unstacked_rb_te += 1
    if rb_te_cap is not None:
        assert unstacked_rb_te == 0, f"unstacked rb+te {unstacked_rb_te}"
        for pair, used in rb_te_counts.items():
            assert used <= rb_te_cap, f"rb+te {pair} {used} > {rb_te_cap}"
    paid = sum(1 for item in book if item.salary >= MIN_SALARY)
    assert paid >= math.ceil(0.90 * target)
    return {
        "lineups": len(book),
        "bringback": bring,
        "secondary": secondary,
        "max_share": max_share,
        "under_floor": under_floor,
        "salary_min": min(item.salary for item in book),
        "salary_max": max(item.salary for item in book),
        "games": games,
        "counts": counts,
        "rb_pairs": pair_counts,
        "rb_te_pairs": rb_te_counts,
        "unstacked_rb_te": unstacked_rb_te,
    }


def exposure_table(
    book: Sequence[Candidate],
    meta: Mapping[str, PoolPlayer],
    *,
    limit: int = 20,
) -> list[tuple[str, str, str, int, float]]:
    counts: Counter[str] = Counter()
    for item in book:
        counts.update(item.ids)
    rows = []
    for pid, used in counts.most_common(limit):
        player = meta[pid]
        rows.append(
            (
                player.nickname,
                player.position,
                player.team,
                used,
                100.0 * used / max(len(book), 1),
            )
        )
    return rows


def load_quantiles(path: Path = CALIBRATION_PATH) -> dict[str, Any]:
    raw = json.loads(path.read_text())
    calibration = raw["calibration"] if "calibration" in raw else raw
    quantiles = calibration.get("quantiles") or {}
    return {"skill": list(quantiles.get("skill") or []), "dst": list(quantiles.get("dst") or [])}


def run_portfolio(
    *,
    salary_path: Path = SALARY_PATH,
    ceiling_path: Path = CEILING_PATH,
    upload_path: Path = UPLOAD_PATH,
    ids_path: Path = IDS_PATH,
    optimizer_path: Path = OPTIMIZER_PATH,
) -> list[Candidate]:
    """Overlay the ceiling, solve the book, and write the two FanDuel files."""

    salary = pd.read_csv(salary_path)
    ceiling = pd.read_csv(ceiling_path)
    portfolio = build_portfolio_frame(salary, ceiling, load_quantiles())
    updated = attach_portfolio_columns(ceiling, portfolio)
    updated.to_csv(ceiling_path, index=False)
    all_players = players_from_frame(portfolio)
    set_nicknames(all_players)
    pool = eligible_players(all_players)
    print(f"eligible pool {len(pool)} of {len(all_players)}")
    write_optimizer_csv(optimizer_path, pool)
    candidates = build_candidate_pool(optimizer_path, pool)
    book = choose_book(candidates)
    if not _book_ready(book):
        relaxed = select_book(candidates, allow_cheap=CHEAP_LIMIT)
        if len(relaxed) > len(book):
            book = relaxed
    audit = verify_book(book, all_players)
    write_book_files(book, upload_path, ids_path)
    _print_report(book, {player.player_id: player for player in all_players}, audit)
    print(f"upload -> {upload_path}")
    print(f"ids -> {ids_path}")
    return book


def _print_report(
    book: Sequence[Candidate],
    meta: Mapping[str, PoolPlayer],
    audit: Mapping[str, Any],
) -> None:
    print(
        f"book {audit['lineups']} unique; bring-back {audit['bringback']}; "
        f"secondary {audit['secondary']}; max share {audit['max_share']}; "
        f"salary {audit['salary_min']}-{audit['salary_max']}; "
        f"under {MIN_SALARY}: {audit['under_floor']}"
    )
    print("top 20 exposure")
    print("player | pos | team | lineups | pct")
    for name, pos, team, used, pct in exposure_table(book, meta):
        print(f"{name} | {pos} | {team} | {used} | {pct:.1f}")
    print("game stacks")
    games: Counter[str] = audit["games"]
    for game, used in games.most_common(10):
        print(f"{game} {used}")
    ranked = sorted(book, key=lambda item: item.blend, reverse=True)[:5]
    print("top 5 ceilings")
    for index, item in enumerate(ranked, start=1):
        names = []
        for _slot, pid in item.seats:
            player = meta[pid]
            names.append(f"{player.nickname} ${player.salary}")
        print(f"{index}. ${item.salary} blend {item.blend:.2f} | {item.tags}")
        print("   " + "; ".join(names))


def main() -> None:
    run_portfolio()


if __name__ == "__main__":
    main()
