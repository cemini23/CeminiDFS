"""Tests for the code-health queue tool (scripts/code_health.py)."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("code_health", ROOT / "scripts" / "code_health.py")
ch = importlib.util.module_from_spec(_spec)
sys.modules["code_health"] = ch
_spec.loader.exec_module(ch)


def test_evaluation_path_is_never_scanned():
    scanned = [ch.rel(p) for p in ch.source_files()]
    assert not any(p.startswith("src/ceminidfs/eval_loop/") for p in scanned)
    assert "src/ceminidfs/pipeline/metrics.py" not in scanned


def test_action_boundary_is_never_scanned():
    scanned = [ch.rel(p) for p in ch.source_files()]
    for path in (
        "src/ceminidfs/export/handoff.py",
        "src/ceminidfs/export/jev_gate.py",
        "src/ceminidfs/export/late_swap.py",
        "src/ceminidfs/integrations/jev.py",
    ):
        assert path not in scanned


def test_scoring_path_is_guarded_not_excluded():
    assert ch.is_guarded("src/ceminidfs/pipeline/backtest.py")
    assert not ch.is_excluded("src/ceminidfs/pipeline/backtest.py")
    assert not ch.is_guarded("src/ceminidfs/data/salary.py")


def test_unused_import_respects_noqa_reexport(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "ROOT", tmp_path)
    src = tmp_path / "m.py"
    src.write_text("from os import path  # noqa: F401\n", encoding="utf-8")
    assert ch.check_unused_imports(ast.parse(src.read_text()), "m.py") == []


def test_unused_import_flags_real_dead_import(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "ROOT", tmp_path)
    src = tmp_path / "m.py"
    src.write_text("from os import path\n", encoding="utf-8")
    found = ch.check_unused_imports(ast.parse(src.read_text()), "m.py")
    assert [f["symbol"] for f in found] == ["path"]


def test_composite_weights_review_heavier_than_mechanics():
    assert ch.composite(100.0, 0.0) == 25.0
    assert ch.composite(0.0, 100.0) == 75.0
    assert ch.composite(60.0, None) == 60.0


def test_stable_id_depends_on_kind_file_symbol_only():
    a = ch.stable_id("dead_code", "src/x.py", "f")
    assert a == ch.stable_id("dead_code", "src/x.py", "f")
    assert a != ch.stable_id("complexity", "src/x.py", "f")
    assert a != ch.stable_id("dead_code", "src/y.py", "f")


def test_complexity_counts_branch_nodes():
    tree = ast.parse(
        "def f(x):\n"
        "    if x:\n"
        "        for i in range(3):\n"
        "            if i and x:\n"
        "                pass\n"
        "    return 1\n"
    )
    fn = tree.body[0]
    # 1 + if + for + if + boolop(1)
    assert ch.complexity(fn) == 5


def test_complexity_ignores_nested_function_bodies():
    tree = ast.parse(
        "def outer(x):\n"
        "    def inner(y):\n"
        "        if y:\n"
        "            return 1\n"
        "        return 2\n"
        "    if x:\n"
        "        return inner(x)\n"
        "    return 0\n"
    )
    # outer: base 1 + if(x); inner has its own finding.
    assert ch.complexity(tree.body[0]) == 2


def test_normalized_dump_ignores_identifier_names():
    a = ast.parse("def f(x):\n    return x + 1\n").body[0]
    b = ast.parse("def g(y):\n    return y + 2\n").body[0]
    assert ch.normalized_dump(a) == ch.normalized_dump(b)


def _write_queue(path: Path, file: str) -> str:
    fid = ch.stable_id("complexity", file, "f")
    state = {
        "version": 1,
        "generated": None,
        "files_scanned": 1,
        "findings": [
            {
                "id": fid,
                "kind": "complexity",
                "file": file,
                "line": 1,
                "symbol": "f",
                "detail": "test",
                "guarded": ch.is_guarded(file),
                "mechanical": 50.0,
                "review": None,
                "review_notes": None,
                "composite": 50.0,
                "status": "open",
                "note": None,
                "first_seen": "2026-01-01T00:00:00+00:00",
                "updated": "2026-01-01T00:00:00+00:00",
            }
        ],
    }
    path.write_text(json.dumps(state), encoding="utf-8")
    return fid


def test_resolve_refuses_guarded_item_without_baseline(tmp_path, monkeypatch):
    queue = tmp_path / "queue.json"
    fid = _write_queue(queue, "src/ceminidfs/pipeline/backtest.py")
    monkeypatch.setattr(ch, "QUEUE_PATH", queue)

    assert ch.main(["resolve", fid, "--note", "x"]) == 3
    state = json.loads(queue.read_text())
    assert state["findings"][0]["status"] == "open"


def test_resolve_allows_guarded_item_with_baseline_flag(tmp_path, monkeypatch):
    queue = tmp_path / "queue.json"
    fid = _write_queue(queue, "src/ceminidfs/pipeline/backtest.py")
    monkeypatch.setattr(ch, "QUEUE_PATH", queue)

    assert ch.main(["resolve", fid, "--baseline-rerun"]) == 0
    state = json.loads(queue.read_text())
    assert state["findings"][0]["status"] == "resolved"


def test_next_skips_guarded_items_by_default(tmp_path, monkeypatch, capsys):
    queue = tmp_path / "queue.json"
    _write_queue(queue, "src/ceminidfs/pipeline/backtest.py")
    monkeypatch.setattr(ch, "QUEUE_PATH", queue)

    assert ch.main(["next"]) == 0
    assert "queue empty" in capsys.readouterr().out

    assert ch.main(["next", "--include-guarded"]) == 0
    assert "backtest.py" in capsys.readouterr().out
