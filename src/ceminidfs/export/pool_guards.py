"""Candidate-pool guards for the optimizer.

Two explicit guards live here. Both change the candidate pool only. The
optimizer still chooses freely.

- **Team dart.** ``--keep-team-dart SALARY`` keeps the cheapest eligible player
  at or below a dollar amount on every slate team. The guard fires only when the
  normal path removed every player on that team. It widens the pool; it cannot
  force a player into a book.
- **Soft fade.** ``--soft-fade TEAM`` lowers the weight of a team. A research
  ``fade`` lowers the weight of one player. Neither deletes a player. A hard
  fade (``--exclude`` or a research ``exclude``) removes a player.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd
from pydfs_lineup_optimizer.exceptions import LineupOptimizerException
from pydfs_lineup_optimizer.fantasy_points_strategy import BaseFantasyPointsStrategy

from ceminidfs.data.research_locks import QB_CELL_OPEN_TOKENS
from ceminidfs.data.stadiums import normalize_team_abbr
from ceminidfs.export.lineup_report import player_team
from ceminidfs.export.stack_rules import nfl_positions

# A skill player with no rush, target, or pass attempt stays out of the pool.
SKILL_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})

# The dart rule must never revive a player who cannot start.
UNAVAILABLE_INJURY_TOKENS = frozenset({"OUT", "O", "IR", "D", "DOUBTFUL", "PUP", "NFI"})

# A soft fade multiplies the player weight. The default keeps 65 percent.
DEFAULT_SOFT_FADE_WEIGHT = 0.65

# A classic multi-game slate must keep this many skill players after hard removes.
DEFAULT_MIN_SKILL_POOL = 40

_TEAM_KEYS = ("team", "team abbrev", "teamabbrev", "tm")
_POSITION_KEYS = ("position", "pos", "roster position")
_QB_CELL_KEYS = ("qb_cell", "qb cell")
_QB_STARTER_KEYS = ("is_qb_starter", "is qb starter")
_TRUTHY = frozenset({"1", "true", "yes", "y", "t", "x"})


def _fold_player_name(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _is_truthy(value: object) -> bool:
    return str(value or "").strip().lower() in _TRUTHY


def normalize_player_soft_fade_weights(
    soft_fade: Mapping[str, float] | Iterable[str] | None,
    *,
    default_weight: float = DEFAULT_SOFT_FADE_WEIGHT,
) -> dict[str, float]:
    """Return folded player name -> weight with a 0..1 clamp.

    A sequence of names uses ``default_weight`` for each name. A zero or
    negative weight would delete the player, so the default replaces it.
    """

    if soft_fade is None:
        return {}
    items = soft_fade.items() if isinstance(soft_fade, Mapping) else ((name, default_weight) for name in soft_fade)
    weights: dict[str, float] = {}
    for name, value in items:
        key = _fold_player_name(name)
        if not key:
            continue
        try:
            weight = float(value)
        except (TypeError, ValueError):
            weight = default_weight
        if weight <= 0:
            weight = default_weight
        weights[key] = min(1.0, weight)
    return weights


def normalize_soft_fade_weights(
    soft_fade: dict[str, float] | None,
    *,
    default_weight: float = DEFAULT_SOFT_FADE_WEIGHT,
) -> dict[str, float]:
    """Return team -> weight with normalized team keys and a 0..1 clamp."""

    weights: dict[str, float] = {}
    for team, value in (soft_fade or {}).items():
        key = normalize_team_abbr(str(team))
        if not key:
            continue
        try:
            weight = float(value)
        except (TypeError, ValueError):
            weight = default_weight
        # A zero or negative weight would delete the team. Soft fade discounts.
        if weight <= 0:
            weight = default_weight
        weights[key] = min(1.0, weight)
    return weights


class SoftFadeStrategy(BaseFantasyPointsStrategy):
    """Discount the fantasy points of softly faded teams and players.

    The strategy never removes a player.
    """

    def __init__(
        self,
        weights: dict[str, float],
        player_weights: dict[str, float] | None = None,
    ):
        self.weights = normalize_soft_fade_weights(weights)
        self.player_weights = normalize_player_soft_fade_weights(player_weights)

    def get_player_fantasy_points(self, player: Any) -> float:
        multiplier = self.weights.get(normalize_team_abbr(player_team(player)), 1.0)
        multiplier *= self.player_weights.get(
            _fold_player_name(getattr(player, "full_name", "")),
            1.0,
        )
        return float(getattr(player, "fppg", 0.0) or 0.0) * multiplier


def apply_soft_fade(
    optimizer: Any,
    soft_fade: dict[str, float] | None,
    *,
    player_soft_fade: Mapping[str, float] | Iterable[str] | None = None,
    default_weight: float = DEFAULT_SOFT_FADE_WEIGHT,
) -> dict[str, float]:
    """Lower the weight of each softly faded team or player.

    Return the applied team weights. Soft fade never removes a player, so the
    pool size does not change.
    """

    weights = normalize_soft_fade_weights(soft_fade, default_weight=default_weight)
    player_weights = normalize_player_soft_fade_weights(
        player_soft_fade,
        default_weight=default_weight,
    )
    if not weights and not player_weights:
        return {}
    optimizer.set_fantasy_points_strategy(SoftFadeStrategy(weights, player_weights))
    for team, weight in sorted(weights.items()):
        print(
            f"soft fade: {team} weight {weight:g} (discount only, no player removed)",
            file=sys.stderr,
        )
    if player_weights:
        print(
            f"player soft fade: {len(player_weights)} names at {default_weight:g} (not removed)",
            file=sys.stderr,
        )
    return weights


def _lowered_row(row: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(key).strip().lower(): str(value or "").strip()
        for key, value in row.items()
        if key
    }


def _row_value(lowered: Mapping[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = lowered.get(key)
        if value:
            return value
    return ""


def open_qb_teams_from_csv(path: str | Path) -> set[str]:
    """Return teams with an open quarterback cell.

    A ``qb_cell`` value of ``open``, ``unassigned``, or ``tbd`` marks the row's
    team. When the CSV has an ``is_qb_starter`` column, a team with two or more
    QB rows and no truthy starter is also open. An absent column is not inferred.
    """

    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    open_teams: set[str] = set()
    qb_rows: dict[str, list[bool]] = defaultdict(list)
    has_starter_column = False
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        for row in reader:
            lowered = _lowered_row(row)
            team = normalize_team_abbr(_row_value(lowered, _TEAM_KEYS))
            cell = _row_value(lowered, _QB_CELL_KEYS).lower()
            if team and cell in QB_CELL_OPEN_TOKENS:
                open_teams.add(team)
            starter_key = next((key for key in _QB_STARTER_KEYS if key in lowered), None)
            if starter_key is not None:
                has_starter_column = True
            position = _row_value(lowered, _POSITION_KEYS).upper()
            if team and position == "QB":
                starter_value = lowered.get(starter_key) if starter_key else ""
                qb_rows[team].append(_is_truthy(starter_value))

    if has_starter_column:
        for team, starter_flags in qb_rows.items():
            if len(starter_flags) >= 2 and not any(starter_flags):
                open_teams.add(team)
    return open_teams


def _is_qb_player(player: Any) -> bool:
    return "QB" in nfl_positions(player)


def apply_open_qb_gate(optimizer: Any, open_teams: Iterable[str]) -> list[str]:
    """Remove every QB on an open team. Print one warning per team.

    The gate does not choose a starting quarterback. Return the teams it acted on.
    """

    teams = {normalize_team_abbr(team) for team in open_teams if str(team or "").strip()}
    if not teams:
        return []
    pool = getattr(optimizer, "player_pool", None)
    if pool is None:
        return []

    removed_teams: list[str] = []
    for team in sorted(teams):
        removed = 0
        for player in list(getattr(pool, "all_players", []) or []):
            if normalize_team_abbr(player_team(player)) != team or not _is_qb_player(player):
                continue
            try:
                pool.remove_player(player)
            except LineupOptimizerException:
                continue
            removed += 1
        if removed:
            print(f"QB cell open for {team}; no quarterback rostered", file=sys.stderr)
            removed_teams.append(team)
    return removed_teams


def count_eligible_skill_players(optimizer: Any) -> int:
    """Count eligible QB, RB, WR, and TE players. Defense does not count."""

    pool = getattr(optimizer, "player_pool", None)
    if pool is None:
        return 0
    seen: set[str] = set()
    count = 0
    for player in getattr(pool, "filtered_players", []) or []:
        if not (nfl_positions(player) & SKILL_POSITIONS):
            continue
        identity = _player_identity(player)
        if identity in seen:
            continue
        seen.add(identity)
        count += 1
    return count


def apply_skill_pool_floor(
    optimizer: Any,
    floor: int | None,
    *,
    site_key: str,
) -> int:
    """Raise before the solve when the eligible skill pool is below the floor.

    Return the eligible skill count. A ``None`` floor, a showdown site, or a
    tiny slate skips the gate. Floor ``0`` logs and disables the gate.
    """

    if floor is None or site_key in {"fanduel_showdown", "draftkings_showdown"}:
        return count_eligible_skill_players(optimizer)
    if _optimizer_is_tiny_slate(optimizer):
        return count_eligible_skill_players(optimizer)

    count = count_eligible_skill_players(optimizer)
    print(f"skill pool: {count} eligible, floor {floor}", file=sys.stderr)
    if floor > 0 and count < floor:
        raise ValueError(
            f"skill pool: {count} eligible, floor {floor}; "
            "hard excludes removed too many skill players"
        )
    return count


def _optimizer_is_tiny_slate(optimizer: Any) -> bool:
    teams = getattr(getattr(optimizer, "player_pool", None), "available_teams", None)
    return len(list(teams or [])) <= 2


def _player_identity(player: Any) -> str:
    return str(getattr(player, "id", None) or getattr(player, "full_name", None) or player)


def _is_injury_eligible(player: Any) -> bool:
    if bool(getattr(player, "is_injured", False)):
        return False
    tag = str(getattr(player, "injury_status", "") or "").strip().upper()
    if not tag:
        return True
    return tag not in UNAVAILABLE_INJURY_TOKENS


def _player_salary(player: Any) -> float:
    try:
        return float(getattr(player, "salary"))
    except (TypeError, ValueError):
        return float("inf")


def apply_team_dart_guard(
    optimizer: Any,
    dart_salary: float,
    *,
    slate_teams: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Keep one cheap eligible player alive on every slate team.

    A team is at risk when no eligible player remains at or below the dart
    salary. The guard restores the cheapest eligible player at or below that
    salary. The rule fires only after the normal path removed the player, so the
    log shows the teams that the normal path would have lost.

    A negative or zero ``dart_salary`` is off. Return one record per kept team.
    """

    if dart_salary is None or float(dart_salary) <= 0:
        return []

    pool = getattr(optimizer, "player_pool", None)
    if pool is None:
        return []

    cap = float(dart_salary)
    all_players = list(pool.all_players)
    eligible_now = {_player_identity(player) for player in pool.filtered_players}

    teams = set(slate_teams or ())
    if not teams:
        teams = {player_team(player) for player in all_players if player_team(player)}

    kept: list[dict[str, Any]] = []
    for team in sorted(teams):
        candidates = [player for player in all_players if player_team(player) == team]
        affordable = [
            player
            for player in candidates
            if _is_injury_eligible(player) and _player_salary(player) <= cap
        ]
        if not affordable:
            continue
        # At risk when no eligible player at or below the dart salary remains.
        if any(_player_identity(player) in eligible_now for player in affordable):
            continue
        cheapest = min(affordable, key=_player_salary)
        try:
            pool.restore_player(cheapest)
        except LineupOptimizerException:
            # The player is already eligible by another route; nothing to do.
            continue
        eligible_now.add(_player_identity(cheapest))
        record = {
            "team": team,
            "player": str(getattr(cheapest, "full_name", "") or ""),
            "salary": int(_player_salary(cheapest)),
            "note": "kept by --keep-team-dart; the normal path had removed the team",
        }
        kept.append(record)
        print(
            f"team dart: kept {record['player']} ({team}, ${record['salary']}) "
            "-- the normal path removed the whole team",
            file=sys.stderr,
        )
    return kept


