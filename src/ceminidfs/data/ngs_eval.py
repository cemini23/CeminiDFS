"""NGS (Next Gen Stats) evaluation stub — P2 reference only.

This module provides a stub loader for NFL Next Gen Stats data via
sportsdataverse-py. It is intentionally a no-op in the default path
to avoid network dependencies in production fetch operations.

To use NGS data in the future:
1. Install sportsdataverse: pip install sportsdataverse>=0.0.60
2. Call load_ngs_passing_sample(season) with optional import
3. Integrate player-level athleticism features (speed, distance, separation)
   into the projection engine as desired.

See: docs/ngs-participation-eval.md for full evaluation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


def load_ngs_passing_sample(season: int) -> "pd.DataFrame | None":
    """Stub loader for NGS passing data.

    Attempts to import sportsdataverse and load NGS passing sample data.
    Returns None if the library is not available or on any fetch error.

    Args:
        season: NFL season year (e.g., 2024)

    Returns:
        DataFrame with NGS passing metrics (aggressiveness, completion_probability,
        expected_completion_percentage, etc.) or None if unavailable.
    """
    try:
        import sportsdataverse.nfl as nfl  # type: ignore
        df = nfl.load_nfl_ngs_passing(seasons=[season], return_as_pandas=True)
        return df  # type: ignore
    except Exception:
        # Stub: no network fetch in default path
        return None
