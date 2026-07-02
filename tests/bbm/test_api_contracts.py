"""BBM API contract tests for WS-B fixes."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from ceminidfs.bbm import ledger, session
from ceminidfs.bbm.api_server import create_server
from ceminidfs.bbm.models import Archetype, PivotResult


class _ServerHarness:
    def __init__(self, *, port: int, draft_id: str, token: str | None = None):
        self.port = port
        self.server = create_server(
            host="127.0.0.1",
            port=port,
            draft_id=draft_id,
            slot=4,
            archetype="D",
            token=token,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "_ServerHarness":
        self.thread.start()
        time.sleep(0.2)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.server.shutdown()
        self.thread.join(timeout=1)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def _api_get(url: str) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _api_post(url: str, payload: dict[str, Any], token: str | None = None) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-BBM-Token"] = token
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


@pytest.fixture
def api_test_setup(bbm_db: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(ledger, "get_db_path", lambda: bbm_db)
    monkeypatch.setattr(session, "get_db_path", lambda: bbm_db)
    monkeypatch.setattr("ceminidfs.bbm.api_server._get_ledger", lambda: ledger)
    monkeypatch.setattr("ceminidfs.bbm.api_server._get_session", lambda: session)
    draft_id = "test-api-contracts"
    ledger.create_draft(draft_id, slot=4, archetype="D", db_path=bbm_db)
    return draft_id


def test_pick_unknown_404_no_stub(api_test_setup: str, bbm_db: Path) -> None:
    with _ServerHarness(port=18770, draft_id=api_test_setup) as server:
        status, body = _api_post(f"{server.base}/api/pick", {"draft_id": api_test_setup, "name": "Xyzzy Qwerty"})
    assert status == 404
    assert "Player not found" in body["error"]

    conn = sqlite3.connect(bbm_db)
    stub_count = conn.execute(
        "SELECT COUNT(*) FROM players_dim WHERE player_id LIKE 'stub:%'"
    ).fetchone()[0]
    conn.close()
    assert stub_count == 0


def test_taken_unknown_stubs_with_warning(api_test_setup: str, bbm_db: Path) -> None:
    with _ServerHarness(port=18771, draft_id=api_test_setup) as server:
        status, body = _api_post(f"{server.base}/api/taken", {"draft_id": api_test_setup, "name": "Mystery Dude"})
    assert status == 200
    assert body["is_stub"] is True
    assert "verify spelling" in body["warning"]

    conn = sqlite3.connect(bbm_db)
    room_taken_count = conn.execute(
        "SELECT COUNT(*) FROM room_taken WHERE draft_id = ?",
        (api_test_setup,),
    ).fetchone()[0]
    conn.close()
    assert room_taken_count == 1


def test_sync_labels_via_board_parse(api_test_setup: str) -> None:
    with _ServerHarness(port=18772, draft_id=api_test_setup) as server:
        status, body = _api_post(
            f"{server.base}/api/sync",
            {
                "draft_id": api_test_setup,
                "labels": ["Select Ja'Marr Chase, WR, CIN", "draft pick", "Pick Puka Nacua"],
            },
        )
    assert status == 200
    assert body["synced_count"] == 2
    assert body["unmatched_count"] == 0


def test_sync_unknown_reports_unmatched_no_stub(api_test_setup: str, bbm_db: Path) -> None:
    with _ServerHarness(port=18773, draft_id=api_test_setup) as server:
        status, body = _api_post(
            f"{server.base}/api/sync",
            {"draft_id": api_test_setup, "names": ["Ghost Player"]},
        )
    assert status == 200
    assert body["synced_count"] == 0
    assert body["unmatched_count"] == 1

    conn = sqlite3.connect(bbm_db)
    stub_count = conn.execute(
        "SELECT COUNT(*) FROM players_dim WHERE player_id LIKE 'stub:%'"
    ).fetchone()[0]
    conn.close()
    assert stub_count == 0


def test_undo_endpoint(api_test_setup: str) -> None:
    with _ServerHarness(port=18774, draft_id=api_test_setup) as server:
        pick_status, _ = _api_post(
            f"{server.base}/api/pick",
            {"draft_id": api_test_setup, "name": "Ja'Marr Chase"},
        )
        assert pick_status == 200

        undo_status, undo_body = _api_post(
            f"{server.base}/api/undo",
            {"draft_id": api_test_setup},
        )
        state_status, state_body = _api_get(f"{server.base}/api/state?draft_id={api_test_setup}")
        second_undo_status, second_undo_body = _api_post(
            f"{server.base}/api/undo",
            {"draft_id": api_test_setup},
        )

    assert undo_status == 200
    assert undo_body["undone"] == "pick"
    assert state_status == 200
    assert state_body["current_round"] == 1
    assert second_undo_status == 404
    assert second_undo_body["error"] == "Nothing to undo"


def test_recommendations_get_is_readonly(api_test_setup: str, bbm_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    top_players = ledger.list_available_players(limit=6, db_path=bbm_db)
    assert len(top_players) >= 5
    for i, player in enumerate(top_players[:5], start=1):
        ledger.record_pick(api_test_setup, i, i, player["player_id"], is_mine=True, db_path=bbm_db)

    def forced_pivot(*args: Any, **kwargs: Any) -> PivotResult:
        del args, kwargs
        return PivotResult(new_archetype=Archetype.B, warning="forced advisory pivot", trigger_reason="test")

    monkeypatch.setattr("ceminidfs.bbm.session.pivot_state_machine", forced_pivot)

    with _ServerHarness(port=18775, draft_id=api_test_setup) as server:
        status_1, body_1 = _api_get(f"{server.base}/api/recommendations?draft_id={api_test_setup}")
        status_2, body_2 = _api_get(f"{server.base}/api/recommendations?draft_id={api_test_setup}")

    assert status_1 == 200
    assert status_2 == 200
    assert body_1["pivot_warning"] is not None
    assert body_2["pivot_warning"] is not None

    conn = sqlite3.connect(bbm_db)
    pivot_applied = conn.execute(
        "SELECT pivot_applied FROM drafts WHERE draft_id = ?",
        (api_test_setup,),
    ).fetchone()[0]
    conn.close()
    assert pivot_applied == 0


def test_pivot_endpoint_applies(api_test_setup: str, bbm_db: Path) -> None:
    with _ServerHarness(port=18776, draft_id=api_test_setup) as server:
        status, body = _api_post(
            f"{server.base}/api/pivot",
            {"draft_id": api_test_setup, "archetype": "B"},
        )
        rec_status, rec_body = _api_get(f"{server.base}/api/recommendations?draft_id={api_test_setup}")

    assert status == 200
    assert body["pivot_applied"] is True

    conn = sqlite3.connect(bbm_db)
    draft_row = conn.execute(
        "SELECT archetype, pivot_applied FROM drafts WHERE draft_id = ?",
        (api_test_setup,),
    ).fetchone()
    conn.close()
    assert draft_row == ("B", 1)
    assert rec_status == 200
    assert rec_body["pivot_warning"] is None


def test_pick_ambiguous_includes_player_ids(api_test_setup: str, bbm_db: Path) -> None:
    with _ServerHarness(port=18780, draft_id=api_test_setup) as server:
        status, body = _api_post(
            f"{server.base}/api/pick",
            {"draft_id": api_test_setup, "name": "Chase"},
        )
    assert status == 200
    assert body["ambiguous"] is True
    assert len(body["matches"]) >= 2
    for match in body["matches"]:
        assert match["player_id"]
        assert match["index"] >= 1
        assert match["name"]
        assert match["position"]
        assert match["team"]

    conn = sqlite3.connect(bbm_db)
    picks_count = conn.execute(
        "SELECT COUNT(*) FROM picks WHERE draft_id = ?",
        (api_test_setup,),
    ).fetchone()[0]
    conn.close()
    assert picks_count == 0


def test_pick_by_player_id(api_test_setup: str, bbm_db: Path) -> None:
    chase_brown_id = ledger.get_players_by_name("Chase Brown", db_path=bbm_db)[0]["player_id"]
    with _ServerHarness(port=18781, draft_id=api_test_setup) as server:
        status, body = _api_post(
            f"{server.base}/api/pick",
            {"draft_id": api_test_setup, "player_id": chase_brown_id},
        )
        missing_status, missing_body = _api_post(
            f"{server.base}/api/pick",
            {"draft_id": api_test_setup, "player_id": "bbm:nope"},
        )
    assert status == 200
    assert body["player"]["name"] == "Chase Brown"
    assert missing_status == 404
    assert missing_body["error"] == "Player not found: bbm:nope"

    conn = sqlite3.connect(bbm_db)
    pick_exists = conn.execute(
        "SELECT COUNT(*) FROM picks WHERE draft_id = ? AND player_id = ?",
        (api_test_setup, chase_brown_id),
    ).fetchone()[0]
    conn.close()
    assert pick_exists == 1


def test_taken_by_player_id_no_stub(api_test_setup: str, bbm_db: Path) -> None:
    puka_id = ledger.get_players_by_name("Puka Nacua", db_path=bbm_db)[0]["player_id"]
    with _ServerHarness(port=18782, draft_id=api_test_setup) as server:
        status, body = _api_post(
            f"{server.base}/api/taken",
            {"draft_id": api_test_setup, "player_id": puka_id},
        )
        missing_status, missing_body = _api_post(
            f"{server.base}/api/taken",
            {"draft_id": api_test_setup, "player_id": "bbm:ghost"},
        )
    assert status == 200
    assert body["is_stub"] is False
    assert missing_status == 404
    assert missing_body["error"] == "Player not found: bbm:ghost"

    conn = sqlite3.connect(bbm_db)
    room_taken_count = conn.execute(
        "SELECT COUNT(*) FROM room_taken WHERE draft_id = ? AND player_id = ?",
        (api_test_setup, puka_id),
    ).fetchone()[0]
    stub_count = conn.execute(
        "SELECT COUNT(*) FROM players_dim WHERE player_id LIKE 'stub:%'"
    ).fetchone()[0]
    conn.close()
    assert room_taken_count == 1
    assert stub_count == 0


def test_sync_ambiguous_reports_matches(api_test_setup: str, bbm_db: Path) -> None:
    with _ServerHarness(port=18783, draft_id=api_test_setup) as server:
        status, body = _api_post(
            f"{server.base}/api/sync",
            {"draft_id": api_test_setup, "names": ["Chase"]},
        )
    assert status == 200
    assert body["ambiguous_count"] == 1
    assert body["ambiguous"][0]["query"] == "Chase"
    assert len(body["ambiguous"][0]["matches"]) >= 2
    for match in body["ambiguous"][0]["matches"]:
        assert match["player_id"]
        assert match["index"] >= 1

    conn = sqlite3.connect(bbm_db)
    room_taken_count = conn.execute(
        "SELECT COUNT(*) FROM room_taken WHERE draft_id = ?",
        (api_test_setup,),
    ).fetchone()[0]
    conn.close()
    assert room_taken_count == 0


def test_sync_skips_already_picked(api_test_setup: str, bbm_db: Path) -> None:
    with _ServerHarness(port=18784, draft_id=api_test_setup) as server:
        pick_status, _ = _api_post(
            f"{server.base}/api/pick",
            {"draft_id": api_test_setup, "name": "Ja'Marr Chase"},
        )
        assert pick_status == 200

        sync_status, sync_body = _api_post(
            f"{server.base}/api/sync",
            {"draft_id": api_test_setup, "names": ["Ja'Marr Chase", "Puka Nacua"]},
        )
        first_undo_status, first_undo = _api_post(
            f"{server.base}/api/undo",
            {"draft_id": api_test_setup},
        )
        second_undo_status, second_undo = _api_post(
            f"{server.base}/api/undo",
            {"draft_id": api_test_setup},
        )
    assert sync_status == 200
    assert [item["name"] for item in sync_body["synced"]] == ["Puka Nacua"]
    assert sync_body["skipped_existing"] == ["Ja'Marr Chase"]
    assert sync_body["skipped_count"] == 1
    assert first_undo_status == 200
    assert first_undo["undone"] == "taken"
    assert second_undo_status == 200
    assert second_undo["undone"] == "pick"

    jamarr_id = ledger.get_players_by_name("Ja'Marr Chase", db_path=bbm_db)[0]["player_id"]
    conn = sqlite3.connect(bbm_db)
    chase_in_room_taken = conn.execute(
        "SELECT COUNT(*) FROM room_taken WHERE draft_id = ? AND player_id = ?",
        (api_test_setup, jamarr_id),
    ).fetchone()[0]
    conn.close()
    assert chase_in_room_taken == 0


def test_sync_rescan_reports_skipped(api_test_setup: str, bbm_db: Path) -> None:
    with _ServerHarness(port=18785, draft_id=api_test_setup) as server:
        first_status, _ = _api_post(
            f"{server.base}/api/sync",
            {"draft_id": api_test_setup, "names": ["Puka Nacua"]},
        )
        second_status, second_body = _api_post(
            f"{server.base}/api/sync",
            {"draft_id": api_test_setup, "names": ["Puka Nacua"]},
        )
    assert first_status == 200
    assert second_status == 200
    assert second_body["synced_count"] == 0
    assert second_body["skipped_count"] == 1

    conn = sqlite3.connect(bbm_db)
    action_taken_count = conn.execute(
        "SELECT COUNT(*) FROM action_log WHERE draft_id = ? AND action_type = 'taken'",
        (api_test_setup,),
    ).fetchone()[0]
    conn.close()
    assert action_taken_count == 1


def test_pivot_warning_survives_empty_recs(
    api_test_setup: str, bbm_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    top_players = ledger.list_available_players(limit=6, db_path=bbm_db)
    assert len(top_players) >= 5
    for i, player in enumerate(top_players[:5], start=1):
        ledger.record_pick(api_test_setup, i, i, player["player_id"], is_mine=True, db_path=bbm_db)

    def forced_pivot(*args: Any, **kwargs: Any) -> PivotResult:
        del args, kwargs
        return PivotResult(new_archetype=Archetype.B, warning="forced advisory pivot", trigger_reason="test")

    monkeypatch.setattr("ceminidfs.bbm.session.pivot_state_machine", forced_pivot)
    monkeypatch.setattr("ceminidfs.bbm.session.recommend_top3", lambda *args, **kwargs: [])

    with _ServerHarness(port=18786, draft_id=api_test_setup) as server:
        status, body = _api_get(f"{server.base}/api/recommendations?draft_id={api_test_setup}")

    assert status == 200
    assert body["recommendations"] == []
    assert body["pivot_warning"] is not None
    assert body["pivot_to"] == "B"


def test_pivot_to_cleared_after_apply(
    api_test_setup: str, bbm_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    top_players = ledger.list_available_players(limit=6, db_path=bbm_db)
    assert len(top_players) >= 5
    for i, player in enumerate(top_players[:5], start=1):
        ledger.record_pick(api_test_setup, i, i, player["player_id"], is_mine=True, db_path=bbm_db)

    def forced_pivot(*args: Any, **kwargs: Any) -> PivotResult:
        del args, kwargs
        return PivotResult(new_archetype=Archetype.B, warning="forced advisory pivot", trigger_reason="test")

    monkeypatch.setattr("ceminidfs.bbm.session.pivot_state_machine", forced_pivot)

    with _ServerHarness(port=18787, draft_id=api_test_setup) as server:
        apply_status, apply_body = _api_post(
            f"{server.base}/api/pivot",
            {"draft_id": api_test_setup, "archetype": "B"},
        )
        rec_status, rec_body = _api_get(f"{server.base}/api/recommendations?draft_id={api_test_setup}")

    assert apply_status == 200
    assert apply_body["pivot_applied"] is True
    assert rec_status == 200
    assert rec_body["pivot_warning"] is None
    assert rec_body["pivot_to"] is None


def test_post_token_enforced(api_test_setup: str) -> None:
    with _ServerHarness(port=18777, draft_id=api_test_setup, token="s3cret") as server:
        no_token_status, no_token_body = _api_post(
            f"{server.base}/api/pick",
            {"draft_id": api_test_setup, "name": "Ja'Marr Chase"},
        )
        token_status, token_body = _api_post(
            f"{server.base}/api/pick",
            {"draft_id": api_test_setup, "name": "Ja'Marr Chase"},
            token="s3cret",
        )
        get_status, _ = _api_get(f"{server.base}/api/state?draft_id={api_test_setup}")

    assert no_token_status == 401
    assert no_token_body["error"] == "Unauthorized"
    assert token_status == 200
    assert token_body["player"]["name"] == "Ja'Marr Chase"
    assert get_status == 200
