"""Tests for the fade-coverage report, the team dart rule, and soft fade."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.export.pool_guards import (
    apply_soft_fade,
    apply_team_dart_guard,
    normalize_soft_fade_weights,
)
from ceminidfs.pipeline.fade_coverage import (
    DEFAULT_PRODUCED_THRESHOLD,
    season_rollup,
    team_coverage,
)

SALARY_HEADER = (
    "Id,Position,First Name,Nickname,Last Name,FPPG,Played,Salary,Game,Team,"
    "Opponent,Injury Indicator,Injury Details,Tier,,,Roster Position"
)
LINEUP_HEADER = "QB,RB,RB,WR,WR,WR,TE,FLEX,DEF"


def _write_salary(path: Path, rows: list[tuple[str, str, str, int]]) -> Path:
    """Write a minimal FanDuel salary CSV. Rows are (nickname, team, game, salary)."""

    by_game: dict[str, list[tuple[str, str, str, int]]] = {}
    for name, team, game, salary in rows:
        by_game.setdefault(game, []).append((name, team, game, salary))
    lines = [SALARY_HEADER]
    index = 0
    for game, game_rows in by_game.items():
        for name, team, _game, salary in game_rows:
            opp = game.split("@")[1] if game.split("@")[0] == team else game.split("@")[0]
            index += 1
            lines.append(
                f"{index},{'QB'},{name},{name},{name},10.0,1,{salary},{game},{team},{opp},,,"
                ",,QB/FLEX"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_lineups(path: Path, names: list[str]) -> Path:
    seats = list(names) + [""] * (9 - len(names))
    path.write_text(f"{LINEUP_HEADER}\n" + ",".join(seats) + "\n", encoding="utf-8")
    return path


def _pbp_frame(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """Fake play-by-play frame with precomputed actual points per player."""

    return pd.DataFrame(
        [
            {"season": 2026, "week": 3, "player_name": name, "team": team, "fd_actual": points}
            for name, team, points in rows
        ]
    )


def test_zero_exposure_scorer_is_flagged_and_non_slate_team_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    salary = _write_salary(
        tmp_path / "salary.csv",
        [
            ("Alpha One", "AAA", "AAA@BBB", 5000),
            ("Bravo One", "BBB", "AAA@BBB", 5000),
        ],
    )
    lineups = _write_lineups(tmp_path / "lineups.csv", ["Alpha One"])

    def fake_points(pbp: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
        return pbp

    monkeypatch.setattr(
        "ceminidfs.pipeline.fade_coverage.actual_week_fantasy_points", fake_points
    )
    # CCC played that week but is not on the salary CSV slate.
    pbp = _pbp_frame(
        [
            ("Alpha One", "AAA", 8.0),
            ("Bravo One", "BBB", 20.0),
            ("Ghost One", "CCC", 20.0),
        ]
    )

    coverage = team_coverage(
        3, salary, lineups, season=2026, threshold=18.0, pbp=pbp
    )
    by_team = coverage.set_index("team")

    # BBB has zero exposure and a 20-point scorer.
    assert bool(by_team.loc["BBB", "zero_exposure"]) is True
    assert bool(by_team.loc["BBB", "faded_and_produced"]) is True
    assert float(by_team.loc["BBB", "top_scorer_points"]) == 20.0

    # CCC is not on the salary CSV. Its 20-point scorer must not be counted.
    assert "CCC" not in by_team.index
    assert set(coverage["team"]) == {"AAA", "BBB"}


def test_rostered_team_is_not_flagged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    salary = _write_salary(
        tmp_path / "salary.csv",
        [
            ("Alpha One", "AAA", "AAA@BBB", 5000),
            ("Bravo One", "BBB", "AAA@BBB", 5000),
        ],
    )
    lineups = _write_lineups(tmp_path / "lineups.csv", ["Bravo One"])

    def fake_points(pbp: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
        return pbp

    monkeypatch.setattr(
        "ceminidfs.pipeline.fade_coverage.actual_week_fantasy_points", fake_points
    )
    pbp = _pbp_frame(
        [
            ("Alpha One", "AAA", 4.0),
            ("Bravo One", "BBB", 30.0),
        ]
    )

    coverage = team_coverage(3, salary, lineups, season=2026, pbp=pbp)
    by_team = coverage.set_index("team")

    assert int(by_team.loc["BBB", "book_exposure"]) == 1
    assert bool(by_team.loc["BBB", "zero_exposure"]) is False
    assert bool(by_team.loc["BBB", "faded_and_produced"]) is False


def test_threshold_defaults_to_18_and_governs_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    salary = _write_salary(
        tmp_path / "salary.csv",
        [
            ("Alpha One", "AAA", "AAA@BBB", 5000),
            ("Bravo One", "BBB", "AAA@BBB", 5000),
        ],
    )
    lineups = _write_lineups(tmp_path / "lineups.csv", ["Alpha One"])
    pbp = _pbp_frame([("Bravo One", "BBB", 17.9)])

    def fake_points(frame: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
        return frame

    monkeypatch.setattr(
        "ceminidfs.pipeline.fade_coverage.actual_week_fantasy_points", fake_points
    )

    coverage = team_coverage(3, salary, lineups, season=2026, pbp=pbp)
    row = coverage.set_index("team").loc["BBB"]
    assert DEFAULT_PRODUCED_THRESHOLD == 18.0
    assert bool(row["faded_and_produced"]) is False

    raised = team_coverage(3, salary, lineups, season=2026, threshold=17.0, pbp=pbp)
    assert bool(raised.set_index("team").loc["BBB", "faded_and_produced"]) is True


def test_rollup_counts_a_team_twice_when_it_fails_in_two_weeks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    salary = _write_salary(
        tmp_path / "salary.csv",
        [
            ("Alpha One", "AAA", "AAA@BBB", 5000),
            ("Bravo One", "BBB", "AAA@BBB", 5000),
        ],
    )
    lineups = _write_lineups(tmp_path / "lineups.csv", ["Alpha One"])
    pbp = _pbp_frame(
        [
            ("Alpha One", "AAA", 5.0),
            ("Bravo One", "BBB", 25.0),
        ]
    )

    def fake_points(frame: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
        return frame

    monkeypatch.setattr(
        "ceminidfs.pipeline.fade_coverage.actual_week_fantasy_points", fake_points
    )
    # season_rollup uses the module-level loader, so supply the frame through it.
    monkeypatch.setattr(
        "ceminidfs.pipeline.fade_coverage.load_season_pbp", lambda season: pbp
    )

    rollup = season_rollup(
        2026,
        [1, 2],
        salary_paths={1: salary, 2: salary},
        lineups_paths={1: lineups, 2: lineups},
    )

    assert list(rollup["team"]) == ["BBB"]
    assert int(rollup.loc[0, "faded_and_produced_weeks"]) == 2
    assert rollup.loc[0, "weeks"] == "1,2"


class _FakePlayer:
    """Hashable player stub with the pydfs fields the guards read."""

    def __init__(
        self, name: str, team: str, salary: int, *, injured: bool = False
    ) -> None:
        self.id = name
        self.full_name = name
        self.team = team
        self.salary = float(salary)
        self.fppg = 10.0
        self.is_injured = injured
        self.positions = ("RB",)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _FakePlayer) and self.id == other.id


class _FakePool:
    """Minimal pydfs-like pool. Enough for the dart guard."""

    def __init__(self, players: list[_FakePlayer]):
        self.all_players = list(players)
        self.removed_players: set[_FakePlayer] = set()

    @property
    def filtered_players(self) -> list[_FakePlayer]:
        return [p for p in self.all_players if p not in self.removed_players]

    def remove_player(self, player: _FakePlayer) -> None:
        self.removed_players.add(player)

    def restore_player(self, player: _FakePlayer) -> None:
        self.removed_players.discard(player)


def _player(name: str, team: str, salary: int, *, injured: bool = False) -> _FakePlayer:
    return _FakePlayer(name, team, salary, injured=injured)


def test_keep_team_dart_keeps_the_cheapest_eligible_player_on_a_cut_team() -> None:
    # The normal path removed every FOX player: the whole roster sits above the
    # 5000 cut. AAA and BBB have no player at or below the cut, so the rule
    # cannot keep one.
    players = [
        _player("Alpha Star", "AAA", 9000),
        _player("Fox Cheap", "FOX", 4800),
        _player("Fox Pricey", "FOX", 7000),
        _player("Fox Hurt", "FOX", 4000, injured=True),
        _player("Bravo Star", "BBB", 8000),
    ]
    pool = _FakePool(players)
    for player in players:
        if player.salary > 5000 or player.team == "FOX":
            pool.remove_player(player)
    optimizer = SimpleNamespace(player_pool=pool)

    kept = apply_team_dart_guard(optimizer, 5000)

    # Only FOX had an eligible player at or below the dart salary.
    assert [record["team"] for record in kept] == ["FOX"]
    assert kept[0]["player"] == "Fox Cheap"
    eligible = {p.full_name for p in pool.filtered_players}
    assert eligible == {"Fox Cheap"}
    # The cheapest FOX player is OUT. The rule did not revive him.
    assert "Fox Hurt" not in eligible


def test_keep_team_dart_off_by_default_and_leaves_a_covered_team_alone() -> None:
    players = [
        _player("Alpha Cheap", "AAA", 4500),
        _player("Alpha Star", "AAA", 9000),
    ]
    pool = _FakePool(players)
    pool.remove_player(players[1])
    optimizer = SimpleNamespace(player_pool=pool)

    assert apply_team_dart_guard(optimizer, 0) == []
    assert apply_team_dart_guard(optimizer, -1) == []
    assert apply_team_dart_guard(optimizer, 5000) == []
    assert "Alpha Cheap" in {p.full_name for p in pool.filtered_players}


def test_soft_fade_discounts_a_team_and_never_removes_it() -> None:
    players = [_player("Cin Star", "CIN", 9000), _player("Sea Star", "SEA", 9000)]
    optimizer = SimpleNamespace(
        player_pool=_FakePool(players),
        set_fantasy_points_strategy=lambda strategy: setattr(
            optimizer, "fantasy_points_strategy", strategy
        ),
    )

    weights = apply_soft_fade(optimizer, {"CIN": 0.5})

    assert weights == {"CIN": 0.5}
    strategy = optimizer.fantasy_points_strategy
    assert strategy.get_player_fantasy_points(players[0]) == pytest.approx(5.0)
    assert strategy.get_player_fantasy_points(players[1]) == pytest.approx(10.0)
    assert len(optimizer.player_pool.filtered_players) == 2


def test_normalize_soft_fade_weights_keeps_team_abbreviations_and_clamps() -> None:
    weights = normalize_soft_fade_weights({"cin": 0.4, "JAC": 0.0, "WAS": 2.0})
    assert weights == {"CIN": 0.4, "JAX": 0.65, "WAS": 1.0}
