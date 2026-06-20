import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("pydfs_lineup_optimizer")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.export.optimize import _is_tiny_slate, _relax_tiny_slate_limits


def test_is_tiny_slate_false_for_six_team_pool():
    optimizer = SimpleNamespace(
        player_pool=SimpleNamespace(available_teams=["KC", "BUF", "PHI", "DAL", "DET", "GB"])
    )

    assert _is_tiny_slate(optimizer) is False


def test_relax_tiny_slate_limits_skips_main_slate():
    class Settings:
        max_from_one_team = 4
        min_teams = 3

    optimizer = SimpleNamespace(
        player_pool=SimpleNamespace(available_teams=["KC", "BUF", "PHI", "DAL", "DET", "GB"]),
        settings=Settings(),
    )

    _relax_tiny_slate_limits(optimizer, "fanduel")

    assert optimizer.settings.max_from_one_team == 4
    assert optimizer.settings.min_teams == 3
