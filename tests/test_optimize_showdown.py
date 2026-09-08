"""Showdown (6-man single-game) normalize + optimize + validate coverage.

FanDuel 2026 single-game is MVP 1.5x salary AND points, $60k, max 5 from one
team, DST allowed — modeled on DraftKings captain mode via pydfs
``Site.DRAFTKINGS_CAPTAIN_MODE`` (not the obsolete 1+4 ``FANDUEL_SINGLE_GAME``).
"""

import csv
from pathlib import Path

import pytest

pytest.importorskip("pydfs_lineup_optimizer")

from ceminidfs.export.normalize import normalize_csv, normalize_site
from ceminidfs.export.optimize import (
    DEFAULT_MIN_SALARY,
    LINEUP_HEADERS,
    SHOWDOWN_SITES,
    generate_lineups,
    lineup_to_row,
    write_lineup_rows,
)
from ceminidfs.orchestrator.validate import SALARY_CAPS, validate_lineups_csv

# 1x (FLEX) lobby salaries; the FD pool sits at the $60k scale, the DK pool at
# $50k, so each site can fill its own budget with 6 of these 10 players.
_FD_PLAYERS = [
    # SEA
    ("Sam Darnold", "QB", "SEA", 15000, 24.5),
    ("Jadarian Price", "RB", "SEA", 12000, 19.8),
    ("Jaxon Smith-Njigba", "WR", "SEA", 10000, 16.2),
    ("AJ Barner", "TE", "SEA", 8000, 11.4),
    ("Seahawks", "DST", "SEA", 6000, 9.1),
    # NE
    ("Drake Maye", "QB", "NE", 13000, 22.0),
    ("Rhamondre Stevenson", "RB", "NE", 11000, 17.5),
    ("A.J. Brown", "WR", "NE", 9500, 15.0),
    ("Hunter Henry", "TE", "NE", 7500, 10.2),
    ("Patriots", "DST", "NE", 5500, 8.4),
]

_DK_PLAYERS = [
    # SEA
    ("Sam Darnold", "QB", "SEA", 12000, 24.5),
    ("Jadarian Price", "RB", "SEA", 9500, 19.8),
    ("Jaxon Smith-Njigba", "WR", "SEA", 8200, 16.2),
    ("AJ Barner", "TE", "SEA", 6500, 11.4),
    ("Seahawks", "DST", "SEA", 5000, 9.1),
    # NE
    ("Drake Maye", "QB", "NE", 10500, 22.0),
    ("Rhamondre Stevenson", "RB", "NE", 8800, 17.5),
    ("A.J. Brown", "WR", "NE", 7500, 15.0),
    ("Hunter Henry", "TE", "NE", 6000, 10.2),
    ("Patriots", "DST", "NE", 4500, 8.4),
]


