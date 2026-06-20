"""Counting stat projection helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import pandas as pd

from ceminidfs.models.defense import build_defense_ratings, defense_multiplier


LEAGUE_YPA = 7.0
LEAGUE_YPC = 4.3
LEAGUE_YPT = 7.8
LEAGUE_CATCH_RATE = 0.65
LEAGUE_ADOT = 10.0
LEAGUE_INT_RATE = 0.025
LEAGUE_TD_PER_ATT = 0.045
LEAGUE_TD_PER_CARRY = 0.03
LEAGUE_TD_PER_TARGET = 0.045


@dataclass(frozen=True)
class PlayerStatProjection:
    season: int
    week: int
    team: str
    opponent: str
    player_id: str
    player_name: str
    position: str
    pass_yds: float
    pass_td: float
    int: float
    rush_yds: float
    rush_td: float
    rec: float
    rec_yds: float
    rec_td: float
    fumbles_lost: float = 0.0
    ypa: float = LEAGUE_YPA
    ypc: float = LEAGUE_YPC
    ypt: float = LEAGUE_YPT
    catch_rate: float = LEAGUE_CATCH_RATE
    adot: float = LEAGUE_ADOT

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def regress_rate(observed: float, sample: float, prior: float, k: float) -> float:
    """Shrink an observed rate toward a league prior."""

    denominator = sample + k
    if denominator <= 0:
        return prior
    return ((observed * sample) + (prior * k)) / denominator



def player_efficiency_from_pbp(
    pbp: pd.DataFrame,
    player_id: str,
    through_week: int,
) -> dict[str, float]:
    """Return regressed passing, rushing, and receiving efficiency for one player."""

    historical = _historical_pbp(pbp, through_week)
    if historical.empty:
        return _league_efficiency()

    player = str(player_id)
    pass_eff = _passing_efficiency(historical, player)
    rush_eff = _rushing_efficiency(historical, player)
    rec_eff = _receiving_efficiency(historical, player)
    return {
        "ypa": pass_eff["ypa"],
        "int_rate": pass_eff["int_rate"],
        "td_rate": pass_eff["td_rate"],
        "ypc": rush_eff["ypc"],
        "td_per_carry": rush_eff["td_per_carry"],
        "ypt": rec_eff["ypt"],
        "catch_rate": rec_eff["catch_rate"],
        "adot": rec_eff["adot"],
        "td_per_target": rec_eff["td_per_target"],
    }


def project_player_stats(
    usage_row: Mapping[str, Any],
    efficiency: Mapping[str, Any],
    *,
    week: int,
    defense_ratings: Mapping[str, Mapping[str, float]] | None = None,
) -> PlayerStatProjection:
    """Project counting stats from usage volume and regressed efficiency."""

    pass_attempts = _mapping_float(usage_row, "projected_pass_attempts")
    carries = _mapping_float(usage_row, "projected_carries")
    targets = _mapping_float(usage_row, "projected_targets")
    opponent = str(usage_row.get("opponent", ""))
    pass_mult = defense_multiplier(opponent, "pass", defense_ratings)
    rush_mult = defense_multiplier(opponent, "rush", defense_ratings)

    ypa = _mapping_float(efficiency, "ypa", default=LEAGUE_YPA)
    ypc = _mapping_float(efficiency, "ypc", default=LEAGUE_YPC)
    ypt = _mapping_float(efficiency, "ypt", default=LEAGUE_YPT)
    catch_rate = _mapping_float(efficiency, "catch_rate", default=LEAGUE_CATCH_RATE)
    adot = _mapping_float(efficiency, "adot", default=LEAGUE_ADOT)
    int_rate = _mapping_float(efficiency, "int_rate", default=LEAGUE_INT_RATE)
    td_rate = _mapping_float(efficiency, "td_rate", default=LEAGUE_TD_PER_ATT)
    td_per_carry = _mapping_float(efficiency, "td_per_carry", default=LEAGUE_TD_PER_CARRY)
    td_per_target = _mapping_float(efficiency, "td_per_target", default=LEAGUE_TD_PER_TARGET)

    return PlayerStatProjection(
        season=int(usage_row.get("season", 0) or 0),
        week=int(usage_row.get("week", week) or week),
        team=str(usage_row.get("team", "")),
        opponent=str(usage_row.get("opponent", "")),
        player_id=str(usage_row.get("player_id", "")),
        player_name=str(usage_row.get("player_name", "")),
        position=str(usage_row.get("position", "")).upper(),
        pass_yds=_non_negative(pass_attempts * ypa * pass_mult),
        pass_td=_non_negative(pass_attempts * td_rate),
        int=_non_negative(pass_attempts * int_rate),
        rush_yds=_non_negative(carries * ypc * rush_mult),
        rush_td=_non_negative(carries * td_per_carry),
        rec=_non_negative(targets * catch_rate),
        rec_yds=_non_negative(targets * ypt * pass_mult),
        rec_td=_non_negative(targets * td_per_target),
        fumbles_lost=_non_negative(_mapping_float(usage_row, "fumbles_lost")),
        ypa=ypa,
        ypc=ypc,
        ypt=ypt,
        catch_rate=catch_rate,
        adot=adot,
    )


def build_week_stats(
    usage_df: pd.DataFrame,
    pbp: pd.DataFrame,
    *,
    season: int,
    week: int,
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Build player counting-stat projections for a target week."""

    columns = list(PlayerStatProjection.__dataclass_fields__)
    if usage_df.empty:
        return pd.DataFrame(columns=columns)

    week_usage = usage_df.loc[
        (pd.to_numeric(usage_df.get("season", season), errors="coerce") == season)
        & (pd.to_numeric(usage_df.get("week", week), errors="coerce") == week)
    ].copy()
    if week_usage.empty:
        return pd.DataFrame(columns=columns)

    historical_pbp = pbp.copy()
    if not historical_pbp.empty and "season" in historical_pbp.columns:
        historical_pbp = historical_pbp.loc[
            pd.to_numeric(historical_pbp["season"], errors="coerce").fillna(season) == season
        ]

    defense_cfg = {}
    if isinstance(config, Mapping):
        defense_cfg = config.get("defense", {})
    alpha = float(defense_cfg.get("alpha", 0.08)) if isinstance(defense_cfg, Mapping) else 0.08
    defense_ratings = build_defense_ratings(historical_pbp, through_week=week, alpha=alpha)

    efficiency_by_player: dict[str, dict[str, float]] = {}
    rows: list[dict[str, Any]] = []
    for _, usage_row in week_usage.iterrows():
        player_id = str(usage_row.get("player_id", ""))
        if player_id not in efficiency_by_player:
            efficiency_by_player[player_id] = player_efficiency_from_pbp(
                historical_pbp,
                player_id,
                through_week=week,
            )
        projection = project_player_stats(
            usage_row.to_dict(),
            efficiency_by_player[player_id],
            week=week,
            defense_ratings=defense_ratings,
        )
        rows.append(projection.to_dict())

    return pd.DataFrame(rows, columns=columns)


