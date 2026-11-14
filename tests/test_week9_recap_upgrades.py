"""Week 9 recap fixes: Doubtful vacuum, book scaling, and exposure caps."""

import csv
from pathlib import Path

import pandas as pd
import pytest

from ceminidfs.export.mme_portfolio import (
    Candidate,
    PoolPlayer,
    _count_floors,
    _verify_totals,
    select_book,
    verify_book,
    write_book_files,
)
from ceminidfs.export.recap_guards import (
    Opportunity,
    OpportunityIndex,
    fold_key,
    fragile_rb_caps,
    load_scheme_vetoes,
    prelock_salary_archive,
    questionable_exposure_caps,
    scaled_book_caps,
    write_lineups_resolved_csv,
    write_team_exposure_fade,
)
from ceminidfs.situational.engine import _score_row
from ceminidfs.situational.injuries import VACUUM_DONOR_TOKENS, apply_injury_vacuum


def test_doubtful_donors_are_zeroed_and_do_not_absorb():
    assert VACUUM_DONOR_TOKENS == {"O", "OUT", "IR", "D", "DOUBTFUL"}
    frame = pd.DataFrame(
        [
            _skill("Out Receiver", "WR", "O", lagged=10.0, targets=8.0),
            _skill("Cam Skattebo", "RB", "D", lagged=12.0, targets=2.0, carries=10.0),
            _skill("Brenen Thompson", "WR", "DOUBTFUL", lagged=9.0, targets=6.0),
            _skill(
                "Rotation Wideout",
                "WR",
                "",
                lagged=8.0,
                targets=7.0,
                receptions=4.0,
                yards=50.0,
            ),
            _skill(
                "Rotation Back",
                "RB",
                "",
                lagged=7.0,
                targets=1.0,
                carries=8.0,
                rush_yards=40.0,
            ),
        ]
    )
    out = apply_injury_vacuum(frame, None)
    skattebo = _named(out, "Cam Skattebo")
    thompson = _named(out, "Brenen Thompson")
    wideout = _named(out, "Rotation Wideout")
    back = _named(out, "Rotation Back")
    assert skattebo["lagged_fd"] == 0.0
    assert thompson["lagged_fd"] == 0.0
    assert skattebo["vacated_target_boost"] == 0.0
    assert skattebo["vacated_carry_boost"] == 0.0
    assert thompson["vacated_target_boost"] == 0.0
    assert wideout["vacated_target_boost"] > 0.0
    assert back["vacated_carry_boost"] == pytest.approx(10.0)
    assert wideout["lagged_fd"] > 8.0
    assert back["lagged_fd"] > 7.0


def test_score_row_zeros_a_doubtful_player():
    scored = _score_row(
        {
            "player_id": "rb-1",
            "position": "RB",
            "injury_status": "DOUBTFUL",
            "lagged_fd": 12.5,
            "q4_flag": True,
        },
        {},
    )
    assert scored["lagged_fd"] == 0.0
    assert scored["q4_flag"] is False


def test_book_floors_scale_for_133_and_stay_exact_at_150():
    assert _count_floors(150) == (113, 75, 15)
    assert _count_floors(133) == (101, 67, 14)
    _verify_totals(15, 113, 75, 150)
    _verify_totals(14, 101, 67, 133)
    with pytest.raises(AssertionError):
        _verify_totals(15, 101, 67, 133)
    with pytest.raises(AssertionError, match="bring-back"):
        _verify_totals(0, 100, 67, 133)
    assert scaled_book_caps(133) == {"QB": 31, "RB": 29, "WR": 29, "TE": 29, "DST": 29}
    assert scaled_book_caps(150) == {"QB": 36, "RB": 33, "WR": 33, "TE": 33, "DST": 33}


def test_select_book_uses_the_scaled_bringback_floor():
    bringbacks = [_lineup(index, 1.0, True) for index in range(120)]
    fillers = [_lineup(200 + index, 50.0, False) for index in range(40)]
    scaled = select_book(bringbacks + fillers, count=133)
    classic = select_book(bringbacks + fillers, count=150)
    assert sum(item.bringback for item in scaled) == 101
    assert sum(item.bringback for item in classic) == 113
    open_fillers = [_lineup(400 + index, 50.0, False) for index in range(133)]
    forced = select_book(
        bringbacks + open_fillers,
        count=133,
        bringback_min=0,
        secondary_min=0,
    )
    assert sum(item.bringback for item in forced) == 0
    cheap = [_cheap_lineup(index) for index in range(10)]
    short = select_book(
        cheap,
        count=10,
        bringback_min=0,
        secondary_min=0,
        allow_cheap=15,
        caps={"WR": 10},
    )
    assert len(short) == 1


