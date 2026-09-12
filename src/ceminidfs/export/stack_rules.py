"""Parse GPP stack rules and apply them to a pydfs optimizer.

Supported rule text (case-insensitive):

- ``qb:3`` — QB plus two WR/TE teammates (PositionsStack)
- ``CIN:3`` — three players from CIN
- ``CIN3-TB2`` or ``CIN:3-TB:2`` — game stack (3 from CIN, 2 from TB)
- ``3-2`` — any game, 5 players, at least 2 from each side
- ``game:5`` — any game, 5 players, at least 1 from each side
- ``wr:2`` / ``te:2`` — two same-team players at that position
- ``rb+dst`` — RB and DST/DEF from the same team
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from pydfs_lineup_optimizer.stacks import GameStack, PlayersGroup, PositionsStack, TeamStack

from ceminidfs.data.stadiums import TEAM_ALIASES, normalize_team_abbr
from ceminidfs.export.lineup_report import opponent_team, player_team

POSITION_TOKENS = frozenset({"QB", "RB", "WR", "TE", "FLEX", "K", "D", "DEF", "DST"})
OFFENSE_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})
DST_POSITIONS = frozenset({"D", "DEF", "DST"})
NFL_SKILL_POSITIONS = OFFENSE_POSITIONS | DST_POSITIONS | frozenset({"K"})

_TEAM_COUNT = re.compile(r"^([A-Za-z]{2,4}):?(\d+)$")
_GAME_PAIR = re.compile(r"^([A-Za-z]{2,4}):?(\d+)-([A-Za-z]{2,4}):?(\d+)$")
_NUMERIC_SPLIT = re.compile(r"^(\d+)-(\d+)$")
_POS_COUNT = re.compile(r"^([A-Za-z]{1,4}):(\d+)$")


@dataclass(frozen=True)
class StackSpec:
    kind: str
    size: int | None = None
    team: str | None = None
    teams: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    positions: tuple[str, ...] = field(default_factory=tuple)
    min_from_team: int | None = None
    raw: str = ""


def parse_stack_rule(rule: str) -> StackSpec:
    """Parse one stack rule. Raise ValueError on bad text."""

    raw = str(rule or "").strip()
    if not raw:
        raise ValueError("empty stack rule")
    token = raw.lower().replace(" ", "")

    if token in {"rb+dst", "rbdst", "rb-dst", "rb+def"}:
        return StackSpec(kind="rb_dst", raw=raw)

    if token.startswith("game:"):
        size = int(token.split(":", 1)[1])
        if size < 2:
            raise ValueError(f"Invalid stack rule {rule!r}; game size must be >= 2")
        return StackSpec(kind="game", size=size, min_from_team=1, raw=raw)

    qb_match = re.fullmatch(r"qb:(\d+)", token)
    if qb_match:
        size = int(qb_match.group(1))
        if size < 2:
            raise ValueError(f"Invalid stack rule {rule!r}; qb stack must be >= 2")
        return StackSpec(kind="qb_stack", size=size, raw=raw)

    numeric = _NUMERIC_SPLIT.fullmatch(token)
    if numeric:
        left, right = int(numeric.group(1)), int(numeric.group(2))
        if left < 1 or right < 1:
            raise ValueError(f"Invalid stack rule {rule!r}; both sides must be >= 1")
        return StackSpec(
            kind="game",
            size=left + right,
            min_from_team=min(left, right),
            raw=raw,
        )

    pair = _GAME_PAIR.fullmatch(raw.replace(" ", ""))
    if pair and pair.group(1).upper() not in POSITION_TOKENS:
        home = normalize_team_abbr(pair.group(1))
        away = normalize_team_abbr(pair.group(3))
        return StackSpec(
            kind="game_pair",
            teams=((home, int(pair.group(2))), (away, int(pair.group(4)))),
            raw=raw,
        )

    pos = _POS_COUNT.fullmatch(token)
    if pos and pos.group(1).upper() in POSITION_TOKENS:
        position = _canonical_position(pos.group(1))
        return StackSpec(
            kind="position",
            size=int(pos.group(2)),
            positions=(position,),
            raw=raw,
        )

    team_count = _TEAM_COUNT.fullmatch(raw.replace(" ", ""))
    if team_count and team_count.group(1).upper() not in POSITION_TOKENS:
        return StackSpec(
            kind="team",
            size=int(team_count.group(2)),
            team=normalize_team_abbr(team_count.group(1)),
            raw=raw,
        )

    raise ValueError(
        f"Invalid stack rule {rule!r}; expected qb:3, CIN:3, CIN3-TB2, 3-2, game:5, wr:2, or rb+dst"
    )


def parse_stack_rules(rules: list[str] | None) -> list[StackSpec]:
    """Parse stack rules. A token that contains ``|`` splits into multiple rules."""

    specs: list[StackSpec] = []
    for rule in rules or []:
        raw = str(rule or "").strip()
        if "|" in raw:
            parts = [part.strip() for part in raw.split("|") if part.strip()]
            if not parts:
                raise ValueError("empty stack rule")
            specs.extend(parse_stack_rule(part) for part in parts)
        else:
            specs.append(parse_stack_rule(rule))
    return specs


def apply_stack_specs(optimizer: Any, specs: list[StackSpec]) -> None:
    """Attach parsed stack specs to a loaded pydfs optimizer."""

    available_teams = {str(team).upper(): str(team) for team in optimizer.player_pool.available_teams}
    available_positions = {str(pos).upper() for pos in optimizer.player_pool.available_positions}
    dst_pos = _dst_position(available_positions)

    for spec in specs:
        if spec.kind == "qb_stack":
            catch = ("WR", "TE")
            size = spec.size or 2
            positions: list[Any] = ["QB"] + [catch] * (size - 1)
            optimizer.add_stack(PositionsStack(positions))
        elif spec.kind == "team":
            team = _match_team(spec.team or "", available_teams)
            optimizer.add_stack(TeamStack(spec.size or 2, for_teams=[team]))
        elif spec.kind == "game_pair":
            for team, count in spec.teams:
                matched = _match_team(team, available_teams)
                optimizer.add_stack(TeamStack(count, for_teams=[matched]))
        elif spec.kind == "game":
            optimizer.add_stack(GameStack(spec.size or 2, min_from_team=spec.min_from_team or 1))
        elif spec.kind == "position":
            position = _canonical_position(spec.positions[0] if spec.positions else "")
            if position in {"D", "DEF", "DST"}:
                position = dst_pos
            optimizer.add_stack(TeamStack(spec.size or 2, for_positions=[position]))
        elif spec.kind == "rb_dst":
            optimizer.add_stack(PositionsStack(["RB", dst_pos]))
        else:
            raise ValueError(f"Unknown stack kind {spec.kind!r}")


def resolve_pool_player(optimizer: Any, query: str) -> Any:
    """Find one player by id or name. Raise ValueError if missing."""

    text = str(query or "").strip()
    if not text:
        raise ValueError("empty player query")
    pool = optimizer.player_pool
    by_id = pool.get_player_by_id(text)
    if by_id is not None:
        return by_id
    try:
        by_name = pool.get_player_by_name(text)
    except Exception:
        by_name = None
    if by_name is not None:
        return by_name
    needle = _fold_name(text)
    matches = [player for player in pool.all_players if needle in _fold_name(player.full_name)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        flex = [player for player in matches if "FLEX" in {str(pos).upper() for pos in player.positions}]
        if len(flex) == 1:
            return flex[0]
        unique_names = sorted({player.full_name for player in matches})
        if len(unique_names) == 1:
            return matches[0]
        names = ", ".join(unique_names[:8])
        raise ValueError(f"Ambiguous player {query!r}; matches: {names}")
    raise ValueError(f"Player not found in pool: {query!r}")


def apply_locks_and_excludes(
    optimizer: Any,
    *,
    locks: list[str] | None = None,
    excludes: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Lock and remove players by name or id. Return resolved names."""

    locked_names: list[str] = []
    excluded_names: list[str] = []
    pool = optimizer.player_pool
    for query in locks or []:
        player = resolve_pool_player(optimizer, query)
        pool.lock_player(player)
        locked_names.append(player.full_name)
    for query in excludes or []:
        player = resolve_pool_player(optimizer, query)
        pool.remove_player(player)
        excluded_names.append(player.full_name)
    return locked_names, excluded_names


