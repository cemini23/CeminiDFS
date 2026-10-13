"""Hindsight upper bound for one Sunday late-swap window.

The oracle sees the final FanDuel stat line. It is not a live strategy.
This module does not build a particle filter.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from ceminidfs.config import PROJECT_ROOT
from ceminidfs.data.salary import parse_salary_csv
from ceminidfs.data.stadiums import normalize_team_abbr
from ceminidfs.pipeline.backtest import actual_week_fantasy_points, load_season_pbp

SEASON = 2026
WEEK = 3
SALARY_CAP = 60_000
SALARY_FLOOR = 58_500
STOP_POINTS = 8.0
STOP_SWAPS = 2
HINDSIGHT_ORACLE = True
LIVE_INFORMATION_ONLY = False

# Sunday afternoon lock waves only. TNF, SNF, and MNF are not decision times.
# A kickoff at or before the decision time is locked.
DECISION_CLOCKS = (time(13, 0), time(16, 5), time(16, 25))
AFTERNOON_KICKOFFS = frozenset(DECISION_CLOCKS)

LINEUP_SLOTS = ("QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DEF")
SLOT_POSITIONS = {
    "QB": frozenset({"QB"}),
    "RB": frozenset({"RB"}),
    "WR": frozenset({"WR"}),
    "TE": frozenset({"TE"}),
    "FLEX": frozenset({"RB", "WR", "TE"}),
    "DEF": frozenset({"DEF", "D", "DST"}),
}
_NAME_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})

DEFAULT_LINEUPS = PROJECT_ROOT / "runs" / "2026_week_3" / "lineups.csv"
DEFAULT_SALARY = PROJECT_ROOT / "data" / "slates" / "2026-09-27_fd_sun.csv"
DEFAULT_SCRATCH = PROJECT_ROOT / "config" / "2026-w03-sun-scratch.csv"
DEFAULT_SCHEDULE = PROJECT_ROOT / "artifacts" / "cache" / "schedules_2026.parquet"
DEFAULT_ROSTER = PROJECT_ROOT / "artifacts" / "cache" / "rosters_2026.parquet"
DEFAULT_REPORT = PROJECT_ROOT / "briefs" / "2026-10-03_k280-measure.md"


@dataclass(frozen=True)
class OraclePlayer:
    """One salary-file player with a final FanDuel point total."""

    name: str
    team: str
    position: str
    salary: int
    kickoff: datetime
    fd_points: float
    scratched: bool = False


@dataclass(frozen=True)
class Seat:
    """One FanDuel roster slot and the player who fills it."""

    slot: str
    player: OraclePlayer


@dataclass(frozen=True)
class OracleLineupResult:
    """Oracle lineup. The flags say this choice used the final stat line."""

    seats: tuple[Seat, ...]
    hindsight_oracle: bool = HINDSIGHT_ORACLE
    live_information_only: bool = LIVE_INFORMATION_ONLY


@dataclass(frozen=True)
class LineupScore:
    """Held lineup versus the hindsight oracle lineup."""

    index: int
    held_points: float
    oracle_points: float
    swaps: int
    changes: tuple[str, ...]


@dataclass(frozen=True)
class MeasureResult:
    """Printed measurement for one slate."""

    status: str
    points_gained: float | None
    swaps_changed: int | None
    lineups: tuple[LineupScore, ...]
    detail: str
    hindsight_oracle: bool = HINDSIGHT_ORACLE
    live_information_only: bool = LIVE_INFORMATION_ONLY


def normalize_person_name(name: str) -> str:
    """Return a join key for a person name. Drops suffixes and punctuation."""

    text = str(name or "").lower().replace("'", "").replace(".", "").replace("-", " ")
    parts = [part for part in text.split() if part and part not in _NAME_SUFFIXES]
    return " ".join(parts)


def canonical_position(position: str) -> str:
    """Return QB, RB, WR, TE, or DEF."""

    token = str(position or "").strip().upper()
    if token in {"D", "DST", "DEF"}:
        return "DEF"
    return token


def player_key(player: OraclePlayer) -> str:
    """Return the identity used to keep one player out of two seats."""

    return f"{normalize_person_name(player.name)}|{player.team}"


def player_is_locked(kickoff: datetime, decision_time: datetime) -> bool:
    """Return True when the player's game has started at the decision time."""

    return kickoff <= decision_time


