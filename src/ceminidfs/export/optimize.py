"""pydfs-lineup-optimizer wrapper for CeminiDFS exports."""

from __future__ import annotations

import argparse
import csv
import itertools
import math
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from ceminidfs.data.availability import is_unavailable_status

from .build_gates import (
    FIVE_CORE_SIZE,
    BuildGateError,
    assert_core_cap,
    assert_exposure_cap,
    low_ceiling_names,
    low_ceiling_violations,
    position_lead_exempt,
)
from .lineup_report import format_lineup_report, write_lineup_report
from .normalize import SHOWDOWN_SITES, normalize_site
from .pool_guards import (
    TREND_MIN_EXPOSURE,
    TREND_MIN_SALARY,
    apply_open_qb_gate,
    apply_skill_pool_floor,
    apply_soft_fade,
    apply_team_dart_guard,
    open_qb_teams_from_csv,
    participation_name_key,
)
from .stack_rules import (
    apply_locks_and_excludes,
    apply_pool_constraints,
    apply_stack_specs,
    attach_csv_original_positions,
    nfl_positions,
    parse_stack_rules,
    resolve_repeating_players,
)

DEFAULT_MIN_SALARY = {
    "fanduel": 59400,
    "draftkings": 49000,
    "fanduel_showdown": 56000,
    "draftkings_showdown": 45000,
}

