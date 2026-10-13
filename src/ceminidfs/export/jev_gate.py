"""Jev pre-lock gate. The gate marks. It does not change a lineup.

Five checks, one Jev primitive each:

1. status      Noul   is a rostered Q/D player, or a player at the exposure
                      cap, expected to be active?
2. QB starter  Noul   is a rostered QB the confirmed starter?
3. injection   Score  is a document that feeds the gate safe to follow?
4. late swap   Choice which legal alternative answers a late-swap alert row?
5. cash claim  Noul   does the recap cash count stand on a standings screenshot?

Thresholds live in this file, not in Jev. The gate writes
``jev_gate_report.csv`` beside the other review reports. The operator reads
it. The operator may then exclude a player, cap exposure, or late-swap. Nothing
in this module writes a lineup, a projection, or an ownership number.

Every Jev failure blocks the gate and asks the operator.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ceminidfs.integrations.jev import (
    FIND,
    SCREEN,
    VERIFY,
    JevClient,
    JevError,
)

from .normalize import normalize_site
from .review_reports import load_player_index, parse_lineup_csv

JEV_GATE_NAME = "jev_gate_report.csv"
JEV_GATE_HEADER = [
    "player",
    "question",
    "primitive",
    "result",
    "confidence",
    "action",
    "evidence_ref",
]

# A verdict stands only at or above this confidence. Below it, a person looks.
NOUL_CONFIDENCE_FLOOR = 0.80
# Above this probability the claim is treated as supported.
NOUL_HIGH = 0.5
# The injection rubric. block at or above 0.75, review at or above 0.25.
SCREEN_BLOCK_AT = 0.75
SCREEN_REVIEW_AT = 0.25
# More alternatives than this do not change the operator's choice.
MAX_ALTERNATIVES = 8

Q_OR_D_STATUS = frozenset({"Q", "QUESTIONABLE", "D", "DOUBTFUL"})

STATUS_EVIDENCE_REF = "status_packet"
PLAYERS_EVIDENCE_REF = "players_csv"
LATE_SWAP_EVIDENCE_REF = "late_swap_alert_report.csv"
CASH_EVIDENCE_REF = "standings_screenshot"


@dataclass(frozen=True)
class JevGateRow:
    player: str
    question: str
    primitive: str
    result: str
    confidence: str
    action: str
    evidence_ref: str

    def as_row(self) -> list[str]:
        return [
            self.player,
            self.question,
            self.primitive,
            self.result,
            self.confidence,
            self.action,
            self.evidence_ref,
        ]


@dataclass
class JevGateResult:
    rows: list[JevGateRow] = field(default_factory=list)
    blocked: bool = False
    blocked_reason: str = ""
    path: Path | None = None

    def counts(self) -> dict[str, int]:
        tally = {action: 0 for action in ("pass", "flag", "review", "block")}
        for row in self.rows:
            tally[row.action] = tally.get(row.action, 0) + 1
        return tally

    def low_confidence(self) -> int:
        return sum(1 for row in self.rows if row.action == "review")

    def summary(self) -> str:
        tally = self.counts()
        return (
            f"jev gate: pass={tally['pass']} flag={tally['flag']} "
            f"review={tally['review']} block={tally['block']} "
            f"low_confidence={self.low_confidence()}"
        )


def is_q_or_d(status: str | None) -> bool:
    """Return True for a Questionable or Doubtful status string."""

    text = str(status or "").strip().upper()
    if not text:
        return False
    return text in Q_OR_D_STATUS or text.startswith("DOUBTFUL")


def _by_display_name(players: Mapping[str, Any]) -> dict[str, Any]:
    """Index PlayerMeta by its display name.

    ``load_player_index`` keys by folded name and by player id. A lineup cell
    resolves to the display name, so the gate needs this third view.
    """

    index: dict[str, Any] = {}
    for meta in players.values():
        name = getattr(meta, "name", "")
        if name and name not in index:
            index[name] = meta
    return index


def _book_names(lineups: Sequence[Sequence[tuple[str, str]]]) -> list[str]:
    seen: dict[str, None] = {}
    for seats in lineups:
        for _slot, name in seats:
            key = str(name).strip()
            if key:
                seen.setdefault(key, None)
    return list(seen)


def _exposure_counts(lineups: Sequence[Sequence[tuple[str, str]]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for seats in lineups:
        for _slot, name in seats:
            key = str(name).strip()
            counts[key] = counts.get(key, 0) + 1
    return counts


def status_claim(name: str, team: str, game: str, date: str | None) -> str:
    """Return one atomic Noul question for a player's availability."""

    where = f"for {team}" if team else ""
    matchup = f" in {game}" if game else ""
    when = f" on {date}" if date else ""
    parts = " ".join(part for part in (where, matchup, when) if part)
    return f"{name} is expected to be active {parts}.".replace("  ", " ").strip()


