"""Campaign quality gate — mechanical rubric + AI review.

score_campaign(): deterministic rubric, 0-100, no AI.
ai_review_campaign(): server-side Gemini call, brand safety check.

Both run on activation. score_campaign also runs as pre-flight on
the campaign detail page (informational only, no AI).
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

ACTIVATION_THRESHOLD = 85

# ── Rubric weights ─────────────────────────────────────────────────
# Keys must match AC2 exactly.
_WEIGHTS = {
    "brief_completeness": 25,
    "content_guidance": 15,
    "payout_rates": 15,
    "targeting": 10,
    "assets_provided": 10,
    "title_quality": 10,
    "dates_valid": 5,
    "budget_sufficient": 10,
}

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
]


# ── Mechanical rubric ──────────────────────────────────────────────


def score_campaign(campaign) -> dict:
    """Score campaign against 8-criterion rubric. Deterministic — no AI.

    Returns:
        {
            "score": int,          # 0-100 total
            "passed": bool,        # score >= 85
            "feedback": list[str], # actionable messages for failed criteria
            "criteria": {          # per-criterion breakdown
                "<key>": {"score": int, "max": int, "feedback": str}
            }
        }
    """
    criteria = {}
    feedback = []

    # 1. Brief completeness (25 pts)
    brief = (campaign.brief or "").strip()
    brief_len = len(brief)
    max_pts = _WEIGHTS["brief_completeness"]
    if brief_len >= 300:
        pts = max_pts
        fb = "Brief is complete."
    elif brief_len >= 100:
        pts = max_pts // 2  # 12
        fb = f"Brief is too short ({brief_len} chars). Describe your product, its key features, and who it's for. Aim for 300+ characters."
        feedback.append(fb)
    else:
        pts = 0
        fb = f"Brief is too short ({brief_len} chars). Describe your product, its key features, and who it's for. Aim for 300+ characters."
        feedback.append(fb)
    criteria["brief_completeness"] = {"score": pts, "max": max_pts, "feedback": fb}

    # 2. Content guidance (15 pts) — repost campaigns are exempt
    max_pts = _WEIGHTS["content_guidance"]
    campaign_type = getattr(campaign, "campaign_type", "ai_generated") or "ai_generated"
    if campaign_type == "repost":
        pts = max_pts
        fb = "exempt — repost campaign provides content directly"
    else:
        guidance = (campaign.content_guidance or "").strip()
        guidance_len = len(guidance)
        if guidance_len >= 50:
            pts = max_pts
            fb = "Content guidance is sufficient."
        elif guidance_len >= 20:
            pts = max_pts // 2  # 7
            fb = "Content guidance is very brief. Add tone, must-include phrases, or examples."
            feedback.append(fb)
        else:
            pts = 0
            fb = "No content guidance provided. Add tone instructions, must-include phrases, or content examples."
            feedback.append(fb)
    criteria["content_guidance"] = {"score": pts, "max": max_pts, "feedback": fb}

    # 3. Payout rates (15 pts)
    # Full: rate_per_like >= $0.01 AND at least 2 rate types set
    # Partial: 1 rate type set with reasonable amount
    # Zero: all $0 or only 1 rate < $0.005
    max_pts = _WEIGHTS["payout_rates"]
    rules = campaign.payout_rules or {}
    rate_like = float(rules.get("rate_per_like", 0) or 0)
    rate_view = float(rules.get("rate_per_1k_impressions", 0) or 0)
    rate_repost = float(rules.get("rate_per_repost", 0) or 0)
    rate_click = float(rules.get("rate_per_click", 0) or 0)

    nonzero_rates = sum([
        1 for r in [rate_like, rate_view, rate_repost, rate_click] if r > 0
    ])
    has_competitive_like = rate_like >= 0.01

    if has_competitive_like and nonzero_rates >= 2:
        pts = max_pts
        fb = "Payout rates are competitive."
    elif nonzero_rates >= 1:
        pts = max_pts // 2  # 7
        fb = "Payout rates are low. Set rate_per_like >= $0.01 and at least 2 rate types to attract quality creators."
        feedback.append(fb)
    else:
        pts = 0
        fb = "Payout rates are all zero or below minimum. Set at least rate_per_like >= $0.01 and configure at least 2 rate types."
        feedback.append(fb)
    criteria["payout_rates"] = {"score": pts, "max": max_pts, "feedback": fb}

    # 4. Targeting (10 pts)
    max_pts = _WEIGHTS["targeting"]
    targeting = campaign.targeting or {}
    niche_tags = targeting.get("niche_tags") or []
    required_platforms = targeting.get("required_platforms") or []
    has_niches = bool(niche_tags)
    has_platforms = bool(required_platforms)

    if has_niches and has_platforms:
        pts = max_pts
        fb = "Targeting is well-specified."
    elif has_niches or has_platforms:
        pts = max_pts // 2  # 5
        fb = "Partial targeting. Add both niche tags and required platforms for best creator matching."
        feedback.append(fb)
    else:
        pts = 0
        fb = "No targeting specified. Add niche tags and required platforms for better creator matching."
        feedback.append(fb)
    criteria["targeting"] = {"score": pts, "max": max_pts, "feedback": fb}

    # 5. Assets provided (10 pts)
    # Full: product images OR company URLs provided
    # Partial: only company name
    # Zero: no assets at all
    max_pts = _WEIGHTS["assets_provided"]
    assets = campaign.assets or {}
    image_urls = assets.get("image_urls") or []
    links = assets.get("links") or []
    file_urls = assets.get("file_urls") or []
    company_urls = getattr(campaign, "company_urls", None) or []

    has_images = bool(image_urls)
    has_links = bool(links) or bool(file_urls) or bool(company_urls)

    if has_images or has_links:
        pts = max_pts
        fb = "Assets are provided."
    else:
        pts = 0
        fb = "No assets (product images or company URLs) provided. Add at least one image or website link."
        feedback.append(fb)
    criteria["assets_provided"] = {"score": pts, "max": max_pts, "feedback": fb}

    # 6. Title quality (10 pts)
    max_pts = _WEIGHTS["title_quality"]
    title = (campaign.title or "").strip()
    title_len = len(title)
    if 15 <= title_len <= 80:
        pts = max_pts
        fb = "Title is descriptive and well-sized."
    elif 10 <= title_len <= 100:
        pts = max_pts // 2  # 5
        fb = "Title is slightly outside ideal range (15-80 chars). Make it more descriptive."
        feedback.append(fb)
    else:
        pts = 0
        if title_len < 10:
            fb = f"Campaign title is too short ({title_len} chars). Use a descriptive title of 15-80 characters."
        else:
            fb = f"Campaign title is too long ({title_len} chars). Keep it under 80 characters."
        feedback.append(fb)
    criteria["title_quality"] = {"score": pts, "max": max_pts, "feedback": fb}

    # 7. Dates valid (5 pts)
    max_pts = _WEIGHTS["dates_valid"]
    start_date = campaign.start_date
    end_date = campaign.end_date
    now = datetime.now(timezone.utc)

    if start_date and end_date:
        # Ensure timezone-aware for comparison
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        duration_days = (end_date - start_date).days
        start_in_future = start_date.date() >= now.date()
        end_after_start = end_date > start_date
        duration_ok = 7 <= duration_days <= 90

        if start_in_future and end_after_start and duration_ok:
            pts = max_pts
            fb = "Dates are valid."
        elif end_after_start and 1 <= duration_days <= 365:
            pts = max_pts // 2  # 2
            if not start_in_future:
                fb = "Start date is in the past. Set start date to today or later."
            else:
                fb = f"Campaign duration ({duration_days} days) is outside ideal range (7-90 days)."
            feedback.append(fb)
        else:
            pts = 0
            if not end_after_start:
                fb = "End date must be after start date."
            else:
                fb = "Campaign dates are invalid."
            feedback.append(fb)
    else:
        pts = 0
        fb = "Campaign dates are missing."
        feedback.append(fb)
    criteria["dates_valid"] = {"score": pts, "max": max_pts, "feedback": fb}

    # 8. Budget sufficient (10 pts)
    max_pts = _WEIGHTS["budget_sufficient"]
    budget = float(campaign.budget_total or 0)
    if budget >= 100:
        pts = max_pts
        fb = "Budget is sufficient."
    elif budget >= 50:
        pts = max_pts // 2  # 5
        fb = "Budget below recommended minimum. Campaigns under $100 reach fewer creators."
        feedback.append(fb)
    else:
        pts = 0
        fb = "Budget below minimum. Add funds to reach at least $100 for meaningful creator reach."
        feedback.append(fb)
    criteria["budget_sufficient"] = {"score": pts, "max": max_pts, "feedback": fb}

    total_score = sum(c["score"] for c in criteria.values())
    passed = total_score >= ACTIVATION_THRESHOLD

    return {
        "score": total_score,
        "passed": passed,
        "feedback": feedback,
        "criteria": criteria,
    }


# ── AI review ─────────────────────────────────────────────────────


async def ai_review_campaign(campaign) -> dict:
    """Server-side Gemini AI review. Catches what rules can't.

    Test-mode env vars (read live, not at module load):
      AMPLIFIER_UAT_BYPASS_AI_REVIEW=1  → return bypassed marker
      AMPLIFIER_UAT_FORCE_AI_REVIEW_RESULT=<json> → return that JSON directly

    Returns:
        {
            "passed": bool | None,
            "brand_safety": "safe" | "caution" | "reject" | None,
            "concerns": list[str],
            "niche_rate_assessment": str | None,
            "error": str (only on fallback/bypass)
        }
    """
    # UAT bypass flag — forces fallback branch so AI review is skipped entirely
    if os.environ.get("AMPLIFIER_UAT_BYPASS_AI_REVIEW", "").strip() == "1":
        logger.info("AI review bypassed (UAT flag) — mechanical-only")
        return {
            "passed": None,
            "brand_safety": None,
            "concerns": [],
            "niche_rate_assessment": None,
            "error": "bypassed",
        }

    # UAT force-result flag — pin a specific outcome without calling Gemini
    force_result = os.environ.get("AMPLIFIER_UAT_FORCE_AI_REVIEW_RESULT", "").strip()
    if force_result:
        try:
            result = json.loads(force_result)
            logger.info("AI review forced via UAT flag: brand_safety=%s", result.get("brand_safety"))
            return result
        except json.JSONDecodeError:
            logger.warning("AMPLIFIER_UAT_FORCE_AI_REVIEW_RESULT is not valid JSON — ignoring")

    # Real Gemini call
    try:
        result = await _run_gemini_review(campaign)
        return result
    except Exception as exc:
        logger.error("AI review failed, falling back to mechanical-only: %s", exc, exc_info=True)
        return {
            "passed": None,
            "brand_safety": None,
            "concerns": [],
            "niche_rate_assessment": None,
            "error": "fallback",
        }


async def _run_gemini_review(campaign) -> dict:
    """Call Gemini to review the campaign. Returns parsed dict."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set on server")

    title = campaign.title or ""
    brief = campaign.brief or ""
    guidance = campaign.content_guidance or ""
    rules = campaign.payout_rules or {}
    targeting = campaign.targeting or {}
    niche_tags = targeting.get("niche_tags") or []

    prompt = f"""You are a campaign quality reviewer for a social media marketplace. Review this advertising campaign and assess brand safety.

Campaign Title: {title}
Campaign Brief: {brief}
Content Guidance for creators: {guidance}
Niche Tags / Target Audience: {", ".join(niche_tags) if niche_tags else "Not specified"}
Payout Rates: {json.dumps(rules)}

Review for these 5 concerns:
1. Is the brief coherent and specific, or vague filler text?
2. Are the payout rates competitive for this niche? (finance campaigns need higher rates than lifestyle)
3. Does the content guidance contain anything harmful? (attacking competitors, misleading claims, fake reviews, defamation)
4. Does the targeting make sense for the product? (finance product targeting fashion = mismatch)
5. Is this a legitimate product, or does it look like a scam or spam?

Return ONLY valid JSON (no markdown, no commentary):
{{
  "passed": true or false,
  "brand_safety": "safe" or "caution" or "reject",
  "concerns": ["concern 1", "concern 2"],
  "niche_rate_assessment": "competitive" or "below average" or "too low"
}}

Rules:
- brand_safety = "reject" ONLY for content with harmful guidance (fake reviews, competitor attacks, defamation, scam/misleading claims)
- brand_safety = "caution" for borderline cases (aggressive tone, vague suspicious claims)
- brand_safety = "safe" for legitimate campaigns
- concerns must mention specific issues found (e.g. "competitor", "false claims", "defamation", "harmful content", "niche mismatch", "targeting mismatch")
- If no concerns, return an empty concerns list"""

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
            text = response.text.strip()
            result = _parse_json_response(text)

            # Validate and normalize
            if result.get("brand_safety") not in ("safe", "caution", "reject"):
                result["brand_safety"] = "safe"
            if not isinstance(result.get("concerns"), list):
                result["concerns"] = []
            if "passed" not in result:
                result["passed"] = result.get("brand_safety") != "reject"
            if "niche_rate_assessment" not in result:
                result["niche_rate_assessment"] = None

            return result
        except Exception as e:
            last_error = e
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                logger.warning("Gemini model %s rate limited during AI review, trying next...", model)
                continue
            raise

    raise last_error


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
