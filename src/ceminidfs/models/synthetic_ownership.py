"""Zero-scrape synthetic ownership (Integration D).

No external ownership board is read. Jev classifies each slate-viable player
into one of five ownership buckets from a heuristic chalk card. Python converts
the bucket probabilities to a continuous ``raw_own`` and normalizes each FanDuel
roster position to its expected ownership mass.

    raw_own = sum(p_bucket * midpoint)
    jev_proj_own = raw_own * (position_target / sum(raw_own in position))

Jev routes. Python does the arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from ceminidfs.jev_client import ChoiceResult, TieredJevClient

BUCKET_ORDER = (
    "contrarian_sub_3pct",
    "low_own_3_to_8pct",
    "moderate_8_to_15pct",
    "chalk_15_to_25pct",
    "mega_chalk_25pct_plus",
)
BUCKET_MIDPOINT: dict[str, float] = {
    "contrarian_sub_3pct": 0.015,
    "low_own_3_to_8pct": 0.055,
    "moderate_8_to_15pct": 0.115,
    "chalk_15_to_25pct": 0.200,
    "mega_chalk_25pct_plus": 0.320,
}

# Sum of jev_proj_own within each FanDuel roster position. One lineup is
# QB + 2 RB + 3 WR + TE + FLEX + DEF. The flex mass is folded into RB and WR.
POSITION_OWNERSHIP_TARGET: dict[str, float] = {
    "QB": 100.0,
    "RB": 235.0,
    "WR": 335.0,
    "TE": 130.0,
    "DEF": 100.0,
    "DST": 100.0,
    "D": 100.0,
}
DEFAULT_POSITION_TARGET = 100.0

MIN_PROJECTION = 4.0

OWNERSHIP_QUESTION = (
    "Given this FanDuel DFS chalk card, which ownership bucket is this player "
    "most likely to land in for the upcoming slate?"
)


@dataclass
class ChalkCard:
    player_id: str
    position: str
    state: dict[str, Any]
    raw_own: float = 0.0
    top_bucket: str = ""
    confidence: float = 0.0
    provider_used: str = "prior"


def build_chalk_card(
    row: Mapping[str, Any],
    *,
    value_rank_at_pos: int | None = None,
    vegas_team_implied_total_rank: int | None = None,
    salary_change_wow: Any = None,
    last_week_fpts: Any = None,
    is_min_price_injury_fill_in: bool | None = None,
) -> ChalkCard:
    """Assemble the compact heuristic chalk card for one player."""

    player_id = str(row.get("player_id") or row.get("gsgid") or row.get("player_name") or "").strip()
    position = str(row.get("position") or "").upper()
    salary = _number(row.get("fanduel_salary") or row.get("salary") or row.get("Salary"))
    if is_min_price_injury_fill_in is None:
        is_min_price_injury_fill_in = bool(row.get("is_min_price_injury_fill_in")) or (
            salary is not None and salary <= 4500 and bool(row.get("injury_status") or row.get("report_status"))
        )
    state = {
        "position": position,
        "fanduel_salary": salary,
        "salary_change_wow": _number(salary_change_wow if salary_change_wow is not None else row.get("salary_change_wow")),
        "value_rank_at_pos": int(value_rank_at_pos) if value_rank_at_pos is not None else _optional_int(row.get("value_rank_at_pos")),
        "last_week_fpts": _number(last_week_fpts if last_week_fpts is not None else row.get("last_week_fpts")),
        "vegas_team_implied_total_rank": int(vegas_team_implied_total_rank)
        if vegas_team_implied_total_rank is not None
        else _optional_int(row.get("vegas_team_implied_total_rank")),
        "is_min_price_injury_fill_in": bool(is_min_price_injury_fill_in),
    }
    return ChalkCard(player_id=player_id, position=position, state=state)


def value_ranks_at_position(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Rank ``proj_fpts / (salary / 1000)`` within each position (1 is best)."""

    by_position: dict[str, list[tuple[float, str]]] = {}
    for row in rows:
        player_id = str(row.get("player_id") or row.get("player_name") or "").strip()
        projection = _number(row.get("fd_projection") or row.get("projection"))
        salary = _number(row.get("fanduel_salary") or row.get("salary"))
        if not player_id or projection is None or not salary:
            continue
        position = str(row.get("position") or "").upper()
        by_position.setdefault(position, []).append((projection / (salary / 1000.0), player_id))

    ranks: dict[str, int] = {}
    for entries in by_position.values():
        entries.sort(key=lambda item: (-item[0], item[1]))
        for rank, (_value, player_id) in enumerate(entries, start=1):
            ranks[player_id] = rank
    return ranks


def classify_ownership(
    client: TieredJevClient | None,
    cards: Sequence[ChalkCard],
) -> dict[str, ChoiceResult]:
    """Route each card to a bucket distribution. No client means prior weights."""

    results: dict[str, ChoiceResult] = {}
    for card in cards:
        if client is None:
            results[card.player_id] = _prior_choice(card)
            continue
        results[card.player_id] = client.jev_choice(
            card.state, OWNERSHIP_QUESTION, list(BUCKET_ORDER)
        )
    return results


