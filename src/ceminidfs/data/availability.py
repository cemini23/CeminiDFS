"""Player availability from salary exports and cached nflverse injury reports."""

from __future__ import annotations

import csv
import math
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import pandas as pd

from ceminidfs.data.fetch import week_cache_dir

UNAVAILABLE_STATUSES = frozenset(
    {
        "O",
        "OUT",
        "IR",
        "PUP",
        "NFI",
        "NA",
        "EXEMPT",
        "COMMISSIONER EXEMPT",
        "SUSPENDED",
        "DOUBTFUL",
        "D",
        "DOUBTFUL TO PLAY",
        "INACTIVE",
    }
)

PLAYER_ID_COLUMNS = ("gsis_id", "player_id", "gsis_it_id")
STATUS_COLUMNS = (
    "report_status",
    "game_status",
    "injury_status",
    "status",
    "practice_status",
)
WEEK_COLUMNS = ("week", "week_num")


def normalize_injury_status(value: Any) -> str:
    """Return uppercase injury token from FanDuel or nflverse labels."""

    token = str(value or "").strip().upper()
    if not token:
        return ""
    if token in UNAVAILABLE_STATUSES:
        return token
    for prefix in ("OUT", "DOUBTFUL", "IR", "PUP", "EXEMPT", "SUSPENDED"):
        if token.startswith(prefix):
            return prefix
    if "EXEMPT" in token:
        return "EXEMPT"
    if "SUSPENDED" in token:
        return "SUSPENDED"
    return token


def is_unavailable_status(status: Any) -> bool:
    """True when a player should be excluded from the usage projection pool."""

    token = normalize_injury_status(status)
    if not token:
        return False
    if token in {"O", "OUT", "IR", "PUP", "NFI", "NA", "D", "EXEMPT", "SUSPENDED"}:
        return True
    if token in UNAVAILABLE_STATUSES:
        return True
    return (
        token.startswith("DOUBTFUL")
        or token.startswith("EXEMPT")
        or token.startswith("SUSPENDED")
        or "EXEMPT" in token
    )


def unavailable_player_ids_from_salary_rows(rows: list[Mapping[str, Any]]) -> set[str]:
    """Collect player ids flagged Out/Doubtful on a salary export."""

    excluded: set[str] = set()
    for row in rows:
        status = row.get("injury_status") or row.get("Injury Indicator") or row.get("injury")
        if not is_unavailable_status(status):
            continue
        player_id = str(
            row.get("fd_id")
            or row.get("dk_id")
            or row.get("player_key")
            or row.get("player_id")
            or row.get("Id")
            or ""
        ).strip()
        if player_id:
            excluded.add(player_id)
    return excluded


def unavailable_player_ids_from_week_cache(season: int, week: int) -> set[str]:
    """Collect unavailable player ids from cached injuries.parquet when present."""

    path = week_cache_dir(season, week) / "injuries.parquet"
    if not path.is_file():
        return set()

    try:
        frame = pd.read_parquet(path)
    except (OSError, ValueError):
        return set()

    if frame.empty:
        return set()

    week_col = _first_col(frame, WEEK_COLUMNS)
    if week_col:
        frame = frame.loc[pd.to_numeric(frame[week_col], errors="coerce") == week]

    id_col = _first_col(frame, PLAYER_ID_COLUMNS)
    status_col = _first_col(frame, STATUS_COLUMNS)
    if id_col is None or status_col is None:
        return set()

    excluded: set[str] = set()
    for _, row in frame.iterrows():
        if not is_unavailable_status(row.get(status_col)):
            continue
        player_id = str(row.get(id_col, "") or "").strip()
        if player_id:
            excluded.add(player_id)
    return excluded


def resolve_unavailable_player_ids(
    season: int,
    week: int,
    *,
    roster: pd.DataFrame | None = None,
    salary_rows: list[Mapping[str, Any]] | None = None,
    config: Mapping[str, Any] | None = None,
) -> set[str]:
    """Merge salary and cached injury exclusions for one week."""

    cfg = dict(config or {})
    if cfg.get("ignore_injuries"):
        return set()

    excluded = unavailable_player_ids_from_week_cache(season, week)
    if salary_rows:
        excluded.update(unavailable_player_ids_from_salary_rows(salary_rows))

    if roster is not None and not roster.empty and "injury_status" in roster.columns:
        for _, row in roster.iterrows():
            if is_unavailable_status(row.get("injury_status")):
                player_id = str(row.get("player_id", "") or "").strip()
                if player_id:
                    excluded.add(player_id)
    return excluded


