"""AI niche classification from scraped social media profiles.

Feeds scraped post content to Gemini to classify user niches.
Used during onboarding (step 4) to pre-select niche checkboxes.
Results stored in local DB and synced to server.

Provider chain: Gemini (primary). Returns empty list on failure.
"""

import json
import logging
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.local_db import (
    get_all_scraped_profiles,
    get_scraped_profile,
    upsert_scraped_profile,
)
from utils.server_client import update_profile

logger = logging.getLogger(__name__)

VALID_NICHES = [
    "finance", "tech", "beauty", "fashion", "fitness", "gaming",
    "food", "travel", "education", "lifestyle", "business",
    "health", "entertainment", "crypto",
]

MAX_POSTS = 50
MAX_NICHES = 4


# ── Gemini Client ────────────────────────────────────────────────


def _get_gemini_client():
    """Initialize and return a Gemini client, or None if no API key."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — niche classification unavailable")
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.error("Failed to initialize Gemini client: %s", e)
        return None


# ── Prompt Construction ──────────────────────────────────────────


def _build_prompt(scraped_profiles: dict) -> str:
    """Build classification prompt from scraped profile data.

    Args:
        scraped_profiles: dict keyed by platform, each with 'recent_posts' list.

    Returns:
        Prompt string with post texts and classification instructions.
    """
    post_texts = []
    for platform, data in scraped_profiles.items():
        for post in data.get("recent_posts", []):
            # Reddit uses 'title', other platforms use 'text'
            text = post.get("text") or post.get("title") or ""
            text = text.strip()
            if text:
                post_texts.append(text)

    # Truncate to MAX_POSTS
    post_texts = post_texts[:MAX_POSTS]

    niches_list = ", ".join(VALID_NICHES)
    posts_block = "\n".join(f"- {t}" for t in post_texts) if post_texts else "(no posts)"

    return f"""Based on these social media posts by a single user, classify their content niches.

Choose 1-4 niches from this list ONLY:
{niches_list}

Posts:
{posts_block}

