import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.export.canonical import CANONICAL_FIELDS
from ceminidfs.export.normalize import normalize_csv
from ceminidfs.orchestrator.run import _parse_stages
from ceminidfs.pipeline.project import project_week


SAMPLE_SALARY_CSV = """\
Id,Nickname,Position,Team,Opponent,Salary,FPPG,Injury Indicator
1,Patrick Mahomes,QB,KC,BUF,8500,22.5,
2,Travis Kelce,TE,KC,BUF,7200,14.1,Q
"""


def test_project_emits_canonical_schema(tmp_path: Path):
    salary = tmp_path / "salary.csv"
    salary.write_text(SAMPLE_SALARY_CSV, encoding="utf-8")

    canonical = project_week(
        2024,
        1,
        salary,
        {"work_dir": tmp_path, "allow_fppg_fallback": True, "projection_mode": "auto"},
    )
    rows = list(csv.DictReader(canonical.open(encoding="utf-8")))

    assert len(rows) == 2
    assert list(rows[0].keys())[: len(CANONICAL_FIELDS)] == CANONICAL_FIELDS
    assert rows[0]["fd_id"] == "1"
    assert rows[0]["name"] == "Patrick Mahomes"
    assert rows[0]["fd_projection"] == "22.5"
    assert rows[0]["slate_id"] == "2024_w1"
    assert rows[0]["game"] == "KC@BUF"
    assert rows[1]["injury_status"] == "Q"


def test_project_to_normalize_preserves_player_ids(tmp_path: Path):
    salary = tmp_path / "salary.csv"
    salary.write_text(SAMPLE_SALARY_CSV, encoding="utf-8")

    canonical = project_week(
        2024,
        1,
        salary,
        {"work_dir": tmp_path, "allow_fppg_fallback": True, "projection_mode": "auto"},
    )
    normalized = tmp_path / "normalized.csv"
    count = normalize_csv(canonical, normalized, site="fanduel")

    assert count == 2
    rows = list(csv.DictReader(normalized.open(encoding="utf-8")))
    assert rows[0]["Id"] == "1"
    assert rows[1]["Id"] == "2"
    assert rows[0]["First Name"] == "Patrick"
    assert rows[0]["Last Name"] == "Mahomes"
    assert rows[0]["FPPG"] == "22.5"
    assert rows[0]["Game"] == "KC@BUF"


def test_parse_stages_auto_inserts_normalize_before_optimize():
    assert _parse_stages("project,optimize") == ["project", "normalize", "optimize"]
    assert _parse_stages("optimize") == ["normalize", "optimize"]


def test_parse_stages_rejects_unknown_stage():
    with pytest.raises(ValueError, match="Unknown stage"):
        _parse_stages("fetch,invalid")
