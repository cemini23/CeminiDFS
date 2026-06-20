from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ceminidfs.data.fetch import fetch_week_datasets, write_fetch_manifest


def fetch_week(
    season: int,
    week: int,
    config: Mapping[str, Any] | None = None,
) -> Path:
    """Fetch datasets and write fetch manifest; return manifest path."""
    cfg = dict(config or {})
    work_dir = Path(cfg.get("work_dir", Path("runs") / f"{season}_week_{week}"))
    work_dir.mkdir(parents=True, exist_ok=True)

    datasets = fetch_week_datasets(season, week, cfg)
    return write_fetch_manifest(season, week, datasets, work_dir, cfg)