def _passing_efficiency(pbp: pd.DataFrame, player_id: str) -> dict[str, float]:
    passer_col = _first_present(pbp, ("passer_player_id", "passer_id", "qb_player_id"))
    if passer_col is None:
        attempts = pd.DataFrame()
    else:
        attempts = pbp.loc[_pass_flag(pbp).eq(1) & pbp[passer_col].fillna("").astype(str).eq(player_id)]

    sample = float(len(attempts))
    yards = _sum_first_numeric(attempts, ("passing_yards", "pass_yards", "yards_gained"))
    touchdowns = _sum_first_numeric(attempts, ("passing_tds", "pass_touchdown", "touchdown"))
    interceptions = _sum_first_numeric(attempts, ("interceptions", "interception"))
    return {
        "ypa": regress_rate(_rate(yards, sample), sample, LEAGUE_YPA, 250.0),
        "td_rate": regress_rate(_rate(touchdowns, sample), sample, LEAGUE_TD_PER_ATT, 250.0),
        "int_rate": regress_rate(_rate(interceptions, sample), sample, LEAGUE_INT_RATE, 250.0),
    }


def _rushing_efficiency(pbp: pd.DataFrame, player_id: str) -> dict[str, float]:
    rusher_col = _first_present(pbp, ("rusher_player_id", "rusher_id"))
    if rusher_col is None:
        carries = pd.DataFrame()
    else:
        carries = pbp.loc[_rush_flag(pbp).eq(1) & pbp[rusher_col].fillna("").astype(str).eq(player_id)]

    sample = float(len(carries))
    yards = _sum_first_numeric(carries, ("rushing_yards", "rush_yards", "yards_gained"))
    touchdowns = _sum_first_numeric(carries, ("rushing_tds", "rush_touchdown", "touchdown"))
    return {
        "ypc": regress_rate(_rate(yards, sample), sample, LEAGUE_YPC, 250.0),
        "td_per_carry": regress_rate(
            _rate(touchdowns, sample),
            sample,
            LEAGUE_TD_PER_CARRY,
            250.0,
        ),
    }


