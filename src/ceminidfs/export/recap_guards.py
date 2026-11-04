"""Week-7 recap guardrails for the FanDuel pool and the MME book.

G1 drops a skill player who misses the touch floor or the cheap-salary floor.
G2 keeps one starting quarterback per team.
G3 drops a free agent, a reserve, and a skill player with no recent snaps.
G4 caps exposure and blocks an unstacked same-team running back and tight end.
G8 copies the salary file when the week loader reads it.
"""

from __future__ import annotations

import csv
import math
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from ceminidfs.data.stadiums import normalize_team_abbr

CHEAP_SALARY = 4800
CHEAP_PLAYED = 3
CHEAP_FPPG = 4.5
RB_TOUCH_FLOOR = 4
RECEIVER_TARGET_FLOOR = 4
TARGET_SHARE_FLOOR = 0.15
ROUTE_SHARE_FLOOR = 0.55
# A priced starter stays in the pool when the usage floor would drop him.
RECEIVER_EXEMPT_SALARY = 6000
RECEIVER_EXEMPT_FPPG = 10.0
SKILL_POSITIONS = frozenset({"RB", "WR", "TE"})
# 25% of a 150-lineup book. round(0.25 * 150) is 38. One player stays at or under 38.
MME_EXPOSURE = 0.25
MME_PLAYER_CAP = 38
WR_TE_CAP = MME_PLAYER_CAP
RB_CAP = MME_PLAYER_CAP
RB_PAIR_CAP = 24
RB_TE_CAP = 9
BOOK_SIZE = 150

INACTIVE_ROSTER = frozenset(
    {
        "FA",
        "FREE AGENT",
        "CUT",
        "RES",
        "RESERVE",
        "IR",
        "PUP",
        "NFI",
        "SUS",
        "SUSP",
        "SUSPENDED",
        "PS",
        "PRACTICE SQUAD",
        "DEV",
        "INA",
        "OUT",
        "O",
        "D",
        "DOUBTFUL",
    }
)
NAME_SUFFIXES = frozenset({"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"})


def fold_key(value: object) -> str:
    """Fold a display name. Apostrophes and case do not change the key."""

    text = str(value or "")
    for src in ("\u2019", "\u2018", "`"):
        text = text.replace(src, "'")
    text = text.replace("'", "")
    return " ".join(text.casefold().split())


def canon_position(value: object) -> str:
    token = str(value or "").strip().upper()
    if token in {"D", "DEF", "DST"}:
        return "DST"
    return token


def name_keys(value: object) -> set[str]:
    """Fold a display name into the keys used by the touch index."""

    folded = fold_key(value)
    if not folded:
        return set()
    keys = {folded}
    if "." in folded:
        tail = folded.split(".")[-1].strip()
        if tail:
            keys.add(tail)
    tokens = folded.split()
    if tokens and tokens[-1] in NAME_SUFFIXES:
        stem = " ".join(tokens[:-1]).strip()
        if stem:
            keys.add(stem)
    return keys


def _last_token(name: str) -> str:
    tokens = name.split()
    token = tokens[-1] if tokens else name
    if token in NAME_SUFFIXES and len(tokens) > 1:
        token = tokens[-2]
    if "." in token:
        token = token.split(".")[-1]
    return token


def _as_share(value: object) -> float | None:
    """Return a 0..1 share. A value above 1.5 is a percent."""

    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    if number > 1.5:
        number = number / 100.0
    if number > 1:
        number = 1.0
    return number


def receiver_exempt(position: object, salary: int | None, fppg: float | None) -> bool:
    """True when salary and FPPG waive the WR/TE usage floor."""

    if canon_position(position) not in {"WR", "TE"}:
        return False
    if salary is None or fppg is None:
        return False
    try:
        price = int(salary)
        points = float(fppg)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(points):
        return False
    return price >= RECEIVER_EXEMPT_SALARY and points >= RECEIVER_EXEMPT_FPPG


