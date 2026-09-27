"""Rookie prior tests. Every default coefficient is zero."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.rookie_prior import (
    RookiePriorSettings,
    apply_rookie_prior,
    build_rookie_priors,
    compute_rookie_prior,
    load_college_features_csv,
)


def test_default_coefficients_return_zero_prior():
    settings = RookiePriorSettings()
    features = {
        "draft_capital": 1.0,
        "dominator_rating": 0.35,
        "breakout_age": 19.5,
        "career_yards_per_route_run": 2.8,
    }

    assert compute_rookie_prior(features, settings) == pytest.approx(0.0)
    assert build_rookie_priors({"p1": features}, settings)["p1"] == pytest.approx(0.0)


def test_explicit_coefficients_move_the_prior():
    settings = RookiePriorSettings(
        draft_capital_coefficient=0.1,
        dominator_coefficient=1.0,
        breakout_age_coefficient=-0.2,
        yards_per_route_run_coefficient=0.5,
    )
    features = {
        "draft_capital": 1.0,
        "dominator_rating": 0.30,
        "breakout_age": 20.0,
        "career_yards_per_route_run": 2.0,
    }

    # 0.1*1 + 1.0*0.30 - 0.2*20 + 0.5*2 = 0.1 + 0.3 - 4.0 + 1.0 = -2.6
    assert compute_rookie_prior(features, settings) == pytest.approx(-2.6)


def test_missing_csv_returns_empty_mapping(tmp_path: Path):
    assert load_college_features_csv(tmp_path / "missing.csv") == {}
    assert load_college_features_csv(None) == {}
    assert load_college_features_csv("") == {}


def test_loaded_csv_default_path_keeps_the_projection(tmp_path: Path):
    csv_path = _write_college_csv(tmp_path)
    features = load_college_features_csv(csv_path)
    rows = [{"player_id": "rookie1", "fd_projection": 10.0}]

    default = apply_rookie_prior(rows, features, RookiePriorSettings())

    assert features["rookie1"]["career_yards_per_route_run"] == pytest.approx(2.0)
    assert default[0]["rookie_prior"] == pytest.approx(0.0)
    assert default[0]["fd_projection"] == pytest.approx(10.0)


def test_loaded_csv_explicit_coefficient_moves_the_projection(tmp_path: Path):
    csv_path = _write_college_csv(tmp_path)
    features = load_college_features_csv(csv_path)
    rows = [{"player_id": "rookie1", "fd_projection": 10.0}]
    settings = RookiePriorSettings(yards_per_route_run_coefficient=0.5)

    moved = apply_rookie_prior(rows, features, settings)

    assert moved[0]["rookie_prior"] == pytest.approx(1.0)
    assert moved[0]["fd_projection"] == pytest.approx(11.0)


def test_csv_without_feature_columns_keeps_prior_zero(tmp_path: Path):
    csv_path = tmp_path / "college.csv"
    csv_path.write_text("player_id\nrookie1\n", encoding="utf-8")

    features = load_college_features_csv(csv_path)
    rows = [{"player_id": "rookie1", "fd_projection": 10.0}]
    settings = RookiePriorSettings(yards_per_route_run_coefficient=0.5)

    result = apply_rookie_prior(rows, features, settings)

    assert result[0]["rookie_prior"] == pytest.approx(0.0)
    assert result[0]["fd_projection"] == pytest.approx(10.0)


def test_from_config_defaults_to_zero_coefficients():
    settings = RookiePriorSettings.from_config({})

    assert settings.draft_capital_coefficient == pytest.approx(0.0)
    assert settings.dominator_coefficient == pytest.approx(0.0)
    assert settings.breakout_age_coefficient == pytest.approx(0.0)
    assert settings.yards_per_route_run_coefficient == pytest.approx(0.0)


def _write_college_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "college_features.csv"
    csv_path.write_text(
        "player_id,player_name,draft_capital,dominator_rating,breakout_age,"
        "career_yards_per_route_run\n"
        "rookie1,Rookie One,12,0.30,20.0,2.0\n",
        encoding="utf-8",
    )
    return csv_path