def participation_name_key(value: object) -> str:
    """Fold a player name for the role gate. Case and extra spaces do not matter."""

    return " ".join(str(value or "").casefold().split())


def names_with_participation(pbp: pd.DataFrame, *, through_week: int) -> set[str]:
    """Return names with a rush, a target, or a pass attempt in weeks 1..through_week."""

    if pbp is None or pbp.empty or through_week < 1:
        return set()
    frame = pbp
    if "week" in frame.columns:
        weeks = pd.to_numeric(frame["week"], errors="coerce")
        frame = frame.loc[(weeks >= 1) & (weeks <= through_week)]
    if frame.empty:
        return set()

    names: set[str] = set()
    pass_flag = _any_flag(frame, ("pass_attempt", "pass"))
    rush_flag = _any_flag(frame, ("rush", "rush_attempt"))
    _collect_names(names, frame, pass_flag, ("passer_player_name", "passer", "qb_player_name"))
    _collect_names(names, frame, pass_flag, ("receiver_player_name", "receiver"))
    _collect_names(names, frame, rush_flag, ("rusher_player_name", "rusher"))
    return names


def apply_participation_gate(
    rows: Sequence[Mapping[str, Any]],
    participated: set[str],
    *,
    week: int,
) -> list[dict[str, Any]]:
    """Drop skill players with no prior touch. Defense rows stay.

    Week 1 has no prior week, so the gate drops nobody. The log line is
    ``role gate: floor=1 touch in weeks 1..{week-1}; dropped={n}``.
    """

    end_week = week - 1
    if week <= 1:
        print(
            f"role gate: floor=1 touch in weeks 1..{end_week}; dropped=0",
            file=sys.stderr,
        )
        return [dict(row) for row in rows]

    known = {participation_name_key(name) for name in participated}
    kept: list[dict[str, Any]] = []
    dropped = 0
    for row in rows:
        if _is_skill_row(row) and participation_name_key(_row_name(row)) not in known:
            dropped += 1
            continue
        kept.append(dict(row))
    print(
        f"role gate: floor=1 touch in weeks 1..{end_week}; dropped={dropped}",
        file=sys.stderr,
    )
    return kept


def _any_flag(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    mask = pd.Series(False, index=frame.index)
    for column in columns:
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce").fillna(0)
        mask = mask | values.eq(1)
    return mask


def _collect_names(
    names: set[str],
    frame: pd.DataFrame,
    mask: pd.Series,
    columns: tuple[str, ...],
) -> None:
    column = next((name for name in columns if name in frame.columns), None)
    if column is None or not bool(mask.any()):
        return
    for value in frame.loc[mask, column].dropna():
        text = str(value).strip()
        if text and text.lower() != "nan":
            names.add(participation_name_key(text))


def _row_name(row: Mapping[str, Any]) -> str:
    for key in ("Name", "name", "player_name", "Nickname"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    first = str(row.get("First Name") or row.get("first_name") or "").strip()
    last = str(row.get("Last Name") or row.get("last_name") or "").strip()
    return f"{first} {last}".strip()


def _row_position(row: Mapping[str, Any]) -> str:
    for key in ("Position", "fd_position", "position", "Roster Position"):
        value = str(row.get(key) or "").strip().upper()
        if value:
            return value.split("/")[0].strip()
    return ""


def _is_skill_row(row: Mapping[str, Any]) -> bool:
    return _row_position(row) in SKILL_POSITIONS
