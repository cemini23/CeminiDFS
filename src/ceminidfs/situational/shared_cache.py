"""Shared situational cache: three parquet artifacts plus a deterministic manifest.

The caller applies the point-in-time week cutoff before calling
:func:`write_shared_cache`. This module does not drop player rows. It adds
the quarter-count columns, then serializes the frames and records their
content hashes in a ``manifest.json``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Union

import pandas as pd

from ceminidfs.situational.contract import canon_team
from ceminidfs.situational.eb import EB_K, empirical_bayes
from ceminidfs.situational.lag import cut_point_in_time

PLAYER_TELEMETRY_NAME = "player_telemetry_pit.parquet"
DEFENSE_COUNTERPART_NAME = "defense_counterpart_pit.parquet"
GAME_CONTEXT_NAME = "game_context_pit.parquet"

# One prior target in each quarter. The prior mean is 0.25.
QUARTER_SHARE_PRIOR = 0.25

COUNT_COLUMNS = (
    "q1_targets",
    "q2_targets",
    "q3_targets",
    "q4_targets",
    "total_targets",
    "q3_recs",
    "q4_recs",
    "q4_rush_att",
    "total_rush_att",
    "q4_trail_targets",
    "q4_lead_rush_att",
)
SHARE_COLUMNS = ("w_rec_q3_eb", "w_rec_q4_eb", "w_rush_q4_eb")
TEAM_COLUMNS = tuple(f"team_{name}" for name in COUNT_COLUMNS)
QUARTER_COLUMNS = COUNT_COLUMNS + SHARE_COLUMNS + TEAM_COLUMNS


def write_shared_cache(
    destination: Union[str, Path],
    *,
    players: pd.DataFrame,
    defense: pd.DataFrame,
    games: pd.DataFrame,
    season: int,
    week: int,
    max_source_week: int,
    pbp: pd.DataFrame | None = None,
) -> dict:
    """Write the three shared-cache parquet files and their manifest.

    Writes ``players`` to :data:`PLAYER_TELEMETRY_NAME`, ``defense`` to
    :data:`DEFENSE_COUNTERPART_NAME`, and ``games`` to :data:`GAME_CONTEXT_NAME`
    under ``destination`` (created if needed), each with ``index=False``.

    The player file gains the quarter counts. ``pbp`` is optional. When it is
    present, the counts use plays with ``week < target week`` (and earlier
    seasons). When it is absent, missing count columns are 0 and the shrunk
    shares use the 0.25 prior.

    The manifest records ``season``, ``week``, ``max_source_week``, and a
    ``files`` mapping with each parquet's ``sha256`` (hex digest of the file
    bytes), ``rows``, and ``columns``. It is serialized with sorted keys and
    compact separators plus a trailing newline, and the same dict is returned.
    """

    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    players = attach_quarter_telemetry(players, pbp, season=int(season), week=int(week))

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


def attach_quarter_telemetry(
    players: pd.DataFrame,
    pbp: pd.DataFrame | None,
    *,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Add player and team quarter counts. Do not drop player rows.

    Player counts follow the player across teams. Team counts follow the
    team on the player row. Shares shrink toward 0.25 with strength ``EB_K``.
    """

    frame = players.copy() if players is not None else pd.DataFrame()
    if pbp is not None:
        frame = frame.drop(columns=[name for name in QUARTER_COLUMNS if name in frame.columns])
        player_counts, team_counts = player_quarter_counts(pbp, season=int(season), week=int(week))
        if "player_id" in frame.columns and not player_counts.empty:
            frame["player_id"] = frame["player_id"].astype(str)
            stats = player_counts.drop(columns=["team"], errors="ignore")
            frame = frame.merge(stats, on="player_id", how="left")
        if "team" in frame.columns and not team_counts.empty:
            keyed = frame.copy()
            keyed["_team_key"] = keyed["team"].map(canon_team)
            teams = team_counts.copy()
            teams["team"] = teams["team"].map(canon_team)
            keyed = keyed.merge(teams, left_on="_team_key", right_on="team", how="left", suffixes=("", "_y"))
            drop = ["_team_key"]
            drop.extend(column for column in keyed.columns if column.endswith("_y"))
            frame = keyed.drop(columns=drop)
    return _stamp_quarter_columns(frame)


