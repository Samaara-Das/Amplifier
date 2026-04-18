"""4-Phase AI Content Agent — Research → Strategy → Creation → Review.

Replaces the single-prompt ContentGenerator with an intelligent pipeline that
adapts content to campaign goals, learns from performance data, and produces
format-aware, platform-native content.

Phases:
1. Research (weekly per campaign): Deep-dive into product, competitors, trends
2. Strategy (weekly per campaign): Map campaign_goal + tone → content plan
3. Creation (daily): Generate platform-native content following the strategy
4. Review: Auto-approve (full_auto) or queue for user review (semi_auto)

Uses existing AiManager (Gemini → Mistral → Groq) — all free-tier providers.
Falls back to basic ContentGenerator.generate() if anything fails.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent

# ── Goal → Strategy mapping ─────────────────────────────────────

GOAL_STRATEGY = {
    "leads": {
        "x": {"formats": ["text", "image_text"], "cta": "link_in_bio",
               "posts_per_day": 2, "post_times_est": ["08:00", "18:00"],
               "image_probability": 0.5,
               "hooks": ["problem_solution", "social_proof", "stat"]},
        "linkedin": {"formats": ["text", "image_text"], "cta": "comment_link",
                     "posts_per_day": 1, "post_times_est": ["10:00"],
                     "image_probability": 0.7,
                     "hooks": ["story", "stat", "contrarian"]},
        "facebook": {"formats": ["text", "image_text"], "cta": "link_post",
                     "posts_per_day": 1, "post_times_est": ["13:00"],
                     "image_probability": 0.6,
                     "hooks": ["social_proof", "curiosity"]},
        "reddit": {"formats": ["text"], "cta": "subtle_mention",
                   "posts_per_day": 0.5, "post_times_est": ["13:00"],
                   "image_probability": 0.0,
                   "hooks": ["story", "contrarian"]},
    },
    "virality": {
        "x": {"formats": ["text", "image_text"], "cta": "retweet",
               "posts_per_day": 3, "post_times_est": ["08:00", "13:00", "18:00"],
               "image_probability": 0.6,
               "hooks": ["contrarian", "curiosity", "surprising_result"]},
        "linkedin": {"formats": ["text", "image_text"], "cta": "share",
                     "posts_per_day": 1, "post_times_est": ["10:00"],
                     "image_probability": 0.8,
                     "hooks": ["contrarian", "story", "stat"]},
        "facebook": {"formats": ["text", "image_text"], "cta": "share",
                     "posts_per_day": 2, "post_times_est": ["13:00", "20:00"],
                     "image_probability": 0.7,
                     "hooks": ["curiosity", "surprising_result"]},
        "reddit": {"formats": ["text"], "cta": "upvote",
                   "posts_per_day": 1, "post_times_est": ["13:00"],
                   "image_probability": 0.1,
                   "hooks": ["contrarian", "story"]},
    },
    "brand_awareness": {
        "x": {"formats": ["text", "image_text"], "cta": "natural_mention",
               "posts_per_day": 1, "post_times_est": ["08:00"],
               "image_probability": 0.4,
               "hooks": ["story", "social_proof", "curiosity"]},
        "linkedin": {"formats": ["text", "image_text"], "cta": "natural_mention",
                     "posts_per_day": 0.5, "post_times_est": ["10:00"],
                     "image_probability": 0.6,
                     "hooks": ["story", "stat"]},
        "facebook": {"formats": ["text", "image_text"], "cta": "natural_mention",
                     "posts_per_day": 0.5, "post_times_est": ["20:00"],
                     "image_probability": 0.5,
                     "hooks": ["story", "social_proof"]},
        "reddit": {"formats": ["text"], "cta": "genuine_review",
                   "posts_per_day": 0.3, "post_times_est": ["13:00"],
                   "image_probability": 0.0,
                   "hooks": ["story", "contrarian"]},
    },
    "engagement": {
        "x": {"formats": ["text"], "cta": "reply",
               "posts_per_day": 2, "post_times_est": ["08:00", "18:00"],
               "image_probability": 0.2,
               "hooks": ["curiosity", "contrarian", "question"]},
        "linkedin": {"formats": ["text"], "cta": "comment",
                     "posts_per_day": 1, "post_times_est": ["10:00"],
                     "image_probability": 0.3,
                     "hooks": ["question", "contrarian", "stat"]},
        "facebook": {"formats": ["text"], "cta": "comment",
                     "posts_per_day": 1, "post_times_est": ["20:00"],
                     "image_probability": 0.2,
                     "hooks": ["question", "curiosity"]},
        "reddit": {"formats": ["text"], "cta": "discussion",
                   "posts_per_day": 0.5, "post_times_est": ["13:00"],
                   "image_probability": 0.0,
                   "hooks": ["question", "contrarian"]},
    },
}

# ── Hook descriptions for prompts ───────────────────────────────

HOOK_DESCRIPTIONS = {
    "problem_solution": "Start with a common problem the audience has, then reveal the product as the solution. E.g. 'I used to struggle with X. Then I found Y.'",
    "surprising_result": "Lead with an unexpected outcome. E.g. 'I didn't expect this to actually work, but here's what happened after 2 weeks.'",
    "social_proof": "Reference what others are doing/saying. E.g. 'Everyone's been talking about this. I finally tried it.'",
    "curiosity": "Create a knowledge gap. E.g. 'There's a reason most people get this wrong — and it's not what you think.'",
    "contrarian": "Challenge conventional wisdom. E.g. 'Unpopular opinion: the way most people do X is completely backwards.'",
    "story": "Start with a personal narrative. E.g. 'Last week something happened that completely changed how I think about X.'",
    "stat": "Lead with a striking number. E.g. '73% of people don't know this about X. Here's why it matters.'",
    "question": "Open with a thought-provoking question. E.g. 'What would you do if you could X without Y?'",
}

# ── Tone descriptions ───────────────────────────────────────────

TONE_GUIDE = {
    "professional": "Polished, authoritative, data-driven. Suit LinkedIn well. Avoid slang.",
    "casual": "Relaxed, conversational, like texting a friend. Use contractions, informal language.",
    "edgy": "Bold, opinionated, slightly provocative. Challenge the status quo. Short punchy sentences.",
    "educational": "Clear, structured, teaches something. Use 'Here's how/why' framing. Step-by-step when possible.",
    "humorous": "Witty, self-deprecating, playful. Use humor to make the product memorable.",
    "inspirational": "Uplifting, motivational, aspirational. Connect the product to bigger life goals.",
}


# ── Research Phase ──────────────────────────────────────────────


async def _run_research(campaign: dict, manager) -> dict:
    """Phase 1: Deep-dive into campaign product, URLs, and context.

    Scrapes company URLs (if any), analyzes campaign assets, and builds
    a research context that the strategy and creation phases can use.

    Stores results in agent_research table for caching (weekly refresh).

    Args:
        campaign: Campaign data dict
        manager: AiManager instance

    Returns: Research context dict with keys:
        product_summary, key_features, target_audience, competitive_angle,
        content_angles, scraped_content
    """
    from utils.content_generator import _scrape_url_deep, _build_research_brief

    campaign_id = campaign.get("campaign_id") or campaign.get("server_id")

    # Check cache: skip if researched within the last 7 days
    # Filter to full_research rows only — strategy rows share the same table
    from utils.local_db import get_research
    existing = get_research(campaign_id)
    research_rows = [r for r in existing if r.get("research_type") == "full_research"]
    if research_rows:
        latest = research_rows[0]  # get_research returns DESC, so [0] is newest
        created = latest.get("created_at", "")
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            # SQLite datetime('now') is UTC-naive; normalize to UTC-aware if missing tz
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - created_dt < timedelta(days=7):
                logger.info("Using cached research for campaign %s (age: %s)", campaign_id, created)
                try:
                    return json.loads(latest["content"])
                except (json.JSONDecodeError, TypeError):
                    return {"scraped_content": latest["content"]}
        except (ValueError, TypeError):
            pass

    # Scrape company URLs
    assets = campaign.get("assets") or {}
    if isinstance(assets, str):
        try:
            assets = json.loads(assets)
        except (json.JSONDecodeError, TypeError):
            assets = {}

    urls = []
    for key in ("company_urls", "urls", "links"):
        raw = assets.get(key) or []
        if isinstance(raw, list):
            urls.extend(u for u in raw if isinstance(u, str) and u.startswith("http"))

    scraped_data = campaign.get("scraped_data") or {}
    if isinstance(scraped_data, str):
        try:
            scraped_data = json.loads(scraped_data)
        except (json.JSONDecodeError, TypeError):
            scraped_data = {}
    extra = scraped_data.get("urls") or []
    if isinstance(extra, list):
        urls.extend(u for u in extra if isinstance(u, str) and u.startswith("http"))

    # Deduplicate, limit to 3
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)
        if len(unique_urls) >= 3:
            break

    scrape_results = []
    for url in unique_urls:
        data = _scrape_url_deep(url)
        if data:
            scrape_results.append(data)

    scraped_brief = _build_research_brief(scrape_results) if scrape_results else ""

    # Build research context from campaign data + scraped content
    title = campaign.get("title", "")
    brief = campaign.get("brief", "")
    guidance = campaign.get("content_guidance", "")
    goal = campaign.get("campaign_goal", "brand_awareness")
    tone = campaign.get("tone", "")

    # Use AI to synthesize research into structured context
    research_prompt = f"""Analyze this campaign and provide a structured research brief.

