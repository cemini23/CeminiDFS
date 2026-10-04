"""Week 4 P0: the optimizer reads the model, and the role gate drops a 0-touch name."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("pydfs_lineup_optimizer")

from ceminidfs.export.normalize import normalize_csv
from ceminidfs.export.pool_guards import apply_participation_gate, names_with_participation
from ceminidfs.orchestrator.run import _canonical_for_sim, run_pipeline

CANONICAL_HEADER = [
    "name",
    "fd_id",
    "fd_position",
    "fd_salary",
    "fd_projection",
    "team",
    "opp",
    "game",
    "injury_status",
]

POOL = [
    ("QB One", "QB", "5000", "18.00", ""),
    ("RB One", "RB", "5000", "12.00", ""),
    ("RB Two", "RB", "5000", "11.00", ""),
    ("WR One", "WR", "5000", "10.00", ""),
    ("WR Two", "WR", "5000", "9.50", ""),
    ("WR Three", "WR", "5000", "9.00", ""),
    ("Brock Bowers", "TE", "5000", "7.08", ""),
    ("WR Four", "WR", "5000", "8.50", ""),
    ("Kansas City Chiefs", "DEF", "5000", "6.00", ""),
]


def _write_canonical(path: Path, rows: list[tuple[str, str, str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_HEADER)
        writer.writeheader()
        for index, (name, pos, salary, projection, injury) in enumerate(rows, start=1):
            writer.writerow(
                {
                    "name": name,
                    "fd_id": str(index),
                    "fd_position": pos,
                    "fd_salary": salary,
                    "fd_projection": projection,
                    "team": "KC",
                    "opp": "BUF",
                    "game": "KC@BUF",
                    "injury_status": injury,
                }
            )


def _write_salary(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["Id", "Nickname", "Position", "Team", "Opponent", "Salary", "FPPG", "Injury Indicator"]
        )
        for index, (name, pos, salary, _projection, injury) in enumerate(POOL, start=1):
            writer.writerow([index, name, pos, "KC", "BUF", salary, "25.60", injury])


def _normalized_by_name(path: Path) -> dict[str, dict[str, str]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    return {f"{row['First Name']} {row['Last Name']}".strip(): row for row in rows}


def _touch_frame() -> pd.DataFrame:
    """Three plays. A pass attempt, a target, and a rush. Week 4 does not count."""

    return pd.DataFrame(
        [
            {
                "week": 1,
                "pass": 1,
                "pass_attempt": 1,
                "rush": 0,
                "passer_player_name": "Starter QB",
                "receiver_player_name": "Questionable TE",
                "rusher_player_name": None,
            },
            {
                "week": 2,
                "pass": 0,
                "pass_attempt": 0,
                "rush": 1,
                "passer_player_name": None,
                "receiver_player_name": None,
                "rusher_player_name": "Touched RB",
            },
            {
                "week": 4,
                "pass": 0,
                "pass_attempt": 0,
                "rush": 1,
                "passer_player_name": None,
                "receiver_player_name": None,
                "rusher_player_name": "Late Debut",
            },
        ]
    )


def test_optimize_stage_keeps_model_projection(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    salary = tmp_path / "salary.csv"
    _write_salary(salary)
    _write_canonical(work / "canonical_projections_1999_w9.csv", POOL)
    # The decoy file carries the salary number. The season-week file carries the model.
    decoy = work / "canonical_projections_1999_w9.csv"
    text = decoy.read_text(encoding="utf-8").replace("7.08", "25.60")
    decoy.write_text(text, encoding="utf-8")
    _write_canonical(work / "canonical_projections_2026_w1.csv", POOL)

    run_pipeline(
        2026,
        1,
        salary,
        stages="optimize",
        config={"work_dir": work, "site": "fanduel", "count": 1, "min_salary": 0},
    )

    rows = _normalized_by_name(work / "normalized_players.csv")
    assert float(rows["Brock Bowers"]["FPPG"]) == 7.08
    for name, _pos, _salary, projection, _injury in POOL:
        assert float(rows[name]["FPPG"]) == float(projection)


def test_optimize_without_canonical_raises_and_writes_nothing(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    salary = tmp_path / "salary.csv"
    _write_salary(salary)

    with pytest.raises(FileNotFoundError, match=str(work)):
        run_pipeline(
            2026,
            1,
            salary,
            stages="optimize",
            config={"work_dir": work, "site": "fanduel", "count": 1},
        )

    assert not (work / "normalized_players.csv").exists()


def test_optimize_refuses_when_canonical_path_is_the_salary_file(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    salary = work / "canonical_projections_2026_w1.csv"
    _write_salary(salary)

    with pytest.raises(ValueError, match="salary CSV"):
        run_pipeline(
            2026,
            1,
            salary,
            stages="optimize",
            config={"work_dir": work, "site": "fanduel", "count": 1},
        )

    assert not (work / "normalized_players.csv").exists()


def test_names_with_participation_uses_rush_target_and_pass(tmp_path: Path):
    del tmp_path
    names = names_with_participation(_touch_frame(), through_week=3)
    assert names == {"starter qb", "questionable te", "touched rb"}


def test_role_gate_drops_zero_touch_and_keeps_questionable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    work = tmp_path / "work"
    work.mkdir()
    rows = [
        ("Zero Touch", "WR", "5000", "9.00", ""),
        ("Questionable TE", "TE", "5000", "8.00", "Q"),
        ("Starter QB", "QB", "8000", "18.00", ""),
        ("Touched RB", "RB", "6000", "12.00", ""),
        ("Late Debut", "WR", "5000", "7.00", ""),
        ("Buffalo Bills", "DEF", "4000", "6.00", ""),
    ]
    _write_canonical(work / "canonical_projections_1999_w4.csv", rows)

    run_pipeline(
        1999,
        4,
        tmp_path / "salary.csv",
        stages="normalize",
        config={
            "work_dir": work,
            "site": "fanduel",
            "participation_pbp": _touch_frame(),
        },
    )

    kept = _normalized_by_name(work / "normalized_players.csv")
    assert "Zero Touch" not in kept
    assert "Late Debut" not in kept
    assert kept["Questionable TE"]["Injury Indicator"] == "Q"
    assert kept["Starter QB"]["Position"] == "QB"
    assert kept["Touched RB"]["Position"] == "RB"
    assert kept["Buffalo Bills"]["Position"] == "D"
    assert "role gate: floor=1 touch in weeks 1..3; dropped=2" in capsys.readouterr().err


def test_week_one_role_gate_drops_nobody(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    def _boom(season: int) -> pd.DataFrame:
        raise AssertionError(f"week 1 must not load play-by-play ({season})")

    monkeypatch.setattr("ceminidfs.pipeline.backtest.load_season_pbp", _boom)
    work = tmp_path / "work"
    work.mkdir()
    _write_canonical(
        work / "canonical_projections_1999_w1.csv",
        [("Zero Touch", "WR", "5000", "9.00", "")],
    )

    run_pipeline(
        1999,
        1,
        tmp_path / "unused-salary.csv",
        stages="normalize",
        config={"work_dir": work, "site": "fanduel"},
    )

    kept = _normalized_by_name(work / "normalized_players.csv")
    assert "Zero Touch" in kept
    assert "role gate: floor=1 touch in weeks 1..0; dropped=0" in capsys.readouterr().err


def test_allow_stub_skips_role_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    def _boom(season: int) -> pd.DataFrame:
        raise AssertionError(f"allow_stub must not load play-by-play ({season})")

    monkeypatch.setattr("ceminidfs.pipeline.backtest.load_season_pbp", _boom)
    work = tmp_path / "work"
    work.mkdir()
    _write_canonical(
        work / "canonical_projections_1999_w4.csv",
        [("Zero Touch", "WR", "5000", "9.00", "")],
    )

    run_pipeline(
        1999,
        4,
        tmp_path / "unused-salary.csv",
        stages="normalize",
        config={"work_dir": work, "site": "fanduel", "allow_stub": True},
    )

    kept = _normalized_by_name(work / "normalized_players.csv")
    assert "Zero Touch" in kept
    assert "role gate: skipped (allow_stub)" in capsys.readouterr().err


def test_missing_pbp_raises_before_normalized_pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _missing(season: int) -> pd.DataFrame:
        raise FileNotFoundError(f"no pbp for {season}")

    monkeypatch.setattr("ceminidfs.pipeline.backtest.load_season_pbp", _missing)
    work = tmp_path / "work"
    work.mkdir()
    _write_canonical(
        work / "canonical_projections_1999_w4.csv",
        [("Zero Touch", "WR", "5000", "9.00", "")],
    )

    with pytest.raises(FileNotFoundError, match="no pbp"):
        run_pipeline(
            1999,
            4,
            tmp_path / "unused-salary.csv",
            stages="normalize",
            config={"work_dir": work, "site": "fanduel"},
        )

    assert not (work / "normalized_players.csv").exists()


def test_apply_participation_gate_on_three_row_frame():
    frame = _touch_frame()
    names = names_with_participation(frame, through_week=3)
    rows = [
        {"First Name": "Zero", "Last Name": "Touch", "Position": "WR"},
        {"First Name": "Questionable", "Last Name": "TE", "Position": "TE", "Injury Indicator": "Q"},
        {"First Name": "Buffalo", "Last Name": "Bills", "Position": "D"},
    ]
    kept = apply_participation_gate(rows, names, week=4)
    names_kept = {f"{row['First Name']} {row['Last Name']}" for row in kept}
    assert names_kept == {"Questionable TE", "Buffalo Bills"}


def test_walker_stays_kc_and_likely_stays_nyg(tmp_path: Path):
    source = tmp_path / "canonical.csv"
    source.write_text(
        "name,fd_id,fd_position,fd_salary,fd_projection,team,opp\n"
        "Kenneth Walker III,1,RB,6100,8.10,KC,LV\n"
        "Isaiah Likely,2,TE,5400,6.20,NYG,DAL\n",
        encoding="utf-8",
    )
    output = tmp_path / "normalized.csv"
    normalize_csv(source, output, site="fanduel")
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    by_name = {f"{row['First Name']} {row['Last Name']}": row for row in rows}
    assert by_name["Kenneth Walker III"]["Team"] == "KC"
    assert by_name["Isaiah Likely"]["Team"] == "NYG"


def test_optimize_raises_when_only_another_week_file_exists(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    salary = tmp_path / "salary.csv"
    _write_salary(salary)
    # w10 sorts before w4. The old helper returned that file.
    _write_canonical(work / "canonical_projections_2026_w10.csv", POOL)

    with pytest.raises(FileNotFoundError, match="canonical_projections_2026_w4.csv"):
        run_pipeline(
            2026,
            4,
            salary,
            stages="optimize",
            config={"work_dir": work, "site": "fanduel", "count": 1},
        )

    assert not (work / "normalized_players.csv").exists()


def test_canonical_for_sim_uses_the_week_file(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    week_file = work / "canonical_projections_2026_w4.csv"
    other_file = work / "canonical_projections_2026_w10.csv"
    week_file.write_text("week\n", encoding="utf-8")
    other_file.write_text("other\n", encoding="utf-8")

    chosen = _canonical_for_sim({"work_dir": work, "season": 2026, "week": 4})

    assert chosen == week_file


def test_canonical_for_sim_rejects_another_week_file(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "canonical_projections_2026_w10.csv").write_text("other\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Refusing to use another canonical file"):
        _canonical_for_sim({"work_dir": work, "season": 2026, "week": 4})


def test_canonical_for_sim_returns_none_when_the_folder_is_empty(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()

    assert _canonical_for_sim({"work_dir": work, "season": 2026, "week": 4}) is None


def test_canonical_for_sim_honors_an_explicit_path(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "canonical_projections_2026_w10.csv").write_text("other\n", encoding="utf-8")
    explicit = tmp_path / "pinned.csv"
    explicit.write_text("pinned\n", encoding="utf-8")

    chosen = _canonical_for_sim(
        {
            "work_dir": work,
            "season": 2026,
            "week": 4,
            "canonical_path": explicit,
        }
    )

    assert chosen == explicit
