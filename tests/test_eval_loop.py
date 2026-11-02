"""Noise band, chronological split, and the keep gate."""

from datetime import date

import pytest

from ceminidfs.eval_loop.noise_band import (
    NoiseBand,
    campaign_slate_count,
    keep_or_revert,
    loop_block_reasons,
    noise_band,
    slates_required,
    stdev_bounds,
)
from ceminidfs.eval_loop.objective import (
    ALLOWED_PARAMETERS,
    BLOCK_COUNT,
    CODE_PATH,
    CONFIDENCE,
    FORBIDDEN_PATHS,
    LOWER_IS_BETTER,
    METRIC_KEY,
    METRIC_NAME,
    MINIMUM_EFFECT,
)
from ceminidfs.eval_loop.observed_mae import OBSERVED_SLATE_MAE
from ceminidfs.eval_loop.walk_forward import walk_forward


def _maes() -> list[float]:
    return [row.mae for row in OBSERVED_SLATE_MAE]


def test_objective_constants_stay_fixed():
    assert METRIC_NAME == "projection_mae"
    assert METRIC_KEY == "mae"
    assert LOWER_IS_BETTER is True
    assert CODE_PATH == "ceminidfs.pipeline.metrics.accuracy_metrics"
    assert MINIMUM_EFFECT == 0.10
    assert CONFIDENCE == 0.95
    assert BLOCK_COUNT == 2
    assert ALLOWED_PARAMETERS == ()
    assert "src/ceminidfs/eval_loop/objective.py" in FORBIDDEN_PATHS
    assert "src/ceminidfs/pipeline/metrics.py" in FORBIDDEN_PATHS


def test_observed_slate_dates_are_chronological():
    dates = [row.slate_date for row in OBSERVED_SLATE_MAE]
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates)) == 13
    assert dates[0] == date(2025, 10, 5)
    assert dates[-1] == date(2025, 12, 28)


def test_projection_mae_noise_band_from_2025_weeks():
    band = noise_band(_maes(), minimum_effect=MINIMUM_EFFECT, confidence=CONFIDENCE)

    assert band.n == 13
    assert band.mean == pytest.approx(4.759633604973616)
    assert band.stdev == pytest.approx(0.20962390612124346)
    assert band.half_width == pytest.approx(0.1266744586798723)
    assert band.n_required == 20
    assert band.half_width > band.minimum_effect
    assert campaign_slate_count(band.n_required, BLOCK_COUNT) == 40


def test_stdev_interval_shows_the_spread_is_uncertain():
    low, high = stdev_bounds(_maes(), confidence=CONFIDENCE)
    assert low == pytest.approx(0.1503183653132968)
    assert high == pytest.approx(0.34603354781979334)
    assert slates_required(low, MINIMUM_EFFECT, confidence=CONFIDENCE) == 12
    assert slates_required(high, MINIMUM_EFFECT, confidence=CONFIDENCE) == 49


def test_short_history_blocks_even_a_large_mae_drop():
    band = noise_band(_maes(), minimum_effect=MINIMUM_EFFECT, confidence=CONFIDENCE)
    reasons = loop_block_reasons(band, block_count=BLOCK_COUNT)
    result = keep_or_revert(
        4.76,
        4.00,
        band,
        lower_is_better=LOWER_IS_BETTER,
        block_count=BLOCK_COUNT,
    )

    assert "the history is shorter than one noise-band block" in reasons
    assert "the history is shorter than the train block plus the holdout" in reasons
    assert result.action == "blocked"
    assert result.reasons == reasons


def test_keep_only_when_the_gain_clears_the_half_width():
    band = NoiseBand(
        n=40,
        mean=4.0,
        stdev=0.2,
        half_width=0.05,
        minimum_effect=0.10,
        n_required=20,
        confidence=0.95,
    )

    kept = keep_or_revert(4.0, 3.94, band, lower_is_better=True, block_count=2)
    inside = keep_or_revert(4.0, 3.96, band, lower_is_better=True, block_count=2)
    worse = keep_or_revert(4.0, 4.20, band, lower_is_better=True, block_count=2)
    higher = keep_or_revert(0.40, 0.50, band, lower_is_better=False, block_count=2)

    assert kept.action == "keep"
    assert inside.action == "revert"
    assert worse.action == "revert"
    assert higher.action == "keep"


def test_one_precise_block_still_blocks_without_a_holdout():
    band = NoiseBand(
        n=25,
        mean=4.0,
        stdev=0.2,
        half_width=0.08,
        minimum_effect=0.10,
        n_required=20,
        confidence=0.95,
    )
    reasons = loop_block_reasons(band, block_count=2)
    assert reasons == ("the history is shorter than the train block plus the holdout",)


def test_noise_band_rejects_a_single_slate():
    with pytest.raises(ValueError, match="need at least two slates"):
        noise_band([1.0], minimum_effect=0.10)


def test_walk_forward_expands_in_date_order_without_shuffle():
    rows = list(OBSERVED_SLATE_MAE)
    shuffled = list(reversed(rows))
    folds = walk_forward(shuffled, n_folds=3, train_ratio=0.5)

    assert len(folds) == 3
    covered: list[int] = []
    previous_train: tuple[int, ...] = ()
    for train_idx, test_idx in folds:
        assert set(train_idx).isdisjoint(test_idx)
        assert previous_train == () or set(previous_train) < set(train_idx)
        previous_train = train_idx
        train_dates = [shuffled[index].slate_date for index in train_idx]
        test_dates = [shuffled[index].slate_date for index in test_idx]
        assert train_dates == sorted(train_dates)
        assert test_dates == sorted(test_dates)
        assert max(train_dates) < min(test_dates)
        covered.extend(test_idx)

    assert len(covered) == len(set(covered))
    assert walk_forward(shuffled, 3, 0.5) == folds


def test_walk_forward_gives_early_folds_the_remainder():
    slates = [date(2025, 10, day) for day in range(5, 15)]
    folds = walk_forward(slates, n_folds=3, train_ratio=0.5)

    assert [len(train) for train, _test in folds] == [5, 7, 9]
    assert [len(test) for _train, test in folds] == [2, 2, 1]


def test_walk_forward_rejects_a_short_remainder():
    slates = [date(2025, 10, 5 + offset) for offset in range(5)]
    with pytest.raises(ValueError, match="not enough slates for the test folds"):
        walk_forward(slates, n_folds=4, train_ratio=0.5)


def test_walk_forward_rejects_a_missing_date():
    with pytest.raises(ValueError, match="slate has no date"):
        walk_forward([{"name": "no date"}, {"name": "still none"}], n_folds=1, train_ratio=0.5)


def test_same_day_slates_keep_input_order():
    slates = [
        {"date": date(2025, 10, 12), "name": "second"},
        {"date": date(2025, 10, 5), "name": "first"},
        {"date": date(2025, 10, 12), "name": "third"},
    ]
    folds = walk_forward(slates, n_folds=1, train_ratio=0.34)
    train_idx, test_idx = folds[0]

    assert train_idx == (1,)
    assert test_idx == (0, 2)
