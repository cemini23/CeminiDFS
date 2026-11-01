"""Unit tests for the Week 7 recap guardrails G1-G4, G6, and G8."""

from pathlib import Path

import pandas as pd
import pytest

from ceminidfs.export.mme_portfolio import Candidate, select_book
from ceminidfs.export.pool_guards import apply_qb_starter_gate
from ceminidfs.export.recap_guards import (
    RB_CAP,
    RB_PAIR_CAP,
    RB_TE_CAP,
    WR_TE_CAP,
    archive_loaded_salary,
    assert_one_qb_per_team,
    build_opportunity_index,
    cheap_season_blocked,
    environment_scale,
    is_backup_quarterback,
    load_qb_starters_csv,
    lookup_opportunity,
    opportunity_blocked,
    roster_excluded,
    skill_excluded,
    write_qb_starters_csv,
)
from ceminidfs.models.scoring import fd_points
from ceminidfs.situational.injuries import apply_injury_vacuum


def test_defensive_pat_scores_two_points():
    assert fd_points({"dst_defensive_pat": 1}) == pytest.approx(2.0)
    assert fd_points({"dst_blocked_kick": 1, "dst_defensive_pat": 1}) == pytest.approx(4.0)
    assert fd_points({}) == 0.0


def test_min_salary_touch_floor_blocks_a_punt():
    assert opportunity_blocked("WR", targets=2, carries=4)
    assert not opportunity_blocked("WR", targets=3, carries=0)
    assert opportunity_blocked("TE", targets=1, carries=0)
    assert opportunity_blocked("RB", targets=1, carries=2)
    assert not opportunity_blocked("RB", targets=1, carries=3)
    assert not opportunity_blocked("QB", targets=0, carries=0)
    assert cheap_season_blocked("WR", salary=4500, played=2, fppg=12.0)
    assert cheap_season_blocked("WR", salary=4800, played=4, fppg=4.4)
    assert not cheap_season_blocked("WR", salary=4800, played=3, fppg=4.5)
    assert not cheap_season_blocked("WR", salary=4900, played=1, fppg=1.0)
    assert skill_excluded(
        position="WR",
        name="Jeshaun Jones",
        salary=4500,
        played=1,
        fppg=0.0,
        targets=1,
        carries=0,
        snaps=1,
    )
    assert not skill_excluded(
        position="WR",
        name="Jeshaun Jones",
        salary=4500,
        played=1,
        fppg=0.0,
        targets=0,
        carries=0,
        snaps=0,
        whitelist=frozenset({"Jeshaun Jones"}),
    )


def test_opportunity_index_uses_the_last_two_active_games():
    pbp = pd.DataFrame(
        {
            "season": [2026, 2026, 2026, 2026, 2026],
            "week": [5, 6, 6, 7, 7],
            "posteam": ["TB", "TB", "TB", "TB", "TB"],
            "pass": [1, 1, 1, 1, 0],
            "rush": [0, 0, 0, 0, 1],
            "receiver_player_id": ["wr1", "wr1", "wr1", "wr2", None],
            "receiver_player_name": ["Mike Evans", "Mike Evans", "Mike Evans", "Jeshaun Jones", None],
            "rusher_player_id": [None, None, None, None, "rb1"],
            "rusher_player_name": [None, None, None, None, "Bucky Irving"],
        }
    )
    index = build_opportunity_index(pbp, before_week=8)
    evans = lookup_opportunity(index, "TB", "Mike Evans", "Evans")
    jones = lookup_opportunity(index, "TB", "Jeshaun Jones", "Jones")
    irving = lookup_opportunity(index, "TB", "Bucky Irving", "Irving")
    assert evans is not None and evans.targets == 3
    assert jones is not None and jones.targets == 1
    assert irving is not None and irving.carries == 1
    assert opportunity_blocked("WR", jones.targets, jones.carries)
    assert not opportunity_blocked("WR", evans.targets, evans.carries)


def test_backup_quarterback_gate_keeps_one_starter():
    starters = {"NYG": "J.J. McCarthy", "TB": "Baker Mayfield"}
    assert is_backup_quarterback("NYG", "Jameis Winston", "QB", starters)
    assert not is_backup_quarterback("NYG", "J.J. McCarthy", "QB", starters)
    assert is_backup_quarterback("TB", "Jalon Daniels", "QB", starters)
    assert not is_backup_quarterback("TB", "Baker Mayfield", "WR", starters)
    assert_one_qb_per_team({"NYG": {"j j mccarthy"}})
    with pytest.raises(AssertionError):
        assert_one_qb_per_team({"NYG": {"j j mccarthy", "jameis winston"}})


def test_optimizer_gate_removes_the_backup(tmp_path: Path):
    class _Player:
        def __init__(self, name: str, team: str, pos: str):
            self.full_name = name
            self.team = team
            self.positions = [pos]
            self.fppg = 10.0

    class _Pool:
        def __init__(self, players):
            self.all_players = list(players)

        def remove_player(self, player):
            self.all_players.remove(player)

    class _Opt:
        def __init__(self, players):
            self.player_pool = _Pool(players)

    starter = _Player("J.J. McCarthy", "NYG", "QB")
    backup = _Player("Jameis Winston", "NYG", "QB")
    receiver = _Player("Malik Nabers", "NYG", "WR")
    optimizer = _Opt([starter, backup, receiver])
    removed = apply_qb_starter_gate(optimizer, {"NYG": "J.J. McCarthy"})
    assert removed == ["Jameis Winston"]
    assert backup.fppg == 0.0
    assert [player.full_name for player in optimizer.player_pool.all_players] == [
        "J.J. McCarthy",
        "Malik Nabers",
    ]
    path = write_qb_starters_csv(tmp_path / "qb_starters_2026-11-01.csv", {"NYG": "J.J. McCarthy"})
    assert load_qb_starters_csv(path)["NYG"] == "J.J. McCarthy"


