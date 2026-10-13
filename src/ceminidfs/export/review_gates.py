"""Week-4 recap gates. Each writer makes a CSV. None of them edit a projection.

The operator reads the CSV. The operator may then exclude, cap exposure, or
late-swap. These functions do not change FPPG, a lineup, or a model weight.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

QB_STARTER_NAME = "qb_starter_report.csv"
STACK_CONCENTRATION_NAME = "stack_concentration_report.csv"
CORRELATED_PAIR_NAME = "correlated_pair_report.csv"
DEFENSE_CONTEXT_NAME = "defense_context_report.csv"
PROJECTION_BANDS_NAME = "projection_bands.csv"

QB_STARTER_HEADER = [
    "player",
    "team",
    "is_qb_starter",
    "snap_share",
    "starter_change_hours",
    "flag",
    "note",
]
STACK_CONCENTRATION_HEADER = [
    "lineup_index",
    "qb",
    "partner",
    "partner_position",
    "partner_count",
    "l3_target_share",
    "adot",
    "flag",
    "note",
]
CORRELATED_PAIR_HEADER = ["te", "dst", "lineup_count", "lineup_indexes", "note"]
DEFENSE_CONTEXT_HEADER = [
    "dst",
    "team",
    "opponent",
    "pass_multiplier",
    "opp_implied_total",
    "opp_sack_pct",
    "opp_to_pct",
    "opp_fumbles_lost",
    "note",
]
PROJECTION_BANDS_HEADER = [
    "player",
    "team",
    "position",
    "salary",
    "projection",
    "p85",
    "p15",
    "flag",
    "note",
]

DO_NOT_AUTO_APPLY = "do_not_auto_apply"
SNAP_SHARE_FLOOR = 0.90
STARTER_CHANGE_HOURS = 72
LOW_TARGET_SHARE = 0.12
LOW_ADOT = 8.0
VALUE_SALARY_MAX = 5500
P15_NEAR_ZERO = 1.0
WEATHER_NOTE = "prelock_fade_only; do_not_attribute_without_pass_rate_delta"
FR_NOTE = "fr_source=opponent_fumbles_lost; display_only"

_STARTER_KEYS = ("is_qb_starter", "is qb starter")
_SNAP_KEYS = ("snap_share", "snap share", "projected_snap_share")
_CHANGE_HOUR_KEYS = ("starter_change_hours", "starter change hours")
_CHANGE_FLAG_KEYS = ("starter_changed_within_72h", "starter_change_72h")
_SHARE_KEYS = ("l3_target_share", "l3 target share", "prior_3_week_target_share")
_ADOT_KEYS = ("adot", "aDOT", "average_depth_of_target")
_P85_KEYS = ("p85", "projection p85")
_P15_KEYS = ("p15", "projection p15")
_MULT_KEYS = ("pass_multiplier", "defense_multiplier", "multiplier")
_SKILL = frozenset({"WR", "TE", "RB"})
_VALUE = frozenset({"WR", "RB"})
_DEFENSE = frozenset({"D", "DEF", "DST"})


def write_qb_starter_report(
    path: str | Path,
    lineups: Sequence[Sequence[tuple[str, str]]],
    players: Mapping[str, Any],
) -> Path:
    """Flag a rostered QB who is not a confirmed starter.

    A blank starter column is not confirmed. A snap share below 90 percent
    is a flag. A starter change at or inside 72 hours is a flag. A missing
    snap share or a missing announcement time is a note. It is not invented.
    """

    rows: list[list[str]] = []
    seen: set[str] = set()
    for seats in lineups:
        for _slot, name in seats:
            meta = _meta(players, name)
            if meta is None or not _is_qb(meta):
                continue
            key = _name_key(meta.name)
            if key in seen:
                continue
            seen.add(key)
            rows.append(_qb_row(meta))
    rows.sort(key=lambda row: (row[5] == "", row[0].lower()))
    return _write_report(path, QB_STARTER_HEADER, rows)


def write_stack_concentration_report(
    path: str | Path,
    lineups: Sequence[Sequence[tuple[str, str]]],
    players: Mapping[str, Any],
) -> Path:
    """Show each QB stack partner's prior-3-week target share.

    A partner is low-share when that share is below 0.12. A partner is
    low-aDOT when aDOT is below 8. The report does not drop the stack.
    """

    rows: list[list[str]] = []
    for index, seats in enumerate(lineups, start=1):
        rows.extend(_stack_rows(index, seats, players))
    return _write_report(path, STACK_CONCENTRATION_HEADER, rows)


def write_correlated_pair_report(
    path: str | Path,
    lineups: Sequence[Sequence[tuple[str, str]]],
    players: Mapping[str, Any],
) -> Path:
    """Flag a TE and DST pair that appears on more than one lineup."""

    groups: dict[tuple[str, str], list[int]] = {}
    for index, seats in enumerate(lineups, start=1):
        te_name, dst_name = _te_dst_pair(seats, players)
        if not te_name or not dst_name:
            continue
        groups.setdefault((te_name, dst_name), []).append(index)

    rows: list[list[str]] = []
    for (te_name, dst_name), indexes in sorted(groups.items()):
        if len(indexes) < 2:
            continue
        rows.append(
            [
                te_name,
                dst_name,
                str(len(indexes)),
                " ".join(str(item) for item in indexes),
                "identical_te_dst_pair",
            ]
        )
    return _write_report(path, CORRELATED_PAIR_HEADER, rows)


def write_defense_context_report(
    path: str | Path,
    players: Mapping[str, Any],
    *,
    implied_totals: Mapping[str, str] | None = None,
    context: Mapping[str, Any] | None = None,
) -> Path:
    """Show DST context beside the existing pass multiplier.

    The multiplier cell is copied. Opponent fumbles lost stay the fumble
    recovery input. This writer does not down-weight a DST.
    """

    totals = {str(key).upper(): str(value) for key, value in (implied_totals or {}).items()}
    payload = context or {}
    multipliers = payload.get("multipliers") or {}
    opponents = payload.get("opponents") or {}
    rows: list[list[str]] = []
    seen: set[str] = set()
    for meta in players.values():
        if not _is_defense(meta):
            continue
        key = _name_key(getattr(meta, "name", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(_defense_row(meta, totals, multipliers, opponents))
    rows.sort(key=lambda row: row[0].lower())
    return _write_report(path, DEFENSE_CONTEXT_HEADER, rows)


def write_projection_bands_report(
    path: str | Path,
    players: Mapping[str, Any],
) -> Path:
    """Put P85 and P15 beside the existing projection. Do not change it."""

    rows: list[list[str]] = []
    seen: set[str] = set()
    for meta in players.values():
        name = str(getattr(meta, "name", "") or "")
        key = _name_key(name)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(_band_row(meta))
    rows.sort(key=lambda row: (row[7] == "", row[0].lower()))
    return _write_report(path, PROJECTION_BANDS_HEADER, rows)


def opponent_context_from_pbp(pbp: Any, *, through_week: int) -> dict[str, dict[str, str]]:
    """Return sack rate, turnover rate, and fumbles lost for each offense.

    Fumbles lost are the only fumble figure. Rates use weeks before
    ``through_week``. A missing column stays blank.
    """

    import pandas as pd

    if pbp is None or getattr(pbp, "empty", True) or "posteam" not in pbp.columns:
        return {}
    frame = pbp
    if "week" in frame.columns:
        weeks = pd.to_numeric(frame["week"], errors="coerce")
        frame = frame.loc[weeks < through_week]
    if frame.empty:
        return {}

    has_fumbles = "fumble_lost" in frame.columns
    context: dict[str, dict[str, str]] = {}
    for team, group in frame.groupby(frame["posteam"].astype(str).str.upper()):
        team_code = str(team).strip().upper()
        if not team_code or team_code == "NAN":
            continue
        sacks = _flag_sum(group, "sack")
        dropbacks = _dropback_count(group)
        interceptions = _flag_sum(group, "interception")
        fumbles_lost = _flag_sum(group, "fumble_lost") if has_fumbles else 0.0
        plays = float(len(group))
        context[team_code] = {
            "sack_pct": _rate(sacks, dropbacks),
            "to_pct": _rate(interceptions + fumbles_lost, plays) if has_fumbles or "interception" in group.columns else "",
            "fumbles_lost": _count(fumbles_lost) if has_fumbles else "",
        }
    return context


def pass_multipliers_from_pbp(pbp: Any, *, through_week: int) -> dict[str, str]:
    """Copy the existing pass-side defense multiplier. Do not refit it."""

    from ceminidfs.models.defense import build_defense_ratings, defense_multiplier

    if pbp is None or getattr(pbp, "empty", True):
        return {}
    ratings = build_defense_ratings(pbp, through_week)
    multipliers: dict[str, str] = {}
    for team in ratings:
        multipliers[str(team).upper()] = f"{defense_multiplier(team, 'pass', ratings):.4f}"
    return multipliers


def load_defense_context(season: int, week: int) -> dict[str, Any]:
    """Read cached play-by-play for the defense report. Return blanks on failure."""

    try:
        from ceminidfs.pipeline.backtest import load_season_pbp

        pbp = load_season_pbp(int(season))
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"defense context: no play-by-play ({exc})", file=sys.stderr)
        return {}
    return {
        "multipliers": pass_multipliers_from_pbp(pbp, through_week=int(week)),
        "opponents": opponent_context_from_pbp(pbp, through_week=int(week)),
    }


def _qb_row(meta: Any) -> list[str]:
    starter = _pick(meta.row, _STARTER_KEYS)
    snap = _pick(meta.row, _SNAP_KEYS)
    hours = _pick(meta.row, _CHANGE_HOUR_KEYS)
    changed = _pick(meta.row, _CHANGE_FLAG_KEYS)
    flags: list[str] = []
    notes: list[str] = []
    if not _is_truthy(starter):
        flags.append("starter_not_confirmed")
    snap_value = _fraction(snap)
    if snap_value is None:
        notes.append("snap_share_missing")
    elif snap_value < SNAP_SHARE_FLOOR:
        flags.append("snap_share_below_90")
    hour_value = _number(hours)
    if hour_value is not None and hour_value <= STARTER_CHANGE_HOURS:
        flags.append("starter_change_72h")
    elif _is_truthy(changed):
        flags.append("starter_change_72h")
    else:
        notes.append("no_starter_change_timestamp")
    return [
        meta.name,
        str(getattr(meta, "team", "") or ""),
        starter,
        snap,
        hours,
        "|".join(flags),
        "; ".join(notes),
    ]


def _stack_rows(
    index: int,
    seats: Sequence[tuple[str, str]],
    players: Mapping[str, Any],
) -> list[list[str]]:
    qb_meta = None
    for _slot, name in seats:
        meta = _meta(players, name)
        if meta is not None and _is_qb(meta):
            qb_meta = meta
            break
    if qb_meta is None:
        return []
    partners: list[Any] = []
    for _slot, name in seats:
        meta = _meta(players, name)
        if meta is None or meta is qb_meta:
            continue
        if str(getattr(meta, "team", "") or "") != str(qb_meta.team or ""):
            continue
        if not _position_in(meta, _SKILL):
            continue
        partners.append(meta)
    rows: list[list[str]] = []
    for partner in partners:
        share = _pick(partner.row, _SHARE_KEYS)
        adot = _pick(partner.row, _ADOT_KEYS)
        flags: list[str] = []
        notes: list[str] = []
        share_value = _number(share)
        adot_value = _number(adot)
        if share_value is None:
            notes.append("target_share_missing")
        elif share_value < LOW_TARGET_SHARE:
            flags.append("low_target_share")
        if adot_value is None:
            notes.append("adot_missing")
        elif adot_value < LOW_ADOT:
            flags.append("low_adot")
        rows.append(
            [
                str(index),
                qb_meta.name,
                partner.name,
                str(getattr(partner, "position", "") or ""),
                str(len(partners)),
                share,
                adot,
                "|".join(flags),
                "; ".join(notes),
            ]
        )
    return rows


def _te_dst_pair(
    seats: Sequence[tuple[str, str]],
    players: Mapping[str, Any],
) -> tuple[str, str]:
    te_name = ""
    dst_name = ""
    for slot, name in seats:
        slot_name = str(slot or "").upper()
        meta = _meta(players, name)
        if slot_name == "TE" and not te_name:
            te_name = meta.name if meta is not None else name
        if slot_name in {"DEF", "DST", "D"} and not dst_name:
            dst_name = meta.name if meta is not None else name
    return te_name, dst_name


def _defense_row(
    meta: Any,
    totals: Mapping[str, str],
    multipliers: Mapping[str, str],
    opponents: Mapping[str, Mapping[str, str]],
) -> list[str]:
    team = str(getattr(meta, "team", "") or "").upper()
    opponent = _opponent(meta)
    multiplier = _pick(meta.row, _MULT_KEYS) or str(multipliers.get(team, "") or "")
    implied = str(totals.get(opponent, "") or "")
    opp = opponents.get(opponent) or {}
    notes = [FR_NOTE]
    if not multiplier:
        notes.append("multiplier_missing")
    if not implied:
        notes.append("implied_total_missing")
    return [
        meta.name,
        team,
        opponent,
        multiplier,
        implied,
        str(opp.get("sack_pct", "") or ""),
        str(opp.get("to_pct", "") or ""),
        str(opp.get("fumbles_lost", "") or ""),
        "; ".join(notes),
    ]


def _band_row(meta: Any) -> list[str]:
    projection = str(getattr(meta, "projection", "") or "")
    p85 = _pick(meta.row, _P85_KEYS)
    p15 = _pick(meta.row, _P15_KEYS)
    notes: list[str] = []
    flag = ""
    if not p85:
        notes.append("p85_missing")
    if not p15:
        notes.append("p15_missing")
    else:
        p15_value = _number(p15)
        salary = _number(str(getattr(meta, "salary", "") or ""))
        if (
            p15_value is not None
            and p15_value < P15_NEAR_ZERO
            and salary is not None
            and salary <= VALUE_SALARY_MAX
            and _position_in(meta, _VALUE)
        ):
            flag = "p15_near_zero"
    return [
        meta.name,
        str(getattr(meta, "team", "") or ""),
        str(getattr(meta, "position", "") or ""),
        str(getattr(meta, "salary", "") or ""),
        projection,
        p85,
        p15,
        flag,
        "; ".join(notes),
    ]


def _opponent(meta: Any) -> str:
    game_teams = set(getattr(meta, "game_teams", ()) or ())
    team = str(getattr(meta, "team", "") or "").upper()
    others = [item for item in game_teams if item and item != team]
    if others:
        return sorted(others)[0]
    row = getattr(meta, "row", {}) or {}
    for key in ("opponent", "opp"):
        value = str(row.get(key, "") or "").strip().upper()
        if value:
            return value
    return ""


def _meta(players: Mapping[str, Any], name: str) -> Any | None:
    key = _name_key(name)
    if key in players:
        return players[key]
    for meta in players.values():
        if _name_key(getattr(meta, "name", "")) == key:
            return meta
    return None


def _is_qb(meta: Any) -> bool:
    return _position_in(meta, frozenset({"QB"}))


def _is_defense(meta: Any) -> bool:
    return _position_in(meta, _DEFENSE)


def _position_in(meta: Any, wanted: frozenset[str]) -> bool:
    tokens = {str(getattr(meta, "position", "") or "").upper()}
    tokens.update(str(item).upper() for item in (getattr(meta, "positions", ()) or ()))
    if "DST" in tokens:
        tokens.add("D")
    return bool(tokens & wanted)


def _pick(row: Mapping[str, str], keys: Sequence[str]) -> str:
    lower = {str(key).strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = lower.get(str(key).strip().lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _name_key(name: str) -> str:
    return " ".join(str(name or "").lower().split())


def _is_truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "t"}


def _number(value: str) -> float | None:
    text = str(value or "").strip().replace("%", "").replace(",", "")
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if parsed != parsed:
        return None
    return parsed


def _fraction(value: str) -> float | None:
    parsed = _number(value)
    if parsed is None:
        return None
    if parsed > 1.5:
        return parsed / 100.0
    return parsed


def _dropback_count(frame: Any) -> float:
    import pandas as pd

    mask = pd.Series(False, index=frame.index)
    for column in ("pass_attempt", "sack"):
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        mask = mask | values.gt(0)
    return float(mask.sum())


def _flag_sum(frame: Any, column: str) -> float:
    import pandas as pd

    if column not in frame.columns:
        return 0.0
    values = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return float(values.sum())


def _rate(numerator: float, denominator: float) -> str:
    if denominator <= 0:
        return ""
    return f"{numerator / denominator:.4f}"


def _count(value: float) -> str:
    if value <= 0:
        return "0"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4f}"


def _write_report(path: str | Path, header: list[str], rows: Iterable[Sequence[str]]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"{DO_NOT_AUTO_APPLY}: {out}")
    return out
