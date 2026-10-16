"""Tiered typed Jev client for structured ``Choice`` / ``Score`` decisions.

Jev is a discrete epistemic router. It reads structured state and returns a
calibrated probability vector plus a confidence. It never runs continuous math,
regression, or Monte Carlo simulation. Python owns all of that.

Provider routing order (``provider``):

1. ``typesafe`` — Primary A. TypeSafe System One API. One forward pass over the
   ``state`` can answer many questions. ``TYPESAFE_API_KEY`` (or
   ``TYPESAFE_AI_API_KEY``, or ``~/.cemini/typesafe-api-key``).
2. ``mcp``      — Primary B. Jev MCP server. A pre-populated batch artifact
   (``JEV_MCP_BATCH``) answers offline. ``JEV_MCP_URL`` posts over HTTP.
3. ``openrouter`` — Backup. Used when the primaries are unconfigured or raise a
   transient error (timeout, HTTP 429, or 5xx). ``OPENROUTER_API_KEY``.
4. ``prior``    — Offline fallback. Deterministic prior weights. No network.

Every answer is cached on disk at ``data/cache/jev/<sha256>.json`` keyed by the
canonical ``(model_version, state_hash, questions_hash)``. A repeated run costs
nothing and is byte-for-byte reproducible.

Every path fails closed. A response that violates the schema, or carries a NaN
or null confidence, triggers one backup-provider retry. If that also fails the
client raises ``JevValidationError`` (or applies the prior fallback when the
caller asked for it). No path returns a silent pass.

Relationship to ``ceminidfs.integrations.jev``
---------------------------------------------
This module is the model-wide **tiered router**: structured ``Choice``/``Score``
routing across provider tiers (typesafe / mcp / openrouter) with a deterministic
prior fallback and a sha256 disk cache. It is what the projection and calibration
path imports. ``ceminidfs.integrations.jev`` is the separate pre-lock **gate**
seam: three fail-closed primitives (``verify``/``screen``/``find``) over stdio MCP
with a fixture replayer, where every failure raises and the caller blocks. The
router degrades to a prior offline; the gate never does. Keep gate callers on
``integrations.jev`` and routing callers here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:  # pragma: no cover - optional HTTP client.
    import httpx
except ImportError:  # pragma: no cover - urllib fallback path.
    httpx = None  # type: ignore[assignment]

from pydantic import BaseModel, ConfigDict

try:  # pragma: no cover - PROJECT_ROOT is stable; the fallback guards partial installs.
    from ceminidfs.config import PROJECT_ROOT
except Exception:  # pragma: no cover
    PROJECT_ROOT = Path.cwd()

LOGGER = logging.getLogger("ceminidfs.jev")

DEFAULT_MODEL_VERSION = "jev-1.13"
DEFAULT_TYPESAFE_MODEL = "jev-latest"
DEFAULT_TYPESAFE_BASE = "https://api.typesafe.ai"
DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "typesafe/jev-1.13"
DEFAULT_KEY_PATH = "~/.cemini/typesafe-api-key"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "jev"
DEFAULT_TIMEOUT = 60.0
PROBABILITY_TOLERANCE = 1.0e-2
MAX_CONCURRENCY = 16

PROVIDER_AUTO = "auto"
PROVIDER_TYPESAFE = "typesafe"
PROVIDER_MCP = "mcp"
PROVIDER_OPENROUTER = "openrouter"
PROVIDER_PRIOR = "prior"
PROVIDERS = (PROVIDER_AUTO, PROVIDER_TYPESAFE, PROVIDER_MCP, PROVIDER_OPENROUTER, PROVIDER_PRIOR)

FALLBACK_PRIOR = "prior"
FALLBACK_RAISE = "raise"

# Deterministic priors. Jev is a router; when no network provider is reachable
# the router uses these categorical base rates. They are documented, fixed, and
# independent of the state, so a backtest is reproducible without a key.
REGIME_PRIOR: dict[str, float] = {
    "full_role": 0.60,
    "snap_count_decoy": 0.20,
    "in_game_reaggravation_exit": 0.12,
    "pre_game_inactive": 0.08,
}
OWNERSHIP_PRIOR: dict[str, float] = {
    "contrarian_sub_3pct": 0.35,
    "low_own_3_to_8pct": 0.30,
    "moderate_8_to_15pct": 0.20,
    "chalk_15_to_25pct": 0.10,
    "mega_chalk_25pct_plus": 0.05,
}
ALIGNMENT_PRIOR: dict[str, float] = {
    "heavy_shadow_65pct_plus": 0.40,
    "base_side_alignment_35_to_65pct": 0.40,
    "schemed_avoidance_slot_motion_sub_35pct": 0.20,
}
KNOWN_PRIORS: dict[str, dict[str, float]] = {
    **REGIME_PRIOR,
    **OWNERSHIP_PRIOR,
    **ALIGNMENT_PRIOR,
}
PRIOR_CONFIDENCE = 0.55


class JevError(RuntimeError):
    """Base class for every Jev client failure."""


class JevUnavailableError(JevError):
    """No provider is configured or reachable."""


class JevValidationError(JevError):
    """A provider answered, but the payload violates the schema."""


class JevProviderError(JevError):
    """A provider transport failed. ``transient`` drives the failover choice."""

    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.transient = bool(transient)


class HTTPTimeout(Exception):
    """The transport timed out."""


class HTTPStatusError(Exception):
    """The transport returned a non-2xx status code."""

    def __init__(self, status: int, body: str = "") -> None:
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = int(status)
        self.body = body


# --------------------------------------------------------------------------- #
# Pydantic result models. The client always builds these, so the schema is
# enforced at the boundary the caller sees.
# --------------------------------------------------------------------------- #
class ChoiceResult(BaseModel):
    """A normalized choice distribution over named options."""

    model_config = ConfigDict(extra="allow")

    probabilities: dict[str, float]
    top_choice: str
    confidence: float
    provider_used: str
    model_version: str = DEFAULT_MODEL_VERSION
    cached: bool = False

    def probability(self, choice: str) -> float:
        return float(self.probabilities.get(choice, 0.0))


class ScoreResult(BaseModel):
    """A normalized score distribution over an ordered scale."""

    model_config = ConfigDict(extra="allow")

    probabilities: dict[str, float]
    expected_score: float
    confidence: float
    provider_used: str
    model_version: str = DEFAULT_MODEL_VERSION
    cached: bool = False


# --------------------------------------------------------------------------- #
# Canonicalization and hashing.
# --------------------------------------------------------------------------- #
def canonical_json(value: Any) -> str:
    """Return a stable JSON string for hashing a state or questions payload."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def state_hash(state: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json(dict(state)))


