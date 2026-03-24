"""Automated content screening for prohibited campaign categories.

Keyword-based screening with word-boundary matching to minimise false positives.
Flagged campaigns require manual admin review before activation.
"""

import re

PROHIBITED_KEYWORDS: dict[str, list[str]] = {
    "adult": [
        "porn", "pornography", "xxx", "nude", "nudes", "nudity",
        "onlyfans", "escort", "escorts", "sex work", "sex worker",
        "sexually explicit", "erotic", "adult content", "adult entertainment",
        "strip club", "cam girl", "cam boy", "sex toy", "sex toys",
    ],
    "gambling": [
        "casino", "casinos", "betting", "sports betting", "online betting",
        "slots", "slot machine", "poker", "wager", "wagering",
        "bookmaker", "bookie", "roulette", "blackjack", "gambling",
        "sportsbook", "daily fantasy", "parlay",
    ],
    "drugs": [
        "marijuana", "cannabis", "cocaine", "opioid", "opioids",
        "drug dealer", "drug dealing", "meth", "methamphetamine",
        "heroin", "fentanyl", "psychedelic", "psychedelics",
        "buy drugs", "sell drugs", "drug sale", "drug sales",
        "controlled substance", "controlled substances",
    ],
    "weapons": [
        "gun sale", "gun sales", "firearms dealer", "firearms dealers",
        "ammunition", "weapon shop", "weapon sales", "buy guns",
        "sell guns", "gun dealer", "illegal weapons", "assault rifle",
        "automatic weapon", "automatic weapons",
    ],
    "financial_fraud": [
        "guaranteed returns", "guaranteed profit", "guaranteed profits",
        "get rich quick", "pyramid scheme", "pyramid schemes",
        "ponzi", "ponzi scheme", "forex signals guaranteed",
        "double your money", "risk free investment", "risk-free returns",
        "no risk investment", "money laundering", "100% returns",
        "500% returns", "1000% returns",
    ],
    "hate_speech": [
        "white supremacy", "white supremacist", "white power",
        "neo nazi", "neo-nazi", "hate group", "hate groups",
        "racial superiority", "ethnic cleansing",
        "kill all", "death to",
    ],
}

# Pre-compile regex patterns with word boundaries for each keyword.
# Patterns are cached at module level so they're compiled once.
_COMPILED_PATTERNS: dict[str, list[tuple[str, re.Pattern]]] = {}

for _category, _keywords in PROHIBITED_KEYWORDS.items():
    _COMPILED_PATTERNS[_category] = []
    for _kw in _keywords:
        # Use word boundaries (\b) for single-word keywords.
        # For multi-word phrases, anchor at the start and end of the phrase.
        pattern = re.compile(r"\b" + re.escape(_kw) + r"\b", re.IGNORECASE)
        _COMPILED_PATTERNS[_category].append((_kw, pattern))


def screen_campaign(
    title: str,
    brief: str,
    content_guidance: str = "",
) -> dict:
    """Screen campaign text for prohibited content categories.

    Checks title + brief + content_guidance against all keyword lists.
    Uses word-boundary matching to reduce false positives (e.g., "grass" won't
    match "ass", "therapist" won't match anything unintended).

    Returns:
        {
            "flagged": bool,
            "flagged_keywords": ["keyword1", "keyword2"],
            "categories": ["adult", "gambling"],
        }
    """
    # Combine all text fields for scanning
    combined_text = f"{title} {brief} {content_guidance or ''}"

    flagged_keywords: list[str] = []
    flagged_categories: set[str] = set()

    for category, patterns in _COMPILED_PATTERNS.items():
        for keyword, pattern in patterns:
            if pattern.search(combined_text):
                if keyword not in flagged_keywords:
                    flagged_keywords.append(keyword)
                flagged_categories.add(category)

    return {
        "flagged": len(flagged_keywords) > 0,
        "flagged_keywords": flagged_keywords,
        "categories": sorted(flagged_categories),
    }
