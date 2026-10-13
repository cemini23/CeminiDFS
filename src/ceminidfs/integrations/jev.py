"""TypeSafe Jev client seam for the pre-lock gate.

Jev is a typed-question model. It reads prose and returns judgements. It is
not an optimizer and not a constraint solver. This module only moves text in
and judgements out.

Three tools, one per Jev primitive:

- ``verify``  (Noul)   claim against evidence -> verdict and confidence
- ``screen``  (Score)  text against a rubric -> probabilities and a
  recommendation of pass, review, block, or skip
- ``find``    (Choice) candidates against a query -> a ranked choice

The seam exists for one reason: the tests must run with no key and no network.
``RecordedJevClient`` replays a fixture. ``MCPJevClient`` speaks MCP over stdio
to the installed ``mcp-jev`` launcher.

Every path fails closed. A missing key, a missing launcher, a start failure, a
timeout, a JSON-RPC error, or a malformed payload raises. The caller must block
and ask the operator. No path returns an empty judgement that reads as a pass.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

DEFAULT_LAUNCHER = "~/.local/bin/mcp-jev"
DEFAULT_KEY_PATH = "~/.cemini/typesafe-api-key"
DEFAULT_TIMEOUT = 180.0
PROTOCOL_VERSION = "2024-11-05"

VERIFY = "verify"
SCREEN = "screen"
FIND = "find"

TOOL_NAMES = {VERIFY: "jev_verify", SCREEN: "jev_screen", FIND: "jev_find"}


class JevError(RuntimeError):
    """Base class for every Jev seam failure. The gate blocks on any of these."""


class JevUnavailableError(JevError):
    """No key, no launcher, or the server did not start."""


class JevResponseError(JevError):
    """The server answered with an error or an unreadable payload."""


class JevClient(Protocol):
    """The three primitives. Every method returns the parsed tool payload."""

    def verify(
        self,
        claims: Sequence[str],
        evidence: str | Sequence[Mapping[str, Any]],
        *,
        auto_accept: float = 0.8,
    ) -> dict[str, Any]: ...

    def screen(
        self,
        text: str,
        *,
        purpose: str | None = None,
        block_at: float = 0.75,
        review_at: float = 0.25,
    ) -> dict[str, Any]: ...

    def find(
        self,
        query: str,
        candidates: Sequence[Mapping[str, Any]],
        *,
        top_k: int = 5,
    ) -> dict[str, Any]: ...


def load_key(key_path: str | Path | None = None) -> str | None:
    """Return the TypeSafe key from the environment or the key file.

    The key is never logged and never written. An absent key returns ``None``.
    """

    value = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if value:
        return value
    path = Path(key_path or DEFAULT_KEY_PATH).expanduser()
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return None


class MCPJevClient:
    """Speak MCP JSON-RPC over stdio to the ``mcp-jev`` launcher."""

    def __init__(
        self,
        command: str | None = None,
        *,
        key_path: str | Path | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        launcher = command or os.environ.get("JEV_MCP_COMMAND") or DEFAULT_LAUNCHER
        self.command = str(Path(launcher).expanduser())
        self.timeout = float(timeout)
        key = load_key(key_path)
        if not key:
            raise JevUnavailableError(
                f"no TypeSafe key. Set TYPESAFE_API_KEY or write {DEFAULT_KEY_PATH}"
            )
        if not Path(self.command).is_file() and shutil.which(self.command) is None:
            raise JevUnavailableError(f"jev launcher not found: {self.command}")

        env = dict(os.environ)
        env["TYPESAFE_API_KEY"] = key
        try:
            self._proc = subprocess.Popen(
                [self.command],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
        except OSError as exc:
            raise JevUnavailableError(f"jev launcher did not start: {exc}") from exc

        self._inbox: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stderr: list[str] = []
        self._next_id = 0
        self._start_reader()
        self._initialize()

    def _start_reader(self) -> None:
        def pump() -> None:
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                text = line.strip()
                if not text:
                    continue
                try:
                    self._inbox.put(json.loads(text))
                except json.JSONDecodeError:
                    continue

        def drain() -> None:
            assert self._proc.stderr is not None
            for line in self._proc.stderr:
                self._stderr.append(line.rstrip())
                del self._stderr[:-20]

        threading.Thread(target=pump, daemon=True).start()
        threading.Thread(target=drain, daemon=True).start()

    def _send(self, payload: Mapping[str, Any]) -> None:
        if self._proc.stdin is None:
            raise JevUnavailableError("jev stdin is closed")
        try:
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            raise JevUnavailableError(f"jev pipe is closed: {exc}") from exc

    def _read(self, request_id: int) -> dict[str, Any]:
        while True:
            try:
                message = self._inbox.get(timeout=self.timeout)
            except queue.Empty as exc:
                raise JevUnavailableError(
                    f"jev did not answer in {self.timeout:.0f}s"
                ) from exc
            if message.get("id") != request_id:
                continue
            return message

    def _initialize(self) -> None:
        self._next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "ceminidfs", "version": "0.1"},
                },
            }
        )
        message = self._read(self._next_id)
        if "error" in message:
            raise JevUnavailableError(f"jev initialize failed: {message['error']}")
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _call(self, primitive: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": TOOL_NAMES[primitive], "arguments": dict(arguments)},
            }
        )
        message = self._read(request_id)
        if "error" in message:
            raise JevResponseError(f"jev {primitive} failed: {message['error']}")
        result = message.get("result")
        if not isinstance(result, Mapping):
            raise JevResponseError(f"jev {primitive} returned no result")
        content = result.get("content")
        text = ""
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, Mapping):
                text = str(first.get("text", ""))
        if result.get("isError"):
            raise JevResponseError(f"jev {primitive} error: {text or 'unknown'}")
        try:
            payload = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise JevResponseError(f"jev {primitive} returned unreadable text") from exc
        if not isinstance(payload, dict):
            raise JevResponseError(f"jev {primitive} payload is not an object")
        return payload

    def verify(
        self,
        claims: Sequence[str],
        evidence: str | Sequence[Mapping[str, Any]],
        *,
        auto_accept: float = 0.8,
    ) -> dict[str, Any]:
        return self._call(
            VERIFY,
            {"claims": list(claims), "evidence": evidence, "auto_accept": auto_accept},
        )

    def screen(
        self,
        text: str,
        *,
        purpose: str | None = None,
        block_at: float = 0.75,
        review_at: float = 0.25,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"text": text, "block_at": block_at, "review_at": review_at}
        if purpose:
            arguments["purpose"] = purpose
        return self._call(SCREEN, arguments)

    def find(
        self,
        query: str,
        candidates: Sequence[Mapping[str, Any]],
        *,
        top_k: int = 5,
    ) -> dict[str, Any]:
        return self._call(
            FIND,
            {"query": query, "candidates": list(candidates), "top_k": top_k},
        )

    def close(self) -> None:
        proc = getattr(self, "_proc", None)
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            proc.kill()

    def __enter__(self) -> "MCPJevClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


class RecordedJevClient:
    """Replay recorded tool payloads. No key, no network, no subprocess.

    The fixture is a JSON object with one optional list per primitive. Each
    call pops the next payload for that primitive. An exhausted list raises, so
    a test cannot pass by silently reusing an answer.
    """

    def __init__(self, fixture: str | Path | Mapping[str, Any]) -> None:
        if isinstance(fixture, (str, Path)):
            data = json.loads(Path(fixture).read_text(encoding="utf-8"))
        else:
            data = dict(fixture)
        if not isinstance(data, dict):
            raise JevResponseError("jev fixture must be a JSON object")
        self._queues: dict[str, list[dict[str, Any]]] = {}
        for primitive in (VERIFY, SCREEN, FIND):
            recorded = data.get(primitive, [])
            if isinstance(recorded, Mapping):
                recorded = [recorded]
            if not isinstance(recorded, list):
                raise JevResponseError(f"jev fixture '{primitive}' must be a list")
            self._queues[primitive] = [dict(item) for item in recorded]
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _next(self, primitive: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append((primitive, dict(arguments)))
        pending = self._queues[primitive]
        if not pending:
            raise JevResponseError(f"jev fixture has no {primitive} response left")
        return pending.pop(0)

    def verify(
        self,
        claims: Sequence[str],
        evidence: str | Sequence[Mapping[str, Any]],
        *,
        auto_accept: float = 0.8,
    ) -> dict[str, Any]:
        return self._next(
            VERIFY,
            {"claims": list(claims), "evidence": evidence, "auto_accept": auto_accept},
        )

    def screen(
        self,
        text: str,
        *,
        purpose: str | None = None,
        block_at: float = 0.75,
        review_at: float = 0.25,
    ) -> dict[str, Any]:
        return self._next(
            SCREEN,
            {"text": text, "purpose": purpose, "block_at": block_at, "review_at": review_at},
        )

    def find(
        self,
        query: str,
        candidates: Sequence[Mapping[str, Any]],
        *,
        top_k: int = 5,
    ) -> dict[str, Any]:
        return self._next(
            FIND,
            {"query": query, "candidates": list(candidates), "top_k": top_k},
        )


def build_jev_client(
    *,
    fixture: str | Path | None = None,
    command: str | None = None,
    key_path: str | Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> JevClient:
    """Return a recorded client for a fixture, else a live MCP client.

    A fixture wins. Without a fixture the live client starts, and raises
    ``JevUnavailableError`` when the key or the launcher is absent.
    """

    if fixture is not None:
        return RecordedJevClient(fixture)
    return MCPJevClient(command, key_path=key_path, timeout=timeout)