Return ONLY a JSON array of niche strings, e.g.: ["finance", "tech"]
Do not include any other text, explanation, or markdown formatting."""


# ── Response Parsing ─────────────────────────────────────────────


def _parse_niches_response(text: str) -> list[str]:
    """Parse Gemini response into a validated list of niche strings.

    Handles markdown fences, surrounding text, mixed case, duplicates,
    and filters out any niches not in VALID_NICHES.

    Returns empty list on parse failure.
    """
    text = text.strip()

    # Strip markdown code fences
    if "```" in text:
        text = re.sub(r"```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*", "", text)
        text = text.strip()

    # Try to extract a JSON array from the text
    parsed = None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Try to find a JSON array in surrounding text
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                pass

    if not isinstance(parsed, list):
        logger.warning("Could not parse niches response: %s", text[:200])
        return []

    # Filter: only strings, lowercase, in VALID_NICHES, deduplicated
    seen = set()
    result = []
    for item in parsed:
        if not isinstance(item, str):
            continue
        niche = item.strip().lower()
        if niche in VALID_NICHES and niche not in seen:
            seen.add(niche)
            result.append(niche)

    return result


# ── Main Classification ──────────────────────────────────────────


async def classify_niches(scraped_profiles: dict) -> list[str]:
    """Feed scraped post content to Gemini to classify user niches.

    Args:
        scraped_profiles: dict keyed by platform, each with 'recent_posts' list.

    Returns:
        List of niche strings from VALID_NICHES (typically 1-4 niches).
        Empty list on failure or when no posts are available.
    """
    # Check if there are any posts at all
    total_posts = 0
    for platform, data in scraped_profiles.items():
        for post in data.get("recent_posts", []):
            text = post.get("text") or post.get("title") or ""
            if text.strip():
                total_posts += 1

    if total_posts == 0:
        logger.info("No posts to classify — returning empty niches")
        return []

    # Build prompt
    prompt = _build_prompt(scraped_profiles)

    # Try Gemini
    client = _get_gemini_client()
    if client is None:
        logger.warning("No Gemini client — cannot classify niches")
        return []

    try:
        logger.info("Classifying niches via Gemini (%d posts)...", total_posts)
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        niches = _parse_niches_response(response.text)

        # Cap at MAX_NICHES
        niches = niches[:MAX_NICHES]

        logger.info("Detected niches: %s", niches)
        return niches

    except Exception as e:
        logger.error("Gemini niche classification failed: %s", e)
        return []


# ── Integration with Profile Scraper ─────────────────────────────


async def classify_and_store(platforms: list[str] = None):
    """Load scraped profiles from local DB, run classification, store results.

    Reads all scraped profiles, builds the scraped_profiles dict,
    calls classify_niches(), updates local DB, and syncs to server.
    """
    profiles = get_all_scraped_profiles()
    if not profiles:
        logger.info("No scraped profiles — skipping niche classification")
        return

    # Filter by platforms if specified
    if platforms:
        profiles = [p for p in profiles if p["platform"] in platforms]
        if not profiles:
            logger.info("No matching profiles for platforms %s", platforms)
            return

    # Build the scraped_profiles dict from DB rows
    scraped_profiles = {}
    for p in profiles:
        try:
            recent_posts = json.loads(p.get("recent_posts", "[]"))
        except (json.JSONDecodeError, TypeError):
            recent_posts = []
        scraped_profiles[p["platform"]] = {"recent_posts": recent_posts}

    # Classify
    niches = await classify_niches(scraped_profiles)

    if not niches:
        logger.info("No niches detected — leaving DB unchanged")
        return

    # Store results: update each scraped_profile's ai_niches field
    niches_json = json.dumps(niches)
    for p in profiles:
        upsert_scraped_profile(
            platform=p["platform"],
            follower_count=p.get("follower_count", 0),
            following_count=p.get("following_count", 0),
            bio=p.get("bio"),
            display_name=p.get("display_name"),
            profile_pic_url=p.get("profile_pic_url"),
            recent_posts=p.get("recent_posts", "[]"),
            engagement_rate=p.get("engagement_rate", 0.0),
            posting_frequency=p.get("posting_frequency", 0.0),
            ai_niches=niches_json,
        )
    logger.info("Stored niches %s for %d platform(s)", niches, len(profiles))

    # Sync to server
    try:
        update_profile(ai_detected_niches=niches)
        logger.info("Synced ai_detected_niches to server")
    except Exception as e:
        logger.error("Failed to sync niches to server: %s", e)


# ── Standalone Retrieval (for onboarding UI) ─────────────────────


def get_detected_niches() -> list[str]:
    """Get the most recently detected niches from local DB.

    Reads ai_niches from all scraped_profiles and returns the
    deduplicated, sorted union. Used by onboarding UI to show
    pre-selected niche checkboxes.

    Returns:
        Sorted list of unique niche strings.
    """
    profiles = get_all_scraped_profiles()
    if not profiles:
        return []

    all_niches = set()
    for p in profiles:
        raw = p.get("ai_niches", "[]")
        try:
            niches = json.loads(raw)
            if isinstance(niches, list):
                for n in niches:
                    if isinstance(n, str) and n.strip().lower() in VALID_NICHES:
                        all_niches.add(n.strip().lower())
        except (json.JSONDecodeError, TypeError):
            logger.debug("Malformed ai_niches for %s: %s", p.get("platform"), raw)

    return sorted(all_niches)


# ── CLI Entry Point ──────────────────────────────────────────────


async def _main():
    """Run niche classification on all scraped profiles."""
    import argparse

    parser = argparse.ArgumentParser(description="Classify user niches from scraped profiles")
    parser.add_argument(
        "--platforms", nargs="*",
        help="Platforms to classify (default: all with scraped data)",
    )
    args = parser.parse_args()

    await classify_and_store(args.platforms)

    niches = get_detected_niches()
    print(f"Detected niches: {niches}")


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level="INFO",
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(ROOT / "logs" / "niche_classifier.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    asyncio.run(_main())