def _canonical_position(token: str) -> str:
    upper = token.strip().upper()
    if upper in {"DEF", "DST", "D"}:
        return "D"
    return upper


def _dst_position(available_positions: set[str]) -> str:
    for candidate in ("DST", "D", "DEF"):
        if candidate in available_positions:
            return candidate
    return "D"


def _match_team(requested: str, available: dict[str, str]) -> str:
    normalized = normalize_team_abbr(requested)
    if normalized in available:
        return available[normalized]
    if requested.upper() in available:
        return available[requested.upper()]
    for alias, canon in TEAM_ALIASES.items():
        if canon == normalized and alias in available:
            return available[alias]
    raise ValueError(
        f"Team {requested!r} is not in this player pool. Available: {', '.join(sorted(available))}"
    )


def _fold_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def max_repeating_from_uniques(slate_size: int, uniques: int) -> int:
    """Map ``uniques`` to pydfs ``max_repeating_players`` (slate_size - N)."""

    if uniques < 0:
        raise ValueError(f"uniques must be >= 0, got {uniques}")
    return int(slate_size) - int(uniques)


def resolve_repeating_players(
    *,
    slate_size: int,
    max_repeating_players: int | None,
    uniques: int | None,
) -> int | None:
    """Prefer ``uniques`` when both aliases are set."""

    if uniques is not None:
        return max_repeating_from_uniques(slate_size, uniques)
    return max_repeating_players