def starter_claim(name: str, team: str) -> str:
    """Return one atomic Noul question for a QB depth-chart spot."""

    return f"{name} is the confirmed starter for {team}.".replace("  ", " ").strip()


def build_status_packet(
    players: Mapping[str, Any],
    names: Iterable[str],
    *,
    date: str | None = None,
    extra: str | None = None,
) -> str:
    """Return the status packet text that becomes the evidence."""

    lines = ["Week status packet" + (f" ({date})" if date else "")]
    for name in names:
        meta = players.get(name)
        if meta is None:
            lines.append(f"{name} | status unknown")
            continue
        lines.append(
            " | ".join(
                part
                for part in (
                    meta.name or name,
                    meta.position,
                    meta.team,
                    meta.game_raw,
                    f"injury: {meta.injury}" if meta.injury else "",
                )
                if part
            )
        )
    if extra and extra.strip():
        lines.append("Inactive report:")
        lines.append(extra.strip())
    return "\n".join(lines)


def _verify_action(verdict: str, noul: float | None, confidence: float | None) -> str:
    """Map one Noul answer to a gate action. Thresholds live here.

    Only a contradicted claim can flag. ``unsupported`` means the evidence
    does not address the claim. That is silence, not evidence against it.
    Silence routes to the operator, because a run that flags every player the
    packet is quiet about is worse than no gate at all.
    """

    if verdict in {"unsupported", "unknown"} or noul is None:
        return "review"
    if confidence is None or confidence < NOUL_CONFIDENCE_FLOOR:
        return "review"
    return "pass" if noul >= NOUL_HIGH else "flag"


def _relation_noul(result: Mapping[str, Any]) -> tuple[float | None, float | None]:
    """Return ``(noul, confidence)`` from a jev_verify result row."""

    confidence = result.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    probabilities = result.get("probabilities")
    noul: float | None = None
    if isinstance(probabilities, Mapping):
        value = probabilities.get("supports")
        try:
            noul = float(value) if value is not None else None
        except (TypeError, ValueError):
            noul = None
    if noul is None:
        verdict = str(result.get("verdict", "")).lower()
        if verdict == "verified":
            noul = 1.0
        elif verdict == "contradicted":
            noul = 0.0
    return noul, confidence


