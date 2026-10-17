"""Shared situational cache: three parquet artifacts plus a deterministic manifest.

The caller applies the point-in-time week cutoff before calling
:func:`write_shared_cache`; this module never drops rows and never filters
weeks. It only serializes exactly the frames it is given and records their
content hashes in a ``manifest.json`` for downstream verification.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Union

import pandas as pd

PLAYER_TELEMETRY_NAME = "player_telemetry_pit.parquet"
DEFENSE_COUNTERPART_NAME = "defense_counterpart_pit.parquet"
GAME_CONTEXT_NAME = "game_context_pit.parquet"


def write_shared_cache(
    destination: Union[str, Path],
    *,
    players: pd.DataFrame,
    defense: pd.DataFrame,
    games: pd.DataFrame,
    season: int,
    week: int,
    max_source_week: int,
) -> dict:
    """Write the three shared-cache parquet files and their manifest.

    Writes ``players`` to :data:`PLAYER_TELEMETRY_NAME`, ``defense`` to
    :data:`DEFENSE_COUNTERPART_NAME`, and ``games`` to :data:`GAME_CONTEXT_NAME`
    under ``destination`` (created if needed), each with ``index=False``.

    The manifest records ``season``, ``week``, ``max_source_week``, and a
    ``files`` mapping with each parquet's ``sha256`` (hex digest of the file
    bytes), ``rows``, and ``columns``. It is serialized with sorted keys and
    compact separators plus a trailing newline, and the same dict is returned.
    """

    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)

    artifacts = (
        (PLAYER_TELEMETRY_NAME, players),
        (DEFENSE_COUNTERPART_NAME, defense),
        (GAME_CONTEXT_NAME, games),
    )

    files: dict = {}
    for name, frame in artifacts:
        path = dest / name
        frame.to_parquet(path, index=False)
        files[name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rows": int(frame.shape[0]),
            "columns": int(frame.shape[1]),
        }

    manifest = {
        "season": int(season),
        "week": int(week),
        "max_source_week": int(max_source_week),
        "files": files,
    }

    manifest_path = dest / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return manifest
