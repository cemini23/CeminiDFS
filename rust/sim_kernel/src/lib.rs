//! Lineup total, linear quantile, and leverage scoring.
//!
//! The matrix layout is C-contiguous `(n_players, n_iterations)`.
//! Each lineup total adds selected rows in index order, one iteration at a time.

use numpy::PyReadonlyArray2;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Numpy `quantile(..., method="linear")`. This wrapper copies, then selects.
pub fn quantile_linear(values: &[f64], q: f64) -> f64 {
    let mut owned = values.to_vec();
    quantile_linear_in_place(&mut owned, q)
}

/// Same quantile as [`quantile_linear`], on a buffer this function may reorder.
pub fn quantile_linear_in_place(values: &mut [f64], q: f64) -> f64 {
    if values.is_empty() || !q.is_finite() || !(0.0..=1.0).contains(&q) {
        return f64::NAN;
    }
    if values.iter().any(|value| value.is_nan()) {
        return f64::NAN;
    }
    let n = values.len();
    let h = q * ((n as f64) - 1.0);
    let lo = (h.floor() as usize).min(n - 1);
    let hi = (h.ceil() as usize).min(n - 1);
    values.select_nth_unstable_by(lo, f64::total_cmp);
    // Save `low` first. The second select reorders every index below `hi`.
    let low = values[lo];
    let high = if hi == lo {
        low
    } else {
        values.select_nth_unstable_by(hi, f64::total_cmp);
        values[hi]
    };
    let gamma = h - (lo as f64);
    low + (high - low) * gamma
}

fn sum_group(matrix: &[f64], n_iter: usize, indexes: &[usize], out: &mut [f64]) {
    out.fill(0.0);
    for &index in indexes {
        let row = &matrix[index * n_iter..(index + 1) * n_iter];
        for (slot, value) in out.iter_mut().zip(row.iter()) {
            *slot += *value;
        }
    }
}

fn lineup_totals_owned(
    matrix: &[f64],
    n_iter: usize,
    groups: &[Vec<usize>],
) -> (Vec<f64>, Vec<usize>) {
    let n_groups = groups.len();
    let mut flat = vec![0.0; n_groups.saturating_mul(n_iter)];
    let lengths = vec![n_iter; n_groups];
    for (group_index, group) in groups.iter().enumerate() {
        let start = group_index * n_iter;
        sum_group(
            matrix,
            n_iter,
            group,
            &mut flat[start..start + n_iter],
        );
    }
    (flat, lengths)
}

fn leverage_scores_owned(
    matrix: &[f64],
    n_iter: usize,
    groups: &[Vec<usize>],
    ownership_fractions: &[f64],
    top_fraction: f64,
    exponent: f64,
) -> (Vec<f64>, f64) {
    if groups.is_empty() {
        return (Vec::new(), 0.0);
    }
    let (mut flat, lengths) = lineup_totals_owned(matrix, n_iter, groups);
    // Selection reorders `flat` across lineup groups. `grouped` keeps each lineup.
    let grouped = flat.clone();
    let threshold = quantile_linear_in_place(&mut flat, 1.0 - top_fraction);
    let mut scores = Vec::with_capacity(groups.len());
    let mut offset = 0usize;
    for (length, ownership) in lengths.iter().zip(ownership_fractions.iter()) {
        let totals = &grouped[offset..offset + *length];
        offset += *length;
        let mut hits = 0.0f64;
        for value in totals {
            if *value >= threshold {
                hits += 1.0;
            }
        }
        let tail = if totals.is_empty() {
            f64::NAN
        } else {
            hits / (totals.len() as f64)
        };
        scores.push(tail / ownership.powf(exponent));
    }
    (scores, threshold)
}

fn checked_groups(groups: &[Vec<usize>], n_players: usize) -> PyResult<()> {
    for group in groups {
        for &index in group {
            if index >= n_players {
                return Err(PyValueError::new_err(
                    "player index is outside the matrix",
                ));
            }
        }
    }
    Ok(())
}

fn with_matrix_slice<T>(
    matrix: &PyReadonlyArray2<'_, f64>,
    body: impl FnOnce(&[f64], usize, usize) -> PyResult<T>,
) -> PyResult<T> {
    let view = matrix.as_array();
    if !view.is_standard_layout() {
        return Err(PyValueError::new_err(
            "matrix must be a C-contiguous float64 array",
        ));
    }
    let slice = view.as_slice().ok_or_else(|| {
        PyValueError::new_err("matrix must be a C-contiguous float64 array")
    })?;
    let n_players = view.shape()[0];
    let n_iter = view.shape()[1];
    body(slice, n_players, n_iter)
}

