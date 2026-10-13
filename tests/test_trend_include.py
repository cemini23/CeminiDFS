"""Friday trend include: practice plus last week, then a lineup floor."""

from __future__ import annotations

import pandas as pd

from ceminidfs.export.optimize import enforce_named_min_counts
from ceminidfs.export.pool_guards import (
    friday_trend_names,
    is_questionable_row,
    practice_keeps_player,
    split_trend_names_by_salary,
)


def test_practice_keeps_limited_and_full_only():
    assert practice_keeps_player("Full Participation")
    assert practice_keeps_player("Limited Participation in Practice")
    assert not practice_keeps_player("Did Not Participate")
    assert not practice_keeps_player("Out")
    assert not practice_keeps_player("")


def test_friday_trend_needs_practice_and_last_week():
    injuries = pd.DataFrame(
        [
            {"week": 5, "practice_status": "Full Participation", "full_name": "Ja'Marr Chase"},
            {"week": 5, "practice_status": "Limited Participation", "full_name": "Jordan Addison"},
            {"week": 5, "practice_status": "Did Not Participate", "full_name": "Ashton Jeanty"},
            {"week": 5, "practice_status": "Full Participation", "full_name": "Justin Jefferson"},
            {"week": 4, "practice_status": "Full Participation", "full_name": "Old Guy"},
        ]
    )
    played = {"ja'marr chase", "jordan addison", "ashton jeanty"}

    names = friday_trend_names(injuries, played, week=5)

    assert names == {"ja'marr chase", "jordan addison"}


def test_questionable_tag_does_not_cover_a_healthy_player():
    assert is_questionable_row({"Injury Indicator": "Q", "First Name": "Ja'Marr"})
    assert not is_questionable_row({"Injury Indicator": "", "First Name": "Jahmyr"})
    assert not is_questionable_row({"Injury Indicator": "O", "First Name": "Breece"})
    assert not is_questionable_row({"First Name": "Jahmyr", "Last Name": "Gibbs"})


def test_salary_floor_forces_wright_and_leaves_holani_eligible():
    rows = [
        {"First Name": "Jaylen", "Last Name": "Wright", "Salary": 5600},
        {"First Name": "George", "Last Name": "Holani", "Salary": 4900},
        {"First Name": "Ja'Marr", "Last Name": "Chase", "Salary": "8900"},
    ]
    keys = {"jaylen wright", "george holani", "ja'marr chase", "missing player"}

    forced, eligible = split_trend_names_by_salary(rows, keys, min_salary=5500)

    assert forced == ["Jaylen Wright", "Ja'Marr Chase"]
    assert eligible == ["George Holani"]


def _chase_count(book: list[list[str]]) -> int:
    return sum(1 for lineup in book if "Ja'Marr Chase" in lineup)


def test_enforce_swaps_chase_in_and_keeps_the_book_length():
    selected = [
        ["Purdy", "Gibbs", "Jones"],
        ["Purdy", "Olave", "Tate"],
        ["Cousins", "Taylor", "Wilson"],
        ["Goff", "Brown", "St. Brown"],
    ]
    candidates = [
        ["Purdy", "Ja'Marr Chase", "Jones"],
        ["Burrow", "Ja'Marr Chase", "Higgins"],
    ]

    book = enforce_named_min_counts(
        selected,
        candidates,
        ["Ja'Marr Chase"],
        final_count=4,
        exposure=0.5,
        max_exposure=1.0,
    )

    assert len(book) == 4
    assert _chase_count(book) == 2


def test_enforce_uses_an_earlier_lineup_when_the_cap_blocks_the_last_one():
    selected = [
        ["Gibbs", "A"],
        ["Gibbs", "B"],
        ["Tate", "C"],
        ["Tate", "D"],
    ]
    candidates = [["Ja'Marr Chase", "Gibbs", "Z"]]

    book = enforce_named_min_counts(
        selected,
        candidates,
        ["Ja'Marr Chase"],
        final_count=4,
        exposure=0.25,
        max_exposure=0.5,
    )

    assert len(book) == 4
    assert _chase_count(book) == 1
    assert sum(1 for lineup in book if "Gibbs" in lineup) == 2


def test_enforce_logs_a_shortfall_and_keeps_the_book(capsys):
    selected = [["Purdy", "Gibbs"], ["Cousins", "Taylor"]]

    book = enforce_named_min_counts(
        selected,
        [["Olave", "Tate"]],
        ["Ja'Marr Chase"],
        final_count=2,
        exposure=0.5,
        max_exposure=1.0,
    )

    assert book == selected
    assert "Ja'Marr Chase is in 0 of 2 lineups" in capsys.readouterr().err
