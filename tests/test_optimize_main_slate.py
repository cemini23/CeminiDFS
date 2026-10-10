import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("pydfs_lineup_optimizer")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.export.normalize import normalize_csv
from ceminidfs.export.optimize import (
    _is_tiny_slate,
    _relax_tiny_slate_limits,
    generate_lineups,
    optimize_lineups,
)
from ceminidfs.export.stack_rules import nfl_positions


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


def test_classic_qb3_stack_composition(tmp_path: Path):
    salary_path = Path(__file__).resolve().parent / "fixtures" / "synthetic_fd_slate.csv"
    players_path = tmp_path / "players.csv"
    normalize_csv(salary_path, players_path, site="fanduel")

    lineups = generate_lineups(
        players_path,
        site="fanduel",
        count=1,
        stacks=["qb:3"],
        max_exposure=1.0,
        min_salary=0,
    )

    assert lineups
    for lineup in lineups:
        qbs = [player for player in lineup.players if "QB" in nfl_positions(player)]
        assert len(qbs) == 1
        qb = qbs[0]
        wr_te = [
            player
            for player in lineup.players
            if player.team == qb.team and nfl_positions(player) & {"WR", "TE"}
        ]
        assert len(wr_te) >= 2


def test_questionable_player_stays_eligible_and_can_lock(tmp_path: Path):
    salary_path = Path(__file__).resolve().parent / "fixtures" / "synthetic_fd_slate.csv"
    marked = tmp_path / "salary_q.csv"
    with salary_path.open(encoding="utf-8-sig") as src, marked.open("w", newline="", encoding="utf-8") as dest:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dest, fieldnames=list(reader.fieldnames or []))
        writer.writeheader()
        for row in reader:
            if row.get("Nickname") == "Isiah Pacheco":
                row["Injury Indicator"] = "Q"
            writer.writerow(row)

    players_path = tmp_path / "players.csv"
    normalize_csv(marked, players_path, site="fanduel")
    rows = list(csv.DictReader(players_path.open(encoding="utf-8-sig")))
    pacheco = next(row for row in rows if row.get("Last Name") == "Pacheco")
    assert pacheco.get("Injury Indicator") == "Q"

    lineups = generate_lineups(
        players_path,
        site="fanduel",
        count=1,
        locks=["Isiah Pacheco"],
        max_exposure=1.0,
        min_salary=0,
    )

    assert lineups
    for lineup in lineups:
        names = {player.full_name for player in lineup.players}
        assert "Isiah Pacheco" in names


def test_player_exposure_cap_refuses_a_short_book(tmp_path: Path):
    """A book that cannot meet the requested count raises and writes nothing."""
    salary_path = Path(__file__).resolve().parent / "fixtures" / "synthetic_fd_slate.csv"
    players_path = tmp_path / "players.csv"
    normalize_csv(salary_path, players_path, site="fanduel")

    real_lineups = generate_lineups(
        players_path,
        site="fanduel",
        count=1,
        max_exposure=1.0,
        min_salary=0,
    )
    assert len(real_lineups) == 1
    template = real_lineups[0]

    import ceminidfs.export.optimize as opt_module

    out_csv = tmp_path / "lineups.csv"
    with (
        patch.object(opt_module, "_optimize_or_raise", return_value=[template] * 10),
        pytest.raises(ValueError, match=r"wrote 3 lineups; requested 10"),
    ):
        optimize_lineups(
            players_path,
            out_csv,
            site="fanduel",
            count=10,
            max_exposure=0.3,
            max_team_exposure=0.4,
            min_salary=0,
        )

    assert not out_csv.exists()
    assert not out_csv.with_name("lineups_fanduel_upload.csv").exists()


def test_generate_lineups_default_max_exposure_is_035():
    import inspect
    from ceminidfs.export.optimize import generate_lineups

    sig = inspect.signature(generate_lineups)
    default = sig.parameters["max_exposure"].default
    assert default == 0.35
