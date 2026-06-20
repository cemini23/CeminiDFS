"""Late-swap existing pydfs lineups after teams lock.

pydfs can import site upload CSVs via ``load_lineups_from_csv``. CeminiDFS also
writes a simpler name-based lineup CSV, so this module falls back to parsing
that format when the installed pydfs importer cannot read the lineup file.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

from .normalize import normalize_site
from .optimize import LINEUP_HEADERS
from .optimize import _lineup_row, _load_pydfs, _relax_tiny_slate_limits, _site_enum


def _normalize_team(team: str) -> str:
    return team.strip().upper()


def _normalize_teams(teams: set[str]) -> set[str]:
    return {_normalize_team(team) for team in teams if _normalize_team(team)}


def _players_on_locked_teams(players: list[Any], locked_teams: set[str]) -> list[Any]:
    normalized = _normalize_teams(locked_teams)
    return [player for player in players if _normalize_team(str(getattr(player, "team", ""))) in normalized]


def late_swap_lineups(
    lineups_csv: str | Path,
    players_csv: str | Path,
    locked_teams: set[str],
    out_path: str | Path,
    site: str = "fanduel",
    count: int | None = None,
) -> int:
    """Late-swap existing lineups and return the number written.

    If pydfs cannot import ``lineups_csv`` directly, the fallback parser supports
    the simple CeminiDFS lineup format emitted by ``export.optimize``. Older
    pydfs installs without ``optimize_lineups`` cannot preserve lineup-specific
    locks and will raise a clear error instead of silently rebuilding everything.
    """

    site_key = normalize_site(site)
    lineups_file = Path(lineups_csv)
    players_file = Path(players_csv)
    out_file = Path(out_path)
    if not lineups_file.is_file():
        raise FileNotFoundError(f"Lineups CSV not found: {lineups_file}")
    if not players_file.is_file():
        raise FileNotFoundError(f"Players CSV not found: {players_file}")

    Site, Sport, get_optimizer, _TeamStack = _load_pydfs()
    optimizer = get_optimizer(_site_enum(site_key, Site), Sport.FOOTBALL)
    optimizer.load_players_from_csv(str(players_file))
    _relax_tiny_slate_limits(optimizer, site_key)

    players = list(optimizer.player_pool.all_players)
    locked_player_count = _mark_locked_team_games_started(players, locked_teams)
    if locked_teams and locked_player_count == 0:
        teams = ", ".join(sorted({str(getattr(player, "team", "")) for player in players}))
        raise ValueError(
            f"No players found for locked teams {sorted(_normalize_teams(locked_teams))}; "
            f"slate teams: {teams}"
        )

    existing_lineups = _load_lineups(optimizer, lineups_file, site_key)
    target_count = count if count is not None else len(existing_lineups)
    if target_count <= 0:
        raise ValueError("count must be positive")
    existing_lineups = existing_lineups[:target_count]

    if hasattr(optimizer, "optimize_lineups"):
        swapped = list(optimizer.optimize_lineups(existing_lineups))
    else:
        raise RuntimeError(
            "Installed pydfs-lineup-optimizer does not expose optimize_lineups; "
            "late swap cannot preserve locked players. Upgrade pydfs-lineup-optimizer."
        )

    if not swapped:
        raise ValueError("optimizer returned 0 lineups; check CSV columns and locked teams")

    header = LINEUP_HEADERS[site_key]
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for lineup in swapped:
            writer.writerow(_lineup_row(lineup.players, header))

    return len(swapped)


def _mark_locked_team_games_started(players: list[Any], locked_teams: set[str]) -> int:
    locked_players = _players_on_locked_teams(players, locked_teams)
    if not locked_players:
        return 0

    try:
        from pydfs_lineup_optimizer.player import GameInfo
    except ImportError as exc:  # pragma: no cover - _load_pydfs fails first in normal use
        raise RuntimeError("pydfs-lineup-optimizer is required for late swap") from exc

    for player in locked_players:
        game_info = getattr(player, "game_info", None)
        if game_info is None:
            player.game_info = GameInfo(None, None, None, game_started=True)
        else:
            game_info.game_started = True
        # Some pydfs examples use this name; is_game_started reads game_info in 3.6.
        setattr(player, "game_started", True)
    return len(locked_players)


def _load_lineups(optimizer: Any, lineups_file: Path, site_key: str) -> list[Any]:
    pydfs_error: Exception | None = None
    if hasattr(optimizer, "load_lineups_from_csv"):
        try:
            return list(optimizer.load_lineups_from_csv(str(lineups_file)))
        except Exception as exc:  # noqa: BLE001 - fallback handles alternate valid format
            pydfs_error = exc

    try:
        return _load_simple_lineups(lineups_file, optimizer.player_pool.all_players, site_key)
    except ValueError as exc:
        if pydfs_error is not None:
            raise ValueError(
                "Could not load lineups with pydfs load_lineups_from_csv or CeminiDFS simple lineup parser"
            ) from pydfs_error
        raise exc


def _load_simple_lineups(lineups_file: Path, players: list[Any], site_key: str) -> list[Any]:
    try:
        from pydfs_lineup_optimizer.lineup import Lineup
        from pydfs_lineup_optimizer.player import LineupPlayer
    except ImportError as exc:  # pragma: no cover - _load_pydfs fails first in normal use
        raise RuntimeError("pydfs-lineup-optimizer is required for late swap") from exc

    header = LINEUP_HEADERS[site_key]
    players_by_name = {_normalize_name(player.full_name): player for player in players}
    lineups: list[Any] = []

    with lineups_file.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            columns = next(reader)
        except StopIteration as exc:
            raise ValueError("empty lineups CSV") from exc

        if columns[: len(header)] != header:
            raise ValueError(f"unsupported CeminiDFS lineup headers: {columns}")

        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            lineup_players = []
            for position, name in zip(header, row[: len(header)]):
                clean_name = name.strip()
                if not clean_name:
                    continue
                player = players_by_name.get(_normalize_name(clean_name))
                if player is None:
                    raise ValueError(f"Lineup player not found in players pool: {clean_name}")
                lineup_players.append(LineupPlayer(player, position))
            if len(lineup_players) != len(header):
                raise ValueError(f"lineup has {len(lineup_players)} players; expected {len(header)}")
            lineups.append(Lineup(lineup_players))

    if not lineups:
        raise ValueError("no lineups found in lineups CSV")
    return lineups


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().split())


def main() -> int:
    parser = argparse.ArgumentParser(description="Late-swap pydfs lineups after teams lock")
    parser.add_argument("--lineups", required=True, help="Existing lineup CSV path")
    parser.add_argument("--players", required=True, help="Normalized pydfs player CSV path")
    parser.add_argument("--lock-team", action="append", default=[], help="Team abbreviation whose game has locked")
    parser.add_argument("--out", help="Output CSV path for swapped lineups")
    parser.add_argument("--site", default="fanduel", choices=["fanduel", "fd", "draftkings", "dk"])
    parser.add_argument("--count", type=int, default=None, help="Optional number of lineups to swap")
    args = parser.parse_args()

    try:
        output_path = (
            Path(args.out)
            if args.out
            else Path(args.lineups).with_name(f"{Path(args.lineups).stem}_late_swap.csv")
        )
        count = late_swap_lineups(
            args.lineups,
            args.players,
            set(args.lock_team),
            output_path,
            site=args.site,
            count=args.count,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {count} late-swapped lineups -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