LINEUP_HEADERS = {
    "fanduel": ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DEF"],
    "draftkings": ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"],
    "fanduel_showdown": ["MVP", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"],
    "draftkings_showdown": ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"],
}

POSITION_ALIASES = {
    "DEF": ("DEF", "D", "DST"),
    "DST": ("DST", "DEF", "D"),
    "MVP": ("MVP", "CPT"),
}

CELL_FORMATS = ("name", "name_id", "id")

# Log of every team the dart rule kept. ``generate_lineups`` fills the list.
# The build report reads it after the solve. The list is process-local.
TEAM_DART_LOG: list[dict[str, Any]] = []


def _load_pydfs() -> tuple[Any, Any, Any, Any]:
    try:
        from pydfs_lineup_optimizer import Site, Sport, get_optimizer
        from pydfs_lineup_optimizer.stacks import TeamStack
    except ImportError as exc:
        raise RuntimeError(
            "pydfs-lineup-optimizer is required for lineup optimization. "
            "Install it with: pip install pydfs-lineup-optimizer"
        ) from exc
    return Site, Sport, get_optimizer, TeamStack


def _site_enum(site_key: str, site_cls: Any) -> Any:
    # 2026 FanDuel single-game (MVP 1.5x salary+points, DST allowed, $60k)
    # is not pydfs FANDUEL_SINGLE_GAME (old 1 MVP + 4 UTIL, no DST); both
    # showdown sites ride DK captain-mode structure (see generate_lineups for
    # the FanDuel $60k budget override).
    if site_key in SHOWDOWN_SITES:
        return site_cls.DRAFTKINGS_CAPTAIN_MODE
    if site_key == "fanduel":
        return site_cls.FANDUEL
    if site_key == "draftkings":
        return site_cls.DRAFTKINGS
    raise ValueError(f"Unsupported site: {site_key}")


def _player_id(player: Any) -> str:
    for attr in ("id", "player_id"):
        value = getattr(player, attr, None)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def cell_format(player: Any, fmt: str = "name") -> str:
    """Format one lineup seat as name, ``Name (id)``, or id-only."""

    if fmt not in CELL_FORMATS:
        raise ValueError(f"unsupported cell format: {fmt}")
    name = str(getattr(player, "full_name", "") or "").strip()
    if fmt == "name":
        return name
    player_id = _player_id(player)
    if not player_id:
        raise ValueError(f"missing FanDuel id for player: {name or '?'}")
    if fmt == "id":
        return player_id
    return f"{name} ({player_id})"


def _lineup_row(players: list[Any], header: list[str], fmt: str = "name") -> list[str]:
    by_pos: dict[str, list[Any]] = {}
    for player in players:
        by_pos.setdefault(player.lineup_position, []).append(player)

    row: list[str] = []
    for column in header:
        bucket: list[Any] = []
        for alias in POSITION_ALIASES.get(column, (column,)):
            if by_pos.get(alias):
                bucket = by_pos[alias]
                break
        row.append(cell_format(bucket.pop(0), fmt) if bucket else "")
    return row


def fanduel_artifact_paths(out_path: str | Path) -> tuple[Path, Path]:
    """Return ``*_fanduel_upload.csv`` and ``*_fanduel_ids.csv`` next to ``out_path``."""

    out_file = Path(out_path)
    stem = out_file.stem
    return (
        out_file.with_name(f"{stem}_fanduel_upload.csv"),
        out_file.with_name(f"{stem}_fanduel_ids.csv"),
    )


def write_lineup_artifacts(lineups: list[Any], out_path: str | Path, site: str = "fanduel") -> int:
    """Write name-only, FanDuel upload, and id-only lineup CSVs. Return row count."""

    site_key = normalize_site(site)
    header = LINEUP_HEADERS[site_key]
    out_file = Path(out_path)
    upload_path, ids_path = fanduel_artifact_paths(out_file)
    name_rows = [_lineup_row(lineup.players, header, fmt="name") for lineup in lineups]
    upload_rows = [_lineup_row(lineup.players, header, fmt="name_id") for lineup in lineups]
    id_rows = [_lineup_row(lineup.players, header, fmt="id") for lineup in lineups]
    write_lineup_rows(name_rows, out_file, site_key)
    write_lineup_rows(upload_rows, upload_path, site_key)
    write_lineup_rows(id_rows, ids_path, site_key)
    print(f"FanDuel upload -> {upload_path}")
    print(f"FanDuel ids -> {ids_path}")
    return len(lineups)


def _exposure_player_names(lineup: Any) -> list[str]:
    players = getattr(lineup, "players", None)
    if players is not None:
        return [str(getattr(player, "full_name", "") or "").strip() for player in players]
    if isinstance(lineup, dict):
        return [str(value).strip() for value in lineup.values() if str(value).strip()]
    try:
        return [str(value).strip() for value in lineup if str(value).strip()]
    except TypeError:
        return []


def _exposure_teams(lineup: Any) -> list[str]:
    players = getattr(lineup, "players", None)
    if players is None:
        return []
    teams: list[str] = []
    seen: set[str] = set()
    for player in players:
        team = str(getattr(player, "team", "") or "").strip().upper()
        if team and team not in seen:
            seen.add(team)
            teams.append(team)
    return teams


class ExposureCapError(ValueError):
    """A merged lineup would put a player over the exposure cap."""


def _exposure_cap(limit: float, final_count: int) -> int:
    cap = math.floor(float(limit) * final_count + 1e-9)
    if limit > 0:
        cap = max(cap, 1)
    return cap


def _pydfs_exposure_for_book(
    max_exposure: float | None,
    book_count: int,
    request_n: int,
) -> float | None:
    """Return the pydfs exposure that stops at the written-book appearance cap.

    pydfs blocks the next lineup when ``exposure <= used / n``. An exposure of
    0.35 on 25 lineups still allows 9 uses. The book cap is 8. The same
    players then fill the pool, and the book cannot reach 25. Pass
    ``cap / n`` so the solver stops at that cap. A value of 1 or more stays
    uncapped. The projection does not change.
    """

    if max_exposure is None or max_exposure >= 1 or request_n <= 0 or book_count <= 0:
        return max_exposure
    return _exposure_cap(max_exposure, book_count) / request_n


def _exposure_name_key(name: str) -> str:
    return " ".join(str(name).lower().split())


def select_with_exposure_caps(
    lineups: list[Any],
    final_count: int,
    max_exposure: float | None = None,
    max_team_exposure: float | None = None,
    exposure_overrides: Mapping[str, float] | None = None,
) -> list[Any]:
    """Greedily keep lineups that stay under player and/or team exposure caps.

    ``exposure_overrides`` raises the player cap for a named player. The value
    is a fraction of the book size. Every other player keeps ``max_exposure``.
    """

    player_cap = _exposure_cap(max_exposure, final_count) if max_exposure is not None else None
    team_cap = (
        _exposure_cap(max_team_exposure, final_count) if max_team_exposure is not None else None
    )
    overrides = {
        _exposure_name_key(name): _exposure_cap(value, final_count)
        for name, value in (exposure_overrides or {}).items()
    }
    selected: list[Any] = []
    player_counts: dict[str, int] = {}
    team_counts: dict[str, int] = {}
    for lineup in lineups:
        names = [
            " ".join(name.lower().split())
            for name in _exposure_player_names(lineup)
            if str(name).strip()
        ]
        teams = _exposure_teams(lineup)
        if player_cap is not None and any(
            player_counts.get(name, 0) + 1 > overrides.get(name, player_cap) for name in names
        ):
            continue
        if team_cap is not None and any(team_counts.get(team, 0) + 1 > team_cap for team in teams):
            continue
        selected.append(lineup)
        for name in names:
            player_counts[name] = player_counts.get(name, 0) + 1
        for team in teams:
            team_counts[team] = team_counts.get(team, 0) + 1
        if len(selected) >= final_count:
            break
    return selected


def _lineup_signature(lineup: Any) -> tuple[str, ...]:
    return tuple(sorted(_exposure_name_key(name) for name in _exposure_player_names(lineup)))


def _exposure_counts(lineups: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for lineup in lineups:
        for name in _exposure_player_names(lineup):
            key = _exposure_name_key(name)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _swap_respects_cap(
    counts: Mapping[str, int],
    old_sig: tuple[str, ...],
    new_sig: tuple[str, ...],
    cap: int | None,
) -> bool:
    """Return True when replacing ``old_sig`` with ``new_sig`` stays at or under ``cap``."""

    if cap is None:
        return True
    delta: dict[str, int] = {}
    for name in old_sig:
        delta[name] = delta.get(name, 0) - 1
    for name in new_sig:
        delta[name] = delta.get(name, 0) + 1
    return all(counts.get(name, 0) + change <= cap for name, change in delta.items())


def _apply_signature_delta(
    counts: dict[str, int],
    old_sig: tuple[str, ...],
    new_sig: tuple[str, ...],
) -> None:
    for name in old_sig:
        counts[name] = counts.get(name, 0) - 1
    for name in new_sig:
        counts[name] = counts.get(name, 0) + 1


def enforce_named_min_counts(
    selected: list[Any],
    candidates: list[Any],
    names: Iterable[str],
    *,
    final_count: int,
    exposure: float,
    max_exposure: float | None,
) -> list[Any]:
    """Keep each named player in at least ``exposure`` of the final book.

    The simulation rerank can drop a player the solver was told to use.
    This swaps a lower lineup for a candidate that contains the player.
    The swap tries the lowest lineups first, then an earlier lineup when the
    exposure cap would break. A player who is not in any legal candidate
    stays missing, and the log says so.
    """

    book = list(selected[:final_count])
    book_sigs = [_lineup_signature(lineup) for lineup in book]
    need = max(1, int(round(float(exposure) * final_count)))
    cap = _exposure_cap(max_exposure, final_count) if max_exposure is not None else None
    in_book = set(book_sigs)
    pool: list[tuple[Any, tuple[str, ...]]] = []
    pool_seen = set(in_book)
    for lineup in list(selected) + list(candidates):
        sig = _lineup_signature(lineup)
        if sig in pool_seen:
            continue
        pool.append((lineup, sig))
        pool_seen.add(sig)
    counts = _exposure_counts(book)

    for raw_name in names:
        key = _exposure_name_key(str(raw_name))
        if not key:
            continue
        while sum(1 for sig in book_sigs if key in sig) < need:
            placed = False
            for lineup, sig in pool:
                if sig in in_book or key not in sig:
                    continue
                if len(book) < final_count and _swap_respects_cap(counts, (), sig, cap):
                    book.append(lineup)
                    book_sigs.append(sig)
                    in_book.add(sig)
                    _apply_signature_delta(counts, (), sig)
                    placed = True
                    break
                for index in range(len(book) - 1, -1, -1):
                    if key in book_sigs[index]:
                        continue
                    old_sig = book_sigs[index]
                    if not _swap_respects_cap(counts, old_sig, sig, cap):
                        continue
                    book[index] = lineup
                    book_sigs[index] = sig
                    in_book.discard(old_sig)
                    in_book.add(sig)
                    _apply_signature_delta(counts, old_sig, sig)
                    placed = True
                    break
                if placed:
                    break
            if not placed:
                have = sum(1 for sig in book_sigs if key in sig)
                print(
                    f"trend include: {raw_name} is in {have} of {len(book)} lineups; "
                    f"wanted {need}",
                    file=sys.stderr,
                )
                break
    return book


def _read_lineup_csv_rows(path: str | Path, site: str) -> list[list[str]]:
    """Read a lineup CSV with ``csv.reader``. Keep every seat, including blanks."""

    site_key = normalize_site(site)
    header = LINEUP_HEADERS[site_key]
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Lineups CSV not found: {file_path}")
    rows: list[list[str]] = []
    with file_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            columns = [cell.strip() for cell in next(reader)]
        except StopIteration as exc:
            raise ValueError(f"empty lineups CSV: {file_path}") from exc
        if columns[: len(header)] != header:
            raise ValueError(f"unsupported lineup headers: {columns}")
        width = len(header)
        for raw in reader:
            if not any(cell.strip() for cell in raw):
                continue
            cells = [cell.strip() for cell in raw[:width]]
            if len(cells) < width:
                cells.extend([""] * (width - len(cells)))
            rows.append(cells)
    return rows


def _seat_name_keys(row: list[str]) -> list[tuple[str, str]]:
    seats: list[tuple[str, str]] = []
    for cell in row:
        display = " ".join(cell.split())
        if not display:
            continue
        seats.append((_exposure_name_key(display), display))
    return seats


def merge_lineup_csvs(
    base_path: str | Path,
    extra_path: str | Path,
    out_path: str | Path,
    *,
    max_exposure: float,
    final_count: int,
    site: str = "fanduel",
    core_cap: int | None = None,
    core_size: int = FIVE_CORE_SIZE,
) -> int:
    """Append extra rows, or raise before creating ``out_path``.

    The cap is ``floor(max_exposure * final_count)``. ``final_count`` is the
    book size. It is not the number of rows in the two files. The first extra
    row that would break the cap raises ``ExposureCapError``. Earlier extra
    rows are not written.

    ``core_cap`` refuses a repeated ``core_size``-player core over the limit.
    """

    site_key = normalize_site(site)
    cap = _exposure_cap(max_exposure, final_count)
    base_rows = _read_lineup_csv_rows(base_path, site_key)
    extra_rows = _read_lineup_csv_rows(extra_path, site_key)
    counts: dict[str, int] = {}
    for row in base_rows:
        for key, _display in _seat_name_keys(row):
            counts[key] = counts.get(key, 0) + 1
    core_counts: dict[tuple[str, ...], int] = {}
    if core_cap is not None:
        for row in base_rows:
            for combo in _row_core_keys(row, core_size):
                core_counts[combo] = core_counts.get(combo, 0) + 1

    accepted: list[list[str]] = []
    for row in extra_rows:
        adds: dict[str, int] = {}
        for key, display in _seat_name_keys(row):
            would = counts.get(key, 0) + adds.get(key, 0) + 1
            if would > cap:
                raise ExposureCapError(f"{display} would appear {would} times; cap is {cap}")
            adds[key] = adds.get(key, 0) + 1
        if core_cap is not None:
            for combo in _row_core_keys(row, core_size):
                would = core_counts.get(combo, 0) + 1
                if would > core_cap:
                    raise BuildGateError(
                        f"{core_size}-player core would appear {would} times; "
                        f"cap is {core_cap}: " + ", ".join(combo)
                    )
        for key, added in adds.items():
            counts[key] = counts.get(key, 0) + added
        if core_cap is not None:
            for combo in _row_core_keys(row, core_size):
                core_counts[combo] = core_counts.get(combo, 0) + 1
        accepted.append(row)
    return write_lineup_rows(base_rows + accepted, out_path, site_key)


def _row_core_keys(row: Iterable[str], size: int) -> list[tuple[str, ...]]:
    keys = sorted({_exposure_name_key(cell) for cell in row if str(cell).strip()})
    if len(keys) < size:
        return []
    return list(itertools.combinations(keys, size))


def _player_ids_by_name(players_csv: str | Path) -> dict[str, str]:
    """Map a normalized player name to its FanDuel id."""

    path = Path(players_csv)
    if not path.is_file():
        raise FileNotFoundError(f"players CSV not found: {path}")
    mapping: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            lowered = {
                str(key).strip().lower(): str(value or "").strip()
                for key, value in raw.items()
                if key
            }
            player_id = (
                lowered.get("id")
                or lowered.get("player id")
                or lowered.get("player_id")
                or ""
            )
            if not player_id:
                continue
            first = lowered.get("first name") or lowered.get("firstname") or ""
            last = lowered.get("last name") or lowered.get("lastname") or ""
            full = " ".join(part for part in (first, last) if part).strip()
            nickname = lowered.get("nickname") or lowered.get("name") or ""
            for label in (full, nickname):
                key = _exposure_name_key(label)
                if key:
                    mapping[key] = player_id
    return mapping


def write_merged_upload(
    name_csv: str | Path,
    players_csv: str | Path,
    site: str = "fanduel",
) -> tuple[Path, Path]:
    """Write FanDuel upload and id files for a merged name-only lineup CSV."""

    site_key = normalize_site(site)
    name_rows = _read_lineup_csv_rows(name_csv, site_key)
    id_by_name = _player_ids_by_name(players_csv)
    upload_rows: list[list[str]] = []
    id_rows: list[list[str]] = []
    for row in name_rows:
        upload: list[str] = []
        ids: list[str] = []
        for cell in row:
            name = " ".join(cell.split())
            if not name:
                upload.append("")
                ids.append("")
                continue
            player_id = id_by_name.get(_exposure_name_key(name))
            if not player_id:
                raise ValueError(f"missing FanDuel id for player: {name}")
            upload.append(f"{name} ({player_id})")
            ids.append(player_id)
        upload_rows.append(upload)
        id_rows.append(ids)
    upload_path, ids_path = fanduel_artifact_paths(name_csv)
    write_lineup_rows(upload_rows, upload_path, site_key)
    write_lineup_rows(id_rows, ids_path, site_key)
    print(f"FanDuel upload -> {upload_path}")
    print(f"FanDuel ids -> {ids_path}")
    return upload_path, ids_path


def _fold_lineup_name(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def te_def_pair(lineup: Any, site_key: str = "fanduel") -> tuple[str, str] | None:
    """Return the folded tight end and defense names on a classic lineup.

    Return ``None`` when either seat is absent. The pair is the rule key.
    """

    players = list(getattr(lineup, "players", []) or [])

    def slot_name(slots: set[str], position: str) -> str | None:
        for player in players:
            slot = str(getattr(player, "lineup_position", "") or "").upper()
            if slot in slots:
                name = _fold_lineup_name(getattr(player, "full_name", ""))
                if name:
                    return name
        for player in players:
            if position in nfl_positions(player):
                name = _fold_lineup_name(getattr(player, "full_name", ""))
                if name:
                    return name
        return None

    tight_end = slot_name({"TE"}, "TE")
    defense = slot_name({"DEF", "DST", "D"}, "D")
    if not tight_end or not defense:
        return None
    return (tight_end, defense)


def filter_te_def_pairs(
    lineups: list[Any],
    count: int,
    site_key: str = "fanduel",
) -> tuple[list[Any], tuple[str, str] | None]:
    """Keep the first ``count`` lineups that carry a new tight end and defense pair.

    Return the kept lineups and the most common repeated pair (or ``None``).
    """

    seen: set[tuple[str, str]] = set()
    kept: list[Any] = []
    pair_counts: dict[tuple[str, str], int] = {}
    for lineup in lineups:
        pair = te_def_pair(lineup, site_key)
        if pair is not None:
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
            if pair in seen:
                continue
            seen.add(pair)
        kept.append(lineup)
        if len(kept) >= count:
            break
    repeated: tuple[str, str] | None = None
    if pair_counts:
        candidate, hits = max(pair_counts.items(), key=lambda item: item[1])
        if hits > 1:
            repeated = candidate
    return kept, repeated


def _te_def_pair_message(
    repeated_pair: tuple[str, str] | None,
    found: int,
    count: int,
) -> str:
    if repeated_pair is not None:
        tight_end, defense = repeated_pair
        return (
            f"tight end and defense pair repeated: {tight_end} + {defense}; "
            f"only {found} unique pairs for {count} lineups"
        )
    return f"optimizer wrote {found} lineups; requested {count}"


def _lineup_player_names(lineup: Any) -> set[str]:
    return {
        _fold_lineup_name(getattr(player, "full_name", ""))
        for player in getattr(lineup, "players", []) or []
        if str(getattr(player, "full_name", "")).strip()
    }


def _assert_locks_and_excludes_hold(
    lineups: list[Any],
    locks: list[str],
    excludes: list[str],
) -> None:
    """Raise when a requested lock is missing or a hard exclude is present."""

    if not lineups:
        return
    wanted = {_fold_lineup_name(name) for name in locks or [] if str(name).strip()}
    banned = {_fold_lineup_name(name) for name in excludes or [] if str(name).strip()}
    for index, lineup in enumerate(lineups, start=1):
        names = _lineup_player_names(lineup)
        missing = sorted(wanted - names)
        if missing:
            raise ValueError(f"requested lock missing from lineup {index}: {', '.join(missing)}")
        present = sorted(banned & names)
        if present:
            raise ValueError(f"hard exclude in lineup {index}: {', '.join(present)}")


def _request_lineups(
    optimizer: Any,
    *,
    request_count: int,
    count: int,
    max_exposure: float | None,
    allow_short: bool = False,
) -> list[Any]:
    """Ask for extra lineups for the pair filter. Fall back to ``count``.

    A tight repeating cap or an exact-size pool can make the larger request
    infeasible. The original count is the fallback.
    """

    try:
        return _optimize_or_raise(
            optimizer,
            n=request_count,
            max_exposure=_pydfs_exposure_for_book(max_exposure, count, request_count),
            allow_short=allow_short,
        )
    except ValueError as exc:
        if request_count == count or "could not build lineups" not in str(exc):
            raise
    print(
        f"optimizer could not build {request_count} lineups; retry with {count}",
        file=sys.stderr,
    )
    return _optimize_or_raise(
        optimizer,
        n=count,
        max_exposure=_pydfs_exposure_for_book(max_exposure, count, count),
        allow_short=allow_short,
    )


def _install_unique_te_def_rule(optimizer: Any, site_key: str) -> None:
    """Ban a repeated tight-end and defense pair inside the solver.

    The post-filter cannot invent a new pair. The solver must leave the pair
    after one use. The projection does not change.
    """

    from pydfs_lineup_optimizer.rules import OptimizerRule
    from pydfs_lineup_optimizer.solvers import SolverSign

    class UniqueTeDefPairRule(OptimizerRule):
        def __init__(self, optimizer, players_dict, context):
            super().__init__(optimizer, players_dict, context)
            self._seen: list[tuple[Any, Any]] = []
            self._by_name: dict[str, Any] | None = None

        def _variables_by_name(self) -> dict[str, Any]:
            if self._by_name is None:
                names: dict[str, Any] = {}
                for player, variable in self.players_dict.items():
                    names.setdefault(_fold_lineup_name(player.full_name), variable)
                self._by_name = names
            return self._by_name

        def apply_for_iteration(self, solver, result):
            if result is not None:
                pair = te_def_pair(result, site_key)
                if pair is not None:
                    names = self._variables_by_name()
                    tight_end = names.get(pair[0])
                    defense = names.get(pair[1])
                    if tight_end is not None and defense is not None:
                        self._seen.append((tight_end, defense))
            for index, (tight_end, defense) in enumerate(self._seen, start=1):
                solver.add_constraint(
                    [tight_end, defense],
                    None,
                    SolverSign.LTE,
                    1,
                    name=f"unique_te_def_{index}",
                )

    optimizer.add_new_rule(UniqueTeDefPairRule)


def _gate_section(gates: Mapping[str, Any] | None, key: str) -> dict[str, Any]:
    """Return one gate block from the config, or an empty mapping."""

    if not gates:
        return {}
    block = gates.get(key)
    if isinstance(block, Mapping):
        return dict(block)
    return {}


def _optimizer_pool(optimizer: Any) -> list[Any]:
    return list(getattr(getattr(optimizer, "player_pool", None), "all_players", []) or [])


def exposure_hatch_overrides(
    players: Iterable[Any],
    gates: Mapping[str, Any] | None,
    max_exposure: float | None,
) -> dict[str, float]:
    """Return ``{name: cap}`` for players allowed above the default cap.

    ``players`` is any iterable with a name, a projection, and a position.
    A pydfs player and a normalized CSV row both work.
    """

    hatch = _gate_section(gates, "exposure_hatch")
    if not hatch.get("enabled") or max_exposure is None:
        return {}
    cap = float(hatch.get("cap", max_exposure))
    if cap <= float(max_exposure):
        return {}
    return position_lead_exempt(
        players,
        margin=float(hatch.get("lead_margin", 4.0)),
        cap=cap,
    )


def _apply_solver_exposure_hatch(
    optimizer: Any,
    overrides: Mapping[str, float],
    *,
    book_count: int,
    request_n: int,
) -> None:
    """Give each exempt player his own pydfs max exposure.

    pydfs reads ``player.max_exposure`` before the global value. The exempt
    player then reaches the higher cap, and every other player keeps the
    default cap.
    """

    if not overrides or request_n <= 0 or book_count <= 0:
        return
    for player in _optimizer_pool(optimizer):
        key = _exposure_name_key(getattr(player, "full_name", ""))
        if key in overrides:
            player.max_exposure = _exposure_cap(overrides[key], book_count) / request_n


def install_five_core_rule(optimizer: Any, *, size: int, cap: int) -> None:
    """Ban a repeated ``size``-player core inside the solver.

    After each lineup the rule counts every ``size``-subset of that lineup.
    When a subset reaches ``cap`` uses, the solver gets ``sum(subset) <= cap-1``.
    The solver then avoids that combination and still reaches the book size.
    A subset of a legal book is legal, so a later rerank cannot break the cap.
    """

    from pydfs_lineup_optimizer.rules import OptimizerRule
    from pydfs_lineup_optimizer.solvers import SolverSign

    class FiveCoreRule(OptimizerRule):
        def __init__(self, optimizer, players_dict, context):
            super().__init__(optimizer, players_dict, context)
            self._by_name: dict[str, Any] | None = None
            self._used: dict[tuple[str, ...], int] = {}
            self._exhausted: list[tuple[str, ...]] = []

        def _variables_by_name(self) -> dict[str, Any]:
            if self._by_name is None:
                names: dict[str, Any] = {}
                for player, variable in self.players_dict.items():
                    names.setdefault(_fold_lineup_name(player.full_name), variable)
                self._by_name = names
            return self._by_name

        def apply_for_iteration(self, solver, result):
            if result is not None:
                keys = sorted(
                    {
                        _fold_lineup_name(getattr(player, "full_name", ""))
                        for player in getattr(result, "players", [])
                    }
                    - {""}
                )
                if len(keys) >= size:
                    for combo in itertools.combinations(keys, size):
                        count = self._used.get(combo, 0) + 1
                        self._used[combo] = count
                        if count >= cap and combo not in self._exhausted:
                            self._exhausted.append(combo)
            names = self._variables_by_name()
            for index, combo in enumerate(self._exhausted, start=1):
                variables = [names.get(name) for name in combo]
                if any(variable is None for variable in variables):
                    continue
                solver.add_constraint(
                    variables,
                    None,
                    SolverSign.LTE,
                    size - 1,
                    name=f"five_core_{index}",
                )

    optimizer.add_new_rule(FiveCoreRule)


def load_gate_projections(csv_path: str | Path) -> tuple[dict[str, float], dict[str, str]]:
    """Return ``(projection, position)`` lookups from a players CSV."""

    from .build_gates import load_gate_context

    path = Path(csv_path)
    if not path.is_file():
        return {}, {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return load_gate_context(list(csv.DictReader(handle)))


def assert_gates_from_csv(
    lineups: list[Any],
    csv_path: str | Path,
    *,
    gates: Mapping[str, Any] | None,
    max_exposure: float | None,
    exposure_overrides: Mapping[str, float] | None = None,
    book_count: int | None = None,
) -> None:
    """Raise when the book breaks a gate. Read the projections from a CSV."""

    projections, positions = load_gate_projections(csv_path)
    assert_book_gates(
        lineups,
        gates=gates,
        max_exposure=max_exposure,
        exposure_overrides=exposure_overrides,
        projections=projections,
        positions=positions,
        book_count=book_count,
    )


def assert_book_gates(
    lineups: list[Any],
    *,
    gates: Mapping[str, Any] | None,
    max_exposure: float | None,
    exposure_overrides: Mapping[str, float] | None = None,
    projections: Mapping[str, float] | None = None,
    positions: Mapping[str, str] | None = None,
    book_count: int | None = None,
) -> None:
    """Raise when the finished book breaks a build-time gate."""

    core = _gate_section(gates, "core")
    if core.get("enabled"):
        assert_core_cap(
            lineups,
            int(core.get("max_count", 0)),
            size=int(core.get("size", FIVE_CORE_SIZE)),
        )
    assert_exposure_cap(
        lineups,
        max_exposure,
        overrides=exposure_overrides,
        book_count=book_count,
    )
    low = _gate_section(gates, "low_ceiling")
    if low.get("enabled") and projections is not None:
        floor = float(low.get("projection_floor", 0.0))
        allowed = int(low.get("max_per_lineup", 1))
        under = low_ceiling_names(
            projections,
            positions or {},
            floor,
            skill_only=bool(low.get("skill_only", True)),
        )
        over = low_ceiling_violations(lineups, under, allowed)
        if over:
            count, names = over[0]
            raise BuildGateError(
                f"lineup holds {count} players under {floor} points; "
                f"limit is {allowed}: " + ", ".join(names)
            )


def apply_friday_trend_exposure(
    optimizer: Any,
    names: Iterable[str],
    *,
    min_salary: int = TREND_MIN_SALARY,
    exposure: float = TREND_MIN_EXPOSURE,
) -> list[str]:
    """Set a lineup floor for trend names at or above ``min_salary``.

    A name below the salary floor stays eligible. The function does not
    delete a questionable player.
    """

    wanted = {participation_name_key(name) for name in names if str(name).strip()}
    if not wanted:
        return []
    forced: list[str] = []
    eligible_only: list[str] = []
    pool = getattr(getattr(optimizer, "player_pool", None), "all_players", []) or []
    for player in pool:
        full_name = str(getattr(player, "full_name", "") or "").strip()
        if participation_name_key(full_name) not in wanted:
            continue
        salary = int(float(getattr(player, "salary", 0) or 0))
        if salary < min_salary:
            eligible_only.append(full_name)
            continue
        player.min_exposure = float(exposure)
        forced.append(full_name)
    if forced or eligible_only:
        print(
            "trend include: "
            f"floor={exposure} on {len(forced)} players at salary>={min_salary}; "
            f"eligible only={len(eligible_only)}",
            file=sys.stderr,
        )
        if forced:
            print("trend include forced: " + ", ".join(sorted(forced)), file=sys.stderr)
    return forced


def generate_lineups(
    csv_path: str | Path,
    site: str = "fanduel",
    count: int = 150,
    *,
    min_salary: int | None = None,
    max_exposure: float | None = 0.35,
    stacks: list[str] | None = None,
    locks: list[str] | None = None,
    excludes: list[str] | None = None,
    max_repeating_players: int | None = 7,
    no_offense_vs_dst: bool = False,
    one_rb_per_team: bool = False,
    projection_floor: float | None = None,
    uniques: int | None = None,
    max_team_exposure: float | None = None,
    keep_team_dart: float = 0.0,
    soft_fade: dict[str, float] | None = None,
    player_soft_fade: Mapping[str, float] | Iterable[str] | None = None,
    min_skill_pool: int | None = None,
    open_qb_teams: Iterable[str] | None = None,
    require_count: bool = True,
    friday_trend_keys: Iterable[str] | None = None,
    gates: Mapping[str, Any] | None = None,
) -> list[Any]:
    """Generate pydfs lineup objects without writing them."""

    site_key = normalize_site(site)
    csv_file = Path(csv_path)
    if not csv_file.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_file}")

    print(
        "optimizer request: "
        f"count={count} locks={list(locks or [])} excludes={list(excludes or [])} "
        f"stacks={list(stacks or [])}",
        file=sys.stderr,
    )

    Site, Sport, get_optimizer, _team_stack = _load_pydfs()
    optimizer = get_optimizer(_site_enum(site_key, Site), Sport.FOOTBALL)
    if site_key == "fanduel_showdown":
        # FanDuel 2026 single game: 1 MVP + 5 FLEX at $60k, max 5 per team —
        # same 6-man structure as DK captain mode but with the FD budget/team cap.
        optimizer.settings.budget = 60000
        optimizer.settings.max_from_one_team = 5
    optimizer.load_players_from_csv(str(csv_file))
    attach_csv_original_positions(optimizer, csv_file)
    _relax_tiny_slate_limits(optimizer, site_key)
    keep_injury_tagged_players(optimizer, csv_file)
    apply_open_qb_gate(
        optimizer,
        set(open_qb_teams or ()) | open_qb_teams_from_csv(csv_file),
    )
    resolved_locks, resolved_excludes = apply_locks_and_excludes(
        optimizer,
        locks=locks,
        excludes=excludes,
    )
    assert_locked_players_eligible(optimizer)
    low_ceiling = _gate_section(gates, "low_ceiling")
    apply_pool_constraints(
        optimizer,
        no_offense_vs_dst=no_offense_vs_dst,
        one_rb_per_team=one_rb_per_team,
        projection_floor=projection_floor,
        low_ceiling_floor=(
            float(low_ceiling["projection_floor"]) if low_ceiling.get("enabled") else None
        ),
        low_ceiling_max=int(low_ceiling.get("max_per_lineup", 1)),
    )
    apply_soft_fade(optimizer, soft_fade, player_soft_fade=player_soft_fade)
    apply_skill_pool_floor(optimizer, min_skill_pool, site_key=site_key)
    TEAM_DART_LOG.clear()
    dart_log = apply_team_dart_guard(optimizer, keep_team_dart)
    apply_stack_specs(optimizer, parse_stack_rules(stacks))
    apply_friday_trend_exposure(optimizer, friday_trend_keys or ())

    repeating = resolve_repeating_players(
        slate_size=len(LINEUP_HEADERS[site_key]),
        max_repeating_players=max_repeating_players,
        uniques=uniques,
    )
    if uniques is None and _is_tiny_slate(optimizer) and repeating == 7:
        repeating = None

    if repeating is not None:
        optimizer.set_max_repeating_players(repeating)

    salary_floor = DEFAULT_MIN_SALARY[site_key] if min_salary is None else min_salary
    if salary_floor:
        optimizer.set_min_salary_cap(salary_floor)

    if _is_tiny_slate(optimizer) and max_exposure == 0.35:
        max_exposure = None

    pair_guard = site_key in {"fanduel", "draftkings"}
    # The solver bans a repeated tight-end and defense pair. Ask for the book
    # size. A larger request with the book cap is infeasible on a full slate.
    if pair_guard and require_count:
        _install_unique_te_def_rule(optimizer, site_key)

    core = _gate_section(gates, "core")
    if core.get("enabled") and site_key in {"fanduel", "draftkings"}:
        install_five_core_rule(
            optimizer,
            size=int(core.get("size", FIVE_CORE_SIZE)),
            cap=int(core.get("max_count", 0)),
        )

    overrides = exposure_hatch_overrides(_optimizer_pool(optimizer), gates, max_exposure)
    request_count = count
    _apply_solver_exposure_hatch(
        optimizer,
        overrides,
        book_count=count,
        request_n=request_count,
    )
    lineups = _request_lineups(
        optimizer,
        request_count=request_count,
        count=count,
        max_exposure=max_exposure or None,
        allow_short=not require_count,
    )
    if not lineups:
        raise ValueError("optimizer returned 0 lineups; check CSV columns and salaries")
    if (
        max_exposure is not None
        or max_team_exposure is not None
        or overrides
    ):
        lineups = select_with_exposure_caps(
            lineups,
            count,
            max_exposure=max_exposure,
            max_team_exposure=max_team_exposure,
            exposure_overrides=overrides,
        )
    TEAM_DART_LOG.extend(dart_log)
    if require_count and len(lineups) < count:
        raise ValueError(f"optimizer wrote {len(lineups)} lineups; requested {count}")
    if pair_guard and require_count:
        lineups, repeated_pair = filter_te_def_pairs(lineups, count, site_key)
        if len(lineups) < count:
            raise ValueError(_te_def_pair_message(repeated_pair, len(lineups), count))
    if require_count and len(lineups) != count:
        raise ValueError(f"optimizer wrote {len(lineups)} lineups; requested {count}")
    _assert_locks_and_excludes_hold(lineups, resolved_locks, resolved_excludes)
    assert_gates_from_csv(
        lineups,
        csv_file,
        gates=gates,
        max_exposure=max_exposure,
        exposure_overrides=overrides,
        book_count=count,
    )
    return lineups


def lineup_to_row(lineup: Any, site: str = "fanduel") -> list[str]:
    """Convert a pydfs lineup object to the CeminiDFS lineup CSV row format."""

    site_key = normalize_site(site)
    return _lineup_row(lineup.players, LINEUP_HEADERS[site_key])


def write_lineup_rows(rows: list[list[str]], out_path: str | Path, site: str = "fanduel") -> int:
    """Write lineup rows using the standard site header and return row count."""

    site_key = normalize_site(site)
    out_file = Path(out_path)
    header = LINEUP_HEADERS[site_key]
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    return len(rows)


def optimize_lineups(
    csv_path: str | Path,
    out_path: str | Path,
    site: str = "fanduel",
    count: int = 150,
    *,
    min_salary: int | None = None,
    max_exposure: float | None = 0.35,
    stacks: list[str] | None = None,
    locks: list[str] | None = None,
    excludes: list[str] | None = None,
    max_repeating_players: int | None = 7,
    no_offense_vs_dst: bool = False,
    one_rb_per_team: bool = False,
    projection_floor: float | None = None,
    uniques: int | None = None,
    max_team_exposure: float | None = None,
    keep_team_dart: float = 0.0,
    soft_fade: dict[str, float] | None = None,
    player_soft_fade: Mapping[str, float] | Iterable[str] | None = None,
    min_skill_pool: int | None = None,
    open_qb_teams: Iterable[str] | None = None,
    friday_trend_keys: Iterable[str] | None = None,
    report_path: str | Path | None = None,
    flag_wr_triples: bool = False,
    late_swap_audit: bool = False,
    ownership_fade_report: bool = False,
    ownership_calibration: str | Path | None = None,
    flag_duplicate_cores: bool = False,
    dart_ceiling_report: bool = False,
    flag_qb_starter: bool = False,
    flag_stack_concentration: bool = False,
    flag_correlated_pairs: bool = False,
    defense_context_report: bool = False,
    projection_bands: bool = False,
    environment: str | Path | None = None,
    season: int | None = None,
    week: int | None = None,
    gates: Mapping[str, Any] | None = None,
) -> int:
    """Optimize lineups from a pydfs CSV and return the number written."""

    site_key = normalize_site(site)
    lineups = generate_lineups(
        csv_path,
        site=site_key,
        count=count,
        min_salary=min_salary,
        max_exposure=max_exposure,
        stacks=stacks,
        locks=locks,
        excludes=excludes,
        max_repeating_players=max_repeating_players,
        no_offense_vs_dst=no_offense_vs_dst,
        one_rb_per_team=one_rb_per_team,
        projection_floor=projection_floor,
        uniques=uniques,
        max_team_exposure=max_team_exposure,
        keep_team_dart=keep_team_dart,
        soft_fade=soft_fade,
        player_soft_fade=player_soft_fade,
        min_skill_pool=min_skill_pool,
        open_qb_teams=open_qb_teams,
        friday_trend_keys=friday_trend_keys,
        gates=gates,
    )
    written = write_lineup_artifacts(lineups, out_path, site_key)
    from ceminidfs.export.review_reports import maybe_write_review_reports

    maybe_write_review_reports(
        out_path,
        csv_path,
        site=site_key,
        flag_wr_triples=flag_wr_triples,
        late_swap_audit=late_swap_audit,
        ownership_fade_report=ownership_fade_report,
        ownership_calibration=ownership_calibration,
        flag_duplicate_cores=flag_duplicate_cores,
        dart_ceiling_report=dart_ceiling_report,
        flag_qb_starter=flag_qb_starter,
        flag_stack_concentration=flag_stack_concentration,
        flag_correlated_pairs=flag_correlated_pairs,
        defense_context_report=defense_context_report,
        projection_bands=projection_bands,
        environment=environment,
        season=season,
        week=week,
        core_cap=_gate_section(gates, "core").get("max_count"),
    )
    _write_build_report(
        lineups,
        out_path,
        stacks=stacks,
        locks=locks,
        excludes=excludes,
        no_offense_vs_dst=no_offense_vs_dst,
        one_rb_per_team=one_rb_per_team,
        projection_floor=projection_floor,
        uniques=uniques,
        max_team_exposure=max_team_exposure,
        keep_team_dart=keep_team_dart,
        soft_fade=soft_fade,
        team_dart_log=list(TEAM_DART_LOG),
        report_path=report_path,
    )
    return written


def _write_build_report(
    lineups: list[Any],
    out_path: str | Path,
    *,
    stacks: list[str] | None,
    locks: list[str] | None,
    excludes: list[str] | None,
    no_offense_vs_dst: bool = False,
    one_rb_per_team: bool = False,
    projection_floor: float | None = None,
    uniques: int | None = None,
    max_team_exposure: float | None = None,
    keep_team_dart: float = 0.0,
    soft_fade: dict[str, float] | None = None,
    team_dart_log: list[dict[str, Any]] | None = None,
    report_path: str | Path | None,
) -> None:
    text = format_lineup_report(
        lineups,
        stacks=stacks,
        locks=locks,
        excludes=excludes,
        no_offense_vs_dst=no_offense_vs_dst,
        one_rb_per_team=one_rb_per_team,
        projection_floor=projection_floor,
        uniques=uniques,
        max_team_exposure=max_team_exposure,
        keep_team_dart=keep_team_dart,
        soft_fade=soft_fade,
        team_dart_log=team_dart_log,
    )
    target = Path(report_path) if report_path is not None else Path(out_path).with_suffix(".report.txt")
    write_lineup_report(text, target)
    print(text)
    print(f"Wrote lineup report -> {target}")


def _injury_status_by_name(csv_path: str | Path) -> dict[str, str]:
    """Read a salary CSV and map folded player name to injury status.

    Return ``{}`` when the file is missing or has no injury column.
    """

    path = Path(csv_path)
    if not path.is_file():
        return {}
    injury_aliases = ("injury indicator", "injury", "inj", "status", "injury_status")
    mapping: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        lowered = {str(name).strip().lower(): name for name in reader.fieldnames or []}
        injury_col = next((lowered[key] for key in injury_aliases if key in lowered), None)
        if injury_col is None:
            return {}
        first_col = lowered.get("first name") or lowered.get("firstname")
        last_col = lowered.get("last name") or lowered.get("lastname")
        name_col = (
            lowered.get("name") or lowered.get("player_name") or lowered.get("nickname")
        )
        for raw in reader:
            first = str(raw.get(first_col, "") or "").strip() if first_col else ""
            last = str(raw.get(last_col, "") or "").strip() if last_col else ""
            display = " ".join(part for part in (first, last) if part).strip()
            if not display and name_col:
                display = str(raw.get(name_col, "") or "").strip()
            status = str(raw.get(injury_col, "") or "").strip()
            key = _exposure_name_key(display) if display else ""
            if key and status:
                mapping[key] = status
    return mapping


def keep_injury_tagged_players(optimizer: Any, csv_path: str | Path | None = None) -> None:
    """Keep Q/questionable rows that pydfs marks injured, drop unavailable rows.

    The FanDuel importer sets ``is_injured`` for any non-empty Injury Indicator.
    Default pydfs filtering would drop every Q tag, so this function sets
    ``pool.with_injured = True``. It must still drop OUT/IR/PUP/NFI/NA/D/
    EXEMPT/SUSPENDED/DOUBTFUL/INACTIVE rows.

    Some callers pass a raw FanDuel salary CSV with no upstream normalize step.
    Read the status from ``csv_path`` itself in that case.
    """

    pool = getattr(optimizer, "player_pool", None)
    if pool is None:
        return
    status_by_name = _injury_status_by_name(csv_path) if csv_path is not None else {}
    removed = 0
    removed_statuses: set[str] = set()
    for player in list(pool.all_players):
        key = _exposure_name_key(getattr(player, "full_name", ""))
        status = status_by_name.get(key, "") if key else ""
        if status and is_unavailable_status(status):
            pool.remove_player(player)
            removed += 1
            removed_statuses.add(status.strip().upper())
    if removed > 0:
        print(
            f"optimizer pool: removed {removed} unavailable players "
            f"({sorted(removed_statuses)})",
            file=sys.stderr,
        )
    pool.with_injured = True
    all_n = len(pool.all_players)
    filtered_n = len(pool.filtered_players)
    tagged = sum(1 for player in pool.all_players if getattr(player, "is_injured", False))
    print(
        f"optimizer pool: {all_n} loaded, {filtered_n} eligible, {tagged} injury-tagged (kept)",
        file=sys.stderr,
    )


def assert_locked_players_eligible(optimizer: Any) -> None:
    """Raise ValueError when a lock is missing from the eligible pool."""

    pool = getattr(optimizer, "player_pool", None)
    if pool is None:
        return
    eligible = set(pool.filtered_players)
    missing = [
        player.full_name
        for player in getattr(pool, "locked_players", [])
        if player not in eligible
    ]
    if missing:
        names = ", ".join(missing)
        raise ValueError(
            f"Locked player(s) are not in the eligible pool: {names}. "
            "Questionable (Q) tags stay in the pool; check --lock versus --exclude."
        )


def _optimize_or_raise(optimizer: Any, **kwargs: Any) -> list[Any]:
    allow_short = bool(kwargs.pop("allow_short", False))
    built: list[Any] = []
    try:
        for lineup in optimizer.optimize(**kwargs):
            built.append(lineup)
        return built
    except KeyError as exc:
        raise ValueError(
            f"Locked player is not in the eligible optimizer pool: {exc}. "
            "Questionable (Q) tags stay in the pool; check --lock versus --exclude."
        ) from exc
    except Exception as exc:
        name = type(exc).__name__
        message = str(exc)
        stopped = name in {"LineupOptimizerException", "GenerateLineupException"} or "Unable to build" in message
        if allow_short and built and stopped:
            requested = kwargs.get("n")
            print(
                f"optimizer stopped after {len(built)} lineups; requested {requested}",
                file=sys.stderr,
            )
            return built
        if stopped:
            raise ValueError(f"pydfs could not build lineups: {message}") from exc
        raise


def _relax_tiny_slate_limits(optimizer: Any, site_key: str) -> None:
    if site_key in SHOWDOWN_SITES:
        # Single-game slates are always one game (two teams); captain mode
        # already caps max_from_one_team at 5 and DK/FD showdown allow a full
        # team, so the classic FD 9-slot tiny-slate relaxation does not apply.
        return
    if site_key != "fanduel" or not _is_tiny_slate(optimizer):
        return
    lineup_size = len(LINEUP_HEADERS[site_key])
    optimizer.settings.max_from_one_team = lineup_size
    optimizer.settings.min_teams = len(optimizer.player_pool.available_teams)


def _is_tiny_slate(optimizer: Any) -> bool:
    return len(getattr(optimizer.player_pool, "available_teams", []) or []) <= 2


def main() -> int:
    parser = argparse.ArgumentParser(description="NFL DFS lineup optimizer wrapper")
    parser.add_argument("--csv", required=True, help="Player projection CSV path")
    parser.add_argument("--out", required=True, help="Output CSV path for lineups")
    parser.add_argument(
        "--site",
        default="fanduel",
        choices=sorted(
            {
                "fanduel",
                "fd",
                "draftkings",
                "dk",
                *SHOWDOWN_SITES,
                "fd_showdown",
                "fd_single",
                "dk_showdown",
                "dk_captain",
                "draftkings_captain",
            }
        ),
    )
    parser.add_argument("--count", type=int, default=150, help="Number of lineups")
    parser.add_argument("--min-salary", type=int, default=None, help="Min salary cap used (0=disable)")
    parser.add_argument("--max-exposure", type=float, default=0.35, help="Max player exposure 0-1")
    parser.add_argument(
        "--max-team-exposure",
        type=float,
        default=None,
        help="Max share of lineups that may include any one team (0-1; default off)",
    )
    parser.add_argument("--max-repeating-players", type=int, default=7)
    parser.add_argument("--uniques", type=int, default=None, help="Alias: max_repeating = slate_size - N")
    parser.add_argument(
        "--no-offense-vs-dst",
        action="store_true",
        default=False,
        help="Block DST plus an offensive player from the opposing team",
    )
    parser.add_argument(
        "--one-rb-per-team",
        action="store_true",
        default=False,
        help="At most one RB from any single team",
    )
    parser.add_argument(
        "--projection-floor",
        type=float,
        default=None,
        help="Remove unlocked pool players with FPPG below N",
    )
    parser.add_argument(
        "--stack",
        action="append",
        default=[],
        help="Stack rule: qb:3, CIN:3, CIN3-TB2, 3-2, game:5, wr:2, rb+dst",
    )
    parser.add_argument("--lock", action="append", default=[], help="Force a player into every lineup")
    parser.add_argument("--exclude", action="append", default=[], help="Remove a player from the pool")
    args = parser.parse_args()

    try:
        count = optimize_lineups(
            args.csv,
            args.out,
            site=args.site,
            count=args.count,
            min_salary=args.min_salary,
            max_exposure=args.max_exposure,
            stacks=args.stack,
            locks=args.lock,
            excludes=args.exclude,
            max_repeating_players=args.max_repeating_players,
            no_offense_vs_dst=args.no_offense_vs_dst,
            one_rb_per_team=args.one_rb_per_team,
            projection_floor=args.projection_floor,
            uniques=args.uniques,
            max_team_exposure=args.max_team_exposure,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {count} lineups -> {Path(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