CAMPAIGN TITLE: {title}
CAMPAIGN BRIEF: {brief}
CONTENT GUIDANCE: {guidance}
CAMPAIGN GOAL: {goal}
TONE: {tone or 'not specified'}

{scraped_brief}

Return ONLY valid JSON (no markdown fences):
{{
    "product_summary": "1-2 sentence summary of what the product/service is",
    "key_features": ["feature 1", "feature 2", "feature 3"],
    "target_audience": "who would benefit from this product",
    "competitive_angle": "what makes this product different from alternatives",
    "content_angles": ["angle 1 for content", "angle 2", "angle 3", "angle 4", "angle 5"],
    "emotional_hooks": ["emotional trigger 1", "emotional trigger 2", "emotional trigger 3"],
    "pricing": "pricing info if found on website, or empty string",
    "testimonials": ["testimonial 1 if found", "testimonial 2 if found"]
}}"""

    try:
        raw = await manager.generate(research_prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
            raw = re.sub(r"\n?```\s*$", "", raw)
        research = json.loads(raw)
    except Exception as e:
        logger.warning("AI research synthesis failed: %s. Using basic context.", e)
        research = {
            "product_summary": brief[:200] if brief else title,
            "key_features": [],
            "target_audience": "general audience",
            "competitive_angle": "",
            "content_angles": [],
            "emotional_hooks": [],
            "pricing": "",
            "testimonials": [],
        }

    research["scraped_content"] = scraped_brief

    # ── Recent niche news via Gemini grounded search ───────────────
    # Gives creation phase real events to reference for timelier posts.
    niche = research.get("target_audience", "") or title or goal
    news_prompt = (
        f"List 3 to 5 recent news headlines (last 30 days) about the niche or topic: "
        f"'{niche}'. Return ONLY a JSON array of headline strings, e.g. "
        f'["Headline 1", "Headline 2"]. No markdown fences.'
    )
    try:
        news_raw = await manager.generate_with_search(news_prompt)
        if news_raw:
            news_raw = news_raw.strip()
            if news_raw.startswith("```"):
                news_raw = re.sub(r"^```(?:json)?\s*\n?", "", news_raw)
                news_raw = re.sub(r"\n?```\s*$", "", news_raw)
            parsed_news = json.loads(news_raw)
            if isinstance(parsed_news, list):
                research["recent_niche_news"] = [str(h) for h in parsed_news[:5]]
                logger.info("Research: got %d news headlines for '%s'", len(research["recent_niche_news"]), niche)
            else:
                research["recent_niche_news"] = []
        else:
            research["recent_niche_news"] = []
    except Exception as e:
        logger.warning("Recent niche news fetch failed: %s. Skipping.", e)
        research["recent_niche_news"] = []

    # ── Product image analysis via Gemini vision ──────────────────
    # Cache: done once per weekly research refresh (controlled by outer 7-day cache).
    image_analysis = ""
    local_images: list[str] = []

    # Preferred source: downloaded product images at data/product_images/{campaign_id}/
    # (populated by background_agent._download_campaign_product_images()).
    download_dir = ROOT / "data" / "product_images" / str(campaign_id)
    if download_dir.exists():
        for p in sorted(download_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                local_images.append(str(p))

    # Fallback: check campaign.assets for already-local file paths
    # (legacy field names: "product_images" or "image_urls" when they happen to be absolute paths).
    if not local_images:
        for key in ("product_images", "image_urls"):
            raw = assets.get(key) or []
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    raw = []
            if isinstance(raw, list):
                local_images.extend(p for p in raw if isinstance(p, str) and os.path.isfile(p))
    if local_images:
        vision_prompt = (
            "Describe these product photos visually: colors, composition, vibe, "
            "what they show, how they could be used in social media posts. "
            "Keep it concise — 2-3 sentences max."
        )
        try:
            image_analysis = await manager.generate_with_vision(vision_prompt, local_images[:3])
            if image_analysis:
                logger.info("Research: product image analysis complete (%d chars)", len(image_analysis))
        except Exception as e:
            logger.warning("Product image vision analysis failed: %s. Skipping.", e)
    research["image_analysis"] = image_analysis or ""

    # Cache research
    from utils.local_db import add_research
    add_research(campaign_id, "full_research", json.dumps(research))
    logger.info("Research complete for campaign %s: %d angles, %d features",
                campaign_id, len(research.get("content_angles", [])),
                len(research.get("key_features", [])))

    return research


# ── Strategy Phase ──────────────────────────────────────────────


def _build_strategy(campaign: dict, research: dict, insights: list[dict] = None) -> dict:
    """Phase 2: Determine content plan based on campaign_goal + tone.

    Uses the static GOAL_STRATEGY mapping as a base, then adjusts based on:
    - Campaign preferred_formats (if specified by company)
    - Performance insights from past posts (if available)
    - Research context (content angles to use)

    Args:
        campaign: Campaign data dict
        research: Research context from Phase 1
        insights: Performance insights from agent_content_insights table

    Returns: Strategy dict with per-platform plan
    """
    goal = campaign.get("campaign_goal", "brand_awareness")
    tone = campaign.get("tone") or "casual"
    preferred = campaign.get("preferred_formats") or {}
    if isinstance(preferred, str):
        try:
            preferred = json.loads(preferred)
        except (json.JSONDecodeError, TypeError):
            preferred = {}

    # Start with goal-based defaults
    base = GOAL_STRATEGY.get(goal, GOAL_STRATEGY["brand_awareness"])

    strategy = {"platforms": {}, "tone": tone, "tone_guide": TONE_GUIDE.get(tone, ""),
                "goal": goal, "content_angles": research.get("content_angles", []),
                "emotional_hooks": research.get("emotional_hooks", [])}

    from utils.guard import filter_disabled
    for platform in filter_disabled(["x", "linkedin", "facebook", "reddit"]):
        plat_base = dict(base.get(platform, base.get("linkedin", {})))

        # Override formats if company specified preferences
        if platform in preferred and preferred[platform]:
            plat_base["formats"] = preferred[platform]

        # Adjust hooks based on performance insights
        if insights:
            plat_insights = [i for i in insights if i.get("platform") == platform and i.get("sample_count", 0) >= 3]
            if plat_insights:
                # Sort by engagement rate, use top hooks
                plat_insights.sort(key=lambda x: x.get("avg_engagement_rate", 0), reverse=True)
                top_hooks = [i["hook_type"] for i in plat_insights[:3] if i.get("hook_type")]
                if top_hooks:
                    plat_base["hooks"] = top_hooks
                    logger.info("Strategy: %s hooks adjusted by insights → %s", platform, top_hooks)

        strategy["platforms"][platform] = plat_base

    logger.info("Strategy built for goal=%s, tone=%s: %s",
                goal, tone, {p: s.get("formats") for p, s in strategy["platforms"].items()})

    return strategy


async def _refine_strategy_with_ai(
    campaign: dict,
    base_strategy: dict,
    research: dict,
    manager,
    user_profiles: list[dict] = None,
) -> dict:
    """Phase 2 (AI layer): Refine the base strategy using AI reasoning.

    Checks for a cached "strategy" row in agent_research (7-day TTL).
    If cached, reuses it. Otherwise makes ONE AI call to:
      - Adapt to the creator's natural voice (from user_profiles)
      - Incorporate performance insights already baked into base_strategy
      - Add creator_voice_notes per platform

    Falls back to base_strategy on any AI or JSON failure.

    Args:
        campaign: Campaign data dict.
        base_strategy: Strategy from _build_strategy().
        research: Research context from Phase 1.
        manager: AiManager instance.
        user_profiles: List of user profile dicts (one per platform).

    Returns:
        Refined strategy dict with optional creator_voice_notes per platform.
    """
    campaign_id = campaign.get("campaign_id") or campaign.get("server_id")

    # Check strategy cache (separate from full_research rows)
    from utils.local_db import get_research, add_research
    existing = get_research(campaign_id)
    strategy_rows = [r for r in existing if r.get("research_type") == "strategy"]
    if strategy_rows:
        latest = strategy_rows[0]
        created = latest.get("created_at", "")
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            # SQLite datetime('now') is UTC-naive; normalize to UTC-aware if missing tz
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - created_dt < timedelta(days=7):
                logger.info("Using cached strategy for campaign %s", campaign_id)
                try:
                    cached = json.loads(latest["content"])
                    if isinstance(cached, dict) and "platforms" in cached:
                        return cached
                except (json.JSONDecodeError, TypeError):
                    pass
        except (ValueError, TypeError):
            pass

    # Build concise profile summary for the AI
    profile_text = ""
    if user_profiles:
        profile_parts = []
        for p in user_profiles:
            plat = p.get("platform", "unknown")
            bio = p.get("bio", "")
            style = p.get("style_notes", "")
            niches = p.get("niches", "")
            followers = p.get("follower_count", 0)
            recent = p.get("recent_posts", "")
            if isinstance(recent, list):
                recent = "; ".join(str(r)[:100] for r in recent[:3])
            elif isinstance(recent, str):
                recent = recent[:300]
            profile_parts.append(
                f"Platform: {plat} | Followers: {followers} | "
                f"Bio: {bio[:100]} | Style: {style} | Niches: {niches} | "
                f"Recent posts: {recent}"
            )
        profile_text = "\n".join(profile_parts)

    goal = campaign.get("campaign_goal", "brand_awareness")
    tone = campaign.get("tone") or "casual"
    research_summary = {
        "product_summary": research.get("product_summary", ""),
        "target_audience": research.get("target_audience", ""),
        "content_angles": research.get("content_angles", [])[:3],
    }

    refine_prompt = f"""You are a social media strategist for Amplifier, a creator marketing platform.

