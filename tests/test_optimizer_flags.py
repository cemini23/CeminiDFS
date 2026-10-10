"""Optimizer flag checks on a 20-player pool. No full-slate solve."""

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("pydfs_lineup_optimizer")

from ceminidfs.cli import _optimizer_build_overrides, build_parser
from ceminidfs.export.optimize import (
    LINEUP_HEADERS,
    _assert_locks_and_excludes_hold,
    generate_lineups,
    optimize_lineups,
    te_def_pair,
)
from ceminidfs.export.pool_guards import apply_soft_fade, open_qb_teams_from_csv
from ceminidfs.orchestrator.run import _optimize_build_kwargs

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

# Three teams, so the pool is not a tiny slate. Salaries fit under $60,000.
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
        for row in POOL:
            player_id, first, last, pos, team, salary, fppg, opp = row
            game = f"{team}@{opp} 01:00PM ET"
            writer.writerow([player_id, first, last, pos, team, salary, fppg, game, "", opp])
    return path


def _names(lineup) -> set[str]:
    return {player.full_name for player in lineup.players}


def _rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        assert header == LINEUP_HEADERS["fanduel"]
        return list(reader)


def test_lock_is_in_every_lineup(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    players = _write_pool(tmp_path / "players.csv")
    lineups = generate_lineups(
        players,
        count=2,
        locks=["Patrick Mahomes"],
        max_exposure=1.0,
        min_salary=0,
    )
    assert len(lineups) == 2
    for lineup in lineups:
        assert "Patrick Mahomes" in _names(lineup)
    err = capsys.readouterr().err
    assert "optimizer request:" in err
    assert "count=2" in err
    assert "locks=['Patrick Mahomes']" in err


def test_exclude_removes_the_name(tmp_path: Path):
    players = _write_pool(tmp_path / "players.csv")
    lineups = generate_lineups(
        players,
        count=1,
        excludes=["Josh Allen"],
        max_exposure=1.0,
        min_salary=0,
    )
    assert lineups
    for lineup in lineups:
        assert "Josh Allen" not in _names(lineup)


def test_team_stack_puts_three_players_on_every_lineup(tmp_path: Path):
    players = _write_pool(tmp_path / "players.csv")
    lineups = generate_lineups(
        players,
        count=1,
        stacks=["KC:3"],
        max_exposure=1.0,
        min_salary=0,
    )
    assert lineups
    for lineup in lineups:
        kc = [player for player in lineup.players if str(player.team).upper() == "KC"]
        assert len(kc) >= 3


def test_count_writes_the_requested_book(tmp_path: Path):
    players = _write_pool(tmp_path / "players.csv")
    out = tmp_path / "lineups.csv"
    written = optimize_lineups(players, out, count=2, max_exposure=1.0, min_salary=0)
    assert written == 2
    assert len(_rows(out)) == 2


def test_uniques_caps_shared_names(tmp_path: Path):
    players = _write_pool(tmp_path / "players.csv")
    out = tmp_path / "lineups.csv"
    written = optimize_lineups(
        players,
        out,
        count=2,
        uniques=8,
        max_exposure=1.0,
        min_salary=0,
    )
    assert written == 2
    rows = _rows(out)
    shared = set(rows[0]) & set(rows[1])
    assert len(shared) <= 1


def test_max_exposure_caps_the_written_book(tmp_path: Path):
    players = _write_pool(tmp_path / "players.csv")
    out = tmp_path / "lineups.csv"
    written = optimize_lineups(players, out, count=2, max_exposure=0.5, min_salary=0)
    assert written == 2
    counts: dict[str, int] = {}
    for row in _rows(out):
        for cell in row:
            name = cell.strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
    assert counts
    assert max(counts.values()) <= 1


def test_infeasible_count_raises_and_writes_nothing(tmp_path: Path):
    players = _write_pool(tmp_path / "players.csv")
    out = tmp_path / "lineups.csv"
    with pytest.raises(ValueError):
        optimize_lineups(players, out, count=3, max_exposure=0.5, min_salary=0)
    assert not out.exists()
    assert not out.with_name("lineups_fanduel_upload.csv").exists()


def test_run_and_optimize_share_optimizer_flag_keys():
    parser = build_parser()
    shared = [
        "--lock",
        "Patrick Mahomes",
        "--exclude",
        "Josh Allen",
        "--stack",
        "KC:3",
        "--uniques",
        "4",
        "--max-exposure",
        "0.4",
        "--count",
        "2",
    ]
    run_args = parser.parse_args(
        ["run", "--season", "2026", "--week", "4", "--salary", "salary.csv", *shared]
    )
    opt_args = parser.parse_args(
        ["optimize", "--csv", "players.csv", "--out", "lineups.csv", *shared]
    )
    run_over = _optimizer_build_overrides(run_args)
    opt_over = _optimizer_build_overrides(opt_args)
    assert set(run_over) == set(opt_over)
    assert run_over == opt_over
    assert run_args.count == opt_args.count == 2
    run_kw = _optimize_build_kwargs({**run_over, "count": run_args.count})
    opt_kw = _optimize_build_kwargs({**opt_over, "count": opt_args.count})
    assert set(run_kw) == set(opt_kw)
    assert run_kw == opt_kw


OPEN_QB_POOL = [
    ("1", "Patrick", "Mahomes", "QB", "KC", "8000", "30", "BUF", "open"),
    ("2", "Carson", "Wentz", "QB", "KC", "5000", "10", "BUF", "open"),
    ("3", "Isiah", "Pacheco", "RB", "KC", "6100", "18", "BUF", ""),
    ("4", "Kareem", "Hunt", "RB", "KC", "5200", "12", "BUF", ""),
    ("5", "Rashee", "Rice", "WR", "KC", "6400", "16", "BUF", ""),
    ("6", "Xavier", "Worthy", "WR", "KC", "5600", "14", "BUF", ""),
    ("7", "Travis", "Kelce", "TE", "KC", "7000", "17", "BUF", ""),
    ("8", "Kansas City", "Chiefs", "D", "KC", "3600", "8", "BUF", ""),
    ("9", "Josh", "Allen", "QB", "BUF", "8100", "29", "KC", ""),
    ("10", "James", "Cook", "RB", "BUF", "6800", "17", "KC", ""),
    ("11", "Ray", "Davis", "RB", "BUF", "5000", "11", "KC", ""),
    ("12", "Khalil", "Shakir", "WR", "BUF", "5900", "13", "KC", ""),
    ("13", "Stefon", "Diggs", "WR", "BUF", "6200", "15", "KC", ""),
    ("14", "Dalton", "Kincaid", "TE", "BUF", "5500", "12", "KC", ""),
    ("15", "Buffalo", "Bills", "D", "BUF", "3500", "7", "KC", ""),
    ("16", "Joe", "Burrow", "QB", "CIN", "7900", "28", "KC", ""),
    ("17", "Ja'Marr", "Chase", "WR", "CIN", "8200", "24", "KC", ""),
    ("18", "Tee", "Higgins", "WR", "CIN", "7100", "18", "KC", ""),
    ("19", "Chase", "Brown", "RB", "CIN", "6000", "15", "KC", ""),
    ("20", "Mike", "Gesicki", "WR", "CIN", "4500", "8", "KC", ""),
    ("21", "Cincinnati", "Bengals", "D", "CIN", "3400", "6", "KC", ""),
]


def _write_open_qb_pool(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER + ["qb_cell"])
        for row in OPEN_QB_POOL:
            player_id, first, last, pos, team, salary, fppg, opp, cell = row
            game = f"{team}@{opp} 01:00PM ET"
            writer.writerow(
                [player_id, first, last, pos, team, salary, fppg, game, "", opp, cell]
            )
    return path


def test_research_fade_becomes_player_discount(tmp_path: Path):
    research = tmp_path / "research_fade.csv"
    research.write_text(
        "Name,Exclude,Fade\nJosh Allen,yes,0\nPatrick Mahomes,,true\n",
        encoding="utf-8",
    )
    args = build_parser().parse_args(
        ["optimize", "--csv", "p.csv", "--out", "l.csv", "--research-csv", str(research)]
    )
    overrides = _optimizer_build_overrides(args)
    assert overrides["excludes"] == ["Josh Allen"]
    assert overrides["player_soft_fade"] == ["Patrick Mahomes"]

    kwargs = _optimize_build_kwargs(dict(overrides))
    assert kwargs["player_soft_fade"] == ["Patrick Mahomes"]
    assert "Patrick Mahomes" not in kwargs.get("excludes", [])


def test_player_soft_fade_discounts_and_keeps_the_player():
    players = [SimpleNamespace(full_name="Faded Name", team="KC", fppg=10.0)]
    pool = SimpleNamespace(filtered_players=list(players), all_players=list(players))
    optimizer = SimpleNamespace(player_pool=pool)
    optimizer.set_fantasy_points_strategy = lambda strategy: setattr(
        optimizer, "strategy", strategy
    )

    apply_soft_fade(optimizer, None, player_soft_fade=["Faded Name"])

    assert optimizer.strategy.get_player_fantasy_points(players[0]) == pytest.approx(6.5)
    assert len(pool.filtered_players) == 1


def test_open_qb_cell_removes_every_qb_and_warns_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    players = _write_open_qb_pool(tmp_path / "players.csv")
    lineups = generate_lineups(
        players,
        count=1,
        max_exposure=1.0,
        min_salary=0,
    )

    for lineup in lineups:
        names = _names(lineup)
        assert "Patrick Mahomes" not in names
        assert "Carson Wentz" not in names
    err = capsys.readouterr().err
    assert err.count("QB cell open for KC; no quarterback rostered") == 1


def test_open_qb_teams_from_csv_infers_two_starters_without_a_truthy_flag(tmp_path: Path):
    path = tmp_path / "players.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Id", "First Name", "Last Name", "Position", "Team", "is_qb_starter"])
        writer.writerow(["1", "QB", "One", "QB", "CHI", ""])
        writer.writerow(["2", "QB", "Two", "QB", "CHI", "false"])
        writer.writerow(["3", "QB", "Three", "QB", "KC", "True"])
        writer.writerow(["4", "QB", "Four", "QB", "KC", "False"])

    assert open_qb_teams_from_csv(path) == {"CHI"}


