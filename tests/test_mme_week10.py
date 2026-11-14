"""Week 10 guardrails for the FanDuel 150-lineup book."""

import csv
from pathlib import Path

import pandas as pd
import pytest

from ceminidfs.data.stadiums import normalize_team_abbr
from ceminidfs.export.mme_portfolio import (
    Candidate,
    PoolPlayer,
    canon_game,
    canon_position,
    candidate_from_players,
    fold_name,
    players_from_frame,
    verify_book,
)
from ceminidfs.export.mme_week10 import (
    BOOK_CAP,
    CONTEST_PREFIX,
    DESKTOP_NOV14,
    IDS_PATH,
    MAIN_GAMES,
    NAMED_EXCLUDES,
    PLAYER_CAP_NAMES,
    QB_STARTERS,
    RESERVE_VS_HUB,
    RUN_DIR,
    SALARY_PATH,
    STARTER_FLOORS,
    adjust_tails_week10,
    build_week10_pool,
    empty_opportunity_index,
    player_cap_map,
    score_week10_frame,
)
from ceminidfs.export.recap_guards import RB_PAIR_CAP, RB_TE_CAP, write_team_exposure_fade


def test_caps_and_starter_table_match_the_week10_budget():
    assert BOOK_CAP == {"QB": 36, "RB": 38, "WR": 38, "TE": 38, "DST": 33}
    assert RB_PAIR_CAP == 24
    assert RB_TE_CAP == 9
    assert len(QB_STARTERS) == 20
    assert len(MAIN_GAMES) == 10
    assert "NE@DET" not in MAIN_GAMES
    assert STARTER_FLOORS["carson beck"] == 14.2
    assert STARTER_FLOORS["kyle mccord"] == 14.0
    assert PLAYER_CAP_NAMES["kenneth walker iii"] == 12
    assert PLAYER_CAP_NAMES["c.j. stroud"] == 12
    assert PLAYER_CAP_NAMES["donte thornton jr."] == 6
    assert RESERVE_VS_HUB <= NAMED_EXCLUDES
    assert fold_name("Chris Bell") in NAMED_EXCLUDES
    assert fold_name("Jonathon Brooks") in NAMED_EXCLUDES
    assert fold_name("Puka Nacua") in RESERVE_VS_HUB


def test_week10_tails_follow_the_dome_and_wind_card():
    assert adjust_tails_week10("SF@DAL", "SF", "WR", "Deebo Samuel Sr.", 10, 20) == pytest.approx(
        (10.6, 21.2)
    )
    assert adjust_tails_week10("SF@DAL", "SF", "RB", "Christian McCaffrey", 10, 20) == pytest.approx(
        (10.6, 21.2)
    )
    assert adjust_tails_week10("SF@DAL", "DAL", "RB", "Javonte Williams", 10, 20) == pytest.approx(
        (10.0, 20.0)
    )
    assert adjust_tails_week10("CAR@NO", "NO", "QB", "Tyler Shough", 10, 20) == pytest.approx(
        (10.4, 20.8)
    )
    assert adjust_tails_week10("CAR@NO", "CAR", "RB", "Chuba Hubbard", 10, 20) == pytest.approx(
        (10.6, 21.2)
    )
    assert adjust_tails_week10("SEA@LV", "SEA", "RB", "Zach Charbonnet", 10, 20) == pytest.approx(
        (10.6, 21.2)
    )
    assert adjust_tails_week10("SEA@LV", "LV", "WR", "Brock Bowers", 10, 20) == pytest.approx(
        (10.4, 20.8)
    )
    assert adjust_tails_week10("BUF@NYJ", "NYJ", "WR", "Garrett Wilson", 10, 20) == pytest.approx(
        (9.2, 18.4)
    )
    assert adjust_tails_week10("BUF@NYJ", "BUF", "RB", "James Cook III", 10, 20) == pytest.approx(
        (10.6, 21.2)
    )
    assert adjust_tails_week10("BUF@NYJ", "BUF", "DST", "Buffalo", 10, 20) == pytest.approx(
        (10.6, 21.2)
    )
    assert adjust_tails_week10("BUF@NYJ", "NYJ", "DST", "New York", 10, 20) == pytest.approx(
        (10.0, 20.0)
    )
    assert adjust_tails_week10("HOU@CLE", "HOU", "QB", "C.J. Stroud", 10, 20) == pytest.approx(
        (9.0, 18.0)
    )
    assert adjust_tails_week10("HOU@CLE", "CLE", "WR", "Jerry Jeudy", 10, 20) == pytest.approx(
        (9.0, 18.0)
    )
    assert adjust_tails_week10("HOU@CLE", "HOU", "RB", "David Montgomery", 10, 20) == pytest.approx(
        (10.5, 21.0)
    )
    assert adjust_tails_week10("HOU@CLE", "CLE", "TE", "Harold Fannin Jr.", 10, 20) == pytest.approx(
        (10.5, 21.0)
    )
    assert adjust_tails_week10("MIN@GB", "GB", "QB", "Jordan Love", 10, 20) == pytest.approx(
        (10.0, 20.0)
    )


