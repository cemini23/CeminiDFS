"""Ceiling caps, salary-team labels, and the week-6 shared cache."""

from pathlib import Path

import pandas as pd
import pytest

from ceminidfs.situational.contract import FeatureTables
from ceminidfs.situational.eb import empirical_bayes
import numpy as np

from ceminidfs.situational.engine import _cache_players, _read_salary, score_players
from ceminidfs.situational.features import _passer_rows, _weekly_skill_points
from ceminidfs.situational.game_context import _fallback_referee, build_game_context
from ceminidfs.situational.injuries import apply_injury_vacuum
from ceminidfs.situational.quantiles import SKILL_CAP, apply_ceiling
from ceminidfs.situational.shared_cache import write_shared_cache

CACHE = Path("artifacts/cache")
SALARY = Path("data/slates/2026-10-18_fd_sun.csv")


def test_ceiling_is_capped_and_is_not_a_scalar():
    table = [
        {"position": "RB", "bucket": "*", "n": 40, "q90": 10.0, "q99": 18.0},
        {"position": "RB", "bucket": "8-12", "n": 30, "q90": 8.0, "q99": 14.0},
        {"position": "RB", "bucket": "16-20", "n": 30, "q90": 14.0, "q99": 24.0},
    ]
    low90, low99 = apply_ceiling(10.0, "RB", table, 0.0)
    high90, high99 = apply_ceiling(18.0, "RB", table, 1.5)
    assert low99 <= SKILL_CAP
    assert high99 <= SKILL_CAP
    assert high99 > high90
    ratios = [low90 / 10.0, high90 / 18.0]
    assert ratios[0] != pytest.approx(ratios[1])
    blown90, blown99 = apply_ceiling(50.0, "RB", table, 40.0)
    assert blown90 <= SKILL_CAP
    assert blown99 <= SKILL_CAP


def test_empirical_bayes_uses_fifteen_trials():
    shrunk = empirical_bayes(
        pd.Series([1.0]),
        pd.Series([2.0]),
        pd.Series([0.2]),
    )
    assert shrunk.iloc[0] == pytest.approx((1.0 + 15.0 * 0.2) / (2.0 + 15.0))


def test_sack_is_not_a_pass_attempt_and_bonus_is_included():
    plays = pd.DataFrame(
        [
            {
                "passer_player_id": "qb",
                "passer_player_name": "J.Hurts",
                "posteam": "PHI",
                "defteam": "NYG",
                "season": 2026,
                "week": 1,
                "game_id": "g",
                "play_id": 1,
                "pass": 1,
                "sack": 1,
                "yards_gained": -7,
                "qtr": 1,
            }
        ]
    )
    rows = _passer_rows(plays)
    assert rows.iloc[0]["pass_att"] == 0.0
    assert rows.iloc[0]["pass_yds"] == 0.0
    points = _weekly_skill_points(pd.DataFrame([{"pass_yds": 300.0, "rush_yds": 100.0}]))
    assert points.iloc[0] == pytest.approx(300.0 * 0.04 + 3.0 + 100.0 * 0.1 + 3.0)


