"""Point-in-time lag, tail math, FDR, and correlation bounds."""

import math

import numpy as np
import pandas as pd

from ceminidfs.models.correlation import build_correlation_matrix
from ceminidfs.models.simulate import simulate_fd_points
from ceminidfs.situational.fdr import benjamini_hochberg
from ceminidfs.situational.contract import FeatureTables
from ceminidfs.situational.engine import score_players
from ceminidfs.situational.features import build_point_in_time_tables
from ceminidfs.situational.lag import cut_point_in_time
from ceminidfs.situational.stack_corr import apply_corr_boost, estimate_pair_boost
from ceminidfs.situational.tail import (
    fit_log_sigma,
    gamma_poisson_at_least,
    gamma_survival_matched,
    lognormal_survival,
    median_from_mean,
    mixture_yard_survival,
    poisson_at_least,
    yard_bonus_probability,
)


def test_cut_drops_current_week_and_week_zero():
    frame = pd.DataFrame(
        {
            "season": [2025, 2025, 2025, 2024],
            "week": [0, 5, 6, 18],
            "yards": [500, 10, 90, 40],
        }
    )
    cut = cut_point_in_time(frame, season=2025, week=6)
    assert set(zip(cut["season"], cut["week"], strict=True)) == {(2025, 5), (2024, 18)}


def test_player_rate_excludes_target_week_and_week_zero():
    rows = []
    for week, yards in ((0, 500.0), (1, 10.0), (2, 90.0)):
        rows.append(
            {
                "season": 2025,
                "week": week,
                "play_type": "pass",
                "pass": 1,
                "rush": 0,
                "complete_pass": 1,
                "qtr": 1,
                "yardline_100": 50,
                "score_differential": 0,
                "pass_touchdown": 0,
                "yards_gained": yards,
                "posteam": "KC",
                "defteam": "BUF",
                "game_id": f"g{week}",
                "play_id": week + 1,
                "receiver_player_id": "p1",
                "receiver_player_name": "A.Player",
            }
        )
    tables = build_point_in_time_tables(season=2025, week=2, pbp=pd.DataFrame(rows))
    player = tables.players.loc[tables.players["player_id"].eq("p1")].iloc[0]
    assert player["rec_yds_per_game"] == 10
    assert tables.audit["max_week_same_season"] == 1
    assert tables.audit["lookahead_ok"] is True


def test_ngs_week_zero_is_not_a_feature():
    pbp = pd.DataFrame(
        [
            {
                "season": 2025,
                "week": 1,
                "play_type": "pass",
                "pass": 1,
                "rush": 0,
                "complete_pass": 1,
                "qtr": 1,
                "yardline_100": 50,
                "score_differential": 0,
                "pass_touchdown": 0,
                "yards_gained": 10,
                "posteam": "KC",
                "defteam": "BUF",
                "game_id": "g1",
                "play_id": 1,
                "receiver_player_id": "p1",
                "receiver_player_name": "A.Player",
            }
        ]
    )
    ngs = pd.DataFrame(
        [
            {
                "season": 2025,
                "week": 0,
                "player_gsis_id": "p1",
                "player_display_name": "A Player",
                "player_position": "WR",
                "avg_separation": 20.0,
            },
            {
                "season": 2025,
                "week": 1,
                "player_gsis_id": "p1",
                "player_display_name": "A Player",
                "player_position": "WR",
                "avg_separation": 2.0,
            },
        ]
    )
    tables = build_point_in_time_tables(
        season=2025,
        week=2,
        pbp=pbp,
        ngs_receiving=ngs,
    )
    player = tables.players.iloc[0]
    assert player["avg_separation"] == 2


def test_lognormal_median_survival_and_mixture_limits():
    sigma = 0.4
    median = 50.0
    assert abs(lognormal_survival(median, sigma, median) - 0.5) < 1e-6
    mean = median * math.exp(0.5 * sigma * sigma)
    assert abs(median_from_mean(mean, sigma) - median) < 1e-8
    assert abs(mixture_yard_survival(median, sigma, 80.0, 1.0) - lognormal_survival(median, sigma, 80.0)) < 1e-10
    assert abs(mixture_yard_survival(median, sigma, 80.0, 0.0) - gamma_survival_matched(median, sigma, 80.0)) < 1e-10
    bonus = yard_bonus_probability(mean, sigma, "rec_yds", weight_lognormal=1.0)
    assert abs(bonus - lognormal_survival(median, sigma, 100.0)) < 1e-10
    assert fit_log_sigma(np.array([1.0] * 19)) is None
    fitted = fit_log_sigma(np.exp(np.linspace(0.1, 1.0, 25)))
    assert fitted is not None and fitted > 0


def test_poisson_and_gamma_poisson_limits():
    expected = 1.0 - 1.5 * math.exp(-0.5)
    assert abs(poisson_at_least(2, 0.5) - expected) < 1e-6
    close = gamma_poisson_at_least(2, 0.5, 1e-6)
    assert abs(close - expected) < 1e-3
    assert poisson_at_least(0, 0.2) == 1.0
    assert poisson_at_least(2, 0.0) == 0.0


