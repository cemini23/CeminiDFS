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
from typing import Mapping, Sequence

import pandas as pd

from ceminidfs.data.stadiums import normalize_team_abbr

CHEAP_SALARY = 4800
CHEAP_PLAYED = 3
CHEAP_FPPG = 4.5
RB_TOUCH_FLOOR = 4
RECEIVER_TARGET_FLOOR = 3
SKILL_POSITIONS = frozenset({"RB", "WR", "TE"})
WR_TE_CAP = 42
RB_CAP = 45
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


def opportunity_blocked(position: object, targets: int, carries: int) -> bool:
    """True when the last two active games miss the touch floor."""

    pos = canon_position(position)
    if pos == "RB":
        return int(targets) + int(carries) < RB_TOUCH_FLOOR
    if pos in {"WR", "TE"}:
        return int(targets) < RECEIVER_TARGET_FLOOR
    return False


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
) -> bool:
    """True when G1 or G3 removes this skill player. A whitelist name stays."""

    pos = canon_position(position)
    if pos not in SKILL_POSITIONS:
        return False
    allowed = {fold_key(item) for item in (whitelist or ())}
    if fold_key(name) in allowed:
        return False
    if roster_excluded(
        status=roster_status,
        snaps=0 if snaps is None else snaps,
        starter_note=starter_note or fold_key(name) in allowed,
        roster_fresh=roster_fresh,
    ) and (roster_fresh or snaps is not None):
        if roster_fresh and inactive_roster_status(roster_status):
            return True
        if snaps is not None and snaps <= 0 and not starter_note:
            return True
    if targets is not None and carries is not None and opportunity_blocked(pos, targets, carries):
        return True
    return cheap_season_blocked(pos, salary, played, fppg)


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


def highest_salary_starters(frame: pd.DataFrame) -> dict[str, str]:
    """Pick the highest-salary active quarterback on each team."""

    if frame.empty:
        return {}
    blocked = {"O", "OUT", "IR", "D", "DOUBTFUL", "PUP", "NFI", "SUS", "SUSPENDED"}
    best: dict[str, tuple[int, str]] = {}
    for record in frame.to_dict(orient="records"):
        if canon_position(record.get("Position") or record.get("position")) != "QB":
            continue
        status = str(record.get("Injury Indicator") or record.get("injury_indicator") or "").strip().upper()
        if status in blocked:
            continue
        team = normalize_team_abbr(str(record.get("Team") or record.get("team") or ""))
        name = str(record.get("Nickname") or record.get("nickname") or "").strip()
        if not team or not name:
            continue
        try:
            salary = int(float(record.get("Salary") or record.get("salary") or 0))
        except (TypeError, ValueError):
            salary = 0
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
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        written.append(dest)
    return written


@dataclass(frozen=True)
class Opportunity:
    targets: int
    carries: int
    snaps: int


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


def build_opportunity_index(
    pbp: pd.DataFrame,
    rosters: pd.DataFrame | None = None,
    *,
    season: int = 2026,
    before_week: int = 8,
    active_games: int = 2,
    snap_games: int = 3,
) -> OpportunityIndex:
    """Sum targets, carries, and snaps before the slate week.

    Targets and carries use the player's last two games with a touch.
    Snaps use the team's last three played weeks.
    """

    if pbp is None or pbp.empty:
        return OpportunityIndex(by_name={}, active_teams=frozenset())
    frame = pbp.copy()
    if "season" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["season"], errors="coerce").eq(int(season))].copy()
    frame["week"] = pd.to_numeric(frame.get("week"), errors="coerce")
    frame = frame.loc[frame["week"].lt(int(before_week)) & frame["week"].notna()].copy()
    if frame.empty or "posteam" not in frame.columns:
        return OpportunityIndex(by_name={}, active_teams=frozenset())
    frame["team"] = frame["posteam"].map(_club)
    frame = frame.loc[frame["team"].ne("")].copy()
    active = frozenset(frame["team"].dropna().astype(str))
    if frame.empty:
        return OpportunityIndex(by_name={}, active_teams=active)

    names: dict[str, set[str]] = defaultdict(set)
    if rosters is not None and not rosters.empty and "gsis_id" in rosters.columns:
        for record in rosters.to_dict(orient="records"):
            gsis = str(record.get("gsis_id") or "")
            if not gsis:
                continue
            for column in ("full_name", "football_name"):
                names[gsis] |= name_keys(record.get(column))
            full = f"{record.get('first_name') or ''} {record.get('last_name') or ''}".strip()
            names[gsis] |= name_keys(full)

    # (team, gsis, week) -> [targets, carries, snaps]
    cells: dict[tuple[str, str, int], list[int]] = defaultdict(lambda: [0, 0, 0])
    team_weeks: dict[str, set[int]] = defaultdict(set)

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
    by_name: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    for (team, gsis), rows in by_player.items():
        rows.sort()
        active_rows = [row for row in rows if row[1] + row[2] > 0]
        chosen = active_rows[-int(active_games) :]
        targets = sum(row[1] for row in chosen)
        carries = sum(row[2] for row in chosen)
        window = snap_window.get(team, set())
        snaps = sum(row[3] for row in rows if row[0] in window)
        for key in names.get(gsis, set()):
            bucket = by_name[(team, key)]
            bucket[0] += int(targets)
            bucket[1] += int(carries)
            bucket[2] += int(snaps)
    packed = {
        key: Opportunity(targets=values[0], carries=values[1], snaps=values[2])
        for key, values in by_name.items()
    }
    return OpportunityIndex(by_name=packed, active_teams=active)


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
