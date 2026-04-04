"""Campaign quality scoring — gates activation on content completeness.

Scores campaigns 0-100 against a rubric. Campaigns below 85 cannot be
activated. Returns actionable feedback for companies to improve.
"""

import logging

logger = logging.getLogger(__name__)

QUALITY_RUBRIC = {
    "brief_length": {"weight": 20, "min_chars": 100, "good_chars": 300},
    "content_guidance_present": {"weight": 15},
    "payout_rates_reasonable": {"weight": 15},
    "targeting_specified": {"weight": 10},
    "assets_provided": {"weight": 10},
    "title_descriptive": {"weight": 10, "min_chars": 10, "max_chars": 100},
    "dates_valid": {"weight": 10},
    "budget_sufficient": {"weight": 10},
}

ACTIVATION_THRESHOLD = 85


async def score_campaign_quality(campaign) -> dict:
    """Score campaign quality against rubric.

    Returns:
        {
            "score": 0-100,
            "passed": bool (score >= 85),
            "feedback": ["Brief is too short...", ...],
            "breakdown": {"brief_length": 15, ...}
        }
    """
    score = 0
    breakdown = {}
    feedback = []

    # 1. Brief length (20 points)
    brief = campaign.brief or ""
    brief_len = len(brief.strip())
    rubric = QUALITY_RUBRIC["brief_length"]
    if brief_len >= rubric["good_chars"]:
        points = rubric["weight"]
    elif brief_len >= rubric["min_chars"]:
        points = int(rubric["weight"] * brief_len / rubric["good_chars"])
    else:
        points = 0
        feedback.append(
            f"Brief is too short ({brief_len} chars). Add more product details — "
            f"aim for at least {rubric['min_chars']} characters."
        )
    breakdown["brief_length"] = points
    score += points

    # 2. Content guidance (15 points)
    guidance = campaign.content_guidance or ""
    if len(guidance.strip()) > 20:
        points = QUALITY_RUBRIC["content_guidance_present"]["weight"]
    elif len(guidance.strip()) > 0:
        points = QUALITY_RUBRIC["content_guidance_present"]["weight"] // 2
        feedback.append("Content guidance is very brief. Add tone, must-include phrases, or examples.")
    else:
        points = 0
        feedback.append("No content guidance provided. Add tone, key messages, or examples for creators.")
    breakdown["content_guidance_present"] = points
    score += points

    # 3. Payout rates reasonable (15 points)
    rules = campaign.payout_rules or {}
    cpm = rules.get("rate_per_1k_impressions", 0)
    if cpm >= 1.0:
        points = QUALITY_RUBRIC["payout_rates_reasonable"]["weight"]
    elif cpm >= 0.50:
        points = QUALITY_RUBRIC["payout_rates_reasonable"]["weight"] // 2
        feedback.append(f"CPM rate (${cpm:.2f}/1K) is below average. Consider $2-5/1K for better creator interest.")
    else:
        points = 0
        feedback.append("Payout rates are too low to attract quality creators. Set CPM to at least $1/1K impressions.")
    breakdown["payout_rates_reasonable"] = points
    score += points

    # 4. Targeting specified (10 points)
    targeting = campaign.targeting or {}
    has_targeting = bool(
        targeting.get("niche_tags")
        or targeting.get("required_platforms")
        or targeting.get("target_regions")
        or targeting.get("min_followers")
    )
    if has_targeting:
        points = QUALITY_RUBRIC["targeting_specified"]["weight"]
    else:
        points = 0
        feedback.append("No targeting specified. Add niche tags, platforms, or regions for better creator matching.")
    breakdown["targeting_specified"] = points
    score += points

    # 5. Assets provided (10 points)
    assets = campaign.assets or {}
    has_assets = bool(
        assets.get("image_urls")
        or assets.get("links")
        or assets.get("hashtags")
        or assets.get("brand_guidelines")
    )
    if has_assets:
        points = QUALITY_RUBRIC["assets_provided"]["weight"]
    else:
        points = 0
        feedback.append("No assets (images, links, hashtags) provided. Adding these helps creators make better content.")
    breakdown["assets_provided"] = points
    score += points

    # 6. Title descriptive (10 points)
    title = campaign.title or ""
    title_len = len(title.strip())
    rubric = QUALITY_RUBRIC["title_descriptive"]
    if rubric["min_chars"] <= title_len <= rubric["max_chars"]:
        points = rubric["weight"]
    elif title_len > 0:
        points = rubric["weight"] // 2
        if title_len < rubric["min_chars"]:
            feedback.append("Campaign title is too short. Use a descriptive title (10-100 characters).")
        elif title_len > rubric["max_chars"]:
            feedback.append("Campaign title is too long. Keep it under 100 characters.")
    else:
        points = 0
        feedback.append("Campaign title is missing.")
    breakdown["title_descriptive"] = points
    score += points

    # 7. Dates valid (10 points)
    if campaign.start_date and campaign.end_date:
        if campaign.end_date > campaign.start_date:
            points = QUALITY_RUBRIC["dates_valid"]["weight"]
        else:
            points = 0
            feedback.append("End date must be after start date.")
    else:
        points = 0
        feedback.append("Campaign dates are missing.")
    breakdown["dates_valid"] = points
    score += points

    # 8. Budget sufficient (10 points)
    budget = float(campaign.budget_total or 0)
    if budget >= 50:
        points = QUALITY_RUBRIC["budget_sufficient"]["weight"]
    elif budget >= 10:
        points = QUALITY_RUBRIC["budget_sufficient"]["weight"] // 2
        feedback.append(f"Budget (${budget:.0f}) is low. $50+ recommended for meaningful reach.")
    else:
        points = 0
        feedback.append("Budget is too low. Minimum $10 recommended.")
    breakdown["budget_sufficient"] = points
    score += points

    passed = score >= ACTIVATION_THRESHOLD

    return {
        "score": score,
        "passed": passed,
        "feedback": feedback,
        "breakdown": breakdown,
    }