def _row(**kwargs: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": "136490-1",
        "Position": "QB",
        "First Name": "Carson",
        "Nickname": "Carson Beck",
        "Last Name": "Beck",
        "FPPG": 0.0,
        "Played": 1,
        "Salary": 6000,
        "Game": "LAR@ARI",
        "Team": "ARI",
        "Opponent": "LAR",
        "Injury Indicator": "",
        "Injury Details": "",
    }
    base.update(kwargs)
    return base


def _ceiling(ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {"player_id": ids, "lagged_fd": [0.0] * len(ids), "p90": [float("nan")] * len(ids), "p99": [float("nan")] * len(ids)}
    )


def test_zero_fppg_starters_enter_and_backups_and_excludes_stay_out():
    salary = pd.DataFrame(
        [
            _row(),
            _row(
                **{
                    "Id": "136490-2",
                    "Nickname": "Joey Aguilar",
                    "First Name": "Joey",
                    "Last Name": "Aguilar",
                    "FPPG": 12.0,
                }
            ),
            _row(
                **{
                    "Id": "136490-3",
                    "Nickname": "Kyle McCord",
                    "First Name": "Kyle",
                    "Last Name": "McCord",
                    "Team": "MIA",
                    "Opponent": "IND",
                    "Game": "MIA@IND",
                    "FPPG": 0.0,
                }
            ),
            _row(
                **{
                    "Id": "136490-4",
                    "Nickname": "Brady Cook",
                    "First Name": "Brady",
                    "Last Name": "Cook",
                    "Team": "MIA",
                    "Opponent": "IND",
                    "Game": "MIA@IND",
                    "FPPG": 8.0,
                }
            ),
            _row(
                **{
                    "Id": "136490-5",
                    "Position": "WR",
                    "Nickname": "Chris Bell",
                    "First Name": "Chris",
                    "Last Name": "Bell",
                    "Team": "MIA",
                    "Opponent": "IND",
                    "Game": "MIA@IND",
                    "FPPG": 2.9,
                    "Injury Indicator": "D",
                    "Injury Details": "Knee",
                }
            ),
            _row(
                **{
                    "Id": "136490-6",
                    "Position": "WR",
                    "Nickname": "Anthony Gould",
                    "First Name": "Anthony",
                    "Last Name": "Gould",
                    "Team": "IND",
                    "Opponent": "MIA",
                    "Game": "MIA@IND",
                    "Salary": 4200,
                    "FPPG": 0.42,
                    "Played": 5,
                }
            ),
            _row(
                **{
                    "Id": "136490-7",
                    "Position": "RB",
                    "Nickname": "Josh Jacobs",
                    "First Name": "Josh",
                    "Last Name": "Jacobs",
                    "Team": "GB",
                    "Opponent": "MIN",
                    "Game": "MIN@GB",
                    "Salary": 6900,
                    "FPPG": 9.5,
                    "Injury Indicator": "O",
                }
            ),
        ]
    )
    frame = score_week10_frame(
        salary,
        _ceiling([f"136490-{index}" for index in range(1, 8)]),
        {"skill": [], "dst": []},
        empty_opportunity_index(),
    ).set_index("player_id")
    assert frame.loc["136490-1", "never_enter"] == 0
    assert frame.loc["136490-1", "portfolio_lagged"] == pytest.approx(14.2)
    assert frame.loc["136490-1", "portfolio_fpts"] > 0
    assert frame.loc["136490-3", "portfolio_lagged"] == pytest.approx(14.0)
    assert frame.loc["136490-3", "never_enter"] == 0
    assert frame.loc["136490-2", "never_enter"] == 1
    assert frame.loc["136490-4", "never_enter"] == 1
    assert frame.loc["136490-5", "never_enter"] == 1
    assert frame.loc["136490-7", "never_enter"] == 1
    assert frame.loc["136490-6", "never_enter"] == 0
    assert frame.loc["136490-6", "portfolio_fpts"] > 0
    players = players_from_frame(frame.reset_index())
    caps = player_cap_map(players)
    assert caps == {}