def test_salary_team_beats_history_and_out_is_zeroed():
    players = pd.DataFrame(
        [
            {
                "player_id": "wandale",
                "player_name": "Wan'Dale Robinson",
                "team": "NYG",
                "position": "WR",
                "fd_points_per_game": 8.0,
                "targets_per_game": 6.0,
                "receptions_per_game": 4.0,
                "rec_yds_per_game": 40.0,
                "rec_td_per_game": 0.2,
                "inside10_target_share": 0.1,
                "trail4_opps": 20.0,
            },
            {
                "player_id": "hurts",
                "player_name": "Jalen Hurts",
                "team": "PHI",
                "position": "QB",
                "fd_points_per_game": 18.0,
                "carries_per_game": 8.0,
                "rush_yds_per_game": 40.0,
                "rush_td_per_game": 0.4,
                "trail4_opps": 30.0,
            },
            {
                "player_id": "barkley",
                "player_name": "Saquon Barkley",
                "team": "PHI",
                "position": "RB",
                "fd_points_per_game": 16.0,
                "carries_per_game": 18.0,
                "rush_yds_per_game": 80.0,
                "rush_td_per_game": 0.6,
                "targets_per_game": 3.0,
                "trail4_opps": 40.0,
            },
        ]
    )
    salary = pd.DataFrame(
        [
            _salary("wandale-id", "WR", "Wan'Dale Robinson", "Robinson", "TEN", "NE"),
            _salary("hurts-id", "QB", "Jalen Hurts", "Hurts", "PHI", "NYG", injury="O"),
            _salary("barkley-id", "RB", "Saquon Barkley", "Barkley", "PHI", "NYG"),
        ]
    )
    tables = FeatureTables(players=players, defense=pd.DataFrame(), audit={})
    scored = score_players(tables, _calibration(), salary)
    wandale = scored.loc[scored["player_id"].eq("wandale-id")].iloc[0]
    hurts = scored.loc[scored["player_id"].eq("hurts-id")].iloc[0]
    barkley = scored.loc[scored["player_id"].eq("barkley-id")].iloc[0]
    assert wandale["team"] == "TEN"
    assert hurts["team"] == "PHI"
    assert hurts["injury_status"] == "OUT"
    assert hurts["lagged_fd"] == 0.0
    assert pd.isna(hurts["p99"])
    assert barkley["vacated_carry_boost"] > 0


def test_flags_require_the_opportunity_floor():
    frame = pd.DataFrame(
        [
            {
                "player_id": "fringe",
                "player_name": "Laquon Treadwell",
                "team": "BAL",
                "salary_team": "BAL",
                "position": "WR",
                "lagged_fd": 1.0,
                "trail4_opps": 2.0,
                "q3_rz_touch_share": 0.9,
                "q4_trail_target_share": 0.9,
                "opp_def_q3_slow_start": 1.0,
                "avg_yac_above_expectation": 1.0,
            },
            {
                "player_id": "starter",
                "player_name": "Starter",
                "team": "BAL",
                "salary_team": "BAL",
                "position": "WR",
                "lagged_fd": 12.0,
                "trail4_opps": 24.0,
                "q3_rz_touch_share": 0.9,
                "q4_trail_target_share": 0.9,
                "opp_def_q3_slow_start": 1.0,
                "avg_yac_above_expectation": 1.0,
            },
        ]
    )
    from ceminidfs.situational.engine import _apply_report_flags

    flagged = _apply_report_flags(
        frame,
        {"thresholds": {"q3_rz_touch_share_p75": 0.2, "q4_trail_target_share_p75": 0.2}},
    )
    assert bool(flagged.loc[flagged["player_id"].eq("fringe"), "q3_flag"].iloc[0]) is False
    assert bool(flagged.loc[flagged["player_id"].eq("starter"), "q3_flag"].iloc[0]) is True


def test_injury_vacuum_follows_the_salary_team():
    frame = pd.DataFrame(
        [
            {
                "player_name": "Donor",
                "team": "NYG",
                "salary_team": "TEN",
                "position": "WR",
                "injury_indicator": "O",
                "lagged_fd": 10.0,
                "targets_per_game": 8.0,
                "inside10_target_share": 0.25,
            },
            {
                "player_name": "Mate",
                "team": "NYG",
                "salary_team": "TEN",
                "position": "WR",
                "injury_indicator": "",
                "lagged_fd": 9.0,
                "targets_per_game": 7.0,
                "receptions_per_game": 4.0,
                "rec_yds_per_game": 50.0,
                "rec_td_per_game": 0.3,
                "inside10_target_share": 0.1,
            },
        ]
    )
    out = apply_injury_vacuum(frame, None)
    donor = out.loc[out["player_name"].eq("Donor")].iloc[0]
    mate = out.loc[out["player_name"].eq("Mate")].iloc[0]
    assert donor["lagged_fd"] == 0.0
    assert mate["vacated_target_boost"] == pytest.approx(8.0)
    assert mate["lagged_fd"] > 9.0