def test_benjamini_hochberg_locks_the_first_four():
    p_values = {
        "a": 0.001,
        "b": 0.01,
        "c": 0.03,
        "d": 0.04,
        "e": 0.2,
        "f": 0.5,
    }
    table = benjamini_hochberg(p_values, q=0.10)
    rejected = table.loc[table["reject"], "feature"].tolist()
    assert rejected == ["a", "b", "c", "d"]
    ordered = table.sort_values("rank")
    assert list(ordered["q_value"]) == sorted(ordered["q_value"])


def test_corr_boost_is_symmetric_and_clipped():
    matrix = np.eye(2)
    boosted = apply_corr_boost(
        matrix,
        ["a", "b"],
        pd.DataFrame([{"player_a": "a", "player_b": "b", "corr_boost": 5.0}]),
    )
    assert boosted[0, 1] == 0.95
    assert boosted[1, 0] == 0.95
    assert boosted[0, 0] == 1.0
    assert np.allclose(boosted, boosted.T)


def test_role_prior_keeps_a_positive_boost_after_psd():
    frame = pd.DataFrame(
        [
            {"player_id": "qb", "team": "KC", "opp": "BUF", "position": "QB", "fd_projection": 20},
            {"player_id": "wr", "team": "KC", "opp": "BUF", "position": "WR", "fd_projection": 15},
        ]
    )
    base = build_correlation_matrix(frame)
    boost = pd.DataFrame([{"player_a": "qb", "player_b": "wr", "corr_boost": 0.1}])
    boosted = build_correlation_matrix(frame, corr_boost=boost)
    assert base[0, 1] == base[1, 0]
    assert boosted[0, 1] > base[0, 1]
    assert np.allclose(np.diag(boosted), 1.0)


def test_pair_boost_keeps_a_real_gap_and_drops_noise():
    rng = np.random.default_rng(20261017)
    signal = _pair_frame(rng, flagged_rho=0.85, base_rho=0.05)
    estimate = estimate_pair_boost(signal, kind="qb_skill", n_boot=80)
    assert estimate.boost > 0
    assert estimate.ci_low > 0
    noise = _pair_frame(rng, flagged_rho=0.4, base_rho=0.4)
    quiet = estimate_pair_boost(noise, kind="qb_skill", n_boot=80)
    assert quiet.boost == 0.0


def test_last_name_fallback_does_not_copy_a_teammate():
    players = pd.DataFrame(
        [
            {
                "player_id": "josh",
                "player_name": "Josh Allen",
                "team": "BUF",
                "position": "QB",
                "pass_yds_per_game": 250.0,
                "pass_td_per_game": 2.0,
            }
        ]
    )
    tables = FeatureTables(players=players, defense=pd.DataFrame(), audit={})
    salary = pd.DataFrame(
        [
            {
                "salary_id": "josh-id",
                "position_salary": "QB",
                "full_name": "Josh Allen",
                "last_name": "Allen",
                "team": "BUF",
                "opponent": "KC",
                "salary": 9000,
                "fppg": 20.0,
            },
            {
                "salary_id": "kyle-id",
                "position_salary": "QB",
                "full_name": "Kyle Allen",
                "last_name": "Allen",
                "team": "BUF",
                "opponent": "KC",
                "salary": 5000,
                "fppg": 0.0,
            },
        ]
    )
    scored = score_players(tables, {"targets": {}, "thresholds": {}, "correlation": {}}, salary)
    josh = scored.loc[scored["player_id"].eq("josh-id")].iloc[0]
    kyle = scored.loc[scored["player_id"].eq("kyle-id")].iloc[0]
    assert josh["lagged_fd"] > 10
    assert kyle["lagged_fd"] == 0


def test_copula_with_boost_is_repeatable():
    frame = pd.DataFrame(
        [
            {"player_id": "qb", "team": "KC", "opp": "BUF", "position": "QB", "fd_projection": 18},
            {"player_id": "wr", "team": "KC", "opp": "BUF", "position": "WR", "fd_projection": 14},
        ]
    )
    boost = pd.DataFrame([{"player_a": "qb", "player_b": "wr", "corr_boost": 0.1}])
    config = {"corr_boost": boost}
    first = simulate_fd_points(frame, n_iterations=30, seed=20261017, method="copula", config=config)
    second = simulate_fd_points(frame, n_iterations=30, seed=20261017, method="copula", config=config)
    assert np.allclose(first, second)


def _pair_frame(rng: np.random.Generator, *, flagged_rho: float, base_rho: float) -> pd.DataFrame:
    rows = []
    for week in range(1, 201):
        for flag, rho in ((True, flagged_rho), (False, base_rho)):
            for _ in range(40):
                shock = rng.normal(size=2)
                left = shock[0]
                right = rho * shock[0] + math.sqrt(max(0.0, 1.0 - rho * rho)) * shock[1]
                rows.append(
                    {
                        "season": 2024,
                        "week": week,
                        "flag": flag,
                        "points_a": left,
                        "points_b": right,
                    }
                )
    return pd.DataFrame(rows)
