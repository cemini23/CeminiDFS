"""Hard constraint validator for BBM roster construction.

Implements bye week, team stacking, and structural constraints
per the BBM7 strategy brief.
"""

from __future__ import annotations

from typing import List, Dict

from ceminidfs.bbm.config import (
    MAX_SAME_BYE,
    NEVER_SAME_BYE,
    MAX_SAME_TEAM,
    MAX_SAME_TEAM_ARCHETYPE_C,
)
from ceminidfs.bbm.models import Player, Roster, Archetype


def validate_pick(player: Player, roster: Roster, archetype: Archetype) -> List[str]:
    """Validate a potential pick against all hard constraints.

    Args:
        player: Player being considered for selection
        roster: Current roster state
        archetype: Current draft archetype

    Returns:
        List of violation strings (empty if valid)
    """
    violations: List[str] = []

    # Check fade signals
    if player.is_faded():
        violations.append(f"FADED: {player.name}")
        return violations  # Early exit - faded players are excluded

    # 1. QB bye week constraint: All 3 QBs must have distinct bye weeks
    qb_violations = _validate_qb_byes(player, roster)
    violations.extend(qb_violations)

    # 2. 3-TE builds: All TEs must have distinct bye weeks
    te_violations = _validate_te_byes(player, roster)
    violations.extend(te_violations)

    # 3. Bye week limits: <=7 players same bye (teammates exempt), never 10+
    bye_violations = _validate_bye_limits(player, roster)
    violations.extend(bye_violations)

    # 4. Team stacking limits: <=4 same team (5 only for Archetype C)
    team_violations = _validate_team_limits(player, roster, archetype)
    violations.extend(team_violations)

    return violations


def _validate_qb_byes(player: Player, roster: Roster) -> List[str]:
    """Validate that all 3 QBs would have distinct bye weeks."""
    violations: List[str] = []

    if player.position != "QB":
        return violations

    existing_qb_byes = roster.get_qb_bye_weeks()

    # If we're adding a QB and would have 3 QBs total
    if roster.qb_count >= 2:
        # Check if any existing QB shares this bye
        if player.bye_week in existing_qb_byes:
            violations.append(
                f"QB_BYE_DUPLICATE: 3rd QB {player.name} shares bye {player.bye_week}"
            )

    # If we're adding a 4th QB, that's also a structural issue
    if roster.qb_count >= 3:
        violations.append(f"QB_OVERFLOW: Already have {roster.qb_count} QBs")

    return violations


def _validate_te_byes(player: Player, roster: Roster) -> List[str]:
    """Validate that in 3-TE builds, all TEs have distinct bye weeks."""
    violations: List[str] = []

    if player.position != "TE":
        return violations

    # Only applies to 3-TE builds
    if roster.te_count < 2:
        return violations

    existing_te_byes = roster.get_te_bye_weeks()

    # If adding 3rd TE, check for bye conflicts
    if roster.te_count >= 2:
        if player.bye_week in existing_te_byes:
            violations.append(
                f"TE_BYE_DUPLICATE: 3rd TE {player.name} shares bye {player.bye_week}"
            )

    return violations


def _validate_bye_limits(player: Player, roster: Roster) -> List[str]:
    """Validate bye week limits: <=7 players (teammates exempt), never 10+."""
    violations: List[str] = []

    # Count players by bye week (excluding teammates who are exempt)
    bye_counts: Dict[int, int] = {}
    bye_teammates: Dict[int, int] = {}

    for p in roster.players:
        bye = p.bye_week
        bye_counts[bye] = bye_counts.get(bye, 0) + 1

        # Count teammates (players who share team with others on roster)
        if roster.has_teammate(p):
            bye_teammates[bye] = bye_teammates.get(bye, 0) + 1

    # Calculate non-exempt count for player's bye week
    player_bye = player.bye_week
    total_on_bye = bye_counts.get(player_bye, 0) + 1  # +1 for this player
    exempt_on_bye = bye_teammates.get(player_bye, 0)
    if roster.has_teammate(player):
        exempt_on_bye += 1  # This player would be exempt if they have a teammate

    non_exempt_on_bye = total_on_bye - exempt_on_bye

    # Hard limit: never 10+ same bye
    if total_on_bye >= NEVER_SAME_BYE:
        violations.append(
            f"BYE_HARD_LIMIT: {total_on_bye} players on bye {player_bye} (max {NEVER_SAME_BYE - 1})"
        )

    # Soft limit: <=7 non-exempt players same bye
    if non_exempt_on_bye > MAX_SAME_BYE:
        violations.append(
            f"BYE_SOFT_LIMIT: {non_exempt_on_bye} non-exempt players on bye {player_bye} (max {MAX_SAME_BYE})"
        )

    return violations


def _validate_team_limits(player: Player, roster: Roster, archetype: Archetype) -> List[str]:
    """Validate team stacking limits: <=4 same team (5 only for Archetype C)."""
    violations: List[str] = []

    team = player.team
    current_count = roster.get_player_count_by_team(team)
    new_count = current_count + 1

    # Archetype C allows 5 from same team
    max_allowed = MAX_SAME_TEAM_ARCHETYPE_C if archetype == Archetype.C else MAX_SAME_TEAM

    if new_count > max_allowed:
        violations.append(
            f"TEAM_LIMIT: {new_count} players from {team} (max {max_allowed} for archetype {archetype.value})"
        )

    return violations


def get_roster_bye_summary(roster: Roster) -> Dict[int, Dict[str, any]]:
    """Get detailed bye week breakdown for roster analysis.

    Returns:
        Dict mapping bye_week -> {total, exempt, non_exempt, players}
    """
    bye_summary: Dict[int, Dict[str, any]] = {}

    for p in roster.players:
        bye = p.bye_week
        if bye not in bye_summary:
            bye_summary[bye] = {"total": 0, "exempt": 0, "non_exempt": 0, "players": []}

        bye_summary[bye]["total"] += 1
        bye_summary[bye]["players"].append(p.name)

        # Check if exempt (has teammate on roster)
        teammates = roster.get_teammates(p)
        if teammates:
            bye_summary[bye]["exempt"] += 1
        else:
            bye_summary[bye]["non_exempt"] += 1

    return bye_summary


def get_roster_team_summary(roster: Roster) -> Dict[str, List[str]]:
    """Get team stacking summary for roster analysis."""
    team_summary: Dict[str, List[str]] = {}

    for p in roster.players:
        team_summary.setdefault(p.team, []).append(p.name)

    return team_summary


def passes_all_constraints(player: Player, roster: Roster, archetype: Archetype) -> bool:
    """Quick check if player passes all hard constraints.

    Returns True only if no violations exist.
    """
    violations = validate_pick(player, roster, archetype)
    return len(violations) == 0


def get_violation_severity(violation: str) -> str:
    """Classify violation severity for UI highlighting.

    Returns: "CRITICAL", "WARNING", or "INFO"
    """
    if "FADED" in violation:
        return "CRITICAL"
    if "HARD_LIMIT" in violation or "OVERFLOW" in violation:
        return "CRITICAL"
    if "DUPLICATE" in violation or "LIMIT" in violation:
        return "WARNING"
    return "INFO"
