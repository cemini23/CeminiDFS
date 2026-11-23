"""Tiered player exposure caps for a GPP book.

The flat ``max_exposure`` value cannot tell a $9,000 WR from a $4,800 WR. The
Week 11 recap showed 23%-35% exposure on cheap and mid-tier RBs and WRs. A
tier cap gives each salary band its own ceiling.

Cap precedence for one player:

1. An explicit per-player override. It may raise or lower the cap.
2. ``ROLE_CLIFF_WARNING`` in ``role_flags`` gets ``role_cliff_cap``.
3. An RB on a negative game script gets ``bad_game_script_rb.cap``.
4. The salary tier cap.
5. ``None``. The caller keeps the global ``max_exposure``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .build_gates import name_key

ROLE_CLIFF_WARNING = "ROLE_CLIFF_WARNING"

REASON_OVERRIDE = "override"
REASON_ROLE_CLIFF = "role_cliff"
REASON_RB_BAD_GAME_SCRIPT = "rb_bad_game_script"
REASON_TIER_STUD = "tier:stud"
REASON_TIER_MID = "tier:mid"
REASON_TIER_VALUE = "tier:value"

DEFAULT_SKILL_POSITIONS = ("QB", "RB", "WR", "TE")
DEFAULT_STUD_MIN_SALARY = 7000.0
DEFAULT_STUD_CAP = 0.35
DEFAULT_MID_MIN_SALARY = 5500.0
DEFAULT_MID_MAX_SALARY = 7000.0
DEFAULT_MID_CAP = 0.20
DEFAULT_VALUE_MAX_SALARY = 5500.0
DEFAULT_VALUE_CAP = 0.12
DEFAULT_SPREAD_THRESHOLD = 10.0
DEFAULT_BAD_GAME_SCRIPT_CAP = 0.10
DEFAULT_ROLE_CLIFF_CAP = 0.10


@dataclass(frozen=True)
class ExposureTierConfig:
    """One parsed ``exposure_tiers`` block."""

    enabled: bool
    stud_min_salary: float
    stud_cap: float
    mid_min_salary: float
    mid_max_salary: float
    mid_cap: float
    value_max_salary: float
    value_cap: float
    skill_positions: frozenset[str]
    spread_threshold: float
    bad_game_script_cap: float
    role_cliff_cap: float
    player_overrides: Mapping[str, float] = field(default_factory=dict)


def exposure_tier_config(config: Mapping[str, Any] | None) -> ExposureTierConfig | None:
    """Return the parsed tier settings. Return ``None`` when the tier is off."""

    block = _exposure_block(config)
    if not block:
        return None
    if not bool(block.get("enabled", False)):
        return None

    stud = _section(block, "stud")
    mid = _section(block, "mid")
    value = _section(block, "value")
    script = _section(block, "bad_game_script_rb")
    skill = block.get("skill_positions")
    skill_positions = (
        frozenset(str(item).strip().upper() for item in skill if str(item).strip())
        if isinstance(skill, (list, tuple, set, frozenset))
        else frozenset(DEFAULT_SKILL_POSITIONS)
    )
    return ExposureTierConfig(
        enabled=True,
        stud_min_salary=float(stud.get("min_salary", DEFAULT_STUD_MIN_SALARY)),
        stud_cap=float(stud.get("cap", DEFAULT_STUD_CAP)),
        mid_min_salary=float(mid.get("min_salary", DEFAULT_MID_MIN_SALARY)),
        mid_max_salary=float(mid.get("max_salary", DEFAULT_MID_MAX_SALARY)),
        mid_cap=float(mid.get("cap", DEFAULT_MID_CAP)),
        value_max_salary=float(value.get("max_salary", DEFAULT_VALUE_MAX_SALARY)),
        value_cap=float(value.get("cap", DEFAULT_VALUE_CAP)),
        skill_positions=skill_positions or frozenset(DEFAULT_SKILL_POSITIONS),
        spread_threshold=float(script.get("spread_threshold", DEFAULT_SPREAD_THRESHOLD)),
        bad_game_script_cap=float(script.get("cap", DEFAULT_BAD_GAME_SCRIPT_CAP)),
        role_cliff_cap=float(block.get("role_cliff_cap", DEFAULT_ROLE_CLIFF_CAP)),
        player_overrides=_player_overrides(block.get("player_overrides")),
    )


def tier_cap(position: Any, salary: Any, cfg: ExposureTierConfig | None) -> float | None:
    """Return the salary tier cap. Return ``None`` for a position outside the tiers."""

    if cfg is None:
        return None
    pos = _position_token(position)
    if pos not in cfg.skill_positions:
        return None
    money = _salary_value(salary)
    if money is None:
        return None
    if pos == "QB" or money >= cfg.stud_min_salary:
        return cfg.stud_cap
    if money >= cfg.mid_min_salary:
        return cfg.mid_cap
    return cfg.value_cap


def tier_reason(position: Any, salary: Any, cfg: ExposureTierConfig | None) -> str:
    """Return the tier label that matches :func:`tier_cap`."""

    if cfg is None:
        return ""
    pos = _position_token(position)
    if pos not in cfg.skill_positions:
        return ""
    money = _salary_value(salary)
    if money is None:
        return ""
    if pos == "QB" or money >= cfg.stud_min_salary:
        return REASON_TIER_STUD
    if money >= cfg.mid_min_salary:
        return REASON_TIER_MID
    return REASON_TIER_VALUE


def bad_game_script_cap(
    position: Any,
    team: Any,
    spreads: Mapping[str, Any] | None,
    cfg: ExposureTierConfig | None,
) -> float | None:
    """Return the RB cap on a blowout underdog. Return ``None`` for another case.

    ``spreads`` uses the betting convention from
    :func:`ceminidfs.data.vegas.extract_spread_total`: a positive number means
    the team is the underdog.
    """

    if cfg is None or not spreads:
        return None
    if _position_token(position) != "RB":
        return None
    spread = _spread_value(spreads.get(_team_token(team)))
    if spread is None:
        return None
    if spread >= cfg.spread_threshold:
        return cfg.bad_game_script_cap
    return None


def exposure_cap_for_player(
    position: Any,
    salary: Any,
    team: Any = "",
    *,
    cfg: ExposureTierConfig | None,
    spreads: Mapping[str, Any] | None = None,
    role_flags: Any = "",
    explicit: Mapping[str, Any] | float | None = None,
    name: Any = "",
) -> float | None:
    """Return the lowest applicable cap for one player.

    ``explicit`` is a per-player override. Pass a mapping keyed by player name,
    or pass the resolved cap number. ``name`` selects the entry in the mapping.
    ``explicit`` wins over every other cap, and it may raise the cap.
    """

    override = _explicit_cap(explicit, name)
    if override is not None:
        return override
    if cfg is None:
        return None
    if _has_role_cliff(role_flags):
        return cfg.role_cliff_cap
    script = bad_game_script_cap(position, team, spreads, cfg)
    tier = tier_cap(position, salary, cfg)
    candidates = [cap for cap in (script, tier) if cap is not None]
    if not candidates:
        return None
    return min(candidates)


def exposure_cap_map(
    players: Iterable[Any],
    *,
    config: Mapping[str, Any] | None,
    spreads: Mapping[str, Any] | None = None,
    role_flags: Mapping[str, str] | None = None,
) -> tuple[dict[str, float], dict[str, str]]:
    """Return ``({name: cap}, {name: reason})`` for the tier and guard caps.

    The cap map holds one entry per affected player. A player who keeps the
    global cap has no entry. The key is the folded player name.
    """

    cfg = exposure_tier_config(config)
    if cfg is None:
        return {}, {}
    flags = role_flags or {}
    caps: dict[str, float] = {}
    reasons: dict[str, str] = {}
    for player in players:
        name = _player_name(player)
        if not name:
            continue
        key = name_key(name)
        position = _player_position(player)
        salary = _player_salary(player)
        team = _player_team(player)
        cap = exposure_cap_for_player(
            position,
            salary,
            team,
            cfg=cfg,
            spreads=spreads,
            role_flags=flags.get(key, ""),
            explicit=cfg.player_overrides,
            name=name,
        )
        if cap is None:
            continue
        caps[key] = cap
        reasons[key] = _cap_reason(
            cfg,
            position=position,
            salary=salary,
            team=team,
            spreads=spreads,
            role_flags=flags.get(key, ""),
            explicit=cfg.player_overrides,
            name=name,
        )
    return caps, reasons


def override_caps(config: Mapping[str, Any] | None) -> dict[str, float]:
    """Return the folded ``{name: cap}`` explicit override map from the config."""

    block = _exposure_block(config)
    if not block:
        return {}
    return {name_key(name): cap for name, cap in _player_overrides(block.get("player_overrides")).items()}


def _cap_reason(
    cfg: ExposureTierConfig,
    *,
    position: Any,
    salary: Any,
    team: Any,
    spreads: Mapping[str, Any] | None,
    role_flags: Any,
    explicit: Mapping[str, Any] | float | None,
    name: Any,
) -> str:
    if _explicit_cap(explicit, name) is not None:
        return REASON_OVERRIDE
    if _has_role_cliff(role_flags):
        return REASON_ROLE_CLIFF
    script = bad_game_script_cap(position, team, spreads, cfg)
    tier = tier_cap(position, salary, cfg)
    if script is not None and (tier is None or script <= tier):
        return REASON_RB_BAD_GAME_SCRIPT
    return tier_reason(position, salary, cfg)


def _exposure_block(config: Mapping[str, Any] | None) -> dict[str, Any]:
    if not config:
        return {}
    block = config.get("exposure_tiers")
    if isinstance(block, Mapping):
        return dict(block)
    if "stud" in config or "value" in config:
        return dict(config)
    return {}


def _section(block: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = block.get(key)
    return value if isinstance(value, Mapping) else {}


def _player_overrides(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    caps: dict[str, float] = {}
    for name, cap in value.items():
        token = str(name or "").strip()
        if not token:
            continue
        try:
            caps[token] = float(cap)
        except (TypeError, ValueError):
            continue
    return caps


def _explicit_cap(explicit: Mapping[str, Any] | float | None, name: Any) -> float | None:
    if explicit is None:
        return None
    if isinstance(explicit, Mapping):
        key = name_key(name)
        if not key:
            return None
        for candidate, cap in explicit.items():
            if name_key(candidate) == key:
                try:
                    return float(cap)
                except (TypeError, ValueError):
                    return None
        return None
    try:
        return float(explicit)
    except (TypeError, ValueError):
        return None


def _has_role_cliff(role_flags: Any) -> bool:
    if not role_flags:
        return False
    if isinstance(role_flags, str):
        return ROLE_CLIFF_WARNING in role_flags
    return ROLE_CLIFF_WARNING in {str(item).strip() for item in role_flags}


def _position_token(value: Any) -> str:
    return str(value or "").strip().upper()


def _team_token(value: Any) -> str:
    return str(value or "").strip().upper()


def _salary_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _spread_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _player_name(player: Any) -> str:
    if isinstance(player, Mapping):
        for key in ("full_name", "name", "player_name", "Nickname"):
            value = player.get(key)
            if value not in (None, ""):
                return str(value).strip()
        first = str(player.get("First Name") or player.get("first_name") or "").strip()
        last = str(player.get("Last Name") or player.get("last_name") or "").strip()
        return " ".join(part for part in (first, last) if part).strip()
    for attribute in ("full_name", "name", "player_name"):
        value = getattr(player, attribute, None)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _player_position(player: Any) -> str:
    if isinstance(player, Mapping):
        for key in ("position", "pos", "fd_position", "Position"):
            value = player.get(key)
            if value not in (None, ""):
                return str(value).strip().upper()
        return ""
    position = getattr(player, "position", None)
    if isinstance(position, (list, tuple)):
        position = position[0] if position else None
    if position not in (None, ""):
        return str(position).strip().upper()
    for attribute in ("pos", "fd_position"):
        value = getattr(player, attribute, None)
        if value not in (None, ""):
            return str(value).strip().upper()
    positions = getattr(player, "positions", None)
    if positions:
        return str(list(positions)[0]).strip().upper()
    return ""


def _player_salary(player: Any) -> Any:
    if isinstance(player, Mapping):
        for key in ("salary", "fd_salary", "Salary"):
            value = player.get(key)
            if value not in (None, ""):
                return value
        return None
    return getattr(player, "salary", None)


def _player_team(player: Any) -> str:
    if isinstance(player, Mapping):
        for key in ("team", "Team", "team_raw"):
            value = player.get(key)
            if value not in (None, ""):
                return str(value).strip().upper()
        return ""
    return str(getattr(player, "team", "") or "").strip().upper()
