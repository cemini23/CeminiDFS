"""Post-draft audit module for BBM roster validation.

Provides checklist validation for position counts, bye week violations,
exposure summary, and CLV estimates per pick.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Tuple

from ceminidfs.bbm.config import (
    ROSTER_TARGETS,
    MAX_SAME_BYE,
    NEVER_SAME_BYE,
    MAX_SAME_TEAM,
    MAX_SAME_TEAM_ARCHETYPE_C,
    TOTAL_ENTRIES,
    EXPOSURE_SOFT_BRAKE_PCT,
)
from ceminidfs.bbm.models import (
    Player, Roster, Archetype, AuditResult,
    Draft
)
from ceminidfs.bbm.validator import get_roster_bye_summary, get_roster_team_summary


@dataclass
class PickAnalysis:
    """Analysis of a single pick."""
    round: int
    pick_num: int
    player: Player
    adp: float
    clv_delta: float
    position: str
    was_recommended: bool
    warnings: List[str]


@dataclass
class ExposureSummary:
    """Summary of exposure for a player."""
    player_id: str
    player_name: str
    count: int
    pct: float
    cap: float
    status: str  # "ok", "soft_brake", "at_cap"


def audit_draft(
    draft: Draft,
    roster: Roster,
    picks: List[PickAnalysis],
    exposure_counts: Dict[str, int],
    archetype: Archetype
) -> AuditResult:
    """Run full post-draft audit.

    Args:
        draft: Draft metadata
        roster: Final roster
        picks: List of pick analyses
        exposure_counts: Player exposure counts across portfolio
        archetype: Draft archetype used

    Returns:
        AuditResult with all findings
    """
    # 1. Position counts
    position_counts = _audit_position_counts(roster)

    # 2. Bye week violations
    bye_violations = _audit_bye_weeks(roster)

    # 3. Team stacking audit
    team_counts = _audit_team_stacking(roster, archetype)

    # 4. Exposure summary
    exposure_summary = _audit_exposure_summary(roster, exposure_counts)

    # 5. CLV estimate
    estimated_clv = _estimate_clv(picks)

    # 6. Compile warnings
    warnings = []

    # Check position count issues
    for pos, (current, (min_tgt, max_tgt)) in position_counts.items():
        if current < min_tgt:
            warnings.append(f"{pos} under target: {current} < {min_tgt}")
        elif current > max_tgt:
            warnings.append(f"{pos} over target: {current} > {max_tgt}")

    # Check team stacking issues
    for team, count in team_counts.items():
        max_allowed = MAX_SAME_TEAM_ARCHETYPE_C if archetype == Archetype.C else MAX_SAME_TEAM
        if count > max_allowed:
            warnings.append(f"Team stacking: {count} from {team} (max {max_allowed})")

    # Passes if no critical violations
    passes_audit = len(bye_violations) == 0 and len([w for w in warnings if "CRITICAL" in w]) == 0

    return AuditResult(
        draft_id=draft.draft_id,
        archetype=archetype.value,
        position_counts={pos: cnt for pos, (cnt, _) in position_counts.items()},
        bye_violations=bye_violations,
        team_counts=team_counts,
        exposure_summary=exposure_summary,
        estimated_clv=estimated_clv,
        passes_audit=passes_audit,
        warnings=warnings
    )


def _audit_position_counts(roster: Roster) -> Dict[str, Tuple[int, Tuple[int, int]]]:
    """Audit roster position counts against targets.

    Returns dict of position -> (current_count, (min_target, max_target))
    """
    counts = {
        "QB": (roster.qb_count, ROSTER_TARGETS["QB"]),
        "RB": (roster.rb_count, ROSTER_TARGETS["RB"]),
        "WR": (roster.wr_count, ROSTER_TARGETS["WR"]),
        "TE": (roster.te_count, ROSTER_TARGETS["TE"]),
    }
    return counts


def _audit_bye_weeks(roster: Roster) -> List[str]:
    """Audit bye week constraints and return violations."""
    violations = []
    bye_summary = get_roster_bye_summary(roster)

    for bye_week, data in bye_summary.items():
        total = data["total"]
        non_exempt = data["non_exempt"]

        # Hard limit: never 10+
        if total >= NEVER_SAME_BYE:
            violations.append(
                f"CRITICAL: {total} players on bye week {bye_week} (max {NEVER_SAME_BYE - 1})"
            )

        # Soft limit: <=7 non-exempt
        if non_exempt > MAX_SAME_BYE:
            violations.append(
                f"WARNING: {non_exempt} non-exempt players on bye {bye_week} (max {MAX_SAME_BYE})"
            )

    # Check QB bye weeks (must be distinct for 3 QBs)
    qb_byes = roster.get_qb_bye_weeks()
    if roster.qb_count >= 3 and len(qb_byes) < roster.qb_count:
        violations.append(
            f"CRITICAL: QB bye weeks not distinct ({len(qb_byes)} unique for {roster.qb_count} QBs)"
        )

    # Check TE bye weeks for 3-TE builds
    if roster.te_count >= 3:
        te_byes = roster.get_te_bye_weeks()
        if len(te_byes) < roster.te_count:
            violations.append(
                f"WARNING: TE bye weeks not distinct ({len(te_byes)} unique for {roster.te_count} TEs)"
            )

    return violations


def _audit_team_stacking(roster: Roster, archetype: Archetype) -> Dict[str, int]:
    """Audit team stacking and return team counts."""
    team_summary = get_roster_team_summary(roster)
    return {team: len(players) for team, players in team_summary.items()}


def _audit_exposure_summary(
    roster: Roster,
    exposure_counts: Dict[str, int]
) -> Dict[str, float]:
    """Generate exposure summary for roster players.

    Returns dict of player_id -> exposure percentage
    """
    summary = {}

    for player in roster.players:
        count = exposure_counts.get(player.player_id, 0)
        pct = count / TOTAL_ENTRIES
        summary[player.player_id] = pct

    return summary


def _estimate_clv(picks: List[PickAnalysis]) -> float:
    """Estimate cumulative CLV (Closing Line Value) for the draft.

    CLV delta = pick_num - adp (positive = value, negative = reached)
    """
    if not picks:
        return 0.0

    total_clv = sum(p.clv_delta for p in picks)
    return total_clv / len(picks)


def get_exposure_status(pct: float, cap: float) -> str:
    """Get exposure status classification."""
    if pct >= cap:
        return "at_cap"
    elif pct >= cap - EXPOSURE_SOFT_BRAKE_PCT:
        return "soft_brake"
    else:
        return "ok"


def format_audit_report(result: AuditResult) -> str:
    """Format audit result as human-readable report."""
    lines = [
        f"=== Draft Audit: {result.draft_id} ===",
        f"Archetype: {result.archetype}",
        f"Passes Audit: {result.passes_audit}",
        "",
        "--- Position Counts ---",
    ]

    for pos, count in result.position_counts.items():
        target = ROSTER_TARGETS.get(pos, (0, 0))
        status = "✓" if target[0] <= count <= target[1] else "✗"
        lines.append(f"  {status} {pos}: {count} (target {target[0]}-{target[1]})")

    lines.extend([
        "",
        "--- Bye Week Check ---",
    ])

    if result.bye_violations:
        for v in result.bye_violations:
            lines.append(f"  ✗ {v}")
    else:
        lines.append("  ✓ No bye week violations")

    lines.extend([
        "",
        "--- Team Stacking ---",
    ])

    max_team = max(result.team_counts.values()) if result.team_counts else 0
    max_team_name = max(result.team_counts, key=result.team_counts.get) if result.team_counts else "N/A"
    lines.append(f"  Max stack: {max_team} from {max_team_name}")

    lines.extend([
        "",
        "--- Exposure Summary ---",
        f"  Players tracked: {len(result.exposure_summary)}",
        "",
        "--- CLV Estimate ---",
        f"  Average CLV delta: {result.estimated_clv:+.1f}",
    ])

    if result.warnings:
        lines.extend([
            "",
            "--- Warnings ---",
        ])
        for w in result.warnings:
            lines.append(f"  ! {w}")

    return "\n".join(lines)


def quick_audit(roster: Roster, archetype: Archetype) -> Tuple[bool, List[str]]:
    """Quick audit for CLI during draft.

    Returns: (passes, list of warnings)
    """
    warnings = []

    # Position check
    for pos, (min_tgt, max_tgt) in ROSTER_TARGETS.items():
        count = getattr(roster, f"{pos.lower()}_count")
        if count > max_tgt:
            warnings.append(f"{pos} count {count} exceeds max {max_tgt}")

    # Bye check
    bye_summary = get_roster_bye_summary(roster)
    for bye, data in bye_summary.items():
        if data["total"] >= NEVER_SAME_BYE:
            warnings.append(f"Bye {bye}: {data['total']} players (critical)")
        elif data["non_exempt"] > MAX_SAME_BYE:
            warnings.append(f"Bye {bye}: {data['non_exempt']} non-exempt (warning)")

    # Team check
    max_allowed = MAX_SAME_TEAM_ARCHETYPE_C if archetype == Archetype.C else MAX_SAME_TEAM
    team_summary = get_roster_team_summary(roster)
    for team, players in team_summary.items():
        if len(players) > max_allowed:
            warnings.append(f"{team}: {len(players)} players exceeds max {max_allowed}")

    passes = len([w for w in warnings if "critical" in w.lower()]) == 0

    return passes, warnings
