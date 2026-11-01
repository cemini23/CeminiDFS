"""Portfolio rules for the Week 6 FanDuel 150-lineup book."""

import pandas as pd
import pytest

from ceminidfs.export.mme_portfolio import (
    MAX_SHARED,
    Candidate,
    PoolPlayer,
    adjust_tails,
    blend_points,
    build_portfolio_frame,
    catcher_count,
    dst_faces_qb_or_primary_rb,
    has_bringback,
    is_hard_exclude,
    noise_sigma,
    select_book,
    shares_ok,
    upload_cell,
)


def test_hard_exclude_tokens_backups_and_london_teams():
    assert is_hard_exclude("O", "Saquon Barkley", "PHI", "")
    assert is_hard_exclude("OUT", "Saquon Barkley", "PHI", "")
    assert is_hard_exclude("IR", "Jalen Hurts", "PHI", "")
    assert is_hard_exclude("D", "Someone", "PHI", "")
    assert is_hard_exclude("DOUBTFUL", "Someone", "PHI", "")
    assert is_hard_exclude("SUSP", "Someone", "PHI", "")
    assert is_hard_exclude("NA", "Someone", "PHI", "")
    assert is_hard_exclude("", "Case Keenum", "CHI", "")
    assert is_hard_exclude("", "Kyle Allen", "BUF", "")
    assert is_hard_exclude("Q", "Ja'Kobi Lane", "BAL", "Wrist")
    assert is_hard_exclude("", "Keagen Trost", "TB", "")
    assert is_hard_exclude("", "Alec Ingold", "LAC", "")
    assert is_hard_exclude("", "Player", "HOU", "")
    assert is_hard_exclude("", "Player", "JAX", "")
    assert is_hard_exclude("", "Player", "PHI", "Suspended")
    assert not is_hard_exclude("Q", "Caleb Williams", "CHI", "Hamstring")
    assert not is_hard_exclude("", "Josh Allen", "BUF", "")
    assert not is_hard_exclude("", "DK Metcalf", "PIT", "Illness")
    assert not is_hard_exclude("", "Tyler Higbee", "LAR", "")


def test_blend_and_sigma():
    assert blend_points(10, 20, 30) == pytest.approx(18.5)
    assert noise_sigma(20, 10) == pytest.approx(1.8)
    assert noise_sigma(5, 10) == 0.0


def test_weather_tails():
    assert adjust_tails("PIT@TB", "PIT", "WR", "DK Metcalf", 10, 20) == (9.0, 18.0)
    assert adjust_tails("PIT@TB", "TB", "QB", "Jalon Daniels", 10, 20) == (9.0, 18.0)
    assert adjust_tails("CHI@ATL", "CHI", "WR", "DJ Moore", 10, 20) == (10, 20)
    assert adjust_tails("ARI@LAR", "LAR", "WR", "Puka Nacua", 10, 20) == (10, 20)
    assert adjust_tails("BUF@LV", "BUF", "QB", "Josh Allen", 10, 20) == (10, 20)
    assert adjust_tails("PIT@TB", "TB", "RB", "Bucky Irving", 10, 20) == pytest.approx((10.6, 21.2))
    assert adjust_tails("PIT@TB", "PIT", "DST", "Pittsburgh Steelers", 10, 20) == pytest.approx(
        (10.6, 21.2)
    )
    assert adjust_tails("PIT@TB", "TB", "TE", "Cade Otton", 10, 20) == (10, 20)
    assert adjust_tails("LAC@KC", "KC", "WR", "Xavier Worthy", 10, 20) == pytest.approx((9.7, 19.4))
    assert adjust_tails("LAC@KC", "KC", "RB", "Kenneth Walker III", 10, 20) == pytest.approx(
        (10.4, 20.8)
    )
    assert adjust_tails("LAC@KC", "LAC", "TE", "Oronde Gadsden", 10, 20) == pytest.approx(
        (10.4, 20.8)
    )
    assert adjust_tails("BAL@CLE", "BAL", "QB", "Tyler Huntley", 10, 20) == (10, 20)


