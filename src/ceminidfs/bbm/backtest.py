"""BBM III replay harness for backtesting recommender performance.

Implements real draft room replay against historical pick data.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from ceminidfs.bbm.models import Player, Roster, DraftState, Archetype, DraftStatus
from ceminidfs.bbm.recommender import recommend_top3
from ceminidfs.bbm.validator import validate_pick
from ceminidfs.bbm.registry import load_registry, build_seed_registry
from ceminidfs.bbm.config import get_bye_week


BBM3_DOWNLOAD_URL = (
    "https://underdognetwork.com/football/best-ball-research/"
    "best-ball-mania-iii-downloadable-pick-by-pick-data"
)
BBM3_EXPECTED_DIR = Path("data/bbm/bbm3_historical")
BBM3_EXPECTED_PATH = "data/bbm/bbm3_historical/"


@dataclass
class BacktestMetrics:
    """Metrics from backtest run."""
    sample_size: int
    structural_pass_rate: float
    median_clv_delta: float
    latency_p99_ms: float
    picks_evaluated: int
    picks_matched_adp: int
    mean_absolute_error_vs_adp: float
    recommendations_made: int
    warnings_generated: int


@dataclass
class BacktestResult:
    """Result of a backtest run."""
    success: bool
    metrics: Optional[BacktestMetrics]
    message: str
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "metrics": {
                "sample_size": self.metrics.sample_size if self.metrics else 0,
                "structural_pass_rate": self.metrics.structural_pass_rate if self.metrics else 0.0,
                "median_clv_delta": self.metrics.median_clv_delta if self.metrics else 0.0,
                "latency_p99_ms": self.metrics.latency_p99_ms if self.metrics else 0.0,
                "picks_evaluated": self.metrics.picks_evaluated if self.metrics else 0,
                "picks_matched_adp": self.metrics.picks_matched_adp if self.metrics else 0,
            } if self.metrics else None,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class DraftReplayResult:
    """Result of replaying a single draft room."""
    draft_id: str
    total_picks: int
    my_picks: List[Dict[str, Any]] = field(default_factory=list)
    top3_hits: int = 0
    clv_deltas: List[float] = field(default_factory=list)
    violations_by_pick: List[List[str]] = field(default_factory=list)
    latencies_ms: List[float] = field(default_factory=list)
    recommendations_made: int = 0
    warnings_generated: int = 0


def load_pick_csv(path: Path | str) -> List[Dict[str, Any]]:
    """Load picks from CSV with tolerant parser.

    Expected columns: draft_id, round, pick_num, slot, player_name, position, team, adp
    Tolerates variations in column names (case insensitive, optional underscores).

    Args:
        path: Path to CSV file

    Returns:
        List of pick dicts with normalized keys
    """
    picks: List[Dict[str, Any]] = []
    path = Path(path)

    if not path.exists():
        return picks

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        # Normalize column names
        field_map: Dict[str, str] = {}
        if reader.fieldnames:
            for field in reader.fieldnames:
                normalized = field.lower().replace("_", "").replace(" ", "")
                if normalized in ["draftid", "draft_id", "draft"]:
                    field_map[field] = "draft_id"
                elif normalized in ["round", "rd"]:
                    field_map[field] = "round"
                elif normalized in ["picknum", "pick_num", "pick", "picknumber"]:
                    field_map[field] = "pick_num"
                elif normalized in ["slot", "draftslot", "draft_slot"]:
                    field_map[field] = "slot"
                elif normalized in ["playername", "player_name", "name", "player"]:
                    field_map[field] = "player_name"
                elif normalized in ["pos", "position"]:
                    field_map[field] = "position"
                elif normalized in ["team", "nflteam"]:
                    field_map[field] = "team"
                elif normalized in ["adp", "averageadp", "avgadp"]:
                    field_map[field] = "adp"

            for row in reader:
                normalized: Dict[str, Any] = {}
                for key, value in row.items():
                    if key is None:
                        continue
                    safe_key = key or ""
                    mapped_key = field_map.get(key, safe_key.lower().replace("_", "").replace(" ", ""))
                    normalized[mapped_key] = value

                # Parse numeric fields
                try:
                    pick = {
                        "draft_id": str(normalized.get("draft_id", "")),
                        "round": int(normalized.get("round", 0)),
                        "pick_num": int(normalized.get("pick_num", 0)),
                        "slot": int(normalized.get("slot", 0)),
                        "player_name": str(normalized.get("player_name", "")).strip(),
                        "position": str(normalized.get("position", "")).upper().strip(),
                        "team": str(normalized.get("team", "")).upper().strip(),
                        "adp": float(normalized.get("adp", 999)),
                    }
                    if pick["draft_id"] and pick["player_name"]:
                        picks.append(pick)
                except (ValueError, TypeError):
                    continue

    return picks


def group_picks_by_draft(picks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group picks by draft_id.

    Args:
        picks: List of pick dicts

    Returns:
        Dict mapping draft_id -> sorted list of picks for that draft
    """
    by_draft: Dict[str, List[Dict[str, Any]]] = {}
    for pick in picks:
        draft_id = pick.get("draft_id", "unknown")
        by_draft.setdefault(draft_id, []).append(pick)

    # Sort each draft's picks by pick_num
    for draft_id in by_draft:
        by_draft[draft_id].sort(key=lambda p: p.get("pick_num", 0))

    return by_draft


