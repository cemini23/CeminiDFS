"""Underdog exposure CSV parser and ledger reconciliation.

Handles parsing of Underdog exposure CSV with tolerant column aliases,
and diffing against internal ledger exposure tracking.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set


# Tolerant column alias mapping
COLUMN_ALIASES = {
    "player": ["player", "name", "player name", "player_name"],
    "position": ["position", "pos"],
    "team": ["team", "nfl team", "nfl_team"],
    "adp": ["adp", "adp_pick", "adp pick"],
    "times_drafted": ["times drafted", "times_drafted", "drafted", "count"],
    "exposure_pct": [
        "exposure %", "exposure_pct", "exposure", "exposure percent",
        "draft %", "draft_pct", "draft_percent", "draft percentage",
        "percent", "%"
    ],
    "total_fees": [
        "total entry fees", "total_entry_fees", "entry fees",
        "fees", "total fees"
    ],
}


@dataclass
class UnderdogExposureRecord:
    """Parsed exposure record from Underdog CSV."""
    player_name: str
    position: str
    team: Optional[str]
    adp: Optional[float]
    times_drafted: int
    exposure_pct: float
    total_fees: Optional[float]
    raw_row: Dict[str, str]

    @property
    def display_name(self) -> str:
        """Normalized display name."""
        return f"{self.player_name} {self.position}" + (f" {self.team}" if self.team else "")


@dataclass
class ExposureDiff:
    """Diff between ledger and Underdog exposure."""
    player_id: str
    player_name: str
    ledger_count: int
    underdog_count: int
    ledger_pct: float
    underdog_pct: float
    diff_count: int
    diff_pct: float
    status: str  # "match", "ledger_ahead", "underdog_ahead", "unknown"

    def __str__(self) -> str:
        if self.status == "match":
            return f"✓ {self.player_name}: {self.ledger_pct:.1%} (match)"
        elif self.status == "ledger_ahead":
            return f"▲ {self.player_name}: ledger {self.ledger_pct:.1%} vs UD {self.underdog_pct:.1%} (+{self.diff_pct:.1%})"
        elif self.status == "underdog_ahead":
            return f"▼ {self.player_name}: ledger {self.ledger_pct:.1%} vs UD {self.underdog_pct:.1%} ({self.diff_pct:.1%})"
        else:
            return f"? {self.player_name}: unknown"


@dataclass
class ReconcileResult:
    """Result of exposure reconciliation."""
    total_underdog_records: int
    matched_records: int
    ledger_ahead: List[ExposureDiff]
    underdog_ahead: List[ExposureDiff]
    unknown_in_ledger: List[str]  # Player names not found in Underdog
    unknown_in_underdog: List[UnderdogExposureRecord]  # Underdog records not in ledger
    total_variance: float
    drifts_flagged: List[str]

    def summary(self) -> str:
        """Generate summary report."""
        lines = [
            "=== Exposure Reconciliation Summary ===",
            f"Underdog records: {self.total_underdog_records}",
            f"Matched: {self.matched_records}",
            f"Ledger ahead: {len(self.ledger_ahead)}",
            f"Underdog ahead: {len(self.underdog_ahead)}",
            f"Unknown in ledger: {len(self.unknown_in_ledger)}",
            f"Unknown in Underdog: {len(self.unknown_in_underdog)}",
            f"Total variance: {self.total_variance:.1%}",
        ]

        if self.drifts_flagged:
            lines.extend(["", "--- Drifts Flagged ---"])
            for drift in self.drifts_flagged[:10]:  # Show first 10
                lines.append(f"  ! {drift}")
            if len(self.drifts_flagged) > 10:
                lines.append(f"  ... and {len(self.drifts_flagged) - 10} more")

        return "\n".join(lines)


def parse_underdog_exposure_csv(csv_path: str | Path) -> List[UnderdogExposureRecord]:
    """Parse Underdog exposure CSV with tolerant column detection.

    Handles various header aliases and CSV formats.

    Args:
        csv_path: Path to Underdog exposure CSV file

    Returns:
        List of parsed exposure records

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If required columns can't be identified
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Exposure CSV not found: {csv_path}")

    records: List[UnderdogExposureRecord] = []

    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        # Try to detect dialect
        sample = f.read(8192)
        f.seek(0)

        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(sample, delimiters=',\t;')
        except csv.Error:
            dialect = csv.excel  # Default to comma

        reader = csv.DictReader(f, dialect=dialect)

        if not reader.fieldnames:
            raise ValueError("CSV file has no headers")

        # Map actual headers to canonical names
        header_map = _map_headers(reader.fieldnames)

        # Validate required columns
        required = ["player", "exposure_pct"]
        missing = [r for r in required if r not in header_map]
        if missing:
            raise ValueError(f"Required columns not found: {missing}. Headers: {reader.fieldnames}")

        for row in reader:
            try:
                record = _parse_row(row, header_map)
                if record:
                    records.append(record)
            except (ValueError, KeyError):
                # Log but continue on parse errors
                continue

    return records


