"""pydfs-lineup-optimizer wrapper for CeminiDFS exports."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Any

from .lineup_report import format_lineup_report, write_lineup_report
from .normalize import SHOWDOWN_SITES, normalize_site
from .stack_rules import (
    apply_locks_and_excludes,
    apply_pool_constraints,
    apply_stack_specs,
    attach_csv_original_positions,
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


def _exposure_name_key(name: str) -> str:
    return " ".join(str(name).lower().split())


def select_with_exposure_caps(
    lineups: list[Any],
    final_count: int,
    max_exposure: float | None = None,
    max_team_exposure: float | None = None,
) -> list[Any]:
    """Greedily keep lineups that stay under player and/or team exposure caps."""

    player_cap = _exposure_cap(max_exposure, final_count) if max_exposure is not None else None
    team_cap = (
        _exposure_cap(max_team_exposure, final_count) if max_team_exposure is not None else None
    )
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
            player_counts.get(name, 0) + 1 > player_cap for name in names
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
) -> int:
    """Append extra rows, or raise before creating ``out_path``.

    The cap is ``floor(max_exposure * final_count)``. ``final_count`` is the
    book size. It is not the number of rows in the two files. The first extra
    row that would break the cap raises ``ExposureCapError``. Earlier extra
    rows are not written.
    """

    site_key = normalize_site(site)
    cap = _exposure_cap(max_exposure, final_count)
    base_rows = _read_lineup_csv_rows(base_path, site_key)
    extra_rows = _read_lineup_csv_rows(extra_path, site_key)
    counts: dict[str, int] = {}
    for row in base_rows:
        for key, _display in _seat_name_keys(row):
            counts[key] = counts.get(key, 0) + 1

    accepted: list[list[str]] = []
    for row in extra_rows:
        adds: dict[str, int] = {}
        for key, display in _seat_name_keys(row):
            would = counts.get(key, 0) + adds.get(key, 0) + 1
            if would > cap:
                raise ExposureCapError(f"{display} would appear {would} times; cap is {cap}")
            adds[key] = adds.get(key, 0) + 1
        for key, added in adds.items():
            counts[key] = counts.get(key, 0) + added
        accepted.append(row)
    return write_lineup_rows(base_rows + accepted, out_path, site_key)


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
) -> list[Any]:
    """Generate pydfs lineup objects without writing them."""

    site_key = normalize_site(site)
    csv_file = Path(csv_path)
    if not csv_file.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_file}")

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
    keep_injury_tagged_players(optimizer)
    apply_locks_and_excludes(optimizer, locks=locks, excludes=excludes)
    assert_locked_players_eligible(optimizer)
    apply_pool_constraints(
        optimizer,
        no_offense_vs_dst=no_offense_vs_dst,
        one_rb_per_team=one_rb_per_team,
        projection_floor=projection_floor,
    )
    apply_stack_specs(optimizer, parse_stack_rules(stacks))

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

    lineups = _optimize_or_raise(optimizer, n=count, max_exposure=max_exposure or None)
    if not lineups:
        raise ValueError("optimizer returned 0 lineups; check CSV columns and salaries")
    if max_exposure is not None or max_team_exposure is not None:
        lineups = select_with_exposure_caps(
            lineups,
            count,
            max_exposure=max_exposure,
            max_team_exposure=max_team_exposure,
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
    report_path: str | Path | None = None,
    flag_wr_triples: bool = False,
    late_swap_audit: bool = False,
    ownership_fade_report: bool = False,
    ownership_calibration: str | Path | None = None,
    flag_duplicate_cores: bool = False,
    dart_ceiling_report: bool = False,
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
    )
    target = Path(report_path) if report_path is not None else Path(out_path).with_suffix(".report.txt")
    write_lineup_report(text, target)
    print(text)
    print(f"Wrote lineup report -> {target}")


def keep_injury_tagged_players(optimizer: Any) -> None:
    """Keep Q/questionable rows that pydfs marks injured.

    The FanDuel importer sets ``is_injured`` for any non-empty Injury Indicator.
    CeminiDFS already dropped OUT/IR/D in normalize. Default pydfs filtering
    would then drop every remaining Q tag.
    """

    pool = getattr(optimizer, "player_pool", None)
    if pool is None:
        return
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
    try:
        return list(optimizer.optimize(**kwargs))
    except KeyError as exc:
        raise ValueError(
            f"Locked player is not in the eligible optimizer pool: {exc}. "
            "Questionable (Q) tags stay in the pool; check --lock versus --exclude."
        ) from exc
    except Exception as exc:
        name = type(exc).__name__
        message = str(exc)
        if name in {"LineupOptimizerException", "GenerateLineupException"} or "Unable to build" in message:
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
