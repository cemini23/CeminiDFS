import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data import fetch as fetch_module


def _ngs_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "season": [2025, 2025],
            "week": [1, 2],
            "player_gsis_id": ["00-0001", "00-0002"],
            "player_display_name": ["Alpha", "Beta"],
            "yards": [50.0, 60.0],
        }
    )


def test_fetch_ngs_rushing_uses_rushing_stat_type(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    captured: dict = {}
    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)
    monkeypatch.setattr(fetch_module, "_require_nflreadpy", lambda: object())
    monkeypatch.setattr(
        fetch_module,
        "_call_nextgen_stats",
        lambda module, stat_type, season: captured.update(stat_type=stat_type) or _ngs_frame(),
    )

    fetch_module.fetch_ngs_rushing(2025)

    assert captured["stat_type"] == "rushing"
    assert (cache_root / "ngs_rushing_2025.parquet").is_file()


def test_fetch_ngs_rushing_reuses_fresh_cache(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    pd.DataFrame({"player_id": ["cached"]}).to_parquet(
        cache_root / "ngs_rushing_2025.parquet", index=False
    )
    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)

    def boom(*args, **kwargs):  # pragma: no cover - guards the loader call
        raise AssertionError("loader must not run when a fresh NGS cache exists")

    monkeypatch.setattr(fetch_module, "_call_nextgen_stats", boom)

    result = fetch_module.fetch_ngs_rushing(2025)

    assert result["player_id"].tolist() == ["cached"]


def test_fetch_ftn_charting_reuses_fresh_cache(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    pd.DataFrame({"player_id": ["cached"], "epa": [0.11]}).to_parquet(
        cache_root / "ftn_charting_2025.parquet", index=False
    )

    def boom(*args, **kwargs):  # pragma: no cover - guards the loader call
        raise AssertionError("loader must not run when a fresh FTN cache exists")

    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)
    monkeypatch.setattr(fetch_module, "_require_nflreadpy", boom)
    monkeypatch.setattr(fetch_module, "_call_with_season", boom)

    result = fetch_module.fetch_ftn_charting(2025)

    assert result["player_id"].tolist() == ["cached"]


def test_fetch_ftn_charting_tolerates_missing_loader(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)
    monkeypatch.setattr(fetch_module, "_require_nflreadpy", lambda: SimpleNamespace())

    result = fetch_module.fetch_ftn_charting(2025)

    assert result.empty


def test_warm_telemetry_caches_degrades_when_fetchers_raise_import_error(monkeypatch):
    def import_error(season, force=False):
        raise ImportError("nflreadpy unavailable in tests")

    monkeypatch.setattr(fetch_module, "fetch_ngs_rushing", import_error)
    monkeypatch.setattr(fetch_module, "fetch_ftn_charting", import_error)

    warmed = fetch_module.warm_telemetry_caches(2025)

    assert set(warmed) == {"rushing", "ftn_charting"}
    assert all(frame.empty for frame in warmed.values())
