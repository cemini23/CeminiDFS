"""Injury and role regime routing for the simulation mixture (Integration A).

The router is split in two:

- Jev (``Choice``) classifies a player into one of four mutually exclusive
  regimes from a compact, categorical state.
- Python turns those four weights into a three-component active-game mixture and
  samples it. Jev never samples and never does arithmetic on the draws.

The only bypass is a healthy player with ``FP/FP/FP`` and no role note. That
player never touches the network: the router returns a fixed healthy prior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ceminidfs.jev_client import ChoiceResult, TieredJevClient

REGIME_ORDER = (
    "full_role",
    "snap_count_decoy",
    "in_game_reaggravation_exit",
    "pre_game_inactive",
)
ACTIVE_REGIMES = REGIME_ORDER[:3]

# Healthy baseline. FP/FP/FP with no role note bypasses the network and uses this.
HEALTHY_PRIOR: dict[str, float] = {
    "full_role": 0.92,
    "snap_count_decoy": 0.05,
    "in_game_reaggravation_exit": 0.03,
    "pre_game_inactive": 0.00,
}

INACTIVE_RISK_THRESHOLD = 0.50

REGIME_QUESTION = (
    "Given this player's injury report and practice status, which single "
    "availability and role regime is most likely for the upcoming game?"
)

_Q_OR_D = {"Q", "QUESTIONABLE", "D", "DOUBTFUL", "OUT", "O"}
_PRACTICE_LIMITED = {"LIMITED PARTICIPATION IN PRACTICE", "LP"}
_PRACTICE_DNP = {"DID NOT PARTICIPATE IN PRACTICE", "DNP"}


@dataclass
class RegimeRouting:
    """The router output for one player. ``probabilities`` sum to one."""

    player_id: str
    probabilities: dict[str, float]
    top_state: str
    confidence: float
    provider_used: str
    inactive_risk: bool = False
    state: dict[str, Any] = field(default_factory=dict)

    def active_weights(self) -> tuple[float, float, float]:
        return active_weights(self.probabilities)


def active_weights(probabilities: Mapping[str, float]) -> tuple[float, float, float]:
    """Renormalize the three active regimes over ``1 - p_inactive``."""

    p_inactive = float(probabilities.get("pre_game_inactive", 0.0))
    remaining = max(0.0, 1.0 - p_inactive)
    if remaining <= 0.0:
        return (1.0, 0.0, 0.0)
    return (
        float(probabilities.get("full_role", 0.0)) / remaining,
        float(probabilities.get("snap_count_decoy", 0.0)) / remaining,
        float(probabilities.get("in_game_reaggravation_exit", 0.0)) / remaining,
    )


def inactive_risk(probabilities: Mapping[str, float]) -> bool:
    return float(probabilities.get("pre_game_inactive", 0.0)) > INACTIVE_RISK_THRESHOLD


def is_injury_designated(row: Mapping[str, Any]) -> bool:
    """Return True on a Q/D report, or a DNP/LP practice day, or a role note."""

    report = _norm(row.get("report_status") or row.get("injury_status"))
    practice = _norm(row.get("practice_status"))
    note = _norm(row.get("depth_chart_notes") or row.get("role_note"))
    if report in _Q_OR_D:
        return True
    if practice in _PRACTICE_LIMITED or practice in _PRACTICE_DNP:
        return True
    if bool(row.get("returning_from_ir")):
        return True
    return bool(note)


def build_regime_state(
    row: Mapping[str, Any],
    *,
    vegas_implied_total: Any = None,
    weeks_since_injury: Any = None,
    depth_chart_notes: Any = None,
) -> dict[str, Any]:
    """Build the compact categorical state the router reads."""

    practice = practice_sequence(row)
    body_part = (
        row.get("report_primary_injury")
        or row.get("practice_primary_injury")
        or row.get("injury_body_part")
        or ""
    )
    notes = depth_chart_notes if depth_chart_notes is not None else row.get("depth_chart_notes")
    return {
        "position": _norm(row.get("position")),
        "practice_wed_thu_fri": practice,
        "injury_body_part": _norm(body_part),
        "weeks_since_injury": _clean_int(weeks_since_injury if weeks_since_injury is not None else row.get("weeks_since_injury")),
        "depth_chart_notes": str(notes or "").strip()[:180],
        "vegas_implied_total": _clean_float(vegas_implied_total),
        "report_status": _norm(row.get("report_status") or row.get("injury_status")),
    }


def practice_sequence(row: Mapping[str, Any]) -> str:
    """Return a ``W/T/F`` practice token such as ``LP/FP/DNP``.

    The nflverse injuries cache carries one practice_status per week, so the same
    token is used for each day. An explicit ``practice_wed_thu_fri`` wins.
    """

    explicit = str(row.get("practice_wed_thu_fri") or "").strip()
    if explicit:
        return explicit.upper()
    token = _practice_token(row.get("practice_status"))
    if not token:
        return ""
    return f"{token}/{token}/{token}"


def route_regimes(
    client: TieredJevClient | None,
    rows: Sequence[Mapping[str, Any]],
    *,
    id_key: str = "player_id",
    implied_totals: Mapping[str, Any] | None = None,
) -> dict[str, RegimeRouting]:
    """Route every row to a regime distribution. Healthy rows bypass the network."""

    totals = implied_totals or {}
    routings: dict[str, RegimeRouting] = {}
    for row in rows:
        player_id = str(row.get(id_key) or row.get("gsis_id") or row.get("player_name") or "").strip()
        if not player_id:
            continue
        team = str(row.get("team") or "").upper()
        implied = totals.get(team) if team else None
        if not is_injury_designated(row):
            routings[player_id] = _healthy_routing(player_id)
            continue
        if client is None:
            routings[player_id] = _prior_routing(player_id, row, implied)
            continue
        state = build_regime_state(row, vegas_implied_total=implied)
        result: ChoiceResult = client.jev_choice(state, REGIME_QUESTION, list(REGIME_ORDER))
        routings[player_id] = RegimeRouting(
            player_id=player_id,
            probabilities=dict(result.probabilities),
            top_state=result.top_choice,
            confidence=result.confidence,
            provider_used=result.provider_used,
            inactive_risk=inactive_risk(result.probabilities),
            state=state,
        )
    return routings


def regime_weight_lookup(routings: Mapping[str, RegimeRouting]) -> dict[str, tuple[float, float, float]]:
    """Return the ``{player_id: (w1, w2, w3)}`` mapping the sampler reads."""

    return {player_id: routing.active_weights() for player_id, routing in routings.items()}


def _healthy_routing(player_id: str) -> RegimeRouting:
    return RegimeRouting(
        player_id=player_id,
        probabilities=dict(HEALTHY_PRIOR),
        top_state="full_role",
        confidence=1.0,
        provider_used="bypass",
        inactive_risk=False,
        state={},
    )


def _prior_routing(player_id: str, row: Mapping[str, Any], implied: Any) -> RegimeRouting:
    from ceminidfs.jev_client import REGIME_PRIOR

    probabilities = {regime: REGIME_PRIOR[regime] for regime in REGIME_ORDER}
    return RegimeRouting(
        player_id=player_id,
        probabilities=probabilities,
        top_state="full_role",
        confidence=0.55,
        provider_used="prior",
        inactive_risk=inactive_risk(probabilities),
        state=build_regime_state(row, vegas_implied_total=implied),
    )


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _practice_token(value: Any) -> str:
    token = _norm(value)
    if not token:
        return ""
    if token in _PRACTICE_DNP:
        return "DNP"
    if token in _PRACTICE_LIMITED:
        return "LP"
    if token.startswith("FULL"):
        return "FP"
    return token[:3]


def _clean_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_int(value: Any) -> int | None:
    cleaned = _clean_float(value)
    return int(cleaned) if cleaned is not None else None
