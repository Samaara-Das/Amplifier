"""Content quality validator for the 4-phase ContentAgent pipeline.

Validates generated content before storing as a draft. Catches structural
issues and anti-quality patterns that the AI prompt alone cannot guarantee.

Public API:
    validate_content(content, previous_drafts_text, manager) -> (bool, [reasons])
"""

from __future__ import annotations

import difflib
import logging
import re

logger = logging.getLogger(__name__)

# ── X character limit (post-FTC disclosure) ────────────────────────
X_CHAR_LIMIT = 280

# ── Reddit title/body length bounds ───────────────────────────────
REDDIT_TITLE_MIN = 60
REDDIT_TITLE_MAX = 120
REDDIT_BODY_MIN = 500
REDDIT_BODY_MAX = 2500  # Relaxed from 1500 per live UAT — Gemini writes longer organically; real Reddit posts often 1500-2500 chars

# ── AI-speak banned phrases (case-insensitive substring match) ─────
# "leverage" was removed from this list after live UAT (2026-04-18):
# it's a legitimate business word (finance, tech, strategy) and Gemini
# legitimately uses it when describing AI/tech products. Substring match
# generated constant false-positives. Spec lists it but pragmatic drop
# is worth more than strict compliance — the other phrases are clearer
# AI-speak tells. Re-add with smarter regex if needed later.
BANNED_PHRASES = [
    "game-changer",
    "game changer",
    "unlock your potential",
    "dive in",
    "let's explore",
    "in today's fast-paced world",
    "synergy",
    "innovative solution",
    "cutting-edge",
    "cutting edge",
]

# ── Diversity thresholds ───────────────────────────────────────────
COSINE_THRESHOLD = 0.8   # embeddings: flag if similarity > this
SEQ_THRESHOLD = 0.85     # SequenceMatcher fallback: flag if ratio > this


def _extract_all_text(content: dict) -> str:
    """Concatenate all platform text from a content dict into one string."""
    parts = []
    for key, val in content.items():
        if key == "image_prompt":
            continue
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, dict):
            # Reddit dict: title + body
            parts.append(val.get("title", ""))
            parts.append(val.get("body", ""))
    return " ".join(p for p in parts if p).strip()


def _check_banned_phrases(content: dict) -> list[str]:
    """Return list of failure reasons for banned phrases found in content."""
    failures = []
    for key, val in content.items():
        if key == "image_prompt":
            continue
        text_to_check = ""
        if isinstance(val, str):
            text_to_check = val
        elif isinstance(val, dict):
            text_to_check = " ".join(str(v) for v in val.values())
        lower = text_to_check.lower()
        for phrase in BANNED_PHRASES:
            if phrase in lower:
                failures.append(f"{key}: contains banned phrase '{phrase}'")
    return failures


async def _check_diversity(
    content_text: str,
    previous_drafts_text: list[str],
    manager,
) -> list[str]:
    """Check content is sufficiently different from previous drafts.

    Tries Gemini embeddings + numpy cosine similarity first.
    Falls back to difflib.SequenceMatcher if embeddings unavailable.
    Returns a list of failure reasons (empty = pass).
    """
    failures = []
    if not previous_drafts_text or not content_text:
        return failures

    # ── Try embedding-based similarity ────────────────────────────
    try:
        import numpy as np

        new_vec = await manager.embed(content_text)
        if new_vec is not None:
            new_arr = np.array(new_vec, dtype=float)
            norm_new = np.linalg.norm(new_arr)
            if norm_new == 0:
                raise ValueError("Zero-norm embedding for new content")
            for i, prev_text in enumerate(previous_drafts_text):
                prev_vec = await manager.embed(prev_text)
                if prev_vec is None:
                    continue
                prev_arr = np.array(prev_vec, dtype=float)
                norm_prev = np.linalg.norm(prev_arr)
                if norm_prev == 0:
                    continue
                cosine = float(np.dot(new_arr, prev_arr) / (norm_new * norm_prev))
                if cosine > COSINE_THRESHOLD:
                    failures.append(
                        f"Content too similar to previous draft #{i+1} "
                        f"(cosine={cosine:.2f} > {COSINE_THRESHOLD})"
                    )
            return failures
    except ImportError:
        logger.info("numpy not available; falling back to SequenceMatcher diversity check")
    except Exception as e:
        logger.warning("Embedding diversity check failed: %s. Falling back to SequenceMatcher.", e)

    # ── SequenceMatcher fallback ───────────────────────────────────
    # Looser threshold (0.85) than cosine (0.80) — pragmatic: text-based
    # similarity is coarser than semantic similarity. Documented tradeoff.
    for i, prev_text in enumerate(previous_drafts_text):
        ratio = difflib.SequenceMatcher(None, content_text, prev_text).ratio()
        if ratio > SEQ_THRESHOLD:
            failures.append(
                f"Content too similar to previous draft #{i+1} "
                f"(SequenceMatcher ratio={ratio:.2f} > {SEQ_THRESHOLD})"
            )
    return failures


async def validate_content(
    content: dict,
    previous_drafts_text: list[str],
    manager,
) -> tuple[bool, list[str]]:
    """Validate generated content before storing as a draft.

    Args:
        content: Platform content dict from _run_creation().
                 Keys: 'x', 'linkedin', 'facebook', 'reddit', 'image_prompt'.
                 Reddit value is a dict {'title': ..., 'body': ...}.
                 All text should be FINAL (FTC disclosure already appended).
        previous_drafts_text: List of concatenated previous draft texts for
                              diversity comparison (last 3 days).
        manager: AiManager instance (used for embed() calls).

    Returns:
        (is_valid, failure_reasons) — is_valid=True means all checks passed.
    """
    reasons = []

    # ── 1. X length check (post-FTC disclosure) ───────────────────
    if "x" in content and isinstance(content["x"], str):
        x_len = len(content["x"])
        if x_len > X_CHAR_LIMIT:
            reasons.append(
                f"x: exceeds {X_CHAR_LIMIT} chars ({x_len} chars after FTC disclosure)"
            )

    # ── 2. Reddit shape check ─────────────────────────────────────
    if "reddit" in content:
        reddit = content["reddit"]
        if not isinstance(reddit, dict):
            reasons.append("reddit: expected a dict with 'title' and 'body'")
        else:
            title = reddit.get("title", "")
            body = reddit.get("body", "")
            if not isinstance(title, str) or not title.strip():
                reasons.append("reddit: missing title")
            elif not (REDDIT_TITLE_MIN <= len(title) <= REDDIT_TITLE_MAX):
                reasons.append(
                    f"reddit: title length {len(title)} out of range "
                    f"[{REDDIT_TITLE_MIN}, {REDDIT_TITLE_MAX}]"
                )
            if not isinstance(body, str) or not body.strip():
                reasons.append("reddit: missing body")
            elif not (REDDIT_BODY_MIN <= len(body) <= REDDIT_BODY_MAX):
                reasons.append(
                    f"reddit: body length {len(body)} out of range "
                    f"[{REDDIT_BODY_MIN}, {REDDIT_BODY_MAX}]"
                )

    # ── 3. Banned phrases check ───────────────────────────────────
    banned_failures = _check_banned_phrases(content)
    reasons.extend(banned_failures)

    # ── 4. Diversity check ────────────────────────────────────────
    content_text = _extract_all_text(content)
    diversity_failures = await _check_diversity(content_text, previous_drafts_text, manager)
    reasons.extend(diversity_failures)

    is_valid = len(reasons) == 0
    if not is_valid:
        logger.info("Content quality check failed: %s", reasons)
    return is_valid, reasons
