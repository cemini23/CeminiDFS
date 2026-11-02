"""Chronological expanding-window splits for slate sequences.

Re-implemented from the walk-forward description. No upstream source file
is copied. The function does not shuffle.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime


def walk_forward(
    slates: Sequence[object],
    n_folds: int,
    train_ratio: float,
) -> list[tuple[tuple[int, ...], tuple[int, ...]]]:
    """Return expanding ``(train_idx, test_idx)`` pairs in date order.

    Indices point into ``slates``. The first train length is
    ``floor(n * train_ratio)``. The later slates form ``n_folds`` contiguous
    test blocks. Earlier blocks take a remainder slate. Fold k trains on every
    slate dated before its test block. A slate is never on both sides of one fold.
    """

    if isinstance(n_folds, bool) or not isinstance(n_folds, int) or n_folds < 1:
        raise ValueError("n_folds must be >= 1")
    if isinstance(train_ratio, bool) or not isinstance(train_ratio, (int, float)):
        raise TypeError("train_ratio must be a real number")
    if not 0.0 < float(train_ratio) < 1.0:
        raise ValueError("train_ratio must be between 0 and 1")
    n = len(slates)
    if n < 2:
        raise ValueError("need at least two slates")

    order = tuple(sorted(range(n), key=lambda index: (_slate_date(slates[index]), index)))
    n_train0 = int(math.floor(n * float(train_ratio)))
    if n_train0 < 1:
        raise ValueError("the first train block is empty")
    sizes = _test_sizes(n - n_train0, n_folds)

    folds: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    start = n_train0
    for size in sizes:
        train_idx = tuple(order[index] for index in range(start))
        test_idx = tuple(order[index] for index in range(start, start + size))
        folds.append((train_idx, test_idx))
        start += size
    return folds


def _test_sizes(n_test: int, n_folds: int) -> list[int]:
    if n_test < n_folds:
        raise ValueError("not enough slates for the test folds")
    base, extra = divmod(n_test, n_folds)
    return [base + (1 if fold < extra else 0) for fold in range(n_folds)]


def _slate_date(slate: object) -> date:
    if isinstance(slate, datetime):
        return slate.date()
    if isinstance(slate, date):
        return slate
    if isinstance(slate, str):
        try:
            return date.fromisoformat(slate)
        except ValueError:
            raise ValueError("slate has no date") from None
    if isinstance(slate, Mapping):
        for key in ("date", "slate_date"):
            if key in slate and slate[key] not in (None, ""):
                return _slate_date(slate[key])
    value = getattr(slate, "slate_date", None)
    if value is None:
        value = getattr(slate, "date", None)
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError("slate has no date")