def slot_allows(slot: str, position: str) -> bool:
    """Return True when the position may fill the FanDuel slot."""

    allowed = SLOT_POSITIONS.get(slot)
    if allowed is None:
        return False
    return canonical_position(position) in allowed


def apply_hindsight_oracle(
    seats: Sequence[Seat],
    pool: Sequence[OraclePlayer],
    decision_time: datetime,
    *,
    salary_cap: int = SALARY_CAP,
    salary_floor: int = SALARY_FLOOR,
) -> OracleLineupResult:
    """Replace unlocked seats with the highest final-point legal substitutes.

    Locked means kickoff is at or before ``decision_time``. The choice uses
    ``fd_points`` on each player. Those points are the final stat line.
    """

    locked_index = [
        index
        for index, seat in enumerate(seats)
        if player_is_locked(seat.player.kickoff, decision_time)
    ]
    open_index = [
        index
        for index, seat in enumerate(seats)
        if index not in set(locked_index)
    ]
    used_locked = {player_key(seats[index].player) for index in locked_index}
    candidates = [
        _candidates_for_seat(seats[index], pool, decision_time, used_locked)
        for index in open_index
    ]
    if open_index and any(not options for options in candidates):
        return OracleLineupResult(tuple(seats))

    locked_salary = sum(seats[index].player.salary for index in locked_index)
    locked_points = sum(seats[index].player.fd_points for index in locked_index)
    best = _search_open_seats(
        seats,
        open_index,
        candidates,
        used_locked,
        locked_salary,
        locked_points,
        salary_cap,
        salary_floor,
    )
    if best is None:
        return OracleLineupResult(tuple(seats))

    chosen = list(seats)
    for index, player in zip(open_index, best):
        chosen[index] = Seat(seats[index].slot, player)
    return OracleLineupResult(tuple(chosen))


def replay_hindsight(
    seats: Sequence[Seat],
    pool: Sequence[OraclePlayer],
    decision_times: Sequence[datetime],
    *,
    salary_cap: int = SALARY_CAP,
    salary_floor: int = SALARY_FLOOR,
) -> OracleLineupResult:
    """Apply each lock wave in order. Later waves see the earlier swaps."""

    current = tuple(seats)
    for decision_time in decision_times:
        current = apply_hindsight_oracle(
            current,
            pool,
            decision_time,
            salary_cap=salary_cap,
            salary_floor=salary_floor,
        ).seats
    return OracleLineupResult(current)


def lineup_points(seats: Sequence[Seat]) -> float:
    """Return the sum of final FanDuel points for one lineup."""

    return float(sum(seat.player.fd_points for seat in seats))


def count_seat_swaps(before: Sequence[Seat], after: Sequence[Seat]) -> int:
    """Return how many seats show a different player name."""

    return sum(
        normalize_person_name(left.player.name) != normalize_person_name(right.player.name)
        for left, right in zip(before, after)
    )


def measure_default_slate() -> MeasureResult:
    """Replay the 2026 week 3 hold book and return the hindsight ceiling."""

    return measure_slate(
        lineups_path=DEFAULT_LINEUPS,
        salary_path=DEFAULT_SALARY,
        scratch_path=DEFAULT_SCRATCH,
        schedule_path=DEFAULT_SCHEDULE,
        roster_path=DEFAULT_ROSTER,
    )


