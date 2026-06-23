import csv
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.config import apply_profile, load_config
from ceminidfs.cli import build_parser
from ceminidfs.export.canonical import write_canonical_csv
from ceminidfs.export.normalize import normalize_csv
from ceminidfs.orchestrator.run import _simulation_rows
from ceminidfs.pipeline.engine import merge_projections_into_canonical, normalize_join_key


def test_gpp_profile_deep_merges_over_conservative_base():
    base = load_config()
    gpp = load_config(profile="gpp")

    assert base["simulate"]["enabled"] is False
    assert base["ownership"]["enabled"] is False
    assert base["sim_rerank"]["enabled"] is False

    assert gpp["simulate"]["enabled"] is True
    assert gpp["simulate"]["method"] == "copula"
    assert gpp["simulate"]["n_iterations"] == 5000
    assert gpp["ownership"]["enabled"] is True
    assert gpp["sim_rerank"]["enabled"] is True
    assert gpp["sim_rerank"]["quantile"] == pytest.approx(0.85)
    assert gpp["sim_rerank"]["ownership_penalty"] == pytest.approx(0.15)
    assert gpp["volume"]["base_pass_rate"] == base["volume"]["base_pass_rate"]


def test_apply_profile_preserves_existing_nested_keys_without_mutating_input():
    cfg = {
        "simulate": {"enabled": False, "seed": 11},
        "sim_rerank": {"enabled": False, "candidates": 100},
    }

    merged = apply_profile(cfg, "gpp")

    assert cfg["simulate"]["enabled"] is False
    assert merged["simulate"]["enabled"] is True
    assert merged["simulate"]["seed"] == 11
    assert merged["sim_rerank"]["enabled"] is True
    assert merged["sim_rerank"]["candidates"] == 2000


def test_run_optimize_project_accept_gpp_profile_flag():
    parser = build_parser()

    run = parser.parse_args(
        [
            "run",
            "--season",
            "2025",
            "--week",
            "1",
            "--salary",
            "slate.csv",
            "--profile",
            "gpp",
        ]
    )
    optimize = parser.parse_args(
        [
            "optimize",
            "--csv",
            "players.csv",
            "--out",
            "lineups.csv",
            "--profile",
            "gpp",
        ]
    )
    project = parser.parse_args(
        [
            "project",
            "--season",
            "2025",
            "--week",
            "1",
            "--salary",
            "slate.csv",
            "--profile",
            "gpp",
        ]
    )

    assert run.profile == "gpp"
    assert optimize.profile == "gpp"
    assert project.profile == "gpp"


def test_simulation_inputs_keep_coherence_columns_after_projection_merge(tmp_path: Path):
    salary_rows = [
        {
            "slate_id": "2025_w1",
            "player_key": "patrick-mahomes",
            "fd_id": "1",
            "fd_position": "QB",
            "fd_salary": "8500",
            "dk_id": "",
            "dk_position": "",
            "dk_salary": "",
            "team": "KC",
            "opp": "BUF",
            "game": "BUF@KC",
            "name": "Patrick Mahomes",
            "player_name": "Patrick Mahomes",
        }
    ]
    stats_df = pd.DataFrame(
        [
            {
                "join_key": normalize_join_key("Patrick Mahomes", "KC", "QB"),
                "fd_projection": 24.5,
                "dk_projection": 26.0,
                "opp": "BUF",
                "game": "BUF@KC",
                "coherence_risk_flag": True,
                "pass_protection_stress": 1.2,
            }
        ]
    )

    merged = merge_projections_into_canonical(salary_rows, stats_df)
    canonical = tmp_path / "canonical.csv"
    normalized = tmp_path / "normalized.csv"

    write_canonical_csv(merged, canonical)
    normalize_csv(canonical, normalized, site="fanduel")
    normalized_rows = list(csv.DictReader(normalized.open(encoding="utf-8")))
    sim_rows = _simulation_rows(pd.DataFrame(normalized_rows))

    assert normalized_rows[0]["coherence_risk_flag"] == "True"
    assert normalized_rows[0]["pass_protection_stress"] == "1.2"
    assert sim_rows[0]["coherence_risk_flag"] == "True"
    assert sim_rows[0]["pass_protection_stress"] == "1.2"
