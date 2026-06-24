"""BBM7 configuration constants and settings."""

from __future__ import annotations

from typing import Dict, List, Tuple

# Portfolio targets (150 entries)
ARCHETYPE_TARGETS = {
    "A": 53,  # RB-forward (35%)
    "B": 38,  # Hero RB + WR (25%)
    "C": 30,  # Stack-heavy (20%)
    "D": 23,  # Zero RB (15%)
    "E": 6,   # Contrarian / CLV-only (4%)
}

ARCHETYPE_NAMES = {
    "A": "RB-forward",
    "B": "Hero RB",
    "C": "Stack-heavy",
    "D": "Zero RB",
    "E": "Contrarian / CLV-only",
}

# Timing split targets
TIMING_TARGETS = {
    "may_jun": 38,      # 25%
    "jul_mid_aug": 82,  # 55%
    "late_aug_sep": 30, # 20%
}

# Archetype × Timing matrix
ARCHETYPE_TIMING_MATRIX = {
    "A": {"may_jun": 8, "jul_mid_aug": 30, "late_aug_sep": 15},
    "B": {"may_jun": 10, "jul_mid_aug": 22, "late_aug_sep": 6},
    "C": {"may_jun": 6, "jul_mid_aug": 18, "late_aug_sep": 6},
    "D": {"may_jun": 10, "jul_mid_aug": 8, "late_aug_sep": 5},
    "E": {"may_jun": 4, "jul_mid_aug": 4, "late_aug_sep": 2},
}

# Exposure caps by tier
TIER_EXPOSURE_CAPS = {
    "elite": 0.35,       # 35% / 53 players
    "stack_core": 0.25,  # 25% / 38 players
    "mid_target": 0.20,  # 20% / 30 players
    "late_lottery": 0.15, # 15% / 23 players
    "single_dart": 0.10,  # 10% / 15 players
}

COMBO_PAIR_CAP = 0.25  # 25% for defined stack pairs

# Exposure soft brake threshold (cap - 5%)
EXPOSURE_SOFT_BRAKE_PCT = 0.05

# In-progress draft weight for exposure preview
IN_PROGRESS_EXPOSURE_WEIGHT = 0.5

# Bye week calendar 2026
BYE_WEEKS: Dict[str, int] = {
    "KC": 5, "CAR": 5,
    "CIN": 6, "MIA": 6, "DET": 6, "MIN": 6,
    "BUF": 7, "LAC": 7, "WAS": 7, "JAX": 7,
    "SF": 8, "NYG": 8, "NO": 8, "HOU": 8,
    "PIT": 9, "TEN": 9,
    "CHI": 10, "DEN": 10, "TB": 10, "PHI": 10,
    "CLE": 11, "ATL": 11, "GB": 11, "NE": 11, "LAR": 11, "SEA": 11,
    "IND": 13, "NYJ": 13, "LV": 13, "BAL": 13,
    "ARI": 14, "DAL": 14,
}

# Hard constraint limits
MAX_SAME_BYE = 7          # ≤7 players same bye (teammates exempt)
NEVER_SAME_BYE = 10       # Never 10+ same bye
MAX_SAME_TEAM = 4         # ≤4 players same NFL team
MAX_SAME_TEAM_ARCHETYPE_C = 5  # 5 allowed only for Archetype C

# Draft format
DRAFT_ROUNDS = 18
TEAM_SIZE = 12
TOTAL_ENTRIES = 150
ENTRY_FEE = 25

# Roster shell targets
ROSTER_TARGETS = {
    "QB": (3, 3),    # min, max
    "RB": (4, 5),
    "WR": (6, 7),
    "TE": (2, 3),
}

# Round-band rules
ROUND_BANDS = {
    "r1_2": (1, 2),
    "r3_5": (3, 5),
    "r6_7": (6, 7),
    "r8_10": (8, 10),
    "r11_13": (11, 13),
    "r14_18": (14, 18),
}

