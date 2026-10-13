"""Build-time gates for a lineup book.

The gates in this module turn the review reports into refusals. Each gate
reads a lineup book and reports or raises. No gate changes a projection.

``optimize`` installs the same rules inside the pydfs solver. The solver then
never returns a book that breaks them. The functions here are the pure,
CSV-side form of the same rules. The reports and the tests use them.
"""

from __future__ import annotations

import math
from collections import Counter
from itertools import combinations
from typing import Any, Iterable, Mapping, Sequence

FIVE_CORE_SIZE = 5


class BuildGateError(ValueError):
    """A lineup book breaks a build-time gate."""


def name_key(name: object) -> str:
    """Fold one name for a comparison."""

    return " ".join(str(name or "").casefold().split())


def lineup_names(lineup: Any) -> list[str]:
    """Return the player names on a lineup.

    Accepts a pydfs lineup, a mapping, a row of cells, or a ``|``-joined
    string such as the ``players`` column of a totals CSV.
    """

    players = getattr(lineup, "players", None)
    if players is not None:
        return [str(getattr(player, "full_name", "") or "").strip() for player in players]
    if isinstance(lineup, Mapping):
        return [str(value).strip() for value in lineup.values() if str(value).strip()]
    if isinstance(lineup, str):
        return [part.strip() for part in lineup.split("|") if part.strip()]
    return [str(value).strip() for value in lineup if str(value).strip()]


def lineup_name_sets(lineups: Iterable[Any]) -> list[tuple[str, ...]]:
    """Return the sorted, folded name set of each lineup."""

    sets: list[tuple[str, ...]] = []
    for lineup in lineups:
        unique = {name_key(name) for name in lineup_names(lineup) if str(name).strip()}
        sets.append(tuple(sorted(unique)))
    return sets


def core_counts(
    lineups: Iterable[Any],
    size: int = FIVE_CORE_SIZE,
) -> Counter[tuple[str, ...]]:
    """Count how many lineups hold each ``size``-player combination."""

    if size <= 0:
        raise ValueError("core size must be positive")
    counts: Counter[tuple[str, ...]] = Counter()
    for names in lineup_name_sets(lineups):
        if len(names) < size:
            continue
        for combo in combinations(names, size):
            counts[combo] += 1
    return counts


def core_violations(
    lineups: Iterable[Any],
    cap: int,
    size: int = FIVE_CORE_SIZE,
) -> list[tuple[int, tuple[str, ...]]]:
    """Return every core over ``cap``, most used first."""

    counts = core_counts(lineups, size)
    over = [(count, combo) for combo, count in counts.items() if count > cap]
    over.sort(key=lambda item: (-item[0], item[1]))
    return over


def max_core_count(lineups: Iterable[Any], size: int = FIVE_CORE_SIZE) -> int:
    """Return the largest count of any repeated core. Zero when none repeat."""

    counts = core_counts(lineups, size)
    return max(counts.values(), default=0)


def assert_core_cap(
    lineups: Sequence[Any],
    cap: int | None,
    *,
    size: int = FIVE_CORE_SIZE,
) -> None:
    """Raise when a core appears on more than ``cap`` lineups."""

    if cap is None:
        return
    over = core_violations(lineups, cap, size)
    if not over:
        return
    count, combo = over[0]
    raise BuildGateError(
        f"{size}-player core appears {count} times; cap is {cap}: "
        + ", ".join(combo)
    )


def exposure_counts(lineups: Iterable[Any]) -> Counter[str]:
    """Count how many lineups hold each player once."""

    counts: Counter[str] = Counter()
    for names in lineup_name_sets(lineups):
        counts.update(names)
    return counts


def exposure_cap_count(limit: float, book_count: int) -> int:
    """Return the appearance cap ``floor(limit * book_count)``."""

    cap = math.floor(float(limit) * book_count + 1e-9)
    if limit > 0:
        cap = max(cap, 1)
    return cap


def exposure_violations(
    lineups: Sequence[Any],
    limit: float | None,
    *,
    overrides: Mapping[str, float] | None = None,
    book_count: int | None = None,
) -> list[tuple[str, int, int]]:
    """Return ``(player, count, cap)`` for each player over the cap.

    ``overrides`` raises the cap for one player. A player who leads his
    position by a wide margin can sit above the default cap. ``book_count``
    is the book size used for the cap. It defaults to the row count.
    """

    if limit is None:
        return []
    size = int(book_count) if book_count is not None else len(lineups)
    if size <= 0:
        return []
    default_cap = exposure_cap_count(limit, size)
    override_caps = {
        name_key(name): exposure_cap_count(value, size)
        for name, value in (overrides or {}).items()
    }
    over: list[tuple[str, int, int]] = []
    for name, count in exposure_counts(lineups).items():
        cap = override_caps.get(name, default_cap)
        if count > cap:
            over.append((name, count, cap))
    over.sort(key=lambda item: (-item[1], item[0]))
    return over


def assert_exposure_cap(
    lineups: Sequence[Any],
    limit: float | None,
    *,
    overrides: Mapping[str, float] | None = None,
    book_count: int | None = None,
) -> None:
    """Raise when a player is over the exposure cap."""

    over = exposure_violations(lineups, limit, overrides=overrides, book_count=book_count)
    if not over:
        return
    name, count, cap = over[0]
    raise BuildGateError(f"{name} is in {count} lineups; exposure cap is {cap}")