def filter_available_roster(roster: pd.DataFrame, excluded_ids: set[str]) -> pd.DataFrame:
    """Drop unavailable players from a roster frame."""

    if roster.empty or not excluded_ids or "player_id" not in roster.columns:
        return roster
    return roster.loc[~roster["player_id"].astype(str).isin(excluded_ids)].copy()


def _first_col(df: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


# Desk hard-exclude tokens. Q / QUESTIONABLE is not in this set.
PRELOCK_HARD_STATUSES = frozenset(
    {
        "OUT",
        "O",
        "IR",
        "INACTIVE",
        "DOUBTFUL",
        "D",
        "NFI",
        "PUP",
        "SUSPENDED",
    }
)

# Internal join keys. FanDuel export Id and Name stay unchanged.
# JAC and JAX join. WSH and WAS join. LAR and LA join as LA.
JOIN_TEAM_ALIASES = {
    "JAC": "JAX",
    "WSH": "WAS",
    "LAR": "LA",
}

QUESTIONABLE_POLICIES = frozenset({"keep", "exclude"})
TEAM_EXPOSURE_CAP = 0.45
PROJECTION_COLUMNS = (
    "player_id",
    "name",
    "team",
    "pos",
    "salary",
    "proj_fd_pts",
    "ownership_proj",
    "injury_status",
    "exposure_cap_applied",
    "role_flags",
)
_LINEUP_POSITIONS = frozenset(
    {
        "QB",
        "RB",
        "WR",
        "TE",
        "FLEX",
        "DEF",
        "DST",
        "D",
        "MVP",
        "CPT",
        "UTIL",
        "SUPERFLEX",
    }
)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TRUTHY = frozenset({"1", "true", "yes", "y", "t", "x", "exclude"})
_ID_KEYS = ("id", "player_id", "fd_id", "playerid")
_NAME_KEYS = ("name", "player", "player_name", "full name")
_TEAM_KEYS = ("team", "team abbrev", "teamabbrev", "club", "tm")
_POS_KEYS = ("position", "pos", "fd_position", "roster position")
_SALARY_KEYS = ("salary", "fd_salary", "salaryflex")
_PROJ_KEYS = (
    "proj_fd_pts",
    "fppg",
    "fd_projection",
    "projection",
    "proj",
    "avgpointspergame",
    "points",
)
_OWN_KEYS = (
    "ownership_proj",
    "ownership",
    "projected ownership",
    "own%",
    "own %",
    "proj_own",
)
_INJURY_KEYS = (
    "injury indicator",
    "injury_status",
    "injury",
    "inj",
    "report_status",
    "status",
)


class PrelockExcludeError(RuntimeError):
    """A generated lineup contains a hard-excluded player."""


@dataclass
class SlatePlayer:
    """One salary-file player. ``player_id`` and ``name`` stay exact."""

    player_id: str
    name: str
    team_raw: str
    team: str
    pos: str
    salary: str
    proj_fd_pts: str
    ownership_proj: str
    fd_status: str
    scratch_status: str = ""
    effective_status: str = ""
    hard_excluded: bool = False
    exclude_reason: str = ""


@dataclass
class PrelockGate:
    """Hard-exclude set for one slate, plus the players used to build it."""

    players: list[SlatePlayer]
    banned_ids: frozenset[str]
    banned_names: frozenset[str]
    slate_date: str
    questionable_policy: str

    @property
    def hard_excluded(self) -> list[SlatePlayer]:
        return [player for player in self.players if player.hard_excluded]

    @property
    def questionable_remaining(self) -> list[SlatePlayer]:
        """Q players who stay in the pool."""

        rows = [
            player
            for player in self.players
            if not player.hard_excluded and is_questionable_status(player.effective_status)
        ]
        return sorted(
            rows,
            key=lambda player: (player.team, player.name.casefold(), player.player_id),
        )


@dataclass(frozen=True)
class _ScratchRow:
    player_id: str
    name: str
    team: str
    status: str
    explicit: bool


@dataclass(frozen=True)
class _BackupQb:
    team: str
    name: str


def is_prelock_hard_status(status: Any) -> bool:
    """True when the desk gate must remove this status."""

    token = normalize_injury_status(status)
    return bool(token) and token in PRELOCK_HARD_STATUSES


def is_questionable_status(status: Any) -> bool:
    """True for a Q tag. Q stays in the pool unless a later rule removes it."""

    token = normalize_injury_status(status)
    return token in {"Q", "QUESTIONABLE"} or token.startswith("QUESTIONABLE")


def normalize_join_team(team: Any) -> str:
    """Return the join key for a FanDuel, ESPN, or NFL team abbreviation.

    ``JAC`` becomes ``JAX``. ``WSH`` becomes ``WAS``. ``LAR`` becomes ``LA``.
    The FanDuel ``Id`` and ``Name`` are not part of this map.
    """

    token = str(team or "").strip().upper()
    return JOIN_TEAM_ALIASES.get(token, token)


def fold_person(value: Any) -> str:
    """Return a case-folded name with collapsed spaces."""

    return " ".join(str(value or "").casefold().split())


def fanduel_export_token(player: SlatePlayer) -> str:
    """Return the FanDuel upload cell. Id and Name stay exact."""

    if player.player_id and player.name:
        return f"{player.player_id}:{player.name}"
    return player.player_id or player.name


def build_prelock_gate(
    salary_csv: str | Path,
    *,
    scratch_csv: str | Path | None = None,
    qb_starters_csv: str | Path | None = None,
    exclude_players: Sequence[str] | None = None,
    questionable_policy: str = "keep",
    slate_date: str | None = None,
    lineup_path: str | Path | None = None,
) -> PrelockGate:
    """Build the hard-exclude set from the salary file and the desk files."""

    policy = str(questionable_policy or "keep").strip().lower()
    if policy not in QUESTIONABLE_POLICIES:
        raise ValueError("include-questionable-policy must be keep or exclude")

    salary_path = Path(salary_csv)
    if not salary_path.is_file():
        raise FileNotFoundError(f"Salary CSV not found: {salary_path}")

    players = _load_salary_players(salary_path)
    scratch_rows = _load_scratch_rows(scratch_csv) if scratch_csv else []
    starters, backups = _load_qb_starter_file(qb_starters_csv) if qb_starters_csv else ({}, [])
    extra_names = [str(name).strip() for name in (exclude_players or []) if str(name).strip()]

    _apply_scratch_rows(players, scratch_rows)
    _apply_backup_qbs(players, starters, backups)
    _apply_named_excludes(players, extra_names)
    if policy == "exclude":
        _apply_questionable_policy(players)

    banned_ids, banned_names = _ban_sets(players, scratch_rows, backups, starters, extra_names)
    date = infer_slate_date(
        slate_date,
        salary_path,
        scratch_csv,
        qb_starters_csv,
        lineup_path,
    )
    return PrelockGate(
        players=players,
        banned_ids=banned_ids,
        banned_names=banned_names,
        slate_date=date,
        questionable_policy=policy,
    )


def infer_slate_date(*values: Any) -> str:
    """Return the first YYYY-MM-DD token, or ``undated``."""

    for value in values:
        if not value:
            continue
        match = _DATE_RE.search(str(value))
        if match:
            return match.group(0)
    return "undated"


def format_questionable_warning(gate: PrelockGate) -> str:
    """Return the Q-player table printed before the solve."""

    rows = gate.questionable_remaining
    lines = [f"questionable players still in the pool: {len(rows)}"]
    if not rows:
        lines.append("No Q player remains in the pool.")
        return "\n".join(lines)
    lines.append("| name | team | pos | salary | injury_status |")
    lines.append("| --- | --- | --- | --- | --- |")
    for player in rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    _md(player.name),
                    _md(player.team),
                    _md(player.pos),
                    _md(player.salary),
                    _md(player.effective_status),
                )
            )
            + " |"
        )
    return "\n".join(lines)