def _map_headers(fieldnames: List[str]) -> Dict[str, str]:
    """Map actual CSV headers to canonical column names."""
    header_map = {}

    for actual_header in fieldnames:
        actual_lower = actual_header.strip().lower()

        for canonical, aliases in COLUMN_ALIASES.items():
            if actual_lower in [a.lower() for a in aliases]:
                header_map[canonical] = actual_header
                break

    return header_map


def _parse_row(row: Dict[str, str], header_map: Dict[str, str]) -> Optional[UnderdogExposureRecord]:
    """Parse a single CSV row into an exposure record."""
    # Required: player name
    player_name = row.get(header_map.get("player", "Player"), "").strip()
    if not player_name:
        return None

    # Required: exposure percentage
    exposure_raw = row.get(header_map.get("exposure_pct", "Exposure %"), "0")
    try:
        # Handle percentage as decimal or with % sign
        exposure_str = exposure_raw.replace('%', '').strip()
        exposure_pct = float(exposure_str) / 100 if float(exposure_str) > 1 else float(exposure_str)
    except (ValueError, TypeError):
        exposure_pct = 0.0

    # Optional fields
    position = row.get(header_map.get("position", ""), "").strip().upper() or None
    team = row.get(header_map.get("team", ""), "").strip().upper() or None

    adp_raw = row.get(header_map.get("adp", ""), "")
    try:
        adp = float(adp_raw) if adp_raw else None
    except (ValueError, TypeError):
        adp = None

    times_raw = row.get(header_map.get("times_drafted", ""), "0")
    try:
        times_drafted = int(float(times_raw)) if times_raw else 0
    except (ValueError, TypeError):
        times_drafted = 0

    fees_raw = row.get(header_map.get("total_fees", ""), "")
    try:
        # Remove currency symbols and commas
        fees_clean = fees_raw.replace('$', '').replace(',', '').strip()
        total_fees = float(fees_clean) if fees_clean else None
    except (ValueError, TypeError):
        total_fees = None

    return UnderdogExposureRecord(
        player_name=player_name,
        position=position or "UNK",
        team=team,
        adp=adp,
        times_drafted=times_drafted,
        exposure_pct=exposure_pct,
        total_fees=total_fees,
        raw_row=row
    )


def reconcile_exposure(
    ledger_counts: Dict[str, int],
    ledger_name_map: Dict[str, str],  # player_id -> canonical name
    underdog_records: List[UnderdogExposureRecord],
    total_entries: int = 150,
    variance_threshold: float = 0.02  # 2% difference threshold
) -> ReconcileResult:
    """Reconcile internal ledger against Underdog exposure CSV.

    Args:
        ledger_counts: Map of player_id -> count from ledger
        ledger_name_map: Map of player_id -> canonical name for matching
        underdog_records: Parsed Underdog exposure records
        total_entries: Total entries in portfolio
        variance_threshold: Pct difference threshold for flagging

    Returns:
        ReconcileResult with all diffs and drifts
    """
    matched = 0
    ledger_ahead: List[ExposureDiff] = []
    underdog_ahead: List[ExposureDiff] = []
    unknown_in_ledger: List[str] = []
    unknown_in_underdog: List[UnderdogExposureRecord] = []

    # Build reverse lookup: normalized name -> player_id
    name_to_id: Dict[str, str] = {}
    for player_id, canonical_name in ledger_name_map.items():
        normalized = _normalize_name(canonical_name)
        name_to_id[normalized] = player_id

    # Track matched ledger entries
    ledger_matched: Set[str] = set()

    for ud_record in underdog_records:
        # Try to match by name
        normalized_ud = _normalize_name(ud_record.player_name)
        player_id = name_to_id.get(normalized_ud)

        # Try fuzzy match if exact fails
        if not player_id:
            player_id = _fuzzy_match_name(normalized_ud, name_to_id)

        if player_id:
            ledger_matched.add(player_id)
            ledger_count = ledger_counts.get(player_id, 0)
            ledger_pct = ledger_count / total_entries

            diff_count = ledger_count - ud_record.times_drafted
            diff_pct = ledger_pct - ud_record.exposure_pct

            # Determine status
            if abs(diff_pct) <= variance_threshold:
                status = "match"
                matched += 1
            elif diff_pct > 0:
                status = "ledger_ahead"
                ledger_ahead.append(ExposureDiff(
                    player_id=player_id,
                    player_name=ledger_name_map.get(player_id, ud_record.player_name),
                    ledger_count=ledger_count,
                    underdog_count=ud_record.times_drafted,
                    ledger_pct=ledger_pct,
                    underdog_pct=ud_record.exposure_pct,
                    diff_count=diff_count,
                    diff_pct=diff_pct,
                    status=status
                ))
            else:
                status = "underdog_ahead"
                underdog_ahead.append(ExposureDiff(
                    player_id=player_id,
                    player_name=ledger_name_map.get(player_id, ud_record.player_name),
                    ledger_count=ledger_count,
                    underdog_count=ud_record.times_drafted,
                    ledger_pct=ledger_pct,
                    underdog_pct=ud_record.exposure_pct,
                    diff_count=diff_count,
                    diff_pct=diff_pct,
                    status=status
                ))
        else:
            # No match found in ledger
            unknown_in_underdog.append(ud_record)

    # Find ledger entries not in Underdog
    for player_id in ledger_counts:
        if player_id not in ledger_matched:
            unknown_in_ledger.append(ledger_name_map.get(player_id, player_id))

    # Calculate total variance
    total_variance = sum(abs(d.diff_pct) for d in ledger_ahead + underdog_ahead)

    # Flag drifts (significant differences)
    drifts = []
    for diff in ledger_ahead + underdog_ahead:
        if abs(diff.diff_pct) > variance_threshold * 2:  # 4% threshold for drift
            drifts.append(
                f"{diff.player_name}: {diff.diff_pct:+.1%} variance"
            )

    return ReconcileResult(
        total_underdog_records=len(underdog_records),
        matched_records=matched,
        ledger_ahead=ledger_ahead,
        underdog_ahead=underdog_ahead,
        unknown_in_ledger=unknown_in_ledger,
        unknown_in_underdog=unknown_in_underdog,
        total_variance=total_variance,
        drifts_flagged=drifts
    )