@pytest.mark.skipif(not (CACHE / "pbp_2026.parquet").is_file(), reason="week cache missing")
@pytest.mark.skipif(not SALARY.is_file(), reason="salary file missing")
def test_week6_dst_teams_and_manifest(tmp_path):
    from ceminidfs.situational.engine import build_cached_grains
    from ceminidfs.situational.features import tables_from_grains
    from ceminidfs.situational.injuries import load_week_injuries

    grains, _audit = build_cached_grains((2023, 2024, 2025, 2026))
    tables = tables_from_grains(grains, season=2026, week=6)
    assert int(tables.audit["max_week_same_season"]) == 5
    assert tables.audit["lookahead_ok"] is True
    salary = _read_salary(SALARY)
    scored = score_players(tables, _live_calibration(), salary, injuries=load_week_injuries(2026, 6))
    assert scored["p99"].dropna().le(SKILL_CAP).all()
    dst = scored.loc[scored["position"].eq("DST")]
    assert len(dst) >= 20
    assert dst["lagged_fd"].gt(0).all()
    assert dst["p90"].notna().all()
    assert dst["p99"].notna().all()
    assert dst["p99"].le(35.0).all()
    ratios = (scored.loc[scored["lagged_fd"].gt(0), "p90"] / scored.loc[scored["lagged_fd"].gt(0), "lagged_fd"])
    assert ratios.nunique() > 1
    raw = pd.read_csv(SALARY)
    raw["Id"] = raw["Id"].astype(str)
    raw["Team"] = raw["Team"].astype(str).str.upper()
    joined = scored.merge(raw[["Id", "Team"]], left_on="player_id", right_on="Id", how="left")
    assert joined["Team"].notna().all()
    assert joined["team"].eq(joined["Team"]).all()
    flagged = scored.loc[scored["q3_flag"].astype(bool) | scored["q4_flag"].astype(bool)]
    if not flagged.empty:
        floor = flagged["lagged_fd"].ge(6.0) | flagged["trail4_opps"].ge(12.0)
        assert bool(floor.all())
    games, source_week = build_game_context(2026, 6)
    assert "away_score" not in games.columns
    assert "home_score" not in games.columns
    assert set(pd.to_numeric(games["week"]).astype(int).unique()) == {6}
    # Prior seasons include playoff weeks. The Week 6 feature cutoff is 5.
    assert int(source_week) > 5
    assert "LAR" in set(games["home_team"].astype(str)) or "LAR" in set(games["away_team"].astype(str))
    referee = games["referee"].astype(str).str.strip()
    assert bool(referee.ne("").all())
    assert bool(~referee.str.lower().isin(["nan", "none", "<na>"]).all())
    assert bool(games["referee_dpi_z"].notna().any())
    cached = _cache_players(tables.players, scored)
    assert {"vacated_target_boost", "vacated_rz_boost"} <= set(cached.columns)
    assert len(cached) == len(tables.players)
    boost_sum = cached["vacated_target_boost"].abs().sum() + cached["vacated_rz_boost"].abs().sum()
    assert float(boost_sum) > 0.0
    manifest = write_shared_cache(
        tmp_path,
        players=tables.players,
        defense=tables.defense,
        games=games,
        season=2026,
        week=6,
        max_source_week=int(tables.audit["max_week_same_season"]),
    )
    assert manifest["max_source_week"] == 5
    assert (tmp_path / "manifest.json").is_file()
    assert (tmp_path / "player_telemetry_pit.parquet").is_file()
    assert (tmp_path / "defense_counterpart_pit.parquet").is_file()
    assert (tmp_path / "game_context_pit.parquet").is_file()