def filter_solver_csv(source: str | Path, dest: str | Path, gate: PrelockGate) -> tuple[Path, int]:
    """Copy the solver CSV without hard-excluded rows.

    Kept rows keep every FanDuel field, including ``Id`` and ``Name``.
    When no row is dropped, return ``source`` and do not leave ``dest``.
    """

    src = Path(source)
    target = Path(dest)
    if not gate.banned_ids and not gate.banned_names:
        return src, 0

    dropped = 0
    kept: list[dict[str, str]] = []
    with src.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        lowered = _header_map(fieldnames)
        for row in reader:
            if _row_is_banned(row, lowered, gate):
                dropped += 1
                continue
            kept.append({key: row.get(key, "") for key in fieldnames})

    if dropped == 0:
        return src, 0

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(kept)
    return target, dropped


@contextmanager
def using_solver_csv(source: str | Path, gate: PrelockGate) -> Iterator[Path]:
    """Yield a solver CSV that omits hard-excluded players."""

    src = Path(source)
    if not gate.banned_ids and not gate.banned_names:
        yield src
        return
    temporary = tempfile.TemporaryDirectory(prefix="ceminidfs-prelock-")
    try:
        dest = Path(temporary.name) / src.name
        path, dropped = filter_solver_csv(src, dest, gate)
        if dropped:
            print(
                f"prelock gate: removed {dropped} hard-excluded players from the pool",
                file=sys.stderr,
            )
        yield path
    finally:
        temporary.cleanup()


