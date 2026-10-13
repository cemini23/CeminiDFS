"""Permutation p-value on fixtures. No network."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.pipeline.permutation_test import permutation_p_value


def test_equal_projection_has_smaller_p_value_than_independent():
    projection = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    equal_actual = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
    independent_actual = [6, 1, 8, 3, 11, 2, 10, 5, 12, 4, 9, 7]

    p_equal = permutation_p_value(projection, equal_actual)
    p_independent = permutation_p_value(projection, independent_actual)

    assert 0 < p_equal < 1
    assert 0 < p_independent <= 1
    assert p_equal < p_independent
