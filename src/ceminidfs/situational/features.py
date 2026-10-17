"""Point-in-time quarter, NGS, and FTN features.

``build_history_grains`` stores one row per player-week. ``tables_from_grains``
is the only reader that turns those rows into a feature table, and it calls
``cut_point_in_time`` first. A target week is not a feature of itself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ceminidfs.situational.contract import (
    canon_teams,
    COUNTING_COLUMNS,
    DEFENSE_COLUMNS,
    PLAYER_COLUMNS,
    FeatureTables,
    HistoryGrains,
)
from ceminidfs.situational.eb import empirical_bayes
from ceminidfs.situational.lag import cut_point_in_time

_POSITIONS = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE"}
_FTN_FLAGS = (
    "is_no_huddle",
    "is_play_action",
    "is_motion",
    "is_qb_fault_sack",
    "is_interception_worthy",
    "n_defense_box",
)


def build_point_in_time_tables(
    *,
    season: int,
    week: int,
    pbp: pd.DataFrame,
    ngs_passing: pd.DataFrame | None = None,
    ngs_rushing: pd.DataFrame | None = None,
    ngs_receiving: pd.DataFrame | None = None,
    ftn: pd.DataFrame | None = None,
) -> FeatureTables:
    """Build lagged player and defense tables for one target week."""

    grains = build_history_grains(
        pbp,
        ngs_passing=ngs_passing,
        ngs_rushing=ngs_rushing,
        ngs_receiving=ngs_receiving,
        ftn=ftn,
    )
    return tables_from_grains(grains, season=season, week=week)


def build_history_grains(
    pbp: pd.DataFrame | None,
    *,
    ngs_passing: pd.DataFrame | None = None,
    ngs_rushing: pd.DataFrame | None = None,
    ngs_receiving: pd.DataFrame | None = None,
    ftn: pd.DataFrame | None = None,
) -> HistoryGrains:
    """Aggregate every completed player-week. Do not use this frame as features."""

    prepared = _prepare_pbp(pbp)
    attached = _attach_ftn(prepared, ftn)
    return HistoryGrains(
        players=_player_grain(attached),
        offense=_offense_grain(attached),
        defense=_defense_grain(attached),
        ngs_receiving=_normalize_player_frame(ngs_receiving),
        ngs_passing=_normalize_player_frame(ngs_passing),
        ngs_rushing=_normalize_player_frame(ngs_rushing),
        slate_sizes=_slate_sizes(prepared),
    )


def tables_from_grains(grains: HistoryGrains, *, season: int, week: int) -> FeatureTables:
    """Collapse grains that are strictly before ``season``/``week``."""

    players_hist = cut_point_in_time(grains.players, season=season, week=week)
    offense_hist = cut_point_in_time(grains.offense, season=season, week=week)
    defense_hist = cut_point_in_time(grains.defense, season=season, week=week)
    receiving = cut_point_in_time(grains.ngs_receiving, season=season, week=week)
    passing = cut_point_in_time(grains.ngs_passing, season=season, week=week)
    rushing = cut_point_in_time(grains.ngs_rushing, season=season, week=week)

    players = _collapse_players(players_hist)
    players = _attach_team_context(players, _collapse_offense(offense_hist))
    players = _attach_ngs(players, receiving, passing, rushing)
    players = _shrink_rates(players)
    players = _reindex_columns(players, PLAYER_COLUMNS)
    defense = _reindex_columns(_collapse_defense(defense_hist), DEFENSE_COLUMNS)
    audit = _audit(
        season=season,
        week=week,
        players_hist=players_hist,
        defense_hist=defense_hist,
        receiving=receiving,
        passing=passing,
        rushing=rushing,
        players=players,
        defense=defense,
    )
    return FeatureTables(players=players, defense=defense, audit=audit)


def _prepare_pbp(pbp: pd.DataFrame | None) -> pd.DataFrame:
    if pbp is None or len(pbp) == 0:
        return pd.DataFrame()
    frame = pbp.copy()
    frame["season"] = pd.to_numeric(frame.get("season"), errors="coerce")
    frame["week"] = pd.to_numeric(frame.get("week"), errors="coerce")
    frame = frame.loc[frame["season"].notna() & frame["week"].notna() & (frame["week"] > 0)].copy()
    if frame.empty:
        return frame
    for column in ("posteam", "defteam", "home_team", "away_team"):
        if column in frame.columns:
            frame[column] = canon_teams(frame[column])
    if "play_type" in frame.columns:
        frame = frame.loc[frame["play_type"].isin(["pass", "run"])].copy()
    if "play_id" not in frame.columns:
        frame["play_id"] = np.arange(len(frame))
    return frame


def _slate_sizes(pbp: pd.DataFrame) -> pd.DataFrame:
    if pbp.empty or "game_id" not in pbp.columns:
        return pd.DataFrame(columns=["season", "week", "games"])
    sizes = (
        pbp.groupby(["season", "week"], as_index=False)["game_id"]
        .nunique()
        .rename(columns={"game_id": "games"})
    )
    return sizes.sort_values(["season", "week"], kind="mergesort").reset_index(drop=True)


def _attach_ftn(pbp: pd.DataFrame, ftn: pd.DataFrame | None) -> pd.DataFrame:
    if pbp.empty or ftn is None or len(ftn) == 0:
        return pbp
    if "nflverse_game_id" not in ftn.columns or "nflverse_play_id" not in ftn.columns:
        return pbp
    flags = [column for column in _FTN_FLAGS if column in ftn.columns]
    if not flags or "game_id" not in pbp.columns or "play_id" not in pbp.columns:
        return pbp
    slim = ftn[["nflverse_game_id", "nflverse_play_id", *flags]].drop_duplicates(
        ["nflverse_game_id", "nflverse_play_id"]
    )
    return pbp.merge(
        slim,
        left_on=["game_id", "play_id"],
        right_on=["nflverse_game_id", "nflverse_play_id"],
        how="left",
    )


def _player_grain(pbp: pd.DataFrame) -> pd.DataFrame:
    if pbp.empty:
        return _empty_player_grain()
    parts = [
        _receiver_rows(pbp),
        _rusher_rows(pbp),
        _passer_rows(pbp),
        _fumble_rows(pbp),
    ]
    parts = [part for part in parts if not part.empty]
    if not parts:
        return _empty_player_grain()
    long = pd.concat(parts, ignore_index=True)
    for column in COUNTING_COLUMNS:
        if column == "games":
            continue
        if column not in long.columns:
            long[column] = 0.0
        long[column] = pd.to_numeric(long[column], errors="coerce").fillna(0.0)
    keys = ["player_id", "season", "week"]
    summed = long.groupby(keys, as_index=False)[list(COUNTING_COLUMNS[:-1])].sum()
    long = long.sort_values(["season", "week", "play_id"], kind="mergesort")
    latest = long.groupby(keys, as_index=False).tail(1)[keys + ["player_name", "team", "opp"]]
    games = (
        long.groupby(keys, as_index=False)["game_id"]
        .nunique()
        .rename(columns={"game_id": "games"})
    )
    grain = summed.merge(latest, on=keys, how="left").merge(games, on=keys, how="left")
    grain["games"] = pd.to_numeric(grain["games"], errors="coerce").fillna(0.0)
    return grain


def _receiver_rows(pbp: pd.DataFrame) -> pd.DataFrame:
    if "receiver_player_id" not in pbp.columns:
        return pd.DataFrame()
    mask = _flag(pbp, "pass").eq(1) & pbp["receiver_player_id"].notna()
    plays = pbp.loc[mask]
    if plays.empty:
        return pd.DataFrame()
    complete = _flag(plays, "complete_pass").eq(1)
    qtr = _num(plays, "qtr")
    yard = _num(plays, "yardline_100")
    yards = _num(plays, "yards_gained").fillna(0.0)
    trailing_q4 = qtr.eq(4) & _num(plays, "score_differential").lt(0)
    play_action = _coalesce_flag(plays, "is_play_action", "")
    motion = _coalesce_flag(plays, "is_motion", "")
    rows = _base_rows(plays, "receiver_player_id", "receiver_player_name")
    rows["targets"] = 1.0
    rows["receptions"] = complete.astype(float).to_numpy()
    rows["rec_yds"] = np.where(complete.to_numpy(), yards.to_numpy(), 0.0)
    rows["rec_td"] = _flag(plays, "pass_touchdown").eq(1).astype(float).to_numpy()
    rows["q3_rec_td"] = np.where(qtr.eq(3).to_numpy(), rows["rec_td"], 0.0)
    rows["rz_targets"] = yard.le(20).astype(float).to_numpy()
    rows["q3_rz_targets"] = (qtr.eq(3) & yard.le(20)).astype(float).to_numpy()
    rows["q4_trail_targets"] = trailing_q4.astype(float).to_numpy()
    rows["explosive_recs"] = (complete & yards.ge(20)).astype(float).to_numpy()
    rows["inside10_targets"] = yard.le(10).astype(float).to_numpy()
    rows["pa_known"] = play_action.notna().astype(float).to_numpy()
    rows["pa_sum"] = play_action.fillna(0.0).to_numpy()
    rows["motion_known"] = motion.notna().astype(float).to_numpy()
    rows["motion_sum"] = motion.fillna(0.0).to_numpy()
    return rows


def _rusher_rows(pbp: pd.DataFrame) -> pd.DataFrame:
    if "rusher_player_id" not in pbp.columns:
        return pd.DataFrame()
    mask = _flag(pbp, "rush").eq(1) & pbp["rusher_player_id"].notna()
    plays = pbp.loc[mask]
    if plays.empty:
        return pd.DataFrame()
    qtr = _num(plays, "qtr")
    yard = _num(plays, "yardline_100")
    yards = _num(plays, "yards_gained").fillna(0.0)
    trailing_q4 = qtr.eq(4) & _num(plays, "score_differential").lt(0)
    rows = _base_rows(plays, "rusher_player_id", "rusher_player_name")
    rows["carries"] = 1.0
    rows["rush_yds"] = yards.to_numpy()
    rows["rush_td"] = _flag(plays, "rush_touchdown").eq(1).astype(float).to_numpy()
    rows["q3_rush_td"] = np.where(qtr.eq(3).to_numpy(), rows["rush_td"], 0.0)
    rows["rz_carries"] = yard.le(20).astype(float).to_numpy()
    rows["q3_rz_carries"] = (qtr.eq(3) & yard.le(20)).astype(float).to_numpy()
    rows["q4_trail_carries"] = trailing_q4.astype(float).to_numpy()
    rows["explosive_rushes"] = yards.ge(15).astype(float).to_numpy()
    rows["inside5_carries"] = yard.le(5).astype(float).to_numpy()
    return rows


def _passer_rows(pbp: pd.DataFrame) -> pd.DataFrame:
    if "passer_player_id" not in pbp.columns:
        return pd.DataFrame()
    mask = _flag(pbp, "pass").eq(1) & pbp["passer_player_id"].notna()
    plays = pbp.loc[mask]
    if plays.empty:
        return pd.DataFrame()
    qtr = _num(plays, "qtr")
    yards = _num(plays, "yards_gained").fillna(0.0)
    fault = _coalesce_flag(plays, "is_qb_fault_sack", "")
    worthy = _coalesce_flag(plays, "is_interception_worthy", "")
    sack = _flag(plays, "sack").eq(1)
    rows = _base_rows(plays, "passer_player_id", "passer_player_name")
    # A sack is not a FanDuel pass attempt.
    rows["pass_att"] = np.where(sack.to_numpy(), 0.0, 1.0)
    # Sack yards are not FanDuel passing yards.
    rows["pass_yds"] = np.where(sack.to_numpy(), 0.0, np.maximum(yards.to_numpy(), 0.0))
    rows["pass_td"] = _flag(plays, "pass_touchdown").eq(1).astype(float).to_numpy()
    rows["q3_pass_td"] = np.where(qtr.eq(3).to_numpy(), rows["pass_td"], 0.0)
    rows["interceptions"] = _flag(plays, "interception").eq(1).astype(float).to_numpy()
    rows["sacks_taken"] = sack.astype(float).to_numpy()
    rows["qb_fault_known"] = (sack & fault.notna()).astype(float).to_numpy()
    rows["qb_fault_sum"] = np.where(sack.to_numpy(), fault.fillna(0.0).to_numpy(), 0.0)
    rows["int_worthy_known"] = worthy.notna().astype(float).to_numpy()
    rows["int_worthy_sum"] = worthy.fillna(0.0).to_numpy()
    return rows


def _fumble_rows(pbp: pd.DataFrame) -> pd.DataFrame:
    if "fumbled_1_player_id" not in pbp.columns:
        return pd.DataFrame()
    mask = _flag(pbp, "fumble_lost").eq(1) & pbp["fumbled_1_player_id"].notna()
    plays = pbp.loc[mask]
    if plays.empty:
        return pd.DataFrame()
    rows = _base_rows(plays, "fumbled_1_player_id", "fumbled_1_player_name")
    rows["fumbles_lost"] = 1.0
    return rows


def _base_rows(plays: pd.DataFrame, id_col: str, name_col: str) -> pd.DataFrame:
    names = plays[name_col] if name_col in plays.columns else ""
    return pd.DataFrame(
        {
            "player_id": plays[id_col].astype(str).to_numpy(),
            "player_name": pd.Series(names, index=plays.index).astype(str).to_numpy(),
            "team": plays.get("posteam", pd.Series("", index=plays.index)).astype(str).to_numpy(),
            "season": _num(plays, "season").to_numpy(),
            "week": _num(plays, "week").to_numpy(),
            "game_id": plays.get("game_id", pd.Series("", index=plays.index)).astype(str).to_numpy(),
            "play_id": _num(plays, "play_id").to_numpy(),
            "opp": plays["defteam"].astype(str).to_numpy() if "defteam" in plays.columns else "",
        }
    )


def _offense_grain(pbp: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "team",
        "season",
        "week",
        "q3_open_epa_sum",
        "q3_open_plays",
        "q3_open_proe_sum",
        "q3_open_proe_plays",
        "rz_drives",
        "rz_td_drives",
        "between_epa_sum",
        "between_plays",
        "q4_trail_pass",
        "pass_att",
        "no_huddle_sum",
        "no_huddle_known",
    ]
    if pbp.empty or "posteam" not in pbp.columns:
        return pd.DataFrame(columns=columns)
    frame = pbp.loc[pbp["posteam"].notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    records = []
    records.append(_opening_drive(frame))
    records.append(_between_20(frame))
    records.append(_pass_script(frame))
    records.append(_red_zone_drives(frame, team_col="posteam"))
    merged = _merge_team_parts(records, columns)
    return merged


def _defense_grain(pbp: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "team",
        "season",
        "week",
        "plays",
        "q3_epa_sum",
        "q3_plays",
        "h1_epa_sum",
        "h1_plays",
        "q4_drop_epa_sum",
        "q4_drop_plays",
        "q4_yac_sum",
        "q4_yac_plays",
        "explosive_comps",
        "dropbacks",
        "q4_comps",
        "q4_dropbacks",
        "light_box_sum",
        "light_box_known",
        "rz_drives",
        "rz_td_drives",
        "sacks",
        "interceptions",
        "fumbles",
        "dst_td",
        "safeties",
        "points_allowed",
    ]
    if pbp.empty or "defteam" not in pbp.columns:
        return pd.DataFrame(columns=columns)
    frame = pbp.loc[pbp["defteam"].notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    qtr = _num(frame, "qtr")
    epa = _num(frame, "epa")
    drop = _flag(frame, "qb_dropback").eq(1) | _flag(frame, "pass").eq(1)
    complete = _flag(frame, "complete_pass").eq(1)
    yards = _num(frame, "yards_gained")
    yac = _num(frame, "yards_after_catch")
    box = _num(frame, "n_defense_box") if "n_defense_box" in frame.columns else pd.Series(np.nan, index=frame.index)
    work = pd.DataFrame(
        {
            "team": frame["defteam"].astype(str).to_numpy(),
            "season": _num(frame, "season").to_numpy(),
            "week": _num(frame, "week").to_numpy(),
            "plays": 1.0,
            "q3_epa_sum": np.where(qtr.eq(3).to_numpy(), epa.fillna(0.0).to_numpy(), 0.0),
            "q3_plays": qtr.eq(3).astype(float).to_numpy(),
            "h1_epa_sum": np.where(qtr.isin([1, 2]).to_numpy(), epa.fillna(0.0).to_numpy(), 0.0),
            "h1_plays": qtr.isin([1, 2]).astype(float).to_numpy(),
            "q4_drop_epa_sum": np.where((qtr.eq(4) & drop).to_numpy(), epa.fillna(0.0).to_numpy(), 0.0),
            "q4_drop_plays": (qtr.eq(4) & drop).astype(float).to_numpy(),
            "q4_yac_sum": np.where((qtr.eq(4) & complete).to_numpy(), yac.fillna(0.0).to_numpy(), 0.0),
            "q4_yac_plays": (qtr.eq(4) & complete & yac.notna()).astype(float).to_numpy(),
            "explosive_comps": (complete & yards.ge(20)).astype(float).to_numpy(),
            "dropbacks": drop.astype(float).to_numpy(),
            "q4_comps": (qtr.eq(4) & complete).astype(float).to_numpy(),
            "q4_dropbacks": (qtr.eq(4) & drop).astype(float).to_numpy(),
            "light_box_sum": np.where(box.notna().to_numpy(), box.le(6).astype(float).to_numpy(), 0.0),
            "light_box_known": box.notna().astype(float).to_numpy(),
            "sacks": _flag(frame, "sack").eq(1).astype(float).to_numpy(),
            "interceptions": _flag(frame, "interception").eq(1).astype(float).to_numpy(),
            "fumbles": _flag(frame, "fumble_lost").eq(1).astype(float).to_numpy(),
            "dst_td": _defense_td(frame).to_numpy(),
            "safeties": _flag(frame, "safety").eq(1).astype(float).to_numpy(),
        }
    )
    summed = work.groupby(["team", "season", "week"], as_index=False).sum(numeric_only=True)
    rz = _red_zone_drives(frame, team_col="defteam")
    if not rz.empty:
        summed = summed.merge(rz, on=["team", "season", "week"], how="left")
    else:
        summed["rz_drives"] = 0.0
        summed["rz_td_drives"] = 0.0
    scores = _points_allowed(pbp)
    if not scores.empty:
        summed = summed.merge(scores, on=["team", "season", "week"], how="left")
    else:
        summed["points_allowed"] = np.nan
    for column in columns:
        if column not in summed.columns:
            summed[column] = np.nan if column == "points_allowed" else 0.0
    return summed[columns]


def _opening_drive(frame: pd.DataFrame) -> pd.DataFrame:
    empty = pd.DataFrame(
        columns=[
            "team",
            "season",
            "week",
            "q3_open_epa_sum",
            "q3_open_plays",
            "q3_open_proe_sum",
            "q3_open_proe_plays",
        ]
    )
    if "drive_quarter_start" not in frame.columns or "fixed_drive" not in frame.columns:
        return empty
    opens = frame.loc[_num(frame, "drive_quarter_start").eq(3) & frame["fixed_drive"].notna()].copy()
    if opens.empty:
        return empty
    idx = opens.groupby(["season", "week", "game_id", "posteam"])["play_id"].idxmin()
    first = opens.loc[idx, ["season", "week", "game_id", "posteam", "fixed_drive"]]
    marked = opens.merge(first, on=["season", "week", "game_id", "posteam", "fixed_drive"], how="inner")
    marked["team"] = marked["posteam"].astype(str)
    marked["epa_value"] = _num(marked, "epa")
    marked["proe_value"] = _num(marked, "pass_oe")
    marked["proe_known"] = marked["proe_value"].notna().astype(float)
    marked["proe_filled"] = marked["proe_value"].fillna(0.0)
    return (
        marked.groupby(["team", "season", "week"], as_index=False)
        .agg(
            q3_open_epa_sum=("epa_value", "sum"),
            q3_open_plays=("epa_value", "size"),
            q3_open_proe_sum=("proe_filled", "sum"),
            q3_open_proe_plays=("proe_known", "sum"),
        )
    )


def _between_20(frame: pd.DataFrame) -> pd.DataFrame:
    yard = _num(frame, "yardline_100")
    part = frame.loc[yard.gt(20) & yard.lt(80)].copy()
    if part.empty:
        return pd.DataFrame(columns=["team", "season", "week", "between_epa_sum", "between_plays"])
    part["team"] = part["posteam"].astype(str)
    part["epa_value"] = _num(part, "epa")
    return part.groupby(["team", "season", "week"], as_index=False).agg(
        between_epa_sum=("epa_value", "sum"),
        between_plays=("epa_value", "size"),
    )


def _pass_script(frame: pd.DataFrame) -> pd.DataFrame:
    passes = frame.loc[_flag(frame, "pass").eq(1)].copy()
    if passes.empty:
        return pd.DataFrame(
            columns=["team", "season", "week", "q4_trail_pass", "pass_att", "no_huddle_sum", "no_huddle_known"]
        )
    qtr = _num(passes, "qtr")
    trail = qtr.eq(4) & _num(passes, "score_differential").lt(0)
    huddle = _coalesce_flag(passes, "is_no_huddle", "no_huddle")
    passes["team"] = passes["posteam"].astype(str)
    sack = _flag(passes, "sack").eq(1)
    passes["q4_trail_pass"] = trail.astype(float).to_numpy()
    passes["pass_att"] = (~sack).astype(float).to_numpy()
    passes["no_huddle_sum"] = huddle.fillna(0.0).to_numpy()
    passes["no_huddle_known"] = huddle.notna().astype(float).to_numpy()
    return passes.groupby(["team", "season", "week"], as_index=False)[
        ["q4_trail_pass", "pass_att", "no_huddle_sum", "no_huddle_known"]
    ].sum()


def _red_zone_drives(frame: pd.DataFrame, *, team_col: str) -> pd.DataFrame:
    empty = pd.DataFrame(columns=["team", "season", "week", "rz_drives", "rz_td_drives"])
    if "drive_inside20" not in frame.columns or "fixed_drive" not in frame.columns:
        return empty
    inside = frame.loc[_flag(frame, "drive_inside20").eq(1) & frame[team_col].notna()].copy()
    if inside.empty:
        return empty
    grouped = inside.groupby(["season", "week", "game_id", team_col, "fixed_drive"], as_index=False).agg(
        pass_td=("pass_touchdown", "max") if "pass_touchdown" in inside.columns else ("play_id", "size"),
        rush_td=("rush_touchdown", "max") if "rush_touchdown" in inside.columns else ("play_id", "size"),
    )
    if "pass_touchdown" not in inside.columns:
        grouped["pass_td"] = 0.0
    if "rush_touchdown" not in inside.columns:
        grouped["rush_td"] = 0.0
    grouped["td"] = (pd.to_numeric(grouped["pass_td"], errors="coerce").fillna(0.0) > 0) | (
        pd.to_numeric(grouped["rush_td"], errors="coerce").fillna(0.0) > 0
    )
    grouped["team"] = grouped[team_col].astype(str)
    out = grouped.groupby(["team", "season", "week"], as_index=False).agg(
        rz_drives=("td", "size"),
        rz_td_drives=("td", "sum"),
    )
    out["rz_td_drives"] = out["rz_td_drives"].astype(float)
    return out


def _points_allowed(pbp: pd.DataFrame) -> pd.DataFrame:
    needed = {"home_team", "away_team", "home_score", "away_score", "season", "week"}
    if not needed.issubset(pbp.columns):
        return pd.DataFrame(columns=["team", "season", "week", "points_allowed"])
    games = pbp.groupby(["season", "week", "game_id"], as_index=False).agg(
        home_team=("home_team", "first"),
        away_team=("away_team", "first"),
        home_score=("home_score", "max"),
        away_score=("away_score", "max"),
    )
    home = pd.DataFrame(
        {
            "team": games["home_team"].astype(str),
            "season": games["season"],
            "week": games["week"],
            "points_allowed": pd.to_numeric(games["away_score"], errors="coerce"),
        }
    )
    away = pd.DataFrame(
        {
            "team": games["away_team"].astype(str),
            "season": games["season"],
            "week": games["week"],
            "points_allowed": pd.to_numeric(games["home_score"], errors="coerce"),
        }
    )
    return pd.concat([home, away], ignore_index=True)


def _defense_td(frame: pd.DataFrame) -> pd.Series:
    returned = _flag(frame, "return_touchdown").eq(1)
    if "td_team" not in frame.columns or "defteam" not in frame.columns:
        return returned.astype(float)
    same = frame["td_team"].astype(str) == frame["defteam"].astype(str)
    return (returned & same).astype(float)


def _merge_team_parts(parts: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    usable = [part for part in parts if part is not None and not part.empty]
    if not usable:
        return pd.DataFrame(columns=columns)
    merged = usable[0]
    for part in usable[1:]:
        merged = merged.merge(part, on=["team", "season", "week"], how="outer")
    for column in columns:
        if column not in merged.columns:
            merged[column] = 0.0
    return merged[columns]


def _collapse_players(hist: pd.DataFrame) -> pd.DataFrame:
    if hist.empty:
        return _reindex_columns(pd.DataFrame(), PLAYER_COLUMNS)
    hist = hist.copy()
    hist["_fd"] = _weekly_skill_points(hist)
    fd_sum = hist.groupby("player_id")["_fd"].sum()
    trail4 = _trail4_opps(hist)
    sum_cols = [column for column in COUNTING_COLUMNS if column != "games" and column in hist.columns]
    totals = hist.groupby("player_id", as_index=False)[sum_cols].sum()
    games = hist.groupby("player_id", as_index=False)["games"].sum()
    latest = (
        hist.sort_values(["season", "week"], kind="mergesort")
        .groupby("player_id", as_index=False)
        .tail(1)[["player_id", "player_name", "team"]]
    )
    totals = totals.merge(games, on="player_id", how="left").merge(latest, on="player_id", how="left")
    games_n = totals["games"].clip(lower=0.0)
    safe_games = games_n.where(games_n > 0, np.nan)

    def per(column: str) -> pd.Series:
        return totals.get(column, 0.0) / safe_games

    td = _series(totals, "rec_td") + _series(totals, "rush_td") + _series(totals, "pass_td")
    q3_td = _series(totals, "q3_rec_td") + _series(totals, "q3_rush_td") + _series(totals, "q3_pass_td")
    rz = _series(totals, "rz_targets") + _series(totals, "rz_carries")
    q3_rz = _series(totals, "q3_rz_targets") + _series(totals, "q3_rz_carries")
    out = pd.DataFrame(
        {
            "player_id": totals["player_id"],
            "player_name": totals["player_name"],
            "team": totals["team"],
            "games": games_n,
            "pass_yds_per_game": per("pass_yds"),
            "rush_yds_per_game": per("rush_yds"),
            "rec_yds_per_game": per("rec_yds"),
            "targets_per_game": per("targets"),
            "carries_per_game": per("carries"),
            "receptions_per_game": per("receptions"),
            "pass_att_per_game": per("pass_att"),
            "pass_td_per_game": per("pass_td"),
            "rush_td_per_game": per("rush_td"),
            "rec_td_per_game": per("rec_td"),
            "int_per_game": per("interceptions"),
            "fumbles_per_game": per("fumbles_lost"),
            "q3_td_share": _ratio(q3_td, td),
            "q3_rz_touch_share": _ratio(q3_rz, rz),
            "q4_trail_target_share": _ratio(_series(totals, "q4_trail_targets"), _series(totals, "targets")),
            "q4_trail_carry_share": _ratio(_series(totals, "q4_trail_carries"), _series(totals, "carries")),
            "explosive_rec_rate": _ratio(_series(totals, "explosive_recs"), _series(totals, "targets")),
            "explosive_rush_rate": _ratio(_series(totals, "explosive_rushes"), _series(totals, "carries")),
            "inside10_target_share": _ratio(_series(totals, "inside10_targets"), _series(totals, "targets")),
            "inside5_carry_share": _ratio(_series(totals, "inside5_carries"), _series(totals, "carries")),
            "play_action_target_share": _ratio(_series(totals, "pa_sum"), _series(totals, "pa_known"), missing=True),
            "motion_target_share": _ratio(_series(totals, "motion_sum"), _series(totals, "motion_known"), missing=True),
            "qb_fault_sack_rate": _ratio(
                _series(totals, "qb_fault_sum"), _series(totals, "qb_fault_known"), missing=True
            ),
            "int_worthy_rate": _ratio(
                _series(totals, "int_worthy_sum"), _series(totals, "int_worthy_known"), missing=True
            ),
            "eb_q3_td": q3_td,
            "eb_td": td,
            "eb_q3_rz": q3_rz,
            "eb_rz": rz,
            "eb_q4_tgt": _series(totals, "q4_trail_targets"),
            "eb_tgt": _series(totals, "targets"),
            "eb_q4_car": _series(totals, "q4_trail_carries"),
            "eb_car": _series(totals, "carries"),
            "eb_expl_rec": _series(totals, "explosive_recs"),
            "eb_expl_rush": _series(totals, "explosive_rushes"),
            "eb_in10": _series(totals, "inside10_targets"),
            "eb_in5": _series(totals, "inside5_carries"),
            "eb_pa_sum": _series(totals, "pa_sum"),
            "eb_pa_known": _series(totals, "pa_known"),
            "eb_mo_sum": _series(totals, "motion_sum"),
            "eb_mo_known": _series(totals, "motion_known"),
            "eb_fault_sum": _series(totals, "qb_fault_sum"),
            "eb_fault_known": _series(totals, "qb_fault_known"),
            "eb_int_sum": _series(totals, "int_worthy_sum"),
            "eb_int_known": _series(totals, "int_worthy_known"),
        }
    )
    out["position"] = [
        _infer_position(att, targets, carries)
        for att, targets, carries in zip(
            _series(totals, "pass_att"),
            _series(totals, "targets"),
            _series(totals, "carries"),
            strict=True,
        )
    ]
    games_safe = out["games"].where(out["games"] > 0)
    out["fd_points_per_game"] = out["player_id"].map(fd_sum) / games_safe
    out["trail4_opps"] = out["player_id"].map(trail4).fillna(0.0)
    return out


def _collapse_offense(hist: pd.DataFrame) -> pd.DataFrame:
    if hist.empty:
        return pd.DataFrame(columns=["team", "team_q3_opening_epa", "team_q3_opening_proe", "team_rz_td_rate", "team_between_20_epa", "team_q4_trail_pass_share", "team_no_huddle_rate"])
    totals = hist.groupby("team", as_index=False).sum(numeric_only=True)
    return pd.DataFrame(
        {
            "team": totals["team"],
            "team_q3_opening_epa": _ratio(
                _series(totals, "q3_open_epa_sum"), _series(totals, "q3_open_plays"), missing=True
            ),
            "team_q3_opening_proe": _ratio(
                _series(totals, "q3_open_proe_sum"),
                _series(totals, "q3_open_proe_plays"),
                missing=True,
            ),
            "team_rz_td_rate": _ratio(_series(totals, "rz_td_drives"), _series(totals, "rz_drives"), missing=True),
            "team_between_20_epa": _ratio(
                _series(totals, "between_epa_sum"), _series(totals, "between_plays"), missing=True
            ),
            "team_q4_trail_pass_share": _ratio(
                _series(totals, "q4_trail_pass"), _series(totals, "pass_att"), missing=True
            ),
            "team_no_huddle_rate": _ratio(
                _series(totals, "no_huddle_sum"), _series(totals, "no_huddle_known"), missing=True
            ),
        }
    )


def _collapse_defense(hist: pd.DataFrame) -> pd.DataFrame:
    if hist.empty:
        return _reindex_columns(pd.DataFrame(), DEFENSE_COLUMNS)
    totals = hist.groupby("team", as_index=False).sum(numeric_only=True)
    q3 = _ratio(_series(totals, "q3_epa_sum"), _series(totals, "q3_plays"), missing=True)
    first_half = _ratio(_series(totals, "h1_epa_sum"), _series(totals, "h1_plays"), missing=True)
    return pd.DataFrame(
        {
            "team": totals["team"],
            "plays": _series(totals, "plays"),
            "def_q3_epa": q3,
            "def_1h_epa": first_half,
            "def_q3_slow_start": q3 - first_half,
            "def_q4_dropback_epa": _ratio(
                _series(totals, "q4_drop_epa_sum"), _series(totals, "q4_drop_plays"), missing=True
            ),
            "def_q4_yac": _ratio(_series(totals, "q4_yac_sum"), _series(totals, "q4_yac_plays"), missing=True),
            "def_explosive_comp_rate": _ratio(
                _series(totals, "explosive_comps"), _series(totals, "dropbacks"), missing=True
            ),
            "def_q4_comp_rate": _ratio(
                _series(totals, "q4_comps"), _series(totals, "q4_dropbacks"), missing=True
            ),
            "def_light_box_rate": _ratio(
                _series(totals, "light_box_sum"), _series(totals, "light_box_known"), missing=True
            ),
            "def_rz_td_rate": _ratio(_series(totals, "rz_td_drives"), _series(totals, "rz_drives"), missing=True),
            "def_sack_rate": _ratio(_series(totals, "sacks"), _series(totals, "dropbacks"), missing=True),
            "def_to_rate": _ratio(
                _series(totals, "interceptions") + _series(totals, "fumbles"),
                _series(totals, "plays"),
                missing=True,
            ),
            "lagged_fd": totals["team"].map(_defense_lagged_fd(hist)),
        }
    )


def _attach_team_context(players: pd.DataFrame, offense: pd.DataFrame) -> pd.DataFrame:
    if players.empty:
        return players
    if offense.empty:
        for column in (
            "team_q3_opening_epa",
            "team_q3_opening_proe",
            "team_rz_td_rate",
            "team_between_20_epa",
            "team_q4_trail_pass_share",
            "team_no_huddle_rate",
        ):
            players[column] = np.nan
        return players
    return players.merge(offense, on="team", how="left")


def _attach_ngs(
    players: pd.DataFrame,
    receiving: pd.DataFrame,
    passing: pd.DataFrame,
    rushing: pd.DataFrame,
) -> pd.DataFrame:
    if players.empty:
        return players
    players = _merge_ngs_means(
        players,
        receiving,
        {
            "avg_cushion": "avg_cushion",
            "avg_separation": "avg_separation",
            "avg_intended_air_yards": "rec_air_yards",
            "percent_share_of_intended_air_yards": "air_yards_share",
            "avg_yac_above_expectation": "avg_yac_above_expectation",
            "player_position": "ngs_position",
            "player_name": "ngs_name",
        },
    )
    players = _merge_ngs_means(
        players,
        passing,
        {
            "completion_percentage_above_expectation": "cpoe",
            "avg_time_to_throw": "avg_time_to_throw",
            "avg_intended_air_yards": "pass_air_yards",
            "player_position": "pass_position",
            "player_name": "pass_name",
        },
    )
    players = _merge_ngs_means(
        players,
        rushing,
        {
            "rush_yards_over_expected_per_att": "ryoe",
            "player_position": "rush_position",
            "player_name": "rush_name",
        },
    )
    if "rec_air_yards" in players.columns:
        air_yards = players["rec_air_yards"]
    else:
        air_yards = pd.Series(np.nan, index=players.index)
    players["avg_intended_air_yards"] = air_yards
    if "pass_air_yards" in players.columns:
        players["avg_intended_air_yards"] = players["avg_intended_air_yards"].where(
            players["avg_intended_air_yards"].notna(),
            players["pass_air_yards"],
        )
    position = players.get("ngs_position", pd.Series(np.nan, index=players.index))
    for column in ("rush_position", "pass_position"):
        if column in players.columns:
            position = position.where(position.notna(), players[column])
    mapped = position.map(lambda value: _POSITIONS.get(str(value).upper(), np.nan) if pd.notna(value) else np.nan)
    players["position"] = mapped.where(mapped.notna(), players["position"])
    for column in ("ngs_name", "pass_name", "rush_name"):
        if column not in players.columns:
            continue
        short = players["player_name"].astype(str).str.contains(r"\.", regex=True) | players["player_name"].eq("nan")
        players.loc[short & players[column].notna(), "player_name"] = players.loc[
            short & players[column].notna(), column
        ]
    return players


def _merge_ngs_means(players: pd.DataFrame, ngs: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    present = {source: target for source, target in columns.items() if source in ngs.columns}
    if ngs.empty or "player_id" not in ngs.columns or not present:
        for target in columns.values():
            if target not in players.columns:
                players[target] = np.nan
        return players
    work = ngs.copy()
    work["player_id"] = work["player_id"].astype(str)
    value_cols = [source for source in present if source not in {"player_position", "player_name"}]
    means = work.groupby("player_id", as_index=False)[value_cols].mean() if value_cols else work[["player_id"]].drop_duplicates()
    latest_cols = [source for source in ("player_position", "player_name") if source in present]
    if latest_cols and "week" in work.columns:
        latest = (
            work.sort_values(["season", "week"], kind="mergesort")
            .groupby("player_id", as_index=False)
            .tail(1)[["player_id", *latest_cols]]
        )
        means = means.merge(latest, on="player_id", how="left")
    means = means.rename(columns=present)
    means["player_id"] = means["player_id"].astype(str)
    players = players.copy()
    players["player_id"] = players["player_id"].astype(str)
    return players.merge(means, on="player_id", how="left")


def _infer_position(attempts: float, targets: float, carries: float) -> str:
    attempts = 0.0 if pd.isna(attempts) else float(attempts)
    targets = 0.0 if pd.isna(targets) else float(targets)
    carries = 0.0 if pd.isna(carries) else float(carries)
    if attempts >= 10 and attempts >= targets and attempts >= carries:
        return "QB"
    if carries > targets and carries > 0 and carries >= attempts:
        return "RB"
    if targets > 0 and targets >= carries:
        return "WR"
    if carries > 0:
        return "RB"
    if attempts > 0:
        return "QB"
    return "UNK"


def _audit(**parts: object) -> dict:
    players_hist = parts["players_hist"]
    defense_hist = parts["defense_hist"]
    season = int(parts["season"])
    week = int(parts["week"])

    def max_same(frame: pd.DataFrame) -> float | None:
        if frame is None or len(frame) == 0 or "season" not in frame.columns:
            return None
        seasons = pd.to_numeric(frame["season"], errors="coerce")
        weeks = pd.to_numeric(frame["week"], errors="coerce")
        same = weeks[seasons == season]
        if same.empty:
            return None
        return float(same.max())

    peak = _peak_week(max_same(players_hist), max_same(defense_hist))
    return {
        "target_season": season,
        "target_week": week,
        "player_week_rows": int(len(players_hist)),
        "defense_week_rows": int(len(defense_hist)),
        "ngs_receiving_rows": int(len(parts["receiving"])),
        "ngs_passing_rows": int(len(parts["passing"])),
        "ngs_rushing_rows": int(len(parts["rushing"])),
        "player_rows": int(len(parts["players"])),
        "defense_rows": int(len(parts["defense"])),
        "max_week_same_season": peak,
        "lookahead_ok": peak is None or peak < week,
    }


def _peak_week(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    if not values:
        return None
    return max(values)


def _normalize_player_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or len(frame) == 0:
        return pd.DataFrame()
    out = frame.copy()
    if "player_id" not in out.columns and "player_gsis_id" in out.columns:
        out = out.rename(columns={"player_gsis_id": "player_id"})
    if "player_name" not in out.columns and "player_display_name" in out.columns:
        out = out.rename(columns={"player_display_name": "player_name"})
    return out


def _empty_player_grain() -> pd.DataFrame:
    columns = ["player_id", "player_name", "team", "opp", "season", "week", "game_id", "play_id", *COUNTING_COLUMNS]
    return pd.DataFrame(columns=columns)


def _reindex_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = pd.Series(dtype=object if column in {"player_id", "player_name", "team", "position"} else float)
    return out.loc[:, list(columns)].reset_index(drop=True)


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _shrink_rates(players: pd.DataFrame) -> pd.DataFrame:
    """Shrink rate features toward the positional mean. Prior strength is 15 trials."""

    if players.empty or "position" not in players.columns:
        return players
    out = players.copy()
    position = out["position"].astype(str)
    specs = (
        ("q3_td_share", "eb_q3_td", "eb_td", False),
        ("q3_rz_touch_share", "eb_q3_rz", "eb_rz", False),
        ("q4_trail_target_share", "eb_q4_tgt", "eb_tgt", False),
        ("q4_trail_carry_share", "eb_q4_car", "eb_car", False),
        ("explosive_rec_rate", "eb_expl_rec", "eb_tgt", False),
        ("explosive_rush_rate", "eb_expl_rush", "eb_car", False),
        ("inside10_target_share", "eb_in10", "eb_tgt", False),
        ("inside5_carry_share", "eb_in5", "eb_car", False),
        ("play_action_target_share", "eb_pa_sum", "eb_pa_known", True),
        ("motion_target_share", "eb_mo_sum", "eb_mo_known", True),
        ("qb_fault_sack_rate", "eb_fault_sum", "eb_fault_known", True),
        ("int_worthy_rate", "eb_int_sum", "eb_int_known", True),
    )
    for name, numer_col, denom_col, missing in specs:
        if numer_col not in out.columns or denom_col not in out.columns:
            continue
        numer = pd.to_numeric(out[numer_col], errors="coerce").fillna(0.0)
        denom = pd.to_numeric(out[denom_col], errors="coerce").fillna(0.0)
        prior = _positional_prior(numer, denom, position)
        shrunk = empirical_bayes(numer, denom, prior)
        if missing:
            shrunk = shrunk.where(denom > 0, np.nan)
        out[name] = shrunk
    return out


def _positional_prior(success: pd.Series, trials: pd.Series, position: pd.Series) -> pd.Series:
    work = pd.DataFrame({"success": success.to_numpy(), "trials": trials.to_numpy(), "position": position.to_numpy()})
    grouped = work.groupby("position", sort=False)[["success", "trials"]].sum()
    rate = grouped["success"] / grouped["trials"].where(grouped["trials"] > 0)
    total_trials = float(work["trials"].sum())
    overall = float(work["success"].sum() / total_trials) if total_trials > 0 else 0.0
    return position.map(rate).fillna(overall).astype(float)


def _weekly_skill_points(hist: pd.DataFrame) -> pd.Series:
    """FanDuel points for one player-week, including the +3 yardage bonus."""

    def column(name: str) -> pd.Series:
        if name not in hist.columns:
            return pd.Series(0.0, index=hist.index)
        return pd.to_numeric(hist[name], errors="coerce").fillna(0.0)

    pass_yds = column("pass_yds")
    rush_yds = column("rush_yds")
    rec_yds = column("rec_yds")
    return (
        pass_yds * 0.04
        + column("pass_td") * 4.0
        - column("interceptions")
        + rush_yds * 0.1
        + column("rush_td") * 6.0
        + column("receptions") * 0.5
        + rec_yds * 0.1
        + column("rec_td") * 6.0
        - column("fumbles_lost") * 2.0
        + 3.0 * pass_yds.ge(300).astype(float)
        + 3.0 * rush_yds.ge(100).astype(float)
        + 3.0 * rec_yds.ge(100).astype(float)
    )


def _trail4_opps(hist: pd.DataFrame) -> pd.Series:
    if hist.empty or "player_id" not in hist.columns:
        return pd.Series(dtype=float)
    work = hist.sort_values(["player_id", "season", "week"], kind="mergesort")
    opps = _series(work, "targets") + _series(work, "carries")
    work = work.assign(_opps=opps.to_numpy())
    last = work.groupby("player_id", sort=False).tail(4)
    return last.groupby("player_id")["_opps"].sum()


def _defense_lagged_fd(hist: pd.DataFrame) -> pd.Series:
    if hist.empty or "team" not in hist.columns:
        return pd.Series(dtype=float)
    points = _defense_week_points(hist)
    return hist.assign(_fd=points.to_numpy()).groupby("team")["_fd"].mean()


def _defense_week_points(hist: pd.DataFrame) -> pd.Series:
    def column(name: str) -> pd.Series:
        if name not in hist.columns:
            return pd.Series(0.0, index=hist.index)
        return pd.to_numeric(hist[name], errors="coerce").fillna(0.0)

    events = (
        column("sacks")
        + 2.0 * column("interceptions")
        + 2.0 * column("fumbles")
        + 6.0 * column("dst_td")
        + 2.0 * column("safeties")
    )
    if "points_allowed" not in hist.columns:
        return events
    allowed = pd.to_numeric(hist["points_allowed"], errors="coerce")
    tier = pd.Series(np.nan, index=hist.index)
    known = allowed.notna()
    values = allowed.fillna(0.0).to_numpy()
    bands = np.select(
        [values <= 0, values <= 6, values <= 13, values <= 20, values <= 27, values <= 34],
        [10.0, 7.0, 4.0, 1.0, 0.0, -1.0],
        default=-4.0,
    )
    tier.loc[known] = bands[known.to_numpy()]
    return events + tier.fillna(0.0)


def _ratio(numer: pd.Series, denom: pd.Series, *, missing: bool = False) -> pd.Series:
    numer = pd.to_numeric(numer, errors="coerce")
    denom = pd.to_numeric(denom, errors="coerce")
    out = numer / denom.where(denom > 0)
    if missing:
        return out.where(denom > 0, np.nan)
    return out.fillna(0.0)


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce")


def _flag(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index)
    return _as_flag(frame[column])


def _coalesce_flag(frame: pd.DataFrame, primary: str, fallback: str) -> pd.Series:
    first = _flag(frame, primary) if primary else pd.Series(np.nan, index=frame.index)
    second = _flag(frame, fallback) if fallback else pd.Series(np.nan, index=frame.index)
    return first.where(first.notna(), second)


def _as_flag(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.astype(float)
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_numeric(values, errors="coerce")
    text = values.astype(str).str.strip().str.lower()
    return text.map({"true": 1.0, "false": 0.0, "1": 1.0, "0": 0.0, "1.0": 1.0, "0.0": 0.0})
