"""Tests for the NGS receiving-elasticity layer (Finding 1).

No NGS frame exists in the cache, so the applied path is exercised with an
in-memory frame. These tests pin the two contracts the audit flagged: the
feature names ``build_ngs_features`` emits must equal the names the model
consumes, and a missing cache must surface an explicit skip marker.
"""

import statistics
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.ngs_elasticity import (
    ALL_FEATURES,
    DEFENSE_FEATURES,
    NGS_APPLIED_MARKER,
    NGS_SKIP_MARKER,
    ZSCORE_FEATURES,
    _defense_lookup,
    apply_receiving_elasticity,
    build_ngs_features,
    ngs_elasticity_diagnostics,
    ngs_marker,
)
from ceminidfs.models import ngs_elasticity


def _receiving() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_id": ["p1", "p1", "p1", "p2", "p2", "p2"],
            "week": [1, 2, 3, 1, 2, 3],
            "opponent": ["KC", "BUF", "DAL", "KC", "BUF", "DAL"],
            "avg_separation": [2.0, 2.5, 3.0, 1.5, 2.0, 2.5],
            "avg_cushion": [5.0, 5.5, 6.0, 6.0, 6.5, 7.0],
            "percent_share_of_intended_air_yards": [0.2, 0.25, 0.3, 0.15, 0.2, 0.25],
            "yprr": [2.0, 2.1, 2.2, 1.9, 2.0, 2.1],
        }
    )


def _defenses() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "opponent": ["KC", "BUF", "DAL"],
            "completion_percentage_above_expectation_allowed": [0.10, 0.02, -0.06],
            "yards_per_attempt_allowed": [8.0, 7.0, 6.0],
        }
    )


def test_emitted_feature_names_match_consumed_names():
    """The columns build_ngs_features emits are exactly the names the model consumes."""

    features = build_ngs_features(_receiving(), _defenses(), window=2)

    assert set(ZSCORE_FEATURES).issubset(features.columns)
    assert ZSCORE_FEATURES == tuple(f"z_{name}" for name in ALL_FEATURES)


def test_defense_lookup_keys_hold_real_zscores():
    """The z_ defense keys carry standardized values, not raw magnitudes."""

    lookup = _defense_lookup(_defenses())
    column = f"z_{DEFENSE_FEATURES[1]}"
    values = [lookup[team][column] for team in ("KC", "BUF", "DAL")]

    assert values[0] > 0.0 > values[-1]
    assert statistics.fmean(values) == pytest.approx(0.0)
    assert statistics.pstdev(values) == pytest.approx(1.0)


def test_ngs_marker_reports_skip_when_cache_absent(tmp_path: Path):
    """No NGS cache must be an explicit skip, never a silent no-op."""

    assert ngs_marker(2025, cache_dir=tmp_path) == NGS_SKIP_MARKER


def test_apply_receiving_elasticity_returns_skip_marker_without_cache(tmp_path: Path):
    stats = pd.DataFrame(
        {"player_id": ["p1"], "position": ["WR"], "rec": [5.0], "rec_yds": [60.0]}
    )

    out, marker = apply_receiving_elasticity(stats, season=2025, cache_dir=tmp_path)

    assert marker == NGS_SKIP_MARKER
    pd.testing.assert_frame_equal(out, stats)


def test_apply_receiving_elasticity_adjusts_when_frame_present():
    """With an NGS frame present the multiplier moves receiving stats."""

    stats = pd.DataFrame(
        {
            "player_id": ["p1", "p2"],
            "position": ["WR", "TE"],
            "rec": [5.0, 6.0],
            "rec_yds": [60.0, 70.0],
        }
    )

    out, marker = apply_receiving_elasticity(stats, season=2025, receiving=_receiving())

    assert marker == NGS_APPLIED_MARKER
    assert out.loc[0, "rec_yds"] > stats.loc[0, "rec_yds"]
    assert out.loc[0, "rec"] > stats.loc[0, "rec"]


def test_apply_receiving_elasticity_fetches_when_cache_absent(monkeypatch: pytest.MonkeyPatch):
    """Absent frames are fetched, then applied, instead of silently skipped."""

    stats = pd.DataFrame(
        {"player_id": ["p1"], "position": ["WR"], "rec": [5.0], "rec_yds": [60.0]}
    )
    fetched: list[int] = []
    monkeypatch.setattr(
        ngs_elasticity, "load_ngs_frames", lambda season, cache_dir=None: (None, None)
    )

    def fake_fetch(season: int):
        fetched.append(season)
        return _receiving(), None

    monkeypatch.setattr(ngs_elasticity, "_fetch_ngs_frames", fake_fetch)

    out, marker = apply_receiving_elasticity(stats, season=2025)

    assert fetched == [2025]
    assert marker == NGS_APPLIED_MARKER
    assert out.loc[0, "rec_yds"] > stats.loc[0, "rec_yds"]


