"""AI-powered profile scraping — 3-tier extraction pipeline.

Tier 1 (TEXT — cheapest, try first):
    Extract all visible page text, send to text AI model (~500-1500 tokens).
    Captures 80%+ of profile data without vision tokens.

Tier 2 (CSS SELECTORS — free, supplement tier 1):
    Use browser automation to query specific elements. Handled by profile_scraper.py.

Tier 3 (SCREENSHOT + VISION — expensive, last resort):
    Take targeted screenshot, send to Gemini Vision. Only if text extraction
    fails to find key fields (no follower count, no display name).

Usage:
    # Tier 1 — text extraction (preferred)
    result = await ai_scrape_profile_from_text("x", page)

    # Tier 3 — screenshot fallback (only if tier 1 misses key fields)
    result = await ai_scrape_profile("x", page)

Falls back gracefully: if the Gemini API key is missing or the call fails,
callers should fall back to CSS-based scraping.
"""

import base64
import json
import logging
import re
from typing import Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)


# ── Extraction Prompts ───────────────────────────────────────────


def _build_extraction_prompt(platform: str) -> str:
    """Build a platform-specific extraction prompt for Gemini Vision."""

    platform_hints = {
        "x": (
            "This is a screenshot of an X (Twitter) profile page. "
            "Look for: display name, @username, bio text, follower count, "
            "following count, and recent tweets with their engagement metrics "
            "(likes, retweets/reposts, replies, views). "
            "Tweets are listed below the profile header as cards with text and "
            "engagement buttons (heart for likes, arrows for retweets, chat "
            "bubble for replies, bar chart for views)."
        ),
        "linkedin": (
            "This is a screenshot of a LinkedIn profile page. "
            "Look for: display name, headline (used as bio), connections or "
            "follower count, about section, work experience entries, and "
            "recent posts with engagement (reactions, comments). "
            "LinkedIn shows connections count near the top and experience "
            "in a dedicated section below."
        ),
        "facebook": (
            "This is a screenshot of a Facebook profile page. "
            "Look for: display name, bio/intro text, friends count (treat as "
            "followers), and recent posts with engagement (likes/reactions, "
            "comments, shares). "
            "Facebook shows friends count on the profile header and posts "
            "in a timeline below."
        ),
        "reddit": (
            "This is a screenshot of a Reddit user profile page. "
            "Look for: display name/username, bio, karma count (treat as "
            "follower_count proxy if no explicit followers shown), follower "
            "count, cake day / account age, and recent posts with their "
            "scores (upvotes), comments count, and subreddit names. "
            "Reddit shows karma prominently and posts as cards with vote "
            "arrows and score."
        ),
    }

    hint = platform_hints.get(platform, f"This is a screenshot of a {platform} profile page.")

    return f"""{hint}

Extract ALL visible profile data from this screenshot. Return a JSON object with EXACTLY this schema (use null for fields you cannot find, 0 for numeric fields you cannot find):

{{
    "display_name": "the user's display name or username",
    "bio": "bio/headline/description text, or null if not visible",
    "follower_count": 0,
    "following_count": 0,
    "recent_posts": [
        {{
            "text": "post text content (first 300 chars)",
            "likes": 0,
            "comments": 0,
            "reposts": 0,
            "views": 0,
            "posted_at": "relative time like '2h ago' or '3d' or null",
            "subreddit": "subreddit name if Reddit, otherwise null"
        }}
    ],
    "posting_frequency": 0.0,
    "profile_data": {{
        "about": "about/summary section text or null",
        "experience": null,
        "karma": null,
        "reddit_age": null
    }},
    "ai_detected_niches": ["list", "of", "content", "niches"],
    "content_quality": "low or medium or high",
    "audience_demographics_estimate": {{
        "age_range": "estimated age range like '18-34' or 'unknown'",
        "interests": ["list", "of", "inferred", "interests"]
    }}
}}

Rules:
- Extract up to 10 recent posts if visible
- For engagement metrics, parse abbreviated numbers: 1.2K = 1200, 3.4M = 3400000
- For follower/following counts, also parse abbreviated numbers
- posting_frequency: estimate posts per day based on post timestamps visible (e.g., if you see 5 posts from the last 7 days, that's ~0.71)
- ai_detected_niches: classify the user's content into 1-5 topic niches based on their bio and posts (e.g., "technology", "finance", "fitness", "cooking", "travel")
- content_quality: "low" = mostly reposts/low effort, "medium" = original but basic, "high" = thoughtful/detailed original content
- audience_demographics_estimate: infer from content topics and language style
- profile_data.experience: for LinkedIn, extract as a list of {{"title": "...", "company": "...", "duration": "..."}} objects. null for other platforms.
- profile_data.karma: Reddit karma score (integer), null for other platforms
- profile_data.reddit_age: Reddit account age string (e.g., "2y 3mo"), null for other platforms

Return ONLY valid JSON, no markdown fences, no explanation."""


