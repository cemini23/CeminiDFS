"""Pre-game injury flags and vacated-opportunity redistribution.

Week injury rows are report labels. They are not play-by-play results.
Out and IR players are zeroed. Their targets and red-zone touches move
to active teammates on the salary-file team.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ceminidfs.data.fetch import week_cache_dir

OUT_TOKENS = {"O", "OUT", "IR"}
DOUBT_TOKENS = {"D", "DOUBTFUL"}
REPORT_OUT = {"OUT", "IR"}
REPORT_DOUBT = {"DOUBTFUL"}


def load_week_injuries(season: int, week: int) -> pd.DataFrame:
    """Return the cached injury report for one week. Missing cache is an empty frame."""

    path = week_cache_dir(season, week) / "injuries.parquet"
    if not path.is_file():
        fallback = Path("artifacts/cache") / f"injuries_{int(season)}.parquet"
        path = fallback if fallback.is_file() else path
    if not path.is_file():
        return pd.DataFrame(columns=["gsis_id", "team", "full_name", "report_status"])
    frame = pd.read_parquet(path)
    if "week" in frame.columns:
        frame = frame.loc[pd.to_numeric(frame["week"], errors="coerce") == int(week)].copy()
    keep = [column for column in ("gsis_id", "team", "full_name", "report_status") if column in frame.columns]
    if not keep:
        return pd.DataFrame(columns=["gsis_id", "team", "full_name", "report_status"])
    return frame.loc[:, keep].copy()


def apply_injury_vacuum(frame: pd.DataFrame, injuries: pd.DataFrame | None) -> pd.DataFrame:
    """Flag Out, IR, and Doubtful rows. Move vacated volume to active teammates."""

    out = frame.copy()
    out["injury_status"] = _salary_status(out)
    out = _overlay_report(out, injuries)
    out["vacated_target_boost"] = 0.0
    out["vacated_rz_boost"] = 0.0
    out["vacated_carry_boost"] = 0.0
    if out.empty or ("team" not in out.columns and "salary_team" not in out.columns):
        return out
    status = out["injury_status"].astype(str).str.upper()
    donors = status.isin(OUT_TOKENS)
    if bool(donors.any()):
        out = _redistribute(out, donors)
    out.loc[donors, "lagged_fd"] = 0.0
    out.loc[donors, "vacated_target_boost"] = 0.0
    out.loc[donors, "vacated_rz_boost"] = 0.0
    out.loc[donors, "vacated_carry_boost"] = 0.0
    return out


def _salary_status(frame: pd.DataFrame) -> pd.Series:
    if "injury_indicator" not in frame.columns:
        return pd.Series("", index=frame.index)
    raw = frame["injury_indicator"].astype(str).str.strip().str.upper()
    raw = raw.replace({"NAN": "", "NONE": "", "NAT": ""})
    mapped = raw.map(_token)
    return mapped.fillna("")


def _token(value: str) -> str:
    if value in OUT_TOKENS:
        return "OUT" if value != "IR" else "IR"
    if value in DOUBT_TOKENS:
        return "DOUBTFUL"
    return ""


def _overlay_report(frame: pd.DataFrame, injuries: pd.DataFrame | None) -> pd.DataFrame:
    if injuries is None or injuries.empty or "gsis_id" not in injuries.columns:
        return frame
    report = injuries.copy()
    report["gsis_id"] = report["gsis_id"].astype(str)
    report["status"] = report.get("report_status", pd.Series("", index=report.index)).map(_report_token)
    report = report.loc[report["status"].ne("")].drop_duplicates("gsis_id")
    if report.empty or "player_id" not in frame.columns:
        return frame
    mapping = pd.Series(report["status"].to_numpy(), index=report["gsis_id"].to_numpy())
    looked = frame["player_id"].astype(str).map(mapping)
    current = frame["injury_status"].astype(str)
    # A salary Out/IR label stays. An empty salary label can take the report.
    fill = current.eq("") & looked.notna()
    frame = frame.copy()
    frame.loc[fill, "injury_status"] = looked.loc[fill].astype(str)
    return frame


def _report_token(value: object) -> str:
    text = str(value or "").strip().upper()
    if text in REPORT_OUT or text == "OUT":
        return "IR" if text == "IR" else "OUT"
    if text in REPORT_DOUBT:
        return "DOUBTFUL"
    return ""


def _redistribute(frame: pd.DataFrame, donors: pd.Series) -> pd.DataFrame:
    out = frame.copy()
    team = _current_team(out)
    position = out.get("position", pd.Series("", index=out.index)).astype(str)
    active = ~donors
    targets = _num(out, "targets_per_game")
    carries = _num(out, "carries_per_game")
    inside = _num(out, "inside10_target_share")
    rz_touches = targets * inside
    for label, part_index in out.groupby(team, sort=False).groups.items():
        idx = list(part_index)
        donor_idx = [item for item in idx if bool(donors.loc[item])]
        if not donor_idx:
            continue
        receiver_idx = [
            item
            for item in idx
            if bool(active.loc[item]) and position.loc[item] in {"WR", "RB", "TE"}
        ]
        rb_idx = [item for item in receiver_idx if position.loc[item] == "RB"]
        vacated_targets = float(targets.loc[donor_idx].clip(lower=0).sum())
        vacated_rz = float(rz_touches.loc[donor_idx].clip(lower=0).sum())
        vacated_carries = float(carries.loc[donor_idx].clip(lower=0).sum())
        _spread(out, receiver_idx, "vacated_target_boost", targets, vacated_targets)
        _spread(out, receiver_idx, "vacated_rz_boost", rz_touches, vacated_rz)
        _spread(out, rb_idx, "vacated_carry_boost", carries, vacated_carries)
        _add_receiving_points(out, receiver_idx)
        _add_carry_points(out, rb_idx)
        _ = label
    return out


def _spread(frame: pd.DataFrame, receivers: list, column: str, weights: pd.Series, mass: float) -> None:
    if mass <= 0 or not receivers:
        return
    weight = weights.loc[receivers].clip(lower=0)
    total = float(weight.sum())
    if total <= 0:
        share = mass / len(receivers)
        frame.loc[receivers, column] = frame.loc[receivers, column] + share
        return
    frame.loc[receivers, column] = frame.loc[receivers, column] + mass * weight / total


def _add_receiving_points(frame: pd.DataFrame, receivers: list) -> None:
    if not receivers:
        return
    targets = _num(frame, "targets_per_game").clip(lower=0)
    per_target = (
        _num(frame, "receptions_per_game") * 0.5
        + _num(frame, "rec_yds_per_game") * 0.1
        + _num(frame, "rec_td_per_game") * 6.0
    ) / targets.where(targets > 0)
    extra = frame.loc[receivers, "vacated_target_boost"] * per_target.loc[receivers].fillna(0.0)
    frame.loc[receivers, "lagged_fd"] = _num(frame, "lagged_fd").loc[receivers] + extra


def _add_carry_points(frame: pd.DataFrame, receivers: list) -> None:
    if not receivers:
        return
    carries = _num(frame, "carries_per_game").clip(lower=0)
    per_carry = (
        _num(frame, "rush_yds_per_game") * 0.1 + _num(frame, "rush_td_per_game") * 6.0
    ) / carries.where(carries > 0)
    extra = frame.loc[receivers, "vacated_carry_boost"] * per_carry.loc[receivers].fillna(0.0)
    frame.loc[receivers, "lagged_fd"] = _num(frame, "lagged_fd").loc[receivers] + extra


def _current_team(frame: pd.DataFrame) -> pd.Series:
    """Use the salary-file team when it is present."""

    if "salary_team" in frame.columns:
        salary = frame["salary_team"].astype(str).str.strip()
        if "team" not in frame.columns:
            return salary
        history = frame["team"].astype(str)
        blank = salary.eq("") | salary.str.upper().isin(["NAN", "NONE"])
        return salary.where(~blank, history)
    return frame["team"].astype(str)


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
