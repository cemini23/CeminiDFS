"""Human-gate review CSVs written after a lineup solve (or from `ceminidfs review`).

Flags default off. Writers never change lineup files, never drop Q from the
optimizer pool, and never call late_swap_lineups. `do_not_auto_apply` is
process: print a one-line path after each write.
"""

from __future__ import annotations

import csv
import itertools
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence

from ceminidfs.export.handoff import (
    HANDOFF_COLUMNS,
    HandoffContext,
    HandoffInputError,
    PlayerHandoff,
    build_handoff_context,
    normalize_handoff_name,
)
from ceminidfs.export.lineup_report import lineup_stack_badges
from ceminidfs.export.normalize import normalize_site
from ceminidfs.export.optimize import LINEUP_HEADERS
from ceminidfs.models.ownership import (
    load_ownership_calibration,
    project_ownership,
    project_ownership_calibrated,
)


PARLAYS_HANDOFF_NAME = "ceminidfs_handoff.csv"
# The upgraded player-level contract. Imported so the CLI, tests, and the writer
# share one source of truth. See ``ceminidfs.export.handoff``.
PARLAYS_HANDOFF_HEADER = list(HANDOFF_COLUMNS)

STACK_FRAGILITY_NAME = "stack_fragility_report.csv"
LATE_SWAP_ALERT_NAME = "late_swap_alert_report.csv"
LEVERAGE_FADE_NAME = "leverage_fade_matrix.csv"
DUPLICATE_CORE_NAME = "duplicate_core_report.csv"
DART_CEILING_NAME = "dart_ceiling_rank.csv"
DART_SALARY_MAX = 5500

STACK_FRAGILITY_HEADER = [
    "lineup_index",
    "game",
    "wr_names",
    "wr_count",
    "chalk_qb_wr_wr",
    "note",
]
LATE_SWAP_ALERT_HEADER = ["player", "injury", "lineup_count", "teams", "kickoff_hint"]
LEVERAGE_FADE_HEADER = [
    "player",
    "lineup_exposure_pct",
    "projected_own_pct",
    "leverage",
    "flag",
    "jev_proj_own",
    "player_leverage_ratio",
    "jev_regime_top_state",
    "jev_provider",
]
DUPLICATE_CORE_HEADER = [
    "qb",
    "rb_a",
    "rb_b",
    "lineup_count",
    "lineup_indexes",
    "note",
    "players",
]
CASH_BUCKET_NAME = "cash_bucket_report.csv"
CASH_BUCKET_HEADER = [
    "bucket",
    "rank_low",
    "rank_high",
    "count",
    "score_min",
    "score_max",
    "score_median",
    "cash_count",
    "cash_rate_pct",
]
DEFAULT_CASH_BUCKETS = ((1, 20), (21, 40), (41, 100), (101, 150))
_RANK_KEYS = ("rank", "score_rank_of_150", "rank_of_150", "Score Rank", "place")
_SCORE_KEYS = ("score", "computed_fd", "points", "total", "fd_points", "Score")
_CASH_KEYS = ("cashed", "cashed_inferred", "won", "win", "cash")
DART_CEILING_HEADER = [
    "player",
    "team",
    "position",
    "salary",
    "mean",
    "ceiling",
    "mean_rank",
    "ceiling_rank",
    "note",
]

DO_NOT_AUTO_APPLY = "do_not_auto_apply"
FIVE_CORE_NOTE = "five_core"
FIVE_CORE_CAP_NOTE = "five_core_over_cap"
# A 5-player core that appears fewer than this many times is noise, not a signal.
FIVE_CORE_REPORT_MIN = 5
SHARED_NAMES_NOTE = "shared_names"
SHARED_NAME_MIN = 4
NEGATIVE_LEVERAGE = "NEGATIVE_LEVERAGE"
CHALK_BADGE = "CHALK-QB-WR-WR"
OWN_FLAG_MIN_PCT = 20.0

_CELL_ID_SUFFIX = re.compile(r"\s*\(([^)]+)\)\s*$")
_ID_ONLY = re.compile(r"^[0-9]+(?:-[0-9]+)?$")
_GAME_PAIR = re.compile(r"\b([A-Z]{2,3})@([A-Z]{2,3})\b")
_Q_OR_D = frozenset({"Q", "QUESTIONABLE", "D", "DOUBTFUL"})
_NAME_KEYS = (
    "nickname",
    "name",
    "player",
    "player name",
    "player_name",
    "full name",
    "full_name",
)
_TEAM_KEYS = ("team", "team abbrev", "teamabbrev", "tm", "fd_team", "dk_team")
_POS_KEYS = ("position", "pos", "roster position", "fd_position", "dk_position")
_INJURY_KEYS = ("injury indicator", "injury", "inj", "status", "injury_status")
_GAME_KEYS = ("game", "game info", "matchup")
_ID_KEYS = ("id", "player id", "player_id", "fd_id", "dk_id")
_OWN_KEYS = ("projected ownership", "ownership", "own%", "own")
_SALARY_KEYS = ("salary", "fd_salary", "dk_salary")
_PROJ_KEYS = (
    "fppg",
    "projection",
    "avgpointspergame",
    "avg points per game",
    "fd_projection",
    "dk_projection",
)
_CEILING_KEYS = ("projection ceil", "ceiling", "ceil", "proj_ceiling", "fd_ceiling")
_OPP_KEYS = ("opp", "opponent")
CEILING_MISSING = "ceiling_missing"