def questions_hash(questions: Sequence[Mapping[str, Any]]) -> str:
    return sha256_hex(canonical_json([dict(question) for question in questions]))


def cache_key(model_version: str, state: Mapping[str, Any], questions: Sequence[Mapping[str, Any]]) -> str:
    """Return the deterministic disk-cache key for one System One request."""

    return sha256_hex(
        canonical_json(
            {
                "model_version": str(model_version),
                "state_hash": state_hash(state),
                "questions_hash": questions_hash(questions),
            }
        )
    )


# --------------------------------------------------------------------------- #
# Validation.
# --------------------------------------------------------------------------- #
def validate_probabilities(
    probabilities: Mapping[str, Any],
    *,
    expected_keys: Sequence[str] | None = None,
    tolerance: float = PROBABILITY_TOLERANCE,
) -> dict[str, float]:
    """Return a normalized probability vector, or raise ``JevValidationError``.

    Every value must be finite, in ``[0, 1]``, and the vector must sum to ``1.0``
    within ``tolerance``. When ``expected_keys`` is given, the key set must match
    exactly. Message bodies never reach the caller unvalidated.
    """

    if not isinstance(probabilities, Mapping) or not probabilities:
        raise JevValidationError("probabilities must be a non-empty mapping")

    cleaned: dict[str, float] = {}
    for raw_key, raw_value in probabilities.items():
        key = str(raw_key)
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise JevValidationError(f"probability for {key!r} is not a number") from exc
        if value != value or value in (float("inf"), float("-inf")):
            raise JevValidationError(f"probability for {key!r} is not finite")
        if value < 0.0 or value > 1.0:
            raise JevValidationError(f"probability for {key!r} is outside [0, 1]")
        cleaned[key] = value

    if expected_keys is not None:
        expected = {str(key) for key in expected_keys}
        if set(cleaned) != expected:
            missing = sorted(expected - set(cleaned))
            extra = sorted(set(cleaned) - expected)
            raise JevValidationError(
                f"probability keys do not match the question; missing={missing} extra={extra}"
            )

    total = sum(cleaned.values())
    if total <= 0.0 or abs(total - 1.0) > tolerance:
        raise JevValidationError(f"probabilities sum to {total:.4f}, expected 1.0 +/- {tolerance}")

    return {key: value / total for key, value in cleaned.items()}