def player_quarter_counts(
    pbp: pd.DataFrame | None,
    *,
    season: int,
    week: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return point-in-time player counts and team counts.

    A row is kept when its season is earlier, or its season matches and its
    week is greater than 0 and less than ``week``. Overtime plays count in
    the totals. They do not count in ``q1`` through ``q4``.
    """

    player_cols = ["player_id", "team", *COUNT_COLUMNS]
    team_cols = ["team", *TEAM_COLUMNS]
    empty_players = pd.DataFrame(columns=player_cols)
    empty_teams = pd.DataFrame(columns=team_cols)
    if pbp is None or len(pbp) == 0:
        return empty_players, empty_teams
    if "season" not in pbp.columns or "week" not in pbp.columns:
        return empty_players, empty_teams
    cut = cut_point_in_time(pbp, season=int(season), week=int(week))
    if cut.empty:
        return empty_players, empty_teams
    events = pd.concat(
        [_receiver_events(cut), _rusher_events(cut)],
        ignore_index=True,
    )
    if events.empty:
        return empty_players, empty_teams
    grouped = events.groupby("player_id", as_index=False)[list(COUNT_COLUMNS)].sum()
    latest = (
        events.sort_values(["player_id"], kind="mergesort")
        .groupby("player_id", as_index=False)
        .tail(1)[["player_id", "team"]]
    )
    players = grouped.merge(latest, on="player_id", how="left")
    team_sums = events.groupby("team", as_index=False)[list(COUNT_COLUMNS)].sum()
    team_sums = team_sums.rename(columns={name: f"team_{name}" for name in COUNT_COLUMNS})
    team_sums = team_sums.loc[team_sums["team"].astype(str).ne("")].reset_index(drop=True)
    return players.loc[:, player_cols].reset_index(drop=True), team_sums.loc[:, team_cols].reset_index(drop=True)


def _stamp_quarter_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in (*COUNT_COLUMNS, *TEAM_COLUMNS):
        if column not in out.columns:
            out[column] = 0
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0).astype("int64")
    prior = pd.Series(QUARTER_SHARE_PRIOR, index=out.index, dtype="float64")
    out["w_rec_q3_eb"] = empirical_bayes(
        out["q3_targets"].astype(float),
        out["total_targets"].astype(float),
        prior,
        k=EB_K,
    )
    out["w_rec_q4_eb"] = empirical_bayes(
        out["q4_targets"].astype(float),
        out["total_targets"].astype(float),
        prior,
        k=EB_K,
    )
    out["w_rush_q4_eb"] = empirical_bayes(
        out["q4_rush_att"].astype(float),
        out["total_rush_att"].astype(float),
        prior,
        k=EB_K,
    )
    return out


def _receiver_events(plays: pd.DataFrame) -> pd.DataFrame:
    return _role_events(plays, id_column="receiver_player_id", kind="target")


def _rusher_events(plays: pd.DataFrame) -> pd.DataFrame:
    return _role_events(plays, id_column="rusher_player_id", kind="rush")


def _role_events(plays: pd.DataFrame, *, id_column: str, kind: str) -> pd.DataFrame:
    columns = ["player_id", "team", *COUNT_COLUMNS]
    if id_column not in plays.columns:
        return pd.DataFrame(columns=columns)
    flag = "pass" if kind == "target" else "rush"
    mask = _flag(plays, flag) & plays[id_column].notna()
    part = plays.loc[mask]
    if part.empty:
        return pd.DataFrame(columns=columns)
    qtr = _num(part, "qtr")
    score = _num(part, "score_differential")
    complete = _flag(part, "complete_pass")
    player_id = part[id_column].astype(str)
    keep = player_id.ne("") & ~player_id.str.lower().isin({"nan", "none", "<na>"})
    if kind == "target":
        counts = {
            "q1_targets": qtr.eq(1).astype("int64"),
            "q2_targets": qtr.eq(2).astype("int64"),
            "q3_targets": qtr.eq(3).astype("int64"),
            "q4_targets": qtr.eq(4).astype("int64"),
            "total_targets": pd.Series(1, index=part.index, dtype="int64"),
            "q3_recs": (qtr.eq(3) & complete).astype("int64"),
            "q4_recs": (qtr.eq(4) & complete).astype("int64"),
            "q4_rush_att": pd.Series(0, index=part.index, dtype="int64"),
            "total_rush_att": pd.Series(0, index=part.index, dtype="int64"),
            "q4_trail_targets": (qtr.eq(4) & score.lt(0)).astype("int64"),
            "q4_lead_rush_att": pd.Series(0, index=part.index, dtype="int64"),
        }
    else:
        zeros = pd.Series(0, index=part.index, dtype="int64")
        counts = {
            "q1_targets": zeros,
            "q2_targets": zeros,
            "q3_targets": zeros,
            "q4_targets": zeros,
            "total_targets": zeros,
            "q3_recs": zeros,
            "q4_recs": zeros,
            "q4_rush_att": qtr.eq(4).astype("int64"),
            "total_rush_att": pd.Series(1, index=part.index, dtype="int64"),
            "q4_trail_targets": zeros,
            "q4_lead_rush_att": (qtr.eq(4) & score.gt(0)).astype("int64"),
        }
    rows = pd.DataFrame(
        {
            "player_id": player_id.to_numpy(),
            "team": _team(part).to_numpy(),
            **{name: series.to_numpy() for name, series in counts.items()},
        }
    )
    return rows.loc[keep.to_numpy()].reset_index(drop=True)


def _team(plays: pd.DataFrame) -> pd.Series:
    if "posteam" not in plays.columns:
        return pd.Series("", index=plays.index)
    return plays["posteam"].map(canon_team).fillna("").astype(str)


def _num(plays: pd.DataFrame, column: str) -> pd.Series:
    if column not in plays.columns:
        return pd.Series(float("nan"), index=plays.index)
    return pd.to_numeric(plays[column], errors="coerce")


def _flag(plays: pd.DataFrame, column: str) -> pd.Series:
    if column not in plays.columns:
        return pd.Series(False, index=plays.index)
    return pd.to_numeric(plays[column], errors="coerce").fillna(0).eq(1)