def write_projections_csv(
    gate: PrelockGate,
    output_dir: str | Path,
    *,
    exposure_caps: Mapping[str, str] | None = None,
    role_flags: Mapping[str, str] | None = None,
) -> Path:
    """Write ``projections_<slate_date>.csv`` for the salary pool.

    ``exposure_caps`` and ``role_flags`` are keyed by player id. A missing key
    writes an empty cell.
    """

    destination = Path(output_dir) / f"projections_{gate.slate_date}.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    caps = exposure_caps or {}
    flags = role_flags or {}
    rows = sorted(
        gate.players,
        key=lambda player: (player.team, player.name.casefold(), player.player_id),
    )
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(PROJECTION_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for player in rows:
            writer.writerow(
                {
                    "player_id": player.player_id,
                    "name": player.name,
                    "team": player.team,
                    "pos": player.pos,
                    "salary": player.salary,
                    "proj_fd_pts": player.proj_fd_pts,
                    "ownership_proj": player.ownership_proj,
                    "injury_status": player.effective_status,
                    "exposure_cap_applied": caps.get(player.player_id, ""),
                    "role_flags": flags.get(player.player_id, ""),
                }
            )
    return destination


def read_lineup_tokens(lineup_csv: str | Path) -> list[list[str]]:
    """Return one list of seat cells for each lineup row."""

    path = Path(lineup_csv)
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header:
            return []
        indexes = [
            index
            for index, name in enumerate(header)
            if str(name or "").strip().upper() in _LINEUP_POSITIONS
        ]
        if not indexes:
            indexes = list(range(len(header)))
        lineups: list[list[str]] = []
        for row in reader:
            if not any(str(cell or "").strip() for cell in row):
                continue
            tokens = [
                str(row[index]).strip()
                for index in indexes
                if index < len(row) and str(row[index] or "").strip()
            ]
            if tokens:
                lineups.append(tokens)
        return lineups


def lineup_exclude_hits(lineup_csv: str | Path, gate: PrelockGate) -> list[str]:
    """Return one message per lineup that contains a hard-excluded player."""

    hits: list[str] = []
    for index, tokens in enumerate(read_lineup_tokens(lineup_csv), start=1):
        found: list[str] = []
        for token in tokens:
            name, ident = split_lineup_token(token)
            if ident and ident in gate.banned_ids:
                found.append(name or ident)
                continue
            folded = fold_person(name)
            if folded and folded in gate.banned_names:
                found.append(name or ident)
        if found:
            hits.append(f"lineup {index}: {', '.join(found)}")
    return hits


def split_lineup_token(cell: str) -> tuple[str, str]:
    """Return ``(name, id)`` from a lineup cell."""

    text = str(cell or "").strip()
    if ":" in text:
        left, right = text.split(":", 1)
        if any(char.isdigit() for char in left):
            return right.strip(), left.strip()
    if text.endswith(")") and "(" in text:
        name, _, rest = text.rpartition("(")
        ident = rest[:-1].strip()
        if ident:
            return name.strip(), ident
    if text and any(char.isdigit() for char in text) and " " not in text:
        return "", text
    return text, ""


def exposure_tables(
    gate: PrelockGate,
    lineup_csv: str | Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]], int]:
    """Return team rows, top-25 player rows, and the lineup count."""

    lineups = read_lineup_tokens(lineup_csv)
    count = len(lineups)
    by_id = {player.player_id: player for player in gate.players if player.player_id}
    by_name: dict[str, SlatePlayer] = {}
    name_counts: dict[str, int] = defaultdict(int)
    for player in gate.players:
        folded = fold_person(player.name)
        if folded:
            name_counts[folded] += 1
    for player in gate.players:
        folded = fold_person(player.name)
        if folded and name_counts[folded] == 1:
            by_name[folded] = player

    teams = sorted({player.team for player in gate.players if player.team})
    team_counts = {team: 0 for team in teams}
    player_counts: dict[str, int] = defaultdict(int)
    player_labels: dict[str, SlatePlayer | None] = {}
    player_display: dict[str, str] = {}

    for tokens in lineups:
        seen_teams: set[str] = set()
        seen_players: set[str] = set()
        for token in tokens:
            name, ident = split_lineup_token(token)
            player = by_id.get(ident) if ident else None
            if player is None:
                player = by_name.get(fold_person(name))
            if player is not None and player.team:
                seen_teams.add(player.team)
            if player is not None and player.player_id:
                key = player.player_id
            else:
                key = fold_person(name) or ident
            if not key:
                continue
            seen_players.add(key)
            player_labels.setdefault(key, player)
            player_display.setdefault(key, player.name if player is not None else (name or ident))
        for team in seen_teams:
            team_counts[team] = team_counts.get(team, 0) + 1
        for key in seen_players:
            player_counts[key] += 1

    team_rows: list[dict[str, str]] = []
    for team in sorted(team_counts, key=lambda item: (-team_counts[item], item)):
        hits = team_counts[team]
        pct = _pct(hits, count)
        flag = _team_flag(hits, count)
        team_rows.append(
            {
                "team": team,
                "lineups": str(hits),
                "pct": pct,
                "flag": flag,
            }
        )

    ranked = sorted(
        player_counts,
        key=lambda key: (
            -player_counts[key],
            player_display.get(key, "").casefold(),
            key,
        ),
    )
    player_rows: list[dict[str, str]] = []
    for key in ranked[:25]:
        player = player_labels.get(key)
        hits = player_counts[key]
        player_rows.append(
            {
                "name": player_display.get(key, key),
                "lineups": str(hits),
                "pct": _pct(hits, count),
                "salary": player.salary if player is not None else "",
                "proj_fd_pts": player.proj_fd_pts if player is not None else "",
                "injury_status": player.effective_status if player is not None else "",
            }
        )
    return team_rows, player_rows, count