@dataclass
class PlayerMeta:
    name: str
    team: str = ""
    position: str = ""
    positions: frozenset[str] = field(default_factory=frozenset)
    injury: str = ""
    game_raw: str = ""
    game_id: str = ""
    game_teams: frozenset[str] = field(default_factory=frozenset)
    player_id: str = ""
    salary: str = ""
    projection: str = ""
    projected_own: str = ""
    row: dict[str, str] = field(default_factory=dict)


def maybe_write_review_reports(
    lineups_path: str | Path,
    players_path: str | Path,
    *,
    site: str = "fanduel",
    out_dir: str | Path | None = None,
    flag_wr_triples: bool = False,
    late_swap_audit: bool = False,
    ownership_fade_report: bool = False,
    ownership_calibration: str | Path | None = None,
    flag_duplicate_cores: bool = False,
    dart_ceiling_report: bool = False,
    flag_qb_starter: bool = False,
    flag_stack_concentration: bool = False,
    flag_correlated_pairs: bool = False,
    defense_context_report: bool = False,
    projection_bands: bool = False,
    environment: str | Path | None = None,
    season: int | None = None,
    week: int | None = None,
    core_cap: int | None = None,
    handoff_context: HandoffContext | None = None,
    build_handoff: bool = True,
) -> list[Path]:
    """Write the selected review CSVs next to the lineup file (or into ``out_dir``)."""

    lineups_file = Path(lineups_path)
    players_file = Path(players_path)
    if not lineups_file.is_file():
        raise FileNotFoundError(f"Lineups CSV not found: {lineups_file}")
    if not players_file.is_file():
        raise FileNotFoundError(f"Players CSV not found: {players_file}")

    site_key = normalize_site(site)
    dest = Path(out_dir) if out_dir is not None else lineups_file.parent
    dest.mkdir(parents=True, exist_ok=True)

    players = load_player_index(players_file)
    lineups = parse_lineup_csv(lineups_file, site=site_key, players=players)
    implied_totals = _implied_totals_from_environment(environment)

    context = handoff_context
    if context is None and build_handoff:
        context = _build_handoff_context(dest)

    written: list[Path] = []
    written.append(
        write_parlays_handoff(
            dest / PARLAYS_HANDOFF_NAME,
            lineups,
            players,
            implied_totals=implied_totals,
            context=context,
        )
    )

    if flag_wr_triples:
        written.append(write_stack_fragility_report(dest / STACK_FRAGILITY_NAME, lineups, players))
    if late_swap_audit:
        written.append(write_late_swap_alert_report(dest / LATE_SWAP_ALERT_NAME, lineups, players))
    if ownership_fade_report:
        written.append(
            write_leverage_fade_matrix(
                dest / LEVERAGE_FADE_NAME,
                lineups,
                players,
                site=site_key,
                calibration_path=ownership_calibration,
                context=context,
            )
        )
    if flag_duplicate_cores:
        written.append(
            write_duplicate_core_report(
                dest / DUPLICATE_CORE_NAME,
                lineups,
                core_cap=core_cap,
            )
        )
    if dart_ceiling_report:
        written.append(write_dart_ceiling_rank(dest / DART_CEILING_NAME, players))
    written.extend(
        _write_week4_gates(
            dest,
            lineups,
            players,
            implied_totals=implied_totals,
            flag_qb_starter=flag_qb_starter,
            flag_stack_concentration=flag_stack_concentration,
            flag_correlated_pairs=flag_correlated_pairs,
            defense_context_report=defense_context_report,
            projection_bands=projection_bands,
            season=season,
            week=week,
        )
    )
    return written


def _write_week4_gates(
    dest: Path,
    lineups: list[list[tuple[str, str]]],
    players: Mapping[str, PlayerMeta],
    *,
    implied_totals: Mapping[str, str] | None,
    flag_qb_starter: bool,
    flag_stack_concentration: bool,
    flag_correlated_pairs: bool,
    defense_context_report: bool,
    projection_bands: bool,
    season: int | None,
    week: int | None,
) -> list[Path]:
    """Write the Week-4 gates. A gate reports. It does not edit a projection."""

    from ceminidfs.export.review_gates import (
        CORRELATED_PAIR_NAME,
        DEFENSE_CONTEXT_NAME,
        PROJECTION_BANDS_NAME,
        QB_STARTER_NAME,
        STACK_CONCENTRATION_NAME,
        load_defense_context,
        write_correlated_pair_report,
        write_defense_context_report,
        write_projection_bands_report,
        write_qb_starter_report,
        write_stack_concentration_report,
    )

    written: list[Path] = []
    if flag_qb_starter:
        written.append(write_qb_starter_report(dest / QB_STARTER_NAME, lineups, players))
    if flag_stack_concentration:
        written.append(
            write_stack_concentration_report(dest / STACK_CONCENTRATION_NAME, lineups, players)
        )
    if flag_correlated_pairs:
        written.append(write_correlated_pair_report(dest / CORRELATED_PAIR_NAME, lineups, players))
    if defense_context_report:
        context = {}
        if season is not None and week is not None:
            context = load_defense_context(int(season), int(week))
        written.append(
            write_defense_context_report(
                dest / DEFENSE_CONTEXT_NAME,
                players,
                implied_totals=implied_totals,
                context=context,
            )
        )
    if projection_bands:
        written.append(write_projection_bands_report(dest / PROJECTION_BANDS_NAME, players))
    return written