#[pyfunction]
fn lineup_totals(
    matrix: PyReadonlyArray2<'_, f64>,
    groups: Vec<Vec<usize>>,
) -> PyResult<(Vec<f64>, Vec<usize>)> {
    with_matrix_slice(&matrix, |data, n_players, n_iter| {
        checked_groups(&groups, n_players)?;
        Ok(lineup_totals_owned(data, n_iter, &groups))
    })
}

#[pyfunction]
#[pyo3(name = "quantile_linear")]
fn quantile_linear_py(py: Python<'_>, values: Vec<f64>, q: f64) -> f64 {
    py.detach(move || quantile_linear(&values, q))
}

#[pyfunction]
fn leverage_scores(
    matrix: PyReadonlyArray2<'_, f64>,
    groups: Vec<Vec<usize>>,
    ownership_fractions: Vec<f64>,
    top_fraction: f64,
    exponent: f64,
) -> PyResult<(Vec<f64>, f64)> {
    if groups.is_empty() {
        return Ok((Vec::new(), 0.0));
    }
    if ownership_fractions.len() != groups.len() {
        return Err(PyValueError::new_err(
            "ownership_fractions length must match groups",
        ));
    }
    with_matrix_slice(&matrix, |data, n_players, n_iter| {
        checked_groups(&groups, n_players)?;
        Ok(leverage_scores_owned(
            data,
            n_iter,
            &groups,
            &ownership_fractions,
            top_fraction,
            exponent,
        ))
    })
}

#[pymodule]
fn _sim_kernel_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(lineup_totals, m)?)?;
    m.add_function(wrap_pyfunction!(quantile_linear_py, m)?)?;
    m.add_function(wrap_pyfunction!(leverage_scores, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{quantile_linear, quantile_linear_in_place};

    #[test]
    fn median_of_four_is_two_point_five() {
        let value = quantile_linear(&[1.0, 2.0, 3.0, 4.0], 0.5);
        assert!((value - 2.5).abs() < 1e-12);
    }

    #[test]
    fn quantile_zero_is_minimum() {
        assert_eq!(quantile_linear(&[1.0, 2.0, 3.0, 4.0], 0.0), 1.0);
    }

    #[test]
    fn quantile_one_is_maximum() {
        assert_eq!(quantile_linear(&[1.0, 2.0, 3.0, 4.0], 1.0), 4.0);
    }

    #[test]
    fn nan_input_returns_nan() {
        assert!(quantile_linear(&[1.0, f64::NAN, 3.0], 0.5).is_nan());
    }

    #[test]
    fn empty_input_returns_nan() {
        assert!(quantile_linear(&[], 0.5).is_nan());
    }

    #[test]
    fn unsorted_input_matches_sorted_median() {
        let value = quantile_linear(&[4.0, 1.0, 3.0, 2.0], 0.5);
        assert!((value - 2.5).abs() < 1e-12);
    }

    #[test]
    fn quantile_of_one_element_slice() {
        assert_eq!(quantile_linear(&[7.0], 0.0), 7.0);
        assert_eq!(quantile_linear(&[7.0], 0.5), 7.0);
        assert_eq!(quantile_linear(&[7.0], 1.0), 7.0);
    }

    #[test]
    fn quantile_of_two_element_slice_at_half() {
        let value = quantile_linear(&[10.0, 20.0], 0.5);
        assert!((value - 15.0).abs() < 1e-12);
        let reversed = quantile_linear(&[20.0, 10.0], 0.5);
        assert!((reversed - 15.0).abs() < 1e-12);
    }

    #[test]
    fn in_place_matches_copying_wrapper_on_pseudorandom_buffer() {
        let mut state: u64 = 0x5EED_1234_ABCD_7781;
        let mut values = Vec::with_capacity(1000);
        for _ in 0..1000 {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            let unit = ((state >> 11) as f64) / ((1u64 << 53) as f64);
            values.push(unit);
        }
        for q in [0.0, 0.01, 0.5, 0.99, 1.0] {
            let expected = quantile_linear(&values, q);
            let mut buffer = values.clone();
            let actual = quantile_linear_in_place(&mut buffer, q);
            assert_eq!(actual.to_bits(), expected.to_bits());
        }
    }
}
