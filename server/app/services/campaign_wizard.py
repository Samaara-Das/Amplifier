"""Campaign wizard — AI-assisted campaign creation with URL scraping.

Scrapes company product links (httpx + BeautifulSoup), generates campaign
briefs via Gemini, estimates reach, and suggests payout rates.
"""

import asyncio
import json
import logging
import os
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)

SCRAPE_TIMEOUT = 15


# ── URL Scraping ─────────────────────────────────────────────────


async def scrape_urls(urls: list[str]) -> dict:
    """Scrape company product URLs for content, images, and metadata.

    Lightweight server-side scrape using httpx + BeautifulSoup.
    Works on Vercel (no subprocess/filesystem needed).

    Returns: {"pages": [{"url", "title", "content", "images", "metadata", "nav_links"}]}
    """
    pages = []

    async with httpx.AsyncClient(
        timeout=SCRAPE_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Amplifier/1.0)"},
    ) as client:
        for url in urls:
            try:
                page_data = await _scrape_single_url(client, url)
                if page_data:
                    pages.append(page_data)
            except Exception as e:
                logger.warning("Failed to scrape %s: %s", url, e)
                pages.append({"url": url, "error": str(e)})

    return {"pages": pages}


async def _scrape_single_url(client: httpx.AsyncClient, url: str) -> dict:
    """Scrape a single URL for content, images, metadata, and nav links."""
    resp = await client.get(url)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    parsed = urlparse(url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"

    # Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Metadata (OG tags + meta description)
    metadata = {}
    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        content = meta.get("content", "")
        if prop and content:
            if prop in ("og:title", "og:description", "og:image", "og:site_name", "og:type",
                        "description", "twitter:title", "twitter:description", "twitter:image"):
                metadata[prop] = content

    # Main text content — strip scripts, styles, nav, footer, header
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    # Try to find main content area
    main = soup.find("main") or soup.find("article") or soup.find(role="main")
    if main:
        text = main.get_text(separator="\n", strip=True)
    else:
        body = soup.find("body")
        text = body.get_text(separator="\n", strip=True) if body else ""

    # Clean up text — collapse blank lines
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    content = "\n".join(lines[:200])  # Cap at 200 lines

    # Images — filter out tiny icons and tracking pixels
    images = []
    seen_urls = set()
    for img in soup.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "")
        if not src:
            continue

        img_url = urljoin(url, src)

        # Skip duplicates, data URIs, tiny images
        if img_url in seen_urls:
            continue
        if img_url.startswith("data:"):
            continue
        # Skip common icon/tracking patterns
        if any(p in img_url.lower() for p in [
            "favicon", "icon", "logo", "pixel", "tracking", "1x1",
            "spacer", "blank", "svg+xml", ".svg", "sprite",
        ]):
            continue
        # Skip if dimensions are specified and tiny
        width = img.get("width", "")
        height = img.get("height", "")
        if width and height:
            try:
                if int(width) < 50 or int(height) < 50:
                    continue
            except (ValueError, TypeError):
                pass

        seen_urls.add(img_url)
        images.append({
            "url": img_url,
            "alt": (img.get("alt") or "").strip(),
        })

    # Nav links — same-domain links from navigation
    nav_links = []
    nav_elements = soup.find_all("nav")
    for nav in nav_elements:
        for a in nav.find_all("a", href=True):
            href = urljoin(url, a["href"])
            link_text = a.get_text(strip=True)
            if urlparse(href).netloc == parsed.netloc and link_text:
                nav_links.append({"url": href, "text": link_text})

    return {
        "url": url,
        "title": title,
        "content": content,
        "images": images[:30],  # Cap at 30 images
        "metadata": metadata,
        "nav_links": nav_links[:20],  # Cap at 20 nav links
    }


# ── Gemini AI Call ───────────────────────────────────────────────


GEMINI_MODELS = [
    "gemini-2.0-flash",       # Higher free-tier limit (15 RPM, 1500 RPD)
    "gemini-2.0-flash-lite",  # Fallback
    "gemini-1.5-flash",       # Another fallback
]


