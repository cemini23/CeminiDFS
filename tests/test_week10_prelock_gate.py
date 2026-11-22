"""Week 10 pre-lock gate: scratch status, backup QBs, join keys, and reports."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from ceminidfs.cli import build_parser, main
from ceminidfs.data.availability import (
    PrelockExcludeError,
    build_prelock_gate,
    fanduel_export_token,
    filter_solver_csv,
    format_questionable_warning,
    is_prelock_hard_status,
    normalize_join_team,
)
from ceminidfs.orchestrator.run import _run_optimize

SALARY_HEADER = (
    "Id,Nickname,Position,Team,Salary,FPPG,Injury Indicator,Projected Ownership"
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def _salary(path: Path) -> Path:
    return _write(
        path,
        f"""
{SALARY_HEADER}
136490-100,Travis Etienne Jr.,RB,JAC,7600,14.2,Q,8.5
136490-101,Brian Thomas Jr.,WR,JAC,8000,16.1,Q,12
136490-102,Mac Jones,QB,JAC,6400,12.0,,4
136490-103,Trevor Lawrence,QB,JAC,7800,18.4,,15
136490-104,Patrick Mahomes,QB,KC,8900,22.5,,20
136490-105,Josh Allen,QB,BUF,9000,23.0,,18
136490-4242,Tank Bigsby,RB,JAC,5700,9.4,,3
""",
    )


def _scratch(path: Path) -> Path:
    return _write(
        path,
        """
name,team,status,exclude
Travis Etienne Jr.,JAX,out,1
Brian Thomas Jr.,JAC,Q,0
""",
    )


def _starters(path: Path) -> Path:
    return _write(
        path,
        """
team,starter,backups_hard_exclude
JAC,Trevor Lawrence,Mac Jones
LAR,Matthew Stafford,
WSH,Jayden Daniels,Marcus Mariota
""",
    )


def _gate(tmp_path: Path, **kwargs):
    salary = _salary(tmp_path / "2026-11-15_fd_sun.csv")
    return build_prelock_gate(
        salary,
        scratch_csv=kwargs.get("scratch_csv", _scratch(tmp_path / "scratch.csv")),
        qb_starters_csv=kwargs.get("qb_starters_csv", _starters(tmp_path / "qb.csv")),
        exclude_players=kwargs.get("exclude_players"),
        questionable_policy=kwargs.get("questionable_policy", "keep"),
    ), salary


def _by_id(gate, player_id: str):
    return next(player for player in gate.players if player.player_id == player_id)


def test_scratch_out_overrides_fanduel_questionable(tmp_path: Path) -> None:
    gate, _salary_path = _gate(tmp_path)
    etienne = _by_id(gate, "136490-100")
    thomas = _by_id(gate, "136490-101")

    assert is_prelock_hard_status("out")
    assert is_prelock_hard_status("Q") is False
    assert etienne.hard_excluded is True
    assert etienne.exclude_reason == "scratch_status"
    assert etienne.effective_status == "OUT"
    assert etienne.fd_status == "Q"
    assert etienne.player_id == "136490-100"
    assert etienne.name == "Travis Etienne Jr."
    assert thomas.hard_excluded is False
    assert thomas.effective_status == "Q"

    warning = format_questionable_warning(gate)
    assert "Brian Thomas Jr." in warning
    assert "Travis Etienne Jr." not in warning
    assert "questionable players still in the pool: 1" in warning


def test_backup_qb_is_hard_excluded(tmp_path: Path) -> None:
    gate, _salary_path = _gate(tmp_path)
    mac = _by_id(gate, "136490-102")
    trevor = _by_id(gate, "136490-103")

    assert mac.hard_excluded is True
    assert mac.exclude_reason == "backup_qb"
    assert mac.player_id == "136490-102"
    assert mac.name == "Mac Jones"
    assert trevor.hard_excluded is False
    assert trevor.name == "Trevor Lawrence"
    assert "136490-102" in gate.banned_ids
    assert "trevor lawrence" not in gate.banned_names


def test_jac_normalizes_without_changing_fanduel_export_id(tmp_path: Path) -> None:
    gate, salary = _gate(tmp_path, scratch_csv=None, qb_starters_csv=None)
    tank = _by_id(gate, "136490-4242")

    assert normalize_join_team("JAC") == "JAX"
    assert normalize_join_team("WSH") == "WAS"
    assert normalize_join_team("LAR") == "LA"
    assert normalize_join_team("LA") == "LA"
    assert tank.team == "JAX"
    assert tank.team_raw == "JAC"
    assert tank.player_id == "136490-4242"
    assert tank.name == "Tank Bigsby"
    assert fanduel_export_token(tank) == "136490-4242:Tank Bigsby"
    assert tank.hard_excluded is False

    kept_gate, kept_salary = _gate(tmp_path / "drop")
    dest = tmp_path / "solver.csv"
    path, dropped = filter_solver_csv(kept_salary, dest, kept_gate)
    assert dropped == 2
    assert path == dest
    rows = list(csv.DictReader(dest.open(encoding="utf-8")))
    kept = next(row for row in rows if row["Id"] == "136490-4242")
    assert kept["Id"] == "136490-4242"
    assert kept["Nickname"] == "Tank Bigsby"
    assert kept["Team"] == "JAC"
    assert all(row["Id"] != "136490-102" for row in rows)
    assert all(row["Id"] != "136490-100" for row in rows)


def test_questionable_player_stays_unless_named(tmp_path: Path) -> None:
    salary = _salary(tmp_path / "2026-11-15_fd_sun.csv")
    scratch = _write(
        tmp_path / "scratch.csv",
        """