SKILL_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})


def load_gate_context(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, float], dict[str, str]]:
    """Return ``(projection, position)`` lookups keyed by folded name."""

    projections: dict[str, float] = {}
    positions: dict[str, str] = {}
    for row in rows:
        name = _row_name(row)
        if not name:
            continue
        key = name_key(name)
        projection = _first_number(row, ("FPPG", "fppg", "projection", "AvgPointsPerGame", "fd_projection"))
        if projection is not None:
            projections[key] = projection
        position = _first_text(row, ("Position", "position", "fd_position", "Roster Position", "pos"))
        if position:
            positions[key] = position.upper()
    return projections, positions


def pool_lookups(
    players: Iterable[Any],
) -> tuple[dict[str, float], dict[str, str]]:
    """Return ``(projection, position)`` lookups from player objects."""

    projections: dict[str, float] = {}
    positions: dict[str, str] = {}
    for player in players:
        key = name_key(_player_name(player))
        if not key:
            continue
        projection = _player_projection(player)
        if projection is not None:
            projections[key] = float(projection)
        position = _player_position(player)
        if position:
            positions[key] = position.upper()
    return projections, positions


def low_ceiling_names(
    projections: Mapping[str, float],
    positions: Mapping[str, str],
    floor: float,
    *,
    skill_only: bool = True,
) -> list[str]:
    """Return the names at or under the projection floor.

    A defense and a kicker are excluded when ``skill_only`` is set. Their
    projections sit near the floor and would flag every lineup.
    """

    names: list[str] = []
    for key, projection in projections.items():
        if projection > floor:
            continue
        if skill_only and not _is_skill_position(positions.get(key)):
            continue
        names.append(key)
    return sorted(set(names))


def low_ceiling_violations(
    lineups: Iterable[Any],
    under_floor: Iterable[str],
    max_per_lineup: int,
) -> list[tuple[int, tuple[str, ...]]]:
    """Return ``(count, lineup)`` for each lineup with too many low names."""

    keys = {name_key(name) for name in under_floor}
    if not keys:
        return []
    over: list[tuple[int, tuple[str, ...]]] = []
    for lineup, names in zip(lineups, lineup_name_sets(lineups)):
        hits = tuple(name for name in names if name in keys)
        if len(hits) > max_per_lineup:
            over.append((len(hits), hits))
    over.sort(key=lambda item: (-item[0], item[1]))
    return over


def position_lead_exempt(
    players: Iterable[Any],
    *,
    margin: float,
    cap: float,
) -> dict[str, float]:
    """Return ``{name: cap}`` for a player who leads his position by ``margin``.

    The comparison is within one position. A player is exempt when his
    projection is at least ``margin`` above the next best at that position.
    """

    best: dict[str, list[float]] = {}
    for player in players:
        projection = _player_projection(player)
        position = _player_position(player)
        if projection is None or not position:
            continue
        best.setdefault(position.upper(), []).append(float(projection))

    leaders: dict[str, float] = {}
    lead_positions = {
        position
        for position, values in best.items()
        if len(values) >= 2 and (max(values) - sorted(values)[-2]) >= margin
    }
    if not lead_positions:
        return leaders
    for player in players:
        projection = _player_projection(player)
        position = _player_position(player)
        if projection is None or not position:
            continue
        if position.upper() not in lead_positions:
            continue
        if float(projection) < max(best[position.upper()]) - 1e-9:
            continue
        name = _player_name(player)
        if name:
            leaders[name_key(name)] = float(cap)
    return leaders


def _is_skill_position(position: str | None) -> bool:
    if not position:
        return False
    parts = {
        part.strip().upper()
        for part in str(position).replace("/", ",").split(",")
        if part.strip()
    }
    return bool(parts & SKILL_POSITIONS)


def _player_name(player: Any) -> str:
    value = getattr(player, "full_name", None)
    if value is not None:
        return str(value or "").strip()
    if isinstance(player, Mapping):
        return _row_name(player)
    return ""


def _player_projection(player: Any) -> float | None:
    for attr in ("fppg", "projected_points", "fantasy_points_projection", "projection"):
        value = getattr(player, attr, None)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    if isinstance(player, Mapping):
        return _first_number(player, ("FPPG", "fppg", "projection", "AvgPointsPerGame"))
    return None


def _player_position(player: Any) -> str:
    positions = getattr(player, "positions", None)
    if positions:
        if isinstance(positions, str):
            return positions
        return str(positions[0])
    if isinstance(player, Mapping):
        return _first_text(player, ("Position", "position", "fd_position", "pos")) or ""
    return ""


def _row_name(row: Mapping[str, Any]) -> str:
    first = _first_text(row, ("First Name", "first_name", "first name"))
    last = _first_text(row, ("Last Name", "last_name", "last name"))
    if first and last:
        return f"{first} {last}"
    return _first_text(row, ("name", "player_name", "Name", "Player Name", "Nickname"))


def _first_text(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _first_number(row: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None
