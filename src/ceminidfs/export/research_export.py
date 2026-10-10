"""Research CSVs for CeminiParlays. No prose writer and no club-page fetch."""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from ceminidfs.data.stadiums import STADIUMS, get_stadium, normalize_team_abbr, roof_type_is_weather_exposed
from ceminidfs.data.vegas import enrich_schedules_with_vegas

ENV_COLUMNS = [
    "slate_id",
    "game_id",
    "team",
    "opp",
    "implied_total",
    "spread",
    "roof",
    "weather_exposed",
    "wind_mph",
    "precip_pop",
    "wind_source_url",
    "wind_retrieved_at",
    "precip_source_url",
    "precip_retrieved_at",
]

STATUS_DFS_COLUMNS = [
    "name",
    "team",
    "status",
    "exclude",
    "lock",
    "note",
    "source",
    "retrieved",
]
STATUS_PARLAYS_COLUMNS = ["name", "team", "status", "source", "retrieved"]

NEVER_ENTER = frozenset({"out", "ir", "inactive", "doubtful", "nfi", "pup", "suspended"})
WARN_TOKENS = frozenset({"q", "questionable", "gtd", "game-time", "limited", "dnp"})

_GAME_PAIR = re.compile(r"\b([A-Za-z]{2,4})@([A-Za-z]{2,4})\b")
_DATE_SLASH = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_DATE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_CLOCK = re.compile(r"(\d{1,2}):(\d{2})\s*([AaPp][Mm])?")
_EASTERN = ZoneInfo("America/New_York")
_USE_CACHE = object()

UrlOpener = Callable[[str], bytes | str]


def write_environment_csv(
    salary_path: str | Path,
    out_path: str | Path,
    *,
    season: int,
    week: int,
    slate_id: str | None = None,
    vegas_frame: pd.DataFrame | None | object = _USE_CACHE,
    opener: UrlOpener | None = None,
    retrieved_at: str | None = None,
) -> Path:
    """Write one environment row per salary-file team."""

    slate = slate_id or f"{season}_w{week}"
    teams = slate_teams_from_salary(salary_path, season, week)
    vegas = _vegas_by_team(_resolve_vegas_frame(vegas_frame, season, week))
    stamp = retrieved_at or datetime.now(_EASTERN).isoformat(timespec="seconds")
    weather_by_home: dict[str, dict[str, str]] = {}
    rows: list[dict[str, str]] = []
    for team in sorted(teams, key=lambda item: (teams[item]["game_id"], item)):
        info = teams[team]
        game_id = info["game_id"]
        away, _, home = game_id.partition("@")
        stadium_team = home or team
        roof, exposed = _roof_for_team(stadium_team)
        if stadium_team not in weather_by_home:
            weather_by_home[stadium_team] = _weather_for_home(
                stadium_team,
                exposed,
                info["kickoff"],
                opener=opener,
                retrieved_at=stamp,
            )
        weather = weather_by_home[stadium_team]
        implied, spread = vegas.get(team, ("", ""))
        rows.append(
            {
                "slate_id": slate,
                "game_id": game_id,
                "team": team,
                "opp": info["opp"],
                "implied_total": implied,
                "spread": spread,
                "roof": roof,
                "weather_exposed": "true" if exposed else "false",
                "wind_mph": weather["wind_mph"],
                "precip_pop": weather["precip_pop"],
                "wind_source_url": weather["wind_source_url"],
                "wind_retrieved_at": weather["wind_retrieved_at"],
                "precip_source_url": weather["precip_source_url"],
                "precip_retrieved_at": weather["precip_retrieved_at"],
            }
        )
    return _write_dict_rows(out_path, ENV_COLUMNS, rows)


def slate_teams_from_salary(
    salary_path: str | Path,
    season: int,
    week: int,
) -> dict[str, dict[str, Any]]:
    """Return one record per team on the salary file. Do not add missing teams."""

    from ceminidfs.data.salary import parse_salary_csv

    teams: dict[str, dict[str, Any]] = {}
    for row in parse_salary_csv(salary_path, season, week):
        team = normalize_team_abbr(str(row.get("team") or ""))
        opp = normalize_team_abbr(str(row.get("opp") or ""))
        if not team or team in teams:
            continue
        game_text = str(row.get("game") or "")
        game_id = game_id_from_text(game_text, team, opp)
        if not opp and "@" in game_id:
            away, _, home = game_id.partition("@")
            opp = home if team == away else away
        teams[team] = {
            "opp": opp,
            "game_id": game_id,
            "kickoff": parse_kickoff(game_text),
        }
    return teams


