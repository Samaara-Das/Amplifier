"""Draft node — generates per-platform content using Gemini.

Uses research context, user profile, and brand voice from content-templates.md.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent


def _load_brand_voice() -> str:
    """Load content-templates.md as context for the LLM."""
    templates_path = ROOT / "config" / "content-templates.md"
    if templates_path.exists():
        return templates_path.read_text(encoding="utf-8")
    return ""


def _build_research_context(research: list[dict]) -> str:
    """Format research findings into a prompt section."""
    if not research:
        return "No research available."

    sections = []
    for r in research[:8]:  # Limit to keep prompt manageable
        rtype = r.get("type", "")
        if rtype == "web_search":
            sections.append(f"- [{r.get('title', '')}]({r.get('url', '')}): {r.get('snippet', '')}")
        elif rtype == "company_link":
            sections.append(f"- Company page ({r.get('url', '')}): {r.get('content', '')[:300]}")
        elif rtype == "past_performance":
            sections.append(f"- Past insight: {r.get('insight', '')}")
        else:
            sections.append(f"- {json.dumps(r)[:200]}")

    return "\n".join(sections)


def _build_profile_context(profiles: dict[str, dict], platform: str) -> str:
    """Format user profile for a specific platform into prompt context."""
    profile = profiles.get(platform, {})
    if not profile or not profile.get("bio"):
        return "No profile data available — generate in a generic but authentic voice."

    parts = [f"Bio: {profile['bio']}"]
    if profile.get("follower_count"):
        parts.append(f"Followers: {profile['follower_count']}")
    if profile.get("style_notes"):
        parts.append(f"Writing style: {profile['style_notes']}")
    recent = profile.get("recent_posts", [])
    if recent:
        parts.append("Recent posts by this user:")
        for post in recent[:3]:
            parts.append(f"  - {post[:150]}")

    return "\n".join(parts)


DRAFT_PROMPT = """You are writing a social media post for a specific user's {platform} account to promote a campaign.

── CAMPAIGN ──
Title: {title}
Brief: {brief}
Content Guidance: {guidance}

── RESEARCH (use these to make the content informed and relevant) ──
{research_context}

── USER'S {platform_upper} PROFILE (match their voice and style) ──
{profile_context}

── BRAND VOICE RULES ──
{brand_voice}

── TASK ──
Write ONE {platform} post that:
1. Opens with an emotional hook (greed, fear, freedom, FOMO, competence, or security)
2. Delivers real actionable value a beginner can use today
3. Promotes the campaign naturally — NOT like an ad
4. Matches the user's existing voice and style on {platform}
5. Follows all platform-specific format rules from the brand voice doc

{platform_rules}

Return ONLY the post text. No JSON, no markdown fences, no explanation."""


PLATFORM_RULES = {
    "x": "Max 280 characters. One punchy idea. 1-3 hashtags placed naturally. Contrarian takes work best.",
    "linkedin": "500-1500 characters. Narrative/story format. AGGRESSIVE line breaks. End with a question. 3-5 hashtags at end.",
    "facebook": "200-800 characters. Conversational, community-oriented. Ask a question. 0-2 hashtags max.",
    "reddit": 'Return as JSON: {"title": "60-120 chars, descriptive, NOT clickbait", "body": "500-1500 chars, data-driven, no hashtags/emojis, community member tone"}',
}


def draft_node(state: dict) -> dict:
    """Generate per-platform drafts using Gemini."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    campaign = state.get("campaign", {})
    platforms = state.get("enabled_platforms", ["x", "linkedin", "facebook", "reddit"])
    research = state.get("research", [])
    profiles = state.get("user_profiles", {})

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.error("GEMINI_API_KEY not set — cannot generate drafts")
        return {"drafts": {}, "image_prompt": ""}

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        google_api_key=api_key,
        max_output_tokens=2048,
    )

    brand_voice = _load_brand_voice()
    research_context = _build_research_context(research)

    drafts = {}
    image_prompt = ""

    for platform in platforms:
        logger.info("Drafting for %s...", platform)
        prompt = DRAFT_PROMPT.format(
            platform=platform,
            platform_upper=platform.upper(),
            title=campaign.get("title", ""),
            brief=campaign.get("brief", ""),
            guidance=campaign.get("content_guidance", "") or "",
            research_context=research_context,
            profile_context=_build_profile_context(profiles, platform),
            brand_voice=brand_voice[:3000],  # Truncate to avoid token limits
            platform_rules=PLATFORM_RULES.get(platform, ""),
        )

        try:
            response = llm.invoke(prompt)
            draft_text = response.content.strip()

            # For Reddit, try to parse as JSON
            if platform == "reddit":
                try:
                    parsed = json.loads(draft_text)
                    drafts[platform] = parsed  # {"title": ..., "body": ...}
                except json.JSONDecodeError:
                    # Try to extract JSON from the response
                    import re
                    match = re.search(r'\{[\s\S]*\}', draft_text)
                    if match:
                        drafts[platform] = json.loads(match.group())
                    else:
                        drafts[platform] = {"title": draft_text[:120], "body": draft_text}
            else:
                drafts[platform] = draft_text

            logger.info("Drafted %s (%d chars)", platform,
                        len(draft_text) if isinstance(draft_text, str) else len(json.dumps(drafts[platform])))

        except Exception as e:
            logger.error("Draft failed for %s: %s", platform, e)
            drafts[platform] = ""

    # Generate image prompt from campaign context
    if campaign.get("brief"):
        try:
            img_response = llm.invoke(
                f"Write a 1-sentence vivid image description for a social media post about: "
                f"{campaign.get('title', '')} — {campaign.get('brief', '')[:200]}. "
                f"The image should be bold, attention-grabbing, and professional. "
                f"Return ONLY the description, no explanation."
            )
            image_prompt = img_response.content.strip()
        except Exception as e:
            logger.warning("Image prompt generation failed: %s", e)

    # Store drafts in DB
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from utils.local_db import add_draft
    campaign_id = campaign.get("campaign_id", 0)
    for platform, text in drafts.items():
        draft_text = json.dumps(text) if isinstance(text, dict) else text
        add_draft(campaign_id=campaign_id, platform=platform, draft_text=draft_text)

    return {"drafts": drafts, "image_prompt": image_prompt}
