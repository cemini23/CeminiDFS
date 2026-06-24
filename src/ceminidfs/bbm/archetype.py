"""Archetype router and pivot state machine for BBM drafts.

Handles archetype assignment based on portfolio gaps and
draft pivot logic when primary archetype is blocked.
"""

from __future__ import annotations

from typing import Optional, Dict, List
from ceminidfs.bbm.config import (
    ARCHETYPE_TARGETS,
    ARCHETYPE_NAMES,
    ARCHETYPE_PIVOTS,
    PIVOT_TRIGGERS,
    get_round_band,
    archetype_mult as config_archetype_mult,
)
from ceminidfs.bbm.models import Archetype, Roster, Player, LedgerCounts, PivotResult


def assign_archetype(ledger_counts: LedgerCounts) -> Archetype:
    """Assign archetype furthest below target ratio from portfolio config.

    Args:
        ledger_counts: Current portfolio counts by archetype

    Returns:
        Archetype that is most under-represented
    """
    gaps: Dict[str, float] = {}

    for code in ARCHETYPE_TARGETS:
        gap = ledger_counts.get_archetype_gap(code)
        gaps[code] = gap

    # Return archetype with highest gap (furthest below target)
    max_gap_code = max(gaps, key=gaps.get)
    return Archetype(max_gap_code)


def pivot_state_machine(
    primary: Archetype,
    roster: Roster,
    round_num: int,
    board: List[Player]
) -> PivotResult:
    """Determine if we need to pivot archetype based on board state.

    Args:
        primary: Current primary archetype
        roster: Current roster state
        round_num: Current round (1-18)
        board: Available players on board

    Returns:
        PivotResult with optional new archetype and warning message
    """
    trigger = None
    new_archetype = None
    warning = None

    # Check pivot triggers based on primary archetype
    if primary == Archetype.D:
        # Zero RB -> Hero RB if 0 RB at R6 and elite RB tier empty
        if round_num >= 6 and roster.rb_count == 0:
            if _is_elite_rb_tier_empty(board):
                trigger = PIVOT_TRIGGERS.get("D")
                fallback = _get_fallback(primary, fallback_index=0)
                if fallback:
                    new_archetype = fallback
                    warning = f"WARN: pivot D→{new_archetype.value} (Zero RB blocked)"

    elif primary == Archetype.C:
        # Stack-heavy -> RB-forward if anchor gone + stack lane dead
        if round_num >= 3:
            if _is_stack_anchor_gone(board) and _is_stack_lane_dead(roster, board):
                trigger = PIVOT_TRIGGERS.get("C")
                fallback = _get_fallback(primary, fallback_index=0)
                if fallback:
                    new_archetype = fallback
                    warning = f"WARN: pivot C→{new_archetype.value} (Stack-heavy blocked)"
                else:
                    # Second fallback to Contrarian
                    fallback = _get_fallback(primary, fallback_index=1)
                    if fallback:
                        new_archetype = fallback
                        warning = f"WARN: pivot C→{new_archetype.value} (Stack-heavy blocked, no RB lane)"

    elif primary == Archetype.A:
        # RB-forward -> Hero RB if 0 RB at R5 in RB run
        if round_num >= 5 and roster.rb_count == 0:
            if _is_rb_run_happening(board, round_num):
                trigger = PIVOT_TRIGGERS.get("A")
                fallback = _get_fallback(primary, fallback_index=0)
                if fallback:
                    new_archetype = fallback
                    warning = f"WARN: pivot A→{new_archetype.value} (RB-forward blocked)"

    return PivotResult(
        new_archetype=new_archetype,
        warning=warning,
        trigger_reason=trigger
    )


def archetype_mult(archetype: Archetype, round_num: int) -> float:
    """Get archetype-specific multiplier for a given round band.

    Args:
        archetype: Current draft archetype
        round_num: Current round (1-18)

    Returns:
        Multiplier value (default 1.0 if no special rule)
    """
    return config_archetype_mult(archetype.value, round_num)