def measure_slate(
    *,
    lineups_path: Path,
    salary_path: Path,
    scratch_path: Path,
    schedule_path: Path,
    roster_path: Path,
    season: int = SEASON,
    week: int = WEEK,
) -> MeasureResult:
    """Score one book with the hindsight oracle. Missing joins return NO_EVIDENCE."""

    missing = [
        str(path)
        for path in (lineups_path, salary_path, scratch_path, schedule_path, roster_path)
        if not path.is_file()
    ]
    if missing:
        return _no_evidence("Missing file: " + ", ".join(missing))

    try:
        pbp = load_season_pbp(season)
    except FileNotFoundError as exc:
        return _no_evidence(str(exc))

    actuals = actual_week_fantasy_points(pbp, season, week)
    if actuals.empty:
        return _no_evidence("The nflverse loader returned no week points.")

    kickoffs = load_sunday_kickoffs(schedule_path, season, week)
    if not kickoffs:
        return _no_evidence("The schedule has no Sunday afternoon kickoffs.")

    games = _teams_with_games(pbp, season, week)
    if not set(kickoffs).issubset(games):
        absent = sorted(set(kickoffs) - games)
        return _no_evidence(
            "Sunday games are missing from the play cache: " + ", ".join(absent)
        )

    points = _points_lookup(actuals, roster_path, games)
    scratch = load_scratch_names(scratch_path)
    pool, unresolved = build_pool(salary_path, season, week, kickoffs, points, scratch)
    if unresolved:
        return _no_evidence(
            "These afternoon players have no joined points: " + ", ".join(unresolved)
        )

    try:
        books = load_lineup_seats(lineups_path, pool)
    except ValueError as exc:
        return _no_evidence(str(exc))

    sunday = next(iter(kickoffs.values())).date()
    decisions = decision_times(sunday)
    scores: list[LineupScore] = []
    for index, seats in enumerate(books, start=1):
        oracle = replay_hindsight(seats, pool, decisions)
        changes = _change_lines(seats, oracle.seats)
        scores.append(
            LineupScore(
                index=index,
                held_points=lineup_points(seats),
                oracle_points=lineup_points(oracle.seats),
                swaps=count_seat_swaps(seats, oracle.seats),
                changes=tuple(changes),
            )
        )

    points_gained = sum(row.oracle_points - row.held_points for row in scores)
    swaps_changed = sum(row.swaps for row in scores)
    return MeasureResult(
        status="ok",
        points_gained=float(points_gained),
        swaps_changed=int(swaps_changed),
        lineups=tuple(scores),
        detail="",
    )


def decision_times(slate_day: date) -> tuple[datetime, ...]:
    """Return the Sunday afternoon decision times for one slate date."""

    return tuple(datetime.combine(slate_day, clock) for clock in DECISION_CLOCKS)


def load_sunday_kickoffs(schedule_path: Path, season: int, week: int) -> dict[str, datetime]:
    """Map each Sunday team to its kickoff. Thursday, Saturday, and Monday stay out."""

    frame = pd.read_parquet(schedule_path)
    kickoffs: dict[str, datetime] = {}
    for row in frame.itertuples(index=False):
        if int(getattr(row, "season", season)) != season:
            continue
        if int(getattr(row, "week", week)) != week:
            continue
        if str(getattr(row, "weekday", "")).strip().lower() != "sunday":
            continue
        clock = _parse_clock(getattr(row, "gametime", None))
        if clock is None:
            away = str(getattr(row, "away_team", "") or "").strip()
            home = str(getattr(row, "home_team", "") or "").strip()
            raise ValueError(f"Sunday game {away}@{home} has no parsable gametime")
        game_day = _parse_day(getattr(row, "gameday", None))
        if game_day is None:
            continue
        kickoff = datetime.combine(game_day, clock)
        for team in (getattr(row, "away_team", ""), getattr(row, "home_team", "")):
            abbr = normalize_team_abbr(str(team))
            if abbr:
                kickoffs[abbr] = kickoff
    return kickoffs


def load_scratch_names(scratch_path: Path) -> set[str]:
    """Return normalized names from the scratch file."""

    names: set[str] = set()
    with scratch_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = normalize_person_name(str(row.get("name") or ""))
            if name:
                names.add(name)
    return names