CAMPAIGN GOAL: {goal}
CAMPAIGN TONE: {tone}
RESEARCH SUMMARY: {json.dumps(research_summary)}

CREATOR PROFILES:
{profile_text or "No profile data available."}

BASE STRATEGY (JSON):
{json.dumps(base_strategy, indent=2)}

Refine the base strategy above. Output the same JSON structure but adjusted for:
1. The creator's natural voice and style (adapt hook styles and tone_guide)
2. What content angles resonate with this creator's audience
3. Add "creator_voice_notes" per platform (1-2 sentences: how to match this creator's voice)

Return ONLY valid JSON (no markdown fences). Preserve all existing fields."""

    try:
        raw = await manager.generate(refine_prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
            raw = re.sub(r"\n?```\s*$", "", raw)
        refined = json.loads(raw)
        if not isinstance(refined, dict) or "platforms" not in refined:
            raise ValueError("Refined strategy missing 'platforms' key")
        # Cache the refined strategy
        add_research(campaign_id, "strategy", json.dumps(refined))
        logger.info("Strategy refined with AI for campaign %s", campaign_id)
        return refined
    except Exception as e:
        logger.warning("AI strategy refinement failed: %s. Using base strategy.", e)
        return base_strategy


# ── Creation Phase ──────────────────────────────────────────────


CREATION_PROMPT = """You are a UGC (user-generated content) creator posting on behalf of a brand campaign. Your job is to create content that feels like a REAL PERSON genuinely recommending a product — not an ad, not corporate marketing, not influencer cringe.

── CAMPAIGN CONTEXT ──
Title: {title}
Brief: {brief}
Content Guidance: {guidance}

── RESEARCH ──
Product: {product_summary}
Key Features: {key_features}
Target Audience: {target_audience}
Competitive Angle: {competitive_angle}

── STRATEGY ──
Campaign Goal: {goal} — {goal_description}
Tone: {tone} — {tone_guide}
Today's Content Angle: {content_angle}
Emotional Hook to Use: {emotional_hook}

── PLATFORM INSTRUCTIONS ──
{platform_instructions}

── HOOK STYLE ──
Use this hook style: {hook_style}
{hook_description}

── DAILY VARIATION ──
This is day {day_number} of this campaign.{previous_hooks_section}{news_section}{retry_feedback_section}

── HARD RULES ──
- NEVER sound like AI: avoid "In today's fast-paced world", "game-changer", "unlock your potential", "dive in", "let's explore"
- NEVER use corporate marketing language: no "synergy", "innovative solution", "cutting-edge"
- Each platform version must be GENUINELY DIFFERENT — different angle, hook, structure
- Include any must-include phrases/hashtags from the campaign guidance naturally
- Content must feel authentic and personal, like a real user's post
- If a disclaimer is provided, it will be appended automatically — do NOT include it in your content

── OUTPUT FORMAT ──
Return ONLY a valid JSON object (no markdown fences, no extra text) with these keys:
{output_keys}

Only include keys for the requested platforms."""


GOAL_DESCRIPTIONS = {
    "leads": "Drive clicks, signups, and conversions. Every post should have a clear call-to-action that drives traffic.",
    "virality": "Maximize shares and reach. Content should be surprising, emotional, or provocative enough that people WANT to share it.",
    "brand_awareness": "Build familiarity and positive association. Content should be memorable and consistently present the brand lifestyle.",
    "engagement": "Drive comments, replies, and discussion. Ask questions, take positions, and create content people want to respond to.",
}


async def _run_creation(campaign: dict, strategy: dict, research: dict,
                        manager, enabled_platforms: list[str],
                        day_number: int = 1, previous_hooks: list[str] = None,
                        retry_feedback: list[str] = None) -> dict:
    """Phase 3: Generate platform-native content following the strategy.

    Builds a rich prompt using research context + strategy directives,
    then generates content via AiManager.

    Returns: dict with platform keys (x, linkedin, facebook, reddit, image_prompt)
    """
    import random

    title = campaign.get("title", "")
    brief = campaign.get("brief", "")
    guidance = campaign.get("content_guidance", "")
    goal = strategy.get("goal", "brand_awareness")
    tone = strategy.get("tone", "casual")

    # Pick today's content angle (rotate through available angles)
    angles = research.get("content_angles", [])
    content_angle = angles[(day_number - 1) % len(angles)] if angles else "general product recommendation"

    # Pick emotional hook (rotate)
    emotions = research.get("emotional_hooks", [])
    emotional_hook = emotions[(day_number - 1) % len(emotions)] if emotions else "genuine enthusiasm"

    # Build platform-specific instructions
    platform_lines = []
    hook_types_to_use = []

    for platform in enabled_platforms:
        plat_strategy = strategy.get("platforms", {}).get(platform, {})
        formats = plat_strategy.get("formats", ["text"])
        cta = plat_strategy.get("cta", "natural_mention")
        hooks = plat_strategy.get("hooks", ["story"])

        # Pick hook for this platform (rotate by day + platform index)
        plat_idx = enabled_platforms.index(platform)
        hook = hooks[(day_number + plat_idx) % len(hooks)] if hooks else "story"
        hook_types_to_use.append(hook)

        # Per-platform creator_voice_notes from AI-refined strategy
        voice_note = strategy.get("platforms", {}).get(platform, {}).get("creator_voice_notes", "")
        voice_suffix = f" Creator voice: {voice_note}" if voice_note else ""

        if platform == "x":
            platform_lines.append(f'- "x": Tweet text (max 280 chars). Format: {formats[0]}. CTA style: {cta}. One punchy hook + key benefit. 1-3 hashtags placed naturally.{voice_suffix}')
        elif platform == "linkedin":
            platform_lines.append(f'- "linkedin": Post text (500-1500 chars). Format: {formats[0]}. CTA style: {cta}. Story format — aggressive line breaks (first 2 lines are all people see before "see more"). End with a question. 3-5 hashtags at end.{voice_suffix}')
        elif platform == "facebook":
            platform_lines.append(f'- "facebook": Post text (200-800 chars). Format: {formats[0]}. CTA style: {cta}. Conversational, like telling friends. Ask a question to drive comments. 0-2 hashtags.{voice_suffix}')
        elif platform == "reddit":
            platform_lines.append(
                f'- "reddit": Object with "title" (60-120 chars, descriptive) and "body" (500-1500 chars). '
                f'Format: {formats[0]}. CTA style: {cta}. Write like a community member. '
                f'No hashtags, no emojis, no self-promotion tone. '
                f'MANDATORY: body must include at least ONE caveat, limitation, or "one thing I didn\'t love" — '
                f'real community members never only praise. This is non-negotiable for authenticity.{voice_suffix}'
            )

    platform_lines.append('- "image_prompt": A vivid 1-sentence description for generating an image. Visually bold, lifestyle-oriented, scroll-stopping.')

    # Pick dominant hook for the day
    primary_hook = hook_types_to_use[0] if hook_types_to_use else "story"
    hook_desc = HOOK_DESCRIPTIONS.get(primary_hook, "Write an engaging opening.")

    # Previous hooks section
    prev_section = ""
    if previous_hooks and day_number > 1:
        hooks_list = "\n".join(f"  - {h}" for h in previous_hooks[:8])
        prev_section = f"""
Previous posts started with:
{hooks_list}
Write something COMPLETELY DIFFERENT. Use a different angle, different hook emotion, different structure."""

    # Recent niche news section (injected into prompt when available)
    recent_news = research.get("recent_niche_news") or []
    news_section = ""
    if recent_news:
        headlines = "\n".join(f"  - {h}" for h in recent_news[:5])
        news_section = f"""

── RECENT NEWS ──
Reference one of these recent events if it naturally fits today's angle.
Do NOT force it — only use if it flows organically with the hook:
{headlines}"""

    # Retry feedback section (only present on quality-check retries)
    retry_section = ""
    if retry_feedback:
        reasons_list = "\n".join(f"  - {r}" for r in retry_feedback)
        retry_section = f"""

── CRITICAL FIXES FROM PRIOR ATTEMPT ──
Your previous output was REJECTED for these specific reasons. Fix ALL of them:
{reasons_list}
Pay close attention to length limits and banned phrases. A second rejection means the output is discarded entirely."""

    # Build output keys description
    output_keys = "\n".join(platform_lines)

    prompt = CREATION_PROMPT.format(
        title=title,
        brief=brief,
        guidance=guidance,
        product_summary=research.get("product_summary", brief[:200]),
        key_features=", ".join(research.get("key_features", [])[:5]),
        target_audience=research.get("target_audience", "general audience"),
        competitive_angle=research.get("competitive_angle", ""),
        goal=goal,
        goal_description=GOAL_DESCRIPTIONS.get(goal, "Build awareness"),
        tone=tone,
        tone_guide=TONE_GUIDE.get(tone, "Natural, conversational"),
        content_angle=content_angle,
        emotional_hook=emotional_hook,
        platform_instructions="\n".join(platform_lines),
        hook_style=primary_hook,
        hook_description=hook_desc,
        day_number=day_number,
        previous_hooks_section=prev_section,
        news_section=news_section,
        retry_feedback_section=retry_section,
        output_keys=output_keys,
    )

    # Generate via AiManager
    from utils.content_generator import _parse_json_response, _append_ftc_disclosure
    raw = await manager.generate(prompt)
    content = _parse_json_response(raw)

    # Append FTC disclosure
    disclaimer = campaign.get("disclaimer_text") or "#ad"
    content = _append_ftc_disclosure(content, disclaimer)

    return content


# ── Main ContentAgent class ─────────────────────────────────────


class ContentAgent:
    """4-phase AI content generation pipeline.

    Drop-in enhancement over ContentGenerator. Uses the same AiManager
    and ImageManager, but adds research, strategy, and insight-driven
    creation phases.

    Usage:
        agent = ContentAgent()
        content = await agent.generate_content(campaign_data, platforms, day_number)
    """

    def __init__(self):
        from utils.content_generator import _get_ai_manager, _get_image_manager
        self._manager = _get_ai_manager()
        self._image_manager = _get_image_manager()

    @property
    def has_providers(self) -> bool:
        return self._manager.has_providers

    def get_posting_plan(self, campaign: dict, enabled_platforms: list[str] = None,
                         day_number: int = 1) -> dict:
        """Get the posting plan for today based on campaign strategy.

        The strategy determines per-platform:
        - How many posts today (posts_per_day, fractional = skip some days)
        - What EST times to post at
        - Whether each post should have an image

        Returns: {
            "platforms": {
                "x": {"post_count": 2, "times_est": ["08:00", "18:00"],
                       "include_image": [True, False]},
                "linkedin": {"post_count": 1, "times_est": ["10:00"],
                             "include_image": [True]},
                "reddit": {"post_count": 0, ...},  # skipped today
            }
        }
        """
        import random

        if enabled_platforms is None:
            from utils.guard import filter_disabled
            enabled_platforms = filter_disabled(["x", "linkedin", "facebook", "reddit"])
        else:
            from utils.guard import filter_disabled
            enabled_platforms = filter_disabled(enabled_platforms)

        # Build strategy (lightweight — no AI calls)
        research = {"content_angles": [], "emotional_hooks": []}
        try:
            from utils.local_db import get_content_insights
            insights = get_content_insights()
        except Exception:
            insights = None
        strategy = _build_strategy(campaign, research, insights)

        plan = {"platforms": {}}

        for platform in enabled_platforms:
            plat_strategy = strategy.get("platforms", {}).get(platform, {})
            ppd = plat_strategy.get("posts_per_day", 1)
            times = plat_strategy.get("post_times_est", ["08:00"])
            img_prob = plat_strategy.get("image_probability", 0.5)

            # Handle fractional posts_per_day (e.g., 0.5 = every other day)
            if ppd < 1:
                # Post on this day? Use day_number to deterministically decide
                if (day_number % round(1 / ppd)) != 0:
                    plan["platforms"][platform] = {
                        "post_count": 0, "times_est": [], "include_image": [],
                        "skip_reason": f"Scheduled every {round(1/ppd)} days (next: day {day_number + round(1/ppd) - (day_number % round(1/ppd))})",
                    }
                    continue
                post_count = 1
                times = times[:1]
            else:
                post_count = int(ppd)
                times = times[:post_count]
                # Pad times if we need more than defined
                while len(times) < post_count:
                    # Add evenly spaced times
                    last_h = int(times[-1].split(":")[0])
                    next_h = min(last_h + 3, 22)
                    times.append(f"{next_h:02d}:00")

            # Decide image per post slot
            include_image = [random.random() < img_prob for _ in range(post_count)]

            plan["platforms"][platform] = {
                "post_count": post_count,
                "times_est": times,
                "include_image": include_image,
            }

        return plan

    async def generate_content(
        self,
        campaign: dict,
        enabled_platforms: list[str] = None,
        day_number: int = 1,
        previous_hooks: list[str] = None,
        user_profiles: list[dict] = None,
    ) -> dict:
        """Full 4-phase content generation pipeline.

        Phase 1 (Research): Cached weekly. Scrapes URLs, synthesizes context.
                            Now also fetches recent niche news + product image analysis.
        Phase 2 (Strategy): Built from campaign_goal + tone + insights,
                            then AI-refined with creator profiles (cached weekly).
        Phase 3 (Creation): Generates platform content using research + strategy,
                            including news timeliness injection + Reddit caveat rule.
        Phase 4 (Review): Validates quality (length, Reddit shape, banned phrases,
                          diversity). Retries once if validation fails.

        Falls back to basic ContentGenerator on any phase failure.

        Args:
            campaign: Campaign data dict.
            enabled_platforms: Platforms to generate for. Defaults to all enabled.
            day_number: Day in campaign lifecycle (for hook rotation + variation).
            previous_hooks: First lines of recent posts for anti-repetition.
            user_profiles: List of scraped user profile dicts (one per platform).
                          Used by Phase 2 to adapt tone/voice to creator style.

        Returns: {platform: text, ..., image_prompt: str}
        """
        if enabled_platforms is None:
            from utils.guard import filter_disabled
            enabled_platforms = filter_disabled(["x", "linkedin", "facebook", "reddit"])
        else:
            from utils.guard import filter_disabled
            enabled_platforms = filter_disabled(enabled_platforms)

        if not self._manager.has_providers:
            raise RuntimeError("No AI providers available. Set GEMINI_API_KEY in config/.env")

        try:
            # Phase 1: Research (cached weekly)
            research = await _run_research(campaign, self._manager)
            logger.info("Phase 1 (Research) complete: %d angles", len(research.get("content_angles", [])))

            # Phase 2: Strategy (base) + AI refinement (cached weekly)
            from utils.local_db import get_content_insights
            insights = get_content_insights()
            base_strategy = _build_strategy(campaign, research, insights)
            strategy = await _refine_strategy_with_ai(
                campaign, base_strategy, research, self._manager, user_profiles
            )
            logger.info("Phase 2 (Strategy) complete: goal=%s, tone=%s",
                        strategy.get("goal"), strategy.get("tone"))

            # Build previous_drafts_text for diversity validator
            # Use previous_hooks (first lines only) — concise proxy for full draft text
            previous_drafts_text = list(previous_hooks) if previous_hooks else []

            # Phase 3: Creation
            content = await _run_creation(
                campaign, strategy, research, self._manager,
                enabled_platforms, day_number, previous_hooks,
            )
            logger.info("Phase 3 (Creation) complete: %d platform(s)", len([k for k in content if k != "image_prompt"]))

            # Phase 4: Quality validation + optional retry
            from utils.content_quality import validate_content
            is_valid, reasons = await validate_content(
                content, previous_drafts_text, self._manager
            )
            if not is_valid:
                logger.warning("Quality check failed: %s. Retrying once.", reasons)
                # Build expanded previous_hooks to push AI away from failing content
                # Extract first line of each platform text as additional hook context
                extra_hooks = []
                for key, val in content.items():
                    if key == "image_prompt":
                        continue
                    if isinstance(val, str):
                        first_line = val.split("\n")[0][:80]
                        if first_line:
                            extra_hooks.append(first_line)
                    elif isinstance(val, dict):
                        # Reddit: use title as hook context
                        title_text = val.get("title", "")[:80]
                        if title_text:
                            extra_hooks.append(title_text)
                retry_hooks = list(previous_hooks or []) + extra_hooks
                content = await _run_creation(
                    campaign, strategy, research, self._manager,
                    enabled_platforms, day_number, retry_hooks,
                    retry_feedback=reasons,
                )
                is_valid, reasons = await validate_content(
                    content, previous_drafts_text, self._manager
                )
                if not is_valid:
                    raise RuntimeError(f"Quality check failed after retry: {reasons}")

            # Phase 4: Review — content is returned to caller for approval flow
            return content

        except Exception as e:
            logger.warning("ContentAgent pipeline failed: %s. Falling back to basic generator.", e)
            # Fallback to single-prompt ContentGenerator
            from utils.content_generator import ContentGenerator
            gen = ContentGenerator()
            return await gen.generate(campaign, enabled_platforms, day_number, previous_hooks)

    async def generate_image(
        self,
        prompt: str,
        platform: str = "default",
        product_image_path: str | None = None,
        campaign_brief: str | None = None,
    ) -> str | None:
        """Delegate to ContentGenerator's image generation (unchanged)."""
        from utils.content_generator import ContentGenerator
        gen = ContentGenerator()
        return await gen.generate_image(prompt, platform, product_image_path, campaign_brief)