async def _call_gemini(prompt: str) -> str:
    """Call Gemini API with model fallback chain.

    Tries multiple models in order — if one hits rate limits, tries the next.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    from google import genai

    client = genai.Client(api_key=api_key)
    last_error = None

    for model in GEMINI_MODELS:
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            last_error = e
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                logger.warning("Gemini model %s rate limited, trying next...", model)
                continue
            raise  # Non-rate-limit error, don't retry

    raise last_error  # All models exhausted


def _parse_json_response(text: str) -> dict:
    """Extract JSON from AI response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not parse JSON from AI response: {text[:200]}")


# ── Campaign Wizard ──────────────────────────────────────────────


async def run_campaign_wizard(
    db: AsyncSession,
    product_description: str,
    campaign_goal: str = "brand_awareness",
    company_urls: list[str] | None = None,
    target_niches: list[str] | None = None,
    target_regions: list[str] | None = None,
    required_platforms: list[str] | None = None,
    min_followers: dict[str, int] | None = None,
    must_include: str | list[str] | None = None,
    must_avoid: str | list[str] | None = None,
    budget_range: dict | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    # New fields
    product_name: str | None = None,
    product_features: str | None = None,
    # Legacy (kept for backward compat, ignored)
    tone: str | None = None,
    **kwargs,
) -> dict:
    """Generate a campaign draft using AI.

    1. Scrape company URLs for product info
    2. Build Gemini prompt with all context
    3. Parse structured response
    4. Estimate reach
    5. Return full campaign draft
    """
    # Step 1: Scrape URLs
    scraped_data = {}
    if company_urls:
        try:
            scraped_data = await scrape_urls(company_urls)
        except Exception as e:
            logger.warning("URL scraping failed: %s", e)

    # Build scraped context for the prompt
    scraped_context = ""
    if scraped_data.get("pages"):
        for page in scraped_data["pages"]:
            if page.get("error"):
                continue
            scraped_context += f"\n--- Scraped from {page['url']} ---\n"
            if page.get("title"):
                scraped_context += f"Page title: {page['title']}\n"
            if page.get("metadata"):
                for k, v in page["metadata"].items():
                    scraped_context += f"{k}: {v}\n"
            if page.get("content"):
                scraped_context += f"\nContent:\n{page['content'][:2000]}\n"

    # Normalize must_include/must_avoid
    if isinstance(must_include, list):
        must_include = ", ".join(must_include)
    if isinstance(must_avoid, list):
        must_avoid = ", ".join(must_avoid)

    # Step 2: Build Gemini prompt
    prompt = f"""You are a campaign strategist for Amplifier, a platform where companies pay social media creators to post about their products.

Generate a complete campaign brief based on the following information.

PRODUCT NAME: {product_name or 'Not provided'}
PRODUCT DESCRIPTION: {product_description}
PRODUCT FEATURES & BENEFITS: {product_features or 'Not provided'}
CAMPAIGN GOAL: {campaign_goal}
TARGET NICHES: {', '.join(target_niches or ['general'])}
TARGET REGIONS: {', '.join(target_regions or ['global'])}
REQUIRED PLATFORMS: {', '.join(required_platforms or ['any'])}
MUST INCLUDE IN POSTS: {must_include or 'None'}
MUST AVOID IN POSTS: {must_avoid or 'None'}

{f'SCRAPED PRODUCT INFO:{scraped_context}' if scraped_context else ''}

Generate a JSON response with these fields:
- "title": Campaign title (max 60 chars, catchy and clear)
- "brief": Detailed campaign brief for creators (200-500 words). Explain what the product is, why it matters, what angle to take, what the audience cares about. Be specific and actionable.
- "content_guidance": Instructions for creators — tone, key messages, dos/don'ts, hashtag suggestions, call-to-action ideas. (100-300 words)
- "payout_rules": Object with "rate_per_1k_impressions" (float), "rate_per_like" (float), "rate_per_repost" (float), "rate_per_click" (float). Suggest rates based on the niche and campaign goal.
- "suggested_budget": Recommended total budget in USD (number). Consider the goal and niche.

Return ONLY valid JSON, no markdown fences, no extra text."""

    # Step 3: Call AI
    ai_error = None
    try:
        ai_response = await _call_gemini(prompt)
        generated = _parse_json_response(ai_response)
    except Exception as e:
        ai_error = str(e)
        logger.warning("AI generation failed: %s. Using defaults.", e)
        generated = _generate_defaults(product_name, product_description, product_features, target_niches)

    # Step 4: Estimate reach
    reach = {"matching_users": 0, "estimated_impressions_low": 0, "estimated_impressions_high": 0}
    try:
        payout_rates = generated.get("payout_rules", suggest_payout_rates(target_niches or []))
        reach = await estimate_reach(
            db=db,
            niche_tags=target_niches,
            target_regions=target_regions,
            required_platforms=required_platforms,
            min_followers=min_followers,
            payout_rates=payout_rates,
        )
    except Exception as e:
        logger.warning("Reach estimation failed: %s", e)

    result = {
        **generated,
        "reach_estimate": reach,
        "scraped_data": scraped_data,
    }
    if ai_error:
        result["ai_error"] = ai_error
    return result