def build_pool(
    salary_path: Path,
    season: int,
    week: int,
    kickoffs: Mapping[str, datetime],
    points: Mapping[tuple[str, str], float],
    scratch: set[str],
) -> tuple[tuple[OraclePlayer, ...], tuple[str, ...]]:
    """Build the Sunday afternoon pool. Unresolved players at $5,000+ are listed."""

    rows = parse_salary_csv(salary_path, season, week, site="fanduel")
    pool: list[OraclePlayer] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    for row in rows:
        name = str(row.get("player_name") or row.get("name") or "").strip()
        team = normalize_team_abbr(str(row.get("team") or ""))
        kickoff = kickoffs.get(team)
        if not name or kickoff is None:
            continue
        position = canonical_position(str(row.get("fd_position") or ""))
        salary = _as_int(row.get("fd_salary"))
        if salary <= 0 or position not in {"QB", "RB", "WR", "TE", "DEF"}:
            continue
        lookup = ("__dst__", team) if position == "DEF" else (normalize_person_name(name), team)
        if lookup not in points:
            if salary >= 5_000:
                unresolved.append(f"{name} ({team}, ${salary})")
            continue
        identity = f"{lookup[0]}|{team}|{position}"
        if identity in seen:
            continue
        seen.add(identity)
        pool.append(
            OraclePlayer(
                name=name,
                team=team,
                position=position,
                salary=salary,
                kickoff=kickoff,
                fd_points=float(points[lookup]),
                scratched=normalize_person_name(name) in scratch,
            )
        )
    return tuple(pool), tuple(unresolved)


def load_lineup_seats(
    lineups_path: Path,
    pool: Sequence[OraclePlayer],
) -> tuple[tuple[Seat, ...], ...]:
    """Read the hold book. Raise ValueError when a name is missing or ambiguous."""

    by_name: dict[str, list[OraclePlayer]] = {}
    for player in pool:
        by_name.setdefault(normalize_person_name(player.name), []).append(player)

    books: list[tuple[Seat, ...]] = []
    with lineups_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("The lineup file is empty.") from exc
        if tuple(header[: len(LINEUP_SLOTS)]) != LINEUP_SLOTS:
            raise ValueError(f"Unexpected lineup header: {header}")
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            seats: list[Seat] = []
            for slot, cell in zip(LINEUP_SLOTS, row):
                name = cell.strip()
                matches = by_name.get(normalize_person_name(name), [])
                legal = [player for player in matches if slot_allows(slot, player.position)]
                if len(legal) != 1:
                    raise ValueError(f"Lineup name did not join to one pool player: {name}")
                seats.append(Seat(slot, legal[0]))
            books.append(tuple(seats))
    if len(books) != 4:
        raise ValueError(f"Expected 4 lineups, found {len(books)}.")
    return tuple(books)


