"""Tests for salary-controlled permutation gate. No network."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.pipeline.permutation_gate import (
    PERMUTATION_GATE_DRAWS,
    band_report,
    partial_spearman,
    salary_controlled_p,
)


def test_partial_spearman_salary_copy():
    """When model == salary, partial correlation should be near zero."""
    np.random.seed(42)
    salary = np.random.uniform(5000, 10000, 100)
    # Model is a copy of salary plus small noise
    projection = salary + np.random.normal(0, 10, 100)
    # Actual is salary plus different noise
    actual = salary + np.random.normal(0, 50, 100)

    partial = partial_spearman(projection, salary, actual)
    p_val = salary_controlled_p(projection, salary, actual, draws=200, seed=123)

    assert abs(partial) < 0.3, f"Partial spearman should be near zero, got {partial}"
    assert p_val > 0.1, f"P-value should be large when model adds no info beyond salary, got {p_val}"


def test_partial_spearman_actual_copy():
    """When model == actual, partial correlation should be near one."""
    np.random.seed(42)
    salary = np.random.uniform(5000, 10000, 100)
    actual = salary + np.random.normal(0, 50, 100)
    # Model is a copy of actual
    projection = actual.copy()

    partial = partial_spearman(projection, salary, actual)
    p_val = salary_controlled_p(projection, salary, actual, draws=200, seed=123)

    assert partial > 0.8, f"Partial spearman should be near one, got {partial}"
    assert p_val < 0.05, f"P-value should be small when model matches actual, got {p_val}"


def test_band_report_four_rows():
    """band_report returns four rows with correct n on default slate."""
    # Create a synthetic frame matching the default slate structure
    n = 550
    np.random.seed(42)
    salary = np.random.uniform(4500, 10000, n)
    # Create projection with some skill over salary
    projection = 0.6 * salary + np.random.normal(0, 300, n)
    actual = 0.5 * salary + np.random.normal(0, 400, n)

    frame = pd.DataFrame(
        {"fd_projection": projection, "fd_salary": salary, "fd_actual": actual}
    )

    results = band_report(frame, draws=200, seed=123)

    assert len(results) == 4, f"Expected 4 bands, got {len(results)}"
    band_names = [r.band for r in results]
    assert band_names == ["all", "salary>=6000", "salary>=7000", "salary<6000"]

    # Check n values are reasonable
    all_result = next(r for r in results if r.band == "all")
    assert all_result.n == n

    # Check that bands with n < 20 are marked NO_EVIDENCE (none should be here)
    for r in results:
        if r.n < 20:
            assert r.model_spearman is None
            assert r.cleared_null is None


def test_partial_spearman_matches_metrics():
    """partial_spearman with zero salary effect should match spearman_correlation."""
    from ceminidfs.pipeline.metrics import spearman_correlation

    np.random.seed(42)
    projection = np.random.uniform(5, 30, 50)
    actual = projection + np.random.normal(0, 5, 50)
    salary = np.random.uniform(5000, 10000, 50)  # Independent salary

    # When salary is independent, partial should be close to regular spearman
    regular = spearman_correlation(projection, actual)
    partial = partial_spearman(projection, salary, actual)

    # They won't be exactly equal but should be close
    assert abs(regular - partial) < 0.2


def test_constant_salary_handled():
    """When salary is constant, partial should fall back gracefully."""
    projection = [10, 15, 20, 25, 30]
    salary = [6000, 6000, 6000, 6000, 6000]
    actual = [12, 14, 22, 24, 28]

    partial = partial_spearman(projection, salary, actual)
    # With constant salary, residualization is not well-defined; should return 0
    assert partial == 0.0


def test_permutation_gate_draws_constant():
    assert PERMUTATION_GATE_DRAWS == 2000


if __name__ == "__main__":
    test_partial_spearman_salary_copy()
    test_partial_spearman_actual_copy()
    test_band_report_four_rows()
    test_partial_spearman_matches_metrics()
    test_constant_salary_handled()
    test_permutation_gate_draws_constant()
    print("All tests passed")