def opportunity_blocked(
    position: object,
    targets: int,
    carries: int,
    *,
    salary: int | None = None,
    fppg: float | None = None,
    team_target_share: float | None = None,
    route_share: float | None = None,
    snap_share: float | None = None,
) -> bool:
    """True when the last two active games miss the touch floor.

    A WR or TE needs 4 targets. When a share is present, he also needs a 15%
    team target share, or a 55% route share, or a 55% snap share. A salary at
    or above $6,000 with FPPG at or above 10.0 stays eligible.
    """

    pos = canon_position(position)
    if pos == "RB":
        return int(targets) + int(carries) < RB_TOUCH_FLOOR
    if pos not in {"WR", "TE"}:
        return False
    if receiver_exempt(pos, salary, fppg):
        return False
    if int(targets) < RECEIVER_TARGET_FLOOR:
        return True
    known = [team_target_share, route_share, snap_share]
    if all(value is None for value in known):
        return False
    team_ok = team_target_share is not None and float(team_target_share) >= TARGET_SHARE_FLOOR
    route_ok = route_share is not None and float(route_share) >= ROUTE_SHARE_FLOOR
    snap_ok = snap_share is not None and float(snap_share) >= ROUTE_SHARE_FLOOR
    return not (team_ok or route_ok or snap_ok)


def cheap_season_blocked(position: object, salary: int, played: int, fppg: float) -> bool:
    """True when a salary at or under $4,800 misses the season floor."""

    if canon_position(position) not in SKILL_POSITIONS:
        return False
    if int(salary) > CHEAP_SALARY:
        return False
    return int(played) < CHEAP_PLAYED or float(fppg) < CHEAP_FPPG


def inactive_roster_status(status: object) -> bool:
    """True for a free agent, practice-squad, reserve, or inactive label."""

    token = " ".join(str(status or "").strip().upper().split())
    if not token or token in {"ACT", "ACTIVE", "Q", "QUESTIONABLE"}:
        return False
    if token in INACTIVE_ROSTER:
        return True
    return any(part in token for part in ("FREE AGENT", "PRACTICE", "RESERVE", "SUSPEND"))


def roster_excluded(
    *,
    status: object,
    snaps: int,
    starter_note: bool,
    roster_fresh: bool,
) -> bool:
    """True when the roster label or the snap floor removes the player."""

    if roster_fresh and inactive_roster_status(status):
        return True
    return int(snaps) <= 0 and not starter_note


def skill_excluded(
    *,
    position: object,
    name: object,
    salary: int,
    played: int,
    fppg: float,
    targets: int | None,
    carries: int | None,
    snaps: int | None,
    roster_status: object = "",
    roster_fresh: bool = False,
    starter_note: bool = False,
    whitelist: frozenset[str] | set[str] | None = None,
    team_target_share: float | None = None,
    route_share: float | None = None,
    snap_share: float | None = None,
) -> bool:
    """True when G1 or G3 removes this skill player. A whitelist name stays."""

    pos = canon_position(position)
    if pos not in SKILL_POSITIONS:
        return False
    allowed = {fold_key(item) for item in (whitelist or ())}
    if fold_key(name) in allowed:
        return False
    if _roster_removed(roster_status, snaps, starter_note, roster_fresh):
        return True
    if _opportunity_removed(
        pos,
        targets,
        carries,
        salary,
        fppg,
        team_target_share,
        route_share,
        snap_share,
    ):
        return True
    return cheap_season_blocked(pos, salary, played, fppg)


def _roster_removed(
    roster_status: object,
    snaps: int | None,
    starter_note: bool,
    roster_fresh: bool,
) -> bool:
    if not roster_excluded(
        status=roster_status,
        snaps=0 if snaps is None else snaps,
        starter_note=starter_note,
        roster_fresh=roster_fresh,
    ):
        return False
    if not (roster_fresh or snaps is not None):
        return False
    if roster_fresh and inactive_roster_status(roster_status):
        return True
    return snaps is not None and snaps <= 0 and not starter_note