def _salary_file() -> Path | None:
    for path in (DESKTOP_NOV14, SALARY_PATH, Path("nov14.csv")):
        if path.is_file():
            return path
    return None


def _pool_from_salary(path: Path) -> tuple[list[PoolPlayer], list[PoolPlayer]]:
    salary = pd.read_csv(path)
    ceiling = pd.DataFrame(
        {
            "player_id": salary["Id"].astype(str),
            "lagged_fd": pd.to_numeric(salary["FPPG"], errors="coerce").fillna(0.0),
            "p90": float("nan"),
            "p99": float("nan"),
        }
    )
    return build_week10_pool(salary, ceiling, empty_opportunity_index())


@pytest.mark.skipif(_salary_file() is None, reason="Week 10 salary file is absent")
def test_salary_file_pool_keeps_twenty_starters_and_no_backups():
    _players, pool = _pool_from_salary(_salary_file())  # type: ignore[arg-type]
    quarters = [player for player in pool if player.position == "QB"]
    by_team = {player.team: player.nickname for player in quarters}
    assert set(by_team) == set(QB_STARTERS)
    for team, name in QB_STARTERS.items():
        assert fold_name(by_team[team]) == fold_name(name)
    assert fold_name("Carson Beck") in {fold_name(player.nickname) for player in quarters}
    assert fold_name("Kyle McCord") in {fold_name(player.nickname) for player in quarters}
    blocked = {
        fold_name(player.nickname)
        for player in pool
        if fold_name(player.nickname) in NAMED_EXCLUDES or fold_name(player.nickname) in RESERVE_VS_HUB
    }
    assert blocked == set()
    counts: dict[str, int] = {}
    for player in pool:
        if player.position in {"WR", "TE"}:
            counts[player.team] = counts.get(player.team, 0) + 1
    short = [team for team in QB_STARTERS if counts.get(team, 0) < 2]
    assert short == []


def _book_players(salary: pd.DataFrame, ids: list[str]) -> list[PoolPlayer]:
    meta = {str(row["Id"]): row for row in salary.to_dict(orient="records")}
    players = []
    for pid in ids:
        row = meta[pid]
        players.append(
            PoolPlayer(
                player_id=pid,
                nickname=str(row["Nickname"]),
                team=normalize_team_abbr(str(row["Team"])),
                opp=normalize_team_abbr(str(row["Opponent"])),
                game=canon_game(row["Game"]),
                position=canon_position(row["Position"]),
                salary=int(float(row["Salary"])),
                fpts=1.0,
                lagged=1.0,
                p90=1.0,
                p99=1.0,
                sigma=0.0,
                never_enter=fold_name(row["Nickname"]) in NAMED_EXCLUDES,
            )
        )
    return players


