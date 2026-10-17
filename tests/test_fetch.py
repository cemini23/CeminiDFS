import inspect
import json
import sys
import time
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data import fetch as fetch_module


def _call_fetch_week_datasets(season: int, week: int):
    signature = inspect.signature(fetch_module.fetch_week_datasets)
    kwargs = {}

    for name in signature.parameters:
        if name == "season":
            kwargs[name] = season
        elif name == "week":
            kwargs[name] = week
        elif name == "config":
            kwargs[name] = {}
        else:  # pragma: no cover - defensive if the implementation grows
            raise AssertionError(f"Unhandled fetch_week_datasets parameter: {name}")

    return fetch_module.fetch_week_datasets(**kwargs)


def _call_write_fetch_manifest(season: int, week: int, datasets: dict, tmp_path: Path) -> Path:
    signature = inspect.signature(fetch_module.write_fetch_manifest)
    kwargs = {}

    for name in signature.parameters:
        if name == "season":
            kwargs[name] = season
        elif name == "week":
            kwargs[name] = week
        elif name in {"datasets", "artifacts"}:
            kwargs[name] = datasets
        elif name in {"path", "manifest_path", "out_path", "output_path"}:
            kwargs[name] = tmp_path / "fetch_manifest.json"
        elif name == "config":
            kwargs[name] = {}
        elif name in {"work_dir", "output_dir"}:
            kwargs[name] = tmp_path
        else:  # pragma: no cover - defensive if the implementation grows
            raise AssertionError(f"Unhandled write_fetch_manifest parameter: {name}")

    path = fetch_module.write_fetch_manifest(**kwargs)
    if path is None:
        explicit_path = kwargs.get("path") or kwargs.get("manifest_path")
        explicit_path = explicit_path or kwargs.get("out_path") or kwargs.get("output_path")
        if explicit_path is None:
            raise AssertionError("write_fetch_manifest did not return a path")
        return Path(explicit_path)
    return Path(path)


def _artifact_map(payload: dict) -> dict:
    return payload.get("artifacts") or payload.get("input_artifacts", {}).get("artifacts", {})


def test_filter_by_week():
    frame = pd.DataFrame(
        {
            "week": [1, 2, 1, 3],
            "value": ["a", "b", "c", "d"],
        }
    )

    result = fetch_module.filter_by_week(frame, 1)

    expected = pd.DataFrame({"week": [1, 1], "value": ["a", "c"]})
    assert_frame_equal(result.reset_index(drop=True), expected)


def test_filter_by_week_missing_column():
    frame = pd.DataFrame({"player": ["A", "B"], "value": [10, 20]})

    result = fetch_module.filter_by_week(frame, 1)

    assert_frame_equal(result, frame)


def test_week_cache_dir_paths(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "artifacts" / "cache"
    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)

    path = fetch_module.week_cache_dir(2024, 1)

    assert path.is_absolute()
    assert path.parent != cache_root
    assert path.parts[-1] in {"week_1", "1"}
    assert "2024" in path.parts
    assert path.is_relative_to(cache_root)


