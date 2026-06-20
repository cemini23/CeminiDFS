import csv
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("pydfs_lineup_optimizer")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ceminidfs.orchestrator.run import run_pipeline
from ceminidfs.pipeline import engine
from fixtures.synthetic_cache import write_synthetic_week_cache


def test_run_pipeline_diy_to_fanduel_lineups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    salary_path = Path(__file__).resolve().parent / "fixtures" / "synthetic_fd_slate.csv"
    week_dir = write_synthetic_week_cache(tmp_path, season=2024, week=4)
    monkeypatch.setattr(engine, "week_cache_dir", lambda season, week: week_dir)

    manifest_path = run_pipeline(
        2024,
        4,
        salary_path,
        stages="project,normalize,optimize",
        config={
            "projection_mode": "diy",
            "count": 150,
            "work_dir": tmp_path,
            "site": "fanduel",
        },
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["stage_status"] == {
        "project": "complete",
        "normalize": "complete",
        "optimize": "complete",
        "pipeline": "complete",
    }

    lineups_path = tmp_path / "lineups.csv"
    lineups = list(csv.DictReader(lineups_path.open(encoding="utf-8")))
    assert len(lineups) == 150

    canonical_path = Path(manifest["input_artifacts"]["artifacts"]["canonical_csv"])
    canonical_rows = list(csv.DictReader(canonical_path.open(encoding="utf-8")))
    mahomes = next(row for row in canonical_rows if row["name"] == "Patrick Mahomes")
    assert float(mahomes["fd_projection"]) > 0