def test_free_agent_and_zero_snap_players_are_excluded():
    assert roster_excluded(status="FA", snaps=12, starter_note=False, roster_fresh=True)
    assert roster_excluded(status="Practice Squad", snaps=4, starter_note=False, roster_fresh=True)
    assert roster_excluded(status="ACT", snaps=0, starter_note=False, roster_fresh=True)
    assert not roster_excluded(status="ACT", snaps=0, starter_note=True, roster_fresh=True)
    assert not roster_excluded(status="ACT", snaps=6, starter_note=False, roster_fresh=True)
    assert skill_excluded(
        position="RB",
        name="Najee Harris",
        salary=5000,
        played=4,
        fppg=8.0,
        targets=0,
        carries=0,
        snaps=0,
        roster_status="FA",
        roster_fresh=True,
    )


def test_same_team_rb_te_needs_the_quarterback_and_stays_under_the_cap():
    assert WR_TE_CAP == 42
    assert RB_CAP == 45
    assert RB_PAIR_CAP == 24
    assert RB_TE_CAP == 9

    def candidate(ids, blend, positions):
        return Candidate(
            ids=tuple(ids),
            key=frozenset(ids),
            salary=59600,
            blend=blend,
            bringback=True,
            secondary=True,
            catchers=1,
            dst_conflict=False,
            positions=tuple(positions),
            game="BAL@BUF",
            tags="QB+1",
        )

    stacked = [
        ("qb", "QB"),
        ("rb", "RB"),
        ("te", "TE"),
        ("w1", "WR"),
        ("w2", "WR"),
        ("w3", "WR"),
        ("rb2", "RB"),
        ("dst", "DST"),
        ("flex", "WR"),
    ]
    naked = [
        ("qb2", "QB"),
        ("rb", "RB"),
        ("te", "TE"),
        ("w4", "WR"),
        ("w5", "WR"),
        ("w6", "WR"),
        ("rb3", "RB"),
        ("dst2", "DST"),
        ("flex2", "WR"),
    ]
    teams = {
        "qb": "BAL",
        "rb": "BAL",
        "te": "BAL",
        "rb2": "BUF",
        "qb2": "BUF",
        "w1": "BAL",
        "w2": "BUF",
        "w3": "DAL",
        "w4": "DAL",
        "w5": "DAL",
        "w6": "KC",
        "rb3": "KC",
        "dst": "KC",
        "dst2": "DEN",
        "flex": "DEN",
        "flex2": "DEN",
    }
    caps = {"QB": 5, "RB": 5, "WR": 5, "TE": 5, "DST": 5}
    book = select_book(
        [
            candidate([pid for pid, _pos in naked], 80.0, naked),
            candidate([pid for pid, _pos in stacked], 70.0, stacked),
        ],
        count=2,
        bringback_min=0,
        secondary_min=0,
        caps=caps,
        rb_te_cap=1,
        player_teams=teams,
    )
    assert [item.blend for item in book] == [70.0]


def test_vacuum_boost_skips_a_non_rotation_player():
    frame = pd.DataFrame(
        [
            {
                "player_name": "Donor",
                "team": "TEN",
                "salary_team": "TEN",
                "position": "WR",
                "injury_indicator": "O",
                "lagged_fd": 10.0,
                "targets_per_game": 8.0,
                "inside10_target_share": 0.0,
            },
            {
                "player_name": "Punt",
                "team": "TEN",
                "salary_team": "TEN",
                "position": "WR",
                "injury_indicator": "",
                "lagged_fd": 1.0,
                "targets_per_game": 0.2,
                "receptions_per_game": 0.1,
                "rec_yds_per_game": 1.0,
                "rec_td_per_game": 0.0,
                "inside10_target_share": 0.0,
            },
        ]
    )
    out = apply_injury_vacuum(frame, None)
    punt = out.loc[out["player_name"].eq("Punt")].iloc[0]
    assert punt["vacated_target_boost"] == 0.0
    assert punt["lagged_fd"] == pytest.approx(1.0)


def test_open_air_wind_scales_and_a_dome_does_not():
    assert environment_scale("open", 15, "WR") == pytest.approx(0.90)
    assert environment_scale("open", 15, "RB") == pytest.approx(1.08)
    assert environment_scale("open", 12, "WR") == pytest.approx(0.97)
    assert environment_scale("open", 13, "QB") == pytest.approx(0.99)
    assert environment_scale("dome", 20, "WR") == 1.0
    assert environment_scale("retractable", 15, "QB") == 1.0
    assert environment_scale("canopy", 15, "RB") == 1.0
    assert environment_scale("open", 5, "WR") == 1.0


def test_salary_archive_skips_a_missing_workspace(tmp_path: Path):
    source = tmp_path / "players.csv"
    source.write_text("Id,Salary\n1,5000\n", encoding="utf-8")
    slate = tmp_path / "data" / "slates" / "2026-11-01_fd_sun.csv"
    run_copy = tmp_path / "runs" / "2026_week_8" / "_src_fd_sun.csv"
    workspace = tmp_path / "workspace"
    missing = workspace / "dfs-recap" / "2026-11-01" / "_src_fd_sun.csv"
    written = archive_loaded_salary(
        source,
        [slate, run_copy, missing],
        workspace_root=workspace,
    )
    assert slate in written and run_copy in written
    assert slate.read_text(encoding="utf-8").startswith("Id,Salary")
    assert missing not in written
    assert not missing.exists()