def _format_confidence(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else ""


def _format_noul(verdict: str, noul: float | None) -> str:
    return f"{verdict} noul={noul:.2f}" if noul is not None else verdict


def _legal_alternatives(
    players: Mapping[str, Any],
    name: str,
    *,
    limit: int = MAX_ALTERNATIVES,
) -> list[dict[str, str]]:
    """Return healthy players in the same game and position as ``name``."""

    meta = players.get(name)
    if meta is None or not meta.game_raw:
        return []
    candidates: list[tuple[float, dict[str, str]]] = []
    for other in players.values():
        if other.name == name or not other.name:
            continue
        if is_q_or_d(other.injury):
            continue
        if other.game_raw != meta.game_raw:
            continue
        if other.position != meta.position:
            continue
        try:
            projection = float(other.projection)
        except (TypeError, ValueError):
            projection = 0.0
        candidates.append(
            (
                projection,
                {"id": other.name, "text": f"{other.name} ({other.position}, {other.team})"},
            )
        )
    candidates.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [item[1] for item in candidates[:limit]]


def _read_alerts(lineups_csv: Path) -> list[dict[str, str]]:
    """Read ``late_swap_alert_report.csv`` beside the lineup file."""

    alert_path = lineups_csv.parent / "late_swap_alert_report.csv"
    if not alert_path.is_file():
        return []
    with alert_path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def run_jev_gate(
    lineups_csv: str | Path,
    players_csv: str | Path,
    *,
    client: JevClient,
    site: str = "fanduel",
    out_dir: str | Path | None = None,
    date: str | None = None,
    exposure_cap: float | None = 0.20,
    status_doc: str | None = None,
    standings: str | None = None,
    cash_claim: str | None = None,
    enable_late_swap: bool = True,
    enable_cash: bool = False,
) -> JevGateResult:
    """Run the gate and write ``jev_gate_report.csv``.

    Every Jev error blocks the gate. The report is still written, so the
    operator sees the failure and the scope of the check.
    """

    lineups_file = Path(lineups_csv)
    players_file = Path(players_csv)
    if not lineups_file.is_file():
        raise FileNotFoundError(f"Lineups CSV not found: {lineups_file}")
    if not players_file.is_file():
        raise FileNotFoundError(f"Players CSV not found: {players_file}")

    site_key = normalize_site(site)
    index = load_player_index(players_file)
    lineups = parse_lineup_csv(lineups_file, site=site_key, players=index)
    players = _by_display_name(index)
    book = _book_names(lineups)
    counts = _exposure_counts(lineups)
    book_size = len(lineups) or 1

    # One question per player. A Q/D player and an over-cap player share it.
    question_names: list[str] = []
    for name in book:
        meta = players.get(name)
        over_cap = (
            exposure_cap is not None and counts.get(name, 0) / book_size >= float(exposure_cap)
        )
        if (meta is not None and is_q_or_d(meta.injury)) or over_cap:
            question_names.append(name)

    result = JevGateResult()

    def finish() -> JevGateResult:
        dest = Path(out_dir) if out_dir is not None else lineups_file.parent
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / JEV_GATE_NAME
        _write_report(path, result.rows)
        result.path = path
        return result

    def block(reason: str, *, player: str = "(gate)", question: str = "jev gate") -> JevGateResult:
        result.blocked = True
        result.blocked_reason = reason
        result.rows.append(
            JevGateRow(
                player=player,
                question=question,
                primitive="-",
                result=f"blocked: {reason}",
                confidence="",
                action="block",
                evidence_ref="",
            )
        )
        return finish()

    packet = build_status_packet(
        players,
        question_names,
        date=date,
        extra=status_doc,
    )

    # 1. Injection screen. A blocked document does not enter the gate.
    try:
        screen = client.screen(
            packet,
            purpose="Check a DFS player status packet before it enters the lineup build",
            block_at=SCREEN_BLOCK_AT,
            review_at=SCREEN_REVIEW_AT,
        )
    except JevError as exc:
        return block(str(exc), player="(status_packet)", question="injection screen")
    screen_action = _screen_action(screen)
    probabilities = screen.get("probabilities") or {}
    injection = probabilities.get("injection") if isinstance(probabilities, Mapping) else None
    result.rows.append(
        JevGateRow(
            player="(status_packet)",
            question="injection screen: status packet",
            primitive=SCREEN,
            result=screen_action,
            confidence=_format_confidence(_as_float(injection)),
            action=screen_action,
            evidence_ref=STATUS_EVIDENCE_REF,
        )
    )
    if screen_action == "block":
        result.blocked = True
        result.blocked_reason = "status packet failed the injection screen"
        return finish()

    # 2. Status and QB starter gates (Noul). One call for every question.
    #    Jev evaluates questions in parallel against the same state, so the
    #    whole slate goes in one request.
    claims: list[str] = []
    owners: list[tuple[str, str]] = []
    for name in question_names:
        meta = players.get(name)
        claims.append(
            status_claim(
                name,
                meta.team if meta is not None else "",
                meta.game_raw if meta is not None else "",
                date,
            )
        )
        owners.append((name, STATUS_EVIDENCE_REF))
    for name in book:
        meta = players.get(name)
        if meta is None or meta.position.upper() != "QB":
            continue
        claims.append(starter_claim(name, meta.team))
        owners.append((name, PLAYERS_EVIDENCE_REF))

    if claims:
        try:
            verified = client.verify(claims, packet)
        except JevError as exc:
            return block(str(exc))
        rows = verified.get("results")
        if not isinstance(rows, list) or len(rows) != len(claims):
            return block("jev returned a malformed verify payload")
        for (name, ref), claim, entry in zip(owners, claims, rows):
            if not isinstance(entry, Mapping):
                return block("jev returned a malformed verify row")
            verdict = str(entry.get("verdict", "unknown")).lower()
            noul, confidence = _relation_noul(entry)
            result.rows.append(
                JevGateRow(
                    player=name,
                    question=claim,
                    primitive=VERIFY,
                    result=_format_noul(verdict, noul),
                    confidence=_format_confidence(confidence),
                    action=_verify_action(verdict, noul, confidence),
                    evidence_ref=ref,
                )
            )

    # 3. Late-swap input (Choice). Marks only.
    if enable_late_swap:
        for alert in _read_alerts(lineups_file):
            name = str(alert.get("player", "")).strip()
            if not name:
                continue
            alternatives = _legal_alternatives(players, name)
            if not alternatives:
                result.rows.append(
                    JevGateRow(
                        player=name,
                        question=f"Which legal alternative replaces {name}?",
                        primitive=FIND,
                        result="no legal alternative in this game and position",
                        confidence="",
                        action="review",
                        evidence_ref=LATE_SWAP_EVIDENCE_REF,
                    )
                )
                continue
            try:
                found = client.find(
                    f"Which healthy {players[name].position} in this game replaces {name}?",
                    alternatives,
                    top_k=1,
                )
            except JevError as exc:
                return block(str(exc), player=name, question="late-swap choice")
            top = found.get("top") or []
            first = top[0] if isinstance(top, list) and top else {}
            choice_id = str(first.get("id", "")) if isinstance(first, Mapping) else ""
            probability = _as_float(first.get("probability")) if isinstance(first, Mapping) else None
            exists = str(found.get("exists_verdict", "")).strip()
            label = choice_id or "none"
            result.rows.append(
                JevGateRow(
                    player=name,
                    question=f"Which legal alternative replaces {name}?",
                    primitive=FIND,
                    result=f"{label} ({exists or 'unknown'})",
                    confidence=_format_confidence(probability),
                    action="review",
                    evidence_ref=LATE_SWAP_EVIDENCE_REF,
                )
            )

    # 4. Cash-set claim (Noul). No screenshot means the claim stays UNKNOWN.
    if enable_cash and cash_claim:
        if not standings or not standings.strip():
            result.rows.append(
                JevGateRow(
                    player="(recap)",
                    question=cash_claim,
                    primitive=VERIFY,
                    result="UNKNOWN",
                    confidence="",
                    action="review",
                    evidence_ref=CASH_EVIDENCE_REF,
                )
            )
        else:
            try:
                verified = client.verify([cash_claim], standings)
            except JevError as exc:
                return block(str(exc), player="(recap)", question="cash claim")
            rows = verified.get("results")
            entry = rows[0] if isinstance(rows, list) and rows else {}
            if not isinstance(entry, Mapping):
                return block("jev returned a malformed verify row", player="(recap)")
            verdict = str(entry.get("verdict", "unknown")).lower()
            noul, confidence = _relation_noul(entry)
            result.rows.append(
                JevGateRow(
                    player="(recap)",
                    question=cash_claim,
                    primitive=VERIFY,
                    result=_format_noul(verdict, noul),
                    confidence=_format_confidence(confidence),
                    action=_verify_action(verdict, noul, confidence),
                    evidence_ref=CASH_EVIDENCE_REF,
                )
            )

    return finish()


def write_blocked_report(
    out_dir: str | Path | None,
    lineups_csv: str | Path,
    reason: str,
) -> Path:
    """Write the artifact for a gate that never reached Jev."""

    dest = Path(out_dir) if out_dir is not None else Path(lineups_csv).parent
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / JEV_GATE_NAME
    _write_report(
        path,
        [
            JevGateRow(
                player="(gate)",
                question="jev gate",
                primitive="-",
                result=f"blocked: {reason}",
                confidence="",
                action="block",
                evidence_ref="",
            )
        ],
    )
    return path


def _screen_action(screen: Mapping[str, Any]) -> str:
    """Map a jev_screen recommendation to one of the four gate actions."""

    recommendation = screen.get("recommendation")
    action = ""
    if isinstance(recommendation, Mapping):
        action = str(recommendation.get("action", "")).strip().lower()
    if action == "block":
        return "block"
    if action == "review":
        return "review"
    if action in {"pass", "skip"}:
        # skip means the text is not worth reading, not that it is unsafe.
        return "pass" if action == "pass" else "review"
    return "review"


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _write_report(path: Path, rows: Sequence[JevGateRow]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(JEV_GATE_HEADER)
        for row in rows:
            writer.writerow(row.as_row())
    return path