def _normalize_name(name: str) -> str:
    """Normalize player name for matching."""
    return name.lower().replace("'", "").replace(".", " ").replace("-", " ").replace("  ", " ").strip()


def _build_player_from_row(
    pick: Dict[str, Any], registry_players: List[Dict[str, Any]]
) -> Optional[Player]:
    """Build a Player object from a pick, matching against registry."""
    pick_name = _normalize_name(pick.get("player_name", ""))
    pick_pos = pick.get("position", "").upper()
    pick_team = pick.get("team", "").upper()

    # Find matching player in registry
    for reg_player in registry_players:
        reg_name = _normalize_name(reg_player.get("name", ""))
        reg_merge = _normalize_name(reg_player.get("merge_name", ""))

        # Match by name or merge_name
        if pick_name in (reg_name, reg_merge) or reg_name in pick_name or pick_name in reg_name:
            # Also verify position matches if both specified
            reg_pos = reg_player.get("position", "").upper()
            if pick_pos and reg_pos and pick_pos != reg_pos:
                continue

            return Player(
                player_id=reg_player.get("player_id", f"bbm:{pick_name.replace(' ', '-')}"),
                name=reg_player.get("name", pick.get("player_name", "")),
                merge_name=reg_player.get("merge_name", pick_name),
                position=reg_player.get("position", pick_pos),
                team=reg_player.get("team", pick_team) or reg_player.get("team", "FA"),
                bye_week=reg_player.get("bye_week", get_bye_week(pick_team) or 0),
                adp=reg_player.get("adp", pick.get("adp", 999)),
                strategy_rank=reg_player.get("strategy_rank", int(pick.get("adp", 999))),
                projection_pts=reg_player.get("projection_pts", 100.0),
                signal=reg_player.get("signal", "NEUTRAL"),
                tier=reg_player.get("tier", "mid_target"),
                exposure_cap_pct=reg_player.get("exposure_cap_pct", 0.20),
                drift_coeff=reg_player.get("drift_coeff", 0.0),
                injury_fade=reg_player.get("injury_fade", False),
                notes=reg_player.get("notes", ""),
                fade_rounds=reg_player.get("fade_rounds"),
            )

    # No registry match - create generic player
    return Player(
        player_id=f"bbm:{pick_name.replace(' ', '-')}",
        name=pick.get("player_name", ""),
        merge_name=pick_name,
        position=pick_pos,
        team=pick_team,
        bye_week=get_bye_week(pick_team) or 0,
        adp=pick.get("adp", 999),
        strategy_rank=int(pick.get("adp", 999)),
        projection_pts=100.0,
        signal="NEUTRAL",
        tier="mid_target",
        exposure_cap_pct=0.20,
    )


