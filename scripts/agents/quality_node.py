"""Quality node — validates drafts against content-templates.md hard rules.

Scores each draft 0-100. Flags issues but does NOT re-draft (score and move on).
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

# Hard rules from content-templates.md
BANNED_PHRASES = [
    # AI-sounding
    "in today's fast-paced world", "let's dive in", "here's the thing",
    "game-changer", "leverage", "unlock", "in this post i'll discuss",
    "let me explain", "without further ado",
    # Trading experience claims
    "i traded", "my trades", "i got stopped out", "my p&l",
    "my win rate on live trades", "i lost money trading",
    # Location/age reveals
    "school", "college", "university", "homework",
    "india", " ist ", " ist,", " ist.", "rupee", "rupees", "nse", "bse", "nifty", "sensex",
]

PLATFORM_LIMITS = {
    "x": {"min_chars": 20, "max_chars": 280},
    "linkedin": {"min_chars": 200, "max_chars": 1500},
    "facebook": {"min_chars": 50, "max_chars": 800},
    "reddit_title": {"min_chars": 20, "max_chars": 120},
    "reddit_body": {"min_chars": 200, "max_chars": 1500},
}


def _check_banned_phrases(text: str) -> list[str]:
    """Check for banned phrases (case-insensitive)."""
    text_lower = text.lower()
    found = []
    for phrase in BANNED_PHRASES:
        if phrase in text_lower:
            found.append(f"Banned phrase: '{phrase}'")
    return found


def _check_length(text: str, platform: str) -> list[str]:
    """Check character length against platform limits."""
    issues = []
    limits = PLATFORM_LIMITS.get(platform)
    if not limits:
        return issues
    if len(text) < limits["min_chars"]:
        issues.append(f"Too short ({len(text)} chars, min {limits['min_chars']})")
    if len(text) > limits["max_chars"]:
        issues.append(f"Too long ({len(text)} chars, max {limits['max_chars']})")
    return issues


def _check_emotion_hook(text: str) -> list[str]:
    """Check if the first sentence has an emotional hook."""
    # Simple heuristic: first sentence should contain emotionally-charged words
    first_line = text.split("\n")[0] if text else ""
    first_sentence = first_line.split(".")[0] if first_line else ""

    emotion_signals = [
        "money", "lose", "lost", "stop", "mistake", "wrong", "secret",
        "never", "always", "most traders", "90%", "fail", "fear",
        "free", "freedom", "quit", "sleep", "autopilot", "passive",
        "cheat", "edge", "smart", "hack", "trick", "proof", "backtest",
        "ai", "job", "replace", "future", "skill", "protect",
        "?", "!", "don't", "why", "how", "what if",
    ]

    first_lower = first_sentence.lower()
    has_emotion = any(signal in first_lower for signal in emotion_signals)

    if not has_emotion and len(first_sentence) > 10:
        return ["First sentence lacks emotional hook — consider adding fear/greed/freedom trigger"]
    return []


def _check_value(text: str) -> list[str]:
    """Check if the post delivers actionable value."""
    # Heuristic: should contain specific, actionable language
    action_signals = [
        "here's how", "try this", "step", "do this", "buy when",
        "sell when", "look for", "watch for", "the rule", "this means",
        "you can", "set your", "place your", "use this", "example",
        "%", "$", "data shows", "backtested", "tested", "found",
    ]

    text_lower = text.lower()
    has_value = any(signal in text_lower for signal in action_signals)

    if not has_value and len(text) > 100:
        return ["Post may lack actionable value — add specifics, numbers, or 'do this' instructions"]
    return []


def _score_draft(text: str, platform: str, issues: list[str]) -> float:
    """Calculate quality score 0-100."""
    score = 100.0

    # Deduct for issues
    for issue in issues:
        if "Banned phrase" in issue:
            score -= 25  # Critical
        elif "Too short" in issue or "Too long" in issue:
            score -= 15
        elif "emotional hook" in issue.lower():
            score -= 10
        elif "actionable value" in issue.lower():
            score -= 10
        else:
            score -= 5

    # Bonus for good signals
    text_lower = text.lower() if isinstance(text, str) else ""
    if any(h in text_lower for h in ["#", "hashtag"]):
        score += 2  # Has hashtags (good for most platforms)
    if "?" in text:
        score += 3  # Engagement question
    if any(w in text_lower for w in ["backtest", "data", "tested", "proof"]):
        score += 5  # Data-driven

    return max(0, min(100, score))


def quality_node(state: dict) -> dict:
    """Validate all drafts against hard rules and score them."""
    drafts = state.get("drafts", {})
    quality_scores = {}
    quality_issues = {}

    for platform, draft in drafts.items():
        if not draft:
            quality_scores[platform] = 0
            quality_issues[platform] = ["Empty draft"]
            continue

        # Get text content
        if isinstance(draft, dict):
            # Reddit format: {"title": ..., "body": ...}
            title = draft.get("title", "")
            body = draft.get("body", "")
            text = f"{title}\n{body}"

            issues = []
            issues.extend(_check_banned_phrases(text))
            issues.extend(_check_length(title, "reddit_title"))
            issues.extend(_check_length(body, "reddit_body"))
            issues.extend(_check_emotion_hook(title))
            issues.extend(_check_value(body))
        else:
            text = draft
            issues = []
            issues.extend(_check_banned_phrases(text))
            issues.extend(_check_length(text, platform))
            issues.extend(_check_emotion_hook(text))
            issues.extend(_check_value(text))

        score = _score_draft(text, platform, issues)
        quality_scores[platform] = score
        quality_issues[platform] = issues

        if issues:
            logger.warning("%s quality issues (score %.0f): %s", platform, score, issues)
        else:
            logger.info("%s passed quality check (score %.0f)", platform, score)

    return {"quality_scores": quality_scores, "quality_issues": quality_issues}