def _opportunity_removed(
    pos: str,
    targets: int | None,
    carries: int | None,
    salary: int,
    fppg: float,
    team_target_share: float | None,
    route_share: float | None,
    snap_share: float | None,
) -> bool:
    if targets is None or carries is None:
        return False
    return opportunity_blocked(
        pos,
        targets,
        carries,
        salary=salary,
        fppg=fppg,
        team_target_share=team_target_share,
        route_share=route_share,
        snap_share=snap_share,
    )


def is_backup_quarterback(
    team: object,
    name: object,
    position: object,
    starters: Mapping[str, str],
) -> bool:
    """True when this quarterback is not the one starter for his team."""

    if canon_position(position) != "QB":
        return False
    club = normalize_team_abbr(str(team or ""))
    starter = starters.get(club) or starters.get(str(team or "").strip().upper())
    if not starter:
        return True
    return fold_key(name) != fold_key(starter)


def assert_one_qb_per_team(rostered: Mapping[str, set[str]]) -> None:
    """Raise when one team uses two quarterback identities in the book."""

    extra = {team: sorted(names) for team, names in rostered.items() if len(names) > 1}
    if extra:
        raise AssertionError(f"backup quarterbacks {extra}")


def load_qb_starters_csv(path: str | Path) -> dict[str, str]:
    """Return team -> starter from a ``Team,Starter`` file."""

    csv_path = Path(path)
    starters: dict[str, str] = {}
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        for row in reader:
            lowered = {str(key or "").strip().lower(): str(value or "").strip() for key, value in row.items()}
            team = normalize_team_abbr(lowered.get("team") or lowered.get("club") or "")
            name = lowered.get("starter") or lowered.get("name") or ""
            if team and name:
                starters[team] = name
    return starters


