from types import SimpleNamespace

import pytest

from ceminidfs.export.lineup_report import (
    format_lineup_report,
    lineup_stack_badges,
    player_exposure_rows,
)
from ceminidfs.export.optimize import LINEUP_HEADERS
from ceminidfs.export.stack_rules import (
    max_repeating_from_uniques,
    offense_vs_dst_pairs,
    parse_stack_rule,
    parse_stack_rules,
    players_below_floor,
    rbs_by_team,
    resolve_repeating_players,
)


def test_parse_qb_and_team_and_game_pair():
    qb = parse_stack_rule("qb:3")
    assert qb.kind == "qb_stack"
    assert qb.size == 3

    team = parse_stack_rule("jac:3")
    assert team.kind == "team"
    assert team.team == "JAX"
    assert team.size == 3

    pair = parse_stack_rule("CIN3-TB2")
    assert pair.kind == "game_pair"
    assert pair.teams == (("CIN", 3), ("TB", 2))

    colon_pair = parse_stack_rule("CIN:3-TB:2")
    assert colon_pair.teams == (("CIN", 3), ("TB", 2))


def test_parse_random_game_and_rb_dst():
    split = parse_stack_rule("3-2")
    assert split.kind == "game"
    assert split.size == 5
    assert split.min_from_team == 2

    game = parse_stack_rule("game:5")
    assert game.size == 5
    assert game.min_from_team == 1

    dst = parse_stack_rule("rb+dst")
    assert dst.kind == "rb_dst"

    wr = parse_stack_rule("wr:2")
    assert wr.kind == "position"
    assert wr.positions == ("WR",)


def test_parse_stack_rules_splits_pipe_tokens():
    specs = parse_stack_rules(["qb:3|CIN3-TB2"])
    assert [spec.kind for spec in specs] == ["qb_stack", "game_pair"]
    assert specs[0].size == 3
    assert specs[1].teams == (("CIN", 3), ("TB", 2))

    repeated = parse_stack_rules(["qb:3", "CIN3-TB2"])
    assert [(spec.kind, spec.raw) for spec in repeated] == [
        ("qb_stack", "qb:3"),
        ("game_pair", "CIN3-TB2"),
    ]


def test_parse_stack_rule_rejects_empty_and_junk():
    with pytest.raises(ValueError, match="empty"):
        parse_stack_rule("  ")
    with pytest.raises(ValueError, match="expected"):
        parse_stack_rule("stack-hard")


def _player(name: str, team: str, positions: list[str], opp: str | None = None) -> SimpleNamespace:
    game = None
    if opp:
        game = SimpleNamespace(home_team=team, away_team=opp)
    return SimpleNamespace(full_name=name, team=team, positions=positions, game_info=game)


def test_lineup_stack_badges_qb_and_bring_back():
    lineup = SimpleNamespace(
        players=[
            _player("Joe Burrow", "CIN", ["QB"], "TB"),
            _player("Ja'Marr Chase", "CIN", ["WR"], "TB"),
            _player("Tee Higgins", "CIN", ["WR"], "TB"),
            _player("Mike Evans", "TB", ["WR"], "CIN"),
            _player("Bucky Irving", "TB", ["RB"], "CIN"),
        ]
    )

    badges = lineup_stack_badges(lineup)

    assert "QB+2 CIN" in badges
    assert "BRING-BACK TB x2" in badges
    assert "GAME CIN-TB 3-2" in badges
    assert "CHALK-QB-WR-WR" in badges


def test_exposure_and_report_text():
    chase = _player("Ja'Marr Chase", "CIN", ["WR"], "TB")
    burrow = _player("Joe Burrow", "CIN", ["QB"], "TB")
    lineups = [
        SimpleNamespace(players=[burrow, chase], salary_costs=59500, fantasy_points_projection=120.4),
        SimpleNamespace(players=[chase], salary_costs=59000, fantasy_points_projection=110.0),
    ]

    rows = player_exposure_rows(lineups)
    assert rows[0][0] == "Ja'Marr Chase"
    assert rows[0][1] == 2
    assert rows[0][2] == 1.0

    text = format_lineup_report(lineups, stacks=["qb:3"], locks=["Ja'Marr Chase"], excludes=["Alvin Kamara"])
    assert "Stacks: qb:3" in text
    assert "Locks: Ja'Marr Chase" in text
    assert "100%" in text
    assert "Ja'Marr Chase" in text


def test_uniques_math_classic_and_showdown():
    assert max_repeating_from_uniques(len(LINEUP_HEADERS["fanduel"]), 3) == 6
    assert max_repeating_from_uniques(len(LINEUP_HEADERS["fanduel_showdown"]), 3) == 3
    assert resolve_repeating_players(slate_size=9, max_repeating_players=7, uniques=3) == 6
    assert resolve_repeating_players(slate_size=9, max_repeating_players=4, uniques=None) == 4
    with pytest.raises(ValueError, match="uniques"):
        max_repeating_from_uniques(9, -1)


def test_offense_vs_dst_pairs_skip_empty_opponent():
    dst = _player("Patriots", "NE", ["DST"])
    wr = _player("Jaxon Smith-Njigba", "SEA", ["WR"], "NE")
    assert offense_vs_dst_pairs([dst, wr]) == []


def test_offense_vs_dst_pairs_are_pairwise_not_giant_group():
    dst = _player("Seahawks", "SEA", ["DST"], "NE")
    wr = _player("A.J. Brown", "NE", ["WR"], "SEA")
    qb = _player("Drake Maye", "NE", ["QB"], "SEA")
    teammate = _player("Jaxon Smith-Njigba", "SEA", ["WR"], "NE")
    opp_dst = _player("Patriots", "NE", ["DST"], "SEA")

    pairs = offense_vs_dst_pairs([dst, wr, qb, teammate, opp_dst])
    names = {(left.full_name, right.full_name) for left, right in pairs}

    assert ("Seahawks", "A.J. Brown") in names
    assert ("Seahawks", "Drake Maye") in names
    assert ("Seahawks", "Jaxon Smith-Njigba") not in names
    assert ("Seahawks", "Patriots") not in names
    assert ("Patriots", "Jaxon Smith-Njigba") in names


def test_rbs_by_team_and_projection_floor_skip_locked():
    price = _player("Jadarian Price", "SEA", ["RB"], "NE")
    walker = _player("Kenneth Walker", "SEA", ["RB"], "NE")
    stevenson = _player("Rhamondre Stevenson", "NE", ["RB"], "SEA")
    price.fppg = 19.8
    walker.fppg = 5.0
    stevenson.fppg = 17.5

    grouped = rbs_by_team([price, walker, stevenson])
    assert {player.full_name for player in grouped["SEA"]} == {"Jadarian Price", "Kenneth Walker"}
    assert {player.full_name for player in grouped["NE"]} == {"Rhamondre Stevenson"}

    dropped = players_below_floor([price, walker, stevenson], floor=10.0, locked=[walker])
    assert dropped == []
    dropped = players_below_floor([price, walker, stevenson], floor=10.0, locked=[])
    assert dropped == [walker]


def test_report_lists_build_flags_when_set():
    chase = _player("Ja'Marr Chase", "CIN", ["WR"], "TB")
    text = format_lineup_report(
        [SimpleNamespace(players=[chase])],
        no_offense_vs_dst=True,
        one_rb_per_team=True,
        projection_floor=8.0,
        uniques=3,
    )
    assert "Build: no-offense-vs-dst, one-rb-per-team, projection-floor=8.0, uniques=3" in text
