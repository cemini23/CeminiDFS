"""pydfs-lineup-optimizer wrapper for CeminiDFS exports."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

from .normalize import normalize_site

DEFAULT_MIN_SALARY = {
    "fanduel": 59400,
    "draftkings": 49000,
}

LINEUP_HEADERS = {
    "fanduel": ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DEF"],
    "draftkings": ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"],
}

POSITION_ALIASES = {
    "DEF": ("DEF", "D", "DST"),
    "DST": ("DST", "DEF", "D"),
}


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
    if site_key == "fanduel":
        return site_cls.FANDUEL
    if site_key == "draftkings":
        return site_cls.DRAFTKINGS
    raise ValueError(f"Unsupported site: {site_key}")


def _lineup_row(players: list[Any], header: list[str]) -> list[str]:
    by_pos: dict[str, list[str]] = {}
    for player in players:
        by_pos.setdefault(player.lineup_position, []).append(player.full_name)

    row: list[str] = []
    for column in header:
        names: list[str] = []
        for alias in POSITION_ALIASES.get(column, (column,)):
            if by_pos.get(alias):
                names = by_pos[alias]
                break
        row.append(names.pop(0) if names else "")
    return row


def generate_lineups(
    csv_path: str | Path,
    site: str = "fanduel",
    count: int = 150,
    *,
    min_salary: int | None = None,
    max_exposure: float | None = 0.35,
    stacks: list[str] | None = None,
    max_repeating_players: int | None = 7,
) -> list[Any]:
    """Generate pydfs lineup objects without writing them."""

    site_key = normalize_site(site)
    csv_file = Path(csv_path)
    if not csv_file.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_file}")

    Site, Sport, get_optimizer, TeamStack = _load_pydfs()
    optimizer = get_optimizer(_site_enum(site_key, Site), Sport.FOOTBALL)
    optimizer.load_players_from_csv(str(csv_file))
    _relax_tiny_slate_limits(optimizer, site_key)

    if _is_tiny_slate(optimizer) and max_repeating_players == 7:
        max_repeating_players = None

    if max_repeating_players is not None:
        optimizer.set_max_repeating_players(max_repeating_players)

    salary_floor = DEFAULT_MIN_SALARY[site_key] if min_salary is None else min_salary
    if salary_floor:
        optimizer.set_min_salary_cap(salary_floor)

    for rule in stacks or []:
        parts = rule.lower().split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid stack rule {rule!r}; expected format like qb:2")
        pos, n = parts[0], int(parts[1])
        optimizer.add_stack(TeamStack(n, for_positions=[pos.upper()]))

    if _is_tiny_slate(optimizer) and max_exposure == 0.35:
        max_exposure = None

    lineups = list(optimizer.optimize(n=count, max_exposure=max_exposure or None))
    if not lineups:
        raise ValueError("optimizer returned 0 lineups; check CSV columns and salaries")
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
    max_repeating_players: int | None = 7,
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
        max_repeating_players=max_repeating_players,
    )
    return write_lineup_rows([lineup_to_row(lineup, site_key) for lineup in lineups], out_path, site_key)


def _relax_tiny_slate_limits(optimizer: Any, site_key: str) -> None:
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
    parser.add_argument("--site", default="fanduel", choices=["fanduel", "fd", "draftkings", "dk"])
    parser.add_argument("--count", type=int, default=150, help="Number of lineups")
    parser.add_argument("--min-salary", type=int, default=None, help="Min salary cap used (0=disable)")
    parser.add_argument("--max-exposure", type=float, default=0.35, help="Max player exposure 0-1")
    parser.add_argument("--max-repeating-players", type=int, default=7)
    parser.add_argument("--stack", action="append", default=[], help="Stack rule e.g. qb:2")
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
            max_repeating_players=args.max_repeating_players,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {count} lineups -> {Path(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