# ── Text Extraction Prompt ───────────────────────────────────────


def _build_text_extraction_prompt(platform: str, page_text: str) -> str:
    """Build a prompt for text-based extraction (Tier 1 — no vision)."""

    platform_context = {
        "x": (
            "This is the full text content extracted from an X (Twitter) profile page. "
            "The text contains the user's name, @handle, bio, follower/following counts, "
            "and their recent tweets with engagement metrics (likes, retweets, replies, views). "
            "Numbers may be abbreviated (1.2K = 1200, 3.4M = 3400000)."
        ),
        "linkedin": (
            "This is the full text content extracted from a LinkedIn profile page. "
            "The text contains the user's name, headline, location, follower/connection count, "
            "About section, work experience, education, skills, and recent posts with "
            "reactions/comments. Sections may include 'Show all' or '...more' markers."
        ),
        "facebook": (
            "This is the full text content extracted from a Facebook profile page. "
            "The text contains the user's name, friends count, bio/intro, personal details "
            "(city, hometown, work, education), and recent posts with likes/comments/shares."
        ),
        "reddit": (
            "This is the full text content extracted from a Reddit user profile page. "
            "The text contains the username, karma, account age, follower count, "
            "achievements/trophies, and recent posts with scores, comments, "
            "and subreddit names (r/...)."
        ),
    }

    context = platform_context.get(platform, f"This is text from a {platform} profile page.")

    return f"""{context}

Here is the extracted text:

---
{page_text[:8000]}
---

Extract ALL profile data from this text. Return a JSON object with EXACTLY this schema (use null for fields you cannot find, 0 for numeric fields you cannot find):

{{
    "display_name": "the user's display name",
    "username": "handle or username (with @ for X, u/ for Reddit)",
    "bio": "bio/headline/description text, or null",
    "follower_count": 0,
    "following_count": 0,
    "post_count": 0,
    "location": "location if shown, or null",
    "website": "website URL if shown, or null",
    "join_date": "join date or account age if shown, or null",
    "verified": false,
    "recent_posts": [
        {{
            "text": "post text (first 300 chars)",
            "likes": 0,
            "comments": 0,
            "reposts": 0,
            "views": 0,
            "posted_at": "relative time like '2h ago' or date",
            "subreddit": "subreddit name if Reddit, otherwise null",
            "has_media": false
        }}
    ],
    "posting_frequency": 0.0,
    "profile_data": {{
        "about": "about/summary section text or null",
        "experience": null,
        "education": null,
        "skills": null,
        "karma": null,
        "reddit_age": null,
        "active_subreddits": null,
        "personal_details": null
    }},
    "ai_detected_niches": ["list", "of", "content", "niches"],
    "content_quality": "low or medium or high",
    "audience_demographics_estimate": {{
        "age_range": "estimated age range like '18-34' or 'unknown'",
        "interests": ["list", "of", "inferred", "interests"]
    }}
}}

Rules:
- Extract up to 10 recent posts if visible in the text
- Parse abbreviated numbers: 1.2K = 1200, 3.4M = 3400000
- posting_frequency: estimate posts per day from timestamps visible
- ai_detected_niches: classify into 1-5 topic niches from bio + posts
- content_quality: "low" = reposts/low effort, "medium" = basic original, "high" = thoughtful original
- For LinkedIn: extract experience as [{{"title":"...","company":"...","duration":"..."}}]
- For LinkedIn: extract education as [{{"school":"...","degree":"...","dates":"..."}}]
- For LinkedIn: extract skills as a list of strings
- For Reddit: extract karma, reddit_age, active_subreddits (ranked by frequency)
- For Facebook: extract personal_details (city, hometown, work, education)
- verified: true if you see a verified/blue checkmark badge mention

Return ONLY valid JSON, no markdown fences, no explanation."""