def _normalize_name(name: str) -> str:
    """Normalize player name for matching."""
    # Lowercase, remove suffixes, strip punctuation
    normalized = name.lower().strip()

    # Remove common suffixes
    suffixes = [" jr.", " jr", " sr.", " sr", " iii", " ii", " iv", " v"]
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].strip()

    # Remove punctuation
    normalized = normalized.replace('.', '').replace("'", '').replace('-', ' ')

    # Normalize whitespace
    normalized = ' '.join(normalized.split())

    return normalized


def _fuzzy_match_name(normalized_name: str, name_to_id: Dict[str, str]) -> Optional[str]:
    """Attempt fuzzy name match for unmatched players."""
    # Simple substring match first
    for name, player_id in name_to_id.items():
        if normalized_name in name or name in normalized_name:
            return player_id

    return None


def format_reconcile_report(result: ReconcileResult) -> str:
    """Format reconcile result for CLI output."""

    return result.summary()


def reconcile_from_csv(csv_path: str | Path) -> ReconcileResult:
    """Load ledger counts and reconcile against Underdog exposure CSV."""

    import sqlite3

    from ceminidfs.bbm.config import TOTAL_ENTRIES
    from ceminidfs.bbm.ledger import get_db_path

    db = get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.player_id, pd.name, COUNT(DISTINCT d.draft_id)
        FROM picks p
        JOIN drafts d ON p.draft_id = d.draft_id
        JOIN players_dim pd ON p.player_id = pd.player_id
        WHERE p.is_mine = 1 AND d.status = 'complete'
        GROUP BY p.player_id, pd.name
        """
    )
    ledger_counts: dict[str, int] = {}
    ledger_name_map: dict[str, str] = {}
    for player_id, name, count in cursor.fetchall():
        ledger_counts[player_id] = count
        ledger_name_map[player_id] = name
    conn.close()

    records = parse_underdog_exposure_csv(csv_path)
    return reconcile_exposure(
        ledger_counts,
        ledger_name_map,
        records,
        total_entries=TOTAL_ENTRIES,
    )


def quick_reconcile_check(
    ledger_exposure: Dict[str, float],
    underdog_exposure: Dict[str, float],
    threshold: float = 0.05
) -> Tuple[bool, List[str]]:
    """Quick check for exposure drift.

    Returns: (passes, list of drift warnings)
    """
    warnings = []

    all_players = set(ledger_exposure.keys()) | set(underdog_exposure.keys())

    for player in all_players:
        ledger_pct = ledger_exposure.get(player, 0.0)
        ud_pct = underdog_exposure.get(player, 0.0)

        diff = abs(ledger_pct - ud_pct)

        if diff > threshold:
            direction = "ledger ahead" if ledger_pct > ud_pct else "UD ahead"
            warnings.append(
                f"{player}: {ledger_pct:.1%} vs {ud_pct:.1%} ({direction})"
            )

    passes = len(warnings) == 0

    return passes, warnings
