"""Scoring engine for BBM player recommendations.

Implements the scoring formula from the brief:
score = (projection_pts + clv_bonus) * stack_mult * archetype_mult * exposure_mult
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Callable, Optional, Tuple

from ceminidfs.bbm.config import (
    STACK_MULT_QB,
    STACK_MULT_PASS,
    STACK_MULT_W17_BRINGBACK,
    STACK_MULT_MAX,
    STACK_MULT_MIN_CLV_DELTA,
    EXPOSURE_SOFT_BRAKE_PCT,
    MAX_RECOMMENDATIONS,
    RECOMMENDER_TIMEOUT_MS,
    COMBO_PAIR_CAP,
    clv_weight,
)
from ceminidfs.bbm.models import Player, Roster, DraftState, Archetype, Recommendation
from ceminidfs.bbm.archetype import archetype_mult
from ceminidfs.bbm.validator import validate_pick, get_violation_severity
from ceminidfs.bbm.ledger import combo_pct


@dataclass
class ScoreComponents:
    """Breakdown of scoring calculation."""
    projection: float
    clv_delta: float
    clv_bonus: float
    base_score: float
    stack_mult: float
    archetype_mult: float
    exposure_mult: float
    final_score: float


def score_player(
    player: Player,
    draft_state: DraftState,
    roster: Roster,
    archetype: Archetype,
    exposure_pct_fn: Callable[[str], float]
) -> Tuple[float, ScoreComponents, List[str]]:
    """Score a single player for recommendation ranking.

    Formula: score = (projection_pts + clv_bonus) * stack_mult * archetype_mult * exposure_mult

    Args:
        player: Player to score
        draft_state: Current draft state
        roster: Current roster
        archetype: Current archetype
        exposure_pct_fn: Function to get exposure % for a player_id

    Returns:
        Tuple of (final_score, components, warnings)
    """
    warnings: List[str] = []
    pick_num = draft_state.current_pick_num

    # 1. Calculate CLV delta and bonus
    clv_delta = pick_num - player.adp
    month = draft_state.draft_date.month if draft_state.draft_date else 7
    clv_weight_val = clv_weight(month)
    clv_bonus = clv_delta * clv_weight_val

    # 2. Calculate stack multiplier
    stack_mult = _calculate_stack_mult(
        player, roster, clv_delta, pick_num, draft_state
    )

    # 3. Calculate archetype multiplier
    arch_mult = archetype_mult(archetype, roster.current_round)

    # 4. Calculate exposure multiplier
    exp_mult, exp_warning = _calculate_exposure_mult(
        player, exposure_pct_fn, archetype
    )
    if exp_warning:
        warnings.append(exp_warning)

    # 5. Base projection (default to 0 if None)
    projection = player.projection_pts or 0.0
    base_score = projection + clv_bonus

    # 6. Final score
    final_score = base_score * stack_mult * arch_mult * exp_mult

    components = ScoreComponents(
        projection=projection,
        clv_delta=clv_delta,
        clv_bonus=clv_bonus,
        base_score=base_score,
        stack_mult=stack_mult,
        archetype_mult=arch_mult,
        exposure_mult=exp_mult,
        final_score=final_score
    )

    return final_score, components, warnings


def _calculate_stack_mult(
    player: Player,
    roster: Roster,
    clv_delta: float,
    pick_num: int,
    draft_state: DraftState
) -> float:
    """Calculate stack multiplier based on QB and pass-catcher relationships.

    Rules:
    - +0.30 QB stack (QB + WR/TE from same team)
    - +0.15 pass stack (QB + WR/TE from same team, non-primary)
    - +0.10 W17 bring-back R10+ (opposing player in W17 matchup)
    - Cap at 1.4
    - Require clv_delta >= 3 to stack-reach
    """
    # Must have positive CLV delta to stack-reach
    if clv_delta < STACK_MULT_MIN_CLV_DELTA:
        return 1.0

    mult = 1.0

    # Check for QB stack opportunities
    if player.position in ("WR", "TE"):
        # Look for QB on roster from same team
        for roster_player in roster.players:
            if roster_player.position == "QB" and roster_player.team == player.team:
                # QB stack: +0.30
                mult += STACK_MULT_QB
                break

    elif player.position == "QB":
        # Look for pass-catchers on roster from same team
        pass_catchers = [p for p in roster.players if p.position in ("WR", "TE")]
        for pc in pass_catchers:
            if pc.team == player.team:
                mult += STACK_MULT_PASS
                break

    # W17 bring-back: +0.10 in rounds 10+
    if draft_state.roster.current_round >= 10:
        # Check if this player is in a W17 bring-back matchup
        # against someone on roster (opposing teams playing each other in W17)
        if _is_w17_bringback(player, roster):
            mult += STACK_MULT_W17_BRINGBACK

    return min(mult, STACK_MULT_MAX)


def _is_w17_bringback(player: Player, roster: Roster) -> bool:
    """Check if player is in a W17 bring-back matchup against roster."""
    # W17 matchups - simplified lookup
    # In reality this would be a full schedule lookup
    w17_matchups = _get_w17_matchups()

    player_week = 17  # W17

    for roster_player in roster.players:
        # Check if roster player is in W17
        roster_player_week = 17  # Assume W17 for now

        if roster_player_week == player_week == 17:
            # Check if they're in the same game (opposing teams)
            if _are_opponents(player.team, roster_player.team, w17_matchups):
                return True

    return False


def _get_w17_matchups() -> List[Tuple[str, str]]:
    """Get W17 matchup pairs."""
    # Simplified W17 matchups - would come from schedule module
    # Format: list of (team_a, team_b) pairs playing each other
    return [
        ("KC", "DEN"), ("CAR", "TB"), ("CIN", "PIT"), ("MIA", "NYJ"),
        ("DET", "SF"), ("MIN", "GB"), ("BUF", "NE"), ("LAC", "LV"),
        ("WAS", "DAL"), ("JAX", "TEN"), ("NYG", "IND"), ("NO", "ARI"),
        ("HOU", "BAL"), ("CHI", "SEA"), ("PHI", "ATL"), ("CLE", "LAR"),
    ]


def _are_opponents(team_a: str, team_b: str, matchups: List[Tuple[str, str]]) -> bool:
    """Check if two teams are opponents in a given matchup list."""
    for t1, t2 in matchups:
        if (team_a == t1 and team_b == t2) or (team_a == t2 and team_b == t1):
            return True
    return False


def _calculate_exposure_mult(
    player: Player,
    exposure_pct_fn: Callable[[str], float],
    archetype: Archetype
) -> Tuple[float, Optional[str]]:
    """Calculate exposure multiplier with soft brake.

    Rules:
    - exposure >= cap: multiplier 0.0 (hard prune)
    - exposure >= cap - 5%: linear soft brake from cap-5% to cap
    - Archetype E ignores caps
    """
    # Archetype E (Contrarian) ignores exposure caps
    if archetype == Archetype.E:
        return 1.0, None

    exposure_pct = exposure_pct_fn(player.player_id)
    cap_pct = player.exposure_cap_pct or _get_default_cap(player)

    # Hard prune at cap
    if exposure_pct >= cap_pct:
        return 0.0, f"EXPOSURE_CAP: {exposure_pct:.0%} >= {cap_pct:.0%}"

    # Soft brake zone: cap - 5% to cap
    soft_brake_start = cap_pct - EXPOSURE_SOFT_BRAKE_PCT

    if exposure_pct >= soft_brake_start:
        # Linear interpolation from 1.0 at soft_brake_start to 0.0 at cap
        progress = (exposure_pct - soft_brake_start) / EXPOSURE_SOFT_BRAKE_PCT
        mult = 1.0 - progress
        warning = f"near cap {exposure_pct:.0%}"
        return max(mult, 0.0), warning

    return 1.0, None


def _combo_cap_blocks(player: Player, roster: Roster) -> bool:
    """Check if adding this player would exceed COMBO_PAIR_CAP with any roster teammate.

    Uses combo_pct from ledger to check if any player pair exceeds the 25% cap.
    Returns True if any combo would exceed the cap (player should be blocked).
    """
    for roster_player in roster.players:
        combo_info = combo_pct(roster_player.player_id, player.player_id)
        if combo_info["current"] >= COMBO_PAIR_CAP:
            return True
    return False


def _get_default_cap(player: Player) -> float:
    """Get default exposure cap based on player tier."""
    from ceminidfs.bbm.config import TIER_EXPOSURE_CAPS

    if player.tier:
        return TIER_EXPOSURE_CAPS.get(player.tier, 0.15)

    # Default by position/ADP heuristic
    if player.adp <= 24:
        return 0.35  # elite
    elif player.adp <= 60:
        return 0.25  # stack_core
    elif player.adp <= 120:
        return 0.20  # mid_target
    elif player.adp <= 180:
        return 0.15  # late_lottery
    else:
        return 0.10  # single_dart


def recommend_top3(
    draft_state: DraftState,
    available_players: List[Player],
    exposure_pct_fn: Callable[[str], float],
    max_recommendations: int = MAX_RECOMMENDATIONS
) -> List[Recommendation]:
    """Generate top-N player recommendations for current pick.

    Must complete in <200ms for top-240 players.

    Args:
        draft_state: Current draft state
        available_players: List of available players to consider
        exposure_pct_fn: Function to get exposure % for a player_id
        max_recommendations: Number of recommendations to return

    Returns:
        List of Recommendation objects, sorted by score descending
    """
    start_time = time.time()
    roster = draft_state.roster
    archetype = draft_state.archetype
    current_round = roster.current_round

    scored_players: List[Tuple[Player, float, ScoreComponents, List[str]]] = []

    # Filter and score available players
    for player in available_players:
        # Exclude faded players (use round-specific fade check)
        if player.is_faded_for_round(current_round):
            continue

        # Skip players where any roster teammate combo exceeds COMBO_PAIR_CAP
        if _combo_cap_blocks(player, roster):
            continue

        # Validate against hard constraints
        violations = validate_pick(player, roster, archetype)
        critical_violations = [v for v in violations if get_violation_severity(v) == "CRITICAL"]

        if critical_violations:
            continue  # Skip players with critical violations

        # Score the player
        score, components, warnings = score_player(
            player, draft_state, roster, archetype, exposure_pct_fn
        )

        # Skip if exposure pruned (mult = 0)
        if components.exposure_mult <= 0:
            continue

        # Add constraint warnings
        warnings.extend([v for v in violations if get_violation_severity(v) == "WARNING"])

        scored_players.append((player, score, components, warnings))

    # Sort by score descending
    scored_players.sort(key=lambda x: x[1], reverse=True)

    # Build recommendations
    recommendations: List[Recommendation] = []

    for rank, (player, score, components, warnings) in enumerate(scored_players[:max_recommendations], 1):
        is_stack = components.stack_mult > 1.0

        rec = Recommendation(
            player=player,
            score=score,
            raw_projection=components.projection,
            clv_bonus=components.clv_bonus,
            stack_mult=components.stack_mult,
            archetype_mult=components.archetype_mult,
            exposure_mult=components.exposure_mult,
            warnings=warnings,
            is_stack_opportunity=is_stack
        )
        # Patch rank
        object.__setattr__(rec, '_rank', rank)

        recommendations.append(rec)

    # Check timing
    elapsed_ms = (time.time() - start_time) * 1000
    if elapsed_ms > RECOMMENDER_TIMEOUT_MS:
        # Log warning but still return results
        print(f"WARN: recommender took {elapsed_ms:.1f}ms (target <{RECOMMENDER_TIMEOUT_MS}ms)")

    return recommendations


# Tie-breaker functions (for equal scores)

def tiebreak_stack_w17(player: Player, roster: Roster) -> bool:
    """Tie-breaker 1: Prefer stack / W17 bring-back."""
    # Simplified: check if player creates stack
    if player.position in ("WR", "TE"):
        for rp in roster.players:
            if rp.position == "QB" and rp.team == player.team:
                return True
    return False


def tiebreak_clv_delta(player: Player, pick_num: int) -> bool:
    """Tie-breaker 2: Prefer clv_delta >= 3."""
    clv_delta = pick_num - player.adp
    return clv_delta >= 3


def tiebreak_positive_drift(player: Player, month: int) -> bool:
    """Tie-breaker 3: Prefer positive drift (rookies in May-Jun)."""
    if month in (5, 6) and player.drift_coeff > 0:
        return True
    return False


def tiebreak_furthest_below_cap(player: Player, exposure_pct: float) -> float:
    """Tie-breaker 4: Prefer furthest below exposure cap.

    Returns: distance below cap (higher = better)
    """
    cap = player.exposure_cap_pct or _get_default_cap(player)
    return cap - exposure_pct
