"""Dataclass models for BBM Draft Copilot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set
from enum import Enum


class Signal(str, Enum):
    """Player signal enum."""
    BUY = "BUY"
    FADE = "FADE"
    NEUTRAL = "NEUTRAL"


class Archetype(str, Enum):
    """Draft archetype enum."""
    A = "A"  # RB-forward
    B = "B"  # Hero RB
    C = "C"  # Stack-heavy
    D = "D"  # Zero RB
    E = "E"  # Contrarian / CLV-only


class DraftStatus(str, Enum):
    """Draft status enum."""
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


@dataclass
class Player:
    """Player model with BBM-specific attributes."""
    player_id: str
    name: str
    merge_name: str
    position: str  # QB, RB, WR, TE
    team: str
    bye_week: int
    adp: float
    strategy_rank: Optional[int] = None
    projection_pts: Optional[float] = None
    signal: Signal = Signal.NEUTRAL
    tier: Optional[str] = None  # elite, stack_core, mid_target, late_lottery, single_dart
    exposure_cap_pct: Optional[float] = None
    drift_coeff: float = 0.0
    injury_fade: bool = False
    notes: Optional[str] = None
    fade_rounds: Optional[List[str]] = None  # e.g. ["r3_5"] for round-specific fades

    def is_faded(self) -> bool:
        """Check if player should be excluded (global fade)."""
        return self.signal == Signal.FADE or self.injury_fade

    def is_faded_for_round(self, round_num: int) -> bool:
        """Check if player is faded for a specific round.

        If signal is FADE and fade_rounds is specified, only fade during those rounds.
        If signal is FADE and no fade_rounds, apply global fade to all rounds.
        """
        if self.signal != Signal.FADE and not self.injury_fade:
            return False

        # If no specific fade_rounds, apply global fade
        if not self.fade_rounds:
            return self.is_faded()

        # Check if current round falls within any fade band
        from ceminidfs.bbm.config import get_round_band
        current_band = get_round_band(round_num)
        return current_band in self.fade_rounds


@dataclass
class Roster:
    """Roster state during a draft."""
    players: List[Player] = field(default_factory=list)
    draft_position: int = 1  # 1-12
    current_round: int = 1  # 1-18

    # Position counts
    @property
    def qb_count(self) -> int:
        return sum(1 for p in self.players if p.position == "QB")

    @property
    def rb_count(self) -> int:
        return sum(1 for p in self.players if p.position == "RB")

    @property
    def wr_count(self) -> int:
        return sum(1 for p in self.players if p.position == "WR")

    @property
    def te_count(self) -> int:
        return sum(1 for p in self.players if p.position == "TE")

    @property
    def total_players(self) -> int:
        return len(self.players)

    def get_players_by_position(self, position: str) -> List[Player]:
        """Get all players at a given position."""
        return [p for p in self.players if p.position == position]

    def get_teams(self) -> Dict[str, List[Player]]:
        """Group players by NFL team."""
        teams: Dict[str, List[Player]] = {}
        for p in self.players:
            teams.setdefault(p.team, []).append(p)
        return teams

    def get_bye_weeks(self) -> Dict[int, List[Player]]:
        """Group players by bye week."""
        byes: Dict[int, List[Player]] = {}
        for p in self.players:
            byes.setdefault(p.bye_week, []).append(p)
        return byes

    def get_qb_bye_weeks(self) -> Set[int]:
        """Get set of bye weeks for QBs on roster."""
        return {p.bye_week for p in self.players if p.position == "QB"}

    def get_te_bye_weeks(self) -> Set[int]:
        """Get set of bye weeks for TEs on roster."""
        return {p.bye_week for p in self.players if p.position == "TE"}

    def has_teammate(self, player: Player) -> bool:
        """Check if a player from same team is on roster."""
        return any(p.team == player.team and p.player_id != player.player_id for p in self.players)

    def get_teammates(self, player: Player) -> List[Player]:
        """Get all teammates of a player on roster."""
        return [p for p in self.players if p.team == player.team and p.player_id != player.player_id]

    def get_player_count_by_team(self, team: str) -> int:
        """Count players from a specific NFL team."""
        return sum(1 for p in self.players if p.team == team)

    def get_player_count_by_bye(self, bye_week: int) -> int:
        """Count players with a specific bye week."""
        return sum(1 for p in self.players if p.bye_week == bye_week)


@dataclass
class DraftState:
    """Overall draft state including room context."""
    draft_id: str
    slot: int  # 1-12
    archetype: Archetype
    status: DraftStatus
    roster: Roster
    taken_players: Set[str] = field(default_factory=set)  # player_ids taken by others
    draft_date: Optional[datetime] = None
    underdog_entry_id: Optional[str] = None
    single_entry: bool = False  # Golden / 1-max: skip portfolio exposure + combo caps

    @property
    def current_pick_num(self) -> int:
        """Calculate current pick number in draft."""
        # Snake draft: rounds 1, 3, 5... go 1-12, rounds 2, 4, 6... go 12-1
        round_num = self.roster.current_round
        if round_num % 2 == 1:  # Odd round
            pick_in_round = self.slot
        else:  # Even round (snake back)
            pick_in_round = 13 - self.slot
        return (round_num - 1) * 12 + pick_in_round

    @property
    def picks_remaining(self) -> int:
        """Calculate remaining picks for this drafter."""
        from ceminidfs.bbm.config import DRAFT_ROUNDS
        return DRAFT_ROUNDS - self.roster.total_players


@dataclass
class Pick:
    """Individual pick record."""
    draft_id: str
    round: int
    pick_num: int
    player_id: str
    player_name: str
    is_mine: bool = False


@dataclass
class Draft:
    """Draft metadata."""
    draft_id: str
    draft_date: datetime
    slot: int
    archetype: str
    status: DraftStatus
    underdog_entry_id: Optional[str] = None


@dataclass
class ComboPair:
    """Stack combo pair with exposure cap."""
    player_a: str
    player_b: str
    cap_pct: float = 0.25


@dataclass
class ExposureRecord:
    """Exposure tracking for a player."""
    player_id: str
    player_name: str
    total_entries: int = 150
    completed_drafts: int = 0
    in_progress_drafts: int = 0

    @property
    def exposure_pct(self) -> float:
        """Calculate exposure percentage."""
        from ceminidfs.bbm.config import IN_PROGRESS_EXPOSURE_WEIGHT
        weighted = self.completed_drafts + (self.in_progress_drafts * IN_PROGRESS_EXPOSURE_WEIGHT)
        return weighted / self.total_entries if self.total_entries > 0 else 0.0


@dataclass
class Recommendation:
    """Player recommendation with scoring breakdown."""
    player: Player
    score: float
    raw_projection: float
    clv_bonus: float
    stack_mult: float
    archetype_mult: float
    exposure_mult: float
    warnings: List[str] = field(default_factory=list)
    is_stack_opportunity: bool = False

    @property
    def rank(self) -> int:
        """Display rank (1-based)."""
        return 0  # Set by recommender

    def to_display_line(self) -> str:
        """Format for CLI display."""
        signal_str = f"  {self.player.signal.value}" if self.player.signal != Signal.NEUTRAL else ""
        warn_str = f"  WARN: {'; '.join(self.warnings)}" if self.warnings else ""
        return (
            f"{self.player.name} {self.player.position} {self.player.team}"
            f"{signal_str}  exp {self.exposure_mult:.0%}"
            f"{warn_str}"
        )


@dataclass
class AuditResult:
    """Post-draft audit results."""
    draft_id: str
    archetype: str
    position_counts: Dict[str, int]
    bye_violations: List[str]
    team_counts: Dict[str, int]
    exposure_summary: Dict[str, float]
    estimated_clv: float
    passes_audit: bool
    warnings: List[str]


@dataclass
class LedgerCounts:
    """Exposure counts from ledger."""
    archetype_counts: Dict[str, int] = field(default_factory=dict)
    player_counts: Dict[str, int] = field(default_factory=dict)
    combo_counts: Dict[str, int] = field(default_factory=dict)  # "player_a|player_b"

    def get_archetype_pct(self, archetype: str) -> float:
        """Get archetype completion percentage."""
        from ceminidfs.bbm.config import ARCHETYPE_TARGETS, TOTAL_ENTRIES

        if archetype not in ARCHETYPE_TARGETS:
            return 0.0
        current = self.archetype_counts.get(archetype, 0)
        return current / TOTAL_ENTRIES

    def get_archetype_gap(self, archetype: str) -> float:
        """Get how far below target ratio this archetype is."""
        from ceminidfs.bbm.config import ARCHETYPE_TARGETS, TOTAL_ENTRIES
        if archetype not in ARCHETYPE_TARGETS:
            return 0.0
        current = self.archetype_counts.get(archetype, 0)
        target = ARCHETYPE_TARGETS[archetype]
        return (target - current) / TOTAL_ENTRIES

    def get_player_exposure(self, player_id: str) -> float:
        """Get player exposure percentage."""
        from ceminidfs.bbm.config import TOTAL_ENTRIES

        return self.player_counts.get(player_id, 0) / TOTAL_ENTRIES


@dataclass
class PivotResult:
    """Archetype pivot decision."""
    new_archetype: Optional[Archetype]
    warning: Optional[str]
    trigger_reason: Optional[str]
