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
        "x": {"formats": ["text", "image_text"], "cta": "link_in_bio", "frequency": "2x/day",
               "hooks": ["problem_solution", "social_proof", "stat"]},
        "linkedin": {"formats": ["text", "image_text"], "cta": "comment_link", "frequency": "daily",
                     "hooks": ["story", "stat", "contrarian"]},
        "facebook": {"formats": ["text", "image_text"], "cta": "link_post", "frequency": "daily",
                     "hooks": ["social_proof", "curiosity"]},
        "reddit": {"formats": ["text"], "cta": "subtle_mention", "frequency": "3x/week",
                   "hooks": ["story", "contrarian"]},
    },
    "virality": {
        "x": {"formats": ["text", "image_text"], "cta": "retweet", "frequency": "3x/day",
               "hooks": ["contrarian", "curiosity", "surprising_result"]},
        "linkedin": {"formats": ["text", "image_text"], "cta": "share", "frequency": "daily",
                     "hooks": ["contrarian", "story", "stat"]},
        "facebook": {"formats": ["text", "image_text"], "cta": "share", "frequency": "2x/day",
                     "hooks": ["curiosity", "surprising_result"]},
        "reddit": {"formats": ["text"], "cta": "upvote", "frequency": "daily",
                   "hooks": ["contrarian", "story"]},
    },
    "brand_awareness": {
        "x": {"formats": ["text", "image_text"], "cta": "natural_mention", "frequency": "daily",
               "hooks": ["story", "social_proof", "curiosity"]},
        "linkedin": {"formats": ["text", "image_text"], "cta": "natural_mention", "frequency": "3x/week",
                     "hooks": ["story", "stat"]},
        "facebook": {"formats": ["text", "image_text"], "cta": "natural_mention", "frequency": "3x/week",
                     "hooks": ["story", "social_proof"]},
        "reddit": {"formats": ["text"], "cta": "genuine_review", "frequency": "2x/week",
                   "hooks": ["story", "contrarian"]},
    },
    "engagement": {
        "x": {"formats": ["text"], "cta": "reply", "frequency": "2x/day",
               "hooks": ["curiosity", "contrarian", "question"]},
        "linkedin": {"formats": ["text"], "cta": "comment", "frequency": "daily",
                     "hooks": ["question", "contrarian", "stat"]},
        "facebook": {"formats": ["text"], "cta": "comment", "frequency": "daily",
                     "hooks": ["question", "curiosity"]},
        "reddit": {"formats": ["text"], "cta": "discussion", "frequency": "3x/week",
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
    from utils.local_db import get_research
    existing = get_research(campaign_id)
    if existing:
        latest = existing[0]  # ordered DESC
        created = latest.get("created_at", "")
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
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
    "emotional_hooks": ["emotional trigger 1", "emotional trigger 2", "emotional trigger 3"]
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
        }

    research["scraped_content"] = scraped_brief

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

    for platform in ["x", "linkedin", "facebook", "reddit"]:
        plat_base = dict(base.get(platform, base.get("x", {})))

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
This is day {day_number} of this campaign.{previous_hooks_section}

── HARD RULES ──
- NEVER sound like AI: avoid "In today's fast-paced world", "game-changer", "unlock your potential", "leverage", "dive in", "let's explore"
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
                        day_number: int = 1, previous_hooks: list[str] = None) -> dict:
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

        if platform == "x":
            platform_lines.append(f'- "x": Tweet text (max 280 chars). Format: {formats[0]}. CTA style: {cta}. One punchy hook + key benefit. 1-3 hashtags placed naturally.')
        elif platform == "linkedin":
            platform_lines.append(f'- "linkedin": Post text (500-1500 chars). Format: {formats[0]}. CTA style: {cta}. Story format — aggressive line breaks (first 2 lines are all people see before "see more"). End with a question. 3-5 hashtags at end.')
        elif platform == "facebook":
            platform_lines.append(f'- "facebook": Post text (200-800 chars). Format: {formats[0]}. CTA style: {cta}. Conversational, like telling friends. Ask a question to drive comments. 0-2 hashtags.')
        elif platform == "reddit":
            platform_lines.append(f'- "reddit": Object with "title" (60-120 chars, descriptive) and "body" (500-1500 chars). Format: {formats[0]}. CTA style: {cta}. Write like a community member. No hashtags, no emojis, no self-promotion tone.')

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

    async def generate_content(
        self,
        campaign: dict,
        enabled_platforms: list[str] = None,
        day_number: int = 1,
        previous_hooks: list[str] = None,
    ) -> dict:
        """Full 4-phase content generation pipeline.

        Phase 1 (Research): Cached weekly. Scrapes URLs, synthesizes context.
        Phase 2 (Strategy): Built from campaign_goal + tone + insights.
        Phase 3 (Creation): Generates platform content using research + strategy.
        Phase 4 (Review): Returns content dict (caller handles approval flow).

        Falls back to basic ContentGenerator on any phase failure.

        Returns: {platform: text, ..., image_prompt: str}
        """
        if enabled_platforms is None:
            enabled_platforms = ["x", "linkedin", "facebook", "reddit"]

        if not self._manager.has_providers:
            raise RuntimeError("No AI providers available. Set GEMINI_API_KEY in config/.env")

        try:
            # Phase 1: Research (cached weekly)
            research = await _run_research(campaign, self._manager)
            logger.info("Phase 1 (Research) complete: %d angles", len(research.get("content_angles", [])))

            # Phase 2: Strategy
            from utils.local_db import get_content_insights
            insights = get_content_insights()
            strategy = _build_strategy(campaign, research, insights)
            logger.info("Phase 2 (Strategy) complete: goal=%s, tone=%s",
                        strategy.get("goal"), strategy.get("tone"))

            # Phase 3: Creation
            content = await _run_creation(
                campaign, strategy, research, self._manager,
                enabled_platforms, day_number, previous_hooks,
            )
            logger.info("Phase 3 (Creation) complete: %d platform(s)", len([k for k in content if k != "image_prompt"]))

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
