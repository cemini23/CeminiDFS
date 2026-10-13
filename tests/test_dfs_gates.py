"""Build-time gate tests. The Week 5 run is the fixture.

Week 5 shipped a 38-lineup 5-player core, nine players at 34.7%, a
Questionable player at 25%, and lineups with two sub-8 projections. Each gate
must refuse that shape.
"""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.config import load_config
from ceminidfs.export.build_gates import (
    BuildGateError,
    assert_core_cap,
    assert_exposure_cap,
    core_violations,
    exposure_violations,
    load_gate_context,
    low_ceiling_names,
    low_ceiling_violations,
    max_core_count,
    position_lead_exempt,
)
from ceminidfs.export.review_reports import (
    read_lineup_totals,
    write_cash_bucket_report,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "week5"
WEEK5_LINEUPS = FIXTURES / "lineups.csv"
WEEK5_PLAYERS = FIXTURES / "normalized_players.csv"
WEEK5_TOTALS = FIXTURES / "lineup_totals.csv"


def _read_rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        next(reader)
        return [row for row in reader if any(cell.strip() for cell in row)]


def _player_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


# --- Gate 1: 5-player core cap -------------------------------------------------


def test_week5_shipped_book_breaks_the_five_core_cap():
    book = _read_rows(WEEK5_LINEUPS)

    assert len(book) == 150
    assert max_core_count(book, 5) == 38
    with pytest.raises(BuildGateError, match="5-player core appears 38 times"):
        assert_core_cap(book, 12)


def test_week5_core_cap_names_a_violating_combination():
    book = _read_rows(WEEK5_LINEUPS)

    over = core_violations(book, 12, 5)
    count, combo = over[0]

    assert count == 38
    assert combo == (
        "ja'marr chase",
        "jaylen wright",
        "jordan addison",
        "keenan allen",
        "rhamondre stevenson",
    )


def test_core_cap_accepts_a_book_at_the_limit():
    book = _read_rows(WEEK5_LINEUPS)

    # The worst core holds 38 lineups. A cap of 38 is legal.
    assert_core_cap(book, 38)


# --- Gate 2: exposure cap and position-lead hatch ------------------------------


def test_week5_shipped_book_breaks_the_twenty_percent_cap():
    book = _read_rows(WEEK5_LINEUPS)

    over = exposure_violations(book, 0.20)

    assert len(over) == 22
    assert over[0][:2] == ("aaron jones sr.", 52)
    assert over[0][2] == 30  # floor(0.20 * 150)


def test_position_lead_hatch_lifts_the_qb_and_rb_leaders():
    players = _player_rows(WEEK5_PLAYERS)

    exempt = position_lead_exempt(players, margin=4.0, cap=0.30)

    assert exempt == {"brock purdy": 0.30, "jahmyr gibbs": 0.30}


def test_hatch_raises_the_cap_for_the_exempt_player_only():
    book = _read_rows(WEEK5_LINEUPS)
    over = exposure_violations(book, 0.20, overrides={"brock purdy": 0.30})

    caps = {name: cap for name, _count, cap in over}

    assert caps["brock purdy"] == 45  # floor(0.30 * 150)
    assert caps["aaron jones sr."] == 30


def test_exposure_assert_reports_the_first_breach():
    book = _read_rows(WEEK5_LINEUPS)

    with pytest.raises(BuildGateError, match="exposure cap is 30"):
        assert_exposure_cap(book, 0.20)


def test_gpp_profile_sets_the_twenty_percent_default_and_enables_the_gates():
    gpp = load_config(profile="gpp")

    assert gpp["max_exposure"] == pytest.approx(0.20)
    assert gpp["gates"]["core"] == {"enabled": True, "size": 5, "max_count": 12}
    assert gpp["gates"]["low_ceiling"]["projection_floor"] == pytest.approx(8.0)
    assert gpp["gates"]["low_ceiling"]["max_per_lineup"] == 1
    assert gpp["gates"]["exposure_hatch"]["cap"] == pytest.approx(0.30)
    assert gpp["prelock"]["q_exposure_cap"] == pytest.approx(0.08)


def test_base_profile_leaves_the_gates_off():
    base = load_config()

    assert base["gates"]["core"]["enabled"] is False
    assert base["gates"]["low_ceiling"]["enabled"] is False
    assert base["gates"]["exposure_hatch"]["enabled"] is False


# --- Gate 4: low-ceiling floor -------------------------------------------------


def test_week5_shipped_book_carries_two_low_ceiling_players():
    book = _read_rows(WEEK5_LINEUPS)
    projections, positions = load_gate_context(_player_rows(WEEK5_PLAYERS))
    under = low_ceiling_names(projections, positions, 8.0)

    assert "jaylen wright" in under
    assert "washington commanders" not in under  # a defense is not a skill player

    over = low_ceiling_violations(book, under, 1)

    assert len(over) == 38


def test_low_ceiling_allows_one_weak_player():
    book = [["Weak One", "Strong A", "Strong B"], ["Weak One", "Weak Two", "Strong C"]]
    under = {"weak one", "weak two"}

    over = low_ceiling_violations(book, under, 1)

    assert over == [(2, ("weak one", "weak two"))]


# --- Solver-level enforcement --------------------------------------------------


def test_solver_honours_the_core_cap_and_the_low_ceiling_gate():
    pytest.importorskip("pydfs_lineup_optimizer")

    from ceminidfs.export.optimize import generate_lineups

    gates = {
        "core": {"enabled": True, "size": 5, "max_count": 4},
        "low_ceiling": {"enabled": True, "projection_floor": 8.0, "max_per_lineup": 1},
    }
    book = generate_lineups(
        WEEK5_PLAYERS,
        site="fanduel",
        count=30,
        max_exposure=0.50,
        gates=gates,
    )
    names = [[player.full_name for player in lineup.players] for lineup in book]
    projections, positions = load_gate_context(_player_rows(WEEK5_PLAYERS))
    under = low_ceiling_names(projections, positions, 8.0)

    assert max_core_count(names, 5) <= 4
    assert low_ceiling_violations(names, under, 1) == []


def test_merge_refuses_an_extra_row_that_breaks_the_core_cap(tmp_path: Path):
    from ceminidfs.export.optimize import merge_lineup_csvs

    header = "QB,RB,RB,WR,WR,WR,TE,FLEX,DEF\n"
    core = "A,B,C,D,E,F,G,H,I\n"
    base = tmp_path / "base.csv"
    base.write_text(header + core * 3, encoding="utf-8")
    extra = tmp_path / "extra.csv"
    extra.write_text(header + core, encoding="utf-8")

    written = merge_lineup_csvs(
        base,
        extra,
        tmp_path / "out.csv",
        max_exposure=1.0,
        final_count=10,
        core_cap=4,
    )

    assert written == 4
    with pytest.raises(BuildGateError, match="core would appear 4 times"):
        merge_lineup_csvs(
            base,
            extra,
            tmp_path / "out2.csv",
            max_exposure=1.0,
            final_count=10,
            core_cap=3,
        )
    assert not (tmp_path / "out2.csv").exists()


# --- Gate 3: pre-lock Q/D exposure --------------------------------------------


def test_prelock_gate_refuses_a_questionable_player_at_twenty_five_percent():
    from ceminidfs.export.late_swap import PrelockQError, assert_prelock_q, prelock_q_violations

    over = prelock_q_violations(WEEK5_LINEUPS, WEEK5_PLAYERS, cap=0.08)
    by_name = {entry[0]: entry for entry in over}

    assert by_name["Jordan Addison"] == ("Jordan Addison", "Q", 38, 12)
    assert over[0][0] == "Carnell Tate"  # worst first
    with pytest.raises(PrelockQError, match="Carnell Tate"):
        assert_prelock_q(WEEK5_LINEUPS, WEEK5_PLAYERS, cap=0.08)


def test_prelock_gate_passes_a_high_cap():
    from ceminidfs.export.late_swap import assert_prelock_q

    assert_prelock_q(WEEK5_LINEUPS, WEEK5_PLAYERS, cap=0.40)


# --- Gate 5: cash-line buckets -------------------------------------------------


def test_week5_bucket_distribution_matches_the_audit():
    rows = read_lineup_totals(WEEK5_TOTALS)

    assert len(rows) == 150
    assert rows[0]["rank"] == 1
    assert rows[0]["score"] == pytest.approx(192.54)


def test_bucket_report_lifts_the_41_to_100_group(tmp_path: Path):
    rows = read_lineup_totals(WEEK5_TOTALS)
    out = tmp_path / "cash_bucket_report.csv"

    write_cash_bucket_report(out, rows)

    with out.open(newline="", encoding="utf-8") as handle:
        buckets = {row["bucket"]: row for row in csv.DictReader(handle)}

    assert buckets["1-20"]["score_min"] == "139.24"
    assert buckets["1-20"]["score_max"] == "192.54"
    assert buckets["1-20"]["cash_count"] == "20"
    assert buckets["21-40"]["score_min"] == "129.14"
    assert buckets["21-40"]["cash_count"] == "10"
    assert buckets["41-100"]["count"] == "60"
    assert buckets["41-100"]["score_median"] == "122.03"
    assert buckets["41-100"]["cash_count"] == "0"
    assert buckets["101-150"]["score_max"] == "105.86"
