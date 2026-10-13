"""Late-swap upside measured under a no-leak replay.

The leak in this domain is one field: ``fd_actual``, a player's final FanDuel
stat line. It becomes observable only at the end of that player's game. A swap
decided with ``fd_actual`` in hand is hindsight, not a strategy.

This module never lets a swap decision read ``fd_actual``. It scores unlocked
seats with the pre-game ``fd_projection`` and locks every seat whose kickoff is
at or before the decision time. It then reports three totals on the same book:

- ``held`` — the book as filed.
- ``leak_free`` — re-optimized with only information available at the decision.
- ``hindsight_ceiling`` — the oracle in ``late_swap_oracle``, which reads
  ``fd_actual`` and is therefore unreachable by any live strategy.

It also counts the unlocked players that had live data at a decision time. That
count is the load-bearing number: if it is zero, the live-update premise has no
live signal to work with on this slate.

This module does not build a particle filter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from ceminidfs.config import PROJECT_ROOT
from ceminidfs.data.stadiums import normalize_team_abbr
from ceminidfs.pipeline.late_swap_oracle import (
    DEFAULT_LINEUPS,
    DEFAULT_ROSTER,
    DEFAULT_SALARY,
    DEFAULT_SCRATCH,
    DEFAULT_SCHEDULE,
    OraclePlayer,
    Seat,
    apply_hindsight_oracle,
    build_pool,
    canonical_position,
    decision_times,
    load_lineup_seats,
    load_scratch_names,
    load_sunday_kickoffs,
    normalize_person_name,
    player_is_locked,
    player_key,
    _points_lookup,
    _teams_with_games,
)
from ceminidfs.pipeline.backtest import actual_week_fantasy_points, load_season_pbp

SEASON = 2026
WEEK = 3
SALARY_CAP = 60_000
SALARY_FLOOR = 58_500
STOP_POINTS = 8.0
STOP_SWAPS = 2

DEFAULT_PROJECTIONS = PROJECT_ROOT / "runs" / "2026_week_3" / "canonical_projections_2026_w3.csv"
DEFAULT_REPORT = PROJECT_ROOT / "briefs" / "2026-10-03_k280-measure.md"

# When each decision input becomes observable. The replay may read a field only
# at or after its available instant. "game_start" means the field needs plays,
# which exist only once the game has kicked off.
FIELD_AVAILABILITY: Mapping[str, str] = {
    "kickoff": "pre_game",
    "fd_projection": "pre_game",
    "live_play_stats": "game_start",
    "fd_actual": "game_end",
}


@dataclass(frozen=True)
class WaveAudit:
    """One decision wave: what it could see, and what the leak-free swap gained."""

    decision_time: datetime
    locked_players: int
    unlocked_players: int
    unlocked_with_live_data: int
    leak_free_gain: float
    swaps: int


@dataclass(frozen=True)
class ReplayResult:
    """Held, leak-free, and hindsight totals for one book."""

    status: str
    held_points: float | None
    leak_free_points: float | None
    hindsight_points: float | None
    leak_free_gain: float | None
    foresight_share: float | None
    swaps_changed: int | None
    waves: tuple[WaveAudit, ...]
    detail: str
    blank_projections: int = 0
    live_information_only: bool = True


def assert_no_future(field: str, observed_at: datetime, decision_time: datetime) -> None:
    """Raise when a field is used before the instant it becomes observable."""

    if field not in FIELD_AVAILABILITY:
        raise ValueError(f"Unknown field: {field}")
    if observed_at > decision_time:
        raise ValueError(
            f"Leak: field '{field}' observed at {observed_at.isoformat()} "
            f"is after decision time {decision_time.isoformat()}"
        )


def audit_decision_inputs(
    pool: Sequence[OraclePlayer],
    scored_pool: Sequence[OraclePlayer],
    decision_time: datetime,
    pre_game: datetime,
) -> None:
    """Raise when a swap decision could read a field that is not yet observable.

    Two checks run here so the claim is enforced, not only asserted:

    - The decision pool must hold freshly built players. If any decision-pool
      player IS a real-points player, the ``fd_actual`` field would reach the
      optimizer. A refactor that reuses the real pool trips this check.
    - The pre-game fields must be observable at the decision time.
    """

    real_ids = {id(player) for player in pool}
    if any(id(player) in real_ids for player in scored_pool):
        raise ValueError("Leak guard: a decision-pool player is the real-points player.")
    assert_no_future("kickoff", pre_game, decision_time)
    assert_no_future("fd_projection", pre_game, decision_time)


def live_plays_available(player: OraclePlayer, decision_time: datetime) -> bool:
    """Return True when the player's game has kicked off by the decision time.

    Live drive, snap, and target counts need plays. Plays exist only after the
    kickoff. A field the game has not produced cannot be observed.
    """

    return player.kickoff <= decision_time


def swappable_with_live_data(pool: Sequence[OraclePlayer], decision_time: datetime) -> int:
    """Count unlocked players that also have live data at this decision time.

    A player is swappable when their game has not kicked off (kickoff > time).
    A player has live data when their game has kicked off (kickoff <= time).
    The two sets are disjoint, so this count is zero by construction. The replay
    measures it instead of assuming it.
    """

    return sum(
        1
        for player in pool
        if (not player_is_locked(player.kickoff, decision_time))
        and live_plays_available(player, decision_time)
    )


def load_projection_map(path: Path) -> dict[tuple[str, str], float]:
    """Map (normalized name, team) and ('__dst__', team) to the pre-game projection."""

    frame = pd.read_csv(path)
    found: dict[tuple[str, str], float] = {}
    for row in frame.itertuples(index=False):
        team = normalize_team_abbr(str(getattr(row, "team", "") or ""))
        if not team:
            continue
        position = canonical_position(str(getattr(row, "fd_position", "") or ""))
        name = str(getattr(row, "player_name", "") or getattr(row, "name", "") or "")
        projection = pd.to_numeric(getattr(row, "fd_projection", None), errors="coerce")
        if pd.isna(projection):
            continue
        key = ("__dst__", team) if position == "DEF" else (normalize_person_name(name), team)
        found.setdefault(key, float(projection))
    return found


def projection_key(player: OraclePlayer) -> tuple[str, str]:
    """Return the projection-map key for one player."""

    if player.position == "DEF":
        return ("__dst__", player.team)
    return (normalize_person_name(player.name), player.team)


def pool_on_projections(
    pool: Sequence[OraclePlayer],
    projections: Mapping[tuple[str, str], float],
) -> tuple[tuple[OraclePlayer, ...], int]:
    """Return the pool scored by its pre-game projection. Count blank projections.

    The returned players carry the projection in the ``fd_points`` slot. The
    optimizer inside ``late_swap_oracle`` reads only that slot, so it cannot see
    ``fd_actual``. This is the leak barrier.

    A player the projection build left blank (injured or inactive) scores 0.0.
    That is the pre-game belief and it carries no future information.
    """

    scored: list[OraclePlayer] = []
    missing = 0
    for player in pool:
        value = projections.get(projection_key(player))
        if value is None:
            missing += 1
            value = 0.0
        scored.append(
            OraclePlayer(
                name=player.name,
                team=player.team,
                position=player.position,
                salary=player.salary,
                kickoff=player.kickoff,
                fd_points=value,
                scratched=player.scratched,
            )
        )
    return tuple(scored), missing


def replay_leak_free(
    seats: Sequence[Seat],
    pool: Sequence[OraclePlayer],
    decision_times: Sequence[datetime],
    *,
    salary_cap: int = SALARY_CAP,
    salary_floor: int = SALARY_FLOOR,
) -> tuple[Seat, ...]:
    """Re-optimize unlocked seats at each wave using only pre-game projections."""

    current = tuple(seats)
    for decision_time in decision_times:
        current = apply_hindsight_oracle(
            current,
            pool,
            decision_time,
            salary_cap=salary_cap,
            salary_floor=salary_floor,
        ).seats
    return current


def measure_slate(
    *,
    lineups_path: Path = DEFAULT_LINEUPS,
    salary_path: Path = DEFAULT_SALARY,
    scratch_path: Path = DEFAULT_SCRATCH,
    schedule_path: Path = DEFAULT_SCHEDULE,
    roster_path: Path = DEFAULT_ROSTER,
    projections_path: Path = DEFAULT_PROJECTIONS,
    season: int = SEASON,
    week: int = WEEK,
) -> ReplayResult:
    """Score the book three ways and audit each decision wave for live data."""

    missing = [
        str(path)
        for path in (lineups_path, salary_path, scratch_path, schedule_path, roster_path, projections_path)
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
        return _no_evidence("Sunday games are missing from the play cache: " + ", ".join(absent))

    points = _points_lookup(actuals, roster_path, games)
    scratch = load_scratch_names(scratch_path)
    pool, unresolved = build_pool(salary_path, season, week, kickoffs, points, scratch)
    if unresolved:
        return _no_evidence("These afternoon players have no joined points: " + ", ".join(unresolved))

    try:
        books = load_lineup_seats(lineups_path, pool)
    except ValueError as exc:
        return _no_evidence(str(exc))

    projections = load_projection_map(projections_path)
    scored_pool, blank_projections = pool_on_projections(pool, projections)

    sunday = next(iter(kickoffs.values())).date()
    decisions = decision_times(sunday)

    pre_game = datetime.combine(sunday, time(0, 0))
    for decision_time in decisions:
        audit_decision_inputs(pool, scored_pool, decision_time, pre_game)

    held_points = 0.0
    leak_free_points = 0.0
    hindsight_points = 0.0
    wave_gain = [0.0] * len(decisions)
    wave_swaps = [0] * len(decisions)
    for seats in books:
        scored_seats = _reseat(seats, scored_pool)
        held_points += sum(seat.player.fd_points for seat in seats)
        current_scored = scored_seats
        current_real = tuple(seat.player for seat in seats)
        for index, decision_time in enumerate(decisions):
            next_scored = apply_hindsight_oracle(current_scored, scored_pool, decision_time).seats
            next_real = _players_for(next_scored, pool)
            wave_gain[index] += sum(player.fd_points for player in next_real) - sum(
                player.fd_points for player in current_real
            )
            wave_swaps[index] += sum(
                normalize_person_name(before.name) != normalize_person_name(after.name)
                for before, after in zip(current_real, next_real)
            )
            current_scored = next_scored
            current_real = next_real
        leak_free_points += sum(player.fd_points for player in current_real)
        hindsight_points += sum(
            player.fd_points for player in measure_book_hindsight(seats, pool, decisions)
        )
    swaps_changed = sum(wave_swaps)

    waves = tuple(
        WaveAudit(
            decision_time=decision_time,
            locked_players=sum(1 for player in pool if player_is_locked(player.kickoff, decision_time)),
            unlocked_players=sum(1 for player in pool if not player_is_locked(player.kickoff, decision_time)),
            unlocked_with_live_data=swappable_with_live_data(pool, decision_time),
            leak_free_gain=wave_gain[index],
            swaps=wave_swaps[index],
        )
        for index, decision_time in enumerate(decisions)
    )

    leak_free_gain = leak_free_points - held_points
    ceiling_gap = hindsight_points - held_points
    foresight_share = (hindsight_points - leak_free_points) / ceiling_gap if ceiling_gap else None

    return ReplayResult(
        status="ok",
        held_points=held_points,
        leak_free_points=leak_free_points,
        hindsight_points=hindsight_points,
        leak_free_gain=leak_free_gain,
        foresight_share=foresight_share,
        swaps_changed=swaps_changed,
        waves=waves,
        detail="",
        blank_projections=blank_projections,
    )


def measure_book_hindsight(
    seats: Sequence[Seat],
    pool: Sequence[OraclePlayer],
    decisions: Sequence[datetime],
) -> tuple[OraclePlayer, ...]:
    """Replay the book with the hindsight oracle. Reads fd_actual by design."""

    current = tuple(seats)
    for decision_time in decisions:
        current = apply_hindsight_oracle(current, pool, decision_time).seats
    return tuple(seat.player for seat in current)


def render_report(result: ReplayResult) -> str:
    """Return the leak-free replay block."""

    lines = ["## Leak-free replay", ""]
    if result.status != "ok" or result.leak_free_gain is None or result.swaps_changed is None:
        lines.extend(
            [
                "status: NO_EVIDENCE",
                "leak_free_gain: NO_EVIDENCE",
                "swappable_players_with_live_data: NO_EVIDENCE",
                "",
                result.detail,
                "",
            ]
        )
        return "\n".join(lines)

    live_data_total = sum(wave.unlocked_with_live_data for wave in result.waves)
    live_wave_gain = sum(wave.leak_free_gain for wave in result.waves[1:])
    live_wave_swaps = sum(wave.swaps for wave in result.waves[1:])
    foresight = "n/a" if result.foresight_share is None else f"{result.foresight_share:.3f}"
    lines.extend(
        [
            "live_information_only: true",
            "",
            "This replay lets a swap decision read only information available at",
            "the decision time. The field fd_actual is a leak and is never read.",
            "",
            f"held_points: {result.held_points:.2f}",
            f"leak_free_points: {result.leak_free_points:.2f}",
            f"leak_free_gain: {result.leak_free_gain:.2f}",
            f"swaps_changed: {result.swaps_changed}",
            f"live_wave_gain: {live_wave_gain:.2f}",
            f"live_wave_swaps: {live_wave_swaps}",
            f"hindsight_ceiling_points: {result.hindsight_points:.2f}",
            f"foresight_share_of_ceiling: {foresight}",
            f"swappable_players_with_live_data: {live_data_total}",
            f"blank_projections: {result.blank_projections}",
            "",
            "Decision waves (gain and swaps use only data available at that time):",
        ]
    )
    for wave in result.waves:
        lines.append(
            f"  {wave.decision_time.strftime('%H:%M')}: locked {wave.locked_players}, "
            f"unlocked {wave.unlocked_players}, "
            f"unlocked with live data {wave.unlocked_with_live_data}, "
            f"gain {wave.leak_free_gain:.2f}, swaps {wave.swaps}"
        )
    lines.append("")

    if live_wave_gain < STOP_POINTS or live_wave_swaps < STOP_SWAPS:
        lines.extend(
            [
                "STOP",
                "The live decision waves gain under 8.0 points, or change fewer than 2 seats.",
                "At each live wave, the unlocked players had no live data.",
                "The late-swap lane carries no live edge on this slate.",
                "Do not build a particle filter.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "The live decision waves clear both gates.",
                "A filter must beat the live-wave result before it is worth building.",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_report(text: str, path: Path = DEFAULT_REPORT) -> Path:
    """Append the leak-free block. Keep the other sections in place."""

    path.parent.mkdir(parents=True, exist_ok=True)
    heading = "## Leak-free replay"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if heading in existing:
        existing = existing.split(heading)[0].rstrip() + "\n\n"
    elif existing:
        existing = existing.rstrip() + "\n\n"
    path.write_text(existing + text, encoding="utf-8")
    return path


def main() -> int:
    """Run the leak-free replay and write the report block."""

    result = measure_slate()
    text = render_report(result)
    path = write_report(text)
    print(text, end="")
    print(f"Wrote {path}")
    return 0


def _reseat(seats: Sequence[Seat], scored_pool: Sequence[OraclePlayer]) -> tuple[Seat, ...]:
    """Map each book seat onto the projection-scored pool by identity.

    Raise when a seat has no scored match. A silent fall-back to the original
    seat would carry fd_actual into the leak-free path. Fail loud instead.
    """

    by_key = {player_key(player): player for player in scored_pool}
    out: list[Seat] = []
    for seat in seats:
        key = player_key(seat.player)
        if key not in by_key:
            raise ValueError(f"Leak guard: seat {seat.player.name} has no projection-scored match.")
        out.append(Seat(seat.slot, by_key[key]))
    return tuple(out)


def _players_for(seats: Sequence[Seat], pool: Sequence[OraclePlayer]) -> tuple[OraclePlayer, ...]:
    """Map scored seats back to real-points pool players by identity."""

    by_key = {player_key(player): player for player in pool}
    return tuple(by_key[player_key(seat.player)] for seat in seats)


def _no_evidence(detail: str) -> ReplayResult:
    return ReplayResult(
        status="NO_EVIDENCE",
        held_points=None,
        leak_free_points=None,
        hindsight_points=None,
        leak_free_gain=None,
        foresight_share=None,
        swaps_changed=None,
        waves=(),
        detail=detail,
    )


if __name__ == "__main__":
    raise SystemExit(main())
