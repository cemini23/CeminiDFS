import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data.research_locks import parse_research_locks, parse_research_qb_cells


def test_parse_research_locks_reads_lock_exclude_and_fade(tmp_path: Path):
    path = tmp_path / "research.csv"
    path.write_text(
        "Name,Lock,Exclude,Fade\n"
        "Patrick Mahomes,yes,0,0\n"
        "Alvin Kamara,0,0,true\n"
        "Rome Odunze,,,1\n"
        "Bijan Robinson,,yes,true\n",
        encoding="utf-8",
    )

    locks, excludes, fades = parse_research_locks(path)

    assert locks == ["Patrick Mahomes"]
    # A row with both flags is a hard exclude only.
    assert excludes == ["Bijan Robinson"]
    assert fades == ["Alvin Kamara", "Rome Odunze"]


def test_parse_research_locks_unknown_headers_skips(tmp_path: Path, capsys):
    path = tmp_path / "research.csv"
    path.write_text("foo,bar\n1,2\n", encoding="utf-8")

    locks, excludes, fades = parse_research_locks(path)

    assert locks == []
    assert excludes == []
    assert fades == []
    captured = capsys.readouterr()
    assert "unknown" in captured.err.lower()
    assert "foo" in captured.err


WEEK2_SCRATCH_CSV = Path(__file__).resolve().parents[1] / "config" / "2026-w02-sun-scratch.csv"
WEEK2_SCRATCH_EXCLUDES = [
    "A.J. Brown",
    "Tyler Smith",
    "Isiah Pacheco",
    "Audric Estime",
    "Jayden Higgins",
    "Alfred Collins",
    "Cameron Williams",
    "Michael Penix Jr.",
    "Cameron Jordan",
    "Ja'Kobi Lane",
    "Da'Shawn Hand",
    "Sam Darnold",
    "Nico Collins",
    "Kyler Murray",
    "Minkah Fitzpatrick",
    "Omar Cooper Jr.",
    "Brock Bowers",
    "Zay Flowers",
    "Michael Pittman Jr.",
    "Joey Porter Jr.",
    "Jauan Jennings",
    "Marvin Mims Jr.",
    "Chig Okonkwo",
]
WEEK2_Q_NAMES = [
    "Tua Tagovailoa",
    "Ladd McConkey",
]


def test_week2_scratch_csv_is_exclude_only():
    locks, excludes, fades = parse_research_locks(WEEK2_SCRATCH_CSV)

    assert locks == []
    assert fades == []
    assert excludes == WEEK2_SCRATCH_EXCLUDES
    assert len(excludes) == 23
    for name in WEEK2_Q_NAMES:
        assert name not in excludes


def test_parse_research_qb_cells_reads_open_teams(tmp_path: Path):
    path = tmp_path / "research.csv"
    path.write_text(
        "Name,Team,qb_cell\n"
        "Case Keenum,CHI,open\n"
        "Tyson Bagent,CHI,unassigned\n"
        "Patrick Mahomes,KC,\n"
        "Josh Allen,BUF,starter\n",
        encoding="utf-8",
    )

    assert parse_research_qb_cells(path) == {"CHI"}


def test_parse_research_qb_cells_without_the_column_is_empty(tmp_path: Path):
    path = tmp_path / "research.csv"
    path.write_text("Name,Team\nCase Keenum,CHI\n", encoding="utf-8")

    assert parse_research_qb_cells(path) == set()