def nfl_positions(player: Any) -> set[str]:
    """NFL positions for a pool player (original when roster slots hid them)."""

    orig = {str(item).upper() for item in (getattr(player, "original_positions", None) or ())}
    pos = {str(item).upper() for item in (getattr(player, "positions", None) or ())}
    for group in (orig, pos):
        hit = group & NFL_SKILL_POSITIONS
        if hit:
            return hit
    return orig or pos


def is_dst_player(player: Any) -> bool:
    return bool(nfl_positions(player) & DST_POSITIONS)


def is_offense_player(player: Any) -> bool:
    return bool(nfl_positions(player) & OFFENSE_POSITIONS)


def offense_vs_dst_pairs(players: Iterable[Any]) -> list[tuple[Any, Any]]:
    """Pairwise DST vs opposing skill-player mutexes. Skip empty opponents."""

    pool = list(players)
    pairs: list[tuple[Any, Any]] = []
    for dst in pool:
        if not is_dst_player(dst):
            continue
        opp = opponent_team(dst)
        if not opp:
            continue
        for other in pool:
            if other is dst:
                continue
            if player_team(other) != opp:
                continue
            if not is_offense_player(other):
                continue
            pairs.append((dst, other))
    return pairs


def rbs_by_team(players: Iterable[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for player in players:
        if "RB" not in nfl_positions(player):
            continue
        team = player_team(player)
        if team:
            grouped[team].append(player)
    return dict(grouped)


def players_below_floor(
    players: Iterable[Any],
    floor: float,
    locked: Iterable[Any] | None = None,
) -> list[Any]:
    locked_items = list(locked or [])
    dropped: list[Any] = []
    for player in players:
        if player in locked_items:
            continue
        try:
            fppg = float(getattr(player, "fppg"))
        except (TypeError, ValueError, AttributeError):
            continue
        if fppg < floor:
            dropped.append(player)
    return dropped


def attach_csv_original_positions(optimizer: Any, csv_path: str | Path) -> None:
    """Restore NFL positions from CSV when pydfs hid them behind CPT/FLEX."""

    by_id = _csv_id_nfl_positions(csv_path)
    if not by_id:
        return
    pool = getattr(optimizer, "player_pool", None)
    if pool is None:
        return
    for player in pool.all_players:
        if nfl_positions(player) & NFL_SKILL_POSITIONS:
            continue
        mapped = by_id.get(str(getattr(player, "id", "") or ""))
        if mapped:
            player.original_positions = mapped


def apply_pool_constraints(
    optimizer: Any,
    *,
    no_offense_vs_dst: bool = False,
    one_rb_per_team: bool = False,
    projection_floor: float | None = None,
) -> None:
    """Apply optional GPP pool constraints via pydfs groups / remove_player."""

    if projection_floor is not None:
        locked = set(optimizer.player_pool.locked_players)
        for player in players_below_floor(
            optimizer.player_pool.all_players,
            float(projection_floor),
            locked=locked,
        ):
            optimizer.player_pool.remove_player(player)

    remaining = list(optimizer.player_pool.filtered_players)
    if no_offense_vs_dst:
        for dst, other in offense_vs_dst_pairs(remaining):
            optimizer.add_players_group(PlayersGroup([dst, other], max_from_group=1))

    if one_rb_per_team:
        for team_rbs in rbs_by_team(remaining).values():
            unique_ids = {
                getattr(player, "id", None) or getattr(player, "full_name", None) or player_team(player)
                for player in team_rbs
            }
            if len(unique_ids) < 2:
                continue
            optimizer.add_players_group(PlayersGroup(team_rbs, max_from_group=1))


def _csv_id_nfl_positions(csv_path: str | Path) -> dict[str, list[str]]:
    path = Path(csv_path)
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        if not reader.fieldnames:
            return {}
        fields = {str(name).strip().lower(): name for name in reader.fieldnames if name}
        id_key = fields.get("id")
        pos_key = fields.get("position")
        if not id_key or not pos_key:
            return {}
        by_id: dict[str, list[str]] = {}
        for row in reader:
            player_id = str(row.get(id_key) or "").strip()
            raw_pos = str(row.get(pos_key) or "").strip()
            if not player_id or not raw_pos:
                continue
            mapped = [
                part.strip().upper()
                for part in raw_pos.split("/")
                if part.strip().upper() in NFL_SKILL_POSITIONS
            ]
            if mapped:
                by_id[player_id] = mapped
        return by_id
