"""ESPN 12-team snake full-PPR redraft constants."""

from __future__ import annotations

from typing import Dict, List, Tuple

# Format
TEAMS = 12
DRAFT_ROUNDS = 16  # standard ESPN snake with DST/K + bench
SCORING = "espn_ppr"
LEAGUE_LABEL = "ESPN 12-team snake full PPR"

# Standard ESPN roster shell (starters + typical bench depth)
ROSTER_SHELL: Dict[str, str] = {
    "QB": "1 (max 2)",
    "RB": "2 + FLEX depth (target 4–5)",
    "WR": "2 + FLEX depth (target 5–6)",
    "TE": "1 (max 2)",
    "FLEX": "1 (RB/WR/TE)",
    "DST": "1",
    "K": "1",
    "BENCH": "~6",
}

# ESPN Auto-Pick Strategy — position min/max for the Edit Auto-Pick Strategy panel
POSITION_LIMITS: Dict[str, Tuple[int, int]] = {
    "QB": (1, 2),
    "RB": (4, 6),
    "WR": (5, 7),
    "TE": (1, 2),
    "DST": (1, 1),
    "K": (1, 1),
}

# Per-round Auto-Pick Strategy defaults (Best Available unless position-gated)
# Rounds 15–16 force DST/K so autopick does not grab them early.
AUTOPICK_ROUND_STRATEGY: List[Dict[str, str]] = [
    {"round": "1", "choice": "Best Available"},
    {"round": "2", "choice": "Best Available"},
    {"round": "3", "choice": "Best Available"},
    {"round": "4", "choice": "Best Available"},
    {"round": "5", "choice": "Best Available"},
    {"round": "6", "choice": "Best Available"},
    {"round": "7", "choice": "Best Available"},
    {"round": "8", "choice": "Best Available"},
    {"round": "9", "choice": "Best Available"},
    {"round": "10", "choice": "Best Available"},
    {"round": "11", "choice": "Best Available"},
    {"round": "12", "choice": "Best Available"},
    {"round": "13", "choice": "Best Available"},
    {"round": "14", "choice": "Best Available"},
    {"round": "15", "choice": "DST"},
    {"round": "16", "choice": "K"},
]

# BUY lists — retuned for full PPR (WR/TE up vs half-PPR; early QB still delayed)
BUY_TE = (
    "Kelce",
    "Ferguson",
    "Andrews",
    "Goedert",
    "Strange",
    "Okonkwo",
    "Juwan Johnson",
    "Dulcich",
)

BUY_QB = (
    "Hurts",
    "Daniels",
    "Burrow",
    "Lamar Jackson",
    "Lawrence",
    "Purdy",
    "Stroud",
    "Mayfield",
)

BUY_RB = (
    "Gibbs",
    "Bijan",
    "Taylor",
    "Henry",
    "Chase Brown",
    "Achane",
    "Jeanty",
    "Kyren Williams",
    "Breece Hall",
)

BUY_WR = (
    "Chase",
    "Nacua",
    "Amon-Ra St. Brown",
    "CeeDee Lamb",
    "JSN",
    "McMillan",
    "Egbuka",
    "Brian Thomas Jr.",
    "Nico Collins",
)

BUY_ROOKIE_WR = (
    "Cooper",
    "Boston",
    "Concepcion",
    "Branch",
    "Hurst",
)

FADE_PLAYERS = (
    "Josh Allen early",
    "Bowers R1–2",
    "McBride R1–2",
    "Tyreek Hill",
    "Brandon Aiyuk",
    "Bucky Irving",
)

ROUND_BAND_RULES: List[Dict[str, object]] = [
    {
        "rounds": "R1–2",
        "target": "Elite RB / high-volume WR",
        "buy": (
            "Gibbs",
            "Bijan",
            "Taylor",
            "Henry",
            "Jeanty",
            "Achane",
            "Chase",
            "Nacua",
            "ARSB",
            "Lamb",
        ),
        "fade": ("Bowers", "McBride"),
    },
    {
        "rounds": "R3–5",
        "target": "RB2 / WR2 run (PPR volume)",
        "buy": (
            "Chase Brown",
            "Kyren",
            "Breece",
            "JSN",
            "McMillan",
            "Egbuka",
            "BTJ",
            "Nico Collins",
        ),
        "fade": ("Josh Allen", "Early QB reach"),
    },
    {
        "rounds": "R6–8",
        "target": "QB1 window + TE1 / WR3",
        "buy": ("Hurts", "Daniels", "Burrow", "Lamar", "Kelce", "Ferguson", "Andrews"),
        "fade": ("Ambiguous WR4", "Second TE early"),
    },
    {
        "rounds": "R9–12",
        "target": "FLEX depth + QB2/TE2 lottery",
        "buy": ("Lawrence", "Purdy", "Mayfield", "Goedert", "Strange", "Okonkwo"),
        "fade": ("Same-bye QB pair", "Second K/DST"),
    },
    {
        "rounds": "R13–14",
        "target": "Bench upside / handcuffs",
        "buy": ("Handcuff RBs", "Rookie WR darts", "Juwan Johnson", "Dulcich"),
        "fade": ("Tyreek Hill", "Aiyuk"),
    },
    {
        "rounds": "R15–16",
        "target": "DST then K",
        "buy": ("Streaming DST", "Reliable K"),
        "fade": ("Stacking kickers", "Second DST"),
    },
]

# Prerank output defaults
PRERANK_TOP_N = 200
ADP_REQUIRED_COLUMNS = ("name", "pos", "adp")
OPTIONAL_ADP_COLUMNS = ("team", "notes", "projection_pts")