def format_exposure_summary(gate: PrelockGate, lineup_csv: str | Path) -> str:
    """Return the stdout exposure summary."""

    team_rows, player_rows, count = exposure_tables(gate, lineup_csv)
    return _exposure_text(
        gate.slate_date,
        count,
        team_rows,
        player_rows,
        title=f"exposure summary {gate.slate_date}",
    )


def write_exposure_report(
    gate: PrelockGate,
    lineup_csv: str | Path,
    output_dir: str | Path,
    *,
    tier_rows: Sequence[Mapping[str, str]] | None = None,
    role_cliff_rows: Sequence[Mapping[str, str]] | None = None,
) -> Path:
    """Write ``exposure_report_<slate_date>.md``.

    ``tier_rows`` is the tiered-cap audit. ``role_cliff_rows`` names every
    doubtful player and every player with a role-cliff flag.
    """

    destination = Path(output_dir) / f"exposure_report_{gate.slate_date}.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    team_rows, player_rows, count = exposure_tables(gate, lineup_csv)
    body = _exposure_text(
        gate.slate_date,
        count,
        team_rows,
        player_rows,
        title=f"# Exposure report {gate.slate_date}",
        tier_rows=tier_rows or (),
        role_cliff_rows=role_cliff_rows or (),
    )
    destination.write_text(body + "\n", encoding="utf-8")
    return destination


def archive_slate_files(
    archive_dir: str | Path,
    *,
    salary_csv: str | Path,
    projections_csv: str | Path,
    lineups_csv: str | Path,
) -> list[Path]:
    """Copy the salary file, the projections file, and the lineups into one directory."""

    destination = Path(archive_dir)
    destination.mkdir(parents=True, exist_ok=True)
    projections = Path(projections_csv)
    written = [
        _copy_file(Path(salary_csv), destination / "_src_fd_sun.csv"),
        _copy_file(projections, destination / projections.name),
        _copy_file(Path(lineups_csv), destination / "_src_lineups.csv"),
    ]
    return written


def finish_lineup_outputs(
    gate: PrelockGate,
    *,
    salary_csv: str | Path,
    lineups_csv: str | Path,
    output_dir: str | Path | None = None,
    archive_dir: str | Path | None = None,
    archive_lineups_csv: str | Path | None = None,
    exposure_caps: Mapping[str, str] | None = None,
    role_flags: Mapping[str, str] | None = None,
    tier_rows: Sequence[Mapping[str, str]] | None = None,
    role_cliff_rows: Sequence[Mapping[str, str]] | None = None,
) -> tuple[Path, Path, str]:
    """Write the projection file and the exposure report. Archive when asked.

    ``archive_lineups_csv`` is the upload-ready file for the bundle. It
    defaults to ``lineups_csv``.
    """

    out_dir = Path(output_dir) if output_dir is not None else Path(lineups_csv).parent
    projections = write_projections_csv(
        gate,
        out_dir,
        exposure_caps=exposure_caps,
        role_flags=role_flags,
    )
    report = write_exposure_report(
        gate,
        lineups_csv,
        out_dir,
        tier_rows=tier_rows,
        role_cliff_rows=role_cliff_rows,
    )
    if archive_dir:
        archive_slate_files(
            archive_dir,
            salary_csv=salary_csv,
            projections_csv=projections,
            lineups_csv=archive_lineups_csv or lineups_csv,
        )
        _copy_file(report, Path(archive_dir) / report.name)
    summary = format_exposure_summary(gate, lineups_csv)
    return projections, report, summary