# CLV weight by month (May 1.5, Jul 1.2, Aug 0.8)
CLV_WEIGHT_MONTHLY = {
    5: 1.5,
    6: 1.5,
    7: 1.2,
    8: 0.8,
    9: 0.8,
}

# Stack multipliers
STACK_MULT_QB = 0.30
STACK_MULT_PASS = 0.15
STACK_MULT_W17_BRINGBACK = 0.10
STACK_MULT_MAX = 1.4
STACK_MULT_MIN_CLV_DELTA = 3

# Recommendation settings
MAX_RECOMMENDATIONS = 3
RECOMMENDER_TIMEOUT_MS = 200

# Archetype pivot state machine
ARCHETYPE_PIVOTS: Dict[str, List[Tuple[str, str]]] = {
    "D": [("B", "Hero RB"), ("A", "RB-forward")],
    "C": [("A", "RB-forward"), ("E", "CLV")],
    "A": [("B", "Hero RB")],
}

PIVOT_TRIGGERS = {
    "D": "0 RB at R6 and elite RB tier empty",
    "C": "Anchor gone + stack lane dead",
    "A": "0 RB at R5 in RB run",
}

# Signal values
SIGNAL_BUY = "BUY"
SIGNAL_FADE = "FADE"

# Position codes
POSITIONS = {"QB", "RB", "WR", "TE"}
FLEX_POSITIONS = {"RB", "WR", "TE"}

# Scoring (Half-PPR)
SCORING_HALF_PPR = {
    "pass_yd": 0.04,
    "pass_td": 4.0,
    "int": -1.0,
    "rush_yd": 0.1,
    "rush_td": 6.0,
    "rec": 0.5,
    "rec_yd": 0.1,
    "rec_td": 6.0,
    "fumble": -2.0,
}

# BUY/FADE lists (seed registry)
BUY_TE_CLUSTER = [
    "Kelce", "Ferguson", "Andrews", "Goedert", "Gadsden",
    "Strange", "Okonkwo", "Juwan Johnson", "Dulcich"
]

BUY_QB = [
    "Hurts", "Daniels", "Burrow", "Lawrence", "Purdy",
    "Stroud", "Shough", "Young"
]

BUY_RB_EARLY = [
    "Gibbs", "Bijan", "Taylor", "Henry", "Chase Brown",
    "Achane", "Jeanty"
]

BUY_WR = [
    "Chase", "Nacua", "Amon-Ra St. Brown", "JSN", "McMillan", "Egbuka"
]

BUY_ROOKIE_WR_MAY_JUN = [
    "Cooper", "Boston", "Concepcion", "Branch", "Hurst"
]

FADE_PLAYERS = [
    "Josh Allen", "Bowers", "McBride", "Tyreek Hill", "Aiyuk", "Bucky Irving"
]

# Aliases for draft_card / display
ARCHETYPE_SPLIT = ARCHETYPE_TARGETS
TIMING_SPLIT = TIMING_TARGETS
TIMING_ARCHETYPE_MATRIX = ARCHETYPE_TIMING_MATRIX
TEAMS = TEAM_SIZE

EXPOSURE_CAPS = {k: int(v * 100) for k, v in TIER_EXPOSURE_CAPS.items()}

STACK_PAIRS: List[Tuple[str, str]] = [
    ("Joe Burrow", "Ja'Marr Chase"),
    ("Jalen Hurts", "A.J. Brown"),
    ("Jayden Daniels", "Terry McLaurin"),
    ("Brock Purdy", "George Kittle"),
    ("Trevor Lawrence", "Brian Thomas Jr."),
]

BUY_ROOKIE_WR = BUY_ROOKIE_WR_MAY_JUN

CLV_WEIGHTS_BY_MONTH = {"may": 1.5, "jun": 1.5, "jul": 1.2, "aug": 0.8, "sep": 0.8}