def _receiving_efficiency(pbp: pd.DataFrame, player_id: str) -> dict[str, float]:
    receiver_col = _first_present(pbp, ("receiver_player_id", "receiver_id", "player_id"))
    if receiver_col is None:
        targets = pd.DataFrame()
    else:
        targets = pbp.loc[
            _pass_flag(pbp).eq(1) & pbp[receiver_col].fillna("").astype(str).eq(player_id)
        ]

    sample = float(len(targets))
    yards = _sum_first_numeric(targets, ("receiving_yards", "yards_gained"))
    air_yards = _sum_first_numeric(targets, ("air_yards",))
    receptions = _sum_first_numeric(targets, ("complete_pass", "reception"))
    touchdowns = _sum_first_numeric(targets, ("receiving_tds", "pass_touchdown", "touchdown"))
    return {
        "ypt": regress_rate(_rate(yards, sample), sample, LEAGUE_YPT, 250.0),
        "catch_rate": regress_rate(_rate(receptions, sample), sample, LEAGUE_CATCH_RATE, 80.0),
        "adot": regress_rate(_rate(air_yards, sample), sample, LEAGUE_ADOT, 40.0),
        "td_per_target": regress_rate(
            _rate(touchdowns, sample),
            sample,
            LEAGUE_TD_PER_TARGET,
            80.0,
        ),
    }


def _historical_pbp(pbp: pd.DataFrame, through_week: int) -> pd.DataFrame:
    if pbp.empty or "week" not in pbp.columns:
        return pd.DataFrame()
    weeks = pd.to_numeric(pbp["week"], errors="coerce")
    return pbp.loc[weeks < through_week].copy()


def _league_efficiency() -> dict[str, float]:
    return {
        "ypa": LEAGUE_YPA,
        "int_rate": LEAGUE_INT_RATE,
        "td_rate": LEAGUE_TD_PER_ATT,
        "ypc": LEAGUE_YPC,
        "td_per_carry": LEAGUE_TD_PER_CARRY,
        "ypt": LEAGUE_YPT,
        "catch_rate": LEAGUE_CATCH_RATE,
        "adot": LEAGUE_ADOT,
        "td_per_target": LEAGUE_TD_PER_TARGET,
    }


def _pass_flag(df: pd.DataFrame) -> pd.Series:
    col = _first_present(df, ("pass_attempt", "pass"))
    if col is None:
        return pd.Series(0, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)


def _rush_flag(df: pd.DataFrame) -> pd.Series:
    col = _first_present(df, ("rush_attempt", "rush"))
    if col is None:
        return pd.Series(0, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)


def _first_present(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    for col in aliases:
        if col in df.columns:
            return col
    return None


def _sum_first_numeric(df: pd.DataFrame, aliases: tuple[str, ...]) -> float:
    col = _first_present(df, aliases)
    if df.empty or col is None:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0.0).sum())


def _rate(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def _mapping_float(mapping: Mapping[str, Any], key: str, *, default: float = 0.0) -> float:
    value = mapping.get(key, default)
    coerced = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return default if pd.isna(coerced) else float(coerced)


def _non_negative(value: float) -> float:
    return max(0.0, value)
