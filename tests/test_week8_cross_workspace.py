"""Week 8 cache columns, WR/TE floor, and pre-lock salary copy."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ceminidfs.export.recap_guards import (
    opportunity_blocked,
    prelock_salary_archive,
    skill_excluded,
)
from ceminidfs.orchestrator.run import run_pipeline
from ceminidfs.situational.eb import EB_K
from ceminidfs.situational.shared_cache import (
    PLAYER_TELEMETRY_NAME,
    write_shared_cache,
)

PRIOR = 0.25


def _plays() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": 2026,
                "week": 7,
                "qtr": 4,
                "posteam": "PIT",
                "rush": 1,
                "pass": 0,
                "complete_pass": 0,
                "score_differential": 5,
                "rusher_player_id": "g1",
                "receiver_player_id": None,
            },
            {
                "season": 2026,
                "week": 7,
                "qtr": 4,
                "posteam": "PIT",
                "rush": 1,
                "pass": 0,
                "complete_pass": 0,
                "score_differential": 5,
                "rusher_player_id": "g1",
                "receiver_player_id": None,
            },
            {
                "season": 2026,
                "week": 7,
                "qtr": 3,
                "posteam": "PIT",
                "rush": 0,
                "pass": 1,
                "complete_pass": 1,
                "score_differential": -3,
                "rusher_player_id": None,
                "receiver_player_id": "g1",
            },
            {
                "season": 2026,
                "week": 7,
                "qtr": 4,
                "posteam": "PIT",
                "rush": 0,
                "pass": 1,
                "complete_pass": 0,
                "score_differential": -4,
                "rusher_player_id": None,
                "receiver_player_id": "g1",
            },
            {
                "season": 2026,
                "week": 8,
                "qtr": 4,
                "posteam": "PIT",
                "rush": 0,
                "pass": 1,
                "complete_pass": 1,
                "score_differential": 1,
                "rusher_player_id": None,
                "receiver_player_id": "g1",
            },
            {
                "season": 2026,
                "week": 7,
                "qtr": 1,
                "posteam": "PIT",
                "rush": 0,
                "pass": 1,
                "complete_pass": 1,
                "score_differential": 0,
                "rusher_player_id": None,
                "receiver_player_id": "g1",
            },
            {
                "season": 2026,
                "week": 6,
                "qtr": 4,
                "posteam": "LA",
                "rush": 1,
                "pass": 0,
                "complete_pass": 0,
                "score_differential": 2,
                "rusher_player_id": "g1",
                "receiver_player_id": None,
            },
        ]
    )


def _salary_csv(path: Path) -> Path:
    path.write_text(
        "Id,Nickname,Position,Salary\n135859-167622,Jonah Coleman,RB,5000\n",
        encoding="utf-8",
    )
    return path


def test_player_telemetry_exports_quarter_counts(tmp_path: Path) -> None:
    players = pd.DataFrame(
        {
            "player_id": ["g1", "g2"],
            "team": ["PIT", "LAR"],
            "player_name": ["Kenneth Gainwell", "Other"],
        }
    )
    write_shared_cache(
        tmp_path,
        players=players,
        defense=pd.DataFrame({"defense_team": ["PIT"]}),
        games=pd.DataFrame({"game_id": ["g"]}),
        season=2026,
        week=8,
        max_source_week=7,
        pbp=_plays(),
    )
    out = pd.read_parquet(tmp_path / PLAYER_TELEMETRY_NAME)
    required = {
        "q3_targets",
        "q4_targets",
        "q4_rush_att",
        "w_rec_q3_eb",
        "w_rec_q4_eb",
        "q4_recs",
        "q4_trail_targets",
        "q4_lead_rush_att",
        "total_targets",
        "total_rush_att",
        "team_q4_rush_att",
    }
    assert required <= set(out.columns)
    assert list(out["player_id"]) == ["g1", "g2"]
    g1 = out.set_index("player_id").loc["g1"]
    g2 = out.set_index("player_id").loc["g2"]
    assert int(g1["q1_targets"]) == 1
    assert int(g1["q3_targets"]) == 1
    assert int(g1["q3_recs"]) == 1
    assert int(g1["q4_targets"]) == 1
    assert int(g1["q4_recs"]) == 0
    assert int(g1["q4_trail_targets"]) == 1
    assert int(g1["total_targets"]) == 3
    assert int(g1["q4_rush_att"]) == 3
    assert int(g1["total_rush_att"]) == 3
    assert int(g1["q4_lead_rush_att"]) == 3
    assert int(g1["team_q4_rush_att"]) == 2
    share = (1 + EB_K * PRIOR) / (3 + EB_K)
    rush = (3 + EB_K * PRIOR) / (3 + EB_K)
    assert float(g1["w_rec_q3_eb"]) == pytest.approx(share)
    assert float(g1["w_rec_q4_eb"]) == pytest.approx(share)
    assert float(g1["w_rush_q4_eb"]) == pytest.approx(rush)
    assert int(g2["total_targets"]) == 0
    assert int(g2["q4_rush_att"]) == 0
    assert float(g2["w_rec_q4_eb"]) == pytest.approx(PRIOR)
    assert int(g2["team_q4_rush_att"]) == 1


def test_low_target_receivers_leave_the_pool() -> None:
    assert opportunity_blocked("WR", 3, 0)
    assert opportunity_blocked("TE", 1, 0)
    assert not opportunity_blocked("WR", 4, 0)
    assert not opportunity_blocked("RB", 1, 3)
    assert skill_excluded(
        position="WR",
        name="Omar Cooper Jr.",
        salary=4500,
        played=2,
        fppg=0.0,
        targets=3,
        carries=0,
        snaps=4,
    )
    assert skill_excluded(
        position="TE",
        name="Evan Engram",
        salary=4500,
        played=2,
        fppg=0.0,
        targets=2,
        carries=0,
        snaps=4,
    )
    assert not skill_excluded(
        position="WR",
        name="Priced Starter",
        salary=6000,
        played=2,
        fppg=10.0,
        targets=0,
        carries=0,
        snaps=4,
    )
    assert skill_excluded(
        position="WR",
        name="Cheap Miss",
        salary=5900,
        played=4,
        fppg=12.0,
        targets=1,
        carries=0,
        snaps=4,
    )
    assert skill_excluded(
        position="TE",
        name="Low Fppg",
        salary=7000,
        played=4,
        fppg=9.9,
        targets=1,
        carries=0,
        snaps=4,
    )
    assert opportunity_blocked("WR", 4, 0, team_target_share=0.14)
    assert not opportunity_blocked("WR", 4, 0, team_target_share=0.15)
    assert not opportunity_blocked("WR", 4, 0, route_share=0.55)
    assert not opportunity_blocked("TE", 4, 0, snap_share=0.55)
    assert opportunity_blocked("WR", 3, 0, snap_share=0.90)
    assert not opportunity_blocked("WR", 4, 0)


def test_slate_export_writes_salary_copy_and_fade_audit(tmp_path: Path) -> None:
    source = _salary_csv(tmp_path / "FanDuel-NFL-2026-11-01-135859-players-list.csv")
    run_dir = tmp_path / "runs" / "2026_week_8"
    recap_root = tmp_path / "dfs-recap"
    recap_root.mkdir()
    written = prelock_salary_archive(
        source,
        season=2026,
        week=8,
        work_dir=run_dir,
        slate_date="2026-11-01",
        fixture_id="135859",
        recap_root=recap_root,
    )
    run_copy = run_dir / "_src_fd_sun.csv"
    fade = run_dir / "fade-coverage-w8.md"
    recap_copy = recap_root / "2026-11-01" / "in" / "fd_players_135859.csv"
    assert run_copy.is_file()
    assert fade.is_file()
    assert recap_copy.is_file()
    assert run_copy in written
    assert recap_copy in written
    header = source.read_text(encoding="utf-8").splitlines()[0]
    assert run_copy.read_text(encoding="utf-8").splitlines()[0] == header
    assert recap_copy.read_text(encoding="utf-8").splitlines()[0] == header
    assert "Pre-lock salary copy is on disk." in fade.read_text(encoding="utf-8")

    bare = tmp_path / "bare-recap"
    bare_run = tmp_path / "runs" / "bare"
    prelock_salary_archive(
        source,
        season=2026,
        week=8,
        work_dir=bare_run,
        slate_date="2026-11-01",
        fixture_id="135859",
        recap_root=bare,
    )
    assert (bare_run / "_src_fd_sun.csv").is_file()
    assert (bare_run / "fade-coverage-w8.md").is_file()
    assert not bare.exists()

    with pytest.raises(FileNotFoundError):
        prelock_salary_archive(
            tmp_path / "missing.csv",
            season=2026,
            week=8,
            work_dir=tmp_path / "runs" / "missing",
            recap_root=recap_root,
        )


def test_optimize_stage_archives_before_the_solve(tmp_path: Path) -> None:
    work = tmp_path / "work"
    salary = _salary_csv(tmp_path / "salary.csv")
    with pytest.raises(FileNotFoundError):
        run_pipeline(
            2026,
            8,
            salary,
            stages="optimize",
            config={
                "work_dir": work,
                "site": "fanduel",
                "count": 1,
                "recap_root": work / "missing-recap",
            },
        )
    assert (work / "_src_fd_sun.csv").is_file()
    assert (work / "fade-coverage-w8.md").is_file()
    assert not (work / "missing-recap").exists()
    assert not (work / "lineups.csv").exists()