def game_id_from_text(game: str, team: str, opp: str) -> str:
    match = _GAME_PAIR.search(str(game or ""))
    if match:
        away = normalize_team_abbr(match.group(1))
        home = normalize_team_abbr(match.group(2))
        return f"{away}@{home}"
    if team and opp:
        return f"{normalize_team_abbr(team)}@{normalize_team_abbr(opp)}"
    return ""


def parse_kickoff(game: str) -> datetime | None:
    text = str(game or "")
    iso = _DATE_ISO.search(text)
    slash = _DATE_SLASH.search(text)
    clock = _CLOCK.search(text)
    if clock is None or (iso is None and slash is None):
        return None
    if iso:
        year, month, day = int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
    else:
        assert slash is not None
        month, day, year = int(slash.group(1)), int(slash.group(2)), int(slash.group(3))
    hour = int(clock.group(1))
    minute = int(clock.group(2))
    ampm = clock.group(3)
    if ampm:
        hour = hour % 12
        if ampm.lower() == "pm":
            hour += 12
    return datetime(year, month, day, hour, minute, tzinfo=_EASTERN)


def write_status_csvs(
    injuries_path: str | Path,
    out_dir: str | Path,
    *,
    week: int | None = None,
    retrieved_at: str | None = None,
) -> tuple[Path, Path]:
    """Write status_dfs.csv and status_parlays.csv from injuries.parquet only."""

    path = Path(injuries_path)
    if not path.is_file():
        raise FileNotFoundError(f"injuries cache not found: {path}")
    frame = pd.read_parquet(path)
    if week is not None and "week" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["week"], errors="coerce") == week]
    stamp = retrieved_at or datetime.now(_EASTERN).isoformat(timespec="seconds")
    source = str(path)
    dfs_rows: list[dict[str, str]] = []
    parlay_rows: list[dict[str, str]] = []
    for record in frame.to_dict(orient="records"):
        built = _status_row(record, source=source, retrieved=stamp)
        if built is None:
            continue
        dfs_rows.append({key: built[key] for key in STATUS_DFS_COLUMNS})
        parlay_rows.append({key: built[key] for key in STATUS_PARLAYS_COLUMNS})
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    dfs_path = _write_dict_rows(dest / "status_dfs.csv", STATUS_DFS_COLUMNS, dfs_rows)
    parlay_path = _write_dict_rows(dest / "status_parlays.csv", STATUS_PARLAYS_COLUMNS, parlay_rows)
    return dfs_path, parlay_path


def validate_environment(
    slate_path: str | Path,
    *,
    salary_path: str | Path | None = None,
    season: int = 0,
    week: int = 0,
) -> list[str]:
    """Return environment errors. An empty list means the file is valid."""

    path = Path(slate_path)
    if not path.is_file():
        return [f"environment CSV not found: {path}"]
    errors: list[str] = []
    salary_teams: dict[str, dict[str, Any]] | None = None
    salary_pairs: set[frozenset[str]] | None = None
    if salary_path is not None:
        salary_teams = slate_teams_from_salary(salary_path, season, week)
        salary_pairs = set()
        for info in salary_teams.values():
            pair = _game_pair(str(info["game_id"]))
            if pair:
                salary_pairs.add(pair)
    seen_games: set[frozenset[str]] = set()
    seen_teams: set[str] = set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            team = normalize_team_abbr(str(row.get("team") or ""))
            opp = normalize_team_abbr(str(row.get("opp") or ""))
            game_id = str(row.get("game_id") or "").strip()
            if team:
                seen_teams.add(team)
            if team not in STADIUMS:
                errors.append(f"unknown team code: {team or row.get('team')}")
            pair = _game_pair(game_id)
            row_pair = frozenset(code for code in (team, opp) if code)
            if not pair or pair != row_pair:
                errors.append(f"game_id {game_id or '(blank)'} is not {team} and {opp}")
            elif pair not in seen_games:
                seen_games.add(pair)
                if salary_pairs is not None and pair not in salary_pairs:
                    errors.append(f"game {game_id} is not on the salary file")
            errors.extend(_citation_errors(row, "wind_mph", "wind_source_url", "wind_retrieved_at"))
            errors.extend(
                _citation_errors(row, "precip_pop", "precip_source_url", "precip_retrieved_at")
            )
            errors.extend(_exposed_weather_errors(row))
    if salary_teams is not None:
        for code in salary_teams:
            if code not in seen_teams:
                errors.append(f"salary team {code} has no environment row")
    return errors


