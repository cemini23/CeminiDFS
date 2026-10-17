"""Synthetic holdout gate. A planted signal passes. Noise does not."""

import numpy as np
import pandas as pd

from ceminidfs.situational.backtest import _calibrate_one, _export_gate


def test_planted_signal_passes_and_noise_does_not():
    rng = np.random.default_rng(20261017)
    signal = _panel(rng, planted=True)
    fitted = _calibrate_one(
        signal,
        name="rec_100",
        actual_col="rec_yds",
        threshold=100.0,
        mean_col="rec_yds_per_game",
        features=("signal", "noise"),
        seed=20261017,
        n_boot=80,
        count_model=False,
    )
    assert fitted["export"] is True
    assert "signal" in fitted["kept"]
    assert "noise" not in fitted["kept"]
    assert "baseline" in fitted["coefficients"]
    assert fitted["metrics"]["delta_brier_ci_low"] > 0

    noise = _panel(rng, planted=False)
    quiet = _calibrate_one(
        noise,
        name="rec_100",
        actual_col="rec_yds",
        threshold=100.0,
        mean_col="rec_yds_per_game",
        features=("noise",),
        seed=20261017,
        n_boot=80,
        count_model=False,
    )
    assert quiet["export"] is False


def test_export_gate_follows_the_holdout_rule():
    assert _export_gate(_gate_metrics()) is True
    assert _export_gate(_gate_metrics(delta_brier=0.0)) is False
    assert _export_gate(_gate_metrics(delta_brier=-0.0004)) is False
    assert _export_gate(_gate_metrics(kept=[])) is False
    small = _gate_metrics(
        delta_brier_ci_low=-0.0036,
        n_test=374,
        top_decile_point_lift=1.838,
        model_top_decile=0.459,
        baseline_top_decile=0.324,
        delta_brier_positive_share=0.85,
    )
    assert _export_gate(small) is True
    assert _export_gate({**small, "delta_brier_positive_share": 0.70}) is False
    assert _export_gate({**small, "top_decile_point_lift": 0.39}) is False
    assert _export_gate({**small, "model_top_decile": 0.324}) is False
    large = {**small, "n_test": 3597, "top_decile_point_lift": 0.576}
    assert _export_gate(large) is False


def _gate_metrics(**overrides):
    metrics = {
        "kept": ["signal"],
        "delta_brier": 0.001,
        "delta_brier_ci_low": 0.0002,
        "n_test": 3597,
        "top_decile_point_lift": 0.576,
        "model_top_decile": 0.461,
        "baseline_top_decile": 0.456,
        "delta_brier_positive_share": 0.90,
    }
    metrics.update(overrides)
    return metrics


def _panel(rng: np.random.Generator, *, planted: bool) -> pd.DataFrame:
    rows = []
    for week in range(1, 13):
        for index in range(40):
            signal = 1.0 if index < 20 else 0.0
            noise = float(rng.normal())
            # Means overlap, so the signal is not a copy of the lagged mean.
            # Grinders still tend to have the higher mean.
            if signal == 1.0:
                mean = float(rng.uniform(40.0, 70.0))
            else:
                mean = float(rng.uniform(55.0, 95.0))
            roll = float(rng.random())
            if planted and signal == 1.0 and roll < 0.90:
                yards = 160.0
            elif roll < 0.05:
                yards = 120.0
            else:
                yards = float(rng.uniform(20.0, 60.0))
            rows.append(
                {
                    "season": 2024,
                    "week": week,
                    "player_id": f"p{index}",
                    "position": "WR",
                    "rec_yds": yards,
                    "rec_yds_per_game": mean,
                    "fd_points": yards * 0.1,
                    "signal": signal,
                    "noise": noise,
                }
            )
    return pd.DataFrame(rows)
