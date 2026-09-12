import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.data.research_locks import parse_research_locks


def test_parse_research_locks_reads_lock_and_exclude(tmp_path: Path):
    path = tmp_path / "research.csv"
    path.write_text(
        "Name,Lock,Fade\nPatrick Mahomes,yes,0\nAlvin Kamara,0,true\nRome Odunze,,1\n",
        encoding="utf-8",
    )

    locks, excludes = parse_research_locks(path)

    assert locks == ["Patrick Mahomes"]
    assert excludes == ["Alvin Kamara", "Rome Odunze"]


def test_parse_research_locks_unknown_headers_skips(tmp_path: Path, capsys):
    path = tmp_path / "research.csv"
    path.write_text("foo,bar\n1,2\n", encoding="utf-8")

    locks, excludes = parse_research_locks(path)

    assert locks == []
    assert excludes == []
    captured = capsys.readouterr()
    assert "unknown" in captured.err.lower()
    assert "foo" in captured.err