def test_open_qb_teams_not_inferred_without_the_starter_column(tmp_path: Path):
    path = tmp_path / "players.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Id", "First Name", "Last Name", "Position", "Team"])
        writer.writerow(["1", "QB", "One", "QB", "CHI"])
        writer.writerow(["2", "QB", "Two", "QB", "CHI"])

    assert open_qb_teams_from_csv(path) == set()


def test_skill_pool_floor_refuses_and_writes_no_lineup_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    players = _write_pool(tmp_path / "players.csv")
    out = tmp_path / "lineups.csv"

    with pytest.raises(ValueError, match="skill pool"):
        optimize_lineups(
            players,
            out,
            count=1,
            min_skill_pool=40,
            max_exposure=1.0,
            min_salary=0,
        )

    assert not out.exists()
    assert not out.with_name("lineups_fanduel_upload.csv").exists()
    assert "skill pool: 17 eligible, floor 40" in capsys.readouterr().err


def test_skill_pool_floor_zero_disables_the_gate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    players = _write_pool(tmp_path / "players.csv")
    lineups = generate_lineups(
        players,
        count=1,
        min_skill_pool=0,
        max_exposure=1.0,
        min_salary=0,
    )

    assert len(lineups) == 1
    assert "skill pool: 17 eligible, floor 0" in capsys.readouterr().err