def _write_players(path: Path, rows: list[tuple[str, str, str, int, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Position", "Team", "Salary", "FPPG"])
        writer.writerows(rows)


def _showdown_flow(
    tmp_path: Path,
    site: str,
    rows: list[tuple[str, str, str, int, float]],
    count: int = 2,
) -> tuple[Path, Path, object]:
    """normalize -> optimize -> write lineups CSV; return (captain_csv, lineups_csv, lineups)."""
    source = tmp_path / f"{site}_source.csv"
    captain_csv = tmp_path / f"{site}_captain.csv"
    lineups_csv = tmp_path / f"{site}_lineups.csv"
    _write_players(source, rows)
    normalize_csv(source, captain_csv, site=site)
    lineups = generate_lineups(captain_csv, site=site, count=count)
    write_lineup_rows(
        [lineup_to_row(lineup, site) for lineup in lineups],
        lineups_csv,
        site=site,
    )
    return captain_csv, lineups_csv, lineups


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


@pytest.mark.parametrize("site", ["fanduel_showdown", "draftkings_showdown"])
def test_showdown_aliases_normalize_to_canonical(site: str):
    assert normalize_site(site) == site
    assert site in SHOWDOWN_SITES


def test_normalize_site_accepts_showdown_aliases():
    assert normalize_site("fd_showdown") == "fanduel_showdown"
    assert normalize_site("fd_single") == "fanduel_showdown"
    assert normalize_site("dk_showdown") == "draftkings_showdown"
    assert normalize_site("dk_captain") == "draftkings_showdown"
    assert normalize_site("draftkings_captain") == "draftkings_showdown"


def test_showdown_normalize_emits_cpt_and_flex_rows_shared_id(tmp_path: Path):
    for site, rows in (
        ("fanduel_showdown", _FD_PLAYERS),
        ("draftkings_showdown", _DK_PLAYERS),
    ):
        captain_csv = tmp_path / f"{site}_captain.csv"
        _write_players(tmp_path / f"{site}_source.csv", rows)
        normalize_csv(tmp_path / f"{site}_source.csv", captain_csv, site=site)

        fieldnames, data = _read_csv(captain_csv)
        # 10 players -> 20 captain-mode rows (CPT 1.5x + FLEX 1x per player).
        assert len(data) == len(rows) * 2
        assert "Roster Position" in fieldnames

        by_player: dict[str, dict[str, int]] = {}
        for row in data:
            assert row["Roster Position"] in ("CPT", "FLEX")
            by_player.setdefault(row["ID"], {})[row["Roster Position"]] = int(row["Salary"])
        assert len(by_player) == len(rows)
        for player_id, salaries in by_player.items():
            assert set(salaries) == {"CPT", "FLEX"}
            assert salaries["CPT"] == round(salaries["FLEX"] * 1.5)
        assert any(row["Position"] == "DST" for row in data)


def test_draftkings_showdown_passthrough_does_not_double(tmp_path: Path):
    """A source that is already a DK captain-mode CSV passes through unchanged."""
    source = tmp_path / "dk_captain_source.csv"
    rows = [
        ("QB", "Sam Darnold", 1000, "CPT", 12000, 24.5),
        ("QB", "Sam Darnold", 1000, "FLEX", 8000, 24.5),
        ("DST", "Seahawks", 1001, "CPT", 7500, 9.1),
        ("DST", "Seahawks", 1001, "FLEX", 5000, 9.1),
    ]
    with source.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["Position", "Name", "ID", "Roster Position", "Salary", "AvgPointsPerGame"]
        )
        writer.writerows(rows)

    out = tmp_path / "dk_passthrough.csv"
    normalize_csv(source, out, site="draftkings_showdown")

    fieldnames, data = _read_csv(out)
    assert len(data) == len(rows)
    assert "Roster Position" in fieldnames
    assert all(row["Roster Position"] in ("CPT", "FLEX") for row in data)
    by_id = {row["ID"] for row in data}
    assert by_id == {"1000", "1001"}


@pytest.mark.parametrize(
    ("site", "rows", "cap"),
    [
        ("fanduel_showdown", _FD_PLAYERS, SALARY_CAPS["fanduel_showdown"]),
        ("draftkings_showdown", _DK_PLAYERS, SALARY_CAPS["draftkings_showdown"]),
    ],
)
def test_showdown_optimize_and_validate(
    tmp_path: Path,
    site: str,
    rows: list[tuple[str, str, str, int, float]],
    cap: int,
):
    captain_csv, lineups_csv, lineups = _showdown_flow(tmp_path, site, rows, count=2)

    assert len(lineups) == 2
    for lineup in lineups:
        players = list(lineup.players)
        assert len(players) == 6
        names = [player.full_name for player in players]
        assert len(names) == len(set(names)), "CPT and FLEX of one player both selected"
        captain = next(player for player in players if player.lineup_position == "CPT")
        assert sum(player.salary for player in players) <= cap
        assert captain is not None

    expected_header = LINEUP_HEADERS[site]
    assert len(expected_header) == 6
    assert expected_header[0] == ("MVP" if site == "fanduel_showdown" else "CPT")

    # Roster CSV rows line up with the header and pass site validation
    # (including salary lookup off the captain-mode players CSV).
    fieldnames, _data = _read_csv(lineups_csv)
    assert fieldnames == expected_header

    result = validate_lineups_csv(
        lineups_csv,
        site=site,
        expected_count=2,
        players_csv=captain_csv,
    )
    assert result["valid"] is True
    assert result["lineup_count"] == 2
    assert result["site"] == site


def test_showdown_first_row_slot_is_captain(tmp_path: Path):
    """The first CSV column holds the MVP/CPT player of each lineup."""
    for site, rows in (
        ("fanduel_showdown", _FD_PLAYERS),
        ("draftkings_showdown", _DK_PLAYERS),
    ):
        _captain_csv, lineups_csv, _lineups = _showdown_flow(tmp_path, site, rows, count=2)
        with lineups_csv.open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            rows_out = list(reader)

        assert header[0] == ("MVP" if site == "fanduel_showdown" else "CPT")
        # Header MVP/CPT must not be empty for any lineup.
        assert all(row[0].strip() for row in rows_out)
        # First column name must be present in the captain-mode players CSV.
        fieldnames, data = _read_csv(_captain_csv)
        assert "Name" in fieldnames
        captain_names = {row["Name"].strip() for row in data if row["Roster Position"] == "CPT"}
        assert all(row[0].strip() in captain_names for row in rows_out)


def test_showdown_headers_and_caps_registered():
    assert LINEUP_HEADERS["fanduel_showdown"] == ["MVP", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"]
    assert LINEUP_HEADERS["draftkings_showdown"] == ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"]
    assert DEFAULT_MIN_SALARY["fanduel_showdown"] == 56000
    assert DEFAULT_MIN_SALARY["draftkings_showdown"] == 45000
    assert SALARY_CAPS["fanduel_showdown"] == 60000
    assert SALARY_CAPS["draftkings_showdown"] == 50000


def test_classic_fanduel_headers_still_nine_columns():
    assert LINEUP_HEADERS["fanduel"] == ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DEF"]
    assert LINEUP_HEADERS["draftkings"] == ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
    assert len(LINEUP_HEADERS["fanduel"]) == 9
    assert len(LINEUP_HEADERS["draftkings"]) == 9
