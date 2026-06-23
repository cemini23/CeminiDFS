import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data import sportsdataverse_smoke


def test_load_sdv_pbp_sample_mocked(monkeypatch: pytest.MonkeyPatch):
    expected = pd.DataFrame({"season": [2025], "week": [1], "play_id": [42]})

    def load_nfl_pbp(*, seasons: list[int], return_as_pandas: bool):
        assert seasons == [2025]
        assert return_as_pandas is True
        return expected

    monkeypatch.setitem(
        sys.modules,
        "sportsdataverse.nfl",
        SimpleNamespace(load_nfl_pbp=load_nfl_pbp),
    )

    result = sportsdataverse_smoke.load_sdv_pbp_sample(2025)

    assert_frame_equal(result, expected)


def test_smoke_fetch_pbp_success(monkeypatch: pytest.MonkeyPatch):
    frame = pd.DataFrame({"season": [2025, 2025], "week": [1, 1]})
    monkeypatch.setattr(sportsdataverse_smoke, "load_sdv_pbp_sample", lambda season: frame)

    result = sportsdataverse_smoke.smoke_fetch_pbp(2025)

    assert result["rows"] == 2
    assert result["cols"] == 2
    assert result["elapsed_sec"] >= 0
    assert "error" not in result


def test_smoke_fetch_pbp_error(monkeypatch: pytest.MonkeyPatch):
    def fail(season: int):
        raise ImportError("missing sportsdataverse")

    monkeypatch.setattr(sportsdataverse_smoke, "load_sdv_pbp_sample", fail)

    result = sportsdataverse_smoke.smoke_fetch_pbp(2025)

    assert result["rows"] == 0
    assert result["cols"] == 0
    assert result["elapsed_sec"] >= 0
    assert "missing sportsdataverse" in result["error"]


@pytest.mark.skipif(
    os.environ.get("CEMINIDFS_LIVE_SDV") != "1",
    reason="live sportsdataverse smoke requires opt-in network access",
)
def test_live_sdv_smoke_optional():
    pytest.importorskip("sportsdataverse")

    result = sportsdataverse_smoke.smoke_fetch_pbp(2025)

    assert result.get("error") is None
    assert result["rows"] > 0
    assert result["cols"] > 0
