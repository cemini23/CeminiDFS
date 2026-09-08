"""Normalize projection CSVs into pydfs-lineup-optimizer import formats."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from ceminidfs.data.availability import is_unavailable_status

PASS_THROUGH_FIELDS = [
    "Projected Ownership",
    "Projection Floor",
    "Projection Ceil",
    "coherence_risk_flag",
    "pass_protection_stress",
]

NAME_KEYS = ("name", "player", "player name", "nickname", "full name", "player_key")
FIRST_NAME_KEYS = ("first name", "firstname")
LAST_NAME_KEYS = ("last name", "lastname")
POS_KEYS = ("position", "pos", "roster position")
TEAM_KEYS = ("team", "team abbrev", "teamabbrev", "tm")
OPP_KEYS = ("opp", "opponent")
GAME_KEYS = ("game", "game info", "matchup")
INJURY_KEYS = ("injury", "injury indicator", "inj", "status", "injury_status")

SITE_FIELDS = {
    "fanduel": [
        "Id",
        "First Name",
        "Last Name",
        "Position",
        "Team",
        "Salary",
        "FPPG",
        "Game",
        "Injury Indicator",
    ],
    "draftkings": [
        "Position",
        "Name",
        "ID",
        "Roster Position",
        "Salary",
        "Game Info",
        "TeamAbbrev",
        "AvgPointsPerGame",
    ],
    "fanduel_showdown": [
        "Position",
        "Name + ID",
        "Name",
        "ID",
        "Roster Position",
        "Salary",
        "Game Info",
        "TeamAbbrev",
        "AvgPointsPerGame",
    ],
    "draftkings_showdown": [
        "Position",
        "Name + ID",
        "Name",
        "ID",
        "Roster Position",
        "Salary",
        "Game Info",
        "TeamAbbrev",
        "AvgPointsPerGame",
    ],
}

# 2026 single-game sites emit a DraftKings captain-mode CSV (pydfs
# Site.DRAFTKINGS_CAPTAIN_MODE): each eligible player gets CPT (1.5x salary,
# base FPPG — pydfs multiplies FPPG by 1.5) and FLEX (1x) rows sharing an ID.
SHOWDOWN_SITES = frozenset({"fanduel_showdown", "draftkings_showdown"})

SITE_ALIASES = {
    "fd": "fanduel",
    "fanduel": "fanduel",
    "fan_duel": "fanduel",
    "dk": "draftkings",
    "draftkings": "draftkings",
    "draft_kings": "draftkings",
    "fd_showdown": "fanduel_showdown",
    "fanduel_showdown": "fanduel_showdown",
    "fd_single": "fanduel_showdown",
    "dk_showdown": "draftkings_showdown",
    "dk_captain": "draftkings_showdown",
    "draftkings_showdown": "draftkings_showdown",
    "draftkings_captain": "draftkings_showdown",
}

SITE_KEYS = {
    "fanduel": {
        "id": ("fd_id", "id", "player id", "player_id", "fanduel id"),
        "position": ("fd_position", "fd pos", "fd roster position", *POS_KEYS),
        "salary": ("fd_salary", "fd salary", "fanduel salary", "salary", "sal"),
        "projection": (
            "fd_projection",
            "fd pts",
            "fppg",
            "projection",
            "proj",
            "points",
            "fantasy points",
            "median",
        ),
    },
    "draftkings": {
        "id": ("dk_id", "id", "player id", "player_id", "draftkings id"),
        "position": ("dk_position", "dk pos", "dk roster position", *POS_KEYS),
        "salary": ("dk_salary", "dk salary", "draftkings salary", "salary", "sal"),
        "projection": (
            "dk_projection",
            "dk pts",
            "avgpointspergame",
            "avg points per game",
            "fppg",
            "projection",
            "proj",
            "points",
            "fantasy points",
            "median",
        ),
        "roster_position": ("roster position", "dk_roster_position", "dk roster position"),
    },
    "fanduel_showdown": {
        "id": ("fd_id", "id", "player id", "player_id", "fanduel id"),
        "position": ("fd_position", "fd pos", "fd roster position", *POS_KEYS),
        # FLEX salary is the 1x lobby price (SalaryFlex / SalaryMVP pair).
        "salary": (
            "salaryflex",
            "salary flex",
            "salary_flex",
            "fd_salary",
            "fd salary",
            "fanduel salary",
            "salary",
            "sal",
        ),
        "projection": (
            "fd_projection",
            "fd pts",
            "fppg",
            "projection",
            "proj",
            "points",
            "fantasy points",
            "median",
        ),
        "roster_position": (
            "roster position",
            "fd_roster_position",
            "fd roster position",
            "fd slot",
        ),
    },
    "draftkings_showdown": {
        "id": ("dk_id", "id", "player id", "player_id", "draftkings id"),
        "position": ("dk_position", "dk pos", "dk roster position", *POS_KEYS),
        "salary": (
            "dk_salary",
            "dk salary",
            "draftkings salary",
            "salaryflex",
            "salary flex",
            "salary",
            "sal",
        ),
        "projection": (
            "dk_projection",
            "dk pts",
            "avgpointspergame",
            "avg points per game",
            "fppg",
            "projection",
            "proj",
            "points",
            "fantasy points",
            "median",
        ),
        "roster_position": ("roster position", "dk_roster_position", "dk roster position"),
    },
}


def normalize_site(site: str) -> str:
    """Return the canonical site key for supported DFS sites."""

    normalized = SITE_ALIASES.get(site.strip().lower())
    if not normalized:
        supported = ", ".join(sorted(set(SITE_ALIASES.values())))
        raise ValueError(f"Unsupported site {site!r}; expected one of: {supported}")
    return normalized


def pick(row: dict[str, str], keys: tuple[str, ...]) -> str:
    """Pick the first non-empty value from a row using case-insensitive keys."""

    lower = {k.strip().lower(): v for k, v in row.items()}
    for key in keys:
        value = lower.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def split_name(full: str) -> tuple[str, str]:
    """Split a display name into pydfs FanDuel first/last fields."""

    parts = full.strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[0], parts[1]


def _full_name(row: dict[str, str]) -> str:
    name = pick(row, NAME_KEYS)
    if name:
        return name
    first = pick(row, FIRST_NAME_KEYS)
    last = pick(row, LAST_NAME_KEYS)
    return " ".join(part for part in (first, last) if part).strip()


def _clean_money(value: str) -> str:
    return value.replace("$", "").replace(",", "").strip()


def _game(row: dict[str, str]) -> str:
    game = pick(row, GAME_KEYS)
    if game:
        return game
    team = pick(row, TEAM_KEYS)
    opp = pick(row, OPP_KEYS)
    return f"{team}@{opp}" if team and opp else ""


def _site_position(pos: str, site_key: str) -> str:
    normalized = pos.upper()
    if normalized in {"DEF", "DST", "D"}:
        return "D" if site_key == "fanduel" else "DST"
    return normalized


def _captain_csv_row(
    *,
    name: str,
    player_id: str,
    team: str,
    game: str,
    pos: str,
    roster_position: str,
    salary: int,
    projection: str,
) -> dict[str, str]:
    """One DraftKings captain-mode CSV row (Roster Position CPT or FLEX)."""
    return {
        "Position": pos,
        "Name + ID": f"{name} ({player_id})",
        "Name": name,
        "ID": player_id,
        "Roster Position": roster_position,
        "Salary": str(salary),
        "Game Info": game,
        "TeamAbbrev": team,
        "AvgPointsPerGame": projection,
    }


def _emit_captain_rows(
    row: dict[str, str],
    *,
    site_key: str,
    keys: dict[str, tuple[str, ...]],
    name: str,
    player_id: str,
    team: str,
    game: str,
    pos: str,
    salary: str,
    projection: str,
) -> list[dict[str, str]]:
    """Emit captain-mode rows for one player (shared by showdown sites).

    draftkings_showdown passes through input rows that already carry a
    Roster Position of CPT/FLEX (the DK export is already doubled at 1.5x for
    CPT) instead of doubling again. Everything else doubles: a CPT row at
    round(flex * 1.5) salary plus a FLEX row at the 1x salary, sharing one ID.
    """
    flex = int(salary or 0)
    roster = ""
    if site_key == "draftkings_showdown":
        roster = pick(row, keys["roster_position"]).upper()

    if roster in ("CPT", "FLEX"):
        return [
            _captain_csv_row(
                name=name,
                player_id=player_id,
                team=team,
                game=game,
                pos=pos,
                roster_position=roster,
                salary=flex,
                projection=projection,
            )
        ]
    return [
        _captain_csv_row(
            name=name,
            player_id=player_id,
            team=team,
            game=game,
            pos=pos,
            roster_position="CPT",
            salary=round(flex * 1.5),
            projection=projection,
        ),
        _captain_csv_row(
            name=name,
            player_id=player_id,
            team=team,
            game=game,
            pos=pos,
            roster_position="FLEX",
            salary=flex,
            projection=projection,
        ),
    ]


def _with_pass_through(row: dict[str, str], out_row: dict[str, str]) -> dict[str, str]:
    for field in PASS_THROUGH_FIELDS:
        value = pick(row, (field.lower(), field))
        if value:
            out_row[field] = value
    return out_row


def normalize_csv(inp_path: str | Path, out_path: str | Path, site: str = "fanduel") -> int:
    """Normalize a projection CSV to a pydfs importer CSV and return row count."""

    site_key = normalize_site(site)
    keys = SITE_KEYS[site_key]
    inp = Path(inp_path)
    out = Path(out_path)
    if not inp.is_file():
        raise FileNotFoundError(f"CSV not found: {inp}")

    rows_out: list[dict[str, str]] = []
    auto_id = 100000
    with inp.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("empty CSV")

        for row in reader:
            name = _full_name(row)
            pos = _site_position(pick(row, keys["position"]), site_key)
            salary = _clean_money(pick(row, keys["salary"]))
            projection = pick(row, keys["projection"]) or "0"
            team = pick(row, TEAM_KEYS) or "UNK"
            game = _game(row)
            player_id = pick(row, keys["id"]) or str(auto_id)

            if not name or not pos or not salary:
                continue
            if is_unavailable_status(pick(row, INJURY_KEYS)):
                continue

            if site_key == "fanduel":
                first, last = split_name(name)
                mapped = {
                    "Id": player_id,
                    "First Name": first,
                    "Last Name": last,
                    "Position": pos,
                    "Team": team,
                    "Salary": salary,
                    "FPPG": projection,
                    "Game": game,
                    "Injury Indicator": pick(row, INJURY_KEYS),
                }
                rows_out.append(_with_pass_through(row, mapped))
            elif site_key == "draftkings":
                roster_position = pick(row, keys["roster_position"]).upper() or pos
                mapped = {
                    "Position": pos,
                    "Name": name,
                    "ID": player_id,
                    "Roster Position": roster_position,
                    "Salary": salary,
                    "Game Info": game,
                    "TeamAbbrev": team,
                    "AvgPointsPerGame": projection,
                }
                rows_out.append(_with_pass_through(row, mapped))
            else:
                # Showdown: DK captain-mode CSV (two rows per player, shared ID).
                for mapped in _emit_captain_rows(
                    row,
                    site_key=site_key,
                    keys=keys,
                    name=name,
                    player_id=player_id,
                    team=team,
                    game=game,
                    pos=pos,
                    salary=salary,
                    projection=projection,
                ):
                    rows_out.append(_with_pass_through(row, mapped))

            auto_id += 1

    if not rows_out:
        raise ValueError("no rows mapped; check column headers")

    fieldnames = list(SITE_FIELDS[site_key])
    for field in PASS_THROUGH_FIELDS:
        if any(field in row for row in rows_out):
            fieldnames.append(field)

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    return len(rows_out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize DFS projections for pydfs")
    parser.add_argument("--in", dest="inp", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--site", default="fanduel", choices=sorted(SITE_ALIASES))
    args = parser.parse_args()

    try:
        count = normalize_csv(args.inp, args.out, site=args.site)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Normalized {count} players -> {Path(args.out)} ({normalize_site(args.site)} pydfs format)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
