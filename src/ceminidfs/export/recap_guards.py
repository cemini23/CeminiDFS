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
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

if TYPE_CHECKING:
    from ceminidfs.export.mme_portfolio import Candidate, PoolPlayer

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
    return _receiver_share_blocked(team_target_share, route_share, snap_share)


def _share_clears_floor(share: float | None, floor: float) -> bool:
    return share is not None and float(share) >= floor


def _receiver_share_blocked(
    team_target_share: float | None,
    route_share: float | None,
    snap_share: float | None,
) -> bool:
    if all(value is None for value in (team_target_share, route_share, snap_share)):
        return False
    if _share_clears_floor(team_target_share, TARGET_SHARE_FLOOR):
        return False
    if _share_clears_floor(route_share, ROUTE_SHARE_FLOOR):
        return False
    if _share_clears_floor(snap_share, ROUTE_SHARE_FLOOR):
        return False
    return True


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


def _lowered_cells(row: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(key or "").strip().lower(): str(value or "").strip()
        for key, value in row.items()
    }


def _starter_pair(lowered: Mapping[str, str]) -> tuple[str, str]:
    team = normalize_team_abbr(lowered.get("team") or lowered.get("club") or "")
    name = lowered.get("starter") or lowered.get("name") or ""
    return team, name


def load_qb_starters_csv(path: str | Path) -> dict[str, str]:
    """Return team -> starter from a ``Team,Starter`` file."""

    csv_path = Path(path)
    starters: dict[str, str] = {}
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        for row in reader:
            team, name = _starter_pair(_lowered_cells(row))
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


_WIND_SCALES_STRONG = {"QB": 0.90, "WR": 0.90, "RB": 1.08, "TE": 1.04}
_WIND_SCALES_MEDIUM = {"WR": 0.97, "RB": 1.05, "TE": 1.05, "QB": 0.99}


def _wind_speed(wind_mph: object) -> float:
    try:
        wind = float(wind_mph)
    except (TypeError, ValueError):
        return 0.0
    return wind if math.isfinite(wind) else 0.0


def environment_scale(roof: object, wind_mph: object, position: object) -> float:
    """Scale a tail for open-air wind. A dome or a closed roof stays at 1."""

    if str(roof or "").strip().lower() != "open":
        return 1.0
    wind = _wind_speed(wind_mph)
    pos = canon_position(position)
    if wind >= 15:
        return _WIND_SCALES_STRONG.get(pos, 1.0)
    if wind >= 10:
        return _WIND_SCALES_MEDIUM.get(pos, 1.0)
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


def _archive_labels(
    src: Path,
    slate_date: str | None,
    fixture_id: str | None,
) -> tuple[str, str]:
    date = (slate_date or _slate_date_from_name(src) or "").strip()
    contest = (fixture_id or _fixture_id_from_salary(src) or "slate").strip() or "slate"
    return date, contest


def _place_copy(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.resolve() != src.resolve():
        shutil.copyfile(src, dest)
    if not dest.is_file() or dest.stat().st_size != src.stat().st_size:
        raise OSError(f"salary copy failed: {dest}")
    return dest


def _recap_copy(
    src: Path,
    date: str,
    contest: str,
    root: Path,
    slate_root: Path,
) -> tuple[list[Path], str]:
    """Copy the salary file to the recap gate path and the players path.

    The gate file is ``{root}/{date}/_src_fd_sun.csv``. The players file is
    ``{root}/{date}/in/fd_players_{contest}.csv``. A slate root that exists
    also receives ``{date}/_src_fd_sun.csv``.
    """

    written: list[Path] = []
    notes: list[str] = []
    if not date:
        return written, "skipped: slate date is absent"
    if root.is_dir():
        gate = _place_copy(src, root / date / "_src_fd_sun.csv")
        players = _place_copy(src, root / date / "in" / f"fd_players_{contest}.csv")
        written.extend((gate, players))
        notes.append(str(players))
    else:
        notes.append("skipped: dfs-recap root is absent")
    if slate_root.is_dir():
        slate_copy = _place_copy(src, slate_root / date / "_src_fd_sun.csv")
        written.append(slate_copy)
        notes.append(str(slate_copy))
    return written, "; ".join(notes)


def _count_rows(src: Path) -> int:
    try:
        rows = sum(1 for _ in src.open(encoding="utf-8-sig")) - 1
    except OSError:
        return 0
    return max(rows, 0)


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if not path.is_file():
        raise OSError(f"fade audit failed: {path}")
    return path


def _desk_audit_dir(audit_dir: str | Path | None) -> Path:
    if audit_dir is not None:
        return Path(audit_dir)
    from ceminidfs.pipeline.fade_coverage import WEEK_REPORT_DIR

    return WEEK_REPORT_DIR


def _fade_name(week: int) -> str:
    return f"fade-coverage-w{int(week)}.md"


def _write_fade_audit(
    run_dir: Path,
    season: int,
    week: int,
    src: Path,
    run_copy: Path,
    recap_note: str,
    rows: int,
    *,
    recap_root: Path | None = None,
    slate_date: str = "",
    audit_dir: Path | None = None,
) -> list[Path]:
    audit = run_dir / _fade_name(week)
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
        "Team exposure is written after the book is selected.",
        "",
    ]
    text = "\n".join(lines)
    written = [_write_text(audit, text)]
    # Keep an existing post-game report. Create the desk file when it is missing.
    desk = _desk_audit_dir(audit_dir) / _fade_name(week)
    if not desk.is_file():
        written.append(_write_text(desk, text))
    if recap_root is not None and recap_root.is_dir() and slate_date:
        recap_audit = recap_root / slate_date / _fade_name(week)
        written.append(_write_text(recap_audit, text))
    return written


