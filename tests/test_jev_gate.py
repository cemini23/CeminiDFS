"""Jev pre-lock gate tests. No key. No network.

The Week 5 run is the fixture. The recorded client replays the jev-mcp
response shape, so the gate logic and the thresholds run for real.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ceminidfs.cli import build_parser
from ceminidfs.export.jev_gate import (
    JEV_GATE_HEADER,
    JEV_GATE_NAME,
    build_status_packet,
    run_jev_gate,
    status_claim,
    write_blocked_report,
)
from ceminidfs.integrations.jev import (
    FIND,
    SCREEN,
    VERIFY,
    JevResponseError,
    JevUnavailableError,
    MCPJevClient,
    RecordedJevClient,
    build_jev_client,
    load_key,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
WEEK5 = FIXTURES / "week5"
WEEK5_LINEUPS = WEEK5 / "lineups.csv"
WEEK5_PLAYERS = WEEK5 / "normalized_players.csv"
WEEK5_FIXTURE = FIXTURES / "jev" / "week5_gate.json"


def _run(tmp_path: Path, fixture=WEEK5_FIXTURE, **kwargs):
    client = RecordedJevClient(fixture)
    result = run_jev_gate(
        WEEK5_LINEUPS,
        WEEK5_PLAYERS,
        client=client,
        out_dir=tmp_path,
        date="2026-10-11",
        **kwargs,
    )
    return client, result


def _week5_fixture(**overrides):
    """Load the Week 5 fixture and replace one primitive with a scenario."""

    data = json.loads(WEEK5_FIXTURE.read_text(encoding="utf-8"))
    data.update(overrides)
    return data


def _status_rows(result):
    """Map player to the availability row. A player also has a Choice row."""

    return {row.player: row for row in result.rows if "is expected to be active" in row.question}


def _starter_rows(result):
    return {row.player: row for row in result.rows if "confirmed starter" in row.question}


def _block_rows(result):
    return [row for row in result.rows if row.action == "block"]


# --- Gate 1: status (Noul) -----------------------------------------------------


def test_gate_routes_addison_to_the_operator(tmp_path: Path):
    """Live, a Questionable tag contradicts "active" only weakly.

    Jev returned contradicted at 0.23 confidence. Below the 0.80 floor the
    gate asks a person. That is the specified behavior, and the honest result:
    a Q tag alone is not evidence that a player sits.
    """

    _client, result = _run(tmp_path)

    row = _status_rows(result)["Jordan Addison"]

    assert row.action == "review"
    assert "contradicted" in row.result
    assert row.question == (
        "Jordan Addison is expected to be active for MIN in MIN@NO on 2026-10-11."
    )
    assert row.evidence_ref == "status_packet"


def test_gate_flags_a_player_whose_evidence_contradicts(tmp_path: Path):
    """The flag path. A confident contradiction is a candidate inactive.

    The Week 5 packet never contradicted anyone at 0.80, so this case is
    constructed from the live fixture to exercise the branch.
    """

    data = _week5_fixture()
    for entry in data["verify"][0]["results"]:
        if entry["claim"].startswith("Jordan Addison is expected to be active"):
            entry["verdict"] = "contradicted"
            entry["confidence"] = 0.93
            entry["probabilities"]["supports"] = 0.04

    _client, result = _run(tmp_path, fixture=data)

    row = _status_rows(result)["Jordan Addison"]

    assert row.action == "flag"
    assert row.confidence == "0.93"


def test_unsupported_evidence_routes_to_review_not_flag(tmp_path: Path):
    """Silence is not an accusation.

    The live run returned ``unsupported`` for all 12 QBs, because the packet
    holds no depth-chart data. An early build marked all 12 as flags, which
    accused Rodgers, Goff, Burrow, and Watson of not being starters.
    """

    _client, result = _run(tmp_path)

    starters = _starter_rows(result)

    assert starters["Aaron Rodgers"].result.startswith("unsupported")
    assert starters["Aaron Rodgers"].action == "review"
    assert starters["C.J. Stroud"].action == "review"
    assert not any(row.action == "flag" for row in starters.values())


def test_gate_passes_a_player_with_no_status_doubt(tmp_path: Path):
    _client, result = _run(tmp_path)

    assert _status_rows(result)["Jahmyr Gibbs"].action == "pass"


def test_gate_asks_one_question_per_q_and_over_cap_player(tmp_path: Path):
    _client, result = _run(tmp_path)

    questions = _status_rows(result)

    assert len(questions) == 25


def test_low_confidence_routes_to_the_operator(tmp_path: Path):
    _client, result = _run(tmp_path)

    row = _status_rows(result)["Tee Higgins"]

    assert row.action == "review"
    assert float(row.confidence) < 0.80


# --- Gate 2: QB starter (Noul) -------------------------------------------------


def test_gate_checks_every_rostered_qb(tmp_path: Path):
    _client, result = _run(tmp_path)

    starters = _starter_rows(result)

    assert len(starters) == 12
    assert starters["Brock Purdy"].evidence_ref == "players_csv"
    assert starters["Brock Purdy"].question.endswith("confirmed starter for SF.")


def test_all_noul_questions_go_in_one_call(tmp_path: Path):
    client, _result = _run(tmp_path)

    verify_calls = [call for call in client.calls if call[0] == VERIFY]

    assert len(verify_calls) == 1
    assert len(verify_calls[0][1]["claims"]) == 37


# --- Gate 3: injection screen (Score) -----------------------------------------


def test_gate_blocks_when_the_status_packet_fails_the_screen(tmp_path: Path):
    fixture = {
        "screen": [
            {
                "probabilities": {"injection": 0.99, "substance": 0.9, "relevance": 0.8},
                "recommendation": {
                    "action": "block",
                    "reason": "injection probability 0.99 >= block threshold 0.75",
                },
            }
        ]
    }
    client, result = _run(tmp_path, fixture=fixture)

    assert result.blocked is True
    assert result.rows[0].action == "block"
    assert result.rows[0].primitive == SCREEN
    # The gate stopped. No claim reached Jev.
    assert [call[0] for call in client.calls] == [SCREEN]


def test_screen_review_is_not_a_pass(tmp_path: Path):
    fixture = _week5_fixture(
        screen=[
            {
                "probabilities": {"injection": 0.4, "substance": 0.9, "relevance": 0.7},
                "recommendation": {"action": "review", "reason": "review band"},
            }
        ]
    )
    client, result = _run(tmp_path, fixture=fixture)

    assert result.blocked is False
    assert result.rows[0].action == "review"
    # A review still asks the questions. The screen only blocks on block.
    assert [call[0] for call in client.calls].count(VERIFY) == 1


# --- Gate 4: late-swap input (Choice) -----------------------------------------


def test_gate_marks_late_swap_choices(tmp_path: Path):
    _client, result = _run(tmp_path)

    choices = [row for row in result.rows if row.primitive == FIND]

    assert len(choices) == 9
    assert all(row.action == "review" for row in choices)
    assert all(row.evidence_ref == "late_swap_alert_report.csv" for row in choices)
    addison = [row for row in choices if row.player == "Jordan Addison"][0]
    assert "Jauan_Jennings" in addison.result


# --- Gate 5: cash-set claim ----------------------------------------------------


def test_cash_claim_without_a_screenshot_stays_unknown(tmp_path: Path):
    _client, result = _run(
        tmp_path,
        enable_cash=True,
        cash_claim="Week 5 cashed 30 of 150.",
        standings=None,
    )

    row = [r for r in result.rows if r.player == "(recap)"][0]

    assert row.result == "UNKNOWN"
    assert row.action == "review"


# --- Fail closed ---------------------------------------------------------------


def test_missing_key_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    with pytest.raises(JevUnavailableError, match="no TypeSafe key"):
        build_jev_client(key_path=tmp_path / "absent-key")


def test_missing_launcher_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key-not-real")

    with pytest.raises(JevUnavailableError, match="launcher not found"):
        build_jev_client(command=str(tmp_path / "absent-mcp-jev"))


def test_server_error_blocks_the_gate(tmp_path: Path):
    class BrokenClient:
        def screen(self, *args, **kwargs):
            raise JevResponseError("Connection error: fetch failed")

        def verify(self, *args, **kwargs):  # pragma: no cover - never reached
            raise AssertionError("verify must not run after a blocked screen")

        def find(self, *args, **kwargs):  # pragma: no cover - never reached
            raise AssertionError("find must not run after a blocked screen")

    result = run_jev_gate(
        WEEK5_LINEUPS,
        WEEK5_PLAYERS,
        client=BrokenClient(),
        out_dir=tmp_path,
        date="2026-10-11",
    )

    assert result.blocked is True
    assert result.rows[0].action == "block"
    assert "Connection error" in result.rows[0].result


def test_malformed_verify_payload_blocks(tmp_path: Path):
    fixture = _week5_fixture(
        screen=[{"recommendation": {"action": "pass"}, "probabilities": {"injection": 0.0}}],
        verify=[{"results": []}],
    )
    _client, result = _run(tmp_path, fixture=fixture)

    assert result.blocked is True
    blocks = _block_rows(result)
    assert len(blocks) == 1
    assert "malformed" in blocks[0].result


def test_recorded_client_refuses_to_reuse_an_answer(tmp_path: Path):
    client = RecordedJevClient({"screen": [{"recommendation": {"action": "pass"}}]})

    client.screen("one")

    with pytest.raises(JevResponseError, match="no screen response left"):
        client.screen("two")


def test_blocked_gate_still_writes_the_artifact(tmp_path: Path):
    path = write_blocked_report(tmp_path, WEEK5_LINEUPS, "no TypeSafe key")

    assert path.name == JEV_GATE_NAME
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].split(",") == JEV_GATE_HEADER
    assert lines[1].endswith("block,")


def test_key_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "env-key")

    assert load_key(tmp_path / "absent") == "env-key"


def test_key_file_is_never_required_when_the_env_is_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    key_file = tmp_path / "typesafe-api-key"
    key_file.write_text("file-key\n", encoding="utf-8")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    assert load_key(key_file) == "file-key"


# --- Artifact and contract -----------------------------------------------------


def test_report_header_and_actions(tmp_path: Path):
    _client, result = _run(tmp_path)

    with result.path.open(newline="", encoding="utf-8") as handle:
        import csv

        reader = csv.reader(handle)
        header = next(reader)
        rows = list(reader)

    assert result.path.name == JEV_GATE_NAME
    assert header == JEV_GATE_HEADER
    assert rows
    assert {row[5] for row in rows} <= {"pass", "flag", "review", "block"}


def test_summary_counts_every_action(tmp_path: Path):
    _client, result = _run(tmp_path)

    summary = result.summary()

    assert summary == "jev gate: pass=17 flag=0 review=30 block=0 low_confidence=30"


def test_gate_does_not_write_a_lineup(tmp_path: Path, tmp_path_factory):
    before = WEEK5_LINEUPS.read_bytes()
    _client, _result = _run(tmp_path)

    assert WEEK5_LINEUPS.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [JEV_GATE_NAME]


def test_status_claim_omits_a_missing_date():
    assert status_claim("A B", "KC", "KC@BUF", None) == "A B is expected to be active for KC in KC@BUF."


def test_status_packet_carries_the_inactive_report():
    packet = build_status_packet({}, ["Jordan Addison"], date="2026-10-11", extra="Addison ruled out.")

    assert packet.startswith("Week status packet (2026-10-11)")
    assert "Jordan Addison | status unknown" in packet
    assert "Addison ruled out." in packet


def test_review_jev_flags_parse():
    parser = build_parser()

    args = parser.parse_args(
        [
            "review",
            "--lineups",
            "lineups.csv",
            "--players",
            "players.csv",
            "--jev",
            "--jev-fixture",
            "fixture.json",
            "--jev-date",
            "2026-10-11",
            "--jev-exposure-cap",
            "0.2",
        ]
    )

    assert args.jev is True
    assert str(args.jev_fixture) == "fixture.json"
    assert args.jev_exposure_cap == pytest.approx(0.2)
    assert parser.parse_args(
        ["review", "--lineups", "l.csv", "--players", "p.csv"]
    ).jev is False


def test_mcp_client_is_not_started_without_a_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    with pytest.raises(JevUnavailableError):
        MCPJevClient(command=str(tmp_path / "absent"), key_path=tmp_path / "absent-key")


def test_gate_seam_and_tiered_router_have_distinct_surfaces():
    """The gate seam and the tiered router must stay separate clients.

    ``integrations.jev`` is the fail-closed pre-lock gate (verify/screen/find over
    stdio MCP, fixture-replayable). ``ceminidfs.jev_client`` is the model-wide
    tiered router (jev_choice/jev_score over provider tiers with a prior
    fallback). Merging them would give the gate a silent-prior path, so each must
    expose only its own surface.
    """

    from ceminidfs import jev_client as tiered

    gate = build_jev_client(fixture={"verify": [{}], "screen": [{}], "find": [{}]})
    router = tiered.build_jev_client(provider=tiered.PROVIDER_PRIOR)

    for primitive in (VERIFY, SCREEN, FIND):
        assert hasattr(gate, primitive)
    assert not hasattr(gate, "jev_choice")
    assert not hasattr(gate, "jev_score")

    assert hasattr(router, "jev_choice")
    assert hasattr(router, "jev_score")
    assert not hasattr(router, "verify")
    assert not hasattr(router, "screen")
    assert not hasattr(router, "find")
