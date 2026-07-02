"""Season schedule data (byes + W17) — nflreadpy cache with hardcoded 2026 fallback."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

WEEK_BYES: Final[dict[int, list[str]]] = {
    5: ["CAR", "KC"],
    6: ["CIN", "DET", "MIA", "MIN"],
    7: ["BUF", "JAX", "LAC", "WAS"],
    8: ["HOU", "NO", "NYG", "SF"],
    9: ["PIT", "TEN"],
    10: ["CHI", "DEN", "PHI", "TB"],
    11: ["ATL", "CLE", "GB", "LAR", "NE", "SEA"],
    12: [],
    13: ["BAL", "IND", "LV", "NYJ"],
    14: ["ARI", "DAL"],
}

BYE_WEEKS_2026: Final[dict[str, int]] = {
    team: week for week, teams in WEEK_BYES.items() for team in teams
}


# 2026 Week 17 matchups (BBM championship week). Refresh each season;
WEEK17_MATCHUPS_2026: Final[list[tuple[str, str]]] = [
    ("KC", "DEN"), ("CAR", "TB"), ("CIN", "PIT"), ("MIA", "NYJ"),
    ("DET", "SF"), ("MIN", "GB"), ("BUF", "NE"), ("LAC", "LV"),
    ("WAS", "DAL"), ("JAX", "TEN"), ("NYG", "IND"), ("NO", "ARI"),
    ("HOU", "BAL"), ("CHI", "SEA"), ("PHI", "ATL"), ("CLE", "LAR"),
]


DEFAULT_SEASON: Final[int] = 2026
_SCHEDULE_LOADERS: Final[tuple[str, ...]] = ("load_schedules", "import_schedules")


def get_schedule_cache_path(season: int = DEFAULT_SEASON) -> Path:
    """JSON cache written by `ceminidfs bbm refresh-schedule` (data/bbm is not git-tracked)."""
    return Path("data/bbm") / f"schedule_{season}.json"


def _require_nflreadpy() -> Any:
    """Return the nflreadpy module or raise a clear ImportError."""
    try:
        import nflreadpy

        return nflreadpy
    except ImportError as exc:
        raise ImportError(
            "Install nflreadpy with `pip install nflreadpy` to fetch schedule data."
        ) from exc


def _call_loader(module: Any, loaders: tuple[str, ...], season: int) -> Any:
    """Try loader functions by name; fall back to loader(seasons=season) on TypeError."""
    for loader_name in loaders:
        loader = getattr(module, loader_name, None)
        if loader is None:
            continue
        try:
            return loader(season=season)
        except TypeError:
            return loader(seasons=season)
    raise ImportError("nflreadpy module has no recognized schedule loader")


def _frame_to_dicts(data: Any) -> list[dict[str, Any]]:
    """Convert a Polars/Pandas/iterable frame to a list of row dicts without pandas."""
    if hasattr(data, "to_dicts"):
        return list(data.to_dicts())
    if hasattr(data, "to_dict"):
        try:
            return list(data.to_dict("records"))
        except (TypeError, ValueError, AttributeError):
            pass
    try:
        return list(data)
    except TypeError:
        return list(iter(data))


def _is_complete(data: dict[str, Any]) -> bool:
    """True when the fetched cache has enough byes and W17 matchups."""
    return len(data.get("bye_weeks", {})) >= 28 and len(data.get("week17_matchups", [])) >= 14


def fetch_season_schedule(season: int = DEFAULT_SEASON) -> dict[str, Any]:
    """Fetch REG-season schedule via nflreadpy; derive per-team byes + W17 pairs.

    Raises ImportError (install hint) if nflreadpy is missing, ValueError if the
    fetched season looks incomplete (schedule not published yet).
    """
    module = _require_nflreadpy()
    data = _call_loader(module, _SCHEDULE_LOADERS, season)
    rows = _frame_to_dicts(data)

    weeks_played: defaultdict[str, set[int]] = defaultdict(set)
    week17_matchups: list[tuple[str, str]] = []
    max_week = 0

    for row in rows:
        if str(row.get("game_type", "")).strip().upper() != "REG":
            continue
        if int(row.get("season", 0)) != season:
            continue

        week = int(row.get("week", 0))
        if week <= 0:
            continue

        home = str(row.get("home_team", "")).strip().upper()
        away = str(row.get("away_team", "")).strip().upper()
        if not home or not away:
            continue

        weeks_played[home].add(week)
        weeks_played[away].add(week)
        if week > max_week:
            max_week = week

        if week == 17:
            week17_matchups.append((away, home))

    if max_week < 17:
        raise ValueError(
            f"{season} schedule incomplete (max_week={max_week}) — season not published yet?"
        )

    all_weeks = set(range(1, max_week + 1))
    bye_weeks: dict[str, int] = {}
    for team, weeks in weeks_played.items():
        missing = sorted(all_weeks - weeks)
        if len(missing) == 1:
            bye_weeks[team] = missing[0]

    result = {
        "season": season,
        "fetched": date.today().isoformat(),
        "bye_weeks": bye_weeks,
        "week17_matchups": [list(pair) for pair in week17_matchups],
    }

    if not _is_complete(result):
        raise ValueError(
            f"{season} schedule incomplete ({len(bye_weeks)} byes, "
            f"{len(week17_matchups)} W17 games) — season not published yet?"
        )

    return result


def save_schedule_cache(data: dict[str, Any], path: Path | None = None) -> Path:
    """Write a schedule dict to the JSON cache."""
    target = path or get_schedule_cache_path(data.get("season", DEFAULT_SEASON))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return target


def load_schedule_cache(
    season: int = DEFAULT_SEASON, path: Path | None = None
) -> dict[str, Any] | None:
    """Load a cached schedule dict, or None if missing/invalid/incomplete."""
    target = path or get_schedule_cache_path(season)
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None

    if data.get("season") != season:
        return None

    if not _is_complete(data):
        return None

    return data


def clear_schedule_memo() -> None:
    """Clear the lru_cache used by the active schedule resolver."""
    _active_schedule.cache_clear()


@lru_cache(maxsize=1)
def _active_schedule() -> tuple[dict[str, int], tuple[tuple[str, str], ...], str]:
    """(bye_weeks, w17_matchups, source) — 'cache' when a valid JSON cache exists, else 'hardcoded'."""
    cached = load_schedule_cache(DEFAULT_SEASON)
    if cached is not None:
        byes = {str(t).upper(): int(w) for t, w in cached["bye_weeks"].items()}
        w17 = tuple((str(a).upper(), str(b).upper()) for a, b in cached["week17_matchups"])
        return byes, w17, "cache"
    return dict(BYE_WEEKS_2026), tuple(WEEK17_MATCHUPS_2026), "hardcoded"


def get_schedule_source() -> str:
    """'cache' when serving data/bbm/schedule_<season>.json, else 'hardcoded'."""
    return _active_schedule()[2]


def get_bye_week(team: str) -> int | None:
    """Return the 2026 bye week for a team abbreviation."""
    return _active_schedule()[0].get(team.strip().upper())


def get_week17_matchups() -> list[tuple[str, str]]:
    """Return W17 matchup pairs for bring-back stacking."""
    return list(_active_schedule()[1])


def are_opponents_week17(team_a: str, team_b: str) -> bool:
    """True if the two teams play each other in Week 17."""
    a, b = team_a.strip().upper(), team_b.strip().upper()
    return any({a, b} == {t1, t2} for t1, t2 in _active_schedule()[1])