name,team,status,exclude
Christian Kirk,JAC,Q,1
""",
    )
    # Christian Kirk is not on this salary file. Use Brian as the named Q.
    named = build_prelock_gate(
        salary,
        scratch_csv=scratch,
        exclude_players=["Brian Thomas Jr."],
    )
    brian = _by_id(named, "136490-101")
    assert brian.hard_excluded is True
    assert brian.exclude_reason == "exclude_players"
    assert _by_id(named, "136490-104").hard_excluded is False

    kept = build_prelock_gate(salary, questionable_policy="keep")
    assert _by_id(kept, "136490-101").hard_excluded is False
    assert "Brian Thomas Jr." in format_questionable_warning(kept)


def test_lineup_generation_writes_projections_and_exposure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    salary = _salary(tmp_path / "2026-11-15_fd_sun.csv")
    scratch = _scratch(tmp_path / "scratch.csv")
    starters = _starters(tmp_path / "qb_starters.csv")
    archive = tmp_path / "archive"
    out = tmp_path / "lineups.csv"
    captured: dict[str, str] = {}

    def fake_optimize(*args, **kwargs):
        csv_path = Path(kwargs.get("csv_path") or args[0])
        out_path = Path(kwargs.get("out_path") or args[1])
        captured["csv"] = csv_path.read_text(encoding="utf-8")
        out_path.write_text(
            "QB,RB,RB,WR,WR,WR,TE,FLEX,DEF\n"
            "Trevor Lawrence,Brian Thomas Jr.,Brian Thomas Jr.,Brian Thomas Jr.,"
            "Brian Thomas Jr.,Brian Thomas Jr.,Brian Thomas Jr.,Brian Thomas Jr.,"
            "Brian Thomas Jr.\n",
            encoding="utf-8",
        )
        return 1

    monkeypatch.setattr("ceminidfs.export.optimize.optimize_lineups", fake_optimize)
    result = _run_optimize(
        salary,
        out,
        1,
        {
            "salary_path": str(salary),
            "scratch_csv": str(scratch),
            "qb_starters_csv": str(starters),
            "archive_dir": str(archive),
            "site": "fanduel",
            "include_questionable_policy": "keep",
        },
    )

    assert result == out
    assert "136490-102" not in captured["csv"]
    assert "136490-100" not in captured["csv"]
    assert "136490-103" in captured["csv"]
    stdout = capsys.readouterr().out
    assert "questionable players still in the pool: 1" in stdout
    assert "Brian Thomas Jr." in stdout
    assert "exposure summary 2026-11-15" in stdout
    assert "JAX" in stdout
    assert "over 45%" in stdout
    assert "zero" in stdout

    projections = tmp_path / "projections_2026-11-15.csv"
    report = tmp_path / "exposure_report_2026-11-15.md"
    assert projections.is_file()
    assert projections.stat().st_size > 0
    assert report.is_file()
    assert report.stat().st_size > 0
    header = projections.read_text(encoding="utf-8").splitlines()[0]
    assert header == (
        "player_id,name,team,pos,salary,proj_fd_pts,ownership_proj,injury_status"
    )
    rows = list(csv.DictReader(projections.open(encoding="utf-8")))
    etienne = next(row for row in rows if row["player_id"] == "136490-100")
    assert etienne["name"] == "Travis Etienne Jr."
    assert etienne["team"] == "JAX"
    assert etienne["injury_status"] == "OUT"
    assert "Top 25 players" in report.read_text(encoding="utf-8")
    assert (archive / "_src_fd_sun.csv").stat().st_size > 0
    assert (archive / "projections_2026-11-15.csv").stat().st_size > 0
    assert (archive / "_src_lineups.csv").stat().st_size > 0


def test_generated_lineup_with_backup_qb_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    salary = _salary(tmp_path / "2026-11-15_fd_sun.csv")
    out = tmp_path / "lineups.csv"

    def fake_optimize(*args, **kwargs):
        out_path = Path(kwargs.get("out_path") or args[1])
        out_path.write_text(
            "QB,RB,RB,WR,WR,WR,TE,FLEX,DEF\n"
            "Mac Jones,Brian Thomas Jr.,Brian Thomas Jr.,Brian Thomas Jr.,"
            "Brian Thomas Jr.,Brian Thomas Jr.,Brian Thomas Jr.,Brian Thomas Jr.,"
            "Brian Thomas Jr.\n",
            encoding="utf-8",
        )
        return 1

    monkeypatch.setattr("ceminidfs.export.optimize.optimize_lineups", fake_optimize)
    with pytest.raises(PrelockExcludeError, match="Mac Jones"):
        _run_optimize(
            salary,
            out,
            1,
            {
                "salary_path": str(salary),
                "scratch_csv": str(_scratch(tmp_path / "scratch.csv")),
                "qb_starters_csv": str(_starters(tmp_path / "qb.csv")),
                "site": "fanduel",
            },
        )
    assert (tmp_path / "projections_2026-11-15.csv").stat().st_size > 0
    assert (tmp_path / "exposure_report_2026-11-15.md").stat().st_size > 0


def test_optimize_and_run_commands_exit_1_on_a_hard_exclude(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = build_parser()
    optimize = parser.parse_args(
        [
            "optimize",
            "--csv",
            "players.csv",
            "--out",
            "lineups.csv",
            "--scratch-csv",
            "scratch.csv",
            "--qb-starters-csv",
            "qb.csv",
            "--exclude-players",
            "Mac Jones,Travis Etienne Jr.",
            "--include-questionable-policy",
            "keep",
            "--archive-dir",
            "archive",
            "--slate-date",
            "2026-11-15",
        ]
    )
    run = parser.parse_args(
        [
            "run",
            "--season",
            "2026",
            "--week",
            "10",
            "--salary",
            "salary.csv",
            "--scratch-csv",
            "scratch.csv",
        ]
    )
    assert optimize.scratch_csv == Path("scratch.csv")
    assert optimize.include_questionable_policy == "keep"
    assert run.qb_starters_csv is None

    def boom(*_args, **_kwargs):
        raise PrelockExcludeError("hard-excluded player in lineup 1: Mac Jones")

    monkeypatch.setattr("ceminidfs.cli._run_optimize", boom)
    assert main(["optimize", "--csv", "players.csv", "--out", "lineups.csv"]) == 1
    monkeypatch.setattr("ceminidfs.cli.run_pipeline", boom)
    assert (
        main(
            [
                "run",
                "--season",
                "2026",
                "--week",
                "10",
                "--salary",
                "salary.csv",
                "--stages",
                "optimize",
            ]
        )
        == 1
    )
