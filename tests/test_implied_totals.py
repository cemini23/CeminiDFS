import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.models.implied_totals import (
    GameEnvironmentInputs,
    game_environment_score,
    implied_team_total,
    implied_totals_from_favorite,
    implied_totals_from_spreads,
)


def test_implied_team_total_from_signed_spread():
    assert implied_team_total(total=47, spread=-3) == 25
    assert implied_team_total(total=47, spread=3) == 22


def test_implied_totals_from_favorite_signed_spread():
    totals = implied_totals_from_favorite(total=47, favorite_spread=-3)

    assert totals.favorite == 25
    assert totals.underdog == 22


def test_implied_totals_from_favorite_absolute_spread():
    totals = implied_totals_from_favorite(total=47, favorite_spread=3)

    assert totals.favorite == 25
    assert totals.underdog == 22


def test_implied_totals_from_spreads():
    team_total, opponent_total = implied_totals_from_spreads(total=47, team_spread=-3)

    assert team_total == 25
    assert opponent_total == 22


def test_game_environment_score_placeholder_defaults_to_total_z_score():
    score = game_environment_score(GameEnvironmentInputs(total=48.5))

    assert score == pytest.approx(0.6)