def render_report(result: MeasureResult) -> str:
    """Return the hindsight measurement brief."""

    lines = [
        "# K280 measure",
        "",
        "hindsight_oracle=true",
        "live_information_only=false",
        "",
        "This replay uses the final FanDuel stat line.",
        "The number below is hindsight.",
        "The hold book is runs/2026_week_3/lineups.csv.",
        "The scored book keeps Adonai Mitchell in the two WR seats.",
        "This measurement scores that file.",
        "No contest was entered.",
        "",
    ]
    if result.status != "ok" or result.points_gained is None or result.swaps_changed is None:
        lines.extend(
            [
                "points_gained_hindsight: NO_EVIDENCE",
                "swaps_changed: NO_EVIDENCE",
                "",
                "STOP",
                "The points did not join. Do not build a particle filter.",
                result.detail,
                "",
            ]
        )
        return "\n".join(line for line in lines if line is not None).rstrip() + "\n"

    lines.extend(
        [
            f"points_gained_hindsight: {result.points_gained:.2f}",
            f"swaps_changed: {result.swaps_changed}",
            "",
        ]
    )
    if result.points_gained < STOP_POINTS or result.swaps_changed < STOP_SWAPS:
        lines.extend(
            [
                "STOP",
                "The hindsight gain is under 8.0, or fewer than 2 seats change.",
                "Do not build a particle filter.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "The hindsight gain is at least 8.0 and at least 2 seats change.",
                "A filter must beat this hindsight ceiling on a later slate before it is worth building.",
                "The ceiling is not a target to match.",
                "",
            ]
        )

    lines.append("Lock rule: a player is locked when kickoff is at or before the decision time.")
    lines.append("Decision times are 1:00pm ET, 4:05pm ET, and 4:25pm ET.")
    lines.append("Thursday, Sunday night, and Monday games are out of this replay.")
    lines.append("Salary must stay at or under $60,000 and at or above $58,500.")
    lines.append("A seat can lose points when that salary funds a larger gain.")
    lines.append("")
    for row in result.lineups:
        lines.append(
            f"Lineup {row.index}: held {row.held_points:.2f}, "
            f"hindsight oracle {row.oracle_points:.2f}, seats changed {row.swaps}."
        )
        if row.changes:
            lines.extend(row.changes)
        else:
            lines.append("No seat changed.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(text: str, path: Path = DEFAULT_REPORT) -> Path:
    """Write the measurement brief. Keep an existing permutation section."""

    path.parent.mkdir(parents=True, exist_ok=True)
    heading = "## Permutation test"
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if heading in existing:
            text = text.rstrip() + "\n\n" + heading + existing.split(heading, 1)[1]
            if not text.endswith("\n"):
                text += "\n"
    path.write_text(text, encoding="utf-8")
    return path


def main() -> int:
    """Replay the week 3 book and write the measurement brief."""

    result = measure_default_slate()
    text = render_report(result)
    path = write_report(text)
    print(text, end="")
    print(f"Wrote {path}")
    return 0


def _candidates_for_seat(
    seat: Seat,
    pool: Sequence[OraclePlayer],
    decision_time: datetime,
    used_locked: set[str],
) -> list[OraclePlayer]:
    found: list[OraclePlayer] = []
    seen: set[str] = set()
    for player in pool:
        if player_is_locked(player.kickoff, decision_time):
            continue
        key = player_key(player)
        if key in used_locked or key in seen:
            continue
        if player.scratched and key != player_key(seat.player):
            continue
        if not slot_allows(seat.slot, player.position):
            continue
        seen.add(key)
        found.append(player)
    incumbent = seat.player
    incumbent_key = player_key(incumbent)
    if (
        incumbent_key not in seen
        and not player_is_locked(incumbent.kickoff, decision_time)
        and slot_allows(seat.slot, incumbent.position)
    ):
        found.append(incumbent)
    found.sort(key=lambda player: (-player.fd_points, player.salary, player.name))
    return found


def _search_open_seats(
    seats: Sequence[Seat],
    open_index: Sequence[int],
    candidates: Sequence[Sequence[OraclePlayer]],
    used_locked: set[str],
    locked_salary: int,
    locked_points: float,
    salary_cap: int,
    salary_floor: int,
) -> tuple[OraclePlayer, ...] | None:
    best_points = -1.0
    best_changes = 10**9
    best_names: tuple[str, ...] = ()
    best_players: tuple[OraclePlayer, ...] | None = None
    chosen: list[OraclePlayer] = []
    used = set(used_locked)

    def consider() -> None:
        nonlocal best_points, best_changes, best_names, best_players
        points = locked_points + sum(player.fd_points for player in chosen)
        changes = sum(
            normalize_person_name(player.name)
            != normalize_person_name(seats[open_index[index]].player.name)
            for index, player in enumerate(chosen)
        )
        names = tuple(player.name for player in chosen)
        better_points = points > best_points + 1e-9
        same_points = abs(points - best_points) <= 1e-9
        if best_players is None or better_points or (same_points and changes < best_changes) or (
            same_points and changes == best_changes and names < best_names
        ):
            best_points = points
            best_changes = changes
            best_names = names
            best_players = tuple(chosen)

    def rec(seat_number: int, salary: int) -> None:
        if salary > salary_cap:
            return
        if seat_number == len(open_index):
            if salary >= salary_floor:
                consider()
            return
        optimistic = locked_points + sum(player.fd_points for player in chosen)
        for later in range(seat_number, len(open_index)):
            if candidates[later]:
                optimistic += candidates[later][0].fd_points
        if best_players is not None and optimistic < best_points - 1e-9:
            return
        for player in candidates[seat_number]:
            key = player_key(player)
            if key in used:
                continue
            next_salary = salary + player.salary
            if next_salary > salary_cap:
                continue
            used.add(key)
            chosen.append(player)
            rec(seat_number + 1, next_salary)
            chosen.pop()
            used.remove(key)

    rec(0, locked_salary)
    return best_players


def _points_lookup(
    actuals: pd.DataFrame,
    roster_path: Path,
    games: set[str],
) -> dict[tuple[str, str], float]:
    """Map (normalized name, team) and ('__dst__', team) to final FanDuel points."""

    roster = pd.read_parquet(roster_path)
    if "gsis_id" not in roster.columns or "full_name" not in roster.columns:
        roster_index: dict[tuple[str, str], str] = {}
    else:
        roster = roster.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id")
        roster_index = {}
        for row in roster.itertuples(index=False):
            name = normalize_person_name(str(getattr(row, "full_name", "") or ""))
            team = normalize_team_abbr(str(getattr(row, "team", "") or ""))
            gsis = str(getattr(row, "gsis_id", "") or "").strip()
            if name and team and gsis:
                roster_index[(name, team)] = gsis

    stat_by_id: dict[str, float] = {}
    points: dict[tuple[str, str], float] = {}
    for row in actuals.itertuples(index=False):
        position = canonical_position(str(getattr(row, "position", "") or ""))
        team = normalize_team_abbr(str(getattr(row, "team", "") or ""))
        fd_actual = float(getattr(row, "fd_actual"))
        if position == "DEF" and team:
            points[("__dst__", team)] = fd_actual
            continue
        player_id = str(getattr(row, "player_id", "") or "").strip()
        if player_id:
            stat_by_id[player_id] = fd_actual

    for (name, team), gsis in roster_index.items():
        if team not in games:
            continue
        if gsis in stat_by_id:
            points[(name, team)] = stat_by_id[gsis]
        elif (name, team) not in points:
            # The game is in the cache and the player has no counting stats.
            points[(name, team)] = 0.0
    return points


def _teams_with_games(pbp: pd.DataFrame, season: int, week: int) -> set[str]:
    frame = pbp
    if "week" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["week"], errors="coerce") == week]
    if "season" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["season"], errors="coerce") == season]
    teams: set[str] = set()
    for column in ("home_team", "away_team"):
        if column not in frame.columns:
            continue
        teams.update(
            normalize_team_abbr(str(value))
            for value in frame[column].dropna().astype(str)
            if normalize_team_abbr(str(value))
        )
    return teams


def _change_lines(before: Sequence[Seat], after: Sequence[Seat]) -> list[str]:
    lines: list[str] = []
    for left, right in zip(before, after):
        if normalize_person_name(left.player.name) == normalize_person_name(right.player.name):
            continue
        lines.append(
            f"  {left.slot}: {left.player.name} ({left.player.fd_points:.2f}) -> "
            f"{right.player.name} ({right.player.fd_points:.2f}). Hindsight."
        )
    return lines


def _no_evidence(detail: str) -> MeasureResult:
    return MeasureResult(
        status="NO_EVIDENCE",
        points_gained=None,
        swaps_changed=None,
        lineups=(),
        detail=detail,
    )


def _parse_clock(value: object) -> time | None:
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    text = str(value or "").strip()
    if not text or text.lower() == "nat":
        return None
    hour_text, _, minute_text = text.partition(":")
    if not hour_text.isdigit() or not minute_text[:2].isdigit():
        return None
    return time(int(hour_text), int(minute_text[:2]))


def _parse_day(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text or text.lower() == "nat":
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _as_int(value: object) -> int:
    text = str(value or "").replace("$", "").replace(",", "").strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
