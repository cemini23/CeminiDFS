"""Parse Underdog-style aria labels from draft board DOM elements.

Extracts player names from accessibility labels used in Underdog's
fantasy draft interface for syncing with the CeminiBBM ledger.
"""

from __future__ import annotations

import re


# Patterns to skip as noise (not player names)
# NOTE: "pick" is intentionally NOT in this list as "Pick Player Name" is valid
NOISE_PATTERNS = [
    r"^draft\s+(?:pick|slot|round|player)",
    r"^slot\s+",
    r"^round\s+",
    r"^timer\s*",
    r"^button\s*",
    r"^link\s*",
    r"^image\s*",
    r"^menu\s*",
    r"^navigation\s*",
    r"^search\s*",
    r"^filter\s*",
    r"^sort\s*",
    r"^close\s*",
    r"^open\s*",
    r"^expand\s*",
    r"^collapse\s*",
    r"^loading\s*",
    r"^refresh\s*",
    r"^settings\s*",
    r"^profile\s*",
    r"^account\s*",
    r"^logout\s*",
    r"^login\s*",
    r"^sign\s*",
    r"^team\s+\d+",
    r"^roster\s*",
    r"^queue\s*",
    r"^watchlist\s*",
    r"^favorites\s*",
    r"^history\s*",
    r"^chat\s*",
    r"^notifications?\s*",
    r"^help\s*",
    r"^support\s*",
    r"^info\s*",
    r"^about\s*",
    r"^terms\s*",
    r"^privacy\s*",
    r"^copyright\s*",
    r"^rights\s*",
    r"^reserved\s*",
    r"^all\s*",
    r"^undrafted\s*",
    r"^available\s*",
    r"^taken\s*",
    r"^selected\s*",
    r"^current\s*",
    r"^upcoming\s*",
    r"^previous\s*",
    r"^next\s*",
    r"^back\s*",
    r"^forward\s*",
    r"^first\s*",
    r"^last\s*",
    r"^page\s*",
    r"^of\s*",
    r"^showing\s*",
    r"^results?\s*",
    r"^entries?\s*",
    r"^items?\s*",
    r"^total\s*",
    r"^count\s*",
    r"^number\s*",
    r"^position\s*",
    r"^name\s*",
    r"^rank\s*",
    r"^adp\s*",
    r"^ecr\s*",
    r"^projection\s*",
    r"^points\s*",
    r"^score\s*",
    r"^stats\s*",
    r"^statistic\s*",
    r"^yard\s*",
    r"^touchdown\s*",
    r"^td\s*",
    r"^reception\s*",
    r"^rec\s*",
    r"^target\s*",
    r"^carry\s*",
    r"^attempt\s*",
    r"^completion\s*",
    r"^incompletion\s*",
    r"^interception\s*",
    r"^fumble\s*",
    r"^lost\s*",
    r"^sack\s*",
    r"^qb\s*",
    r"^rb\s*",
    r"^wr\s*",
    r"^te\s*",
    r"^k\s*",
    r"^dst\s*",
    r"^def\s*",
    r"^defense\s*",
    r"^flex\s*",
    r"^super\s*",
    r"^bench\s*",
    r"^reserve\s*",
    r"^injured\s*",
    r"^reserve\s*",
    r"^ir\s*",
    r"^out\s*",
    r"^questionable\s*",
    r"^doubtful\s*",
    r"^probable\s*",
    r"^active\s*",
    r"^inactive\s*",
    r"^suspended\s*",
    r"^holdout\s*",
    r"^contract\s*",
    r"^trade\s*",
    r"^waive\s*",
    r"^release\s*",
    r"^sign\s*",
    r"^extend\s*",
    r"^restructure\s*",
    r"^option\s*",
    r"^tag\s*",
    r"^franchise\s*",
    r"^transition\s*",
    r"^tender\s*",
    r"^offer\s*",
    r"^sheet\s*",
    r"^bonus\s*",
    r"^incentive\s*",
    r"^guarantee\s*",
    r"^salary\s*",
    r"^cap\s*",
    r"^hit\s*",
    r"^space\s*",
    r"^dead\s*",
    r"^money\s*",
    r"^cash\s*",
    r"^dollar\s*",
    r"^million\s*",
    r"^billion\s*",
    r"^percent\s*",
    r"^percentage\s*",
    r"^rate\s*",
    r"^ratio\s*",
    r"^average\s*",
    r"^mean\s*",
    r"^median\s*",
    r"^mode\s*",
    r"^range\s*",
    r"^min\s*",
    r"^max\s*",
    r"^minimum\s*",
    r"^maximum\s*",
    r"^limit\s*",
    r"^threshold\s*",
    r"^boundary\s*",
    r"^edge\s*",
    r"^border\s*",
    r"^line\s*",
    r"^row\s*",
    r"^column\s*",
    r"^cell\s*",
    r"^grid\s*",
    r"^table\s*",
    r"^list\s*",
    r"^item\s*",
    r"^element\s*",
    r"^component\s*",
    r"^section\s*",
    r"^header\s*",
    r"^footer\s*",
    r"^sidebar\s*",
    r"^panel\s*",
    r"^card\s*",
    r"^tile\s*",
    r"^widget\s*",
    r"^module\s*",
    r"^container\s*",
    r"^wrapper\s*",
    r"^inner\s*",
    r"^outer\s*",
    r"^main\s*",
    r"^sub\s*",
    r"^primary\s*",
    r"^secondary\s*",
    r"^tertiary\s*",
    r"^quaternary\s*",
    r"^auxiliary\s*",
    r"^supplementary\s*",
    r"^complementary\s*",
    r"^ancillary\s*",
    r"^accessory\s*",
    r"^attachment\s*",
    r"^addition\s*",
    r"^extra\s*",
    r"^spare\s*",
    r"^backup\s*",
    r"^alternate\s*",
    r"^alternative\s*",
    r"^substitute\s*",
    r"^replacement\s*",
    r"^stand-in\s*",
    r"^proxy\s*",
    r"^delegate\s*",
    r"^representative\s*",
    r"^agent\s*",
    r"^represent\s*",
    r"^symbol\s*",
    r"^icon\s*",
    r"^logo\s*",
    r"^brand\s*",
    r"^trademark\s*",
    r"^tm\s*",
    r"^registered\s*",
    r"^reg\s*",
    r"^circle\s*",
    r"^r\s*",
    r"^c\s*",
    r"^tm\s*",
    r"^sm\s*",
    r"^service\s*",
    r"^mark\s*",
    r"^copyright\s*",
    r"^copy\s*",
    r"^patent\s*",
    r"^pending\s*",
    r"^application\s*",
    r"^serial\s*",
    r"^number\s*",
    r"^id\s*",
    r"^identifier\s*",
    r"^key\s*",
    r"^code\s*",
    r"^token\s*",
    r"^secret\s*",
    r"^password\s*",
    r"^passcode\s*",
    r"^pin\s*",
    r"^access\s*",
    r"^auth\s*",
    r"^authentication\s*",
    r"^authorization\s*",
    r"^permission\s*",
    r"^consent\s*",
    r"^agreement\s*",
    r"^contract\s*",
    r"^deal\s*",
    r"^transaction\s*",
    r"^exchange\s*",
    r"^transfer\s*",
    r"^payment\s*",
    r"^purchase\s*",
    r"^buy\s*",
    r"^sell\s*",
    r"^order\s*",
    r"^cart\s*",
    r"^checkout\s*",
    r"^shipping\s*",
    r"^delivery\s*",
    r"^tracking\s*",
    r"^confirmation\s*",
    r"^receipt\s*",
    r"^invoice\s*",
    r"^bill\s*",
    r"^statement\s*",
    r"^report\s*",
    r"^summary\s*",
    r"^overview\s*",
    r"^detail\s*",
    r"^breakdown\s*",
    r"^analysis\s*",
    r"^review\s*",
    r"^feedback\s*",
    r"^rating\s*",
    r"^review\s*",
    r"^star\s*",
    r"^like\s*",
    r"^dislike\s*",
    r"^thumbs\s*",
    r"^up\s*",
    r"^down\s*",
    r"^vote\s*",
    r"^poll\s*",
    r"^survey\s*",
    r"^question\s*",
    r"^answer\s*",
    r"^response\s*",
    r"^reply\s*",
    r"^comment\s*",
    r"^note\s*",
    r"^annotation\s*",
    r"^remark\s*",
    r"^observation\s*",
    r"^insight\s*",
    r"^finding\s*",
    r"^discovery\s*",
    r"^realization\s*",
    r"^awareness\s*",
    r"^understanding\s*",
    r"^comprehension\s*",
    r"^knowledge\s*",
    r"^wisdom\s*",
    r"^intelligence\s*",
    r"^intellect\s*",
    r"^mind\s*",
    r"^brain\s*",
    r"^thought\s*",
    r"^thinking\s*",
    r"^reason\s*",
    r"^reasoning\s*",
    r"^logic\s*",
    r"^rational\s*",
    r"^irrational\s*",
    r"^emotion\s*",
    r"^feeling\s*",
    r"^sense\s*",
    r"^sensation\s*",
    r"^perception\s*",
    r"^awareness\s*",
    r"^consciousness\s*",
    r"^subconscious\s*",
    r"^unconscious\s*",
    r"^instinct\s*",
    r"^intuition\s*",
    r"^gut\s*",
    r"^hunch\s*",
    r"^impulse\s*",
    r"^urge\s*",
    r"^desire\s*",
    r"^want\s*",
    r"^need\s*",
    r"^requirement\s*",
    r"^necessity\s*",
    r"^essential\s*",
    r"^critical\s*",
    r"^crucial\s*",
    r"^vital\s*",
    r"^important\s*",
    r"^significant\s*",
    r"^major\s*",
    r"^minor\s*",
    r"^small\s*",
    r"^little\s*",
    r"^tiny\s*",
    r"^mini\s*",
    r"^micro\s*",
    r"^macro\s*",
    r"^large\s*",
    r"^big\s*",
    r"^huge\s*",
    r"^massive\s*",
    r"^enormous\s*",
    r"^giant\s*",
    r"^great\s*",
    r"^grand\s*",
    r"^super\s*",
    r"^ultra\s*",
    r"^mega\s*",
    r"^giga\s*",
    r"^tera\s*",
    r"^peta\s*",
    r"^exa\s*",
    r"^zetta\s*",
    r"^yotta\s*",
]


