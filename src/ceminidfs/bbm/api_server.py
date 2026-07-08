"""BBM Phase 3 Local API Server.

HTTP API for Chrome extension integration with CeminiBBM draft copilot.
Uses only stdlib http.server for zero-dependency operation.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse


# Lazy imports to avoid circular dependencies
def _get_ledger() -> Any:
    from ceminidfs.bbm import ledger
    return ledger


def _get_session() -> Any:
    from ceminidfs.bbm import session
    return session


def _get_board_parse() -> Any:
    from ceminidfs.bbm import board_parse
    return board_parse


@dataclass
class ServerConfig:
    """Configuration for the API server."""
    host: str = "127.0.0.1"
    port: int = 8765
    draft_id: Optional[str] = None
    slot: Optional[int] = None
    archetype: Optional[str] = None
    token: Optional[str] = None


class CorsRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler with CORS support for Chrome extension."""

    def __init__(self, config: ServerConfig, *args: Any, **kwargs: Any) -> None:
        self.config = config
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        """Override to suppress default logging (or customize)."""
        # Only log errors, not every request
        if args[1] != "200":
            print(f"[{self.log_date_time_string()}] {self.address_string()} - {format % args}", file=sys.stderr)

    def _set_cors_headers(self) -> None:
        """Add CORS headers to allow Chrome extension access."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-BBM-Token")
        self.send_header("Content-Type", "application/json")

    def _send_json_response(self, data: dict[str, Any], status: int = 200) -> None:
        """Send a JSON response with CORS headers."""
        self.send_response(status)
        self._set_cors_headers()
        response_body = json.dumps(data).encode("utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def _send_error(self, message: str, status: int = 400) -> None:
        """Send an error response."""
        self._send_json_response({"error": message}, status=status)

    def _parse_json_body(self) -> dict[str, Any]:
        """Parse JSON request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        query_params = parse_qs(parsed.query)

        # Flatten query params (take first value)
        params: dict[str, str] = {k: v[0] if v else "" for k, v in query_params.items()}

        try:
            if path == "/" or path == "/api/status":
                self._handle_status()
            elif path == "/health":
                self._handle_health()
            elif path == "/api/state":
                self._handle_state(params)
            elif path == "/api/recommendations":
                self._handle_recommendations(params)
            else:
                self._send_error("Not found", status=404)
        except Exception as e:
            self._send_error(f"Internal error: {e}", status=500)

    def do_POST(self) -> None:
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if self.config.token:
            if self.headers.get("X-BBM-Token") != self.config.token:
                self._send_error("Unauthorized", status=401)
                return

        try:
            body = self._parse_json_body()
        except ValueError as e:
            self._send_error(str(e), status=400)
            return

        try:
            if path == "/api/sync":
                self._handle_sync(body)
            elif path == "/api/pick":
                self._handle_pick(body)
            elif path == "/api/taken":
                self._handle_taken(body)
            elif path == "/api/undo":
                self._handle_undo(body)
            elif path == "/api/pivot":
                self._handle_pivot(body)
            else:
                self._send_error("Not found", status=404)
        except Exception as e:
            self._send_error(f"Internal error: {e}", status=500)

    def _handle_health(self) -> None:
        """GET /health -> {"ok": true}"""
        self._send_json_response({"ok": True})

    def _handle_status(self) -> None:
        """GET / or /api/status -> server + active draft metadata for extension auto-config."""
        payload: dict[str, Any] = {
            "ok": True,
            "service": "ceminidfs-bbm",
            "draft_id": self.config.draft_id,
            "slot": self.config.slot,
            "archetype": self.config.archetype,
            "endpoints": {
                "health": "/health",
                "status": "/api/status",
                "state": "/api/state?draft_id=<id>",
                "recommendations": "/api/recommendations?draft_id=<id>",
            },
            "hint": (
                "Browser: use /health or /api/status — not an error if you see JSON here. "
                "Extension: set draft_id from this response if popup is empty."
            ),
        }
        if self.config.draft_id:
            ledger = _get_ledger()
            state = ledger.get_draft_state(self.config.draft_id)
            if state is not None:
                payload["current_round"] = state.current_round
                payload["pick_num"] = self._compute_pick_num(state.current_round, state.slot)
                payload["status"] = state.status
                payload["single_entry"] = state.is_single_entry
        self._send_json_response(payload)

    def _handle_state(self, params: dict[str, str]) -> None:
        """GET /api/state?draft_id= -> draft state with snake pick number."""
        draft_id = params.get("draft_id") or self.config.draft_id
        if not draft_id:
            self._send_error("Missing draft_id", status=400)
            return

        ledger = _get_ledger()
        state = ledger.get_draft_state(draft_id)

        if state is None:
            self._send_error("Draft not found", status=404)
            return

        # Compute pick_num using snake logic (same as CLI)
        pick_num = self._compute_pick_num(state.current_round, state.slot)

        # Get room_taken count
        room_taken_count = ledger.count_room_taken(draft_id)

        response = {
            "draft_id": state.draft_id,
            "slot": state.slot,
            "archetype": state.archetype,
            "current_round": state.current_round,
            "pick_num": pick_num,
            "total_rounds": state.total_rounds,
            "status": state.status,
            "room_taken": room_taken_count,
        }
        self._send_json_response(response)

    def _handle_recommendations(self, params: dict[str, str]) -> None:
        """GET /api/recommendations?draft_id= -> recommendations."""
        draft_id = params.get("draft_id") or self.config.draft_id
        if not draft_id:
            self._send_error("Missing draft_id", status=400)
            return

        ledger = _get_ledger()
        session = _get_session()

        # Get draft state to determine current round and pick
        state = ledger.get_draft_state(draft_id)
        if state is None:
            self._send_error("Draft not found", status=404)
            return

        current_round = state.current_round
        pick_num = self._compute_pick_num(current_round, state.slot)
        archetype = params.get("archetype") or state.archetype

        meta = session.get_recommendations_meta(
            round_num=current_round,
            pick_num=pick_num,
            archetype_str=archetype,
            draft_id=draft_id,
            limit=5,
        )

        # Format response
        formatted_recs: list[dict[str, Any]] = []
        for i, rec in enumerate(meta["recommendations"], 1):
            formatted_recs.append({
                "rank": i,
                "player_id": rec.get("player_id"),
                "name": rec.get("name"),
                "position": rec.get("position"),
                "team": rec.get("team"),
                "signal": rec.get("signal"),
                "exp_current": rec.get("exp_current"),
                "exp_cap": rec.get("exp_cap"),
                "is_stack_candidate": rec.get("is_stack_candidate"),
                "warnings": rec.get("warnings", []),
                "score": rec.get("score"),
            })

        self._send_json_response({
            "draft_id": draft_id,
            "round": current_round,
            "pick_num": pick_num,
            "archetype": archetype,
            "pivot_warning": meta["pivot_warning"],
            "pivot_to": meta["pivot_to"],
            "recommendations": formatted_recs,
        })

    def _handle_sync(self, body: dict[str, Any]) -> None:
        """POST /api/sync JSON {draft_id, names?: string[], labels?: string[]} -> sync players."""
        draft_id = body.get("draft_id") or self.config.draft_id
        names = body.get("names", [])
        labels = body.get("labels", [])

        if not draft_id:
            self._send_error("Missing draft_id", status=400)
            return

        if not isinstance(names, list) or not isinstance(labels, list):
            self._send_error("names/labels must be arrays", status=400)
            return

        if labels:
            board_parse = _get_board_parse()
            parsed_names = board_parse.extract_names_from_aria_labels(
                [label for label in labels if isinstance(label, str)]
            )
            names = list(names) + board_parse.filter_draft_board_names(parsed_names)

        names = names[:200]

        ledger = _get_ledger()
        session = _get_session()

        # Get state for current round/pick
        state = ledger.get_draft_state(draft_id)
        if state is None:
            self._send_error("Draft not found", status=404)
            return

        current_round = state.current_round
        pick_num = self._compute_pick_num(current_round, state.slot)

        already_recorded = session.get_taken_player_ids(draft_id)
        synced: list[dict[str, Any]] = []
        skipped_existing: list[str] = []
        unmatched: list[str] = []
        ambiguous: list[dict[str, Any]] = []

        for name in names:
            if not isinstance(name, str):
                unmatched.append(str(name))
                continue

            player = ledger.resolve_player_query(name)
            if player is None:
                # Check if ambiguous
                last_ambiguous = ledger.get_last_ambiguous_matches()
                if last_ambiguous and len(last_ambiguous) > 1:
                    ambiguous.append({
                        "query": name,
                        "matches": [
                            {
                                "player_id": m.get("player_id"),
                                "name": m.get("name"),
                                "position": m.get("position"),
                                "team": m.get("team"),
                                "index": i + 1,
                            }
                            for i, m in enumerate(last_ambiguous)
                        ],
                    })
                else:
                    unmatched.append(name)
                continue

            if player["player_id"] in already_recorded:
                skipped_existing.append(player["name"])
                continue

            # Record as taken
            ledger.record_taken(draft_id, current_round, pick_num, player["player_id"])
            already_recorded.add(player["player_id"])
            synced.append({
                "name": player["name"],
                "player_id": player["player_id"],
                "position": player["position"],
                "team": player.get("team"),
            })

        self._send_json_response({
            "draft_id": draft_id,
            "synced": synced,
            "synced_count": len(synced),
            "skipped_existing": skipped_existing,
            "skipped_count": len(skipped_existing),
            "unmatched": unmatched,
            "unmatched_count": len(unmatched),
            "ambiguous": ambiguous,
            "ambiguous_count": len(ambiguous),
        })

    def _handle_pick(self, body: dict[str, Any]) -> None:
        """POST /api/pick JSON {draft_id, name? player_id?} -> resolve and record pick."""
        draft_id = body.get("draft_id") or self.config.draft_id
        name = body.get("name")
        player_id = body.get("player_id")

        if not draft_id:
            self._send_error("Missing draft_id", status=400)
            return

        if player_id is not None and not isinstance(player_id, str):
            self._send_error("Invalid player_id", status=400)
            return

        if not player_id and (not name or not isinstance(name, str)):
            self._send_error("Missing or invalid name", status=400)
            return

        ledger = _get_ledger()

        # Get state for current round/pick
        state = ledger.get_draft_state(draft_id)
        if state is None:
            self._send_error("Draft not found", status=404)
            return

        current_round = state.current_round
        pick_num = self._compute_pick_num(current_round, state.slot)

        if player_id:
            player = ledger.get_player_by_id(player_id)
            if player is None:
                self._send_error(f"Player not found: {player_id}", status=404)
                return
        else:
            # Picks are strict: unknown names return 404 and never create stubs.
            player = ledger.resolve_player_query(name)
            if player is None:
                last_ambiguous = ledger.get_last_ambiguous_matches()
                if last_ambiguous and len(last_ambiguous) > 1:
                    self._send_json_response({
                        "draft_id": draft_id,
                        "ambiguous": True,
                        "query": name,
                        "matches": [
                            {
                                "player_id": m.get("player_id"),
                                "name": m.get("name"),
                                "position": m.get("position"),
                                "team": m.get("team"),
                                "index": i + 1,
                            }
                            for i, m in enumerate(last_ambiguous)
                        ],
                    })
                    return
                self._send_error(f"Player not found: {name}", status=404)
                return

        # Record pick
        result = ledger.record_pick(draft_id, current_round, pick_num, player["player_id"], is_mine=True)

        self._send_json_response({
            "draft_id": draft_id,
            "player": {
                "player_id": player["player_id"],
                "name": player["name"],
                "position": player["position"],
                "team": player.get("team"),
            },
            "round": result["round"],
            "pick_num": result["pick_num"],
            "is_mine": result["is_mine"],
        })

    def _handle_taken(self, body: dict[str, Any]) -> None:
        """POST /api/taken JSON {draft_id, name? player_id?} -> resolve or stub and record taken.

        player_id path never stubs — stubs are only a name-path fallback.
        """
        draft_id = body.get("draft_id") or self.config.draft_id
        name = body.get("name")
        player_id = body.get("player_id")

        if not draft_id:
            self._send_error("Missing draft_id", status=400)
            return

        if player_id is not None and not isinstance(player_id, str):
            self._send_error("Invalid player_id", status=400)
            return

        if not player_id and (not name or not isinstance(name, str)):
            self._send_error("Missing or invalid name", status=400)
            return

        ledger = _get_ledger()

        # Get state for current round/pick
        state = ledger.get_draft_state(draft_id)
        if state is None:
            self._send_error("Draft not found", status=404)
            return

        current_round = state.current_round
        pick_num = self._compute_pick_num(current_round, state.slot)

        is_stub = False

        if player_id:
            player = ledger.get_player_by_id(player_id)
            if player is None:
                self._send_error(f"Player not found: {player_id}", status=404)
                return
        else:
            # Try to resolve player
            player = ledger.resolve_player_query(name)
            if player is None:
                # Check if ambiguous
                last_ambiguous = ledger.get_last_ambiguous_matches()
                if last_ambiguous and len(last_ambiguous) > 1:
                    self._send_json_response({
                        "draft_id": draft_id,
                        "ambiguous": True,
                        "query": name,
                        "matches": [
                            {
                                "player_id": m.get("player_id"),
                                "name": m.get("name"),
                                "position": m.get("position"),
                                "team": m.get("team"),
                                "index": i + 1,
                            }
                            for i, m in enumerate(last_ambiguous)
                        ],
                    })
                    return

                # Create stub
                player = ledger.ensure_player_stub(name)
                is_stub = True

        # Record as taken
        ledger.record_taken(draft_id, current_round, pick_num, player["player_id"])

        response = {
            "draft_id": draft_id,
            "player": {
                "player_id": player["player_id"],
                "name": player["name"],
                "position": player["position"],
                "team": player.get("team"),
            },
            "round": current_round,
            "pick_num": pick_num,
            "is_stub": is_stub,
        }
        if is_stub:
            response["warning"] = f"Unknown player '{name}' recorded as stub — verify spelling"
        self._send_json_response(response)

    def _handle_undo(self, body: dict[str, Any]) -> None:
        """POST /api/undo JSON {draft_id} -> undo last pick/taken action."""
        draft_id = body.get("draft_id") or self.config.draft_id
        if not draft_id:
            self._send_error("Missing draft_id", status=400)
            return
        result = _get_ledger().undo_last_action(draft_id)
        if result is None:
            self._send_error("Nothing to undo", status=404)
            return
        self._send_json_response({"draft_id": draft_id, **result})

    def _handle_pivot(self, body: dict[str, Any]) -> None:
        """POST /api/pivot JSON {draft_id, archetype} -> explicitly apply archetype pivot."""
        draft_id = body.get("draft_id") or self.config.draft_id
        archetype = str(body.get("archetype", "")).upper()
        if not draft_id:
            self._send_error("Missing draft_id", status=400)
            return
        if archetype not in ("A", "B", "C", "D", "E"):
            self._send_error("archetype must be A-E", status=400)
            return
        result = _get_ledger().apply_pivot(draft_id, archetype, f"manual pivot to {archetype}")
        self._send_json_response(result)

    def _compute_pick_num(self, round_num: int, slot: int) -> int:
        """Compute pick number using snake draft logic.

        Same as CLI: odd rounds go 1-12, even rounds go 12-1.
        """
        if round_num % 2 == 1:
            return (round_num - 1) * 12 + slot
        return round_num * 12 - slot + 1


