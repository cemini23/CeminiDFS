"""The short-slate profile and its pre-upload validation."""

from __future__ import annotations

import csv
from argparse import Namespace
from pathlib import Path

import pytest

from ceminidfs.cli import _apply_short_slate, main
from ceminidfs.config import load_config
from ceminidfs.export.exposure_tiers import exposure_tier_config

pytest.importorskip("pydfs_lineup_optimizer")

TEAMS = ("CHI", "DET", "PHI", "DAL", "KC", "BUF")
ROSTER = (
    ("QB", 8000, 20),
    ("RB", 7000, 15),
    ("RB", 6500, 12),
    ("WR", 7500, 16),
    ("WR", 7000, 14),
    ("WR", 6500, 12),
    ("TE", 6500, 12),
    ("D", 4500, 8),
    ("WR", 6000, 11),
)
HEADER = [
    "Id",
    "First Name",
    "Last Name",
    "Position",
    "Team",
    "Salary",
    "FPPG",
    "Game",
    "Injury Indicator",
]


def test_short_slate_merge_replaces_the_ten_game_caps() -> None:
    config = load_config(profile="gpp")

    _apply_short_slate(config, Namespace(short_slate=True))

    assert config["max_exposure"] == pytest.approx(0.65)
    assert config["min_salary"] == 57500
    assert config["uniques"] == 2
    tiers = exposure_tier_config(config)
    assert tiers is not None
    assert tiers.stud_cap == pytest.approx(0.65)
    assert tiers.mid_cap == pytest.approx(0.35)
    assert tiers.value_cap == pytest.approx(0.20)
    assert config["gates"]["core"]["enabled"] is False
    assert config["gates"]["low_ceiling"]["enabled"] is True
    assert config["gates"]["exposure_hatch"]["enabled"] is False


def test_plain_gpp_profile_is_unchanged() -> None:
    config = load_config(profile="gpp")

    assert config["max_exposure"] == pytest.approx(0.20)
    tiers = exposure_tier_config(config)
    assert tiers is not None
    assert tiers.stud_cap == pytest.approx(0.35)
    assert tiers.mid_cap == pytest.approx(0.20)
    assert tiers.value_cap == pytest.approx(0.12)
    assert config.get("uniques") is None
    assert config.get("min_salary") != 57500
    assert config["gates"]["core"]["enabled"] is True


def _write_slate(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for team_index, team in enumerate(TEAMS):
            opponent = TEAMS[(team_index + 1) % len(TEAMS)]
            game = f"{team}@{opponent} 12:30PM ET"
            for slot, (position, salary, fppg) in enumerate(ROSTER):
                player_id = f"134251-{team_index * 100 + slot + 1}"
                first = team
                last = f"{position}{slot}"
                writer.writerow(
                    [
                        player_id,
                        first,
                        last,
                        position,
                        team,
                        salary + team_index * 150,
                        fppg + team_index * 0.7,
                        game,
                        "",
                    ]
                )
    return path


def _fake_stage(bundle: Path, cells: str):
    def _run(csv_path, out_path, count, config):
        (bundle / "_src_lineups.csv").write_text(
            "QB,RB,RB,WR,WR,WR,TE,FLEX,DEF\n" + cells + "\n", encoding="utf-8"
        )
        Path(out_path).write_text("QB,RB,RB,WR,WR,WR,TE,FLEX,DEF\n", encoding="utf-8")
        return Path(out_path)

    return _run


def test_short_slate_cli_applies_config_and_validates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    players = _write_slate(tmp_path / "players.csv")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    seen: dict = {}

    def _run(csv_path, out_path, count, config):
        seen.update(config)
        return _fake_stage(bundle, "134251-1,134251-2,134251-3,134251-4,134251-5,134251-6,134251-7,134251-8,134251-9")(
            csv_path, out_path, count, config
        )

    monkeypatch.setattr("ceminidfs.cli._run_optimize", _run)

    code = main(
        [
            "optimize",
            "--csv",
            str(players),
            "--out",
            str(tmp_path / "lineups.csv"),
            "--profile",
            "gpp",
            "--short-slate",
            "--count",
            "1",
            "--final-count",
            "1",
            "--recap-bundle-dir",
            str(bundle),
            "--expected-count",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert seen["max_exposure"] == pytest.approx(0.65)
    assert seen["min_salary"] == 57500
    assert seen["uniques"] == 2
    assert seen["gates"]["core"]["enabled"] is False
    assert seen["exposure_tiers"]["stud"]["cap"] == pytest.approx(0.65)


def test_short_slate_cli_refuses_a_bad_upload_book(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    players = _write_slate(tmp_path / "players.csv")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    monkeypatch.setattr(
        "ceminidfs.cli._run_optimize",
        _fake_stage(
            bundle,
            "999-1,134251-2,134251-3,134251-4,134251-5,134251-6,134251-7,134251-8,134251-9",
        ),
    )

    code = main(
        [
            "optimize",
            "--csv",
            str(players),
            "--out",
            str(tmp_path / "lineups.csv"),
            "--profile",
            "gpp",
            "--short-slate",
            "--count",
            "1",
            "--final-count",
            "1",
            "--recap-bundle-dir",
            str(bundle),
            "--expected-count",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert code == 1
    assert "upload not ready" in captured.err