def assert_lineups_clean(lineup_csv: str | Path, gate: PrelockGate) -> None:
    """Raise when a lineup contains a hard-excluded player or the file is missing."""

    path = Path(lineup_csv)
    if not path.is_file():
        raise PrelockExcludeError(f"lineup file missing; fail closed: {path}")
    hits = lineup_exclude_hits(path, gate)
    if hits:
        raise PrelockExcludeError("hard-excluded player in " + "; ".join(hits))


def _load_salary_players(path: Path) -> list[SlatePlayer]:
    players: list[SlatePlayer] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"Salary CSV has no header: {path}")
        lowered = _header_map(reader.fieldnames)
        for row in reader:
            name = _player_name(row, lowered)
            player_id = _pick(row, lowered, *_ID_KEYS)
            if not name and not player_id:
                continue
            team_raw = _pick(row, lowered, *_TEAM_KEYS)
            status = normalize_injury_status(_pick(row, lowered, *_INJURY_KEYS))
            player = SlatePlayer(
                player_id=player_id,
                name=name,
                team_raw=team_raw,
                team=normalize_join_team(team_raw),
                pos=_pos_token(_pick(row, lowered, *_POS_KEYS)),
                salary=_number_text(_pick(row, lowered, *_SALARY_KEYS)),
                proj_fd_pts=_number_text(_pick(row, lowered, *_PROJ_KEYS)),
                ownership_proj=_number_text(_pick(row, lowered, *_OWN_KEYS)),
                fd_status=status,
                effective_status=status,
            )
            if is_prelock_hard_status(status):
                player.hard_excluded = True
                player.exclude_reason = "salary_status"
            players.append(player)
    return players


def _load_scratch_rows(path: str | Path) -> list[_ScratchRow]:
    scratch_path = Path(path)
    if not scratch_path.is_file():
        raise FileNotFoundError(f"Scratch CSV not found: {scratch_path}")
    rows: list[_ScratchRow] = []
    with scratch_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            raise ValueError(f"Scratch CSV has no header: {scratch_path}")
        lowered = _header_map(fieldnames)
        has_status = any(key in lowered for key in _INJURY_KEYS)
        has_exclude = any(key in lowered for key in ("exclude", "excluded", "hard_exclude"))
        name_list = not has_status and not has_exclude
        for row in reader:
            name = _player_name(row, lowered)
            player_id = _pick(row, lowered, *_ID_KEYS)
            if not name and not player_id:
                continue
            status = normalize_injury_status(_pick(row, lowered, *_INJURY_KEYS))
            flag = _pick(row, lowered, "exclude", "excluded", "hard_exclude").casefold()
            explicit = name_list or flag in _TRUTHY
            rows.append(
                _ScratchRow(
                    player_id=player_id,
                    name=name,
                    team=normalize_join_team(_pick(row, lowered, *_TEAM_KEYS)),
                    status=status,
                    explicit=explicit or is_prelock_hard_status(status),
                )
            )
    return rows


def _load_qb_starter_file(path: str | Path) -> tuple[dict[str, str], list[_BackupQb]]:
    starter_path = Path(path)
    if not starter_path.is_file():
        raise FileNotFoundError(f"QB starter CSV not found: {starter_path}")
    starters: dict[str, str] = {}
    backups: list[_BackupQb] = []
    with starter_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            raise ValueError(f"QB starter CSV has no header: {starter_path}")
        lowered = _header_map(fieldnames)
        for row in reader:
            team = normalize_join_team(_pick(row, lowered, *_TEAM_KEYS))
            starter = _pick(row, lowered, "starter", "qb", "starter_name")
            if starter:
                starters[team] = fold_person(starter)
            cell = _pick(row, lowered, "backups_hard_exclude", "backups hard exclude")
            for name in _split_backup_cell(cell):
                if name == "__FLAG__":
                    flagged = _player_name(row, lowered)
                    if flagged:
                        backups.append(_BackupQb(team=team, name=flagged))
                    continue
                backups.append(_BackupQb(team=team, name=name))
    return starters, backups


def _apply_scratch_rows(players: list[SlatePlayer], rows: Sequence[_ScratchRow]) -> None:
    by_id, by_key, by_name = _player_indexes(players)
    for row in rows:
        if not row.explicit and not is_prelock_hard_status(row.status):
            continue
        player = _match_player(row.player_id, row.name, row.team, by_id, by_key, by_name)
        if player is None:
            continue
        if row.status:
            player.scratch_status = row.status
        if is_prelock_hard_status(row.status):
            player.effective_status = row.status
            player.hard_excluded = True
            player.exclude_reason = "scratch_status"
        elif row.explicit:
            player.hard_excluded = True
            if not player.exclude_reason:
                player.exclude_reason = "scratch_exclude"