def test_write_fetch_manifest(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "artifacts" / "cache"
    week_dir = cache_root / "2024" / "week_1"

    if hasattr(fetch_module, "_cache_dir"):
        monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)
    if hasattr(fetch_module, "week_cache_dir"):
        monkeypatch.setattr(fetch_module, "week_cache_dir", lambda season, week: week_dir)
    if hasattr(fetch_module, "git_commit"):
        monkeypatch.setattr(fetch_module, "git_commit", lambda: "abc1234")

    datasets = {
        "schedules": {"path": str(week_dir / "schedules.parquet"), "rows": 1},
        "pbp": {"path": str(week_dir / "pbp.parquet"), "rows": 2},
        "injuries": {"path": str(week_dir / "injuries.parquet"), "rows": 3},
    }

    manifest_path = _call_write_fetch_manifest(2024, 1, datasets, tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["run_id"]
    assert payload["git_commit"] == "abc1234"
    assert _artifact_map(payload) == datasets
    assert payload["stage_status"]["fetch"] in {"complete", "success"}


def test_fetch_week_datasets_mocked(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "artifacts" / "cache"
    week_dir = cache_root / "2024" / "week_1"

    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)
    monkeypatch.setattr(fetch_module, "week_cache_dir", lambda season, week: week_dir)

    schedules = pd.DataFrame({"week": [1, 2], "game_id": ["g1", "g2"]})
    pbp = pd.DataFrame({"week": [1, 1, 2], "play_id": [1, 2, 3]})
    injuries = pd.DataFrame({"week": [1, 2], "player": ["A", "B"]})
    rosters = pd.DataFrame({"week": [1, 2], "player": ["A", "B"]})

    monkeypatch.setattr(fetch_module, "fetch_schedules", lambda season: schedules)
    monkeypatch.setattr(fetch_module, "fetch_pbp", lambda season: pbp)
    monkeypatch.setattr(fetch_module, "fetch_injuries", lambda season: injuries)
    monkeypatch.setattr(fetch_module, "fetch_rosters", lambda season: rosters)
    monkeypatch.setattr(
        fetch_module,
        "warm_telemetry_caches",
        lambda season, force=False: {
            "rushing": pd.DataFrame(),
            "ftn_charting": pd.DataFrame(),
        },
    )

    datasets = _call_fetch_week_datasets(2024, 1)

    expected_files = {
        "schedules": week_dir / "schedules.parquet",
        "vegas": week_dir / "vegas.parquet",
        "weather": week_dir / "weather.parquet",
        "pbp": week_dir / "pbp.parquet",
        "injuries": week_dir / "injuries.parquet",
        "rosters": week_dir / "rosters.parquet",
    }

    for name, path in expected_files.items():
        assert path.exists(), f"expected {path} to be written"
        saved = pd.read_parquet(path)
        if name == "weather":
            assert len(saved) == 0
            continue
        if name == "pbp":
            assert set(saved["week"]) == {1, 2}
            assert datasets["pbp"]["scope"] == "season"
            continue
        if name == "rosters":
            assert set(saved["week"]) == {1, 2}
            assert datasets["rosters"]["scope"] == "season"
            continue
        assert set(saved["week"]) == {1}
        source_name = "schedules" if name == "vegas" else name
        assert len(saved) == len(
            fetch_module.filter_by_week(
                {"schedules": schedules, "pbp": pbp, "injuries": injuries, "rosters": rosters}[
                    source_name
                ],
                1,
            )
        )

    assert set(datasets) == {"schedules", "vegas", "weather", "pbp", "injuries", "rosters"}


def test_fetch_week_datasets_warms_rosters(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "artifacts" / "cache"
    week_dir = cache_root / "2024" / "week_1"

    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)
    monkeypatch.setattr(fetch_module, "week_cache_dir", lambda season, week: week_dir)

    frames = {
        "schedules": pd.DataFrame({"week": [1], "game_id": ["g1"]}),
        "pbp": pd.DataFrame({"week": [1], "play_id": [1]}),
        "injuries": pd.DataFrame({"week": [1], "player": ["A"]}),
        "rosters": pd.DataFrame({"week": [1, 2], "player": ["A", "B"]}),
    }
    for name, frame in frames.items():
        monkeypatch.setattr(
            fetch_module,
            f"fetch_{name}",
            lambda season, frame=frame, **kwargs: frame,
        )
    monkeypatch.setattr(
        fetch_module,
        "warm_telemetry_caches",
        lambda season, force=False: {
            "rushing": pd.DataFrame(),
            "ftn_charting": pd.DataFrame(),
        },
    )

    datasets = _call_fetch_week_datasets(2024, 1)

    assert "rosters" in datasets
    assert datasets["rosters"]["scope"] == "season"
    saved = pd.read_parquet(week_dir / "rosters.parquet")
    assert set(saved["week"]) == {1, 2}


def test_fetch_cached_skips_parquet_older_than_ttl(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    stale = pd.DataFrame({"game_id": ["old"]})
    cache_path = cache_root / "schedules_2026.parquet"
    stale.to_parquet(cache_path, index=False)
    old = time.time() - fetch_module.CACHE_TTL_SECONDS - 60
    cache_path.touch()
    import os

    os.utime(cache_path, (old, old))

    fresh = pd.DataFrame({"game_id": ["live"]})
    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)
    monkeypatch.setattr(fetch_module, "_require_nflreadpy", lambda: object())
    monkeypatch.setattr(fetch_module, "_call_loader", lambda *args, **kwargs: fresh)
    monkeypatch.setattr(fetch_module, "_to_pandas", lambda data: data)

    result = fetch_module._fetch_cached("schedules", 2026, ("load_schedules",))

    assert list(result["game_id"]) == ["live"]


def test_fetch_cached_force_ignores_fresh_parquet(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    cache_path = cache_root / "schedules_2026.parquet"
    pd.DataFrame({"game_id": ["cached"]}).to_parquet(cache_path, index=False)
    fresh = pd.DataFrame({"game_id": ["forced"]})
    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)
    monkeypatch.setattr(fetch_module, "_require_nflreadpy", lambda: object())
    monkeypatch.setattr(fetch_module, "_call_loader", lambda *args, **kwargs: fresh)
    monkeypatch.setattr(fetch_module, "_to_pandas", lambda data: data)

    result = fetch_module._fetch_cached("schedules", 2026, ("load_schedules",), force=True)

    assert list(result["game_id"]) == ["forced"]


def test_fetch_force_enabled_reads_nested_config():
    assert fetch_module.fetch_force_enabled({"fetch": {"force": True}}) is True
    assert fetch_module.fetch_force_enabled({"force": True}) is True
    assert fetch_module.fetch_force_enabled({}) is False


def test_injuries_cache_ttl_is_fifteen_minutes_and_default_is_twelve_hours(tmp_path: Path):
    import os

    assert fetch_module.CACHE_TTL_SECONDS == 12 * 60 * 60
    assert fetch_module.CACHE_TTL_SECONDS_BY_KIND["injuries"] == 15 * 60

    cache_path = tmp_path / "injuries_2026.parquet"
    cache_path.write_bytes(b"")
    age = time.time() - 20 * 60
    os.utime(cache_path, (age, age))

    assert fetch_module._cache_is_fresh(cache_path, "injuries") is False
    assert fetch_module._cache_is_fresh(cache_path, "schedules") is True
    assert fetch_module._cache_is_fresh(cache_path) is True


def _ngs_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "season": [2025, 2025],
            "week": [1, 2],
            "player_gsis_id": ["00-0001", "00-0002"],
            "player_display_name": ["Alpha", "Beta"],
            "avg_separation": [2.0, 3.0],
            "avg_cushion": [5.0, 6.0],
            "percent_share_of_intended_air_yards": [0.2, 0.3],
            "yards": [50.0, 60.0],
            "targets": [5.0, 6.0],
        }
    )


