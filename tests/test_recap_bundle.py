"""The self-contained recap handoff bundle."""

import csv
from pathlib import Path

import pytest

pytest.importorskip("pydfs_lineup_optimizer")

from ceminidfs.cli import build_parser
from ceminidfs.config import load_config
from ceminidfs.orchestrator.run import _run_optimize

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
    "Opponent",
]

POOL = [
    ("1", "Patrick", "Mahomes", "QB", "KC", "8000", "30", "BUF"),
    ("2", "Isiah", "Pacheco", "RB", "KC", "6100", "18", "BUF"),
    ("3", "Kareem", "Hunt", "RB", "KC", "5200", "12", "BUF"),
    ("4", "Rashee", "Rice", "WR", "KC", "6400", "16", "BUF"),
    ("5", "Xavier", "Worthy", "WR", "KC", "5600", "14", "BUF"),
    ("6", "Travis", "Kelce", "TE", "KC", "7000", "17", "BUF"),
    ("7", "Kansas City", "Chiefs", "D", "KC", "3600", "8", "BUF"),
    ("8", "Josh", "Allen", "QB", "BUF", "8100", "29", "KC"),
    ("9", "James", "Cook", "RB", "BUF", "6800", "17", "KC"),
    ("10", "Ray", "Davis", "RB", "BUF", "5000", "11", "KC"),
    ("11", "Khalil", "Shakir", "WR", "BUF", "5900", "13", "KC"),
    ("12", "Stefon", "Diggs", "WR", "BUF", "6200", "15", "KC"),
    ("13", "Dalton", "Kincaid", "TE", "BUF", "5500", "12", "KC"),
    ("14", "Buffalo", "Bills", "D", "BUF", "3500", "7", "KC"),
    ("15", "Joe", "Burrow", "QB", "CIN", "7900", "28", "KC"),
    ("16", "Ja'Marr", "Chase", "WR", "CIN", "8200", "24", "KC"),
    ("17", "Tee", "Higgins", "WR", "CIN", "7100", "18", "KC"),
    ("18", "Chase", "Brown", "RB", "CIN", "6000", "15", "KC"),
    ("19", "Mike", "Gesicki", "WR", "CIN", "4500", "8", "KC"),
    ("20", "Cincinnati", "Bengals", "D", "CIN", "3400", "6", "KC"),
]


def _write_pool(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for player_id, first, last, pos, team, salary, fppg, opp in POOL:
            game = f"{team}@{opp} 01:00PM ET"
            writer.writerow([player_id, first, last, pos, team, salary, fppg, game, "", opp])
    return path


def test_optimize_and_run_accept_the_recap_bundle_flags():
    parser = build_parser()

    args = parser.parse_args(
        [
            "optimize",
            "--csv",
            "players.csv",
            "--out",
            "lineups.csv",
            "--recap-bundle-dir",
            "bundle",
            "--exposure-override",
            "Kenneth Gainwell=0.35",
        ]
    )

    assert args.recap_bundle_dir == Path("bundle")
    assert args.exposure_override == ["Kenneth Gainwell=0.35"]


def test_recap_bundle_writes_four_non_empty_files(tmp_path: Path):
    players = _write_pool(tmp_path / "players.csv")
    out = tmp_path / "lineups.csv"
    bundle = tmp_path / "bundle"
    config = {
        "salary_path": str(players),
        "recap_bundle_dir": str(bundle),
        "max_exposure": 1.0,
        "min_salary": 0,
        "exposure_tiers": load_config(profile="gpp")["exposure_tiers"],
    }

    _run_optimize(players, out, 2, config)

    salary_copy = bundle / "_src_fd_sun.csv"
    lineups_copy = bundle / "_src_lineups.csv"
    projections = list(bundle.glob("projections_*.csv"))
    reports = list(bundle.glob("exposure_report_*.md"))

    assert salary_copy.is_file() and salary_copy.stat().st_size > 0
    assert lineups_copy.is_file() and lineups_copy.stat().st_size > 0
    assert len(projections) == 1 and projections[0].stat().st_size > 0
    assert len(reports) == 1 and reports[0].stat().st_size > 0

    assert salary_copy.read_bytes() == players.read_bytes()

    with projections[0].open(encoding="utf-8") as handle:
        projection_ids = {row["player_id"] for row in csv.DictReader(handle)}
    assert projection_ids == {row[0] for row in POOL}

    report_text = reports[0].read_text(encoding="utf-8")
    assert "## Tiered-cap audit" in report_text
    assert "## Questionable / role-cliff players" in report_text
