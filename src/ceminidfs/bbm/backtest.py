"""BBM III replay harness for backtesting recommender performance.

Stub implementation - full BBM III replay requires data download
from Underdog Network best-ball-research repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path


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


def run_backtest(sample: int = 100) -> BacktestResult:
    """Run backtest against BBM III historical pick data.

    **STUB IMPLEMENTATION** - Requires BBM III data download to use fully.

    Data source: https://underdognetwork.com/football/best-ball-research/
                 best-ball-mania-iii-downloadable-pick-by-pick-data

    Reference: https://github.com/fantasydatapros/best-ball-data-bowl

    Args:
        sample: Number of draft rooms to replay (default 100)

    Returns:
        BacktestResult with metrics or message about data requirements
    """
    # Check for BBM III data
    data_path = _get_bbm3_data_path()

    if not data_path:
        return BacktestResult(
            success=False,
            metrics=None,
            message=(
                "BBM III data not found. To run backtest:\n"
                "1. Download BBM III pick-by-pick data from:\n"
                "   https://underdognetwork.com/football/best-ball-research/\n"
                "   best-ball-mania-iii-downloadable-pick-by-pick-data\n"
                "2. Place in data/bbm/bbm3_historical/ directory\n"
                "3. Re-run: ceminidfs bbm backtest --sample 100"
            ),
            details={
                "required_data": "BBM III pick-by-pick CSV",
                "expected_location": "data/bbm/bbm3_historical/",
                "sample_requested": sample,
            }
        )

    # Full implementation would:
    # 1. Load BBM III pick data
    # 2. For each draft room, replay each pick:
    #    - Run recommender with historical board state
    #    - Compare recommendation to actual pick ADP
    #    - Track structural rule pass rate
    #    - Measure latency
    # 3. Aggregate metrics

    # Stub: return simulated metrics
    return _run_stub_backtest(sample)


def _get_bbm3_data_path() -> Optional[Path]:
    """Check for BBM III data file in expected locations."""
    search_paths = [
        Path("data/bbm/bbm3_historical/bbm3_picks.csv"),
        Path("data/bbm/bbm3_historical/bbm3_pick_data.csv"),
        Path("data/bbm/bbm3_historical/pick_by_pick.csv"),
    ]

    for path in search_paths:
        if path.exists():
            return path

    return None


def _run_stub_backtest(sample: int) -> BacktestResult:
    """Run stub backtest with simulated metrics."""
    # Simulated metrics for development/testing
    simulated_metrics = BacktestMetrics(
        sample_size=sample,
        structural_pass_rate=0.87,  # 87% of picks pass structural rules
        median_clv_delta=2.3,     # Median CLV delta of +2.3 picks
        latency_p99_ms=156.0,     # P99 latency 156ms (target <200ms)
        picks_evaluated=sample * 18 * 12,  # sample drafts × rounds × teams
        picks_matched_adp=int(sample * 18 * 12 * 0.73),  # 73% match ADP within 1 round
        mean_absolute_error_vs_adp=1.8,
        recommendations_made=sample * 18 * 12 * 3,  # 3 recommendations per pick
        warnings_generated=int(sample * 18 * 12 * 0.15),  # 15% have warnings
    )

    return BacktestResult(
        success=True,
        metrics=simulated_metrics,
        message=(
            f"Stub backtest completed for {sample} draft rooms.\n"
            "Note: This is simulated data. For real backtesting,\n"
            "download BBM III data per instructions above."
        ),
        details={
            "mode": "stub",
            "simulated": True,
            "metrics_source": "placeholder_values_for_development",
        }
    )


def run_single_draft_replay(
    draft_picks: List[Dict[str, Any]],
    available_players_pool: List[Any],  # List[Player] - avoid circular import
    archetype: str,
) -> Dict[str, Any]:
    """Replay a single draft room and evaluate recommender choices.

    **STUB** - Full implementation pending BBM III data.

    Args:
        draft_picks: List of pick dicts with player_id, pick_num, etc.
        available_players_pool: Pool of available players during draft
        archetype: Archetype code used for this draft

    Returns:
        Dict with replay analysis results
    """
    results = {
        "draft_id": draft_picks[0].get("draft_id", "unknown") if draft_picks else "unknown",
        "total_picks": len(draft_picks),
        "recommendations_vs_actual": [],
        "clv_analysis": [],
        "structural_violations": [],
        "latency_ms": [],
    }

    # Stub: would iterate picks and compare recommender to actual

    return results


def calculate_pass_rate(violations_by_pick: List[List[str]]) -> float:
    """Calculate structural rule pass rate from violation lists."""
    if not violations_by_pick:
        return 0.0

    critical_violations = [
        v for v in violations_by_pick
        if any("HARD_LIMIT" in x or "OVERFLOW" in x or "CRITICAL" in x for x in v)
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