def _salary_row(**kwargs):
    base = {
        "Id": "135326-1",
        "Position": "QB",
        "First Name": "Tanner",
        "Nickname": "Tanner McKee",
        "Last Name": "McKee",
        "FPPG": 0.0,
        "Salary": 6000,
        "Game": "CAR@PHI",
        "Team": "PHI",
        "Opponent": "CAR",
        "Injury Indicator": "",
        "Injury Details": "",
    }
    base.update(kwargs)
    return base


def _named(player_id, position, first, nickname, last, salary, game, team, opp, injury=""):
    return _salary_row(
        **{
            "Id": player_id,
            "Position": position,
            "First Name": first,
            "Nickname": nickname,
            "Last Name": last,
            "Salary": salary,
            "Game": game,
            "Team": team,
            "Opponent": opp,
            "Injury Indicator": injury,
        }
    )


def _quantiles():
    return {
        "skill": [{"position": "QB", "bucket": "*", "n": 100, "q90": 5.0, "q99": 12.0}],
        "dst": [{"position": "DST", "bucket": "*", "n": 100, "q90": 4.0, "q99": 8.0}],
    }


def test_starter_floor_replaces_a_tiny_lag_before_the_ceiling():
    salary = pd.DataFrame([_salary_row()])
    ceiling = pd.DataFrame(
        [{"player_id": "135326-1", "lagged_fd": 1.0, "p90": 2.0, "p99": 3.0, "position": "QB"}]
    )
    frame = build_portfolio_frame(salary, ceiling, _quantiles())
    row = frame.iloc[0]
    assert row["portfolio_lagged"] == pytest.approx(15.8)
    assert row["portfolio_p90"] == pytest.approx(20.8)
    assert row["portfolio_p99"] == pytest.approx(27.8)
    assert row["never_enter"] == 0


def test_overlay_applies_weather_and_zeros_named_excludes():
    salary = pd.DataFrame(
        [
            _named("135326-pit", "WR", "DK", "DK Metcalf", "Metcalf", 6800, "PIT@TB", "PIT", "TB"),
            _named("135326-chi", "WR", "DJ", "DJ Moore", "Moore", 7000, "CHI@ATL", "CHI", "ATL"),
            _named(
                "135326-keenum", "QB", "Case", "Case Keenum", "Keenum", 6400, "CHI@ATL", "CHI", "ATL"
            ),
            _named(
                "135326-caleb",
                "QB",
                "Caleb",
                "Caleb Williams",
                "Williams",
                7900,
                "CHI@ATL",
                "CHI",
                "ATL",
                injury="Q",
            ),
        ]
    )
    ceiling = pd.DataFrame(
        [
            {"player_id": pid, "lagged_fd": 10.0, "p90": 20.0, "p99": 30.0}
            for pid in ("135326-pit", "135326-chi", "135326-keenum", "135326-caleb")
        ]
    )
    frame = build_portfolio_frame(salary, ceiling, _quantiles()).set_index("player_id")
    pit = frame.loc["135326-pit"]
    chi = frame.loc["135326-chi"]
    assert pit["portfolio_p90"] == pytest.approx(18.0)
    assert pit["portfolio_p99"] == pytest.approx(27.0)
    assert pit["portfolio_fpts"] == pytest.approx(17.0)
    assert pit["sigma"] == pytest.approx(1.44)
    assert chi["portfolio_p90"] == pytest.approx(20.0)
    assert chi["portfolio_fpts"] == pytest.approx(18.5)
    assert frame.loc["135326-keenum", "never_enter"] == 1
    assert frame.loc["135326-keenum", "portfolio_fpts"] == 0
    assert frame.loc["135326-caleb", "never_enter"] == 0
    assert frame.loc["135326-caleb", "portfolio_fpts"] == pytest.approx(18.5)


def test_upload_cell_uses_id_and_nickname():
    assert upload_cell("135326-1", "Tanner McKee") == "135326-1:Tanner McKee"