def prelock_salary_archive(
    source: str | Path,
    *,
    season: int,
    week: int,
    work_dir: str | Path,
    slate_date: str | None = None,
    fixture_id: str | None = None,
    recap_root: str | Path = "/workspace/dfs-recap",
    slate_root: str | Path = "/workspace/dfs-slate",
    audit_dir: str | Path | None = None,
) -> list[Path]:
    """Copy the salary file before a solve. Fail when the run copy fails.

    Writes ``runs/.../_src_fd_sun.csv`` and ``fade-coverage-w{week}.md``.
    When ``recap_root`` exists, also writes ``{date}/_src_fd_sun.csv`` and
    ``{date}/in/fd_players_{fixture_id}.csv``. When ``slate_root`` exists,
    also writes ``{date}/_src_fd_sun.csv`` there.
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

    date, contest = _archive_labels(src, slate_date, fixture_id)
    recap_copies, recap_note = _recap_copy(
        src,
        date,
        contest,
        Path(recap_root),
        Path(slate_root),
    )
    written.extend(recap_copies)

    rows = _count_rows(src)
    audits = _write_fade_audit(
        run_dir,
        season,
        week,
        src,
        run_copy,
        recap_note,
        rows,
        recap_root=Path(recap_root),
        slate_date=date,
        audit_dir=None if audit_dir is None else Path(audit_dir),
    )
    written.extend(audits)
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


_UNDER_FADE = re.compile(r"\b(?:rush_yds|rec_yds|pass_yds)\b\s+UNDER\b", re.IGNORECASE)
_MARKET_RE = re.compile(r"\b(?:rush_yds|rec_yds|pass_yds)\b", re.IGNORECASE)
_POS_TAIL = frozenset({"QB", "RB", "WR", "TE", "DST", "FLEX"})
_CONFIRM_TRUE = frozenset({"1", "true", "yes", "y", "active"})
_NAME_FIELDS = ("player", "player name", "name", "nickname")
_MARKET_FIELDS = ("market", "stat", "prop", "market name")
_SIDE_FIELDS = ("side", "direction", "pick", "lean")
_FRAGILE_RB_SALARY = 6500
_FRAGILE_TOUCHES = 15
_PROVENANCE_FIELDS = (
    "player_id",
    "nickname",
    "team",
    "position",
    "salary",
    "source_file",
    "fixture_id",
    "retrieved_et",
)


def scaled_book_caps(
    count: int,
    max_exposure: float = 0.22,
    qb_exposure: float = 0.24,
    dst_exposure: float = 0.22,
) -> dict[str, int]:
    """Scale position caps with ``floor(exposure * count)``."""

    size = max(int(count), 0)
    skill = math.floor(float(max_exposure) * size)
    return {
        "QB": math.floor(float(qb_exposure) * size),
        "RB": skill,
        "WR": skill,
        "TE": skill,
        "DST": math.floor(float(dst_exposure) * size),
    }


def _record_key(key: object) -> str:
    text = str(key or "").strip().casefold().replace("_", " ")
    return " ".join(text.split())


def _lowered_record(record: Mapping[str, Any]) -> dict[str, str]:
    lowered: dict[str, str] = {}
    for key, value in record.items():
        if key is None:
            continue
        lowered[_record_key(key)] = str(value or "").strip()
    return lowered


def _first_cell(lowered: Mapping[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = lowered.get(key)
        if value:
            return value
    return ""


def _name_before_market(text: str) -> str:
    match = _MARKET_RE.search(text)
    if match is None:
        return ""
    name = text[: match.start()].strip(" \t|:-—*")
    tokens = name.split()
    if tokens and tokens[-1].upper() in _POS_TAIL:
        tokens = tokens[:-1]
    return " ".join(tokens)


def _text_veto_names(text: str) -> list[str]:
    names: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or _UNDER_FADE.search(line) is None:
            continue
        cells = [cell.strip(" |-*") for cell in line.split("|")]
        cells = [cell for cell in cells if cell]
        name = ""
        for cell in cells:
            if _MARKET_RE.search(cell) or cell.upper() in _POS_TAIL:
                continue
            name = cell
            break
        if not name:
            name = _name_before_market(" ".join(cells) if cells else line)
        if name:
            names.append(name)
    return names


def _csv_veto_names(path: Path) -> list[str]:
    names: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        if not reader.fieldnames:
            return _text_veto_names(path.read_text(encoding="utf-8"))
        for row in reader:
            lowered = _lowered_record(row)
            name = _first_cell(lowered, _NAME_FIELDS)
            market = _first_cell(lowered, _MARKET_FIELDS)
            side = _first_cell(lowered, _SIDE_FIELDS)
            if market and side:
                if _UNDER_FADE.search(f"{market} {side}") and name:
                    names.append(name)
                continue
            blob = " ".join(value for value in lowered.values() if value)
            if _UNDER_FADE.search(blob):
                names.append(name or _name_before_market(blob))
    return names


def load_scheme_vetoes(
    path: Path | None,
    count: int = BOOK_SIZE,
    max_veto_share: float = 0.08,
) -> dict[str, int]:
    """Cap players named on an under fade in a scheme file.

    The file is ``scheme_vetoes_{date}.csv`` or ``scheme.md``. A row matches
    when it contains ``rush_yds UNDER``, ``rec_yds UNDER``, or ``pass_yds UNDER``.
    The cap is ``max(1, floor(max_veto_share * count))``. Keys are folded names.
    """

    cap = max(1, math.floor(float(max_veto_share) * int(count)))
    if path is None:
        return {}
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    if file_path.suffix.casefold() == ".csv":
        found = _csv_veto_names(file_path)
    else:
        found = _text_veto_names(file_path.read_text(encoding="utf-8"))
    return {fold_key(name): cap for name in found if fold_key(name)}


def _salary_lookup(
    frame: pd.DataFrame,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    by_id: dict[str, dict[str, str]] = {}
    by_name: dict[str, dict[str, str]] = {}
    for record in frame.to_dict(orient="records"):
        lowered = _lowered_record(record)
        pid = lowered.get("id") or lowered.get("player id") or ""
        name = fold_key(lowered.get("nickname") or lowered.get("name") or "")
        if pid:
            by_id[pid] = lowered
        if name:
            by_name[name] = lowered
    return by_id, by_name


def _is_questionable(record: Mapping[str, str]) -> bool:
    status = (
        record.get("injury indicator")
        or record.get("injury")
        or record.get("injury status")
        or ""
    )
    return status.strip().upper() == "Q"


def _confirmed_active(record: Mapping[str, str]) -> bool:
    for key in ("confirmed active", "confirmed", "whitelist"):
        if record.get(key, "").casefold() in _CONFIRM_TRUE:
            return True
    for key in ("injury details", "note", "notes", "status note"):
        if "confirmed active" in record.get(key, "").casefold():
            return True
    return False


def questionable_exposure_caps(
    players: Sequence[PoolPlayer],
    salary_df: pd.DataFrame,
    count: int = BOOK_SIZE,
    q_cap_share: float = 0.12,
) -> dict[str, int]:
    """Cap a Questionable player unless the salary row says he is confirmed active.

    The cap is ``max(1, floor(q_cap_share * count))``. Keys are player ids.
    """

    cap = max(1, math.floor(float(q_cap_share) * int(count)))
    if salary_df is None or salary_df.empty:
        return {}
    by_id, by_name = _salary_lookup(salary_df)
    caps: dict[str, int] = {}
    for player in players:
        record = by_id.get(player.player_id) or by_name.get(fold_key(player.nickname))
        if record is None or not _is_questionable(record) or _confirmed_active(record):
            continue
        caps[player.player_id] = cap
    return caps


def _trailing_touches(index: OpportunityIndex, player: PoolPlayer) -> int | None:
    found = lookup_opportunity(index, player.team, player.nickname, player.last_name)
    if found is None:
        return None
    return int(found.targets) + int(found.carries)


def fragile_rb_caps(
    players: Sequence[PoolPlayer],
    index: OpportunityIndex,
    count: int = BOOK_SIZE,
    fragile_share: float = 0.15,
) -> dict[str, int]:
    """Cap a running back at or under $6,500 with fewer than 15 recent touches.

    The cap is ``floor(fragile_share * count)``. A team with no prior plays
    stays off this cap. Keys are player ids.
    """

    cap = math.floor(float(fragile_share) * int(count))
    caps: dict[str, int] = {}
    for player in players:
        if canon_position(player.position) != "RB":
            continue
        if int(player.salary) > _FRAGILE_RB_SALARY:
            continue
        touches = _trailing_touches(index, player)
        if touches is None or touches >= _FRAGILE_TOUCHES:
            continue
        caps[player.player_id] = cap
    return caps


def write_lineups_resolved_csv(
    path: Path,
    book: Sequence[Candidate],
    players: Sequence[PoolPlayer],
    *,
    source_file: str,
    fixture_id: str,
    retrieved_et: str,
) -> Path:
    """Write one row per unique rostered player with salary-file provenance."""

    meta = {player.player_id: player for player in players}
    ordered: list[str] = []
    seen: set[str] = set()
    for item in book:
        for pid in item.ids:
            if pid in seen:
                continue
            seen.add(pid)
            ordered.append(str(pid))
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_PROVENANCE_FIELDS))
        writer.writeheader()
        for pid in ordered:
            player = meta[pid]
            writer.writerow(
                {
                    "player_id": player.player_id,
                    "nickname": player.nickname,
                    "team": player.team,
                    "position": player.position,
                    "salary": player.salary,
                    "source_file": source_file,
                    "fixture_id": fixture_id,
                    "retrieved_et": retrieved_et,
                }
            )
    return destination


def _team_exposure_text(
    book: Sequence[Candidate],
    players: Sequence[PoolPlayer],
    season: int,
    week: int,
) -> str:
    meta = {player.player_id: player for player in players}
    seats: dict[str, int] = defaultdict(int)
    lineups: dict[str, int] = defaultdict(int)
    teams = {player.team for player in players if player.team}
    for item in book:
        present: set[str] = set()
        for pid in item.ids:
            player = meta.get(pid)
            if player is None or not player.team:
                continue
            seats[player.team] += 1
            present.add(player.team)
            teams.add(player.team)
        for team in present:
            lineups[team] += 1
    total = max(len(book), 1)
    lines = [
        f"# Fade coverage — {int(season)} week {int(week)}",
        "",
        "Team exposure counts seats and lineups that roster the team.",
        "A team with zero lineups is a full fade.",
        "",
        "| Team | Seats | Lineups | Lineup share |",
        "|------|-------|---------|--------------|",
    ]
    for team in sorted(teams):
        used = lineups.get(team, 0)
        lines.append(f"| {team} | {seats.get(team, 0)} | {used} | {used / total:.1%} |")
    lines.append("")
    return "\n".join(lines)


def write_team_exposure_fade(
    book: Sequence[Candidate],
    players: Sequence[PoolPlayer],
    *,
    season: int,
    week: int,
    audit_dir: str | Path | None = None,
    recap_root: str | Path | None = None,
    slate_date: str = "",
) -> list[Path]:
    """Write ``reports/audit/fade-coverage-w{week}.md`` and the recap copy."""

    text = _team_exposure_text(book, players, season, week)
    written = [_write_text(_desk_audit_dir(audit_dir) / _fade_name(week), text)]
    root = None if recap_root is None else Path(recap_root)
    if root is not None and root.is_dir() and slate_date:
        written.append(_write_text(root / slate_date / _fade_name(week), text))
    return written
