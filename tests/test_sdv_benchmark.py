import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.pipeline import sdv_benchmark


def test_critical_column_coverage_complete_frame():
    frame = pd.DataFrame({column: [1] for column in sdv_benchmark.STAGE2_CRITICAL_COLUMNS})

    coverage = sdv_benchmark.critical_column_coverage(frame)

    assert all(coverage.values())
    assert sdv_benchmark.coverage_pct(frame) == 100.0


def test_coverage_pct_partial_frame():
    present = sdv_benchmark.STAGE2_CRITICAL_COLUMNS[:11]
    frame = pd.DataFrame({column: [1] for column in present})

    coverage = sdv_benchmark.critical_column_coverage(frame)

    assert sum(coverage.values()) == 11
    assert sdv_benchmark.coverage_pct(frame) == round(
        (11 / len(sdv_benchmark.STAGE2_CRITICAL_COLUMNS)) * 100,
        2,
    )


def test_benchmark_pbp_fetch_mocked(monkeypatch: pytest.MonkeyPatch):
    columns = sdv_benchmark.STAGE2_CRITICAL_COLUMNS
    nflreadpy_frame = pd.DataFrame(
        [
            {**{column: 1 for column in columns}, "week": 1},
            {**{column: 1 for column in columns}, "week": 2},
        ]
    )
    sdv_frame = pd.DataFrame(
        [
            {**{column: 1 for column in columns[:-1]}, "week": 1},
            {**{column: 1 for column in columns[:-1]}, "week": 2},
        ]
    )

    monkeypatch.setitem(
        sys.modules,
        "nflreadpy",
        SimpleNamespace(load_pbp=lambda seasons: nflreadpy_frame),
    )
    monkeypatch.setitem(
        sys.modules,
        "sportsdataverse.nfl",
        SimpleNamespace(
            load_nfl_pbp=lambda *, seasons, return_as_pandas: sdv_frame,
        ),
    )

    result = sdv_benchmark.benchmark_pbp_fetch(2025, week=1)

    assert result["season"] == 2025
    assert result["week"] == 1
    assert result["providers"]["nflreadpy"]["rows"] == 1
    assert result["providers"]["nflreadpy"]["coverage_pct"] == 100.0
    assert result["providers"]["sportsdataverse"]["rows"] == 1
    assert result["providers"]["sportsdataverse"]["coverage_pct"] < 100.0
