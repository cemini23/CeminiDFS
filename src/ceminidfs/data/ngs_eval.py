"""NGS (Next Gen Stats) evaluation helpers — reference path only.

This module provides a stub loader for NFL Next Gen Stats data via
sportsdataverse-py. It is intentionally a no-op in the default path
to avoid network dependencies in production fetch operations.

To use NGS data in the future:
1. Install sportsdataverse: pip install sportsdataverse>=0.0.60
2. Call load_ngs_passing_sample(season) with optional import
3. Store the CPOE and separation columns on the passing row with
   apply_ngs_passing_residual(). The live coefficients default to zero.

See: docs/ngs-participation-eval.md for full evaluation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, cast

if TYPE_CHECKING:
    import pandas as pd


CPOE_COLUMN = "completion_percentage_above_expectation"
SEPARATION_COLUMN = "avg_separation"

# Live coefficients. They stay at zero until a walk-forward study sets them.
DEFAULT_CPOE_COEFFICIENT = 0.0
DEFAULT_SEPARATION_COEFFICIENT = 0.0

_ID_ALIASES = ("player_gsis_id", "player_id", "gsis_id", "nfl_id", "player_gsisid")
_NAME_ALIASES = ("player_display_name", "player_name", "full_name", "display_name")


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


def extract_ngs_passing_features(ngs_df: Any) -> "pd.DataFrame":
    """Return one feature row per player from an NGS passing frame.

    The returned frame has ``player_id``, ``player_name``, and only the NGS
    columns that the input frame already carries: ``ngs_cpoe`` and
    ``ngs_avg_separation``.
    """
    import pandas as pd

    columns = ["player_id", "player_name", "ngs_cpoe", "ngs_avg_separation"]
    if ngs_df is None or not isinstance(ngs_df, pd.DataFrame) or ngs_df.empty:
        return pd.DataFrame(columns=columns)

    id_col = _first_present(ngs_df, _ID_ALIASES)
    name_col = _first_present(ngs_df, _NAME_ALIASES)
    frame = pd.DataFrame(index=ngs_df.index)
    frame["player_id"] = ngs_df[id_col].fillna("").astype(str) if id_col else ""
    frame["player_name"] = ngs_df[name_col].fillna("").astype(str) if name_col else ""
    if CPOE_COLUMN in ngs_df.columns:
        frame["ngs_cpoe"] = pd.to_numeric(ngs_df[CPOE_COLUMN], errors="coerce")
    if SEPARATION_COLUMN in ngs_df.columns:
        frame["ngs_avg_separation"] = pd.to_numeric(ngs_df[SEPARATION_COLUMN], errors="coerce")

    if "ngs_cpoe" not in frame.columns and "ngs_avg_separation" not in frame.columns:
        return pd.DataFrame(columns=columns)

    frame = frame.loc[frame["player_id"].ne("") | frame["player_name"].ne("")]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    grouped = frame.groupby(["player_id", "player_name"], dropna=False, as_index=False).mean(
        numeric_only=True
    )
    return cast("pd.DataFrame", grouped.reindex(columns=columns))


def apply_ngs_passing_residual(
    rows: list[dict[str, Any]],
    ngs_df: Any,
    *,
    coefficient: float = DEFAULT_CPOE_COEFFICIENT,
    separation_coefficient: float = DEFAULT_SEPARATION_COEFFICIENT,
    config: Mapping[str, Any] | None = None,
    target_field: str = "fd_projection",
) -> list[dict[str, Any]]:
    """Store NGS passing columns on the passing row and add the optional residual.

    The CPOE and separation columns are stored when the NGS frame has them. The
    live coefficients default to zero, so the projection does not change unless
    the caller passes an explicit coefficient or config value.
    """
    if config is not None:
        ngs_cfg = config.get("ngs_eval") or {}
        if isinstance(ngs_cfg, Mapping):
            coefficient = _mapping_float(ngs_cfg, "cpoe_coefficient", coefficient)
            separation_coefficient = _mapping_float(
                ngs_cfg, "separation_coefficient", separation_coefficient
            )

    features = extract_ngs_passing_features(ngs_df)
    by_id: dict[str, dict[str, float]] = {}
    by_name: dict[str, dict[str, float]] = {}
    if not features.empty:
        for _, feature in features.iterrows():
            record = {
                "ngs_cpoe": _optional_float(feature.get("ngs_cpoe")),
                "ngs_avg_separation": _optional_float(feature.get("ngs_avg_separation")),
            }
            player_id = str(feature.get("player_id") or "").strip()
            player_name = _normalize_name(feature.get("player_name"))
            if player_id:
                by_id[player_id] = record
            if player_name:
                by_name[player_name] = record

    output: list[dict[str, Any]] = []
    for row in rows:
        mapped = dict(row)
        feature = _lookup_feature(mapped, by_id, by_name)
        if feature is None:
            output.append(mapped)
            continue

        cpoe = feature.get("ngs_cpoe")
        separation = feature.get("ngs_avg_separation")
        if cpoe is not None:
            mapped["ngs_cpoe"] = cpoe
        if separation is not None:
            mapped["ngs_avg_separation"] = separation

        delta = coefficient * (cpoe or 0.0) + separation_coefficient * (separation or 0.0)
        if delta and _is_passing_row(mapped) and target_field in mapped:
            base = _optional_float(mapped.get(target_field)) or 0.0
            mapped[target_field] = base + delta
        output.append(mapped)
    return output


def _lookup_feature(
    row: Mapping[str, Any],
    by_id: Mapping[str, dict[str, float]],
    by_name: Mapping[str, dict[str, float]],
) -> dict[str, float] | None:
    for key in ("player_id", "fd_id", "dk_id", "gsis_id"):
        player_id = str(row.get(key) or "").strip()
        if player_id and player_id in by_id:
            return by_id[player_id]
    name = _normalize_name(row.get("player_name") or row.get("name"))
    if name and name in by_name:
        return by_name[name]
    return None


def _is_passing_row(row: Mapping[str, Any]) -> bool:
    position = str(
        row.get("position") or row.get("fd_position") or row.get("dk_position") or ""
    ).upper()
    if position == "QB":
        return True
    return "pass_yds" in row or "projected_pass_attempts" in row


def _first_present(frame: Any, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _normalize_name(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _mapping_float(mapping: Mapping[str, Any], key: str, default: float) -> float:
    value = mapping.get(key, default)
    coerced = _optional_float(value)
    return default if coerced is None else coerced


def _optional_float(value: Any) -> float | None:
    import pandas as pd

    coerced = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(coerced) else float(coerced)