# ── Tier 1: Text-Based Extraction ────────────────────────────────


async def ai_scrape_profile_from_text(
    platform: str,
    page: Page,
    pre_collected_text: str | None = None,
) -> Optional[dict]:
    """Extract profile data from page text using a text model (Tier 1 — cheapest).

    Sends page text to Gemini as a text prompt (no vision). Captures 80%+ of
    profile data at ~500-1500 tokens instead of ~5000+ for a screenshot.

    Args:
        platform: One of "x", "linkedin", "facebook", "reddit"
        page: Playwright page already navigated to the profile
        pre_collected_text: Optional pre-collected text from tab navigation.
            If provided, skips page.inner_text() and uses this directly.

    Returns:
        Structured profile dict, or None if extraction fails.
    """
    from utils.local_db import get_setting

    api_key = get_setting("gemini_api_key")
    if not api_key:
        logger.info("AI text scraping skipped: no gemini_api_key configured")
        return None

    # Use pre-collected text if provided, otherwise extract from page
    if pre_collected_text and len(pre_collected_text.strip()) >= 100:
        page_text = pre_collected_text
        logger.info("AI text scrape [%s]: using pre-collected text (%d chars)",
                    platform, len(page_text))
    else:
        logger.info("AI text scrape [%s]: extracting page text...", platform)
        try:
            page_text = await page.inner_text("body", timeout=10000)
        except Exception as e:
            logger.warning("AI text scrape [%s]: text extraction failed: %s", platform, e)
            return None

    if not page_text or len(page_text.strip()) < 100:
        logger.warning("AI text scrape [%s]: page text too short (%d chars), skipping",
                        platform, len(page_text) if page_text else 0)
        return None

    logger.info("AI text scrape [%s]: sending %d chars to Gemini...",
                platform, len(page_text))

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        prompt = _build_text_extraction_prompt(platform, page_text)

        # Try text models (no vision needed — much cheaper)
        models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]
        last_err = None
        raw_text = None
        for model in models:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                raw_text = response.text.strip()
                logger.info("AI text scrape [%s]: got response from %s (%d chars)",
                            platform, model, len(raw_text))
                break
            except Exception as e:
                last_err = e
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    continue
                raise

        if raw_text is None:
            raise last_err

    except Exception as e:
        logger.warning("AI text scrape [%s]: Gemini call failed: %s", platform, e)
        return None

    result = _parse_ai_response(raw_text, platform)
    if result is None:
        logger.warning("AI text scrape [%s]: failed to parse response", platform)
        return None

    logger.info(
        "AI text scrape [%s]: extracted — display_name=%s, followers=%d, posts=%d, "
        "niches=%s, quality=%s",
        platform,
        result.get("display_name"),
        result.get("follower_count", 0),
        len(result.get("recent_posts", [])),
        result.get("ai_detected_niches", []),
        result.get("content_quality"),
    )
    return result


def is_missing_key_fields(result: Optional[dict]) -> bool:
    """Check if a scrape result is missing critical fields (needs Tier 3 escalation)."""
    if result is None:
        return True
    if not result.get("display_name"):
        return True
    if result.get("follower_count", 0) == 0 and result.get("following_count", 0) == 0:
        return True
    return False


# ── Tier 3: Screenshot + Vision (last resort) ───────────────────