def load_team_implied_totals(path: str | Path) -> dict[str, str]:
    """Map a team code to a cited implied total. Skip a blank cell."""

    totals: dict[str, str] = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            team = normalize_team_abbr(str(row.get("team") or ""))
            total = str(row.get("implied_total") or "").strip()
            if team and total:
                totals[team] = total
    return totals


def _status_row(
    record: Mapping[str, Any],
    *,
    source: str,
    retrieved: str,
) -> dict[str, str] | None:
    name = _injury_name(record)
    if not name:
        return None
    report = _clean_cell(record.get("report_status"))
    practice = _clean_cell(record.get("practice_status"))
    report_token = known_status_token(report)
    practice_token = known_status_token(practice)
    if report_token:
        status = report_token
        note = report if report.lower() != status else ""
    elif practice_token:
        status = practice_token
        note = practice if practice.lower() != status else ""
    elif report:
        status = report
        note = ""
    elif practice:
        status = practice
        note = ""
    else:
        return None
    team = normalize_team_abbr(_clean_cell(record.get("team") or record.get("team_abbr")))
    exclude = "true" if status in NEVER_ENTER else "false"
    return {
        "name": name,
        "team": team,
        "status": status,
        "exclude": exclude,
        "lock": "false",
        "note": note,
        "source": source,
        "retrieved": retrieved,
    }


def known_status_token(text: str) -> str:
    """Map a cache status onto a known token. Return blank when the text is unknown."""

    raw = " ".join(str(text or "").strip().lower().replace("_", " ").split())
    if not raw or raw == "nan":
        return ""
    compact = raw.replace(" ", "").replace("-", "")
    phrases = (
        ("did not participate", "dnp"),
        ("didnotparticipate", "dnp"),
        ("limited participation", "limited"),
        ("questionable", "questionable"),
        ("game time decision", "gtd"),
        ("game-time", "game-time"),
        ("gametime", "game-time"),
        ("doubtful", "doubtful"),
        ("inactive", "inactive"),
        ("suspended", "suspended"),
        ("injured reserve", "ir"),
        ("non football injury", "nfi"),
        ("physically unable", "pup"),
    )
    for needle, token in phrases:
        if needle in raw or needle in compact:
            return token
    words = set(raw.replace("-", " ").split())
    if raw in {"out", "o"} or words == {"out"}:
        return "out"
    if raw in {"q"}:
        return "q"
    if raw in {"ir"}:
        return "ir"
    if raw in {"dnp"}:
        return "dnp"
    if raw in {"gtd"}:
        return "gtd"
    if raw in {"nfi"}:
        return "nfi"
    if raw in {"pup"}:
        return "pup"
    if raw in NEVER_ENTER or raw in WARN_TOKENS:
        return raw
    return ""


def _injury_name(record: Mapping[str, Any]) -> str:
    for key in ("full_name", "player_name", "player_display_name"):
        name = _clean_cell(record.get(key))
        if name:
            return name
    first = _clean_cell(record.get("first_name"))
    last = _clean_cell(record.get("last_name"))
    return " ".join(part for part in (first, last) if part)


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def _roof_for_team(team: str) -> tuple[str, bool]:
    code = normalize_team_abbr(team)
    if code not in STADIUMS:
        return "", False
    stadium = get_stadium(code)
    return stadium.roof_type, roof_type_is_weather_exposed(stadium.roof_type)


def _weather_for_home(
    home: str,
    exposed: bool,
    kickoff: datetime | None,
    *,
    opener: UrlOpener | None,
    retrieved_at: str,
) -> dict[str, str]:
    blank = {
        "wind_mph": "",
        "precip_pop": "",
        "wind_source_url": "",
        "wind_retrieved_at": "",
        "precip_source_url": "",
        "precip_retrieved_at": "",
    }
    if not exposed or kickoff is None or home not in STADIUMS:
        return blank
    stadium = get_stadium(home)
    open_fn = opener or _nws_opener
    points_url = f"https://api.weather.gov/points/{stadium.lat:.4f},{stadium.lon:.4f}"
    points = json.loads(_read_opener(open_fn, points_url))
    hourly_url = str(points.get("properties", {}).get("forecastHourly") or "")
    if not hourly_url:
        return blank
    hourly = json.loads(_read_opener(open_fn, hourly_url))
    period = _period_at(hourly.get("properties", {}).get("periods") or [], kickoff)
    if period is None:
        return blank
    wind = _wind_mph(period.get("windSpeed"))
    precip = _precip_pop(period.get("probabilityOfPrecipitation"))
    if wind:
        blank["wind_mph"] = wind
        blank["wind_source_url"] = hourly_url
        blank["wind_retrieved_at"] = retrieved_at
    if precip:
        blank["precip_pop"] = precip
        blank["precip_source_url"] = hourly_url
        blank["precip_retrieved_at"] = retrieved_at
    return blank


