"""Normalize projection CSVs into pydfs-lineup-optimizer import formats."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

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
}

SITE_ALIASES = {
    "fd": "fanduel",
    "fanduel": "fanduel",
    "fan_duel": "fanduel",
    "dk": "draftkings",
    "draftkings": "draftkings",
    "draft_kings": "draftkings",
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
            else:
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
