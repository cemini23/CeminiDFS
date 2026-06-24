"""Draft session orchestration — bridges ledger, registry, and recommender."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from ceminidfs.bbm.config import ARCHETYPE_NAMES, TOTAL_ENTRIES, get_bye_week
from ceminidfs.bbm.ledger import (
    exposure_pct as ledger_exposure,
    get_db_path,
    get_draft_state,
    init_db,
    list_available_players,
    sync_players_from_registry,
)
from ceminidfs.bbm.models import Archetype, DraftState, DraftStatus, Player, Roster, Signal
from ceminidfs.bbm.registry import ensure_seed_registry
from ceminidfs.bbm.recommender import recommend_top3


def ensure_initialized() -> None:
    """Initialize DB and sync player registry."""

    init_db()
    registry = ensure_seed_registry()
    sync_players_from_registry(registry)


def _signal_from_str(value: str | None) -> Signal:
    if not value:
        return Signal.NEUTRAL
    upper = value.upper()
    if upper == "BUY":
        return Signal.BUY
    if upper == "FADE":
        return Signal.FADE
    return Signal.NEUTRAL


def player_from_row(row: dict[str, Any]) -> Player:
    """Convert ledger/registry row to Player model."""

    team = row.get("team") or ""
    merge_name = row.get("merge_name") or row["name"].lower()
    fade_rounds = row.get("fade_rounds")
    if fade_rounds is None and _signal_from_str(row.get("signal")) == Signal.FADE:
        from ceminidfs.bbm.config import FADE_ROUND_BANDS

        for pattern, band in FADE_ROUND_BANDS.items():
            if pattern in merge_name:
                fade_rounds = [band]
                break

    return Player(
        player_id=row["player_id"],
        name=row["name"],
        merge_name=merge_name,
        position=row["position"],
        team=team,
        bye_week=int(row.get("bye_week") or get_bye_week(team) or 0),
        adp=float(row.get("adp") or 999),
        strategy_rank=row.get("strategy_rank"),
        projection_pts=row.get("projection_pts"),
        signal=_signal_from_str(row.get("signal")),
        tier=row.get("tier"),
        exposure_cap_pct=row.get("cap_pct") or row.get("exposure_cap_pct"),
        drift_coeff=float(row.get("drift_coeff") or 0),
        injury_fade=bool(row.get("injury_fade")),
        notes=row.get("notes"),
        fade_rounds=fade_rounds,
    )


def get_taken_player_ids(draft_id: str) -> set[str]:
    """Return player IDs taken in this draft room (mine + others)."""

    db = get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT player_id FROM picks WHERE draft_id = ? AND is_mine = 1",
        (draft_id,),
    )
    mine = {row[0] for row in cursor.fetchall()}
    cursor.execute(
        "SELECT player_id FROM room_taken WHERE draft_id = ?",
        (draft_id,),
    )
    room = {row[0] for row in cursor.fetchall()}
    conn.close()
    return mine | room


def build_draft_state(draft_id: str, round_num: int) -> DraftState | None:
    """Build recommender DraftState from ledger."""

    state = get_draft_state(draft_id)
    if state is None:
        return None

    roster_players: list[Player] = []
    for pick in state.my_picks:
        roster_players.append(
            Player(
                player_id=pick["player_id"],
                name=pick["name"],
                merge_name=pick["name"].lower(),
                position=pick["position"],
                team=pick.get("team") or "",
                bye_week=int(pick.get("bye_week") or 0),
                adp=float(pick.get("adp") or 999),
                signal=_signal_from_str(pick.get("signal")),
                tier=pick.get("tier"),
                exposure_cap_pct=pick.get("cap_pct"),
            )
        )

    roster = Roster(
        players=roster_players,
        draft_position=state.slot,
        current_round=round_num,
    )

    try:
        archetype = Archetype(state.archetype)
    except ValueError:
        archetype = Archetype.B

    status = (
        DraftStatus.COMPLETE if state.status == "complete" else DraftStatus.IN_PROGRESS
    )

    return DraftState(
        draft_id=draft_id,
        slot=state.slot,
        archetype=archetype,
        status=status,
        roster=roster,
        taken_players=get_taken_player_ids(draft_id),
        draft_date=datetime.now(),
    )


def get_available_models(draft_id: str, limit: int = 240) -> list[Player]:
    """List available players as models, excluding taken."""

    taken = get_taken_player_ids(draft_id)
    rows = list_available_players(limit=limit, draft_id=draft_id)
    return [player_from_row(row) for row in rows if row["player_id"] not in taken]


def get_recommendations(
    round_num: int,
    pick_num: int,
    archetype_str: str,
    draft_id: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """CLI bridge — return top-N recommendations as display dicts.
    archetype_str overrides draft_state.archetype when valid.
    """

    draft_state = build_draft_state(draft_id, round_num)
    if draft_state is None:
        return []

    # Override archetype with archetype_str when valid
    if archetype_str:
        try:
            draft_state.archetype = Archetype(archetype_str)
        except ValueError:
            pass  # Keep original archetype if invalid

    available = get_available_models(draft_id)

    def exposure_fn(player_id: str) -> float:
        return ledger_exposure(player_id)["current"]

    recs = recommend_top3(draft_state, available, exposure_fn, max_recommendations=limit)

    results: list[dict[str, Any]] = []
    for rec in recs:
        player = rec.player
        exp = ledger_exposure(player.player_id)
        results.append(
            {
                "player_id": player.player_id,
                "name": player.name,
                "position": player.position,
                "team": player.team,
                "signal": player.signal.value if player.signal != Signal.NEUTRAL else "",
                "exp_current": exp["current"],
                "exp_cap": exp["cap"],
                "is_stack_candidate": rec.is_stack_opportunity,
                "warnings": rec.warnings,
                "score": rec.score,
            }
        )
    return results


def archetype_gap_pct(archetype: str) -> float:
    """Return portfolio gap for archetype as percentage points."""

    db = get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM drafts WHERE archetype = ? AND status = 'complete'",
        (archetype,),
    )
    count = cursor.fetchone()[0] or 0
    conn.close()
    from ceminidfs.bbm.config import ARCHETYPE_TARGETS

    target = ARCHETYPE_TARGETS.get(archetype, 0)
    gap = (target - count) / TOTAL_ENTRIES
    return round(gap * 100, 1)


def archetype_header(archetype: str) -> str:
    """Format archetype line for REPL."""

    name = ARCHETYPE_NAMES.get(archetype, archetype)
    gap = archetype_gap_pct(archetype)
    sign = "+" if gap >= 0 else ""
    return f"Archetype: {archetype} ({name}) — portfolio gap {sign}{gap}%"
