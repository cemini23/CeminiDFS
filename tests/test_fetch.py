import inspect
import json
import sys
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

    monkeypatch.setattr(fetch_module, "fetch_schedules", lambda season: schedules)
    monkeypatch.setattr(fetch_module, "fetch_pbp", lambda season: pbp)
    monkeypatch.setattr(fetch_module, "fetch_injuries", lambda season: injuries)

    datasets = _call_fetch_week_datasets(2024, 1)

    expected_files = {
        "schedules": week_dir / "schedules.parquet",
        "pbp": week_dir / "pbp.parquet",
        "injuries": week_dir / "injuries.parquet",
    }

    for name, path in expected_files.items():
        assert path.exists(), f"expected {path} to be written"
        saved = pd.read_parquet(path)
        assert set(saved["week"]) == {1}
        assert len(saved) == len(fetch_module.filter_by_week({"schedules": schedules, "pbp": pbp, "injuries": injuries}[name], 1))

    assert set(datasets) == {"schedules", "pbp", "injuries"}