class BBMAPIRequestHandler:
    """Factory for creating request handlers with config."""

    def __init__(self, config: ServerConfig):
        self.config = config

    def __call__(self, *args: Any, **kwargs: Any) -> CorsRequestHandler:
        return CorsRequestHandler(self.config, *args, **kwargs)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    draft_id: Optional[str] = None,
    slot: Optional[int] = None,
    archetype: Optional[str] = None,
    token: Optional[str] = None,
) -> HTTPServer:
    """Create an HTTP server instance.

    Args:
        host: Bind address (default: 127.0.0.1 for localhost only).
        port: Port number (default: 8765).
        draft_id: Optional default draft ID.
        slot: Optional default draft slot.
        archetype: Optional default archetype.
        token: Optional static token for POST auth (X-BBM-Token).

    Returns:
        Configured HTTPServer instance.
    """
    config = ServerConfig(
        host=host,
        port=port,
        draft_id=draft_id,
        slot=slot,
        archetype=archetype,
        token=token,
    )
    handler_class = BBMAPIRequestHandler(config)
    return HTTPServer((host, port), handler_class)


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    draft_id: Optional[str] = None,
    slot: Optional[int] = None,
    archetype: Optional[str] = None,
    token: Optional[str] = None,
    on_shutdown: Optional[Callable[[], None]] = None,
) -> None:
    """Run the API server until interrupted.

    Args:
        host: Bind address (default: 127.0.0.1 for localhost only).
        port: Port number (default: 8765).
        draft_id: Optional default draft ID.
        slot: Optional default draft slot.
        archetype: Optional default archetype.
        token: Optional static token for POST auth (X-BBM-Token).
        on_shutdown: Optional callback when server stops.
    """
    server = create_server(host, port, draft_id, slot, archetype, token)

    print(f"BBM API server listening at http://{host}:{port}", flush=True)
    print("Endpoints:", flush=True)
    print("  GET  / or /api/status      -> server status + draft_id", flush=True)
    print("  GET  /health               -> {\"ok\": true}", flush=True)
    print("  GET  /api/state?draft_id=  -> draft state", flush=True)
    print("  GET  /api/recommendations?draft_id= -> recommendations", flush=True)
    print("  POST /api/sync             -> {draft_id, names?: [], labels?: []}", flush=True)
    print("  POST /api/pick             -> {draft_id, name}", flush=True)
    print("  POST /api/taken            -> {draft_id, name}", flush=True)
    print("  POST /api/undo             -> {draft_id}", flush=True)
    print("  POST /api/pivot            -> {draft_id, archetype}", flush=True)
    if token:
        print("  POST auth                  -> X-BBM-Token header required", flush=True)
    print("\nServer ready — extension polls this API (Ctrl+C to stop)", flush=True)
    print("  If panel missing: reload extension + use app.underdogsports.com draft tab", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
    finally:
        server.shutdown()
        if on_shutdown:
            on_shutdown()


# Simple test/run entry point
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BBM Local API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument("--draft-id", help="Default draft ID")
    parser.add_argument("--slot", type=int, help="Default draft slot")
    parser.add_argument("--archetype", help="Default archetype")
    parser.add_argument("--token", type=str, default=None, help="Optional static token required on POST endpoints (X-BBM-Token header)")

    args = parser.parse_args()

    run_server(
        host=args.host,
        port=args.port,
        draft_id=args.draft_id,
        slot=args.slot,
        archetype=args.archetype,
        token=args.token,
    )