def write_qb_starters_csv(path: str | Path, starters: Mapping[str, str]) -> Path:
    """Write ``Team,Starter`` rows. One starter per team."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Team", "Starter"])
        writer.writeheader()
        for team, name in sorted(starters.items()):
            writer.writerow({"Team": normalize_team_abbr(team), "Starter": name})
    return destination


_BLOCKED_QB_STATUSES = frozenset(
    {"O", "OUT", "IR", "D", "DOUBTFUL", "PUP", "NFI", "SUS", "SUSPENDED"}
)


def _record_status(record: Mapping[str, Any]) -> str:
    return str(
        record.get("Injury Indicator") or record.get("injury_indicator") or ""
    ).strip().upper()


def _record_salary(record: Mapping[str, Any]) -> int:
    try:
        return int(float(record.get("Salary") or record.get("salary") or 0))
    except (TypeError, ValueError):
        return 0


def _record_team_name(record: Mapping[str, Any]) -> tuple[str, str] | None:
    team = normalize_team_abbr(str(record.get("Team") or record.get("team") or ""))
    name = str(record.get("Nickname") or record.get("nickname") or "").strip()
    if not team or not name:
        return None
    return team, name


def _qb_salary_record(record: Mapping[str, Any]) -> tuple[str, str, int] | None:
    if canon_position(record.get("Position") or record.get("position")) != "QB":
        return None
    if _record_status(record) in _BLOCKED_QB_STATUSES:
        return None
    team_name = _record_team_name(record)
    if team_name is None:
        return None
    team, name = team_name
    return team, name, _record_salary(record)


def highest_salary_starters(frame: pd.DataFrame) -> dict[str, str]:
    """Pick the highest-salary active quarterback on each team."""

    if frame.empty:
        return {}
    best: dict[str, tuple[int, str]] = {}
    for record in frame.to_dict(orient="records"):
        found = _qb_salary_record(record)
        if found is None:
            continue
        team, name, salary = found
        current = best.get(team)
        if current is None or salary > current[0]:
            best[team] = (salary, name)
    return {team: name for team, (_salary, name) in best.items()}


def environment_scale(roof: object, wind_mph: object, position: object) -> float:
    """Scale a tail for open-air wind. A dome or a closed roof stays at 1."""

    roof_key = str(roof or "").strip().lower()
    if roof_key != "open":
        return 1.0
    try:
        wind = float(wind_mph)
    except (TypeError, ValueError):
        wind = 0.0
    if not math.isfinite(wind):
        wind = 0.0
    pos = canon_position(position)
    if wind >= 15:
        if pos in {"QB", "WR"}:
            return 0.90
        if pos == "RB":
            return 1.08
        if pos == "TE":
            return 1.04
        return 1.0
    if wind >= 10:
        if pos == "WR":
            return 0.97
        if pos in {"RB", "TE"}:
            return 1.05
        if pos == "QB":
            return 0.99
    return 1.0


def archive_loaded_salary(
    source: str | Path,
    copies: Sequence[str | Path],
    *,
    workspace_root: str | Path = "/workspace",
) -> list[Path]:
    """Copy the FanDuel file. Skip a ``/workspace`` copy when that root is absent."""

    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(src)
    root = Path(workspace_root)
    written: list[Path] = []
    for item in copies:
        dest = Path(item)
        try:
            dest.resolve().relative_to(root.resolve())
            under_workspace = True
        except ValueError:
            under_workspace = False
        if under_workspace and not root.is_dir():
            continue
        if dest.resolve() == src.resolve():
            written.append(dest)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        if not dest.is_file() or dest.stat().st_size != src.stat().st_size:
            raise OSError(f"salary copy failed: {dest}")
        written.append(dest)
    return written


def _slate_date_from_name(path: Path) -> str:
    text = path.name
    for index in range(0, max(len(text) - 9, 0)):
        token = text[index : index + 10]
        if (
            len(token) == 10
            and token[4] == "-"
            and token[7] == "-"
            and token[:4].isdigit()
            and token[5:7].isdigit()
            and token[8:10].isdigit()
        ):
            return token
    return ""


def _fixture_id_from_salary(path: Path) -> str:
    """Return the shared FanDuel contest id, or ``slate`` when the file has none."""

    try:
        frame = pd.read_csv(path, nrows=40)
    except (OSError, ValueError, pd.errors.ParserError):
        return "slate"
    id_column = next((column for column in frame.columns if str(column).strip().lower() == "id"), None)
    if id_column is None:
        return "slate"
    prefixes: list[str] = []
    for value in frame[id_column].astype(str):
        text = value.strip()
        if "-" not in text:
            continue
        prefix = text.split("-", 1)[0].strip()
        if prefix.isdigit():
            prefixes.append(prefix)
    if prefixes and len(set(prefixes)) == 1:
        return prefixes[0]
    return "slate"


def prelock_salary_archive(
    source: str | Path,
    *,
    season: int,
    week: int,
    work_dir: str | Path,
    slate_date: str | None = None,
    fixture_id: str | None = None,
    recap_root: str | Path = "/workspace/dfs-recap",
) -> list[Path]:
    """Copy the salary file before a solve. Fail when the run copy fails.

    Writes ``runs/.../_src_fd_sun.csv`` and ``fade-coverage-w{week}.md``.
    When ``recap_root`` exists, also writes
    ``{slate_date}/in/fd_players_{fixture_id}.csv``.
    """

    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(src)
    run_dir = Path(work_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_copy = run_dir / "_src_fd_sun.csv"
    written = archive_loaded_salary(src, [run_copy], workspace_root=run_dir)
    if run_copy not in written or not run_copy.is_file():
        raise OSError(f"salary copy failed: {run_copy}")

    date = (slate_date or _slate_date_from_name(src) or "").strip()
    contest = (fixture_id or _fixture_id_from_salary(src) or "slate").strip() or "slate"
    root = Path(recap_root)
    recap_copy: Path | None = None
    recap_note = "skipped: dfs-recap root is absent"
    if root.is_dir():
        if not date:
            recap_note = "skipped: slate date is absent"
        else:
            recap_copy = root / date / "in" / f"fd_players_{contest}.csv"
            recap_copy.parent.mkdir(parents=True, exist_ok=True)
            if recap_copy.resolve() != src.resolve():
                shutil.copyfile(src, recap_copy)
            if not recap_copy.is_file() or recap_copy.stat().st_size != src.stat().st_size:
                raise OSError(f"salary copy failed: {recap_copy}")
            written.append(recap_copy)
            recap_note = str(recap_copy)

    try:
        rows = sum(1 for _ in src.open(encoding="utf-8-sig")) - 1
    except OSError:
        rows = 0
    if rows < 0:
        rows = 0
    audit = run_dir / f"fade-coverage-w{int(week)}.md"
    lines = [
        f"# Fade coverage audit — {int(season)} week {int(week)}",
        "",
        "Pre-lock salary copy is on disk.",
        "",
        f"- source: {src}",
        f"- run copy: {run_copy}",
        f"- recap copy: {recap_note}",
        f"- rows: {rows}",
        "",
    ]
    audit.write_text("\n".join(lines), encoding="utf-8")
    if not audit.is_file():
        raise OSError(f"fade audit failed: {audit}")
    written.append(audit)
    return written


@dataclass(frozen=True)
class Opportunity:
    targets: int
    carries: int
    snaps: int
    team_targets: int = 0
    route_share: float | None = None
    snap_share: float | None = None


@dataclass(frozen=True)
class OpportunityIndex:
    by_name: Mapping[tuple[str, str], Opportunity]
    active_teams: frozenset[str]


def _club(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip().upper()
    if text in {"", "NAN", "NONE", "NAT"}:
        return ""
    return normalize_team_abbr(text)


class _Bucket:
    def __init__(self) -> None:
        self.targets = 0
        self.carries = 0
        self.snaps = 0
        self.team_targets = 0
        self.route_share: float | None = None
        self.snap_share: float | None = None


def _filter_play_frame(
    pbp: pd.DataFrame,
    season: int,
    before_week: int,
) -> tuple[pd.DataFrame | None, frozenset[str]]:
    frame = pbp.copy()
    if "season" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["season"], errors="coerce").eq(int(season))].copy()
    frame["week"] = pd.to_numeric(frame.get("week"), errors="coerce")
    frame = frame.loc[frame["week"].lt(int(before_week)) & frame["week"].notna()].copy()
    if frame.empty or "posteam" not in frame.columns:
        return None, frozenset()
    frame["team"] = frame["posteam"].map(_club)
    frame = frame.loc[frame["team"].ne("")].copy()
    active = frozenset(frame["team"].dropna().astype(str))
    if frame.empty:
        return None, active
    return frame, active


def _record_name_keys(record: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    for column in ("full_name", "football_name"):
        keys |= name_keys(record.get(column))
    full = f"{record.get('first_name') or ''} {record.get('last_name') or ''}".strip()
    keys |= name_keys(full)
    return keys


def _roster_names(rosters: pd.DataFrame | None) -> dict[str, set[str]]:
    names: dict[str, set[str]] = defaultdict(set)
    if rosters is None or rosters.empty or "gsis_id" not in rosters.columns:
        return names
    for record in rosters.to_dict(orient="records"):
        gsis = str(record.get("gsis_id") or "")
        if not gsis:
            continue
        names[gsis] |= _record_name_keys(record)
    return names


def _player_opportunity(
    rows: list[tuple[int, int, int, int]],
    team: str,
    gsis: str,
    team_week_targets: Mapping[tuple[str, int], int],
    snap_window: Mapping[str, set[int]],
    shares: Mapping[tuple[str, str, int], tuple[float | None, float | None]],
    active_games: int,
) -> tuple[int, int, int, int, float | None, float | None]:
    rows.sort()
    active_rows = [row for row in rows if row[1] + row[2] > 0]
    chosen = active_rows[-int(active_games) :]
    targets = sum(row[1] for row in chosen)
    carries = sum(row[2] for row in chosen)
    chosen_weeks = [row[0] for row in chosen]
    team_targets = sum(team_week_targets.get((team, week_no), 0) for week_no in chosen_weeks)
    window = snap_window.get(team, set())
    snaps = sum(row[3] for row in rows if row[0] in window)
    route_share = _mean_share(shares, team, gsis, chosen_weeks, 0)
    snap_share = _mean_share(shares, team, gsis, chosen_weeks, 1)
    return targets, carries, snaps, team_targets, route_share, snap_share


def _fill_buckets(
    by_player: dict[tuple[str, str], list[tuple[int, int, int, int]]],
    team_week_targets: Mapping[tuple[str, int], int],
    snap_window: Mapping[str, set[int]],
    shares: Mapping[tuple[str, str, int], tuple[float | None, float | None]],
    names: Mapping[str, set[str]],
    active_games: int,
) -> dict[tuple[str, str], _Bucket]:
    by_name: dict[tuple[str, str], _Bucket] = defaultdict(_Bucket)
    for (team, gsis), rows in by_player.items():
        targets, carries, snaps, team_targets, route_share, snap_share = _player_opportunity(
            rows, team, gsis, team_week_targets, snap_window, shares, active_games
        )
        for key in names.get(gsis, set()):
            bucket = by_name[(team, key)]
            bucket.targets += int(targets)
            bucket.carries += int(carries)
            bucket.snaps += int(snaps)
            bucket.team_targets = max(bucket.team_targets, int(team_targets))
            bucket.route_share = _max_share(bucket.route_share, route_share)
            bucket.snap_share = _max_share(bucket.snap_share, snap_share)
    return by_name


def _pack_opportunities(by_name: Mapping[tuple[str, str], _Bucket]) -> dict[tuple[str, str], Opportunity]:
    return {
        key: Opportunity(
            targets=bucket.targets,
            carries=bucket.carries,
            snaps=bucket.snaps,
            team_targets=bucket.team_targets,
            route_share=bucket.route_share,
            snap_share=bucket.snap_share,
        )
        for key, bucket in by_name.items()
    }


def build_opportunity_index(
    pbp: pd.DataFrame,
    rosters: pd.DataFrame | None = None,
    *,
    season: int = 2026,
    before_week: int = 8,
    active_games: int = 2,
    snap_games: int = 3,
    participation: pd.DataFrame | None = None,
) -> OpportunityIndex:
    """Sum targets, carries, and snaps before the slate week.

    Targets and carries use the player's last two games with a touch.
    Snaps use the team's last three played weeks.
    """

    if pbp is None or pbp.empty:
        return OpportunityIndex(by_name={}, active_teams=frozenset())
    frame, active = _filter_play_frame(pbp, season, before_week)
    if frame is None:
        return OpportunityIndex(by_name={}, active_teams=active)

    names = _roster_names(rosters)

    # (team, gsis, week) -> [targets, carries, snaps]
    cells: dict[tuple[str, str, int], list[int]] = defaultdict(lambda: [0, 0, 0])
    team_weeks: dict[str, set[int]] = defaultdict(set)
    team_week_targets: dict[tuple[str, int], int] = defaultdict(int)

    def add(mask: pd.Series, id_column: str, name_column: str, slot: int) -> None:
        if id_column not in frame.columns:
            return
        columns = ["team", "week", id_column]
        if name_column in frame.columns:
            columns.append(name_column)
        part = frame.loc[mask, columns].dropna(subset=[id_column])
        for record in part.to_dict(orient="records"):
            gsis = str(record.get(id_column) or "")
            team = str(record.get("team") or "")
            week = record.get("week")
            if not gsis or not team or pd.isna(week):
                continue
            week_no = int(week)
            cells[(team, gsis, week_no)][slot] += 1
            team_weeks[team].add(week_no)
            if slot == 0:
                team_week_targets[(team, week_no)] += 1
            if name_column in record:
                names[gsis] |= name_keys(record.get(name_column))

    passed = pd.to_numeric(frame.get("pass"), errors="coerce").fillna(0).eq(1)
    rushed = pd.to_numeric(frame.get("rush"), errors="coerce").fillna(0).eq(1)
    add(passed, "receiver_player_id", "receiver_player_name", 0)
    add(rushed, "rusher_player_id", "rusher_player_name", 1)
    add(passed, "passer_player_id", "passer_player_name", 2)
    # A rush or a target is also a snap. The passer add above counts dropbacks.
    for key, counts in list(cells.items()):
        counts[2] += counts[0] + counts[1]

    by_player: dict[tuple[str, str], list[tuple[int, int, int, int]]] = defaultdict(list)
    for (team, gsis, week_no), counts in cells.items():
        by_player[(team, gsis)].append((week_no, counts[0], counts[1], counts[2]))

    snap_window = {
        team: set(sorted(weeks)[-int(snap_games) :]) for team, weeks in team_weeks.items()
    }
    shares = _participation_index(participation)

    by_name = _fill_buckets(
        by_player, team_week_targets, snap_window, shares, names, active_games
    )
    return OpportunityIndex(by_name=_pack_opportunities(by_name), active_teams=active)


def _max_share(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _mean_share(
    shares: Mapping[tuple[str, str, int], tuple[float | None, float | None]],
    team: str,
    gsis: str,
    weeks: Sequence[int],
    slot: int,
) -> float | None:
    values = []
    for week_no in weeks:
        pair = shares.get((team, gsis, int(week_no)))
        if pair is None or pair[slot] is None:
            continue
        values.append(float(pair[slot]))
    if not values:
        return None
    return sum(values) / len(values)


def _first_present(columns: Iterable[str], candidates: tuple[str, ...]) -> str | None:
    for name in candidates:
        if name in columns:
            return name
    return None


def _participation_columns(
    frame: pd.DataFrame,
) -> tuple[str, str | None, str | None, str | None] | None:
    id_column = _first_present(frame.columns, ("gsis_id", "player_id"))
    if id_column is None or "week" not in frame.columns:
        return None
    team_column = _first_present(frame.columns, ("team", "posteam", "recent_team"))
    route_column = _first_present(
        frame.columns, ("route_participation", "route_pct", "route_share")
    )
    snap_column = _first_present(frame.columns, ("offense_pct", "snap_share", "snap_pct"))
    if route_column is None and snap_column is None:
        return None
    return id_column, team_column, route_column, snap_column


def _participation_entry(
    record: Mapping[str, Any],
    id_column: str,
    team_column: str | None,
    route_column: str | None,
    snap_column: str | None,
) -> tuple[tuple[str, str, int], tuple[float | None, float | None]] | None:
    gsis = str(record.get(id_column) or "")
    week = record.get("week")
    if not gsis or pd.isna(week):
        return None
    team = _club(record.get(team_column)) if team_column else ""
    route = _as_share(record.get(route_column)) if route_column else None
    snap = _as_share(record.get(snap_column)) if snap_column else None
    return (team, gsis, int(week)), (route, snap)


def _participation_index(
    frame: pd.DataFrame | None,
) -> dict[tuple[str, str, int], tuple[float | None, float | None]]:
    """Map ``(team, gsis, week)`` to ``(route share, snap share)``."""

    if frame is None or frame.empty:
        return {}
    columns = _participation_columns(frame)
    if columns is None:
        return {}
    id_column, team_column, route_column, snap_column = columns
    found: dict[tuple[str, str, int], tuple[float | None, float | None]] = {}
    for record in frame.to_dict(orient="records"):
        entry = _participation_entry(
            record, id_column, team_column, route_column, snap_column
        )
        if entry is None:
            continue
        key, value = entry
        found[key] = value
    return found


def lookup_opportunity(
    index: OpportunityIndex,
    team: object,
    nickname: object,
    last_name: object,
) -> Opportunity | None:
    """Return the touch row, or None when the team has no prior plays."""

    club = normalize_team_abbr(str(team or ""))
    if club not in index.active_teams:
        return None
    for key in name_keys(nickname):
        found = index.by_name.get((club, key))
        if found is not None:
            return found
    last = _last_token(fold_key(last_name))
    hits = [
        value
        for (club_key, name), value in index.by_name.items()
        if club_key == club and _last_token(name) == last
    ]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return Opportunity(0, 0, 0)
    return max(hits, key=lambda item: (item.targets + item.carries, item.snaps))
