"""AI Campaign Creation Wizard service.

Generates campaign drafts from company input:
1. Scrapes company URLs for context
2. Builds a prompt with product description + scraped data + goal + tone
3. Calls Gemini to generate title, brief, content_guidance
4. Suggests payout rates by niche
5. Estimates reach from matching users
"""

import asyncio
import json
import logging
import os
import re
import subprocess
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)

# Path to the webcrawler CLI (project-local tool)
WEBCRAWLER_PATH = os.environ.get(
    "WEBCRAWLER_PATH",
    "C:/Users/dassa/Work/webcrawler/crawl.py",
)

# ── Payout rate tables by niche ──────────────────────────────────

# Higher-value niches get higher suggested rates
NICHE_PAYOUT_RATES: dict[str, dict[str, float]] = {
    # Premium niches
    "finance": {"rate_per_1k_impressions": 0.75, "rate_per_like": 0.02, "rate_per_repost": 0.05, "rate_per_click": 0.15},
    "crypto": {"rate_per_1k_impressions": 0.75, "rate_per_like": 0.02, "rate_per_repost": 0.05, "rate_per_click": 0.15},
    "business": {"rate_per_1k_impressions": 0.65, "rate_per_like": 0.02, "rate_per_repost": 0.05, "rate_per_click": 0.12},
    "tech": {"rate_per_1k_impressions": 0.60, "rate_per_like": 0.015, "rate_per_repost": 0.04, "rate_per_click": 0.12},
    "education": {"rate_per_1k_impressions": 0.55, "rate_per_like": 0.015, "rate_per_repost": 0.04, "rate_per_click": 0.10},
    "health": {"rate_per_1k_impressions": 0.55, "rate_per_like": 0.015, "rate_per_repost": 0.04, "rate_per_click": 0.10},
    # Standard niches
    "lifestyle": {"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01, "rate_per_repost": 0.05, "rate_per_click": 0.10},
    "fashion": {"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01, "rate_per_repost": 0.05, "rate_per_click": 0.10},
    "beauty": {"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01, "rate_per_repost": 0.05, "rate_per_click": 0.10},
    "fitness": {"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01, "rate_per_repost": 0.05, "rate_per_click": 0.10},
    "gaming": {"rate_per_1k_impressions": 0.45, "rate_per_like": 0.01, "rate_per_repost": 0.03, "rate_per_click": 0.08},
    "food": {"rate_per_1k_impressions": 0.45, "rate_per_like": 0.01, "rate_per_repost": 0.03, "rate_per_click": 0.08},
    "travel": {"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01, "rate_per_repost": 0.04, "rate_per_click": 0.10},
    "entertainment": {"rate_per_1k_impressions": 0.45, "rate_per_like": 0.01, "rate_per_repost": 0.03, "rate_per_click": 0.08},
}

DEFAULT_PAYOUT_RATES = {
    "rate_per_1k_impressions": 0.50,
    "rate_per_like": 0.01,
    "rate_per_repost": 0.05,
    "rate_per_click": 0.10,
}

# ── Gemini prompt ────────────────────────────────────────────────

WIZARD_PROMPT = """You are a campaign strategist for Amplifier, a social media marketing platform.
A company wants to create a campaign. Generate the campaign details from their input.

COMPANY INPUT:
- Product/Service: {product_description}
- Campaign Goal: {goal}
- Tone: {tone}
- Must Include: {must_include}
- Must Avoid: {must_avoid}
- Target Niches: {target_niches}
- Target Regions: {target_regions}

{scraped_context}

Generate a JSON object with these exact keys:
- "title": A compelling campaign title (max 80 chars)
- "brief": A detailed campaign description/brief for influencers (200-500 chars). Explain what the product is, what to highlight, and what the post should achieve.
- "content_guidance": Specific instructions for content creators (200-500 chars). Include tone guidance, must-include elements, things to avoid, and any disclaimers needed.

Return ONLY valid JSON. No markdown fences, no extra text.
"""


# ── URL scraping ─────────────────────────────────────────────────


async def scrape_company_urls(urls: list[str]) -> str:
    """Scrape URLs via the webcrawler CLI and return combined text.

    Truncates total output to ~2000 chars to fit in prompt context.
    Handles failures gracefully: unreachable URLs are skipped.
    """
    if not urls:
        return ""

    combined_parts: list[str] = []

    for url in urls[:3]:  # Limit to 3 URLs to avoid slow responses
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["python", WEBCRAWLER_PATH, "fetch", url],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                content = result.stdout.strip()
                # Take first 800 chars per URL
                combined_parts.append(f"--- Content from {url} ---\n{content[:800]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("Failed to scrape %s: %s", url, e)
            continue

    combined = "\n\n".join(combined_parts)
    # Hard limit: 2000 chars total
    return combined[:2000]


# ── Gemini AI generation ─────────────────────────────────────────


def _parse_json_response(text: str) -> dict:
    """Extract JSON from an AI response, handling markdown fences."""
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
        raise ValueError(f"Could not parse JSON from response: {text[:200]}")


async def generate_campaign_with_ai(
    product_description: str,
    goal: str,
    tone: str,
    must_include: list[str] | str | None,
    must_avoid: list[str] | str | None,
    target_niches: list[str],
    target_regions: list[str],
    scraped_content: str,
) -> dict[str, str]:
    """Call Gemini to generate campaign title, brief, and content_guidance.

    Returns dict with keys: title, brief, content_guidance.
    Raises on failure (caller should handle with defaults).
    """
    # Format must_include / must_avoid
    if isinstance(must_include, list):
        must_include_str = ", ".join(must_include) if must_include else "None specified"
    else:
        must_include_str = must_include or "None specified"

    if isinstance(must_avoid, list):
        must_avoid_str = ", ".join(must_avoid) if must_avoid else "None specified"
    else:
        must_avoid_str = must_avoid or "None specified"

    scraped_context = ""
    if scraped_content:
        scraped_context = f"SCRAPED COMPANY DATA:\n{scraped_content}"

    prompt = WIZARD_PROMPT.format(
        product_description=product_description,
        goal=goal,
        tone=tone or "professional",
        must_include=must_include_str,
        must_avoid=must_avoid_str,
        target_niches=", ".join(target_niches) if target_niches else "general",
        target_regions=", ".join(target_regions) if target_regions else "global",
        scraped_context=scraped_context,
    )

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    from google import genai

    client = genai.Client(api_key=api_key)
    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.5-flash-lite",
        contents=prompt,
    )
    return _parse_json_response(response.text)


def get_default_campaign_content(
    product_description: str, goal: str, tone: str
) -> dict[str, str]:
    """Sensible defaults when AI generation fails."""
    title = product_description[:80] if product_description else "New Campaign"
    brief = (
        f"Promote: {product_description}. "
        f"Goal: {goal.replace('_', ' ')}. "
        "Share authentic content highlighting the key benefits of this product/service."
    )
    content_guidance = (
        f"Tone: {tone or 'professional'}. "
        "Create genuine, engaging content that resonates with your audience. "
        "Include relevant hashtags and a clear call to action."
    )
    return {
        "title": title,
        "brief": brief,
        "content_guidance": content_guidance,
    }


# ── Payout rate suggestion ───────────────────────────────────────


def suggest_payout_rates(niches: list[str]) -> dict[str, float]:
    """Suggest payout rates based on the highest-value niche in the list.

    Finance/crypto/tech campaigns get premium rates; lifestyle gets standard.
    """
    if not niches:
        return dict(DEFAULT_PAYOUT_RATES)

    # Pick the highest-value niche from the provided list
    best_rates = dict(DEFAULT_PAYOUT_RATES)
    best_cpm = 0.0

    for niche in niches:
        niche_lower = niche.lower().strip()
        rates = NICHE_PAYOUT_RATES.get(niche_lower)
        if rates and rates["rate_per_1k_impressions"] > best_cpm:
            best_rates = dict(rates)
            best_cpm = rates["rate_per_1k_impressions"]

    return best_rates


# ── Reach estimation ─────────────────────────────────────────────


async def estimate_reach(
    db: AsyncSession,
    niche_tags: list[str] | None = None,
    target_regions: list[str] | None = None,
    required_platforms: list[str] | None = None,
    min_followers: dict[str, int] | None = None,
    payout_rates: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Estimate campaign reach based on targeting criteria.

    Uses the same hard filters as matching.py to count eligible users,
    then estimates impressions from follower counts and engagement rates.
    """
    # Fetch all active users
    result = await db.execute(
        select(User).where(User.status == "active")
    )
    all_users = result.scalars().all()

    matching_users: list[User] = []
    total_followers = 0
    engagement_rates: list[float] = []
    per_platform: dict[str, dict[str, Any]] = {}

    for user in all_users:
        # Hard filter: required platforms
        if required_platforms:
            user_platforms = set(
                k for k, v in (user.platforms or {}).items()
                if isinstance(v, dict) and v.get("connected")
            )
            if not set(required_platforms).issubset(user_platforms):
                continue

        # Hard filter: minimum follower counts
        if min_followers:
            user_followers = user.follower_counts or {}
            skip = False
            for platform, minimum in min_followers.items():
                if user_followers.get(platform, 0) < minimum:
                    skip = True
                    break
            if skip:
                continue

        # Hard filter: target regions
        if target_regions:
            user_region = getattr(user, "audience_region", "global") or "global"
            if user_region != "global" and user_region not in target_regions:
                continue

        # Hard filter: niche overlap (at least one matching niche, or no niche filter)
        if niche_tags:
            user_niches = set(user.niche_tags or [])
            if not user_niches.intersection(set(niche_tags)):
                continue

        # User matches -- collect stats
        matching_users.append(user)
        user_followers_dict = user.follower_counts or {}

        # Sum followers across required platforms (or all connected platforms)
        platforms_to_count = required_platforms or list(user_followers_dict.keys())
        for plat in platforms_to_count:
            fc = user_followers_dict.get(plat, 0)
            total_followers += fc

            # Per-platform tracking
            if plat not in per_platform:
                per_platform[plat] = {"users": 0, "total_followers": 0}
            per_platform[plat]["users"] += 1
            per_platform[plat]["total_followers"] += fc

        # Extract engagement rate from scraped_profiles if available
        scraped = user.scraped_profiles or {}
        for plat in platforms_to_count:
            plat_data = scraped.get(plat, {})
            if isinstance(plat_data, dict) and "engagement_rate" in plat_data:
                engagement_rates.append(plat_data["engagement_rate"])

    num_matching = len(matching_users)

    # Average engagement rate (default 3.5% if no data)
    avg_engagement = (
        sum(engagement_rates) / len(engagement_rates)
        if engagement_rates
        else 0.035
    )

    # Impression estimates: follower_count * impression_factor
    # Conservative: 30% of followers see a post, Optimistic: 60%
    impressions_low = int(total_followers * 0.3)
    impressions_high = int(total_followers * 0.6)

    # Per-platform impression estimates
    per_platform_result = {}
    for plat, data in per_platform.items():
        per_platform_result[plat] = {
            "users": data["users"],
            "est_impressions_low": int(data["total_followers"] * 0.3),
            "est_impressions_high": int(data["total_followers"] * 0.6),
        }

    # Cost estimate from payout rates
    rates = payout_rates or DEFAULT_PAYOUT_RATES
    cpm = rates.get("rate_per_1k_impressions", 0.50)
    # Cost = CPM * impressions/1000 + engagement-based costs
    # Engagement costs estimated as avg_engagement * impressions * blended_per_engagement_rate
    blended_engagement_rate = (
        rates.get("rate_per_like", 0.01) * 0.7  # likes are most common
        + rates.get("rate_per_repost", 0.05) * 0.2
        + rates.get("rate_per_click", 0.10) * 0.1
    )
    cost_low = (
        (impressions_low / 1000) * cpm
        + impressions_low * avg_engagement * blended_engagement_rate
    )
    cost_high = (
        (impressions_high / 1000) * cpm
        + impressions_high * avg_engagement * blended_engagement_rate
    )

    return {
        "matching_users": num_matching,
        "avg_engagement_rate": round(avg_engagement, 4),
        "estimated_reach": {
            "low": impressions_low,
            "high": impressions_high,
        },
        "estimated_cost": {
            "low": round(cost_low, 2),
            "high": round(cost_high, 2),
        },
        "per_platform": per_platform_result,
    }


def suggest_budget(reach_estimate: dict[str, Any]) -> float:
    """Suggest a budget based on estimated cost range.

    Returns midpoint of cost range, clamped to $50 minimum.
    """
    cost_low = reach_estimate.get("estimated_cost", {}).get("low", 50)
    cost_high = reach_estimate.get("estimated_cost", {}).get("high", 200)
    suggested = (cost_low + cost_high) / 2
    return max(round(suggested, 2), 50.0)


# ── Main wizard orchestrator ─────────────────────────────────────


async def run_campaign_wizard(
    db: AsyncSession,
    product_description: str,
    campaign_goal: str,
    company_urls: list[str] | None = None,
    target_niches: list[str] | None = None,
    target_regions: list[str] | None = None,
    required_platforms: list[str] | None = None,
    min_followers: dict[str, int] | None = None,
    tone: str | None = None,
    must_include: list[str] | str | None = None,
    must_avoid: list[str] | str | None = None,
    budget_range: dict[str, float] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Run the full AI wizard pipeline.

    1. Scrape company URLs for context
    2. Generate campaign via Gemini
    3. Suggest payout rates based on niche
    4. Estimate reach
    5. Suggest budget
    6. Return complete draft for review
    """
    niches = target_niches or []
    regions = target_regions or []
    platforms = required_platforms or []
    followers = min_followers or {}

    # 1. Scrape company URLs
    scraped_content = ""
    scraped_data: dict[str, Any] = {}
    if company_urls:
        try:
            scraped_content = await scrape_company_urls(company_urls)
            if scraped_content:
                scraped_data = {
                    "urls_scraped": len(company_urls),
                    "content_length": len(scraped_content),
                    "urls": company_urls,
                }
        except Exception as e:
            logger.warning("URL scraping failed: %s", e)

    # 2. Generate campaign content via AI
    try:
        ai_result = await generate_campaign_with_ai(
            product_description=product_description,
            goal=campaign_goal,
            tone=tone or "professional",
            must_include=must_include,
            must_avoid=must_avoid,
            target_niches=niches,
            target_regions=regions,
            scraped_content=scraped_content,
        )
        title = ai_result.get("title", "")[:255]
        brief = ai_result.get("brief", "")
        content_guidance = ai_result.get("content_guidance", "")
    except Exception as e:
        logger.warning("AI generation failed, using defaults: %s", e)
        defaults = get_default_campaign_content(product_description, campaign_goal, tone or "professional")
        title = defaults["title"]
        brief = defaults["brief"]
        content_guidance = defaults["content_guidance"]

    # 3. Suggest payout rates
    payout_rates = suggest_payout_rates(niches)

    # 4. Estimate reach
    reach_estimate = await estimate_reach(
        db=db,
        niche_tags=niches or None,
        target_regions=regions or None,
        required_platforms=platforms or None,
        min_followers=followers or None,
        payout_rates=payout_rates,
    )

    # 5. Suggest budget
    suggested = suggest_budget(reach_estimate)
    if budget_range:
        budget_min = budget_range.get("min", 50)
        budget_max = budget_range.get("max", 10000)
        suggested = max(min(suggested, budget_max), budget_min)

    # 6. Build response
    targeting = {
        "niche_tags": niches,
        "target_regions": regions,
        "required_platforms": platforms,
        "min_followers": followers,
    }

    generated_campaign: dict[str, Any] = {
        "title": title,
        "brief": brief,
        "content_guidance": content_guidance,
        "payout_rules": payout_rates,
        "targeting": targeting,
        "budget_total": suggested,
        "assets": {},
    }

    if start_date:
        generated_campaign["start_date"] = start_date
    if end_date:
        generated_campaign["end_date"] = end_date

    return {
        "generated_campaign": generated_campaign,
        "scraped_data": scraped_data,
        "reach_estimate": reach_estimate,
    }