def _get_fallback(primary: Archetype, fallback_index: int = 0) -> Optional[Archetype]:
    """Get fallback archetype from pivot state machine."""
    pivot_list = ARCHETYPE_PIVOTS.get(primary.value, [])

    if fallback_index < len(pivot_list):
        fallback = pivot_list[fallback_index]
        if fallback and fallback[0]:
            return Archetype(fallback[0])

    return None


def _is_elite_rb_tier_empty(board: List[Player]) -> bool:
    """Check if elite RB tier is empty on board.

    Elite RBs: Gibbs, Bijan, Taylor, Henry, Chase Brown, Achane, Jeanty
    """
    elite_rbs = {
        "gibbs", "bijan", "taylor", "henry", "chase brown",
        "achane", "jeanty"
    }

    for player in board:
        if player.position == "RB":
            name_lower = player.name.lower()
            if any(elite in name_lower for elite in elite_rbs):
                return False  # Found an elite RB

    return True  # No elite RBs available


def _is_stack_anchor_gone(board: List[Player]) -> bool:
    """Check if stack anchors (Chase, McConkey) are gone."""
    anchors = {"chase", "mcconkey"}

    for player in board:
        if player.position == "WR":
            name_lower = player.name.lower()
            if any(anchor in name_lower for anchor in anchors):
                return False  # Anchor still available

    return True  # All anchors gone


def _is_stack_lane_dead(roster: Roster, board: List[Player]) -> bool:
    """Check if stack completion lane is dead (no QB/WR pairs available)."""
    # Simplified: check if we have a viable QB stack option
    # In practice, this would check for QB-WR pairs from same team
    return False  # Conservative default


def _is_rb_run_happening(board: List[Player], round_num: int) -> bool:
    """Check if an RB run is happening (multiple RBs going off board)."""
    # In early rounds (R5), if we're seeing RBs fly off, it's an RB run
    # This is contextual and would need historical board state
    # Simplified: assume true if we're in R5+ and haven't taken a RB
    return round_num >= 5


def get_archetype_description(archetype: Archetype) -> str:
    """Get human-readable archetype description."""
    return ARCHETYPE_NAMES.get(archetype.value, "Unknown")


def get_archetype_progress(ledger_counts: LedgerCounts) -> Dict[str, Dict[str, any]]:
    """Get archetype completion progress for portfolio tracking.

    Returns dict with current, target, pct_complete, and gap for each archetype.
    """

    progress = {}
    for code, target in ARCHETYPE_TARGETS.items():
        current = ledger_counts.archetype_counts.get(code, 0)
        pct = (current / target * 100) if target > 0 else 0
        gap = target - current

        progress[code] = {
            "name": ARCHETYPE_NAMES.get(code, code),
            "current": current,
            "target": target,
            "pct_complete": pct,
            "gap": gap,
            "status": "complete" if current >= target else "in_progress" if current > 0 else "not_started"
        }

    return progress


def should_force_archetype_pick(archetype: Archetype, roster: Roster, round_num: int) -> Optional[str]:
    """Check if we need to force a specific position pick for archetype structure.

    Returns position code if forced, None otherwise.
    """
    band = get_round_band(round_num)

    if archetype == Archetype.A:  # RB-forward
        if band == "r1_2" and roster.rb_count < 2:
            return "RB"
        if band == "r11_13" and roster.te_count < 2:
            return "TE"

    elif archetype == Archetype.B:  # Hero RB
        if band == "r1_2":
            if roster.rb_count == 0:
                return "RB"  # Need hero RB
            if roster.wr_count == 0:
                return "WR"
        if band == "r11_13" and roster.te_count < 2:
            return "TE"

    elif archetype == Archetype.C:  # Stack-heavy
        if band in ("r1_2", "r3_5") and roster.wr_count < 2:
            return "WR"  # Stack anchor
        if band == "r6_10" and roster.qb_count < 2:
            return "QB"

    elif archetype == Archetype.D:  # Zero RB
        if band in ("r1_2", "r3_5") and roster.wr_count < 3:
            return "WR"
        if band == "r7_9" and roster.rb_count < 2:
            return "RB"  # Late RBs
        if band == "r11_13" and roster.te_count < 2:
            return "TE"

    return None