@pytest.mark.skipif(not IDS_PATH.is_file() or _salary_file() is None, reason="Week 10 book is absent")
def test_saved_book_meets_the_week10_gates():
    salary = pd.read_csv(_salary_file())  # type: ignore[arg-type]
    with IDS_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    lineups = rows[1:]
    assert len(lineups) == 150
    book: list[Candidate] = []
    seen: set[frozenset[str]] = set()
    for row in lineups:
        ids = [cell.strip() for cell in row if cell.strip()]
        assert len(ids) == 9
        assert all(pid.startswith(CONTEST_PREFIX) for pid in ids)
        players = _book_players(salary, ids)
        item = candidate_from_players(players, banned_teams=frozenset())
        assert item is not None
        book.append(item)
        seen.add(item.key)
    assert len(seen) == 150
    audit = verify_book(
        book,
        _book_players(salary, sorted({pid for item in book for pid in item.ids})),
        caps=BOOK_CAP,
        banned_teams=frozenset(),
        contest_prefix=CONTEST_PREFIX,
        pair_cap=RB_PAIR_CAP,
        rb_te_cap=RB_TE_CAP,
        player_caps={
            player.player_id: PLAYER_CAP_NAMES[fold_name(player.nickname)]
            for player in _book_players(salary, sorted({pid for item in book for pid in item.ids}))
            if fold_name(player.nickname) in PLAYER_CAP_NAMES
        },
    )
    assert audit["lineups"] == 150
    assert 9 - int(audit["max_share"]) >= 3
    assert int(audit["bringback"]) >= 113
    assert int(audit["secondary"]) >= 75
    assert int(audit["unstacked_rb_te"]) == 0
    meta = {
        player.player_id: player
        for player in _book_players(salary, sorted({pid for item in book for pid in item.ids}))
    }
    counts: dict[str, int] = {}
    quarters: set[str] = set()
    for item in book:
        for pid in item.ids:
            player = meta[pid]
            counts[fold_name(player.nickname)] = counts.get(fold_name(player.nickname), 0) + 1
            assert fold_name(player.nickname) not in NAMED_EXCLUDES
            assert fold_name(player.nickname) not in RESERVE_VS_HUB
            if player.position == "QB":
                quarters.add(fold_name(player.nickname))
                assert fold_name(player.nickname) == fold_name(QB_STARTERS[player.team])
    assert counts.get("kenneth walker iii", 0) <= 12
    assert counts.get("c.j. stroud", 0) <= 12
    assert quarters.isdisjoint(
        {
            fold_name(name)
            for name in (
                "Carson Wentz",
                "Kyler Murray",
                "Sam Darnold",
                "Shedeur Sanders",
                "Dillon Gabriel",
                "Justin Fields",
                "Tua Tagovailoa",
                "Anthony Richardson Sr.",
                "Aidan O'Connell",
                "Mac Jones",
                "Jalen Milroe",
                "Davis Mills",
            )
        }
    )
    fade = (RUN_DIR / "fade-coverage-w10.md").read_text(encoding="utf-8")
    audit_text = Path("reports/audit/fade-coverage-w10.md").read_text(encoding="utf-8")
    assert "Team exposure counts seats" in fade
    assert fade == audit_text
    resolved = (RUN_DIR / "lineups_resolved_2026-11-15.csv").read_text(encoding="utf-8").splitlines()[0]
    assert resolved == "fd_id,player_name,team,pos,salary,source_file,fixture_id,retrieved_et"


def test_exposure_fade_writes_the_run_copy(tmp_path: Path):
    player = PoolPlayer(
        player_id="136490-1",
        nickname="Carson Beck",
        team="ARI",
        opp="LAR",
        game="LAR@ARI",
        position="QB",
        salary=6000,
        fpts=14.0,
        lagged=14.0,
        p90=18.0,
        p99=22.0,
        sigma=1.0,
        never_enter=False,
    )
    ids = ("136490-1",)
    item = Candidate(
        ids=ids,
        key=frozenset(ids),
        salary=6000,
        blend=14.0,
        bringback=False,
        secondary=False,
        catchers=0,
        dst_conflict=False,
        positions=(("136490-1", "QB"),),
        game="LAR@ARI",
        tags="",
    )
    run = tmp_path / "run"
    audit = tmp_path / "audit"
    written = write_team_exposure_fade(
        [item],
        [player],
        season=2026,
        week=10,
        audit_dir=audit,
        run_dir=run,
    )
    text = (run / "fade-coverage-w10.md").read_text(encoding="utf-8")
    assert "Team exposure counts seats" in text
    assert "ARI" in text
    assert written[0].read_text(encoding="utf-8") == text