async def ai_scrape_profile(platform: str, page: Page) -> Optional[dict]:
    """Screenshot the profile page, send to Gemini Vision, return structured data.

    Args:
        platform: One of "x", "linkedin", "facebook", "reddit"
        page: Playwright page object already navigated to the profile

    Returns:
        Structured profile dict matching the schema expected by matching.py,
        or None if extraction fails.
    """
    # Get Gemini API key from local settings
    from utils.local_db import get_setting

    api_key = get_setting("gemini_api_key")
    if not api_key:
        logger.info("AI profile scraping skipped: no gemini_api_key configured")
        return None

    # Take full-page screenshot
    logger.info("AI scrape [%s]: taking screenshot...", platform)
    try:
        screenshot_bytes = await page.screenshot(full_page=True, type="png")
    except Exception as e:
        logger.warning("AI scrape [%s]: screenshot failed: %s", platform, e)
        return None

    if not screenshot_bytes or len(screenshot_bytes) < 1000:
        logger.warning("AI scrape [%s]: screenshot too small (%d bytes), skipping",
                        platform, len(screenshot_bytes) if screenshot_bytes else 0)
        return None

    # Send to Gemini Vision API
    logger.info("AI scrape [%s]: sending to Gemini Vision (%d KB screenshot)...",
                platform, len(screenshot_bytes) // 1024)

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        prompt_text = _build_extraction_prompt(platform)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                prompt_text,
                {"inline_data": {"mime_type": "image/png", "data": screenshot_b64}},
            ],
        )

        raw_text = response.text.strip()
        logger.debug("AI scrape [%s]: raw response length=%d", platform, len(raw_text))

    except Exception as e:
        logger.warning("AI scrape [%s]: Gemini Vision call failed: %s", platform, e)
        return None

    # Parse JSON response
    result = _parse_ai_response(raw_text, platform)
    if result is None:
        logger.warning("AI scrape [%s]: failed to parse AI response", platform)
        return None

    logger.info(
        "AI scrape [%s]: extracted — display_name=%s, followers=%d, posts=%d, "
        "niches=%s, quality=%s",
        platform,
        result.get("display_name"),
        result.get("follower_count", 0),
        len(result.get("recent_posts", [])),
        result.get("ai_detected_niches", []),
        result.get("content_quality"),
    )

    return result


# ── Response Parsing ─────────────────────────────────────────────


def _parse_ai_response(raw_text: str, platform: str) -> Optional[dict]:
    """Parse and validate the AI response JSON.

    Handles common AI response quirks: markdown fences, trailing text, etc.
    """
    # Strip markdown code fences if present
    text = raw_text.strip()
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        text = text.strip()

    # Try to find JSON object in the response
    # Sometimes AI adds text before/after the JSON
    json_match = re.search(r'\{[\s\S]*\}', text)
    if not json_match:
        logger.warning("AI scrape [%s]: no JSON object found in response", platform)
        return None

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        logger.warning("AI scrape [%s]: JSON parse error: %s", platform, e)
        return None

    # Validate and normalize the response
    return _normalize_profile_data(data, platform)