def _period_at(periods: list[Mapping[str, Any]], kickoff: datetime) -> Mapping[str, Any] | None:
    for period in periods:
        start = _parse_nws_time(period.get("startTime"))
        end = _parse_nws_time(period.get("endTime"))
        if start is None or end is None:
            continue
        if start <= kickoff < end:
            return period
    return None


def _parse_nws_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_EASTERN)
    return parsed


def _wind_mph(value: Any) -> str:
    match = re.search(r"(\d+(?:\.\d+)?)", str(value or ""))
    if not match:
        return ""
    return _format_number(float(match.group(1)))


def _precip_pop(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("value")
    number = _as_float(value)
    if number is None:
        return ""
    return _format_number(number)


def _nws_opener(url: str) -> bytes:
    import urllib.request

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CeminiDFS research-export",
            "Accept": "application/geo+json",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def _read_opener(opener: UrlOpener, url: str) -> str:
    payload = opener(url)
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    return str(payload)


def _resolve_vegas_frame(
    vegas_frame: pd.DataFrame | None | object,
    season: int,
    week: int,
) -> pd.DataFrame | None:
    if vegas_frame is _USE_CACHE:
        return _read_vegas_cache(season, week)
    if vegas_frame is None:
        return None
    return vegas_frame  # type: ignore[return-value]


def _read_vegas_cache(season: int, week: int) -> pd.DataFrame | None:
    from ceminidfs.data.fetch import week_cache_dir

    week_dir = week_cache_dir(season, week)
    for name in ("vegas.parquet", "schedules.parquet"):
        path = week_dir / name
        if path.is_file():
            return pd.read_parquet(path)
    return None


def _vegas_by_team(frame: pd.DataFrame | None) -> dict[str, tuple[str, str]]:
    if frame is None or frame.empty:
        return {}
    source = frame
    if "home_implied_total" not in source.columns or "spread" not in source.columns:
        source = enrich_schedules_with_vegas(source)
    found: dict[str, tuple[str, str]] = {}
    for record in source.to_dict(orient="records"):
        home = normalize_team_abbr(str(record.get("home_team") or ""))
        away = normalize_team_abbr(str(record.get("away_team") or ""))
        spread = _as_float(record.get("spread"))
        home_total = _as_float(record.get("home_implied_total"))
        away_total = _as_float(record.get("away_implied_total"))
        if home:
            found[home] = (_format_number(home_total), _format_number(spread))
        if away:
            away_spread = None if spread is None else -spread
            found[away] = (_format_number(away_total), _format_number(away_spread))
    return found


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _format_number(value: float | None) -> str:
    if value is None:
        return ""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _game_pair(game_id: str) -> frozenset[str] | None:
    match = _GAME_PAIR.fullmatch(game_id.strip())
    if not match:
        return None
    away = normalize_team_abbr(match.group(1))
    home = normalize_team_abbr(match.group(2))
    if not away or not home or away == home:
        return None
    return frozenset({away, home})


def _exposed_weather_errors(row: Mapping[str, str]) -> list[str]:
    exposed = str(row.get("weather_exposed") or "").strip().lower() == "true"
    if not exposed:
        return []
    team = row.get("team") or "?"
    errors: list[str] = []
    if not str(row.get("wind_mph") or "").strip():
        errors.append(f"{team} wind_mph is blank")
    if not str(row.get("precip_pop") or "").strip():
        errors.append(f"{team} precip_pop is blank")
    return errors


def _citation_errors(row: Mapping[str, str], value_key: str, url_key: str, time_key: str) -> list[str]:
    if not str(row.get(value_key) or "").strip():
        return []
    missing = [
        key
        for key in (url_key, time_key)
        if not str(row.get(key) or "").strip()
    ]
    if not missing:
        return []
    team = row.get("team") or "?"
    joined = ", ".join(missing)
    return [f"{team} {value_key} is filled but {joined} is blank"]


def _write_dict_rows(path: str | Path, columns: list[str], rows: list[dict[str, str]]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return out