def test_game_context_fallback_ignores_the_target_week(tmp_path):
    schedules = pd.DataFrame(
        {
            "game_id": ["2026_05_KC_DEN", "2026_06_SEA_DEN", "2026_06_LAC_DEN"],
            "season": [2026, 2026, 2026],
            "week": [5, 6, 6],
            "home_team": ["DEN", "DEN", "DEN"],
            "away_team": ["KC", "SEA", "LAC"],
            "referee": ["Shawn Hochuli", None, "Future Crew"],
            "roof": ["outdoor", "outdoor", "outdoor"],
            "surface": ["grass", "grass", "grass"],
            "temp": [60, 10, 10],
            "wind": [5, 99, 99],
            "spread_line": [1.0, 3.0, 3.0],
            "total_line": [44.0, 50.0, 50.0],
        }
    )
    schedules.to_parquet(tmp_path / "schedules_2026.parquet", index=False)
    games, _source_week = build_game_context(2026, 6, seasons=(2026,), cache_dir=tmp_path)
    den = games.loc[games["game_id"].eq("2026_06_SEA_DEN")].iloc[0]
    posted = games.loc[games["game_id"].eq("2026_06_LAC_DEN")].iloc[0]
    assert den["referee"] == "Shawn Hochuli"
    assert posted["referee"] == "Future Crew"
    assert "home_score" not in games.columns
    assert "away_score" not in games.columns


def test_blank_referee_uses_the_latest_prior_home_crew():
    slate = pd.DataFrame(
        {
            "home_team": ["DEN", "KC"],
            "referee": [np.nan, "Posted Crew"],
        }
    )
    prior = pd.DataFrame(
        {
            "season": [2026, 2026, 2026],
            "week": [1, 5, 6],
            "home_team": ["DEN", "DEN", "DEN"],
            "referee": ["Carl Cheffers", "Shawn Hochuli", "Future Crew"],
        }
    )
    # The caller passes only weeks before the target. This row is the leak check.
    prior = prior.loc[prior["week"] < 6]
    filled = _fallback_referee(slate, prior)
    assert list(filled) == ["Shawn Hochuli", "Posted Crew"]


def test_cache_players_writes_vacated_boosts():
    players = pd.DataFrame({"player_id": ["c", "a", "b"], "player_name": ["C", "A", "B"]})
    scored = pd.DataFrame(
        {
            "gsis_id": ["b", "b", "DST:TEN"],
            "vacated_target_boost": [1.5, 0.5, 9.0],
            "vacated_rz_boost": [0.2, 0.1, 3.0],
        }
    )
    out = _cache_players(players, scored)
    assert list(out["player_id"]) == ["a", "b", "c"]
    row = out.set_index("player_id")
    assert row.loc["a", "vacated_target_boost"] == 0.0
    assert row.loc["a", "vacated_rz_boost"] == 0.0
    assert row.loc["b", "vacated_target_boost"] == pytest.approx(2.0)
    assert row.loc["b", "vacated_rz_boost"] == pytest.approx(0.3)
    assert "gsis_id" not in out.columns


def _salary(salary_id, position, full_name, last_name, team, opponent, injury=""):
    return {
        "salary_id": salary_id,
        "position_salary": position,
        "full_name": full_name,
        "last_name": last_name,
        "team": team,
        "opponent": opponent,
        "salary": 5000,
        "fppg": 8.0,
        "injury_indicator": injury,
    }


def _calibration():
    table = [
        {"position": "WR", "bucket": "*", "n": 40, "q90": 8.0, "q99": 14.0},
        {"position": "QB", "bucket": "*", "n": 40, "q90": 10.0, "q99": 16.0},
        {"position": "RB", "bucket": "*", "n": 40, "q90": 9.0, "q99": 15.0},
    ]
    return {"targets": {}, "thresholds": {}, "correlation": {}, "quantiles": {"skill": table, "dst": []}}


def _live_calibration():
    skill = []
    for position, q90, q99 in (("QB", 12.0, 20.0), ("RB", 10.0, 18.0), ("WR", 9.0, 16.0), ("TE", 7.0, 12.0)):
        skill.append({"position": position, "bucket": "*", "n": 80, "q90": q90, "q99": q99})
    dst = [{"position": "DST", "bucket": "*", "n": 80, "q90": 6.0, "q99": 11.0}]
    return {"targets": {}, "thresholds": {}, "correlation": {}, "quantiles": {"skill": skill, "dst": dst}}
