"""Human-owned objective for the projection campaign.

A tuning run must not edit this file. The metric formula lives in
``ceminidfs.pipeline.metrics.accuracy_metrics``. This file names that metric
and the keep threshold.
"""

from __future__ import annotations

# Slate MAE from accuracy_metrics. Lower is better.
METRIC_NAME = "projection_mae"
METRIC_KEY = "mae"
LOWER_IS_BETTER = True
CODE_PATH = "ceminidfs.pipeline.metrics.accuracy_metrics"

# A keep must move slate MAE by more than one tenth of a FanDuel point.
# config/nfl_dfs.yaml sets regression.max_overall_mae to 4.85. The measured
# 2025 week 5-17 mean sits 0.09 below that gate, so a tenth of a point is the
# scale this repo already treats as pass or fail.
MINIMUM_EFFECT = 0.10
CONFIDENCE = 0.95

# One train block and one untouched holdout. Each block needs n_required slates.
BLOCK_COUNT = 2

# This campaign authorizes no parameter edits.
ALLOWED_PARAMETERS: tuple[str, ...] = ()

FORBIDDEN_PATHS = (
    "src/ceminidfs/eval_loop/objective.py",
    "src/ceminidfs/eval_loop/observed_mae.py",
    "src/ceminidfs/pipeline/metrics.py",
    "design-log/2026-11-01-projection-mae.md",
)