def replay_draft_room(
    picks: List[Dict[str, Any]],
    registry_players: List[Dict[str, Any]],
    archetype: str = "B",
    slot: int = 4,
) -> DraftReplayResult:
    """Replay a single draft room and evaluate recommender choices.

    Args:
        picks: List of pick dicts for this draft room (sorted by pick_num)
        registry_players: List of player dicts from registry
        archetype: Archetype code used for this draft
        slot: Our draft slot (1-12)

    Returns:
        DraftReplayResult with replay analysis
    """
    if not picks:
        return DraftReplayResult(draft_id="unknown", total_picks=0)

    draft_id = picks[0].get("draft_id", "unknown")
    result = DraftReplayResult(draft_id=draft_id, total_picks=len(picks))

    # In-memory tracking
    taken_player_ids: set[str] = set()
    roster = Roster(players=[], draft_position=slot, current_round=1)

    # Build registry player objects for availability lookup
    registry_player_objects: List[Player] = []
    for rp in registry_players:
        registry_player_objects.append(
            Player(
                player_id=rp.get("player_id", ""),
                name=rp.get("name", ""),
                merge_name=rp.get("merge_name", ""),
                position=rp.get("position", ""),
                team=rp.get("team", ""),
                bye_week=rp.get("bye_week", 0),
                adp=rp.get("adp", 999),
                strategy_rank=rp.get("strategy_rank", 999),
                projection_pts=rp.get("projection_pts", 100.0),
                signal=rp.get("signal", "NEUTRAL"),
                tier=rp.get("tier", "mid_target"),
                exposure_cap_pct=rp.get("exposure_cap_pct", 0.20),
                drift_coeff=rp.get("drift_coeff", 0.0),
                injury_fade=rp.get("injury_fade", False),
                fade_rounds=rp.get("fade_rounds"),
            )
        )

    def zero_exposure_fn(_player_id: str) -> float:
        return 0.0

    arch_enum = Archetype(archetype) if archetype in ["A", "B", "C", "D", "E"] else Archetype.B

    for pick in picks:
        pick_slot = pick.get("slot", 0)
        pick_num = pick.get("pick_num", 0)
        round_num = pick.get("round", 1)

        # Update roster current round based on pick
        roster.current_round = round_num

        # Build player from this pick
        player = _build_player_from_row(pick, registry_players)

        if pick_slot == slot:
            # This is our pick - evaluate recommender
            draft_state = DraftState(
                draft_id=draft_id,
                slot=slot,
                archetype=arch_enum,
                status=DraftStatus.IN_PROGRESS,
                roster=roster,
                taken_players=taken_player_ids.copy(),
            )

            # Get available players (registry players not taken)
            available = [p for p in registry_player_objects if p.player_id not in taken_player_ids]

            # Call recommender and track latency
            start_time = time.time()
            recommendations = recommend_top3(
                draft_state=draft_state,
                available_players=available,
                exposure_pct_fn=zero_exposure_fn,
                max_recommendations=3,
            )
            elapsed_ms = (time.time() - start_time) * 1000
            result.latencies_ms.append(elapsed_ms)

            # Record pick analysis
            pick_analysis: Dict[str, Any] = {
                "round": round_num,
                "pick_num": pick_num,
                "actual_player": player.name,
                "actual_adp": player.adp,
            }

            # Check if actual pick in top-3
            top3_names = [_normalize_name(r.player.name) for r in recommendations[:3]]
            actual_name_normalized = _normalize_name(player.name)
            pick_analysis["in_top3"] = actual_name_normalized in top3_names
            if pick_analysis["in_top3"]:
                result.top3_hits += 1

            # Calculate CLV delta
            clv_delta = pick_num - player.adp
            pick_analysis["clv_delta"] = clv_delta
            result.clv_deltas.append(clv_delta)

            # Validate pick against structural rules
            violations = validate_pick(player, roster, arch_enum)
            pick_analysis["violations"] = violations
            result.violations_by_pick.append(violations)

            # Track warnings
            if violations:
                result.warnings_generated += len(violations)

            result.my_picks.append(pick_analysis)
            result.recommendations_made += len(recommendations)

            # Add player to our roster
            roster.players.append(player)

        # Mark player as taken (by any slot)
        if player and player.player_id:
            taken_player_ids.add(player.player_id)

    return result


