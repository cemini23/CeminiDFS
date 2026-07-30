"""Build ESPN Pre-Draft Rankings CSV from season-long ADP."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from ceminidfs.models.scoring import score_espn_ppr_season
from ceminidfs.redraft import config

_COUNTING_COLS = (
    "pass_yds",
    "pass_td",
    "int",
    "rush_yds",
    "rush_td",
    "rec",
    "rec_yds",
    "rec_td",
    "fumbles_lost",
)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {c: str(c).strip().lower().replace(" ", "_") for c in df.columns}
    out = df.rename(columns=renamed)
    aliases = {
        "player": "name",
        "player_name": "name",
        "full_name": "name",
        "position": "pos",
        "positions": "pos",
        "avg_pick": "adp",
        "average_draft_position": "adp",
        "rank": "adp",
        "tm": "team",
        "nfl_team": "team",
        "proj": "projection_pts",
        "projection": "projection_pts",
        "pts": "projection_pts",
    }
    for src, dest in aliases.items():
        if src in out.columns and dest not in out.columns:
            out = out.rename(columns={src: dest})
    return out


def _score_row_if_needed(row: pd.Series) -> float | None:
    if "projection_pts" in row.index and pd.notna(row.get("projection_pts")):
        try:
            return float(row["projection_pts"])
        except (TypeError, ValueError):
            pass
    if any(col in row.index and pd.notna(row.get(col)) for col in _COUNTING_COLS):
        stats = {col: row.get(col, 0.0) for col in _COUNTING_COLS}
        return float(score_espn_ppr_season(stats))
    return None


def load_adp_csv(path: Path | str) -> pd.DataFrame:
    """Load and normalize an ADP CSV. Requires name, pos, adp columns (or aliases)."""

    raw = pd.read_csv(path)
    if raw.empty:
        raise ValueError(f"ADP CSV is empty: {path}")
    df = _normalize_columns(raw)
    missing = [c for c in config.ADP_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"ADP CSV missing required columns {missing}. "
            f"Need {config.ADP_REQUIRED_COLUMNS} (aliases: player→name, position→pos, avg_pick→adp)."
        )
    out = df.copy()
    out["name"] = out["name"].astype(str).str.strip()
    out["pos"] = out["pos"].astype(str).str.strip().str.upper()
    out["adp"] = pd.to_numeric(out["adp"], errors="coerce")
    out = out.dropna(subset=["name", "pos", "adp"])
    if out.empty:
        raise ValueError(f"No valid ADP rows after cleaning: {path}")
    if "team" not in out.columns:
        out["team"] = ""
    else:
        out["team"] = out["team"].fillna("").astype(str).str.strip().str.upper()
    if "notes" not in out.columns:
        out["notes"] = ""
    else:
        out["notes"] = out["notes"].fillna("").astype(str)
    return out


def build_prerank(
    adp_df: pd.DataFrame,
    *,
    top_n: int = config.PRERANK_TOP_N,
    projections_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return ordered prerank board: rank, name, pos, team, adp, projection_pts, notes."""

    board = adp_df.copy()
    if projections_df is not None and not projections_df.empty:
        proj = _normalize_columns(projections_df)
        name_col = "name" if "name" in proj.columns else None
        if name_col is None:
            raise ValueError("Projections CSV needs a name/player column")
        proj = proj.copy()
        proj["_merge_key"] = proj[name_col].astype(str).str.strip().str.lower()
        board["_merge_key"] = board["name"].astype(str).str.strip().str.lower()
        keep = [c for c in ("projection_pts", *_COUNTING_COLS) if c in proj.columns]
        if keep:
            board = board.drop(
                columns=[c for c in keep if c in board.columns],
                errors="ignore",
            )
            board = board.merge(
                proj[["_merge_key", *keep]].drop_duplicates("_merge_key"),
                on="_merge_key",
                how="left",
            )
        board = board.drop(columns=["_merge_key"], errors="ignore")

    pts = board.apply(_score_row_if_needed, axis=1)
    board["projection_pts"] = pts

    # Primary sort: ADP ascending; tie-break higher ESPN PPR projection
    board = board.sort_values(
        by=["adp", "projection_pts"],
        ascending=[True, False],
        na_position="last",
    )
    board = board.head(int(top_n)).reset_index(drop=True)
    board.insert(0, "rank", range(1, len(board) + 1))

    cols = ["rank", "name", "pos", "team", "adp", "projection_pts", "notes"]
    for col in cols:
        if col not in board.columns:
            board[col] = "" if col in ("team", "notes") else pd.NA
    return board[cols]


def write_prerank_csv(board: pd.DataFrame, path: Path | str) -> Path:
    """Write prerank board to CSV."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(out, index=False)
    return out


def prerank_from_paths(
    adp_path: Path | str,
    out_path: Path | str,
    *,
    top_n: int = config.PRERANK_TOP_N,
    projections_path: Path | str | None = None,
) -> dict[str, Any]:
    """Load ADP (+ optional projections), write prerank CSV, return summary."""

    adp_df = load_adp_csv(adp_path)
    projections_df = None
    if projections_path is not None:
        projections_df = pd.read_csv(projections_path)
    board = build_prerank(adp_df, top_n=top_n, projections_df=projections_df)
    written = write_prerank_csv(board, out_path)
    return {
        "rows": len(board),
        "out": str(written),
        "top_name": str(board.iloc[0]["name"]) if len(board) else None,
        "top_adp": float(board.iloc[0]["adp"]) if len(board) else None,
    }