def test_fetch_ngs_receiving_caches_canonicalized_frame(tmp_path: Path, monkeypatch):
    """The NGS fetcher passes ``stat_type`` and caches ``player_id``/``player_name``."""

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    captured: dict = {}
    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)
    monkeypatch.setattr(fetch_module, "_require_nflreadpy", lambda: object())

    def fake_call(module, stat_type, season):
        captured["module"] = module
        captured["stat_type"] = stat_type
        captured["season"] = season
        return _ngs_frame()

    monkeypatch.setattr(fetch_module, "_call_nextgen_stats", fake_call)

    result = fetch_module.fetch_ngs_receiving(2025)

    assert captured["stat_type"] == "receiving"
    assert captured["season"] == 2025
    cache_path = cache_root / "ngs_receiving_2025.parquet"
    assert cache_path.is_file()
    assert result["player_id"].tolist() == ["00-0001", "00-0002"]
    assert "player_name" in result.columns
    saved = pd.read_parquet(cache_path)
    assert "player_id" in saved.columns and "player_name" in saved.columns


def test_fetch_ngs_passing_uses_passing_stat_type(tmp_path: Path, monkeypatch):
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

    fetch_module.fetch_ngs_passing(2025)

    assert captured["stat_type"] == "passing"
    assert (cache_root / "ngs_passing_2025.parquet").is_file()


def test_fetch_ngs_reuses_fresh_cache(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    pd.DataFrame({"player_id": ["cached"]}).to_parquet(
        cache_root / "ngs_receiving_2025.parquet", index=False
    )
    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)

    def boom(*args, **kwargs):  # pragma: no cover - guards the loader call
        raise AssertionError("loader must not run when a fresh NGS cache exists")

    monkeypatch.setattr(fetch_module, "_call_nextgen_stats", boom)

    result = fetch_module.fetch_ngs_receiving(2025)

    assert result["player_id"].tolist() == ["cached"]


def test_fetch_ngs_tolerates_out_of_range_season(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)
    monkeypatch.setattr(fetch_module, "_require_nflreadpy", lambda: object())

    def out_of_range(module, stat_type, season):
        raise ValueError("Season must be between 2016 and 2025")

    monkeypatch.setattr(fetch_module, "_call_nextgen_stats", out_of_range)

    result = fetch_module.fetch_ngs_receiving(1999)

    assert result.empty


def test_warm_ngs_caches_degrades_without_nflreadpy(tmp_path: Path, monkeypatch):
    """A missing nflreadpy must degrade to empty frames, not raise."""

    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: tmp_path / "cache")

    warmed = fetch_module.warm_ngs_caches(2025)

    assert set(warmed) == {"receiving", "passing"}
    assert all(frame.empty for frame in warmed.values())


def test_fetch_week_datasets_warms_ngs_caches(tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "artifacts" / "cache"
    week_dir = cache_root / "2024" / "week_1"

    monkeypatch.setattr(fetch_module, "_cache_dir", lambda: cache_root)
    monkeypatch.setattr(fetch_module, "week_cache_dir", lambda season, week: week_dir)

    frames = {
        "schedules": pd.DataFrame({"week": [1], "game_id": ["g1"]}),
        "pbp": pd.DataFrame({"week": [1], "play_id": [1]}),
        "injuries": pd.DataFrame({"week": [1], "player": ["A"]}),
        "rosters": pd.DataFrame({"week": [1], "player": ["A"]}),
    }
    for name, frame in frames.items():
        monkeypatch.setattr(
            fetch_module,
            f"fetch_{name}",
            lambda season, frame=frame, **kwargs: frame,
        )

    calls: list[int] = []
    monkeypatch.setattr(
        fetch_module,
        "warm_ngs_caches",
        lambda season, force=False: calls.append(season) or {"receiving": pd.DataFrame()},
    )
    monkeypatch.setattr(
        fetch_module,
        "warm_telemetry_caches",
        lambda season, force=False: {
            "rushing": pd.DataFrame(),
            "ftn_charting": pd.DataFrame(),
        },
    )

    fetch_module.fetch_week_datasets(2024, 1)

    assert calls == [2024]