def run_backtest(
    sample: int = 100,
    csv_path: Optional[Path] = None,
    fixture_path: Optional[Path] = None,
) -> BacktestResult:
    """Run backtest against BBM historical pick data.

    Args:
        sample: Number of draft rooms to replay (default 100)
        csv_path: Path to custom CSV with pick data
        fixture_path: Path to fixture CSV for testing

    Returns:
        BacktestResult with metrics or message about data requirements
    """
    # Determine data source
    data_path: Optional[Path] = None
    source_desc: str = ""

    if csv_path:
        data_path = Path(csv_path) if isinstance(csv_path, str) else csv_path
        source_desc = f"custom CSV: {data_path}"
    elif fixture_path:
        data_path = Path(fixture_path) if isinstance(fixture_path, str) else fixture_path
        source_desc = f"fixture: {data_path}"
    else:
        # Check for BBM III data in default locations
        data_path = _get_bbm3_data_path()
        if data_path:
            source_desc = f"BBM3 data: {data_path}"

    if not data_path or not data_path.exists():
        return BacktestResult(
            success=False,
            metrics=None,
            message=(
                "No backtest data found. To run backtest:\n"
                "1. Provide --csv <path> to custom pick data, or\n"
                "2. Provide --fixture <path> to fixture file, or\n"
                "3. Download BBM III pick-by-pick data from:\n"
                f"   {BBM3_DOWNLOAD_URL}\n"
                f"4. Place in {BBM3_EXPECTED_PATH} directory\n"
                "5. Re-run: ceminidfs bbm backtest --sample 100"
            ),
            details={
                "required_data": "pick-by-pick CSV",
                "expected_location": BBM3_EXPECTED_PATH,
                "sample_requested": sample,
            }
        )

    # Load picks from CSV
    picks = load_pick_csv(data_path)
    if not picks:
        return BacktestResult(
            success=False,
            metrics=None,
            message=f"No valid picks found in {data_path}",
            details={"data_path": str(data_path)}
        )

    # Group by draft
    picks_by_draft = group_picks_by_draft(picks)

    # Limit to sample size
    draft_ids = list(picks_by_draft.keys())[:sample]

    # Load registry for player matching
    registry = load_registry()
    if not registry.get("players"):
        registry = build_seed_registry()
    registry_players = registry.get("players", [])

    # Replay each draft room
    all_results: List[DraftReplayResult] = []
    for draft_id in draft_ids:
        draft_picks = picks_by_draft[draft_id]
        # Determine archetype and slot from first few picks (or use defaults)
        # For backtest, we assume slot=4 and archetype='B' as defaults
        slot = 4
        # Try to infer slot from picks
        for p in draft_picks[:24]:  # Look at first 2 rounds
            if p.get("pick_num", 0) <= 12:
                # This is round 1 - slot = pick_num
                slot = p.get("slot", 4)
                break

        replay_result = replay_draft_room(
            picks=draft_picks,
            registry_players=registry_players,
            archetype="B",
            slot=slot,
        )
        all_results.append(replay_result)

    # Aggregate metrics
    metrics = _aggregate_metrics(all_results, sample)

    return BacktestResult(
        success=True,
        metrics=metrics,
        message=f"Backtest completed for {len(draft_ids)} draft rooms from {source_desc}",
        details={
            "drafts_replayed": len(draft_ids),
            "total_picks": sum(r.total_picks for r in all_results),
            "picks_evaluated": metrics.picks_evaluated,
            "data_source": str(data_path),
        }
    )


