"""Content quality scoring with campaign brief adherence checks.

Combines the existing quality rules (banned phrases, length, hooks) from
quality_node.py with a new brief-adherence scorer so campaign content can
be evaluated against what the company actually asked for.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Re-export the existing quality checks so callers get a single import
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from agents.quality_node import (
    _check_banned_phrases,
    _check_length,
    _check_emotion_hook,
    _check_value,
    _score_draft,
)


# ── Brief adherence ──────────────────────────────────────────────


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace for fuzzy matching."""
    return re.sub(r"\s+", " ", text.lower().strip())


def _extract_keywords(text: str, min_length: int = 4) -> set[str]:
    """Extract meaningful keywords from text (words >= min_length chars)."""
    stop_words = {
        "this", "that", "with", "from", "have", "been", "were", "they",
        "their", "about", "would", "could", "should", "which", "there",
        "these", "those", "than", "then", "also", "just", "more", "some",
        "when", "what", "your", "will", "each", "make", "like", "into",
        "very", "most", "such", "only", "over", "other", "after", "them",
        "being", "does", "doing", "during", "before",
    }
    words = set(re.findall(r"[a-z]{%d,}" % min_length, text.lower()))
    return words - stop_words


def check_brief_adherence(
    content: str,
    campaign_brief: str,
    content_guidance: str = "",
    must_include: list[str] | None = None,
) -> dict:
    """Check how well generated content adheres to the campaign brief.

    Returns: {"score": 0-100, "issues": ["Missing must-include phrase: 'Visit example.com'"]}

    Scoring:
    - Starts at 100
    - Each missing must-include phrase: -20 points
    - Low keyword overlap with brief: -15 points
    - Low keyword overlap with content_guidance: -10 points
    - Empty brief = 100 (no requirements to violate)
    """
    issues: list[str] = []

    # No brief means nothing to check against
    if not campaign_brief and not content_guidance and not must_include:
        return {"score": 100, "issues": []}

    score = 100.0
    content_norm = _normalize(content) if content else ""

    # ── Must-include phrases ──────────────────────────────────────
    if must_include:
        for phrase in must_include:
            if not phrase or not phrase.strip():
                continue
            phrase_norm = _normalize(phrase)
            if phrase_norm not in content_norm:
                issues.append(f"Missing must-include phrase: '{phrase.strip()}'")
                score -= 20

    # ── Brief keyword overlap ─────────────────────────────────────
    if campaign_brief:
        brief_keywords = _extract_keywords(campaign_brief)
        if brief_keywords:
            content_keywords = _extract_keywords(content) if content else set()
            overlap = brief_keywords & content_keywords
            overlap_ratio = len(overlap) / len(brief_keywords) if brief_keywords else 1.0
            if overlap_ratio < 0.2:
                issues.append(
                    f"Low brief relevance: only {len(overlap)}/{len(brief_keywords)} "
                    f"key terms from brief appear in content"
                )
                score -= 15

    # ── Content guidance keyword overlap ──────────────────────────
    if content_guidance:
        guidance_keywords = _extract_keywords(content_guidance)
        if guidance_keywords:
            content_keywords = _extract_keywords(content) if content else set()
            overlap = guidance_keywords & content_keywords
            overlap_ratio = len(overlap) / len(guidance_keywords) if guidance_keywords else 1.0
            if overlap_ratio < 0.2:
                issues.append(
                    f"Low guidance adherence: only {len(overlap)}/{len(guidance_keywords)} "
                    f"guidance terms reflected in content"
                )
                score -= 10

    score = max(0, min(100, score))
    return {"score": int(score), "issues": issues}


# ── Combined quality score ────────────────────────────────────────


def _rules_score(content: str, platform: str) -> tuple[float, list[str]]:
    """Run existing quality checks and return (score, issues)."""
    issues: list[str] = []
    issues.extend(_check_banned_phrases(content))
    issues.extend(_check_length(content, platform))
    issues.extend(_check_emotion_hook(content))
    issues.extend(_check_value(content))
    score = _score_draft(content, platform, issues)
    return score, issues


def combined_quality_score(
    content: str,
    platform: str,
    campaign_brief: str,
    content_guidance: str = "",
    must_include: list[str] | None = None,
) -> dict:
    """Combined score = (existing_rules_score + brief_adherence_score) / 2.

    Returns: {"score": 0-100, "issues": [...], "warning": True if < 60}
    """
    # Rules-based score (banned phrases, length, hooks, value)
    rules_result, rules_issues = _rules_score(content, platform)

    # Brief adherence score
    adherence_result = check_brief_adherence(
        content, campaign_brief, content_guidance, must_include
    )

    # Average the two scores
    combined = (rules_result + adherence_result["score"]) / 2
    combined = int(max(0, min(100, combined)))

    all_issues = rules_issues + adherence_result["issues"]

    return {
        "score": combined,
        "rules_score": int(rules_result),
        "adherence_score": adherence_result["score"],
        "issues": all_issues,
        "warning": combined < 60,
    }