def _generate_defaults(
    product_name: str | None,
    product_description: str,
    product_features: str | None,
    target_niches: list[str] | None,
) -> dict:
    """Fallback when AI generation fails."""
    title = (product_name or product_description)[:60]
    brief = product_description
    if product_features:
        brief += f"\n\nKey features and benefits:\n{product_features}"

    return {
        "title": title,
        "brief": brief,
        "content_guidance": "Create authentic, engaging content about this product. Focus on real benefits and personal experience.",
        "payout_rules": suggest_payout_rates(target_niches or []),
        "suggested_budget": 100,
    }


# ── Payout Rate Suggestions ─────────────────────────────────────


# Niche-based rate tiers
_HIGH_VALUE_NICHES = {"finance", "crypto", "ai", "business", "tech"}
_ENGAGEMENT_NICHES = {"beauty", "fashion", "fitness", "food", "lifestyle"}

def suggest_payout_rates(niches: list[str]) -> dict:
    """Suggest payout rates based on niche. Higher-value niches get higher rates."""
    niche_set = set(n.lower() for n in niches) if niches else set()

    if niche_set & _HIGH_VALUE_NICHES:
        return {
            "rate_per_1k_impressions": 1.00,
            "rate_per_like": 0.02,
            "rate_per_repost": 0.10,
            "rate_per_click": 0.15,
        }
    elif niche_set & _ENGAGEMENT_NICHES:
        return {
            "rate_per_1k_impressions": 0.30,
            "rate_per_like": 0.015,
            "rate_per_repost": 0.08,
            "rate_per_click": 0.10,
        }
    else:
        return {
            "rate_per_1k_impressions": 0.50,
            "rate_per_like": 0.01,
            "rate_per_repost": 0.05,
            "rate_per_click": 0.10,
        }


# ── Reach Estimation ─────────────────────────────────────────────


async def estimate_reach(
    db: AsyncSession,
    niche_tags: list[str] | None = None,
    target_regions: list[str] | None = None,
    required_platforms: list[str] | None = None,
    min_followers: dict[str, int] | None = None,
    payout_rates: dict | None = None,
) -> dict:
    """Estimate campaign reach by counting eligible users and their followers.

    Uses the same hard filters as the matching algorithm.
    """
    # Get all active users
    result = await db.execute(
        select(User).where(User.status == "active")
    )
    users = result.scalars().all()

    matching_users = 0
    total_followers = 0

    for user in users:
        # Required platforms check
        if required_platforms:
            user_platforms = set(
                k for k, v in (user.platforms or {}).items()
                if isinstance(v, dict) and v.get("connected")
            )
            if not set(required_platforms).issubset(user_platforms):
                continue

        # Min followers check
        if min_followers:
            user_followers = user.follower_counts or {}
            skip = False
            for platform, minimum in min_followers.items():
                if user_followers.get(platform, 0) < minimum:
                    skip = True
                    break
            if skip:
                continue

        # Region check
        if target_regions:
            user_region = getattr(user, "audience_region", "global") or "global"
            if user_region != "global" and user_region not in target_regions:
                continue

        matching_users += 1
        user_followers = user.follower_counts or {}
        total_followers += sum(user_followers.values())

    # Estimate impressions (rough: 5-15% of followers see each post)
    low = int(total_followers * 0.05)
    high = int(total_followers * 0.15)

    return {
        "matching_users": matching_users,
        "estimated_impressions_low": low,
        "estimated_impressions_high": high,
        "suggested_payout_rates": payout_rates or suggest_payout_rates([]),
    }