def test_explicit_cache_dir_does_not_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A caller-managed cache dir pins the function offline: absence means skip."""

    stats = pd.DataFrame(
        {"player_id": ["p1"], "position": ["WR"], "rec": [5.0], "rec_yds": [60.0]}
    )
    fetched: list[int] = []
    monkeypatch.setattr(
        ngs_elasticity, "_fetch_ngs_frames", lambda season: fetched.append(season) or (None, None)
    )

    out, marker = apply_receiving_elasticity(stats, season=2025, cache_dir=tmp_path)

    assert fetched == []
    assert marker == NGS_SKIP_MARKER
    pd.testing.assert_frame_equal(out, stats)


def test_ngs_elasticity_diagnostics_reports_delta_and_interaction(tmp_path: Path):
    _receiving().to_parquet(tmp_path / "ngs_receiving_2025.parquet", index=False)

    diagnostics = ngs_elasticity_diagnostics(2025, cache_dir=tmp_path)

    assert diagnostics["available"] is True
    assert diagnostics["n_receiving_rows"] == len(_receiving())
    assert diagnostics["interaction"] > 0.0
    assert diagnostics["delta_max"] >= diagnostics["delta_min"]


def test_receiving_target_is_centered_fractional_deviation():
    """The target is the fractional deviation from the sample mean, so it is centered."""

    receiving = pd.DataFrame({"player_id": ["a", "b", "c"], "yprr": [1.0, 2.0, 3.0]})

    target = ngs_elasticity._receiving_target(receiving)

    assert target is not None
    assert statistics.fmean(target) == pytest.approx(0.0)
    # The receiver exactly at the sample mean maps to a zero deviation...
    assert target.iloc[1] == pytest.approx(0.0)
    # ...while below/above-mean receivers straddle zero.
    assert target.iloc[0] < 0.0 < target.iloc[2]


def test_receiving_target_guards_degenerate_mean_and_zero_routes():
    """A zero sample mean must not divide, and zero routes must not inflate the YPRR."""

    zero_mean = pd.DataFrame({"player_id": ["a", "b"], "yprr": [0.0, 0.0]})
    assert ngs_elasticity._receiving_target(zero_mean) is None

    receiving = pd.DataFrame(
        {
            "player_id": ["a", "b", "c"],
            "yards": [100.0, 200.0, 300.0],
            "routes": [0.0, 100.0, 100.0],
        }
    )
    target = ngs_elasticity._receiving_target(receiving)

    assert target is not None
    assert not np.isfinite(target.iloc[0])  # no routes -> NaN, never a huge finite value
    assert np.isfinite(target.iloc[1:]).all()


def test_fitted_deltas_are_centered_and_not_saturated():
    """A mean-YPRR receiver sits near zero and the deltas are not a flat bound."""

    receiving = _receiving()
    features = build_ngs_features(receiving, _defenses(), window=2)
    target = ngs_elasticity._receiving_target(receiving)
    assert target is not None

    model = ngs_elasticity.fit_ngs_elasticity(features, target.to_numpy(dtype=float))
    deltas = np.asarray(model.predict(features), dtype=float)

    # The fitted offset is zero, not the raw YPRR mean that saturated every row.
    assert model.target_mean == pytest.approx(0.0, abs=1e-9)
    assert deltas.std() > 0.0
    assert not np.allclose(deltas, model.bound)
    assert np.max(np.abs(deltas)) < model.bound


def test_ngs_elasticity_diagnostics_report_spread_and_bound_shares(tmp_path: Path):
    """The diagnostics must expose an sd and per-bound shares, not a flat bound."""

    _receiving().to_parquet(tmp_path / "ngs_receiving_2025.parquet", index=False)

    diagnostics = ngs_elasticity_diagnostics(2025, cache_dir=tmp_path)

    assert diagnostics["delta_sd"] > 0.0
    assert set(diagnostics["share_at_bound"]) == {"lower", "upper"}
    assert diagnostics["share_at_bound"]["lower"] < 1.0
    assert diagnostics["share_at_bound"]["upper"] < 1.0
    assert not (
        diagnostics["delta_min"] == diagnostics["delta_max"] == diagnostics["delta_abs_mean"]
    )
