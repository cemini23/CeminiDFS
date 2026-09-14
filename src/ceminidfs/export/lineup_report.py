"""Human lineup cards: stack badges and exposure tables."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

DST_POSITIONS = frozenset({"D", "DEF", "DST"})
QUESTIONABLE_TOKENS = frozenset({"Q", "QUESTIONABLE"})
DEFAULT_TEAM_EXPOSURE_WARN = 0.5

def lineup_players(lineup: Any) -> list[Any]:
    players = getattr(lineup, "players", None)
    if players is None:
        return []
    return list(players)


def player_positions(player: Any) -> set[str]:
    raw = getattr(player, "positions", None) or ()
    extra = getattr(player, "lineup_position", None)
    values = [str(item).upper() for item in raw]
    if extra:
        values.append(str(extra).upper())
    return {item for item in values if item}


def player_team(player: Any) -> str:
    return str(getattr(player, "team", "") or "").strip().upper()


def player_name(player: Any) -> str:
    return str(getattr(player, "full_name", "") or "").strip()


def opponent_team(player: Any) -> str:
    game = getattr(player, "game_info", None)
    team = player_team(player)
    if game is None or not team:
        return ""
    home = str(getattr(game, "home_team", "") or "").strip().upper()
    away = str(getattr(game, "away_team", "") or "").strip().upper()
    if team == home:
        return away
    if team == away:
        return home
    return ""


def lineup_stack_badges(lineup: Any) -> list[str]:
    """Return short badges such as ``QB+2 CIN`` and ``BRING-BACK TB x1``."""

    players = lineup_players(lineup)
    if not players:
        return []

    team_counts = Counter(player_team(player) for player in players if player_team(player))
    qb = next((player for player in players if "QB" in player_positions(player)), None)
    badges: list[str] = []

    if qb is not None:
        qb_team = player_team(qb)
        pass_mates = [
            player
            for player in players
            if player is not qb
            and player_team(player) == qb_team
            and player_positions(player).intersection({"WR", "TE", "RB"})
        ]
        if pass_mates:
            badges.append(f"QB+{len(pass_mates)} {qb_team}")
        opp = opponent_team(qb)
        if opp:
            bring_backs = [
                player
                for player in players
                if player_team(player) == opp and not player_positions(player).issubset(DST_POSITIONS)
            ]
            if bring_backs:
                badges.append(f"BRING-BACK {opp} x{len(bring_backs)}")
            home = qb_team
            away = opp
            if home and away:
                left = team_counts.get(home, 0)
                right = team_counts.get(away, 0)
                badges.append(f"GAME {home}-{away} {left}-{right}")
        same_team_wrs = [
            player
            for player in players
            if player is not qb
            and player_team(player) == qb_team
            and "WR" in player_positions(player)
        ]
        if len(same_team_wrs) >= 2:
            badges.append("CHALK-QB-WR-WR")

    for team, count in team_counts.most_common():
        if count >= 2 and all(team not in badge for badge in badges):
            badges.append(f"{team} x{count}")

    return badges


def player_exposure_rows(lineups: Iterable[Any]) -> list[tuple[str, int, float]]:
    """Return (name, count, share) sorted by count then name."""

    pool = list(lineups)
    if not pool:
        return []
    counts: Counter[str] = Counter()
    for lineup in pool:
        names = {player_name(player) for player in lineup_players(lineup) if player_name(player)}
        counts.update(names)
    total = len(pool)
    rows = [(name, count, count / total) for name, count in counts.items()]
    rows.sort(key=lambda row: (-row[1], row[0]))
    return rows


def team_exposure_rows(lineups: Iterable[Any]) -> list[tuple[str, int, float]]:
    pool = list(lineups)
    if not pool:
        return []
    counts: Counter[str] = Counter()
    for lineup in pool:
        teams = {player_team(player) for player in lineup_players(lineup) if player_team(player)}
        counts.update(teams)
    total = len(pool)
    rows = [(team, count, count / total) for team, count in counts.items()]
    rows.sort(key=lambda row: (-row[1], row[0]))
    return rows


def player_is_questionable(player: Any) -> bool:
    """True when the player carries a Questionable tag (or pydfs is_injured)."""

    for attr in ("injury_indicator", "injury_status", "injury"):
        token = str(getattr(player, attr, "") or "").strip().upper()
        if token in QUESTIONABLE_TOKENS:
            return True
        if token:
            return False
    return bool(getattr(player, "is_injured", False))


def questionable_exposure_rows(lineups: Iterable[Any]) -> list[tuple[str, int]]:
    """Return (name, lineup_count) for rostered Questionable players."""

    pool = list(lineups)
    counts: Counter[str] = Counter()
    for lineup in pool:
        names = {
            player_name(player)
            for player in lineup_players(lineup)
            if player_name(player) and player_is_questionable(player)
        }
        counts.update(names)
    rows = [(name, count) for name, count in counts.items()]
    rows.sort(key=lambda row: (-row[1], row[0]))
    return rows


def format_lineup_report(
    lineups: Iterable[Any],
    *,
    stacks: list[str] | None = None,
    locks: list[str] | None = None,
    excludes: list[str] | None = None,
    no_offense_vs_dst: bool = False,
    one_rb_per_team: bool = False,
    projection_floor: float | None = None,
    uniques: int | None = None,
    max_team_exposure: float | None = None,
    preview: int = 8,
) -> str:
    """Plain-text report for the operator before FanDuel submit."""

    pool = list(lineups)
    lines = [
        f"Lineups: {len(pool)}",
        f"Stacks: {', '.join(stacks) if stacks else '(none)'}",
        f"Locks: {', '.join(locks) if locks else '(none)'}",
        f"Excludes: {', '.join(excludes) if excludes else '(none)'}",
    ]
    build_flags: list[str] = []
    if no_offense_vs_dst:
        build_flags.append("no-offense-vs-dst")
    if one_rb_per_team:
        build_flags.append("one-rb-per-team")
    if projection_floor is not None:
        build_flags.append(f"projection-floor={projection_floor}")
    if uniques is not None:
        build_flags.append(f"uniques={uniques}")
    if max_team_exposure is not None:
        build_flags.append(f"max-team-exposure={max_team_exposure}")
    if build_flags:
        lines.append(f"Build: {', '.join(build_flags)}")
    shown = len(pool) if len(pool) <= 20 else min(preview, len(pool))
    heading = f"All {shown} lineups" if len(pool) <= 20 else f"First {shown} lineups"
    lines.extend(
        [
            "",
            heading,
        ]
    )
    for index, lineup in enumerate(pool[:shown], start=1):
        badges = lineup_stack_badges(lineup)
        names = ", ".join(player_name(player) for player in lineup_players(lineup) if player_name(player))
        salary = getattr(lineup, "salary_costs", None)
        proj = getattr(lineup, "fantasy_points_projection", None)
        extra = []
        if salary is not None:
            extra.append(f"${int(salary)}")
        if proj is not None:
            extra.append(f"{float(proj):.1f} proj")
        meta = f" ({', '.join(extra)})" if extra else ""
        badge_text = " | ".join(badges) if badges else "no stack"
        lines.append(f"{index}. {badge_text}{meta}")
        lines.append(f"   {names}")

    lines.extend(["", "Player exposure"])
    for name, count, share in player_exposure_rows(pool)[:25]:
        lines.append(f"  {share:5.0%}  {count:3d}  {name}")

    lines.extend(["", "Team exposure (lineups that used the team)"])
    threshold = DEFAULT_TEAM_EXPOSURE_WARN if max_team_exposure is None else max_team_exposure
    for team, count, share in team_exposure_rows(pool):
        lines.append(f"  {share:5.0%}  {count:3d}  {team}")
        if share > threshold:
            lines.append(
                f"WARNING: {team} in {share:.0%} of lineups (above {threshold:.0%})"
            )

    q_rows = questionable_exposure_rows(pool)
    if not q_rows:
        lines.extend(["", "Questionable in book: none", ""])
    else:
        lines.extend(["", "Questionable in book"])
        for name, count in q_rows:
            lines.append(f"  {count:3d}  {name}")
        lines.append("")
    return "\n".join(lines)


def write_lineup_report(text: str, path: Any) -> Any:
    from pathlib import Path

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out