def _apply_backup_qbs(
    players: list[SlatePlayer],
    starters: Mapping[str, str],
    backups: Sequence[_BackupQb],
) -> None:
    by_id, by_key, by_name = _player_indexes(players)
    for backup in backups:
        if _is_listed_starter(backup.name, backup.team, starters):
            continue
        player = _match_player("", backup.name, backup.team, by_id, by_key, by_name)
        if player is None:
            continue
        if player.pos not in {"", "QB"}:
            continue
        if _is_listed_starter(player.name, player.team, starters):
            continue
        if player.hard_excluded:
            continue
        player.hard_excluded = True
        player.exclude_reason = "backup_qb"


def _apply_named_excludes(players: list[SlatePlayer], names: Sequence[str]) -> None:
    by_id, _by_key, by_name = _player_indexes(players)
    for name in names:
        matches: list[SlatePlayer] = []
        if name in by_id:
            matches.append(by_id[name])
        folded = fold_person(name)
        matches.extend(by_name.get(folded, []))
        seen: set[int] = set()
        for player in matches:
            if id(player) in seen:
                continue
            seen.add(id(player))
            if player.hard_excluded:
                continue
            player.hard_excluded = True
            player.exclude_reason = "exclude_players"


def _apply_questionable_policy(players: list[SlatePlayer]) -> None:
    for player in players:
        if player.hard_excluded:
            continue
        if not is_questionable_status(player.effective_status):
            continue
        player.hard_excluded = True
        player.exclude_reason = "questionable_policy"


def _ban_sets(
    players: Sequence[SlatePlayer],
    scratch_rows: Sequence[_ScratchRow],
    backups: Sequence[_BackupQb],
    starters: Mapping[str, str],
    extra_names: Sequence[str],
) -> tuple[frozenset[str], frozenset[str]]:
    ident: set[str] = set()
    names: set[str] = set()
    for player in players:
        if not player.hard_excluded:
            continue
        if player.player_id:
            ident.add(player.player_id)
        folded = fold_person(player.name)
        if folded:
            names.add(folded)
    by_id, by_key, by_name = _player_indexes(list(players))
    for row in scratch_rows:
        if not row.explicit and not is_prelock_hard_status(row.status):
            continue
        if _match_player(row.player_id, row.name, row.team, by_id, by_key, by_name) is not None:
            continue
        if row.player_id:
            ident.add(row.player_id)
        folded = fold_person(row.name)
        if folded:
            names.add(folded)
    for backup in backups:
        if _is_listed_starter(backup.name, backup.team, starters):
            continue
        matched = _match_player("", backup.name, backup.team, by_id, by_key, by_name)
        if matched is not None and matched.pos not in {"", "QB"}:
            continue
        folded = fold_person(backup.name)
        if folded:
            names.add(folded)
    for name in extra_names:
        if name in by_id or by_name.get(fold_person(name)):
            continue
        if any(char.isdigit() for char in name) and " " not in name:
            ident.add(name)
        else:
            folded = fold_person(name)
            if folded:
                names.add(folded)
    return frozenset(ident), frozenset(names)


def _player_indexes(
    players: Sequence[SlatePlayer],
) -> tuple[dict[str, SlatePlayer], dict[tuple[str, str], SlatePlayer], dict[str, list[SlatePlayer]]]:
    by_id: dict[str, SlatePlayer] = {}
    by_key: dict[tuple[str, str], SlatePlayer] = {}
    by_name: dict[str, list[SlatePlayer]] = defaultdict(list)
    for player in players:
        if player.player_id:
            by_id[player.player_id] = player
        folded = fold_person(player.name)
        if not folded:
            continue
        by_name[folded].append(player)
        if player.team:
            by_key[(folded, player.team)] = player
    return by_id, by_key, by_name


def _match_player(
    player_id: str,
    name: str,
    team: str,
    by_id: Mapping[str, SlatePlayer],
    by_key: Mapping[tuple[str, str], SlatePlayer],
    by_name: Mapping[str, Sequence[SlatePlayer]],
) -> SlatePlayer | None:
    if player_id and player_id in by_id:
        return by_id[player_id]
    folded = fold_person(name)
    if not folded:
        return None
    if team and (folded, team) in by_key:
        return by_key[(folded, team)]
    if team:
        return None
    hits = list(by_name.get(folded, ()))
    if len(hits) == 1:
        return hits[0]
    return None


def _is_listed_starter(name: str, team: str, starters: Mapping[str, str]) -> bool:
    folded = fold_person(name)
    if not folded:
        return False
    if team:
        return starters.get(team) == folded
    return folded in set(starters.values())


def _row_is_banned(row: Mapping[str, str], lowered: Mapping[str, str], gate: PrelockGate) -> bool:
    player_id = _pick(row, lowered, *_ID_KEYS)
    if player_id and player_id in gate.banned_ids:
        return True
    name = _player_name(row, lowered)
    folded = fold_person(name)
    return bool(folded) and folded in gate.banned_names