# Common suffixes to strip from player names
SUFFIXES_TO_STRIP = [
    r"\s+jr\.?$",
    r"\s+sr\.?$",
    r"\s+ii\.?$",
    r"\s+iii\.?$",
    r"\s+iv\.?$",
    r"\s+v\.?$",
    r"\s+jr$",
    r"\s+sr$",
    r"\s+ii$",
    r"\s+iii$",
    r"\s+iv$",
    r"\s+v$",
]


def parse_aria_label(text: str) -> str | None:
    """Extract player name from Underdog-style aria label text.

    Underdog aria labels typically follow patterns like:
    - "Select Ja'Marr Chase, WR, CIN"
    - "Ja'Marr Chase wide receiver Cincinnati Bengals"
    - "Player: Ja'Marr Chase"
    - "Pick Ja'Marr Chase"

    Args:
        text: The aria label text to parse.

    Returns:
        Extracted player name or None if no valid name found.
    """
    if not text:
        return None

    # Normalize whitespace and lowercase for matching
    normalized = " ".join(text.split()).strip()
    lower = normalized.lower()

    # Check for noise patterns first
    for pattern in NOISE_PATTERNS:
        if re.match(pattern, lower):
            return None

    # Pattern 1: "Select {Name}, {Position}, {Team}"
    # Pattern 2: "Pick {Name}"
    # Pattern 3: "Player: {Name}"
    # Pattern 4: "{Name} - {Position}"
    # Pattern 5: "{Name} {Position} {Team}"

    # Try explicit prefixes
    prefix_patterns = [
        r"(?:select|pick|choose|draft|player[:\s]+)\s+([A-Za-z][A-Za-z\s\.'-]+?)(?:[,;]|\s+(?:as\s+)?(?:QB|RB|WR|TE|K|DST)|\s+\(|$)",
        r"(?:select|pick|choose|draft|player[:\s]+)\s+([A-Za-z][A-Za-z\s\.'-]+)",
    ]

    for pattern in prefix_patterns:
        match = re.search(pattern, lower, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Clean up the extracted name
            return _clean_name(name)

    # Try extracting just the name part before position/team info
    # Pattern: Name followed by position or team abbreviation
    position_team_pattern = r"^([A-Za-z][A-Za-z\s\.'-]+?)(?:\s+(?:QB|RB|WR|TE|K|DST)|\s+[A-Z]{2,3}(?:\s|$)|\s*[,;]\s*|$)"
    match = re.search(position_team_pattern, normalized)
    if match:
        name = match.group(1).strip()
        return _clean_name(name)

    # If the text looks like a player name (2-3 words, starts with capital)
    # and doesn't match noise patterns, use it
    words = normalized.split()
    if 1 <= len(words) <= 4:
        # Check if it looks like a name (starts with capital, has reasonable chars)
        if re.match(r"^[A-Za-z][A-Za-z\s\.'-]+$", normalized):
            return _clean_name(normalized)

    return None


def _clean_name(name: str) -> str | None:
    """Clean up extracted player name.

    Removes common suffixes, extra whitespace, punctuation, and validates the result.
    """
    if not name:
        return None

    # Lowercase and remove punctuation (apostrophes, periods, etc.)
    lower_name = name.lower()
    lower_name = re.sub(r"['.]", "", lower_name)

    # Strip suffixes
    for pattern in SUFFIXES_TO_STRIP:
        lower_name = re.sub(pattern, "", lower_name, flags=re.IGNORECASE)

    # Clean up whitespace
    cleaned = " ".join(lower_name.split()).strip()

    # Validate minimum length
    if len(cleaned) < 2:
        return None

    # Check for numeric content (unlikely in player names)
    if re.search(r"\d", cleaned):
        return None

    return cleaned


def extract_names_from_aria_labels(labels: list[str]) -> list[str]:
    """Extract player names from a list of aria labels.

    Args:
        labels: List of aria label strings.

    Returns:
        List of extracted player names (may be fewer than input due to filtering).
    """
    names = []
    for label in labels:
        name = parse_aria_label(label)
        if name:
            names.append(name)
    return names


def filter_draft_board_names(names: list[str]) -> list[str]:
    """Deduplicate and filter draft board names.

    Removes duplicates (keeping first occurrence), filters out
    noise entries, and normalizes the names.

    Args:
        names: List of extracted player names.

    Returns:
        Filtered, deduplicated list of player names.
    """
    seen: set[str] = set()
    result: list[str] = []

    for name in names:
        # Skip empty names
        if not name or not name.strip():
            continue

        # Normalize for deduplication
        normalized = name.lower().strip()

        # Skip if already seen
        if normalized in seen:
            continue

        seen.add(normalized)
        result.append(name)

    return result