def _aggregate_metrics(results: List[DraftReplayResult], sample: int) -> BacktestMetrics:
    """Aggregate metrics from all draft replay results."""
    all_clv_deltas: List[float] = []
    all_violations: List[List[str]] = []
    all_latencies: List[float] = []
    total_top3_hits = 0
    total_picks_evaluated = 0
    total_recommendations = 0
    total_warnings = 0

    for result in results:
        all_clv_deltas.extend(result.clv_deltas)
        all_violations.extend(result.violations_by_pick)
        all_latencies.extend(result.latencies_ms)
        total_top3_hits += result.top3_hits
        total_picks_evaluated += len(result.my_picks)
        total_recommendations += result.recommendations_made
        total_warnings += result.warnings_generated

    # Calculate structural pass rate
    structural_pass_rate = calculate_pass_rate(all_violations)

    # Calculate median CLV delta
    clv_stats = calculate_clv_metrics(all_clv_deltas)

    # Calculate latency p99
    latency_p99 = _calculate_p99(all_latencies) if all_latencies else 0.0

    # Calculate MAE vs ADP (simplified: mean of absolute CLV deltas)
    mae_vs_adp = sum(abs(d) for d in all_clv_deltas) / len(all_clv_deltas) if all_clv_deltas else 0.0

    # Picks matched ADP (CLV delta within 12 picks = 1 round)
    picks_matched_adp = sum(1 for d in all_clv_deltas if abs(d) <= 12)

    return BacktestMetrics(
        sample_size=sample,
        structural_pass_rate=structural_pass_rate,
        median_clv_delta=clv_stats["median"],
        latency_p99_ms=latency_p99,
        picks_evaluated=total_picks_evaluated,
        picks_matched_adp=picks_matched_adp,
        mean_absolute_error_vs_adp=mae_vs_adp,
        recommendations_made=total_recommendations,
        warnings_generated=total_warnings,
    )


def _calculate_p99(values: List[float]) -> float:
    """Calculate 99th percentile."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * 0.99)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


def write_backtest_report(result: BacktestResult, path: Path | str) -> Path:
    """Write backtest result to JSON file.

    Args:
        result: BacktestResult to write
        path: Output file path

    Returns:
        Path to written file
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "success": result.success,
        "message": result.message,
        "metrics": result.to_dict().get("metrics"),
        "details": result.details,
    }

    path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    return path


def _get_bbm3_data_path() -> Optional[Path]:
    """Check for BBM III data file in expected locations."""
    search_paths = [
        BBM3_EXPECTED_DIR / "bbm3_picks.csv",
        BBM3_EXPECTED_DIR / "bbm3_pick_data.csv",
        BBM3_EXPECTED_DIR / "pick_by_pick.csv",
    ]

    for path in search_paths:
        if path.exists():
            return path

    return None


def calculate_pass_rate(violations_by_pick: List[List[str]]) -> float:
    """Calculate structural rule pass rate from violation lists."""
    if not violations_by_pick:
        return 0.0

    critical_violations = [
        v for v in violations_by_pick
        if any("HARD_LIMIT" in x or "OVERFLOW" in x or "CRITICAL" in x or "FADED" in x for x in v)
    ]

    passes = len(violations_by_pick) - len(critical_violations)
    return passes / len(violations_by_pick)


def calculate_clv_metrics(clv_deltas: List[float]) -> Dict[str, float]:
    """Calculate CLV delta statistics."""
    if not clv_deltas:
        return {"median": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}

    sorted_deltas = sorted(clv_deltas)
    n = len(sorted_deltas)

    median = sorted_deltas[n // 2] if n % 2 else (sorted_deltas[n // 2 - 1] + sorted_deltas[n // 2]) / 2

    return {
        "median": median,
        "mean": sum(clv_deltas) / len(clv_deltas),
        "min": min(clv_deltas),
        "max": max(clv_deltas),
    }


def validate_backtest_readiness() -> Tuple[bool, str]:
    """Check if system is ready to run backtest."""
    data_path = _get_bbm3_data_path()

    if not data_path:
        return False, (
            "BBM III data not available. "
            "Download from Underdog Network best-ball-research."
        )

    # Check file size
    try:
        size_mb = data_path.stat().st_size / (1024 * 1024)
        if size_mb < 1:
            return False, f"Data file suspiciously small ({size_mb:.1f} MB)"
    except OSError:
        return False, "Cannot read data file"

    return True, f"Ready: {data_path} ({size_mb:.1f} MB)"
