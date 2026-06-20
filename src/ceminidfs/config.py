from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional, Union


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "nfl_dfs.yaml"

DEFAULT_CONFIG: Dict[str, Any] = {
    "paths": {
        "artifacts_dir": "artifacts",
        "cache_dir": "artifacts/cache",
    },
    "seasons": [2024, 2025],
    "rolling_windows": [3, 5, 8],
    "volume": {
        "league_sec_per_play": 36.2,
        "league_total": 44.8,
        "plays_intercept": 62.0,
        "base_pass_rate": 0.565,
        "sack_rate": 0.06,
        "scramble_rate": 0.08,
    },
    "usage": {
        "share_weights": [0.5, 0.3, 0.2],
        "l3_window": 3,
    },
    "sim_rerank": {
        "enabled": False,
        "candidates": 2000,
        "final_count": 150,
    },
}


def runtime_config(**overrides: Any) -> Dict[str, Any]:
    """Load nfl_dfs.yaml defaults and apply CLI/runtime overrides."""

    cfg = load_config()
    for key, value in overrides.items():
        if value is not None:
            cfg[key] = value
    return cfg


def load_config(path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    config = deepcopy(DEFAULT_CONFIG)

    if not config_path.exists():
        return config

    file_config = _read_yaml(config_path)
    return _deep_merge(config, file_config)


def _read_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return _minimal_yaml_load(path.read_text(encoding="utf-8"))

    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected mapping in config file: {path}")
    return loaded


def _minimal_yaml_load(text: str) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    current_key: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue

        if not line.startswith(" "):
            key, sep, value = line.partition(":")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()
            if value:
                parsed[key] = _parse_scalar(value)
                current_key = None
            else:
                parsed[key] = {}
                current_key = key
            continue

        if current_key is None:
            continue

        child = parsed[current_key]
        stripped = line.strip()
        if stripped.startswith("- "):
            if not isinstance(child, list):
                child = []
                parsed[current_key] = child
            child.append(_parse_scalar(stripped[2:].strip()))
            continue

        key, sep, value = stripped.partition(":")
        if sep and isinstance(child, dict):
            child[key.strip()] = _parse_scalar(value.strip())

    return parsed


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value.strip("\"'")


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