def test_verify_book_accepts_the_scaled_133_floor():
    good = _book(133, bringbacks=101)
    audit = verify_book(
        good,
        _players(good),
        caps={"WR": 133},
        banned_teams=frozenset(),
        contest_prefix="",
        count=133,
    )
    assert audit["lineups"] == 133
    assert audit["bringback"] == 101
    short = _book(133, bringbacks=100)
    with pytest.raises(AssertionError, match="bring-back"):
        verify_book(
            short,
            _players(short),
            caps={"WR": 133},
            banned_teams=frozenset(),
            contest_prefix="",
            count=133,
        )


def test_prelock_writes_both_salary_copies(tmp_path: Path):
    source = tmp_path / "FanDuel-NFL-2026-11-08-136184-players-list.csv"
    source.write_text("Id,Nickname,Salary\n136184-1,Cam Skattebo,6000\n", encoding="utf-8")
    recap = tmp_path / "dfs-recap"
    slate = tmp_path / "dfs-slate"
    audit = tmp_path / "audit"
    recap.mkdir()
    slate.mkdir()
    written = prelock_salary_archive(
        source,
        season=2026,
        week=9,
        work_dir=tmp_path / "run",
        slate_date="2026-11-08",
        fixture_id="136184",
        recap_root=recap,
        slate_root=slate,
        audit_dir=audit,
    )
    gate = recap / "2026-11-08" / "_src_fd_sun.csv"
    players = recap / "2026-11-08" / "in" / "fd_players_136184.csv"
    slate_copy = slate / "2026-11-08" / "_src_fd_sun.csv"
    body = source.read_bytes()
    assert gate.read_bytes() == body
    assert players.read_bytes() == body
    assert slate_copy.read_bytes() == body
    assert gate in written and players in written and slate_copy in written
    fade = audit / "fade-coverage-w9.md"
    recap_fade = recap / "2026-11-08" / "fade-coverage-w9.md"
    assert fade.is_file() and recap_fade.is_file()
    assert "Pre-lock salary copy is on disk." in fade.read_text(encoding="utf-8")


def test_lineup_provenance_and_team_exposure(tmp_path: Path):
    book = [_lineup(1, 10.0, True), _lineup(2, 9.0, True)]
    shared = "p1-0"
    second_ids = (shared,) + book[1].ids[1:]
    book[1] = Candidate(
        ids=second_ids,
        key=frozenset(second_ids),
        salary=book[1].salary,
        blend=book[1].blend,
        bringback=True,
        secondary=True,
        catchers=1,
        dst_conflict=False,
        positions=tuple((pid, "WR") for pid in second_ids),
        game="NYG@PHI",
        tags="",
    )
    players = _players(book)
    path = write_lineups_resolved_csv(
        tmp_path / "resolved.csv",
        book,
        players,
        source_file="data/slates/2026-11-08_fd_sun.csv",
        fixture_id="136184",
        retrieved_et="2026-11-08T10:44:00-05:00",
    )
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["fd_id"] for row in rows].count(shared) == 1
    assert set(rows[0]) == {
        "fd_id",
        "player_name",
        "team",
        "pos",
        "salary",
        "source_file",
        "fixture_id",
        "retrieved_et",
    }
    assert rows[0]["source_file"] == "data/slates/2026-11-08_fd_sun.csv"
    assert rows[0]["fixture_id"] == "136184"
    assert rows[0]["retrieved_et"] == "2026-11-08T10:44:00-05:00"
    audit = tmp_path / "audit"
    recap = tmp_path / "dfs-recap"
    recap.mkdir()
    written = write_team_exposure_fade(
        book,
        players,
        season=2026,
        week=9,
        audit_dir=audit,
        recap_root=recap,
        slate_date="2026-11-08",
    )
    text = written[0].read_text(encoding="utf-8")
    assert "NYG" in text
    assert (recap / "2026-11-08" / "fade-coverage-w9.md").read_text(encoding="utf-8") == text
    upload = tmp_path / "upload.csv"
    ids = tmp_path / "ids.csv"
    write_book_files(
        book,
        upload,
        ids,
        season=2026,
        week=9,
        players=players,
        slate_date="2026-11-08",
        audit_dir=audit,
        recap_root=recap,
    )
    assert upload.is_file() and ids.is_file()
    assert "Team exposure counts seats" in (audit / "fade-coverage-w9.md").read_text(
        encoding="utf-8"
    )