def _normalize_profile_data(data: dict, platform: str) -> Optional[dict]:
    """Validate and normalize the parsed AI response into the expected schema."""
    result = {
        "platform": platform,
        "display_name": _safe_str(data.get("display_name")),
        "username": _safe_str(data.get("username")),
        "bio": _safe_str(data.get("bio")),
        "follower_count": _safe_int(data.get("follower_count")),
        "following_count": _safe_int(data.get("following_count")),
        "post_count": _safe_int(data.get("post_count")),
        "location": _safe_str(data.get("location")),
        "website": _safe_str(data.get("website")),
        "join_date": _safe_str(data.get("join_date")),
        "verified": bool(data.get("verified")),
        "recent_posts": [],
        "engagement_rate": 0.0,
        "posting_frequency": _safe_float(data.get("posting_frequency")),
        "profile_data": {},
        "ai_detected_niches": [],
        "content_quality": None,
        "audience_demographics_estimate": None,
    }

    # Normalize recent_posts
    raw_posts = data.get("recent_posts", [])
    if isinstance(raw_posts, list):
        for p in raw_posts[:30]:  # Cap at 30 posts
            if not isinstance(p, dict):
                continue
            post = {
                "text": _safe_str(p.get("text"), max_len=500),
                "likes": _safe_int(p.get("likes")),
                "comments": _safe_int(p.get("comments")),
                "reposts": _safe_int(p.get("reposts")),
                "views": _safe_int(p.get("views")),
                "posted_at": _safe_str(p.get("posted_at")),
                "subreddit": _safe_str(p.get("subreddit")),
                "has_media": bool(p.get("has_media")),
            }
            # Also handle X-specific field names
            if "retweets" in p and post["reposts"] == 0:
                post["reposts"] = _safe_int(p.get("retweets"))
            if "replies" in p and post["comments"] == 0:
                post["comments"] = _safe_int(p.get("replies"))
            if "score" in p and post["likes"] == 0:
                post["likes"] = _safe_int(p.get("score"))
            result["recent_posts"].append(post)

    # Calculate engagement rate
    posts = result["recent_posts"]
    fc = result["follower_count"]
    if posts and fc > 0:
        total_engagement = sum(
            p["likes"] + p["comments"] + p["reposts"] for p in posts
        )
        avg_engagement = total_engagement / len(posts)
        result["engagement_rate"] = round(avg_engagement / fc, 6)

    # Normalize profile_data
    raw_pd = data.get("profile_data", {})
    if isinstance(raw_pd, dict):
        pd = {}
        if raw_pd.get("about"):
            pd["about"] = _safe_str(raw_pd["about"], max_len=1000)
        if raw_pd.get("experience") and isinstance(raw_pd["experience"], list):
            pd["experience"] = raw_pd["experience"][:10]
        if raw_pd.get("education") and isinstance(raw_pd["education"], list):
            pd["education"] = raw_pd["education"][:10]
        elif raw_pd.get("education") and isinstance(raw_pd["education"], str):
            pd["education"] = raw_pd["education"]
        if raw_pd.get("skills") and isinstance(raw_pd["skills"], list):
            pd["skills"] = [str(s).strip() for s in raw_pd["skills"][:30] if s]
        if raw_pd.get("karma") is not None:
            pd["karma"] = _safe_int(raw_pd["karma"])
        if raw_pd.get("reddit_age"):
            pd["reddit_age"] = _safe_str(raw_pd["reddit_age"])
        if raw_pd.get("active_subreddits") and isinstance(raw_pd["active_subreddits"], list):
            pd["active_subreddits"] = [str(s).strip() for s in raw_pd["active_subreddits"][:20] if s]
        if raw_pd.get("personal_details") and isinstance(raw_pd["personal_details"], dict):
            pd["personal_details"] = raw_pd["personal_details"]
        result["profile_data"] = pd

    # Normalize ai_detected_niches
    raw_niches = data.get("ai_detected_niches", [])
    if isinstance(raw_niches, list):
        result["ai_detected_niches"] = [
            str(n).strip().lower() for n in raw_niches[:10] if n
        ]

    # Normalize content_quality
    cq = data.get("content_quality")
    if isinstance(cq, str) and cq.strip().lower() in ("low", "medium", "high"):
        result["content_quality"] = cq.strip().lower()

    # Normalize audience_demographics_estimate
    raw_demo = data.get("audience_demographics_estimate")
    if isinstance(raw_demo, dict):
        result["audience_demographics_estimate"] = {
            "age_range": _safe_str(raw_demo.get("age_range")) or "unknown",
            "interests": [
                str(i).strip() for i in raw_demo.get("interests", [])[:10] if i
            ],
        }

    return result


# ── Safe Type Coercion Helpers ───────────────────────────────────


def _safe_str(value, max_len: int = 0) -> Optional[str]:
    """Safely convert to string, returning None for null/empty."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "null" or s.lower() == "none":
        return None
    if max_len > 0:
        s = s[:max_len]
    return s


def _safe_int(value) -> int:
    """Safely convert to int, handling strings like '1.2K', '3,400', etc."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        # Handle abbreviated numbers
        abbr_match = re.search(r'([\d,.]+)\s*([KkMm])?', text)
        if abbr_match:
            num_str = abbr_match.group(1).replace(",", "")
            suffix = abbr_match.group(2)
            try:
                val = float(num_str)
                if suffix and suffix.upper() == "K":
                    val *= 1000
                elif suffix and suffix.upper() == "M":
                    val *= 1_000_000
                return int(val)
            except ValueError:
                pass
    return 0


def _safe_float(value) -> float:
    """Safely convert to float."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0
