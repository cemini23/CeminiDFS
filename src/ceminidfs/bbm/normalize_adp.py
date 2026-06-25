"""Normalize BBTB ADP exports against nflverse-style names."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from datetime import date
from pathlib import Path
from typing import Any, Iterable

try:  # pragma: no cover - optional dependency
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover - fallback path
    fuzz = None
    process = None

SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b", re.IGNORECASE)
NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")
SPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class MatchResult:
    merge_name: str
    player_id: str
    canonical_name: str
    score: int
    method: str


def normalize_name(name: str) -> str:
    """Normalize player names for matching."""

    cleaned = name.strip().lower()
    cleaned = cleaned.replace("&", " and ")
    cleaned = cleaned.replace(".", " ")
    cleaned = cleaned.replace("'", "")
    cleaned = cleaned.replace("-", " ")
    cleaned = SUFFIX_RE.sub(" ", cleaned)
    cleaned = NON_ALNUM_RE.sub(" ", cleaned)
    cleaned = SPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def _read_csv_rows(path: Path | str) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _pick(row: dict[str, str], keys: Iterable[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            for row_key, row_value in row.items():
                if row_key.strip().lower() == key.strip().lower() and row_value:
                    return str(row_value).strip()
            continue
        if str(value).strip():
            return str(value).strip()
    return ""


def _coerce_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = str(value).strip().replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _tier_from_adp(adp: float) -> str:
    """Map an ADP band to a registry tier."""

    if adp <= 20:
        return "elite"
    if adp <= 60:
        return "stack_core"
    if adp <= 120:
        return "mid_target"
    if adp <= 180:
        return "late_lottery"
    return "single_dart"


def load_nflverse_index(path: Path | str) -> dict[str, MatchResult]:
    """Build a normalized lookup from an nflverse-style player export."""

    rows = _read_csv_rows(path)
    index: dict[str, MatchResult] = {}
    for row in rows:
        name = _pick(row, ("merge_name", "name", "player_name", "full_name"))
        if not name:
            first = _pick(row, ("first_name", "firstname", "first name"))
            last = _pick(row, ("last_name", "lastname", "last name"))
            name = " ".join(part for part in (first, last) if part).strip()
        if not name:
            continue
        merge_name = normalize_name(name)
        player_id = _pick(row, ("player_id", "gsis_id", "gsis", "id"))
        index[merge_name] = MatchResult(
            merge_name=merge_name,
            player_id=player_id,
            canonical_name=name,
            score=100,
            method="exact",
        )
    return index


def _best_fuzzy_match(
    query: str,
    candidates: list[str],
    *,
    threshold: int,
) -> tuple[str, int] | None:
    if not candidates:
        return None

    if process is not None and fuzz is not None:
        match = process.extractOne(query, candidates, scorer=fuzz.ratio)
        if match and int(match[1]) >= threshold:
            return str(match[0]), int(match[1])
        return None

    best_name = ""
    best_score = 0
    for candidate in candidates:
        score = int(SequenceMatcher(None, query, candidate).ratio() * 100)
        if score > best_score:
            best_name = candidate
            best_score = score
    if best_name and best_score >= threshold:
        return best_name, best_score
    return None


def load_overrides(path: Path | str | None) -> dict[str, dict[str, str]]:
    """Load manual merge overrides keyed by normalized merge name."""

    if path is None:
        return {}
    override_path = Path(path)
    if not override_path.exists():
        return {}

    overrides: dict[str, dict[str, str]] = {}
    for row in _read_csv_rows(override_path):
        raw_name = _pick(row, ("merge_name", "name", "player_name"))
        if not raw_name:
            continue
        overrides[normalize_name(raw_name)] = row
    return overrides


def merge_bbtb_csv(
    bbtb_csv: Path | str,
    nflverse_csv: Path | str,
    out_csv: Path | str,
    *,
    overrides_csv: Path | str | None = None,
    threshold: int = 90,
) -> list[dict[str, str]]:
    """Merge a BBTB ADP CSV with nflverse names and write the result."""

    bbtb_rows = _read_csv_rows(bbtb_csv)
    nflverse_index = load_nflverse_index(nflverse_csv)
    overrides = load_overrides(overrides_csv)
    candidate_names = list(nflverse_index)
    merged_rows: list[dict[str, str]] = []

    for row in bbtb_rows:
        raw_name = _pick(row, ("merge_name", "name", "player", "player_name", "full_name"))
        if not raw_name:
            continue

        merge_name = normalize_name(raw_name)
        override = overrides.get(merge_name)
        match = override or nflverse_index.get(merge_name)

        if match is None:
            fuzzy = _best_fuzzy_match(merge_name, candidate_names, threshold=threshold)
            if fuzzy is not None:
                match_name, score = fuzzy
                match = nflverse_index[match_name]
                row["match_method"] = "rapidfuzz" if process is not None else "difflib"
                row["match_score"] = str(score)
            else:
                row["match_method"] = "unmatched"
                row["match_score"] = "0"
        else:
            row["match_method"] = "override" if override is not None else "exact"
            row["match_score"] = "100"

        row["merge_name"] = merge_name
        row["nflverse_name"] = match["name"] if isinstance(match, dict) and "name" in match else ""
        row["player_id"] = (
            match["player_id"]
            if isinstance(match, dict)
            else getattr(match, "player_id", "")
        )
        row["canonical_name"] = (
            match["name"]
            if isinstance(match, dict) and "name" in match
            else getattr(match, "canonical_name", "")
        )
        merged_rows.append(row)

    fieldnames = list(merged_rows[0].keys()) if merged_rows else []
    out_path = Path(out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged_rows)
    return merged_rows


@dataclass(slots=True)
class AdpMergeResult:
    matched: int
    exact_matched: int
    fuzzy_matched: int
    added: int
    unmatched: list[str]
    ambiguous: list[str] = field(default_factory=list)


def merge_adp_csv(
    csv_path: Path | str,
    registry: dict[str, Any],
    *,
    add_unmatched: bool = True,
) -> AdpMergeResult:
    """Update registry ADP values from a BBTB-style CSV (name + adp columns)."""

    rows = _read_csv_rows(csv_path)
    players = registry.setdefault("players", [])
    by_merge: dict[str, dict[str, Any]] = {
        normalize_name(str(p.get("merge_name") or p.get("name", ""))): p for p in players
    }
    candidate_names = list(by_merge)
    matched = 0
    exact_matched = 0
    fuzzy_matched = 0
    added = 0
    unmatched: list[str] = []
    ambiguous: list[str] = []

    for row in rows:
        raw_name = _pick(row, ("merge_name", "name", "player", "player_name", "full_name"))
        if not raw_name:
            continue
        merge_name = normalize_name(raw_name)
        adp_raw = _pick(row, ("adp", "adp_pick", "adp pick", "average_pick"))
        if not adp_raw:
            continue
        try:
            adp_val = float(adp_raw.replace(",", ""))
        except ValueError:
            continue

        player = by_merge.get(merge_name)
        if player is None:
            fuzzy = _best_fuzzy_match(merge_name, candidate_names, threshold=90)
            if fuzzy:
                player = by_merge[fuzzy[0]]
                fuzzy_matched += 1
                if fuzzy[1] < 95:
                    ambiguous.append(raw_name)
            else:
                if add_unmatched:
                    position = _pick(row, ("pos", "position")).upper()
                    new_player = {
                        "player_id": f"bbm:{merge_name.replace(' ', '-')}",
                        "name": raw_name.strip(),
                        "merge_name": merge_name,
                        "position": position,
                        "team": "FA",
                        "bye_week": 0,
                        "adp": adp_val,
                        "strategy_rank": int(adp_val),
                        "projection_pts": 100.0,
                        "signal": "NEUTRAL",
                        "tier": _tier_from_adp(adp_val),
                        "exposure_cap_pct": 0.20,
                        "drift_coeff": 0.0,
                        "injury_fade": False,
                        "notes": "",
                        "fade_rounds": None,
                    }
                    players.append(new_player)
                    by_merge[merge_name] = new_player
                    candidate_names.append(merge_name)
                    matched += 1
                    added += 1
                    continue

                unmatched.append(raw_name)
                continue
        else:
            exact_matched += 1

        player["adp"] = adp_val
        player["strategy_rank"] = int(adp_val)
        matched += 1

    registry.setdefault("meta", {})["updated"] = date.today().isoformat()
    registry["meta"]["adp_source"] = Path(csv_path).name
    registry["meta"]["player_count"] = len(players)
    if added:
        players.sort(key=lambda p: (float(p.get("adp", 9999)), str(p.get("name", ""))))
    return AdpMergeResult(
        matched=matched,
        exact_matched=exact_matched,
        fuzzy_matched=fuzzy_matched,
        added=added,
        unmatched=unmatched,
        ambiguous=ambiguous,
    )


@dataclass(slots=True)
class ProjectionMergeResult:
    matched: int
    exact_matched: int
    fuzzy_matched: int
    unmatched: list[str]


def merge_projections_csv(
    csv_path: Path | str,
    registry: dict[str, Any],
) -> ProjectionMergeResult:
    """Update registry projection points from a CSV keyed by merge name."""

    rows = _read_csv_rows(csv_path)
    players = registry.setdefault("players", [])
    by_merge: dict[str, dict[str, Any]] = {
        normalize_name(str(p.get("merge_name") or p.get("name", ""))): p for p in players
    }
    candidate_names = list(by_merge)
    matched = 0
    exact_matched = 0
    fuzzy_matched = 0
    unmatched: list[str] = []

    for row in rows:
        raw_name = _pick(row, ("merge_name", "name", "player", "player_name", "full_name"))
        if not raw_name:
            continue

        merge_name = normalize_name(raw_name)
        projection_val = _coerce_float(
            _pick(row, ("projection_pts", "projection", "fpts", "half_ppr"))
        )
        if projection_val is None:
            unmatched.append(raw_name)
            continue

        player = by_merge.get(merge_name)
        if player is None:
            fuzzy = _best_fuzzy_match(merge_name, candidate_names, threshold=90)
            if fuzzy is None:
                unmatched.append(raw_name)
                continue
            player = by_merge[fuzzy[0]]
            fuzzy_matched += 1
        else:
            exact_matched += 1

        player["projection_pts"] = projection_val
        matched += 1

    meta = registry.setdefault("meta", {})
    meta["updated"] = date.today().isoformat()
    meta["projection_source"] = Path(csv_path).name

    return ProjectionMergeResult(
        matched=matched,
        exact_matched=exact_matched,
        fuzzy_matched=fuzzy_matched,
        unmatched=unmatched,
    )

