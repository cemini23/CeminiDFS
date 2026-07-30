"""Tests for ESPN season-long redraft prep."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ceminidfs.redraft import config
from ceminidfs.redraft.draft_card import build_draft_card, write_draft_card
from ceminidfs.redraft.prerank import build_prerank, load_adp_csv, prerank_from_paths


def test_draft_card_includes_autopick_and_buy():
    card = build_draft_card()
    assert "ESPN 12-team snake full PPR" in card
    assert "Auto-Pick Strategy" in card
    assert "Position limits" in card
    assert "Gibbs" in card
    assert "| 15 | DST |" in card
    assert "| 16 | K |" in card


def test_write_draft_card(tmp_path: Path):
    out = write_draft_card(tmp_path / "card.md")
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "BUY TE:" in text


def test_prerank_sorts_by_adp(tmp_path: Path):
    adp = tmp_path / "adp.csv"
    adp.write_text(
        "name,pos,team,adp,notes\n"
        "Player B,WR,DAL,12.0,\n"
        "Player A,RB,DET,1.5,elite\n"
        "Player C,QB,PHI,80.0,\n",
        encoding="utf-8",
    )
    summary = prerank_from_paths(adp, tmp_path / "prerank.csv", top_n=10)
    assert summary["rows"] == 3
    assert summary["top_name"] == "Player A"
    board = pd.read_csv(tmp_path / "prerank.csv")
    assert list(board["name"]) == ["Player A", "Player B", "Player C"]
    assert list(board["rank"]) == [1, 2, 3]


def test_prerank_aliases_and_projection_tiebreak(tmp_path: Path):
    adp = tmp_path / "adp.csv"
    adp.write_text(
        "player,position,avg_pick,tm\n"
        "Same Adp One,WR,10.0,KC\n"
        "Same Adp Two,WR,10.0,BUF\n",
        encoding="utf-8",
    )
    proj = tmp_path / "proj.csv"
    proj.write_text(
        "name,projection_pts\n"
        "Same Adp Two,220\n"
        "Same Adp One,180\n",
        encoding="utf-8",
    )
    board = build_prerank(load_adp_csv(adp), projections_df=pd.read_csv(proj))
    assert board.iloc[0]["name"] == "Same Adp Two"
    assert board.iloc[0]["projection_pts"] == pytest.approx(220.0)


def test_prerank_scores_counting_stats():
    adp = pd.DataFrame(
        [
            {
                "name": "Catch King",
                "pos": "WR",
                "team": "SEA",
                "adp": 20.0,
                "notes": "",
                "rec": 100,
                "rec_yds": 1200,
                "rec_td": 8,
            }
        ]
    )
    board = build_prerank(adp)
    # 100 + 120 + 48 = 268 ESPN PPR
    assert board.iloc[0]["projection_pts"] == pytest.approx(268.0)


def test_load_adp_missing_columns(tmp_path: Path):
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required"):
        load_adp_csv(bad)


def test_config_position_limits_cover_starters():
    assert config.POSITION_LIMITS["QB"] == (1, 2)
    assert config.POSITION_LIMITS["DST"] == (1, 1)
    assert config.POSITION_LIMITS["K"] == (1, 1)
    assert len(config.AUTOPICK_ROUND_STRATEGY) == config.DRAFT_ROUNDS