def validate_confidence(value: Any) -> float:
    """Return a finite confidence in ``[0, 1]``, or raise ``JevValidationError``."""

    if value is None:
        raise JevValidationError("confidence is null")
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise JevValidationError("confidence is not a number") from exc
    if confidence != confidence or confidence in (float("inf"), float("-inf")):
        raise JevValidationError("confidence is not finite")
    if confidence < 0.0 or confidence > 1.0:
        raise JevValidationError(f"confidence {confidence} is outside [0, 1]")
    return confidence


# --------------------------------------------------------------------------- #
# Disk cache.
# --------------------------------------------------------------------------- #
@dataclass
class JevCache:
    """A deterministic on-disk cache keyed by ``(model, state, questions)``."""

    root: Path = field(default_factory=lambda: Path(DEFAULT_CACHE_DIR))

    def __post_init__(self) -> None:
        self.root = Path(self.root)

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - corrupt cache is a miss.
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def put(self, key: str, payload: Mapping[str, Any]) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path_for(key)
        text = json.dumps(dict(payload), indent=2, sort_keys=True) + "\n"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
        return path


# --------------------------------------------------------------------------- #
# HTTP transport.
# --------------------------------------------------------------------------- #
def default_post_json(
    url: str,
    *,
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
    timeout: float,
) -> tuple[int, Any]:
    """POST JSON and return ``(status_code, decoded_body)``.

    Prefers ``httpx``. Falls back to ``urllib`` so the client stays usable with
    the base dependency set. Raises ``HTTPTimeout`` on a timeout.
    """

    if httpx is not None:  # pragma: no cover - exercised only with httpx installed.
        try:
            response = httpx.post(url, json=dict(payload), headers=dict(headers), timeout=timeout)
        except httpx.TimeoutException as exc:
            raise HTTPTimeout(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPTimeout(str(exc)) from exc
        return response.status_code, _decode_body(response.text)

    import socket
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        url,
        data=json.dumps(dict(payload)).encode("utf-8"),
        headers={**dict(headers), "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as handle:  # noqa: S310 - fixed https base.
            return int(handle.status), _decode_body(handle.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return int(exc.code), _decode_body(exc.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise HTTPTimeout(str(exc)) from exc


def _decode_body(text: str) -> Any:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def _error_detail(body: Any) -> str:
    """Return a short, readable error detail from a provider error body."""

    if isinstance(body, Mapping):
        detail = body.get("detail")
        if isinstance(detail, Mapping) and detail.get("message"):
            return str(detail["message"])[:200]
        if isinstance(detail, str):
            return detail[:200]
        if isinstance(detail, list) and detail:
            first = detail[0]
            if isinstance(first, Mapping) and first.get("msg"):
                loc = ".".join(str(part) for part in (first.get("loc") or []))
                return f"{loc}: {first['msg']}"[:200]
    if isinstance(body, str):
        return body[:200]
    return ""


def _number_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _status_is_transient(status: int) -> bool:
    return status in (408, 429) or status >= 500


# --------------------------------------------------------------------------- #
# Provider interface.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DecisionRequest:
    """One System One request: a state plus one or more typed questions."""

    state: Mapping[str, Any]
    questions: tuple[Mapping[str, Any], ...]
    model_version: str
    request_key: str


class Provider:
    """A Jev answer source. Subclasses implement ``available`` and ``answers``."""

    name = "provider"

    def available(self) -> bool:  # pragma: no cover - trivial.
        return True

    def answers(self, request: DecisionRequest) -> dict[str, Any]:  # pragma: no cover - abstract.
        raise NotImplementedError


class PriorProvider(Provider):
    """Deterministic offline fallback. No network, no key."""

    name = PROVIDER_PRIOR

    def available(self) -> bool:
        return True

    def answers(self, request: DecisionRequest) -> dict[str, Any]:
        return {"answers": [_prior_answer(q) for q in request.questions]}


def _prior_answer(question: Mapping[str, Any]) -> dict[str, Any]:
    kind = str(question.get("kind", "choice"))
    keys = list(question.get("choices") or question.get("scale") or [])
    weights = _prior_weights(keys)
    return {
        "id": question.get("id"),
        "probabilities": weights,
        "confidence": PRIOR_CONFIDENCE,
        "kind": kind,
    }


def _prior_weights(keys: Sequence[Any]) -> dict[str, float]:
    known = {str(key): KNOWN_PRIORS[str(key)] for key in keys if str(key) in KNOWN_PRIORS}
    if len(known) == len(keys) and keys:
        total = sum(known.values())
        return {key: value / total for key, value in known.items()}
    if not keys:
        raise JevValidationError("prior fallback needs at least one choice")
    uniform = 1.0 / len(keys)
    return {str(key): uniform for key in keys}


class TypeSafeProvider(Provider):
    """Primary A. TypeSafe System One API over HTTP.

    One forward pass over the ``state`` answers every question in the request.
    The wire model is a TypeSafe model name (``jev-latest``); the server reports
    the resolved concrete version (for example ``jev-1.13.0``) in the response.
    """

    name = PROVIDER_TYPESAFE

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        transport: Callable[..., tuple[int, Any]] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key or load_typesafe_key()
        self.base_url = (base_url or os.environ.get("TYPESAFE_API_BASE") or DEFAULT_TYPESAFE_BASE).rstrip("/")
        self.model = (model or os.environ.get("TYPESAFE_MODEL", "")).strip() or DEFAULT_TYPESAFE_MODEL
        self._transport = transport or default_post_json
        self.timeout = float(timeout)
        self.resolved_model: str = ""

    def available(self) -> bool:
        return bool(self.api_key)

    def answers(self, request: DecisionRequest) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "state": dict(request.state),
            "questions": {
                str(question.get("id")): _api_question(question)
                for question in request.questions
            },
        }
        body = self._post(f"{self.base_url}/v1/systemone", payload)
        if isinstance(body, Mapping) and body.get("model"):
            self.resolved_model = str(body["model"])
        return _typesafe_answers(body, request.questions)

    def _post(self, url: str, payload: Mapping[str, Any]) -> Any:
        """POST to System One and return the decoded body, or raise a provider error."""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            status, body = self._transport(
                url, headers=headers, payload=payload, timeout=self.timeout
            )
        except HTTPTimeout as exc:
            raise JevProviderError(f"typesafe timeout: {exc}", transient=True) from exc
        if status < 200 or status >= 300:
            raise JevProviderError(
                f"typesafe HTTP {status}: {_error_detail(body)}",
                transient=_status_is_transient(status),
            )
        return body


class OpenRouterProvider(Provider):
    """Backup. OpenRouter chat completion. The pinned model is a Jev model."""

    name = PROVIDER_OPENROUTER

    def __init__(
        self,
        *,
        api_key: str | None = None,
        url: str | None = None,
        model: str = DEFAULT_OPENROUTER_MODEL,
        transport: Callable[..., tuple[int, Any]] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "").strip() or None
        self.url = url or DEFAULT_OPENROUTER_URL
        self.model = model
        self._transport = transport or default_post_json
        self.timeout = float(timeout)

    def available(self) -> bool:
        return bool(self.api_key)

    def answers(self, request: DecisionRequest) -> dict[str, Any]:
        prompt = json.dumps(
            {
                "state": dict(request.state),
                "questions": [dict(question) for question in request.questions],
            },
            sort_keys=True,
        )
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Jev, a discrete epistemic router. Answer each question "
                        "as JSON: {\"answers\":[{\"id\":...,\"probabilities\":{...},"
                        "\"confidence\":0..1}]}. Probabilities must sum to 1."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            status, body = self._transport(
                self.url, headers=headers, payload=payload, timeout=self.timeout
            )
        except HTTPTimeout as exc:
            raise JevProviderError(f"openrouter timeout: {exc}", transient=True) from exc
        if status < 200 or status >= 300:
            raise JevProviderError(
                f"openrouter HTTP {status}", transient=_status_is_transient(status)
            )
        content = _openrouter_content(body)
        parsed = _parse_json_block(content)
        return _coerce_answers(parsed)


class MCPProvider(Provider):
    """Primary B. MCP transport, or a pre-populated MCP batch artifact.

    A batch artifact is a JSON object keyed by request key. Each value is a
    canonical ``{"answers": [...]}`` payload. This lets an MCP agent drive the
    batch offline with ``jev_verify`` / ``jev_find`` / ``Choice`` / ``Score``.
    """

    name = PROVIDER_MCP

    def __init__(
        self,
        *,
        batch_path: str | Path | None = None,
        url: str | None = None,
        command: str | None = None,
        transport: Callable[..., tuple[int, Any]] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        env_batch = os.environ.get("JEV_MCP_BATCH")
        self.batch_path = Path(batch_path or env_batch).expanduser() if (batch_path or env_batch) else None
        self.url = url or os.environ.get("JEV_MCP_URL")
        self.command = command or os.environ.get("JEV_MCP_COMMAND")
        self._transport = transport or default_post_json
        self.timeout = float(timeout)
        self._batch: dict[str, Any] | None = None

    def available(self) -> bool:
        return bool(self.batch_path or self.url or self.command)

    def answers(self, request: DecisionRequest) -> dict[str, Any]:
        if self.batch_path is not None:
            batch = self._load_batch()
            if request.request_key in batch:
                return _coerce_answers(batch[request.request_key])
            raise JevProviderError(
                f"mcp batch has no entry for {request.request_key}", transient=False
            )
        if self.url:
            payload = {
                "state": dict(request.state),
                "questions": [dict(question) for question in request.questions],
                "model": request.model_version,
            }
            try:
                status, body = self._transport(self.url, headers={}, payload=payload, timeout=self.timeout)
            except HTTPTimeout as exc:
                raise JevProviderError(f"mcp timeout: {exc}", transient=True) from exc
            if status < 200 or status >= 300:
                raise JevProviderError(f"mcp HTTP {status}", transient=_status_is_transient(status))
            return _coerce_answers(body)
        raise JevProviderError("mcp command transport is not implemented without a batch artifact", transient=False)

    def _load_batch(self) -> dict[str, Any]:
        if self._batch is None:
            if self.batch_path is None or not Path(self.batch_path).is_file():
                raise JevProviderError(f"mcp batch not found: {self.batch_path}", transient=False)
            payload = json.loads(Path(self.batch_path).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise JevProviderError("mcp batch must be a JSON object", transient=False)
            self._batch = payload
        return self._batch


# --------------------------------------------------------------------------- #
# Provider response coercion.
# --------------------------------------------------------------------------- #
def _api_question(question: Mapping[str, Any]) -> dict[str, Any]:
    """Translate an internal question into a TypeSafe System One question."""

    kind = str(question.get("kind") or "choice")
    instructions = str(question.get("question") or question.get("instructions") or "")
    if kind == "score":
        scale = [str(value) for value in (question.get("scale") or [])]
        return {"type": "score", "instructions": instructions, "criteria": scale}
    if kind == "noul":
        return {"type": "noul", "instructions": instructions}
    choices = [str(choice) for choice in (question.get("choices") or [])]
    return {
        "type": "choice",
        "instructions": instructions,
        "criteria": {choice: "" for choice in choices},
    }


def _typesafe_answers(body: Any, questions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Translate a System One response into the client's canonical answer list."""

    if not isinstance(body, Mapping):
        raise JevProviderError("typesafe body is not an object", transient=False)
    answers = body.get("answers")
    if not isinstance(answers, Mapping):
        raise JevProviderError("typesafe answers must be an object keyed by question name", transient=False)

    canonical: list[dict[str, Any]] = []
    for question in questions:
        question_id = str(question.get("id"))
        answer = answers.get(question_id)
        if not isinstance(answer, Mapping):
            raise JevProviderError(f"typesafe response is missing answer {question_id!r}", transient=False)
        kind = str(answer.get("type") or question.get("kind") or "choice")
        if kind == "score":
            scale = list(question.get("scale") or [])
            canonical.append(
                {
                    "id": question_id,
                    "probabilities": _score_probabilities(answer.get("probabilities"), scale),
                    "confidence": answer.get("confidence"),
                    "expected_score": answer.get("score"),
                }
            )
        elif kind == "noul":
            probability = _number_or_none(answer.get("noul"))
            probabilities = (
                {"true": probability, "false": 1.0 - probability}
                if probability is not None
                else {}
            )
            canonical.append(
                {
                    "id": question_id,
                    "probabilities": probabilities,
                    "confidence": answer.get("confidence", 1.0),
                }
            )
        else:
            canonical.append(
                {
                    "id": question_id,
                    "probabilities": answer.get("probabilities", {}),
                    "confidence": answer.get("confidence"),
                    "top_choice": answer.get("choice"),
                }
            )
    return {"answers": canonical}


def _score_probabilities(probabilities: Any, scale: Sequence[Any]) -> dict[str, float]:
    """Remap positional score-level probabilities onto the requested scale keys."""

    if not isinstance(probabilities, Mapping):
        return {}
    ordered = sorted(probabilities, key=_key_order)
    if not scale:
        return {str(key): float(probabilities[key]) for key in ordered}
    remapped: dict[str, float] = {}
    for index, key in enumerate(ordered):
        if index >= len(scale):
            break
        try:
            remapped[str(scale[index])] = float(probabilities[key])
        except (TypeError, ValueError):
            continue
    return remapped


def _key_order(key: Any) -> tuple[int, str]:
    try:
        return (0, f"{int(key):020d}")
    except (TypeError, ValueError):
        return (1, str(key))

def _coerce_answers(body: Any) -> dict[str, Any]:
    if isinstance(body, Mapping) and "answers" in body:
        answers = body["answers"]
    elif isinstance(body, list):
        answers = body
    elif isinstance(body, Mapping):
        answers = [body]
    else:
        raise JevProviderError(f"provider returned an unreadable payload: {type(body).__name__}", transient=False)
    if not isinstance(answers, list) or not answers:
        raise JevProviderError("provider returned no answers", transient=False)
    return {"answers": [dict(answer) for answer in answers]}


def _openrouter_content(body: Any) -> str:
    if not isinstance(body, Mapping):
        raise JevProviderError("openrouter body is not an object", transient=False)
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise JevProviderError("openrouter body has no choices", transient=False)
    first = choices[0]
    if not isinstance(first, Mapping):
        raise JevProviderError("openrouter choice is not an object", transient=False)
    message = first.get("message")
    if isinstance(message, Mapping):
        content = message.get("content")
        if isinstance(content, str):
            return content
    if isinstance(first.get("text"), str):
        return str(first["text"])
    raise JevProviderError("openrouter choice has no message content", transient=False)


def _parse_json_block(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
    try:
        return json.loads(stripped)
    except ValueError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(stripped[start : end + 1])
            except ValueError as exc:
                raise JevProviderError("openrouter content is not JSON", transient=False) from exc
        raise JevProviderError("openrouter content is not JSON", transient=False)


# --------------------------------------------------------------------------- #
# Key loading.
# --------------------------------------------------------------------------- #
def load_typesafe_key(key_path: str | Path | None = None) -> str | None:
    """Return the TypeSafe key from the environment or the key file."""

    for name in ("TYPESAFE_API_KEY", "TYPESAFE_AI_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    path = Path(key_path or DEFAULT_KEY_PATH).expanduser()
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return None


# --------------------------------------------------------------------------- #
# Client.
# --------------------------------------------------------------------------- #
@dataclass
class JevClientConfig:
    """Resolved client settings. ``provider`` is the requested routing mode."""

    provider: str = PROVIDER_AUTO
    fallback: str = FALLBACK_PRIOR
    model_version: str = DEFAULT_MODEL_VERSION
    timeout: float = DEFAULT_TIMEOUT
    cache_dir: Path = field(default_factory=lambda: Path(DEFAULT_CACHE_DIR))
    use_cache: bool = True
    enabled: bool = True

    def __post_init__(self) -> None:
        self.cache_dir = Path(self.cache_dir)
        if self.provider not in PROVIDERS:
            raise ValueError(f"provider must be one of {PROVIDERS}")


class TieredJevClient:
    """Route a typed question through the provider tiers and cache the answer."""

    def __init__(
        self,
        config: JevClientConfig | None = None,
        *,
        providers: Sequence[Provider] | None = None,
        cache: JevCache | None = None,
        transport: Callable[..., tuple[int, Any]] | None = None,
    ) -> None:
        self.config = config or JevClientConfig()
        self.transport = transport
        self.cache = cache if cache is not None else JevCache(self.config.cache_dir)
        self.providers = list(providers) if providers is not None else self._build_providers()
        self.failover_log: list[str] = []

    # -- provider construction -------------------------------------------- #
    def _build_providers(self) -> list[Provider]:
        typesafe = TypeSafeProvider(transport=self.transport, timeout=self.config.timeout)
        mcp = MCPProvider(transport=self.transport, timeout=self.config.timeout)
        openrouter = OpenRouterProvider(transport=self.transport, timeout=self.config.timeout)
        prior = PriorProvider()

        selected = self.config.provider
        tiers: list[Provider] = []
        if not self.config.enabled or selected == PROVIDER_PRIOR:
            return [prior]

        if selected in (PROVIDER_AUTO, PROVIDER_TYPESAFE):
            tiers.append(typesafe)
        if selected in (PROVIDER_AUTO, PROVIDER_MCP):
            tiers.append(mcp)
        if selected in (PROVIDER_AUTO, PROVIDER_MCP, PROVIDER_TYPESAFE, PROVIDER_OPENROUTER):
            tiers.append(openrouter)
        if self.config.fallback == FALLBACK_PRIOR:
            tiers.append(prior)
        # Drop unconfigured tiers, but keep the deterministic prior if requested.
        return [tier for tier in tiers if tier.available()]

    # -- public API -------------------------------------------------------- #
    def jev_choice(
        self,
        state: Mapping[str, Any],
        question: str,
        choices: Sequence[str],
        *,
        question_id: str | None = None,
    ) -> ChoiceResult:
        results = self.jev_choice_many(
            state,
            [{"question": question, "choices": list(choices), "id": question_id}],
        )
        return results[0]

    def jev_choice_many(
        self,
        state: Mapping[str, Any],
        questions: Sequence[Mapping[str, Any]],
    ) -> list[ChoiceResult]:
        prepared = [self._prepare_question(q, kind="choice") for q in questions]
        request = self._build_request(state, prepared)
        payload, provider_used, cached = self._resolve(request)
        results: list[ChoiceResult] = []
        for question, answer in zip(prepared, _ordered_answers(payload, prepared), strict=True):
            probabilities = validate_probabilities(
                answer.get("probabilities", {}),
                expected_keys=[str(choice) for choice in question["choices"]],
            )
            confidence = validate_confidence(answer.get("confidence"))
            top_choice = str(answer.get("top_choice") or max(probabilities, key=probabilities.get))
            results.append(
                ChoiceResult(
                    probabilities=probabilities,
                    top_choice=top_choice,
                    confidence=confidence,
                    provider_used=answer.get("provider_used", provider_used),
                    model_version=self.config.model_version,
                    cached=cached,
                )
            )
        return results

    def jev_score(
        self,
        state: Mapping[str, Any],
        question: str,
        scale: Sequence[int | str],
        *,
        question_id: str | None = None,
    ) -> ScoreResult:
        prepared = [self._prepare_question({"question": question, "scale": list(scale), "id": question_id}, kind="score")]
        request = self._build_request(state, prepared)
        payload, provider_used, cached = self._resolve(request)
        answer = _ordered_answers(payload, prepared)[0]
        probabilities = validate_probabilities(
            answer.get("probabilities", {}),
            expected_keys=[str(value) for value in scale],
        )
        confidence = validate_confidence(answer.get("confidence"))
        expected = answer.get("expected_score")
        if expected is None:
            expected = _expected_score(probabilities, scale)
        try:
            expected_float = float(expected)
        except (TypeError, ValueError) as exc:
            raise JevValidationError("expected_score is not a number") from exc
        if expected_float != expected_float:
            raise JevValidationError("expected_score is not finite")
        return ScoreResult(
            probabilities=probabilities,
            expected_score=expected_float,
            confidence=confidence,
            provider_used=answer.get("provider_used", provider_used),
            model_version=self.config.model_version,
            cached=cached,
        )

    async def jev_choice_batch(
        self,
        items: Sequence[tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]],
        *,
        max_concurrency: int = MAX_CONCURRENCY,
    ) -> list[list[ChoiceResult]]:
        """Answer many ``(state, questions)`` items with bounded concurrency."""

        semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))

        async def run(state: Mapping[str, Any], questions: Sequence[Mapping[str, Any]]) -> list[ChoiceResult]:
            async with semaphore:
                return await asyncio.to_thread(self.jev_choice_many, state, questions)

        return await asyncio.gather(*(run(state, questions) for state, questions in items))

    def close(self) -> None:  # pragma: no cover - symmetry for callers.
        return None

    # -- internals --------------------------------------------------------- #
    def _prepare_question(self, question: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
        prepared = dict(question)
        prepared["kind"] = kind
        if prepared.get("id") is None:
            prepared["id"] = sha256_hex(canonical_json(prepared))[:12]
        if kind == "choice":
            choices = prepared.get("choices")
            if not choices:
                raise JevValidationError("choice question needs at least one choice")
            prepared["choices"] = [str(choice) for choice in choices]
        else:
            scale = prepared.get("scale")
            if not scale:
                raise JevValidationError("score question needs at least one scale value")
            prepared["scale"] = [str(value) for value in scale]
        prepared["question"] = str(prepared.get("question", ""))
        return prepared

    def _build_request(
        self, state: Mapping[str, Any], questions: Sequence[Mapping[str, Any]]
    ) -> DecisionRequest:
        key = cache_key(self.config.model_version, state, questions)
        return DecisionRequest(
            state=dict(state),
            questions=tuple(dict(question) for question in questions),
            model_version=self.config.model_version,
            request_key=key,
        )

    def _resolve(self, request: DecisionRequest) -> tuple[dict[str, Any], str, bool]:
        if self.config.use_cache:
            cached = self.cache.get(request.request_key)
            if cached is not None and _cache_entry_is_usable(cached):
                return (
                    {"answers": cached["answers"]},
                    str(cached.get("provider_used", "cache")),
                    True,
                )

        last_error: JevError | None = None
        validation_failed = False
        for provider in self.providers:
            if not provider.available():
                continue
            try:
                payload = provider.answers(request)
            except JevProviderError as exc:
                self._log_failover(request, provider, str(exc), transient=exc.transient)
                last_error = exc
                continue
            try:
                checked = _validate_payload(payload, request.questions, provider.name)
            except JevValidationError as exc:
                validation_failed = True
                self._log_failover(request, provider, f"validation: {exc}", transient=False)
                last_error = exc
                continue
            self._store(request, checked, provider.name)
            return {"answers": checked["answers"]}, provider.name, False

        # Every configured provider failed. Fail closed, or apply the prior.
        if self.config.fallback == FALLBACK_PRIOR or not self.config.enabled:
            prior = PriorProvider()
            payload = _validate_payload(prior.answers(request), request.questions, prior.name)
            return {"answers": payload["answers"]}, prior.name, False

        if validation_failed:
            raise JevValidationError(
                f"all providers returned malformed payloads for request {request.request_key}"
            ) from last_error
        raise JevUnavailableError(
            f"no Jev provider is configured or reachable for request {request.request_key}"
        ) from last_error

    def _store(self, request: DecisionRequest, payload: Mapping[str, Any], provider_used: str) -> None:
        if not self.config.use_cache or provider_used == PROVIDER_PRIOR:
            return
        self.cache.put(
            request.request_key,
            {
                "model_version": self.config.model_version,
                "state_hash": state_hash(request.state),
                "questions_hash": questions_hash(request.questions),
                "provider_used": provider_used,
                "answers": list(payload["answers"]),
            },
        )

    def _log_failover(
        self, request: DecisionRequest, provider: Provider, reason: str, *, transient: bool
    ) -> None:
        mode = "transient" if transient else "hard"
        message = f"jev provider failover ({mode}): {provider.name} -> backup; reason: {reason}"
        self.failover_log.append(message)
        LOGGER.warning(message)


def _cache_entry_is_usable(entry: Mapping[str, Any]) -> bool:
    answers = entry.get("answers")
    return isinstance(answers, list) and bool(answers)


def _ordered_answers(payload: Mapping[str, Any], questions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    answers = list(payload.get("answers", []))
    by_id = {str(answer.get("id")): answer for answer in answers if answer.get("id") is not None}
    ordered: list[dict[str, Any]] = []
    for index, question in enumerate(questions):
        question_id = str(question.get("id"))
        if question_id in by_id:
            ordered.append(by_id[question_id])
        elif index < len(answers):
            ordered.append(answers[index])
        else:
            raise JevValidationError(f"missing answer for question {question_id}")
    return ordered


def _validate_payload(
    payload: Mapping[str, Any],
    questions: Sequence[Mapping[str, Any]],
    provider_used: str,
) -> dict[str, Any]:
    answers = payload.get("answers")
    if not isinstance(answers, list) or len(answers) != len(questions):
        raise JevValidationError("answer count does not match question count")
    checked: list[dict[str, Any]] = []
    for question, answer in zip(questions, answers, strict=True):
        if not isinstance(answer, Mapping):
            raise JevValidationError("answer is not an object")
        expected_keys = [str(key) for key in (question.get("choices") or question.get("scale") or [])]
        probabilities = validate_probabilities(answer.get("probabilities", {}), expected_keys=expected_keys)
        confidence = validate_confidence(answer.get("confidence"))
        record = {
            "id": answer.get("id", question.get("id")),
            "probabilities": probabilities,
            "confidence": confidence,
            "provider_used": provider_used,
        }
        if question.get("kind") == "score":
            scale = list(question.get("scale") or [])
            record["expected_score"] = float(answer.get("expected_score", _expected_score(probabilities, scale)))
        checked.append(record)
    return {"answers": checked}


def _expected_score(probabilities: Mapping[str, float], scale: Sequence[int | str]) -> float:
    total = 0.0
    for index, value in enumerate(scale):
        weight = float(probabilities.get(str(value), 0.0))
        total += weight * _scale_value(value, index)
    return float(total)


def _scale_value(value: Any, index: int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(index)


# --------------------------------------------------------------------------- #
# Convenience builders.
# --------------------------------------------------------------------------- #
def build_jev_client(
    *,
    provider: str = PROVIDER_AUTO,
    fallback: str = FALLBACK_PRIOR,
    enabled: bool = True,
    model_version: str = DEFAULT_MODEL_VERSION,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
    transport: Callable[..., tuple[int, Any]] | None = None,
    providers: Sequence[Provider] | None = None,
) -> TieredJevClient:
    """Build a tiered client from CLI-style options."""

    config = JevClientConfig(
        provider=provider,
        fallback=fallback,
        model_version=model_version,
        enabled=enabled,
        use_cache=use_cache,
        cache_dir=Path(cache_dir) if cache_dir is not None else Path(DEFAULT_CACHE_DIR),
    )
    return TieredJevClient(config, providers=providers, transport=transport)