def raw_ownership(probabilities: Mapping[str, float]) -> float:
    """Return ``sum(p_bucket * midpoint)`` as a fraction of the field."""

    return float(
        sum(float(probabilities.get(bucket, 0.0)) * midpoint for bucket, midpoint in BUCKET_MIDPOINT.items())
    )


def normalize_position_ownership(
    rows: Sequence[Mapping[str, Any]],
    *,
    position_targets: Mapping[str, float] | None = None,
    position_key: str = "position",
    raw_key: str = "raw_own",
    out_key: str = "jev_proj_own",
) -> list[dict[str, Any]]:
    """Scale ``raw_own`` so each position group sums to its FanDuel target.

    Returns a new list of row copies with ``jev_proj_own`` added. Within a
    position, a zero-sum group splits the target equally.
    """

    targets = dict(position_targets or POSITION_OWNERSHIP_TARGET)
    output = [dict(row) for row in rows]
    groups: dict[str, list[int]] = {}
    for index, row in enumerate(output):
        position = str(row.get(position_key) or "").upper()
        groups.setdefault(position, []).append(index)

    for position, indexes in groups.items():
        target = float(targets.get(position, DEFAULT_POSITION_TARGET))
        raws = np.array([float(output[index].get(raw_key, 0.0) or 0.0) for index in indexes], dtype=float)
        total = float(raws.sum())
        if total <= 0.0:
            shares = np.full(len(indexes), target / len(indexes))
        else:
            shares = raws / total * target
        for index, share in zip(indexes, shares, strict=True):
            output[index][out_key] = round(float(share), 4)
    return output


def synthetic_ownership(
    rows: Sequence[Mapping[str, Any]],
    *,
    client: TieredJevClient | None = None,
    min_projection: float = MIN_PROJECTION,
    position_targets: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Return rows with ``raw_own``, ``jev_proj_own``, and routing metadata.

    Only players with ``fd_projection >= min_projection`` are classified. Others
    receive ``jev_proj_own = 0``. Without a client the classifier uses the
    documented ownership prior, so the function is fully offline.
    """

    ranks = value_ranks_at_position(rows)
    cards: list[ChalkCard] = []
    considered: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        projection = _number(row.get("fd_projection") or row.get("projection")) or 0.0
        copy = dict(row)
        if projection < min_projection:
            copy["raw_own"] = 0.0
            copy["jev_proj_own"] = 0.0
            copy["jev_own_top_bucket"] = ""
            copy["jev_provider"] = ""
            skipped.append(copy)
            continue
        card = build_chalk_card(copy, value_rank_at_pos=ranks.get(card_id(copy)))
        cards.append(card)
        considered.append(copy)

    results = classify_ownership(client, cards)
    for copy, card in zip(considered, cards, strict=True):
        result = results.get(card.player_id)
        probabilities = dict(result.probabilities) if result is not None else {bucket: 1.0 / len(BUCKET_ORDER) for bucket in BUCKET_ORDER}
        copy["raw_own"] = raw_ownership(probabilities)
        copy["jev_own_top_bucket"] = result.top_choice if result is not None else _top_bucket(probabilities)
        copy["jev_provider"] = result.provider_used if result is not None else "prior"

    normalized = normalize_position_ownership(
        considered, position_targets=position_targets
    )
    return normalized + skipped


def card_id(row: Mapping[str, Any]) -> str:
    return str(row.get("player_id") or row.get("player_name") or "").strip()


def leverage_score(
    tail_hit_probability: float,
    ownership_fraction: float,
    *,
    exponent: float = 0.5,
) -> float:
    """``p(sim >= top_1pct_threshold) / geom_mean_own ** 0.5``.

    ``ownership_fraction`` is a per-lineup geometric mean ownership in ``(0, 1]``.
    Zero ownership is floored to the smallest observable share.
    """

    floor = 1.0e-4
    own = max(float(ownership_fraction), floor)
    return float(tail_hit_probability) / (own ** float(exponent))


def geometric_mean_ownership(ownership_fractions: Sequence[float]) -> float:
    values = [max(float(value), 1.0e-4) for value in ownership_fractions]
    if not values:
        return 0.0
    return float(np.exp(np.mean(np.log(values))))


def _prior_choice(card: ChalkCard) -> ChoiceResult:
    from ceminidfs.jev_client import OWNERSHIP_PRIOR

    rank = card.state.get("value_rank_at_pos")
    weights = dict(OWNERSHIP_PRIOR)
    if isinstance(rank, int) and rank > 0:
        # Better value ranks lean chalk; the prior is the offline anchor only.
        tilt = max(0.0, min(1.0, 1.0 / (rank + 1.0)))
        weights = {
            bucket: weights[bucket] * (1.0 + tilt if bucket.endswith("_plus") or "chalk" in bucket else 1.0 - tilt * 0.5)
            for bucket in BUCKET_ORDER
        }
    total = sum(weights.values())
    weights = {bucket: weights[bucket] / total for bucket in BUCKET_ORDER}
    return ChoiceResult(
        probabilities=weights,
        top_choice=_top_bucket(weights),
        confidence=0.55,
        provider_used="prior",
        cached=False,
    )


def _top_bucket(probabilities: Mapping[str, float]) -> str:
    if not probabilities:
        return ""
    return max(probabilities, key=probabilities.get)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    cleaned = _number(value)
    return int(cleaned) if cleaned is not None else None
