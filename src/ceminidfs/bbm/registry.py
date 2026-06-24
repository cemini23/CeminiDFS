"""Player registry persistence helpers."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from ceminidfs.bbm.config import (
    BUY_QB,
    BUY_RB_EARLY,
    BUY_ROOKIE_WR_MAY_JUN,
    BUY_TE_CLUSTER,
    BUY_WR,
    FADE_PLAYERS,
    FADE_ROUND_BANDS,
    TIER_EXPOSURE_CAPS,
    get_bye_week,
)
from ceminidfs.config import PROJECT_ROOT

DATA_DIR_NAME = "bbm"
REGISTRY_FILENAME = "player_registry.json"
OVERRIDES_FILENAME = "player_overrides.csv"


def default_data_dir() -> Path:
    """Return the default BBM data directory."""

    return PROJECT_ROOT / "data" / DATA_DIR_NAME


def get_registry_path(data_dir: Path | str | None = None) -> Path:
    """Return the player registry path."""

    base_dir = Path(data_dir) if data_dir is not None else default_data_dir()
    return base_dir / REGISTRY_FILENAME


def load_registry(path: Path | str | None = None) -> dict[str, Any]:
    """Load the player registry JSON."""

    registry_path = Path(path) if path is not None else get_registry_path()
    if not registry_path.exists():
        return {"meta": {}, "players": []}
    return json.loads(registry_path.read_text(encoding="utf-8"))


def save_registry(registry: dict[str, Any], path: Path | str | None = None) -> Path:
    """Save the player registry JSON and return its path."""

    registry_path = Path(path) if path is not None else get_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return registry_path


def _slug_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"bbm:{slug}"


def _normalize_merge(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().replace("'", "").replace(".", " ")).strip()


# Seed ADP / projection estimates for strategy players (refresh via refresh-adp weekly)
_SEED_PLAYERS: list[dict[str, Any]] = [
    # Elite RB/WR R1-2
    {"name": "Jahmyr Gibbs", "position": "RB", "team": "DET", "adp": 3.5, "tier": "elite", "signal": "BUY", "projection_pts": 245},
    {"name": "Bijan Robinson", "position": "RB", "team": "ATL", "adp": 4.2, "tier": "elite", "signal": "BUY", "projection_pts": 242},
    {"name": "Jonathan Taylor", "position": "RB", "team": "IND", "adp": 8.1, "tier": "elite", "signal": "BUY", "projection_pts": 228},
    {"name": "Derrick Henry", "position": "RB", "team": "BAL", "adp": 9.4, "tier": "elite", "signal": "BUY", "projection_pts": 225},
    {"name": "Ashton Jeanty", "position": "RB", "team": "LV", "adp": 11.2, "tier": "elite", "signal": "BUY", "projection_pts": 218},
    {"name": "De'Von Achane", "position": "RB", "team": "MIA", "adp": 12.8, "tier": "elite", "signal": "BUY", "projection_pts": 215},
    {"name": "Ja'Marr Chase", "position": "WR", "team": "CIN", "adp": 1.8, "tier": "elite", "signal": "BUY", "projection_pts": 252},
    {"name": "Puka Nacua", "position": "WR", "team": "LAR", "adp": 5.6, "tier": "elite", "signal": "BUY", "projection_pts": 238},
    {"name": "Amon-Ra St. Brown", "position": "WR", "team": "DET", "adp": 7.3, "tier": "elite", "signal": "BUY", "projection_pts": 232},
    {"name": "CeeDee Lamb", "position": "WR", "team": "DAL", "adp": 6.1, "tier": "elite", "signal": "BUY", "projection_pts": 235},
    {"name": "Ladd McConkey", "position": "WR", "team": "LAC", "adp": 14.5, "tier": "stack_core", "signal": "BUY", "projection_pts": 210},
    # R3-5
    {"name": "Chase Brown", "position": "RB", "team": "CIN", "adp": 28.4, "tier": "stack_core", "signal": "BUY", "projection_pts": 195},
    {"name": "Omarion Hampton", "position": "RB", "team": "LAC", "adp": 32.1, "tier": "stack_core", "signal": "BUY", "projection_pts": 188},
    {"name": "Kyren Williams", "position": "RB", "team": "LAR", "adp": 35.7, "tier": "stack_core", "signal": "BUY", "projection_pts": 182},
    {"name": "Breece Hall", "position": "RB", "team": "NYJ", "adp": 38.2, "tier": "stack_core", "signal": "BUY", "projection_pts": 178},
    {"name": "Jaxon Smith-Njigba", "position": "WR", "team": "SEA", "adp": 29.6, "tier": "stack_core", "signal": "BUY", "projection_pts": 192},
    {"name": "Xavier Worthy", "position": "WR", "team": "KC", "adp": 41.3, "tier": "stack_core", "signal": "BUY", "projection_pts": 175},
    {"name": "Emeka Egbuka", "position": "WR", "team": "TB", "adp": 44.8, "tier": "stack_core", "signal": "BUY", "projection_pts": 170},
    # QB1 R6-7
    {"name": "Jalen Hurts", "position": "QB", "team": "PHI", "adp": 52.3, "tier": "stack_core", "signal": "BUY", "projection_pts": 285},
    {"name": "Jayden Daniels", "position": "QB", "team": "WAS", "adp": 58.7, "tier": "stack_core", "signal": "BUY", "projection_pts": 278},
    {"name": "Joe Burrow", "position": "QB", "team": "CIN", "adp": 61.2, "tier": "stack_core", "signal": "BUY", "projection_pts": 272},
    # QB2 R8-10
    {"name": "Trevor Lawrence", "position": "QB", "team": "JAX", "adp": 88.4, "tier": "mid_target", "signal": "BUY", "projection_pts": 245},
    {"name": "Brock Purdy", "position": "QB", "team": "SF", "adp": 92.1, "tier": "mid_target", "signal": "BUY", "projection_pts": 240},
    {"name": "Patrick Mahomes", "position": "QB", "team": "KC", "adp": 95.6, "tier": "mid_target", "signal": "BUY", "projection_pts": 238},
    {"name": "Baker Mayfield", "position": "QB", "team": "TB", "adp": 98.3, "tier": "mid_target", "signal": "BUY", "projection_pts": 235},
    {"name": "C.J. Stroud", "position": "QB", "team": "HOU", "adp": 102.7, "tier": "mid_target", "signal": "BUY", "projection_pts": 232},
    {"name": "Drake Maye", "position": "QB", "team": "NE", "adp": 118.5, "tier": "mid_target", "signal": "BUY", "projection_pts": 220},
    {"name": "Tyler Shough", "position": "QB", "team": "NO", "adp": 165.2, "tier": "late_lottery", "signal": "BUY", "projection_pts": 185},
    {"name": "Bryce Young", "position": "QB", "team": "CAR", "adp": 172.8, "tier": "late_lottery", "signal": "BUY", "projection_pts": 180},
    # TE cluster R11-13
    {"name": "Travis Kelce", "position": "TE", "team": "KC", "adp": 120.4, "tier": "mid_target", "signal": "BUY", "projection_pts": 131},
    {"name": "Jake Ferguson", "position": "TE", "team": "DAL", "adp": 125.6, "tier": "mid_target", "signal": "BUY", "projection_pts": 128},
    {"name": "Mark Andrews", "position": "TE", "team": "BAL", "adp": 128.9, "tier": "mid_target", "signal": "BUY", "projection_pts": 125},
    {"name": "Dallas Goedert", "position": "TE", "team": "PHI", "adp": 132.4, "tier": "mid_target", "signal": "BUY", "projection_pts": 122},
    {"name": "Harold Fannin Jr.", "position": "TE", "team": "CLE", "adp": 145.2, "tier": "late_lottery", "signal": "BUY", "projection_pts": 110},
    {"name": "Cade Otton", "position": "TE", "team": "TB", "adp": 148.7, "tier": "late_lottery", "signal": "BUY", "projection_pts": 108},
    {"name": "Jonnu Smith", "position": "TE", "team": "PIT", "adp": 152.3, "tier": "late_lottery", "signal": "BUY", "projection_pts": 105},
    {"name": "Juwan Johnson", "position": "TE", "team": "NO", "adp": 158.6, "tier": "late_lottery", "signal": "BUY", "projection_pts": 102},
    {"name": "Greg Dulcich", "position": "TE", "team": "DEN", "adp": 168.4, "tier": "late_lottery", "signal": "BUY", "projection_pts": 95},
    # FADE targets
    {"name": "Josh Allen", "position": "QB", "team": "BUF", "adp": 42.5, "tier": "stack_core", "signal": "FADE", "projection_pts": 290},
    {"name": "Trey McBride", "position": "TE", "team": "ARI", "adp": 18.2, "tier": "elite", "signal": "FADE", "projection_pts": 165},
    {"name": "Brock Bowers", "position": "TE", "team": "LV", "adp": 16.8, "tier": "elite", "signal": "FADE", "projection_pts": 168},
    {"name": "Tyreek Hill", "position": "WR", "team": "MIA", "adp": 155.3, "tier": "late_lottery", "signal": "FADE", "projection_pts": 140},
    {"name": "Brandon Aiyuk", "position": "WR", "team": "SF", "adp": 162.7, "tier": "late_lottery", "signal": "FADE", "projection_pts": 135},
    {"name": "Bucky Irving", "position": "RB", "team": "TB", "adp": 22.4, "tier": "stack_core", "signal": "FADE", "projection_pts": 200},
    # Depth / lottery
    {"name": "Rhamondre Stevenson", "position": "RB", "team": "NE", "adp": 108.2, "tier": "mid_target", "signal": "BUY", "projection_pts": 155},
    {"name": "D'Andre Swift", "position": "RB", "team": "CHI", "adp": 112.5, "tier": "mid_target", "signal": "BUY", "projection_pts": 150},
    {"name": "Tony Pollard", "position": "RB", "team": "TEN", "adp": 115.8, "tier": "mid_target", "signal": "BUY", "projection_pts": 148},
    {"name": "A.J. Brown", "position": "WR", "team": "PHI", "adp": 19.6, "tier": "stack_core", "signal": "BUY", "projection_pts": 205},
    {"name": "George Kittle", "position": "TE", "team": "SF", "adp": 55.4, "tier": "stack_core", "signal": "BUY", "projection_pts": 145},
    {"name": "Terry McLaurin", "position": "WR", "team": "WAS", "adp": 48.2, "tier": "stack_core", "signal": "BUY", "projection_pts": 178},
    {"name": "Brian Thomas Jr.", "position": "WR", "team": "JAX", "adp": 36.5, "tier": "stack_core", "signal": "BUY", "projection_pts": 185},
    {"name": "Malachi Corley", "position": "WR", "team": "NYJ", "adp": 178.2, "tier": "single_dart", "signal": "BUY", "projection_pts": 90, "drift_coeff": 0.15},
    {"name": "Pat Bryant", "position": "WR", "team": "DEN", "adp": 185.6, "tier": "single_dart", "signal": "BUY", "projection_pts": 88, "drift_coeff": 0.15},
]


def build_seed_registry() -> dict[str, Any]:
    """Build seed registry from strategy BUY/FADE tables."""

    players: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_player(entry: dict[str, Any]) -> None:
        merge = _normalize_merge(entry["name"])
        if merge in seen:
            return
        seen.add(merge)
        team = entry["team"]
        tier = entry.get("tier", "mid_target")
        signal = entry.get("signal", "BUY")

        # Set fade_rounds for FADE players based on FADE_ROUND_BANDS config
        fade_rounds = None
        if signal == "FADE":
            # Check if this player has round-specific fade bands
            for pattern, band in FADE_ROUND_BANDS.items():
                if pattern in merge:
                    fade_rounds = [band]
                    break

        players.append(
            {
                "player_id": entry.get("player_id") or _slug_id(entry["name"]),
                "name": entry["name"],
                "merge_name": merge,
                "position": entry["position"],
                "team": team,
                "bye_week": get_bye_week(team) or 0,
                "adp": entry["adp"],
                "strategy_rank": int(entry["adp"]),
                "projection_pts": entry.get("projection_pts", 100.0),
                "signal": signal,
                "tier": tier,
                "exposure_cap_pct": TIER_EXPOSURE_CAPS.get(tier, 0.20),
                "drift_coeff": entry.get("drift_coeff", 0.0),
                "injury_fade": False,
                "notes": entry.get("notes", ""),
                "fade_rounds": fade_rounds,
            }
        )

    for row in _SEED_PLAYERS:
        add_player(row)

    # Ensure named BUY lists appear even if not in _SEED_PLAYERS
    buy_names = (
        [(n, "TE", "mid_target") for n in BUY_TE_CLUSTER]
        + [(n, "QB", "stack_core") for n in BUY_QB]
        + [(n, "RB", "elite") for n in BUY_RB_EARLY]
        + [(n, "WR", "stack_core") for n in BUY_WR]
        + [(n, "WR", "single_dart") for n in BUY_ROOKIE_WR_MAY_JUN]
    )
    adp_cursor = 200.0
    for name, pos, tier in buy_names:
        merge = _normalize_merge(name)
        if merge in seen:
            continue
        add_player(
            {
                "name": name,
                "position": pos,
                "team": "FA",
                "adp": adp_cursor,
                "tier": tier,
                "signal": "BUY",
                "projection_pts": 85.0,
            }
        )
        adp_cursor += 3.0

    for fade_name in FADE_PLAYERS:
        merge = _normalize_merge(fade_name)
        if merge in seen:
            continue
        add_player(
            {
                "name": fade_name,
                "position": "WR",
                "team": "FA",
                "adp": 180.0,
                "tier": "late_lottery",
                "signal": "FADE",
                "projection_pts": 80.0,
            }
        )

    players.sort(key=lambda p: p["adp"])
    return {
        "meta": {
            "updated": date.today().isoformat(),
            "adp_source": "seed",
            "strategy_version": "2026-06-18",
            "player_count": len(players),
        },
        "players": players,
    }


def ensure_seed_registry() -> dict[str, Any]:
    """Load registry or create seed file if missing."""

    path = get_registry_path()
    if path.exists():
        registry = load_registry(path)
        if registry.get("players"):
            return registry

    registry = build_seed_registry()
    save_registry(registry, path)

    overrides = default_data_dir() / OVERRIDES_FILENAME
    if not overrides.exists():
        overrides.write_text(
            "merge_name,player_id,notes\n"
            "# Manual overrides win over fuzzy ADP merge\n",
            encoding="utf-8",
        )

    return registry