def pop_review_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Pull review-report kwargs out of an optimizer ``**kwargs`` mapping."""

    return {
        "flag_wr_triples": bool(kwargs.pop("flag_wr_triples", False)),
        "late_swap_audit": bool(kwargs.pop("late_swap_audit", False)),
        "ownership_fade_report": bool(kwargs.pop("ownership_fade_report", False)),
        "ownership_calibration": kwargs.pop("ownership_calibration", None),
        "flag_duplicate_cores": bool(kwargs.pop("flag_duplicate_cores", False)),
        "dart_ceiling_report": bool(kwargs.pop("dart_ceiling_report", False)),
        "flag_qb_starter": bool(kwargs.pop("flag_qb_starter", False)),
        "flag_stack_concentration": bool(kwargs.pop("flag_stack_concentration", False)),
        "flag_correlated_pairs": bool(kwargs.pop("flag_correlated_pairs", False)),
        "defense_context_report": bool(kwargs.pop("defense_context_report", False)),
        "projection_bands": bool(kwargs.pop("projection_bands", False)),
        "environment": kwargs.pop("environment", None),
        "season": kwargs.pop("season", None),
        "week": kwargs.pop("week", None),
        "core_cap": kwargs.pop("core_cap", None),
        "handoff_context": kwargs.pop("handoff_context", None),
        "build_handoff": bool(kwargs.pop("build_handoff", True)),
    }


def parse_lineup_csv(
    path: str | Path,
    *,
    site: str = "fanduel",
    players: Mapping[str, PlayerMeta] | None = None,
) -> list[list[tuple[str, str]]]:
    """Return lineups as lists of ``(slot, display_name)``. Uses ``csv.reader``."""

    site_key = normalize_site(site)
    header = LINEUP_HEADERS[site_key]
    index = players or {}
    lineups: list[list[tuple[str, str]]] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            columns = next(reader)
        except StopIteration as exc:
            raise ValueError("empty lineups CSV") from exc
        detected = _detect_site(columns)
        if detected is not None:
            header = LINEUP_HEADERS[detected]
        elif columns[: len(header)] != header:
            raise ValueError(f"unsupported CeminiDFS lineup headers: {columns}")
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            seats: list[tuple[str, str]] = []
            for slot, cell in zip(header, row[: len(header)]):
                name = _resolve_cell_name(cell, index)
                if name:
                    seats.append((slot, name))
            if seats:
                lineups.append(seats)
    return lineups


def load_player_index(path: str | Path) -> dict[str, PlayerMeta]:
    """Index players CSV by normalized name and by id.

    Raise ``ValueError`` when a row has neither a position nor a salary. That
    means the header did not match the player schema, so the index would be
    unusable for review reports.
    """

    index: dict[str, PlayerMeta] = {}
    source = Path(path)
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        for raw in reader:
            row = {str(key): ("" if value is None else str(value)) for key, value in raw.items()}
            meta = _player_from_row(row)
            if not meta.name:
                continue
            if not meta.position and not meta.salary:
                raise ValueError(
                    f"{source}: row {meta.name!r} has no position and no salary; "
                    f"header: {', '.join(header)}"
                )
            index[_normalize_name(meta.name)] = meta
            if meta.player_id:
                index[meta.player_id] = meta
    return index


def write_stack_fragility_report(
    path: str | Path,
    lineups: Sequence[Sequence[tuple[str, str]]],
    players: Mapping[str, PlayerMeta],
) -> Path:
    """Same-game WR triples and CHALK-QB-WR-WR. Does not change lineups."""

    rows: list[list[str]] = []
    for index, seats in enumerate(lineups, start=1):
        rows.extend(_fragility_rows_for_lineup(index, seats, players))
    return _write_report(path, STACK_FRAGILITY_HEADER, rows)


def write_late_swap_alert_report(
    path: str | Path,
    lineups: Sequence[Sequence[tuple[str, str]]],
    players: Mapping[str, PlayerMeta],
) -> Path:
    """Rostered Q/D names. Does not call late_swap_lineups. Does not drop Q."""

    counts: Counter[str] = Counter()
    for seats in lineups:
        seen: set[str] = set()
        for _slot, name in seats:
            meta = _lookup(players, name)
            if meta is None or not _is_q_or_d(meta.injury):
                continue
            key = meta.name or name
            if key in seen:
                continue
            seen.add(key)
            counts[key] += 1

    rows: list[list[str]] = []
    for player_name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        meta = _lookup(players, player_name)
        rows.append(
            [
                player_name,
                meta.injury if meta is not None else "",
                str(count),
                meta.team if meta is not None else "",
                meta.game_raw if meta is not None else "",
            ]
        )
    return _write_report(path, LATE_SWAP_ALERT_HEADER, rows)


def read_lineup_totals(path: str | Path) -> list[dict[str, Any]]:
    """Read a totals CSV into ``{rank, score, cashed}`` rows.

    Accepts the Recap Desk ``lineup_totals.csv`` shape. A row without a rank
    or a score is skipped.
    """

    rows: list[dict[str, Any]] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            row = {str(key): ("" if value is None else str(value)) for key, value in raw.items()}
            rank = _parse_number(_first_present(row, _RANK_KEYS))
            score = _parse_number(_first_present(row, _SCORE_KEYS))
            if rank is None or score is None:
                continue
            cashed = _parse_cash(_first_present(row, _CASH_KEYS))
            rows.append({"rank": rank, "score": score, "cashed": cashed})
    rows.sort(key=lambda item: item["rank"])
    return rows


def write_cash_bucket_report(
    path: str | Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    buckets: Sequence[tuple[int, int]] = DEFAULT_CASH_BUCKETS,
) -> Path:
    """Report the score range and the cash rate of each rank bucket.

    A bucket answers "how far short is this group", not "what rank is this
    lineup". Rank 30 and rank 31 differ by noise. The bucket median is the
    number to lift.
    """

    out_rows: list[list[str]] = []
    for low, high in buckets:
        scores = [float(row["score"]) for row in rows if low <= row["rank"] <= high]
        cashes = [
            float(row["score"])
            for row in rows
            if low <= row["rank"] <= high and bool(row.get("cashed"))
        ]
        count = len(scores)
        if count:
            score_min = f"{min(scores):.2f}"
            score_max = f"{max(scores):.2f}"
            median = f"{statistics.median(scores):.2f}"
        else:
            score_min = score_max = median = ""
        rate = f"{(len(cashes) / count * 100.0):.1f}" if count else ""
        out_rows.append(
            [
                f"{low}-{high}",
                str(low),
                str(high),
                str(count),
                score_min,
                score_max,
                median,
                str(len(cashes)),
                rate,
            ]
        )
    return _write_report(path, CASH_BUCKET_HEADER, out_rows)


def _parse_cash(value: str) -> bool:
    text = str(value or "").strip().upper()
    return text in {"Y", "YES", "TRUE", "1", "W"}


def _first_present(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def write_leverage_fade_matrix(
    path: str | Path,
    lineups: Sequence[Sequence[tuple[str, str]]],
    players: Mapping[str, PlayerMeta],
    *,
    site: str = "fanduel",
    calibration_path: str | Path | None = None,
    context: HandoffContext | None = None,
) -> Path:
    """Exposure vs projected own%. Never writes FPPG. Never excludes players.

    The trailing columns report the zero-scrape synthetic ownership and the Jev
    regime routing when a :class:`HandoffContext` is available.
    """

    total = len(lineups)
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    for seats in lineups:
        names = {_canonical_name(players, name) for _slot, name in seats if name}
        counts.update(names)
        for name in names:
            display.setdefault(name, name)

    own_map = _projected_own_map(players, site=site, calibration_path=calibration_path)
    rows: list[list[str]] = []
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    for name, count in ranked:
        exposure = (count / total * 100.0) if total else 0.0
        own = own_map.get(_normalize_name(name), own_map.get(name, 0.0))
        leverage = exposure - own
        flag = ""
        if own >= OWN_FLAG_MIN_PCT and exposure >= own:
            flag = NEGATIVE_LEVERAGE
        record = context.lookup(name) if context is not None else None
        rows.append(
            [
                display.get(name, name),
                f"{exposure:.1f}",
                f"{own:.1f}",
                f"{leverage:.1f}",
                flag,
                record.jev_proj_own if record is not None else "",
                record.leverage_ratio() if record is not None else "",
                record.jev_regime_state if record is not None else "",
                record.jev_provider if record is not None else "",
            ]
        )
    return _write_report(path, LEVERAGE_FADE_HEADER, rows)


def write_duplicate_core_report(
    path: str | Path,
    lineups: Sequence[Sequence[tuple[str, str]]],
    *,
    core_size: int = 5,
    core_cap: int | None = None,
) -> Path:
    """Report a repeated core, or lineups that share four names.

    A 5-player core row lists the full combination in the ``players`` column.
    ``core_cap`` marks a row over the limit. FLEX is ignored for the QB-plus-two-RB
    key. The shared-name rule skips a lineup that a core row already lists.
    Does not change lineups.
    """

    seat_lists = [list(seats) for seats in lineups]
    groups: dict[tuple[str, str, str], list[int]] = {}
    labels: dict[tuple[str, str, str], tuple[str, str, str]] = {}
    for index, seats in enumerate(seat_lists, start=1):
        qb_names = [name for slot, name in seats if slot == "QB" and str(name).strip()]
        rb_names = [name for slot, name in seats if slot == "RB" and str(name).strip()]
        if not qb_names or len(rb_names) < 2:
            continue
        ordered = sorted(rb_names[:2], key=_normalize_name)
        key = (
            _normalize_name(qb_names[0]),
            _normalize_name(ordered[0]),
            _normalize_name(ordered[1]),
        )
        groups.setdefault(key, []).append(index)
        labels.setdefault(key, (qb_names[0], ordered[0], ordered[1]))

    rows: list[list[str]] = []
    covered: set[int] = set()
    for key, indexes in groups.items():
        if len(indexes) < 2:
            continue
        covered.update(indexes)
        qb_name, rb_a, rb_b = labels[key]
        rows.append(
            [
                qb_name,
                rb_a,
                rb_b,
                str(len(indexes)),
                ",".join(str(item) for item in indexes),
                DO_NOT_AUTO_APPLY,
                "",
            ]
        )

    rows.extend(_five_core_rows(seat_lists, core_size=core_size, core_cap=core_cap))

    name_sets = [
        {_normalize_name(str(name)) for _slot, name in seats if str(name).strip()}
        for seats in seat_lists
    ]
    for component in _shared_name_components(name_sets, covered):
        first = seat_lists[component[0] - 1]
        qb_names = [name for slot, name in first if slot == "QB" and str(name).strip()]
        rb_names = [name for slot, name in first if slot == "RB" and str(name).strip()]
        rows.append(
            [
                qb_names[0] if qb_names else "",
                rb_names[0] if rb_names else "",
                rb_names[1] if len(rb_names) > 1 else "",
                str(len(component)),
                ",".join(str(item) for item in component),
                SHARED_NAMES_NOTE,
                "",
            ]
        )

    rows.sort(
        key=lambda row: (
            row[5] not in {FIVE_CORE_NOTE, FIVE_CORE_CAP_NOTE},
            -int(row[3]),
            row[0],
            row[1],
        )
    )
    return _write_report(path, DUPLICATE_CORE_HEADER, rows)


def _five_core_rows(
    seat_lists: Sequence[Sequence[tuple[str, str]]],
    *,
    core_size: int,
    core_cap: int | None,
) -> list[list[str]]:
    """Return one row per 5-player core that repeats above the report floor.

    With a cap, only a core over the cap is reported. Without a cap, a core is
    reported when it appears ``FIVE_CORE_REPORT_MIN`` times or more.
    """

    if core_size < 2:
        return []
    threshold = core_cap if core_cap is not None else FIVE_CORE_REPORT_MIN - 1
    combos: dict[tuple[str, ...], list[int]] = {}
    labels: dict[tuple[str, ...], tuple[str, ...]] = {}
    for index, seats in enumerate(seat_lists, start=1):
        names = [str(name).strip() for _slot, name in seats if str(name).strip()]
        keys = sorted({_normalize_name(name) for name in names})
        if len(keys) < core_size:
            continue
        for combo in itertools.combinations(keys, core_size):
            combos.setdefault(combo, []).append(index)
            labels.setdefault(combo, tuple(combo))
    rows: list[list[str]] = []
    for combo, indexes in combos.items():
        if len(indexes) <= threshold:
            continue
        note = FIVE_CORE_CAP_NOTE if core_cap is not None else FIVE_CORE_NOTE
        rows.append(
            [
                combo[0],
                combo[1] if len(combo) > 1 else "",
                combo[2] if len(combo) > 2 else "",
                str(len(indexes)),
                ",".join(str(item) for item in indexes),
                note,
                " | ".join(labels[combo]),
            ]
        )
    return rows


def _shared_name_components(
    name_sets: Sequence[set[str]],
    covered: set[int],
) -> list[list[int]]:
    """Group uncovered lineups that share ``SHARED_NAME_MIN`` or more names."""

    indexes = [index for index in range(1, len(name_sets) + 1) if index not in covered]
    parent = {index: index for index in indexes}

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for position, left in enumerate(indexes):
        for right in indexes[position + 1 :]:
            if len(name_sets[left - 1] & name_sets[right - 1]) >= SHARED_NAME_MIN:
                union(left, right)

    components: dict[int, list[int]] = defaultdict(list)
    for index in indexes:
        components[find(index)].append(index)
    return sorted(
        (sorted(members) for members in components.values() if len(members) >= 2),
        key=lambda members: members[0],
    )


def write_dart_ceiling_rank(
    path: str | Path,
    players: Mapping[str, PlayerMeta],
) -> Path:
    """Rank salary <= 5500 by the existing mean. Do not invent a ceiling."""

    eligible: list[PlayerMeta] = []
    seen: set[str] = set()
    for meta in players.values():
        if not meta.name:
            continue
        key = _normalize_name(meta.name)
        if key in seen:
            continue
        salary = _parse_number(meta.salary)
        if salary is None or salary > DART_SALARY_MAX:
            continue
        seen.add(key)
        eligible.append(meta)

    mean_values: list[tuple[str, float]] = []
    ceiling_values: list[tuple[str, float]] = []
    prepared: list[tuple[PlayerMeta, str, str, str]] = []
    for meta in eligible:
        mean_text = str(meta.projection or "").strip()
        mean_number = _parse_number(mean_text)
        ceiling_text = _pick(meta.row, _CEILING_KEYS)
        ceiling_number = _parse_number(ceiling_text)
        if ceiling_number is None:
            ceiling_out = ""
            note = CEILING_MISSING
        else:
            ceiling_out = ceiling_text
            note = ""
            ceiling_values.append((meta.name, ceiling_number))
        if mean_number is not None:
            mean_values.append((meta.name, mean_number))
        prepared.append((meta, mean_text, ceiling_out, note))

    mean_ranks = _rank_high_to_low(mean_values)
    ceiling_ranks = _rank_high_to_low(ceiling_values)
    rows: list[list[str]] = []
    for meta, mean_text, ceiling_out, note in prepared:
        rows.append(
            [
                meta.name,
                meta.team,
                meta.position,
                meta.salary,
                mean_text,
                ceiling_out,
                str(mean_ranks[meta.name]) if meta.name in mean_ranks else "",
                str(ceiling_ranks[meta.name]) if meta.name in ceiling_ranks else "",
                note,
            ]
        )
    rows.sort(key=lambda row: (row[6] == "", int(row[6] or 0), row[0].lower()))
    return _write_report(path, DART_CEILING_HEADER, rows)


def _rank_high_to_low(pairs: Sequence[tuple[str, float]]) -> dict[str, int]:
    """Rank 1 is the highest value. Equal values break by player name."""

    ordered = sorted(pairs, key=lambda item: (-item[1], item[0].lower(), item[0]))
    return {name: rank for rank, (name, _value) in enumerate(ordered, start=1)}


def _parse_number(value: Any) -> float | None:
    text = str(value or "").strip().replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if parsed != parsed:  # NaN
        return None
    return parsed


def _fragility_rows_for_lineup(
    lineup_index: int,
    seats: Sequence[tuple[str, str]],
    players: Mapping[str, PlayerMeta],
) -> list[list[str]]:
    lineup_obj = _lineup_namespace(seats, players)
    chalk = CHALK_BADGE in lineup_stack_badges(lineup_obj)
    qb_team = ""
    for player in getattr(lineup_obj, "players", []):
        if "QB" in {str(item).upper() for item in (getattr(player, "positions", None) or ())}:
            qb_team = str(getattr(player, "team", "") or "").strip().upper()
            break
    same_team_wrs = [
        str(getattr(player, "full_name", "") or "").strip()
        for player in getattr(lineup_obj, "players", [])
        if str(getattr(player, "team", "") or "").strip().upper() == qb_team
        and "WR" in {str(item).upper() for item in (getattr(player, "positions", None) or ())}
        and qb_team
    ]

    groups: dict[frozenset[str], list[PlayerMeta]] = defaultdict(list)
    for _slot, name in seats:
        meta = _lookup(players, name)
        if meta is None or "WR" not in meta.positions:
            continue
        key = meta.game_teams if meta.game_teams else frozenset({meta.team} if meta.team else {name})
        groups[key].append(meta)

    rows: list[list[str]] = []
    covered_chalk = False
    for game_teams, wrs in groups.items():
        if len(wrs) < 3:
            continue
        wr_names = sorted({player.name for player in wrs})
        group_chalk = chalk and qb_team and sum(1 for player in wrs if player.team == qb_team) >= 2
        if group_chalk:
            covered_chalk = True
        rows.append(
            [
                str(lineup_index),
                _game_label(wrs, game_teams),
                ", ".join(wr_names),
                str(len(wrs)),
                "Y" if group_chalk else "N",
                DO_NOT_AUTO_APPLY,
            ]
        )

    if chalk and not covered_chalk:
        wr_names = sorted({name for name in same_team_wrs if name})
        metas = [_lookup(players, name) for name in wr_names]
        known = [meta for meta in metas if meta is not None]
        game_teams = known[0].game_teams if known else frozenset()
        rows.append(
            [
                str(lineup_index),
                _game_label(known, game_teams),
                ", ".join(wr_names),
                str(len(wr_names)),
                "Y",
                DO_NOT_AUTO_APPLY,
            ]
        )

    _append_same_game_groups(rows, lineup_index, seats, players)
    return rows


_SKILL_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})


def _append_same_game_groups(
    rows: list[list[str]],
    lineup_index: int,
    seats: Sequence[tuple[str, str]],
    players: Mapping[str, PlayerMeta],
) -> None:
    """Add a row for each same-game skill group of 3 or more names."""

    seen = {
        frozenset(part.strip() for part in row[2].split(",") if part.strip())
        for row in rows
    }
    groups: dict[frozenset[str], list[PlayerMeta]] = defaultdict(list)
    for _slot, name in seats:
        meta = _lookup(players, name)
        if meta is None or not (meta.positions & _SKILL_POSITIONS):
            continue
        key = meta.game_teams if meta.game_teams else frozenset({meta.team} if meta.team else {name})
        groups[key].append(meta)

    for game_teams, members in groups.items():
        unique: list[PlayerMeta] = []
        seen_names: set[str] = set()
        for player in members:
            if not player.name or player.name in seen_names:
                continue
            seen_names.add(player.name)
            unique.append(player)
        if len(unique) < 3:
            continue
        names = sorted(player.name for player in unique)
        name_set = frozenset(names)
        if name_set in seen:
            continue
        seen.add(name_set)
        rows.append(
            [
                str(lineup_index),
                _game_label(unique, game_teams),
                ", ".join(names),
                str(len(unique)),
                "N",
                DO_NOT_AUTO_APPLY,
            ]
        )


def _lineup_namespace(
    seats: Sequence[tuple[str, str]],
    players: Mapping[str, PlayerMeta],
) -> SimpleNamespace:
    lineup_players = []
    for slot, name in seats:
        meta = _lookup(players, name)
        positions = set(meta.positions) if meta is not None else _positions_from_slot(slot)
        if slot.upper() in {"QB", "RB", "WR", "TE"}:
            positions.add(slot.upper())
        team = meta.team if meta is not None else ""
        game_info = None
        if meta is not None and meta.game_id and "@" in meta.game_id:
            away, home = meta.game_id.split("@", 1)
            game_info = SimpleNamespace(home_team=home, away_team=away)
        lineup_players.append(
            SimpleNamespace(
                full_name=meta.name if meta is not None else name,
                team=team,
                positions=sorted(positions),
                lineup_position=slot,
                game_info=game_info,
                injury_indicator=meta.injury if meta is not None else "",
            )
        )
    return SimpleNamespace(players=lineup_players)


def _game_label(wrs: Sequence[PlayerMeta], game_teams: frozenset[str]) -> str:
    for player in wrs:
        if player.game_id:
            return player.game_id
    if len(game_teams) == 2:
        left, right = sorted(game_teams)
        return f"{left}@{right}"
    return ""


def _projected_own_map(
    players: Mapping[str, PlayerMeta],
    *,
    site: str,
    calibration_path: str | Path | None,
) -> dict[str, float]:
    unique: dict[str, PlayerMeta] = {}
    for meta in players.values():
        if meta.name:
            unique[_normalize_name(meta.name)] = meta

    from_csv: dict[str, float] = {}
    missing: list[PlayerMeta] = []
    for key, meta in unique.items():
        parsed = _parse_own_pct(meta.projected_own)
        if parsed is not None and calibration_path is None:
            from_csv[key] = parsed
        else:
            missing.append(meta)

    if calibration_path is None and not missing:
        return from_csv

    rows = [_ownership_input_row(meta, site=site) for meta in unique.values()]
    projected = _project_own_rows(rows, site=site, calibration_path=calibration_path)
    own_map = dict(from_csv)
    for row in projected:
        name = str(row.get("player_name") or "").strip()
        if not name:
            continue
        parsed = _parse_own_pct(row.get("Projected Ownership"))
        if parsed is None:
            continue
        key = _normalize_name(name)
        if key not in from_csv or calibration_path is not None:
            own_map[key] = parsed
    return own_map


def _project_own_rows(
    rows: list[dict[str, Any]],
    *,
    site: str,
    calibration_path: str | Path | None,
) -> list[dict[str, Any]]:
    copies = [dict(row) for row in rows]
    if calibration_path is not None:
        calibration = load_ownership_calibration(calibration_path)
        return project_ownership_calibrated(copies, calibration, site=site)
    return project_ownership(copies, site=site)


def _ownership_input_row(meta: PlayerMeta, *, site: str) -> dict[str, Any]:
    normalized = str(site or "fanduel").strip().lower()
    site_key = "dk" if normalized in {"draftkings", "dk"} else "fd"
    position = meta.position.upper()
    if position in {"D", "DST", "DEF"}:
        position = "DEF"
    row: dict[str, Any] = {
        "player_name": meta.name,
        f"{site_key}_position": position,
        f"{site_key}_salary": meta.salary,
        f"{site_key}_projection": meta.projection,
        "Position": position,
        "Salary": meta.salary,
        "projection": meta.projection,
    }
    if meta.projected_own:
        row["Projected Ownership"] = meta.projected_own
    return row


def _extract_lineup_names(lineups: Any) -> list[list[tuple[str, str]]]:
    """Convert pydfs Lineup objects or CeminiDFS tuple lineups to CeminiDFS format."""

    result: list[list[tuple[str, str]]] = []
    for lineup in (lineups if isinstance(lineups, list) else [lineups]):
        if not lineup:
            continue
        players = getattr(lineup, "players", None)
        if players is not None:
            seats = [(getattr(player, "slot", ""), str(getattr(player, "full_name", "") or "").strip())
                     for player in players if getattr(player, "full_name", None)]
        else:
            seats = lineup if isinstance(lineup, list) else []
        result.append([(slot, name) for slot, name in seats if name])
    return result


def write_parlays_handoff(
    path: str | Path,
    lineups: Any,
    players: Mapping[str, PlayerMeta],
    *,
    implied_totals: Mapping[str, str] | None = None,
    context: HandoffContext | None = None,
    slate_id: str = "",
) -> Path:
    """Write the upgraded player-level handoff CSV next to the lineup file.

    When a :class:`HandoffContext` is supplied the file covers the whole slate
    with disaggregated stat-level GMM bands. Without one it falls back to the
    players rostered in ``lineups``: identity and environment fields are filled
    from the player index and only ``fpts_median`` carries a point estimate
    (the FanDuel projection). DST, DEF, and D rows are omitted. No FanDuel
    contest IDs and no salary are written.
    """

    if context is not None and len(context):
        rows = [record.row() for record in context.ordered()]
        return _write_report(path, PARLAYS_HANDOFF_HEADER, rows)

    totals = implied_totals or {}
    normalized_lineups = _extract_lineup_names(lineups)
    seen: dict[str, PlayerHandoff] = {}
    for seats in normalized_lineups:
        for _slot, name in seats:
            if not name:
                continue
            meta = _lookup(players, name)
            if _is_defense(meta):
                continue
            record = _fallback_handoff(meta, name, implied_totals=totals, slate_id=slate_id)
            seen.setdefault(normalize_handoff_name(record.player_name), record)
    ordered = sorted(seen.values(), key=lambda record: normalize_handoff_name(record.player_name))
    rows = [record.row() for record in ordered]
    return _write_report(path, PARLAYS_HANDOFF_HEADER, rows)


def _fallback_handoff(
    meta: PlayerMeta | None,
    name: str,
    *,
    implied_totals: Mapping[str, str],
    slate_id: str,
) -> PlayerHandoff:
    """Build a handoff record from the player index when no run context exists."""

    team = meta.team if meta is not None else ""
    game_id = meta.game_id if meta is not None else ""
    projection = _handoff_projection(meta) if meta is not None else ""
    return PlayerHandoff(
        player_name=meta.name if meta is not None else name,
        player_id=meta.player_id if meta is not None else "",
        slate_id=slate_id,
        game_id=game_id,
        team=team,
        opp=_opponent(meta, game_id),
        position=meta.position if meta is not None else "",
        implied_total=implied_totals.get(team.upper(), "") if team else "",
        fpts_median=projection,
    )


def _opponent(meta: PlayerMeta | None, game_id: str) -> str:
    if meta is not None:
        opp = str(meta.row.get("opp") or meta.row.get("Opponent") or "").strip().upper()
        if opp:
            return opp
    if game_id and "@" in game_id:
        away, home = game_id.split("@", 1)
        if meta is not None and meta.team:
            team = meta.team.upper()
            if team == away:
                return home
            if team == home:
                return away
    return ""


def _handoff_projection(meta: PlayerMeta | None) -> str:
    """Use fd_projection when that column is present. Do not prefer FPPG over it."""

    if meta is None:
        return ""
    lowered = {str(key).strip().lower() for key in meta.row}
    if "fd_projection" in lowered:
        return _pick(meta.row, ("fd_projection",))
    return meta.projection


def _is_defense(meta: PlayerMeta | None) -> bool:
    if meta is None:
        return False
    tokens = {str(meta.position or "").upper()}
    tokens.update(str(item).upper() for item in meta.positions)
    return bool(tokens & {"D", "DEF", "DST"})


def _build_handoff_context(dest: Path) -> HandoffContext | None:
    """Build the slate-wide handoff context from a run directory, or ``None``.

    A directory without a projection base (a bare optimize on an arbitrary CSV)
    returns ``None`` so the writer falls back to the lineup-level summary. A
    present-but-unreadable input raises :class:`HandoffInputError` and is
    re-raised: that is a corrupt run artifact, not a missing optional file. Any
    other build error also returns ``None``: the handoff is a report, not a gate.
    """

    try:
        return build_handoff_context(dest)
    except HandoffInputError:
        raise
    except Exception:  # pragma: no cover - a report must never break the solve.
        return None


def _implied_totals_from_environment(environment: str | Path | None) -> dict[str, str] | None:
    if not environment:
        return None
    env_path = Path(environment)
    if not env_path.is_file():
        raise FileNotFoundError(f"environment CSV not found: {env_path}")
    from ceminidfs.export.research_export import load_team_implied_totals

    return load_team_implied_totals(env_path)


def _write_report(path: str | Path, header: list[str], rows: Iterable[Sequence[str]]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"{DO_NOT_AUTO_APPLY}: {out}")
    return out


def _player_from_row(row: dict[str, str]) -> PlayerMeta:
    name = _row_name(row)
    team = _pick(row, _TEAM_KEYS).upper()
    position = _pick(row, _POS_KEYS).upper()
    if position == "DST":
        position = "D"
    positions = frozenset(part for part in re.split(r"[/,]", position) if part)
    game_raw = _pick(row, _GAME_KEYS)
    opp = _pick(row, _OPP_KEYS).upper()
    game_id = _parse_game_id(game_raw)
    if game_id:
        away, home = game_id.split("@", 1)
        game_teams = frozenset({away, home})
    elif team and opp:
        game_teams = frozenset({team, opp})
    elif team:
        game_teams = frozenset({team})
    else:
        game_teams = frozenset()
    return PlayerMeta(
        name=name,
        team=team,
        position=position,
        positions=positions,
        injury=_pick(row, _INJURY_KEYS),
        game_raw=game_raw,
        game_id=game_id,
        game_teams=game_teams,
        player_id=_pick(row, _ID_KEYS),
        salary=_pick(row, _SALARY_KEYS),
        projection=_pick(row, _PROJ_KEYS),
        projected_own=_pick(row, _OWN_KEYS),
        row=row,
    )


def _row_name(row: dict[str, str]) -> str:
    first = _pick(row, ("first name", "firstname"))
    last = _pick(row, ("last name", "lastname"))
    combined = " ".join(part for part in (first, last) if part).strip()
    if combined:
        return combined
    return _pick(row, _NAME_KEYS)


def _pick(row: Mapping[str, str], keys: Sequence[str]) -> str:
    lower = {str(key).strip().lower(): value for key, value in row.items()}
    for key in keys:
        value = lower.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _parse_game_id(raw: str) -> str:
    match = _GAME_PAIR.search(str(raw or "").upper())
    if not match:
        return ""
    return f"{match.group(1)}@{match.group(2)}"


def _parse_own_pct(value: Any) -> float | None:
    text = str(value or "").strip().replace("%", "")
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if parsed != parsed:  # NaN
        return None
    return parsed


def _is_q_or_d(token: str) -> bool:
    text = str(token or "").strip().upper()
    if not text:
        return False
    if text in _Q_OR_D:
        return True
    return text.startswith("DOUBTFUL")


def _positions_from_slot(slot: str) -> set[str]:
    token = slot.strip().upper()
    if token in {"DEF", "DST", "D"}:
        return {"DEF", "DST", "D"}
    if token:
        return {token}
    return set()


def _lookup(players: Mapping[str, PlayerMeta], name: str) -> PlayerMeta | None:
    if name in players:
        return players[name]
    return players.get(_normalize_name(name))


def _canonical_name(players: Mapping[str, PlayerMeta], name: str) -> str:
    meta = _lookup(players, name)
    return meta.name if meta is not None else name


def _resolve_cell_name(cell: str, players: Mapping[str, PlayerMeta]) -> str:
    text = cell.strip()
    if not text:
        return ""
    name, player_id = _parse_lineup_cell(text)
    if player_id and player_id in players:
        return players[player_id].name
    if name:
        meta = _lookup(players, name)
        return meta.name if meta is not None else name
    return ""


def _parse_lineup_cell(cell: str) -> tuple[str, str]:
    text = cell.strip()
    match = _CELL_ID_SUFFIX.search(text)
    if match:
        return text[: match.start()].strip(), match.group(1).strip()
    if _ID_ONLY.fullmatch(text):
        return "", text
    return text, ""


def _normalize_name(name: str) -> str:
    stripped = _CELL_ID_SUFFIX.sub("", name).strip()
    return " ".join(stripped.lower().split())


def _detect_site(columns: list[str]) -> str | None:
    for site_key, header in LINEUP_HEADERS.items():
        if columns[: len(header)] == header:
            return site_key
    return None