DEFAULT_ROSTER_SHELL = {
    "qb": f"{ROSTER_TARGETS['QB'][0]}-{ROSTER_TARGETS['QB'][1]}",
    "rb": f"{ROSTER_TARGETS['RB'][0]}-{ROSTER_TARGETS['RB'][1]}",
    "wr": f"{ROSTER_TARGETS['WR'][0]}-{ROSTER_TARGETS['WR'][1]}",
    "te": f"{ROSTER_TARGETS['TE'][0]}-{ROSTER_TARGETS['TE'][1]}",
}

ROUND_BAND_RULES: List[Dict[str, object]] = [
    {
        "rounds": "R1–2",
        "target": "Elite RB/WR",
        "buy": ("Gibbs", "Bijan", "Taylor", "Henry", "Jeanty", "Achane", "Chase", "Nacua", "ARSB", "Lamb"),
        "fade": ("Bowers", "McBride"),
    },
    {
        "rounds": "R3–5",
        "target": "RB2 / WR run",
        "buy": ("Chase Brown", "Hampton", "Kyren", "Breece", "JSN", "McMillan", "Egbuka"),
        "fade": ("Josh Allen",),
    },
    {
        "rounds": "R6–7",
        "target": "QB1 + WR depth",
        "buy": ("Hurts", "Daniels", "Burrow"),
        "fade": ("Ambiguous WR3",),
    },
    {
        "rounds": "R8–10",
        "target": "QB2, depth",
        "buy": ("Lawrence", "Purdy", "Mahomes", "Mayfield"),
        "fade": ("Same-bye QBs",),
    },
    {
        "rounds": "R11–13",
        "target": "TE cluster, QB3",
        "buy": tuple(BUY_TE_CLUSTER),
        "fade": ("Middle-tier TE R8–10",),
    },
    {
        "rounds": "R14–18",
        "target": "Late lottery",
        "buy": ("Johnson", "Dulcich", "Stevenson", "Swift", "Pollard"),
        "fade": ("Tyreek Hill", "Aiyuk"),
    },
]

# Archetype round-band multipliers
ARCHETYPE_ROUND_MULTS: Dict[str, Dict[str, float]] = {
    "A": {  # RB-forward
        "r1_2": 1.2,
        "r3_5": 1.0,
        "r6_7": 1.1,
        "r8_10": 0.9,
        "r11_13": 1.3,  # TE cluster
        "r14_18": 0.8,
    },
    "B": {  # Hero RB
        "r1_2": 1.1,
        "r3_5": 1.2,
        "r6_7": 0.9,
        "r8_10": 1.0,
        "r11_13": 1.3,  # TE cluster
        "r14_18": 0.8,
    },
    "C": {  # Stack-heavy
        "r1_2": 1.3,
        "r3_5": 1.2,
        "r6_7": 1.1,
        "r8_10": 1.0,
        "r11_13": 0.9,
        "r14_18": 0.8,
    },
    "D": {  # Zero RB
        "r1_2": 1.2,
        "r3_5": 1.3,
        "r6_7": 0.9,
        "r8_10": 1.0,
        "r11_13": 1.3,  # TE cluster
        "r14_18": 0.8,
    },
    "E": {  # Contrarian / CLV-only
        "r1_2": 1.0,
        "r3_5": 1.0,
        "r6_7": 1.0,
        "r8_10": 1.0,
        "r11_13": 1.0,
        "r14_18": 1.0,
    },
}


def get_round_band(round_num: int) -> str:
    """Return the round band key for a given round number."""
    for band, (start, end) in ROUND_BANDS.items():
        if start <= round_num <= end:
            return band
    return "r14_18"  # Default to late rounds


def clv_weight(month: int) -> float:
    """Return CLV weight for a given month."""
    return CLV_WEIGHT_MONTHLY.get(month, 1.0)


def archetype_mult(archetype: str, round_num: int) -> float:
    """Return archetype multiplier for a given round."""
    band = get_round_band(round_num)
    return ARCHETYPE_ROUND_MULTS.get(archetype, {}).get(band, 1.0)


def get_bye_week(team: str) -> int | None:
    """Return bye week for a team abbreviation."""
    return BYE_WEEKS.get(team.upper())