def test_uniques_allow_six_shared_players_and_reject_seven():
    left = {str(index) for index in range(9)}
    share_seven = {str(index) for index in range(7)} | {"100", "101"}
    share_six = {str(index) for index in range(6)} | {"100", "101", "102"}
    assert not shares_ok(left, share_seven, MAX_SHARED)
    assert shares_ok(left, share_six, MAX_SHARED)


def _player(player_id: str, **kwargs) -> PoolPlayer:
    base = {
        "player_id": player_id,
        "nickname": player_id,
        "team": "BUF",
        "opp": "LV",
        "game": "BUF@LV",
        "position": "WR",
        "salary": 5000,
        "fpts": 10.0,
    }
    base.update(kwargs)
    return PoolPlayer(**base)


def test_dst_rule_blocks_the_qb_and_the_primary_rb_only():
    qb = _player("qb", position="QB", team="BUF", opp="LV", salary=9500)
    lv_dst = _player("lv", position="DST", team="LV", opp="BUF", salary=3300)
    buf_dst = _player("buf", position="DST", team="BUF", opp="LV", salary=4400)
    lv_wr = _player("wr", position="WR", team="LV", opp="BUF", salary=5000)
    assert dst_faces_qb_or_primary_rb([qb, lv_dst])
    assert not dst_faces_qb_or_primary_rb([qb, buf_dst, lv_wr])
    primary = _player("rb", position="RB", team="BUF", opp="LV", salary=9000)
    cheap = _player("rb2", position="RB", team="KC", opp="LAC", game="LAC@KC", salary=4000)
    assert dst_faces_qb_or_primary_rb([primary, cheap, lv_dst])
    kc_rb = _player("kc", position="RB", team="KC", opp="LAC", game="LAC@KC", salary=9000)
    buf_cheap = _player("cheap", position="RB", team="BUF", opp="LV", salary=4000)
    assert not dst_faces_qb_or_primary_rb([kc_rb, buf_cheap, lv_dst])


def test_bringback_uses_the_quarterback_opponent():
    qb = _player("qb", position="QB", team="LAR", opp="ARI", game="ARI@LAR", salary=7800)
    mate = _player("te", position="TE", team="LAR", opp="ARI", game="ARI@LAR", salary=5200)
    wr = _player("wr", position="WR", team="LAR", opp="ARI", game="ARI@LAR", salary=7200)
    bring = _player("ari", position="WR", team="ARI", opp="LAR", game="ARI@LAR", salary=6100)
    other = _player("kc", position="WR", team="KC", opp="LAC", game="LAC@KC", salary=6100)
    assert has_bringback([qb, bring])
    assert not has_bringback([qb, other])
    assert catcher_count([qb, mate, bring]) == 1
    assert catcher_count([qb, mate, wr]) == 2


def _candidate(ids: list[str], blend: float, **kwargs) -> Candidate:
    frozen = tuple(ids)
    return Candidate(
        ids=frozen,
        key=frozenset(frozen),
        salary=kwargs.get("salary", 59600),
        blend=blend,
        bringback=kwargs.get("bringback", True),
        secondary=kwargs.get("secondary", True),
        catchers=kwargs.get("catchers", 2),
        dst_conflict=kwargs.get("dst_conflict", False),
        positions=tuple((pid, "WR") for pid in frozen),
        game="ARI@LAR",
        tags="QB+2 LAR",
    )


def test_selector_rejects_a_seventh_shared_player_and_a_dst_conflict():
    first = [str(index) for index in range(9)]
    share_seven = [str(index) for index in range(7)] + ["100", "101"]
    share_six = [str(index) for index in range(6)] + ["100", "101", "102"]
    conflict = _candidate([str(200 + index) for index in range(9)], 99.0, dst_conflict=True)
    book = select_book(
        [
            _candidate(first, 50.0),
            _candidate(share_seven, 40.0),
            conflict,
            _candidate(share_six, 30.0),
        ],
        count=3,
        bringback_min=0,
        secondary_min=0,
        caps={"WR": 5},
    )
    assert [item.blend for item in book] == [50.0, 30.0]