def test_scheme_questionable_and_fragile_caps(tmp_path: Path):
    scheme = tmp_path / "scheme.md"
    scheme.write_text(
        "\n".join(
            [
                "# scheme",
                "Josh Jacobs rush_yds UNDER 85.5",
                "| Justin Herbert | QB | pass_yds UNDER | 250 |",
                "Puka Nacua rec_yds OVER 70",
                "",
            ]
        ),
        encoding="utf-8",
    )
    vetoes = load_scheme_vetoes(scheme, count=133)
    assert vetoes[fold_key("Josh Jacobs")] == 10
    assert vetoes[fold_key("Justin Herbert")] == 10
    assert fold_key("Puka Nacua") not in vetoes
    table = tmp_path / "scheme_vetoes_2026-11-08.csv"
    table.write_text(
        "player,market,side\nJosh Jacobs,rush_yds,UNDER\nPuka Nacua,rec_yds,OVER\n",
        encoding="utf-8",
    )
    assert load_scheme_vetoes(table, count=133) == {fold_key("Josh Jacobs"): 10}
    assert load_scheme_vetoes(None, count=133) == {}

    salary = pd.DataFrame(
        [
            {"Id": "q-1", "Nickname": "George Pickens", "Injury Indicator": "Q"},
            {
                "Id": "q-2",
                "Nickname": "Confirmed Back",
                "Injury Indicator": "Q",
                "Confirmed Active": "yes",
            },
            {"Id": "q-3", "Nickname": "Healthy", "Injury Indicator": ""},
        ]
    )
    pool = [
        _pool("q-1", "George Pickens", "WR", 7000),
        _pool("q-2", "Confirmed Back", "WR", 7000),
        _pool("q-3", "Healthy", "RB", 6000),
    ]
    q_caps = questionable_exposure_caps(pool, salary, count=133)
    assert q_caps == {"q-1": 15}

    index = OpportunityIndex(
        by_name={
            ("HOU", "woody marks"): Opportunity(4, 6, 20),
            ("HOU", "bell cow"): Opportunity(8, 12, 40),
            ("NYG", "priced back"): Opportunity(1, 1, 4),
        },
        active_teams=frozenset({"HOU", "DAL"}),
    )
    rbs = [
        _pool("rb-1", "Woody Marks", "RB", 6500, "HOU"),
        _pool("rb-2", "Bell Cow", "RB", 5400, "HOU"),
        _pool("rb-3", "Priced Back", "RB", 8000, "NYG"),
        _pool("rb-4", "Unknown Back", "RB", 5000, "DAL"),
        _pool("rb-5", "Sideline Back", "RB", 4500, "LAR"),
    ]
    assert fragile_rb_caps(rbs, index, count=133) == {"rb-1": 19, "rb-4": 19}


def _skill(
    name: str,
    position: str,
    injury: str,
    *,
    lagged: float,
    targets: float,
    carries: float = 0.0,
    receptions: float = 0.0,
    yards: float = 0.0,
    rush_yards: float = 0.0,
) -> dict[str, object]:
    return {
        "player_name": name,
        "team": "NYG",
        "salary_team": "NYG",
        "position": position,
        "injury_indicator": injury,
        "lagged_fd": lagged,
        "targets_per_game": targets,
        "carries_per_game": carries,
        "receptions_per_game": receptions,
        "rec_yds_per_game": yards,
        "rec_td_per_game": 0.0,
        "rush_yds_per_game": rush_yards,
        "rush_td_per_game": 0.0,
        "inside10_target_share": 0.0,
    }


def _named(frame: pd.DataFrame, name: str) -> pd.Series:
    return frame.loc[frame["player_name"].eq(name)].iloc[0]


def _lineup(index: int, blend: float, bringback: bool, salary: int = 59600) -> Candidate:
    ids = tuple(f"p{index}-{slot}" for slot in range(9))
    return Candidate(
        ids=ids,
        key=frozenset(ids),
        salary=salary,
        blend=blend,
        bringback=bringback,
        secondary=bringback,
        catchers=1,
        dst_conflict=False,
        positions=tuple((pid, "WR") for pid in ids),
        game="NYG@PHI",
        tags="",
    )


def _cheap_lineup(index: int) -> Candidate:
    return _lineup(900 + index, 5.0, False, salary=1000)


def _book(count: int, bringbacks: int) -> list[Candidate]:
    return [_lineup(index, 10.0, index < bringbacks) for index in range(count)]


def _players(book: list[Candidate]) -> list[PoolPlayer]:
    return [
        PoolPlayer(
            player_id=pid,
            nickname=pid,
            team="NYG",
            opp="PHI",
            game="NYG@PHI",
            position="WR",
            salary=5000,
            fpts=10.0,
        )
        for item in book
        for pid in item.ids
    ]


def _pool(
    player_id: str,
    nickname: str,
    position: str,
    salary: int,
    team: str = "DAL",
) -> PoolPlayer:
    return PoolPlayer(
        player_id=player_id,
        nickname=nickname,
        team=team,
        opp="NYG",
        game=f"{team}@NYG",
        position=position,
        salary=salary,
        fpts=8.0,
        last_name=nickname.split()[-1],
    )
