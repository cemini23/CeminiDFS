"""Tests for the tiered Jev client and its three integrations.

Covers:

- Provider routing failover (TypeSafe / MCP -> OpenRouter -> prior).
- The conditional regime Gaussian mixture and its quantile math.
- Position ownership normalization sums.
- The upgraded ``ceminidfs_handoff.csv`` schema.

No test touches the network. Every provider is driven by an injected transport.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ceminidfs.export.handoff import (
    HANDOFF_BASE_COLUMNS,
    HANDOFF_COLUMNS,
    HandoffInputError,
    _gmm_bands,
    build_handoff_context,
    read_canonical,
)
from ceminidfs.export.review_reports import (
    LEVERAGE_FADE_HEADER,
    PARLAYS_HANDOFF_HEADER,
    write_parlays_handoff,
)
from ceminidfs.jev_client import (
    HTTPTimeout,
    JevUnavailableError,
    JevValidationError,
    build_jev_client,
)
from ceminidfs.models.regime_gmm import (
    HEALTHY_PRIOR,
    active_weights,
    inactive_risk,
)
from ceminidfs.models.simulate import (
    GMM_DECOY_LOC,
    GMM_EXIT_LOC,
    median_recenter_factors,
    sample_regime_gmm,
)
from ceminidfs.models.synthetic_ownership import (
    POSITION_OWNERSHIP_TARGET,
    normalize_position_ownership,
)

REGIME_CHOICES = (
    "full_role",
    "snap_count_decoy",
    "in_game_reaggravation_exit",
    "pre_game_inactive",
)


# --------------------------------------------------------------------------- #
# Provider routing failover.
# --------------------------------------------------------------------------- #
def _typesafe_ok(payload: dict, probabilities: dict | None = None, confidence: float = 0.8) -> dict:
    """Build a valid System One response for an outgoing request payload."""

    answers = {}
    for question_id, question in payload["questions"].items():
        criteria = question.get("criteria")
        if isinstance(criteria, dict):
            keys = list(criteria)
        else:
            keys = [str(index) for index in range(len(criteria or []))]
        probs = probabilities if probabilities is not None else {
            key: 1.0 / len(keys) for key in keys
        }
        answer = {"type": question["type"], "confidence": confidence, "probabilities": probs}
        if question["type"] == "choice":
            numeric = {key: value for key, value in probs.items() if isinstance(value, (int, float))}
            if numeric:
                answer["choice"] = max(numeric, key=numeric.get)
        if question["type"] == "score":
            answer["score"] = 0.0
            answer["legend"] = {str(index): key for index, key in enumerate(keys)}
        answers[question_id] = answer
    return {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 1, "output_tokens": 1}}


def _openrouter_body(probabilities: dict[str, float], confidence: float = 0.8) -> dict:
    content = json.dumps(
        {
            "answers": [
                {"probabilities": probabilities, "confidence": confidence}
            ]
        }
    )
    return {"choices": [{"message": {"content": content}}]}


def _state() -> dict:
    return {"position": "WR", "practice_wed_thu_fri": "LP/LP/FP"}


def _question() -> str:
    return "Which regime?"


@pytest.fixture()
def typed_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-typesafe-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.delenv("JEV_MCP_BATCH", raising=False)
    monkeypatch.delenv("JEV_MCP_URL", raising=False)
    monkeypatch.delenv("JEV_MCP_COMMAND", raising=False)


def test_typesafe_transient_failure_fails_over_to_openrouter(typed_keys, tmp_path: Path) -> None:
    calls: list[str] = []

    def transport(url: str, *, headers, payload, timeout):
        if url.endswith("/v1/systemone"):
            calls.append("typesafe")
            raise HTTPTimeout("simulated timeout")
        if "openrouter" in url:
            calls.append("openrouter")
            return 200, _openrouter_body({"full_role": 0.7, "snap_count_decoy": 0.2,
                                          "in_game_reaggravation_exit": 0.05,
                                          "pre_game_inactive": 0.05})
        raise AssertionError(f"unexpected url {url}")

    client = build_jev_client(
        provider="auto",
        fallback="prior",
        cache_dir=tmp_path / "jev-cache",
        transport=transport,
    )
    result = client.jev_choice(_state(), _question(), list(REGIME_CHOICES))
    assert result.provider_used == "openrouter"
    assert result.top_choice == "full_role"
    assert calls == ["typesafe", "openrouter"]
    assert any("failover" in line for line in client.failover_log)


def test_all_network_failure_falls_back_to_prior(typed_keys, tmp_path: Path) -> None:
    def transport(url: str, *, headers, payload, timeout):
        raise HTTPTimeout("down")

    client = build_jev_client(
        provider="auto",
        fallback="prior",
        cache_dir=tmp_path / "jev-cache",
        transport=transport,
    )
    result = client.jev_choice(_state(), _question(), list(REGIME_CHOICES))
    assert result.provider_used == "prior"
    assert set(result.probabilities) == set(REGIME_CHOICES)
    assert pytest.approx(sum(result.probabilities.values()), abs=1e-9) == 1.0


def test_all_network_failure_raises_when_fallback_is_raise(typed_keys, tmp_path: Path) -> None:
    def transport(url: str, *, headers, payload, timeout):
        raise HTTPTimeout("down")

    client = build_jev_client(
        provider="auto",
        fallback="raise",
        cache_dir=tmp_path / "jev-cache",
        transport=transport,
    )
    with pytest.raises(JevUnavailableError):
        client.jev_choice(_state(), _question(), list(REGIME_CHOICES))


def test_invalid_primary_payload_is_rejected_then_backup_answers(typed_keys, tmp_path: Path) -> None:
    calls: list[str] = []

    def transport(url: str, *, headers, payload, timeout):
        if url.endswith("/v1/systemone"):
            calls.append("typesafe")
            # Probabilities do not sum to one: fail closed.
            return 200, _typesafe_ok(
                payload,
                probabilities={
                    "full_role": 0.9,
                    "snap_count_decoy": 0.9,
                    "in_game_reaggravation_exit": 0.9,
                    "pre_game_inactive": 0.9,
                },
            )
        if "openrouter" in url:
            calls.append("openrouter")
            return 200, _openrouter_body({"full_role": 0.6, "snap_count_decoy": 0.2,
                                          "in_game_reaggravation_exit": 0.1,
                                          "pre_game_inactive": 0.1})
        raise AssertionError(f"unexpected url {url}")

    client = build_jev_client(
        provider="auto",
        fallback="prior",
        cache_dir=tmp_path / "jev-cache",
        transport=transport,
    )
    result = client.jev_choice(_state(), _question(), list(REGIME_CHOICES))
    assert result.provider_used == "openrouter"
    assert calls == ["typesafe", "openrouter"]


def test_invalid_primary_and_no_backup_falls_to_prior(typed_keys, tmp_path: Path) -> None:
    def transport(url: str, *, headers, payload, timeout):
        if url.endswith("/v1/systemone"):
            return 200, _typesafe_ok(
                payload,
                probabilities={
                    "full_role": None,
                    "snap_count_decoy": None,
                    "in_game_reaggravation_exit": None,
                    "pre_game_inactive": None,
                },
            )
        raise HTTPTimeout("no backup")

    client = build_jev_client(
        provider="auto",
        fallback="prior",
        cache_dir=tmp_path / "jev-cache",
        transport=transport,
    )
    result = client.jev_choice(_state(), _question(), list(REGIME_CHOICES))
    assert result.provider_used == "prior"


def test_prior_provider_ignores_network_and_is_deterministic(tmp_path: Path) -> None:
    def transport(url: str, *, headers, payload, timeout):  # pragma: no cover - never called.
        raise AssertionError("prior provider must not call the transport")

    client = build_jev_client(
        provider="prior",
        fallback="prior",
        cache_dir=tmp_path / "jev-cache",
        transport=transport,
    )
    first = client.jev_choice(_state(), _question(), list(REGIME_CHOICES))
    second = client.jev_choice(_state(), _question(), list(REGIME_CHOICES))
    assert first.probabilities == second.probabilities
    assert first.provider_used == "prior"


def test_response_is_cached_and_replayed_without_recompute(typed_keys, tmp_path: Path) -> None:
    calls: list[str] = []

    def transport(url: str, *, headers, payload, timeout):
        calls.append(url)
        return 200, _openrouter_body({"full_role": 0.5, "snap_count_decoy": 0.3,
                                      "in_game_reaggravation_exit": 0.1,
                                      "pre_game_inactive": 0.1})

    cache_dir = tmp_path / "jev-cache"
    client = build_jev_client(provider="openrouter", fallback="prior", cache_dir=cache_dir,
                              transport=transport)
    first = client.jev_choice(_state(), _question(), list(REGIME_CHOICES))
    assert first.cached is False
    assert len(list(cache_dir.glob("*.json"))) == 1

    replay = build_jev_client(provider="openrouter", fallback="prior", cache_dir=cache_dir,
                              transport=transport)
    second = replay.jev_choice(_state(), _question(), list(REGIME_CHOICES))
    assert second.cached is True
    assert second.probabilities == first.probabilities
    assert len(calls) == 1  # the second call was served from disk


def test_validation_error_on_explicit_provider_raises() -> None:
    from ceminidfs.jev_client import validate_probabilities

    with pytest.raises(JevValidationError):
        validate_probabilities(
            {"full_role": 0.5, "snap_count_decoy": 0.5},
            expected_keys=list(REGIME_CHOICES),
        )


# --------------------------------------------------------------------------- #
# GMM quantile math.
# --------------------------------------------------------------------------- #
def _draws(median: float, sigma: float, weights: tuple[float, float, float], n: int = 20000):
    rng = np.random.default_rng(20261015)
    return sample_regime_gmm(
        np.array([median]), np.array([sigma]), np.array([weights]), n_iterations=n, rng=rng
    )[0]


def test_healthy_mixture_matches_gaussian_central_band() -> None:
    median, sigma = 12.0, 3.0
    draws = _draws(median, sigma, (1.0, 0.0, 0.0))
    from ceminidfs.models.simulate import SIGMA_EFF_DENOMINATOR

    p15, p50, p85 = np.quantile(draws, (0.15, 0.5, 0.85))
    assert p15 < p50 < p85
    # Component 1 is N(mu, (1.15 sigma)^2). The central band recovers 2.073 * 1.15 * sigma.
    assert p85 - p15 == pytest.approx(2.0 * 1.0364 * 1.15 * sigma, rel=0.05)
    assert (p85 - p15) / SIGMA_EFF_DENOMINATOR == pytest.approx(1.15 * sigma, rel=0.05)
    assert p50 == pytest.approx(median, abs=0.3)


def test_decoy_component_centers_on_fifty_five_percent_of_median() -> None:
    median, sigma = 20.0, 4.0
    draws = _draws(median, sigma, (0.0, 1.0, 0.0))
    assert np.median(draws) == pytest.approx(0.55 * median, rel=0.02)
    assert draws.min() >= 0.0


def test_exit_component_is_truncated_at_zero() -> None:
    median, sigma = 25.0, 5.0
    draws = _draws(median, sigma, (0.0, 0.0, 1.0))
    assert draws.min() >= 0.0
    # TruncatedNormal(loc=0.22*mu, scale=0.45*sigma, low=0) has a positive median.
    assert np.median(draws) == pytest.approx(0.22 * median, rel=0.1)


def test_mixture_draws_never_negative() -> None:
    draws = _draws(6.0, 2.0, (0.4, 0.4, 0.2))
    assert np.all(draws >= 0.0)


def test_active_weights_renormalize_over_one_minus_inactive() -> None:
    weights = active_weights(
        {"full_role": 0.6, "snap_count_decoy": 0.1, "in_game_reaggravation_exit": 0.1,
         "pre_game_inactive": 0.2}
    )
    assert pytest.approx(sum(weights), abs=1e-9) == 1.0
    assert weights[0] == pytest.approx(0.6 / 0.8)
    assert weights[1] == pytest.approx(0.1 / 0.8)


def test_inactive_risk_flag_threshold() -> None:
    assert inactive_risk({"pre_game_inactive": 0.51}) is True
    assert inactive_risk({"pre_game_inactive": 0.50}) is False
    assert inactive_risk(HEALTHY_PRIOR) is False


# --------------------------------------------------------------------------- #
# Median re-centering and the consensus Brier.
# --------------------------------------------------------------------------- #
def _recentered_draws(
    median: float,
    sigma: float,
    weights: tuple[float, float, float],
    *,
    n: int = 200_000,
    seed: int = 20261015,
) -> tuple[float, np.ndarray]:
    factor = median_recenter_factors(
        np.array([median]), np.array([sigma]), np.array([weights])
    )[0]
    draws = sample_regime_gmm(
        np.array([factor * median]),
        np.array([sigma]),
        np.array([weights]),
        n_iterations=n,
        rng=np.random.default_rng(seed),
    )[0]
    return float(factor), draws


@pytest.mark.parametrize(
    "weights",
    [(0.92, 0.05, 0.03), (0.50, 0.30, 0.20), (0.60, 0.25, 0.15)],
)
def test_recentered_mixture_centres_on_mu(weights: tuple[float, float, float]) -> None:
    median, sigma = 20.0, 6.0
    factor, draws = _recentered_draws(median, sigma, weights)
    assert factor >= 1.0
    # The mixture median is mu by construction...
    assert np.median(draws) == pytest.approx(median, rel=0.01)
    # ...so P(draw > mu) lands on 0.5, not the 0.46 a mean-centred mixture gives.
    assert (draws > median).mean() == pytest.approx(0.5, abs=0.01)
    # The mean is pulled toward mu from the left-skewed blend as well.
    assert np.mean(draws) == pytest.approx(median, rel=0.05)


def test_recenter_preserves_component_location_ratios() -> None:
    median, sigma = 20.0, 4.0
    factor = median_recenter_factors(
        np.array([median]), np.array([sigma]), np.array([[0.5, 0.3, 0.2]])
    )[0]
    scaled = factor * median

    def component_median(weights: tuple[float, float, float]) -> float:
        draws = sample_regime_gmm(
            np.array([scaled]),
            np.array([sigma]),
            np.array([weights]),
            n_iterations=200_000,
            rng=np.random.default_rng(7),
        )[0]
        return float(np.median(draws))

    full_role = component_median((1.0, 0.0, 0.0))
    decoy = component_median((0.0, 1.0, 0.0))
    exit_ = component_median((0.0, 0.0, 1.0))
    # Locations stay 1.0 / 0.55 / 0.22 after the shared factor is applied.
    assert full_role / decoy == pytest.approx(1.0 / GMM_DECOY_LOC, rel=0.02)
    assert full_role / exit_ == pytest.approx(1.0 / GMM_EXIT_LOC, rel=0.10)


# --------------------------------------------------------------------------- #
# Handoff bands share the engine's median re-centering.
# --------------------------------------------------------------------------- #
def _healthy_weight_matrix(n_players: int) -> np.ndarray:
    healthy = np.array(
        [
            HEALTHY_PRIOR["full_role"],
            HEALTHY_PRIOR["snap_count_decoy"],
            HEALTHY_PRIOR["in_game_reaggravation_exit"],
        ],
        dtype=float,
    )
    return np.tile(healthy, (n_players, 1))


def test_handoff_gmm_bands_are_recentred_on_projection() -> None:
    """The handoff band median tracks the input projection, not the raw ~0.95x."""

    projections = np.array([6.0, 10.0, 14.0, 20.0, 26.0, 32.0])
    sigmas = 0.5 * projections
    weights = _healthy_weight_matrix(projections.shape[0])
    seed = 20261015
    iterations = 40_000

    bands = _gmm_bands(projections, sigmas, weights, n_iterations=iterations, seed=seed)

    # Re-centred: the sampled median lands within a few percent of the input.
    assert np.allclose(bands["median"], projections, rtol=0.03)

    # A raw (un-recentred) sample on the same inputs and seed stays biased low.
    raw_draws = sample_regime_gmm(
        projections,
        sigmas,
        weights,
        n_iterations=iterations,
        rng=np.random.default_rng(seed),
    )
    raw_medians = np.quantile(raw_draws, 0.5, axis=1)
    assert np.all(raw_medians < projections)
    assert float(np.mean(raw_medians / projections)) < 0.97
    # The two consumers of the same mixture no longer agree.
    assert np.all(bands["median"] > raw_medians)


def test_handoff_injury_blend_widens_the_band() -> None:
    """A heavy decoy/exit routing still returns a wider band than healthy."""

    medians = np.array([18.0, 18.0])
    sigmas = np.array([6.0, 6.0])
    healthy = np.array(
        [
            HEALTHY_PRIOR["full_role"],
            HEALTHY_PRIOR["snap_count_decoy"],
            HEALTHY_PRIOR["in_game_reaggravation_exit"],
        ],
        dtype=float,
    )
    injury = np.array([0.20, 0.50, 0.30], dtype=float)
    weights = np.vstack([healthy, injury])

    bands = _gmm_bands(medians, sigmas, weights, n_iterations=40_000, seed=20261015)

    healthy_band = bands["p85"][0] - bands["p15"][0]
    injury_band = bands["p85"][1] - bands["p15"][1]
    assert injury_band > healthy_band


def test_consensus_brier_beats_climatology_when_discriminating() -> None:
    from ceminidfs.pipeline.calibrate_jev import brier_consensus

    designated = pd.DataFrame(
        {
            "fd_consensus": [10.0, 10.0, 10.0, 10.0],
            "fd_actual": [20.0, 20.0, 5.0, 5.0],
            "p_above_consensus": [0.95, 0.95, 0.05, 0.05],
        }
    )
    metrics = brier_consensus(designated)
    assert metrics["score"] is not None
    assert metrics["climatology"] is not None
    assert metrics["score"] < metrics["climatology"]
    assert metrics["n"] == 4
    assert metrics["n_excluded"] == 0


def test_consensus_brier_loses_climatology_when_anti_discriminating() -> None:
    from ceminidfs.pipeline.calibrate_jev import brier_consensus

    designated = pd.DataFrame(
        {
            "fd_consensus": [10.0, 10.0, 10.0, 10.0],
            "fd_actual": [20.0, 20.0, 5.0, 5.0],
            "p_above_consensus": [0.05, 0.05, 0.95, 0.95],
        }
    )
    metrics = brier_consensus(designated)
    assert metrics["score"] is not None
    assert metrics["climatology"] is not None
    assert metrics["score"] > metrics["climatology"]


def test_consensus_brier_excludes_players_without_baseline() -> None:
    from ceminidfs.pipeline.calibrate_jev import brier_consensus

    designated = pd.DataFrame(
        {
            "fd_consensus": [10.0, float("nan"), 0.0, 10.0],
            "fd_actual": [20.0, 20.0, 20.0, 5.0],
            "p_above_consensus": [0.8, 0.8, 0.8, 0.2],
        }
    )
    metrics = brier_consensus(designated)
    assert metrics["n"] == 2  # the missing and zero baselines are dropped
    assert metrics["n_excluded"] == 2
    assert metrics["observed_rate"] == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# Position ownership normalization sums.
# --------------------------------------------------------------------------- #
def test_position_ownership_normalizes_to_fanduel_mass() -> None:
    rows = []
    for position, count, target_weight in (
        ("QB", 3, 1.0),
        ("RB", 4, 2.0),
        ("WR", 5, 3.0),
        ("TE", 2, 1.5),
        ("DEF", 2, 0.5),
    ):
        for index in range(count):
            rows.append(
                {
                    "position": position,
                    "raw_own": target_weight * (1.0 + 0.1 * index),
                }
            )
    normalized = normalize_position_ownership(rows)
    totals: dict[str, float] = {}
    for row in normalized:
        totals[row["position"]] = totals.get(row["position"], 0.0) + float(row["jev_proj_own"])
    for position, expected in POSITION_OWNERSHIP_TARGET.items():
        if position in totals:
            assert totals[position] == pytest.approx(expected, rel=1e-3)


def test_position_ownership_zero_sum_group_splits_evenly() -> None:
    rows = [{"position": "TE", "raw_own": 0.0}, {"position": "TE", "raw_own": 0.0}]
    normalized = normalize_position_ownership(rows)
    assert normalized[0]["jev_proj_own"] == pytest.approx(65.0)
    assert normalized[1]["jev_proj_own"] == pytest.approx(65.0)


# --------------------------------------------------------------------------- #
# Handoff schema.
# --------------------------------------------------------------------------- #
def test_handoff_columns_match_the_contract() -> None:
    expected = [
        "slate_id",
        "game_id",
        "player_id",
        "player_name",
        "team",
        "opp",
        "position",
        "implied_total",
        "spread",
        "fpts_median",
        "fpts_sigma",
        "jev_proj_own",
        "jev_regime_state",
        "jev_regime_conf",
        "pass_yds_median",
        "pass_yds_sigma",
        "pass_yds_p15",
        "pass_yds_p85",
        "rush_yds_median",
        "rush_yds_sigma",
        "rush_yds_p15",
        "rush_yds_p85",
        "rec_yds_median",
        "rec_yds_sigma",
        "rec_yds_p15",
        "rec_yds_p85",
        "receptions_median",
        "receptions_sigma",
        "pass_tds_mean",
        "rush_rec_tds_mean",
    ]
    assert HANDOFF_COLUMNS == expected
    assert PARLAYS_HANDOFF_HEADER == expected
    assert HANDOFF_BASE_COLUMNS == expected[:14]


def _write_run_dir(root: Path) -> None:
    from ceminidfs.pipeline.engine import normalize_join_key

    players = [
        ("00-001", "Sam Starter", "KC", "QB", "KC", "BUF", "BUF@KC"),
        ("00-002", "Wide Out", "KC", "WR", "KC", "BUF", "BUF@KC"),
    ]
    base_rows = []
    canonical_rows = []
    for player_id, name, team, position, home, opp, game in players:
        base_rows.append(
            {
                "season": 2026,
                "week": 5,
                "team": team,
                "opponent": opp,
                "opp": opp,
                "game": game,
                "player_id": player_id,
                "player_name": name,
                "position": position,
                "join_key": normalize_join_key(name, team, position),
                "fd_projection": 18.0,
                "pass_yds": 250.0,
                "pass_td": 2.0,
                "rush_yds": 10.0,
                "rush_td": 0.0,
                "rec": 4.0,
                "rec_yds": 50.0,
                "rec_td": 0.0,
            }
        )
        canonical_rows.append(
            {
                "slate_id": "2026_w5",
                "player_key": f"fd-{player_id}",
                "fd_id": f"fd-{player_id}",
                "fd_position": position,
                "fd_salary": 7000,
                "fd_projection": 18.0,
                "team": team,
                "opp": opp,
                "game": game,
                "injury_status": "Q",
                "player_name": name,
                "name": name,
                "Projected Ownership": 5.0,
            }
        )
    pd.DataFrame(base_rows).to_parquet(root / "player_projection_base.parquet", index=False)
    pd.DataFrame(canonical_rows).to_csv(root / "canonical_projections_2026_w5.csv", index=False)


def test_handoff_context_and_writer_schema(tmp_path: Path) -> None:
    _write_run_dir(tmp_path)
    context = build_handoff_context(tmp_path, n_iterations=2000)
    assert context is not None
    records = context.ordered()
    assert len(records) == 2
    starter = context.lookup("Sam Starter")
    assert starter is not None
    assert starter.slate_id == "2026_w5"
    assert starter.game_id == "BUF@KC"
    assert starter.player_id == "fd-00-001"
    assert starter.position == "QB"
    assert float(starter.fpts_median) > 0.0
    assert float(starter.fpts_sigma) > 0.0
    assert float(starter.stats["pass_yds_median"]) > 0.0

    written = write_parlays_handoff(
        tmp_path / "ceminidfs_handoff.csv",
        [],
        {},
        context=context,
    )
    header, body = _read_csv(written)
    assert header == HANDOFF_COLUMNS
    assert len(body) == 2
    by_name = {row[3]: row for row in body}
    assert by_name["Sam Starter"][0] == "2026_w5"  # slate id
    assert by_name["Sam Starter"][1] == "BUF@KC"  # game id
    assert by_name["Sam Starter"][9] != ""  # fpts_median sampled from the mixture


def test_handoff_falls_back_without_run_context(tmp_path: Path) -> None:
    context = build_handoff_context(tmp_path)  # no parquet -> None
    assert context is None

    from ceminidfs.export.review_reports import PlayerMeta

    players = {
        "sam starter": PlayerMeta(
            name="Sam Starter",
            team="KC",
            position="QB",
            positions=frozenset({"QB"}),
            game_id="BUF@KC",
            game_raw="BUF@KC",
            player_id="fd-1",
            salary="7000",
            projection="18.5",
            row={"fd_projection": "18.5", "opp": "BUF"},
        )
    }
    written = write_parlays_handoff(
        tmp_path / "fallback.csv",
        [[("QB", "Sam Starter")]],
        players,
        implied_totals={"KC": "25"},
    )
    header, body = _read_csv(written)
    assert header == HANDOFF_COLUMNS
    assert body[0][3] == "Sam Starter"
    assert body[0][7] == "25"
    assert body[0][9] == "18.5"
    assert body[0][5] == "BUF"


def test_leverage_fade_header_extends_with_jev_columns() -> None:
    assert LEVERAGE_FADE_HEADER[:5] == [
        "player",
        "lineup_exposure_pct",
        "projected_own_pct",
        "leverage",
        "flag",
    ]
    assert LEVERAGE_FADE_HEADER[5:] == [
        "jev_proj_own",
        "player_leverage_ratio",
        "jev_regime_top_state",
        "jev_provider",
    ]


def test_handoff_raises_on_existing_but_unreadable_base(tmp_path: Path) -> None:
    """A present-but-corrupt projection base must raise, not degrade to None."""

    (tmp_path / "player_projection_base.parquet").write_bytes(b"not a parquet file")

    with pytest.raises(HandoffInputError) as excinfo:
        build_handoff_context(tmp_path)
    assert "player_projection_base.parquet" in str(excinfo.value)


def test_read_canonical_raises_on_existing_but_unreadable_csv(tmp_path: Path) -> None:
    """A corrupt canonical CSV must raise; only an absent one degrades to empty."""

    (tmp_path / "canonical_projections_2025_w5.csv").write_bytes(b"\xff\xfe,,garbage\x00\x01")

    with pytest.raises(HandoffInputError) as excinfo:
        read_canonical(tmp_path)
    assert "canonical_projections_2025_w5.csv" in str(excinfo.value)


def test_read_canonical_stays_lenient_when_absent(tmp_path: Path) -> None:
    """A genuinely absent optional file stays an empty frame, not an error."""

    assert read_canonical(tmp_path).empty


def _read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with Path(path).open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    return rows[0], rows[1:]