def _exposure_text(
    slate_date: str,
    count: int,
    team_rows: Sequence[Mapping[str, str]],
    player_rows: Sequence[Mapping[str, str]],
    *,
    title: str,
    tier_rows: Sequence[Mapping[str, str]] = (),
    role_cliff_rows: Sequence[Mapping[str, str]] = (),
) -> str:
    del slate_date
    flags = [
        f"{row['team']} {row['flag']}"
        for row in team_rows
        if row.get("flag")
    ]
    flag_line = "Flags: " + ("; ".join(flags) if flags else "none") + "."
    lines = [
        title,
        f"Lineups: {count}",
        flag_line,
        "",
        "## Teams",
        "| team | lineups | pct | flag |",
        "| --- | ---: | ---: | --- |",
    ]
    for row in team_rows:
        lines.append(
            "| "
            + " | ".join(
                (_md(row["team"]), _md(row["lineups"]), _md(row["pct"]), _md(row["flag"]))
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Top 25 players",
            "| name | lineups | pct | salary | proj_fd_pts | injury_status |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in player_rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    _md(row["name"]),
                    _md(row["lineups"]),
                    _md(row["pct"]),
                    _md(row["salary"]),
                    _md(row["proj_fd_pts"]),
                    _md(row["injury_status"]),
                )
            )
            + " |"
        )
    if not player_rows:
        lines.append("|  | 0 | 0.0% |  |  |  |")
    lines.extend(
        [
            "",
            "## Tiered-cap audit",
            "| name | team | pos | salary | cap | reason |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for row in tier_rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    _md(row.get("name", "")),
                    _md(row.get("team", "")),
                    _md(row.get("pos", "")),
                    _md(row.get("salary", "")),
                    _md(row.get("cap", "")),
                    _md(row.get("reason", "")),
                )
            )
            + " |"
        )
    if not tier_rows:
        lines.append("|  |  |  |  |  | none |")
    lines.extend(
        [
            "",
            "## Questionable / role-cliff players",
            "| name | team | pos | salary | injury_status | role_flags |",
            "| --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for row in role_cliff_rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    _md(row.get("name", "")),
                    _md(row.get("team", "")),
                    _md(row.get("pos", "")),
                    _md(row.get("salary", "")),
                    _md(row.get("injury_status", "")),
                    _md(row.get("role_flags", "")),
                )
            )
            + " |"
        )
    if not role_cliff_rows:
        lines.append("|  |  |  |  |  | none |")
    return "\n".join(lines)


def _team_flag(hits: int, count: int) -> str:
    if hits <= 0 or count <= 0:
        return "zero"
    share = hits / count
    if share > TEAM_EXPOSURE_CAP:
        return "over 45%"
    return ""


def _pct(hits: int, count: int) -> str:
    if count <= 0:
        return "0.0%"
    return f"{(100.0 * hits / count):.1f}%"


def _copy_file(source: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == dest.resolve():
        return dest
    shutil.copyfile(source, dest)
    return dest


def _header_map(fieldnames: Sequence[str] | None) -> dict[str, str]:
    return {str(name or "").strip().lower(): str(name) for name in fieldnames or [] if str(name or "").strip()}


def _pick(row: Mapping[str, Any], lowered: Mapping[str, str], *keys: str) -> str:
    for key in keys:
        source = lowered.get(key)
        if source is None:
            continue
        value = str(row.get(source, "") or "").strip()
        if value:
            return value
    return ""


def _player_name(row: Mapping[str, Any], lowered: Mapping[str, str]) -> str:
    nickname = _pick(row, lowered, "nickname")
    if nickname:
        return nickname
    named = _pick(row, lowered, *_NAME_KEYS)
    if named:
        return named
    first = _pick(row, lowered, "first name", "firstname")
    last = _pick(row, lowered, "last name", "lastname")
    return " ".join(part for part in (first, last) if part).strip()


def _pos_token(value: str) -> str:
    token = str(value or "").split("/")[0].strip().upper()
    if token in {"D", "DEF", "DST"}:
        return "DST"
    return token


def _number_text(value: str) -> str:
    text = str(value or "").strip().replace("%", "").replace("$", "").replace(",", "")
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return ""
    if math.isnan(number):
        return ""
    if number.is_integer():
        return str(int(number))
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _split_backup_cell(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text or text.casefold() in {"0", "false", "no", "n"}:
        return []
    if text.casefold() in _TRUTHY:
        return ["__FLAG__"]
    parts = re.split(r"[|;]", text)
    return [part.strip() for part in parts if part.strip()]


def _md(value: object) -> str:
    return str(value or "").replace("|", "/").replace("\n", " ")