def test_post_solve_guard_raises_on_missing_lock_and_present_exclude():
    lineup = SimpleNamespace(
        players=[SimpleNamespace(full_name="Player A"), SimpleNamespace(full_name="Player B")]
    )

    with pytest.raises(ValueError, match="lock"):
        _assert_locks_and_excludes_hold([lineup], ["Player C"], [])
    with pytest.raises(ValueError, match="exclude"):
        _assert_locks_and_excludes_hold([lineup], [], ["Player A"])


def _fake_classic_lineup(qb: str, tight_end: str, defense: str) -> SimpleNamespace:
    def seat(name: str, position: str) -> SimpleNamespace:
        return SimpleNamespace(
            full_name=name,
            lineup_position=position,
            positions=[position],
            original_positions=[position],
        )

    return SimpleNamespace(players=[seat(qb, "QB"), seat(tight_end, "TE"), seat(defense, "DEF")])


def test_classic_solve_has_unique_te_def_pairs(tmp_path: Path):
    players = _write_pool(tmp_path / "players.csv")

    lineups = generate_lineups(
        players,
        count=2,
        max_exposure=1.0,
        min_salary=0,
    )

    pairs = [te_def_pair(lineup, "fanduel") for lineup in lineups]
    assert all(pair is not None for pair in pairs)
    assert len(pairs) == len(set(pairs))


def test_te_def_pair_rule_refuses_a_repeated_pair_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    players = _write_pool(tmp_path / "players.csv")
    out = tmp_path / "lineups.csv"
    same = _fake_classic_lineup("Patrick Mahomes", "Travis Kelce", "Kansas City Chiefs")

    import ceminidfs.export.optimize as opt_module

    monkeypatch.setattr(opt_module, "_optimize_or_raise", lambda *_a, **_k: [same, same])

    with pytest.raises(ValueError, match="pair repeated"):
        optimize_lineups(players, out, count=2, max_exposure=None, min_salary=0)

    assert not out.exists()
    assert not out.with_name("lineups_fanduel_upload.csv").exists()
