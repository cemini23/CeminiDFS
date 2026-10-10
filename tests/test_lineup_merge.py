"""Fail-closed merge of lineup CSVs under the book exposure cap."""

import argparse
import csv
from pathlib import Path

import pytest

from ceminidfs.cli import build_parser, main
from ceminidfs.export.optimize import LINEUP_HEADERS, ExposureCapError, merge_lineup_csvs

HEADER = LINEUP_HEADERS["fanduel"]


def _row(qb: str, rb1: str, rb2: str, tag: str) -> list[str]:
    return [
        qb,
        rb1,
        rb2,
        f"W1-{tag}",
        f"W2-{tag}",
        f"W3-{tag}",
        f"TE-{tag}",
        f"FL-{tag}",
        f"DEF-{tag}",
    ]


def _write(path: Path, rows: list[list[str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def _book(path: Path, name: str, copies: int, total: int = 14) -> Path:
    rows = []
    for index in range(total):
        rb1 = name if index < copies else f"RB-{index}"
        rows.append(_row(f"QB-{index}", rb1, f"RB2-{index}", str(index)))
    return _write(path, rows)


def _counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with path.open(encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader)
        for row in reader:
            for cell in row:
                key = " ".join(cell.lower().split())
                if not key:
                    continue
                counts[key] = counts.get(key, 0) + 1
    return counts


def test_merge_refuses_week2_join_and_does_not_write(tmp_path: Path):
    """A name in 3 of 14 rows, plus one more row, breaks floor(0.20 * 15)."""

    base = _book(tmp_path / "base.csv", "Bijan Robinson", copies=3)
    extra = _write(
        tmp_path / "extra.csv",
        [_row("Jayden Daniels", "Bijan Robinson", "Derrick Henry", "lock")],
    )
    out = tmp_path / "nested" / "merged.csv"

    with pytest.raises(ExposureCapError, match=r"Bijan Robinson would appear 4 times; cap is 3"):
        merge_lineup_csvs(
            base,
            extra,
            out,
            max_exposure=0.20,
            final_count=15,
        )

    assert issubclass(ExposureCapError, ValueError)
    assert not out.exists()
    assert not out.parent.exists()


def test_merge_writes_extra_row_of_new_names(tmp_path: Path):
    base = _write(
        tmp_path / "base.csv",
        [_row("At Cap", f"RB-{index}", f"RB2-{index}", str(index)) for index in range(3)],
    )
    extra = _write(tmp_path / "extra.csv", [_row("New QB", "New RB1", "New RB2", "new")])
    out = tmp_path / "merged.csv"

    count = merge_lineup_csvs(base, extra, out, max_exposure=0.20, final_count=15)

    assert count == 4
    assert out.is_file()
    counts = _counts(out)
    assert counts["at cap"] == 3
    assert max(counts.values()) <= 3


def test_merge_allows_third_copy_when_book_cap_is_three(tmp_path: Path):
    """Cap uses count 15, not the 14-row file length (that cap would be 2)."""

    base = _book(tmp_path / "base.csv", "Bijan Robinson", copies=2)
    extra = _write(
        tmp_path / "extra.csv",
        [_row("Jayden Daniels", "Bijan Robinson", "Derrick Henry", "lock")],
    )
    out = tmp_path / "merged.csv"

    count = merge_lineup_csvs(base, extra, out, max_exposure=0.20, final_count=15)

    assert count == 15
    assert _counts(out)["bijan robinson"] == 3


def test_merge_name_key_ignores_case_and_extra_spaces(tmp_path: Path):
    base = _write(
        tmp_path / "base.csv",
        [
            _row("QB-0", "Bijan  Robinson", "RB2-0", "0"),
            _row("QB-1", "Bijan  Robinson", "RB2-1", "1"),
            _row("QB-2", "bijan robinson", "RB2-2", "2"),
        ],
    )
    extra = _write(
        tmp_path / "extra.csv",
        [_row("QB-x", "Bijan Robinson", "RB2-x", "x")],
    )
    out = tmp_path / "merged.csv"

    with pytest.raises(ExposureCapError, match=r"would appear 4 times; cap is 3"):
        merge_lineup_csvs(base, extra, out, max_exposure=0.20, final_count=15)

    assert not out.exists()


def test_cli_merge_lineups_exits_1_and_prints_the_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    base = _book(tmp_path / "base.csv", "Bijan Robinson", copies=3)
    extra = _write(
        tmp_path / "extra.csv",
        [_row("Jayden Daniels", "Bijan Robinson", "Derrick Henry", "lock")],
    )
    out = tmp_path / "merged.csv"
    players = _players(tmp_path / "players.csv", ["Bijan Robinson"])

    code = main(
        [
            "merge-lineups",
            "--base",
            str(base),
            "--extra",
            str(extra),
            "--out",
            str(out),
            "--players",
            str(players),
            "--max-exposure",
            "0.20",
            "--count",
            "15",
            "--site",
            "fanduel",
        ]
    )

    assert code == 1
    assert not out.exists()
    captured = capsys.readouterr()
    assert "Bijan Robinson" in captured.err
    assert "4" in captured.err
    assert "3" in captured.err


def _players(path: Path, names: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Id", "First Name", "Last Name", "Position"])
        writer.writeheader()
        for index, name in enumerate(names, start=1):
            first, _, last = name.partition(" ")
            writer.writerow(
                {"Id": str(1000 + index), "First Name": first, "Last Name": last, "Position": "WR"}
            )
    return path


def _nine(tag: str) -> list[str]:
    return [
        f"QB {tag}",
        f"RB {tag}a",
        f"RB {tag}b",
        f"WR {tag}a",
        f"WR {tag}b",
        f"WR {tag}c",
        f"TE {tag}",
        f"FL {tag}",
        f"DF {tag}",
    ]


def test_merge_lineups_writes_upload_cells(tmp_path: Path):
    base_names = _nine("Base")
    extra_names = _nine("Extra")
    base = _write(tmp_path / "base.csv", [base_names])
    extra = _write(tmp_path / "extra.csv", [extra_names])
    out = tmp_path / "book" / "merged.csv"
    players = _players(tmp_path / "book" / "players.csv", base_names + extra_names)

    code = main(
        [
            "merge-lineups",
            "--base",
            str(base),
            "--extra",
            str(extra),
            "--out",
            str(out),
            "--players",
            str(players),
            "--max-exposure",
            "1",
            "--count",
            "2",
        ]
    )

    assert code == 0
    upload = tmp_path / "book" / "merged_fanduel_upload.csv"
    ids = tmp_path / "book" / "merged_fanduel_ids.csv"
    assert upload.is_file()
    assert ids.is_file()
    with upload.open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == HEADER
    id_by_name = {}
    with players.open(encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            full = f"{record['First Name']} {record['Last Name']}"
            id_by_name[full] = record["Id"]
    for row in rows[1:]:
        for cell in row:
            name, _, rest = cell.partition(" (")
            assert rest.endswith(")")
            assert rest[:-1] == id_by_name[name]
            assert cell == f"{name} ({id_by_name[name]})"


def test_merge_lineups_requires_players_file_next_to_out(tmp_path: Path):
    base = _write(tmp_path / "base.csv", [_nine("Base")])
    extra = _write(tmp_path / "extra.csv", [_nine("Extra")])
    out = tmp_path / "book" / "merged.csv"

    code = main(
        [
            "merge-lineups",
            "--base",
            str(base),
            "--extra",
            str(extra),
            "--out",
            str(out),
            "--max-exposure",
            "1",
            "--count",
            "2",
        ]
    )

    assert code == 1
    assert not out.exists()
    assert not out.with_name("merged_fanduel_upload.csv").exists()


def test_merge_lineups_help_lists_book_size_flags():
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    help_text = subparsers.choices["merge-lineups"].format_help()
    assert "--base" in help_text
    assert "--extra" in help_text
    assert "--out" in help_text
    assert "--max-exposure" in help_text
    assert "--count" in help_text
    assert "--site" in help_text
    assert "--players" in help_text
