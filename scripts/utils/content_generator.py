"""Content generation via free AI APIs with fallback chain.

Replaces PowerShell + Claude CLI for campaign content generation.
Providers (text): Gemini → Mistral → Groq
Providers (image): Cloudflare Workers AI → Together AI → Pollinations → PIL templates
"""

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent

# Load API keys from config/.env
load_dotenv(ROOT / "config" / ".env")

# ── Prompt template ──────────────────────────────────────────────

CONTENT_PROMPT = """You are a UGC (user-generated content) creator posting on behalf of a brand campaign. Your job is to create content that feels like a REAL PERSON genuinely recommending a product — not an ad, not corporate marketing, not influencer cringe.

CAMPAIGN:
Title: {title}
Brief: {brief}
Content Guidance: {content_guidance}
Product Links/Assets: {assets}

Generate content for these platforms: {platforms}

── YOUR ROLE ──
You are posting AS a regular person who discovered this product and wants to share it. The content should feel like UGC — authentic, personal, and relatable. Think "friend telling you about something cool" not "brand selling you something."

── HOOK (first 1-2 sentences) ──
The hook MUST stop the scroll. Use one of these patterns:
- Problem-solution: "I used to [common problem]. Then I found [product]."
- Surprising result: "I didn't expect [product] to actually [benefit], but here's what happened."
- Social proof: "Everyone's been talking about [product]. I finally tried it."
- Curiosity gap: "There's a reason [specific claim] — and most people don't know about it."
- Contrarian: "Unpopular opinion: [common belief] is wrong. Here's why."

── BODY ──
After the hook:
- Share a specific, personal-feeling experience with the product
- Mention 1-2 concrete features/benefits (from the campaign brief)
- Be genuine — include a minor caveat or "I wish it had X" to sound real
- End with a natural call-to-action (not salesy)
- Use simple, conversational language

── HARD RULES ──
- NEVER sound like AI: avoid "In today's fast-paced world", "game-changer", "unlock your potential", "leverage", "dive in", "let's explore"
- NEVER use corporate marketing language: no "synergy", "innovative solution", "cutting-edge"
- Each platform version must be GENUINELY DIFFERENT — different angle, hook, structure
- Include any must-include phrases/hashtags from the campaign guidance naturally
- Avoid anything listed in the campaign's must-avoid guidance
- Content must feel authentic and personal, like a real user's post

── OUTPUT FORMAT ──
Return ONLY a valid JSON object (no markdown fences, no extra text) with these keys:
- "x": Tweet text (max 280 chars). One punchy hook + key benefit. 1-3 hashtags placed naturally.
- "linkedin": Post text (500-1500 chars). Story format — personal experience with the product. Aggressive line breaks (first 2 lines are all people see before "see more"). End with a question. 3-5 hashtags at end.
- "facebook": Post text (200-800 chars). Conversational, like telling friends. Ask a question to drive comments. 0-2 hashtags.
- "reddit": Object with "title" (60-120 chars, descriptive, NOT clickbait) and "body" (500-1500 chars). Write like a community member sharing a genuine find. No hashtags, no emojis, no self-promotion tone. Include specifics about what you liked and didn't.
- "image_prompt": A vivid description for generating an image featuring the product (1 sentence). Should be visually bold, lifestyle-oriented, and scroll-stopping.

Only include keys for the requested platforms.
"""


def _parse_json_response(text: str) -> dict:
    """Extract JSON from an AI response, handling markdown fences."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not parse JSON from response: {text[:200]}")


# ── FTC disclosure ────────────────────────────────────────────────

X_CHAR_LIMIT = 280


def _append_ftc_disclosure(content: dict, disclaimer: str) -> dict:
    """Append FTC advertising disclosure to generated content per platform.

    US FTC requires paid promotional content to include clear disclosure.
    Appends the disclaimer text to each platform's content appropriately:
    - X: last line (trims content body if needed to fit 280-char limit)
    - LinkedIn/Facebook: appended as a final paragraph
    - Reddit: appended to body text only (title left untouched)
    """
    result = dict(content)

    # ── X (Twitter) — respect 280-char limit ──
    if "x" in result and isinstance(result["x"], str):
        tweet = result["x"].rstrip()
        suffix = f"\n{disclaimer}"
        combined = tweet + suffix
        if len(combined) <= X_CHAR_LIMIT:
            result["x"] = combined
        else:
            # Trim the tweet body to make room for the disclaimer
            max_body = X_CHAR_LIMIT - len(suffix)
            if max_body > 0:
                result["x"] = tweet[:max_body].rstrip() + suffix
            else:
                # Disclaimer alone exceeds limit — just append, let user handle
                result["x"] = combined

    # ── LinkedIn — append as last paragraph ──
    if "linkedin" in result and isinstance(result["linkedin"], str):
        result["linkedin"] = result["linkedin"].rstrip() + f"\n\n{disclaimer}"

    # ── Facebook — append as last paragraph ──
    if "facebook" in result and isinstance(result["facebook"], str):
        result["facebook"] = result["facebook"].rstrip() + f"\n\n{disclaimer}"

    # ── Reddit — append to body only, leave title untouched ──
    if "reddit" in result and isinstance(result["reddit"], dict):
        reddit = dict(result["reddit"])
        body = reddit.get("body", "")
        if isinstance(body, str):
            reddit["body"] = body.rstrip() + f"\n\n{disclaimer}"
        result["reddit"] = reddit

    return result


# ── Providers (via AiManager + ImageManager) ────────────────────
# v2/v3 upgrade: providers extracted to scripts/ai/ with pluggable interfaces.
# ContentGenerator uses AiManager for text and ImageManager for images.

_ai_manager = None
_image_manager = None


def _get_ai_manager():
    """Lazy-initialize the global AiManager singleton."""
    global _ai_manager
    if _ai_manager is None:
        from ai.manager import create_default_manager
        _ai_manager = create_default_manager()
    return _ai_manager


def _get_image_manager():
    """Lazy-initialize the global ImageManager singleton."""
    global _image_manager
    if _image_manager is None:
        from ai.image_manager import create_default_image_manager
        _image_manager = create_default_image_manager()
    return _image_manager


# ── Image generation (via ImageManager) ─────────────────────────
# Old inline providers (_cloudflare_image, _together_image, _pollinations_image,
# _pil_fallback_image) have been extracted to scripts/ai/image_providers/.


# ── Webcrawler helpers ───────────────────────────────────────────

WEBCRAWLER_PATH = "C:/Users/dassa/Work/webcrawler/crawl.py"


def _scrape_url_deep(url: str) -> dict:
    """Deep scrape a URL using the webcrawler CLI.

    Returns dict with keys: title, url, content (markdown), metadata (OG tags).
    Returns {} on failure.
    """
    try:
        result = subprocess.run(
            ["python", WEBCRAWLER_PATH, "--json", "fetch", url],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if "error" not in data:
                return data
        return {}
    except Exception as e:
        logger.debug("Webcrawler fetch failed for %s: %s", url, e)
        return {}


def _scrape_images(url: str) -> list[dict]:
    """Extract images from a URL via webcrawler CLI.

    Returns list of {url, alt} dicts. Returns [] on failure.
    """
    try:
        result = subprocess.run(
            ["python", WEBCRAWLER_PATH, "--json", "images", url],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            return data.get("images", [])
        return []
    except Exception as e:
        logger.debug("Webcrawler images failed for %s: %s", url, e)
        return []


def _build_research_brief(scrape_results: list[dict]) -> str:
    """Combine multiple URL scrapes into a compact research brief for the prompt.

    Caps total length to ~3000 chars to avoid overshooting the prompt budget.
    """
    if not scrape_results:
        return ""

    sections = []
    char_budget = 3000

    for data in scrape_results:
        if not data:
            continue
        url = data.get("url", "")
        title = data.get("title", "")
        content = data.get("content", "")
        metadata = data.get("metadata", {})

        description = (
            metadata.get("og:description")
            or metadata.get("description")
            or ""
        )

        # First 800 chars of page content usually contains the product pitch
        content_snippet = content[:800].strip() if content else ""

        parts = []
        if title:
            parts.append(f"Page: {title}")
        if url:
            parts.append(f"URL: {url}")
        if description:
            parts.append(f"Description: {description}")
        if content_snippet:
            parts.append(f"Content:\n{content_snippet}")

        if parts:
            section = "\n".join(parts)
            current_total = len("\n\n---\n\n".join(sections))
            if current_total + len(section) > char_budget:
                break
            sections.append(section)

    if not sections:
        return ""

    return "── RESEARCH (scraped from company URLs) ──\n" + "\n\n---\n\n".join(sections)


# ── Main class ───────────────────────────────────────────────────


class ContentGenerator:
    """Generate campaign content using AiManager with pluggable provider fallback.

    v2/v3 upgrade: providers are now in scripts/ai/ with a clean interface.
    The AiManager handles registration, rate-limit detection, and auto-fallback.
    """

    def __init__(self):
        self._manager = _get_ai_manager()
        if not self._manager.has_providers:
            logger.error("No AI providers available. Set GEMINI_API_KEY in config/.env")

    async def generate(self, campaign: dict, enabled_platforms: list[str] = None,
                       day_number: int = None, previous_hooks: list[str] = None) -> dict:
        """Generate per-platform content from campaign brief.

        Args:
            campaign: Campaign data dict with title, brief, content_guidance, assets.
            enabled_platforms: List of platform names to generate for.
            day_number: Optional day number of this campaign (for daily variation).
            previous_hooks: Optional list of first lines from previous drafts (for anti-repetition).

        Returns: {
            "x": "tweet text",
            "linkedin": "post text",
            "facebook": "post text",
            "reddit": {"title": "...", "body": "..."},
            "image_prompt": "description for image generation"
        }
        """
        if not self._manager.has_providers:
            raise RuntimeError("No AI providers available. Set GEMINI_API_KEY in config/.env")

        if enabled_platforms is None:
            enabled_platforms = ["x", "linkedin", "facebook", "reddit"]

        prompt = CONTENT_PROMPT.format(
            title=campaign.get("title", ""),
            brief=campaign.get("brief", ""),
            content_guidance=campaign.get("content_guidance", ""),
            assets=campaign.get("assets", ""),
            platforms=", ".join(enabled_platforms),
        )

        # Add daily variation context if provided
        if day_number is not None and day_number > 1:
            variation_section = f"\n\n── DAILY VARIATION (CRITICAL) ──\nThis is day {day_number} of this campaign. You MUST write completely fresh content."
            if previous_hooks:
                hooks_list = "\n".join(f"  - {h}" for h in previous_hooks)
                variation_section += (
                    f"\nPrevious posts started with:\n{hooks_list}\n"
                    "Write something COMPLETELY DIFFERENT. Use a different angle, different hook emotion, "
                    "different structure. Do NOT repeat or rephrase any of the above openings."
                )
            prompt += variation_section

        # v2/v3 upgrade: use AiManager with auto-fallback
        raw_text = await self._manager.generate(prompt)
        content = _parse_json_response(raw_text)

        # Append FTC disclosure to all platform content
        disclaimer = campaign.get("disclaimer_text") or "#ad"
        content = _append_ftc_disclosure(content, disclaimer)

        return content

    async def research_and_generate(
        self,
        campaign: dict,
        enabled_platforms: list[str] = None,
        day_number: int = None,
        previous_hooks: list[str] = None,
    ) -> dict:
        """Generate content with a research phase that scrapes company URLs first.

        1. Extract company URLs from campaign assets or scraped_data fields.
        2. Deep scrape each URL via webcrawler CLI (best-effort, no crash on failure).
        3. Build a research brief and inject it into the assets field.
        4. Call generate() with the enriched campaign data.

        Falls back transparently to generate() if no URLs are found or all scrapes fail.
        The existing generate() method is NOT modified.
        """
        # Collect URLs to scrape
        assets = campaign.get("assets") or {}
        if isinstance(assets, str):
            try:
                assets = json.loads(assets)
            except (json.JSONDecodeError, TypeError):
                assets = {}

        company_urls: list[str] = []

        # assets.company_urls list
        raw_urls = assets.get("company_urls") or assets.get("urls") or []
        if isinstance(raw_urls, list):
            company_urls.extend(u for u in raw_urls if isinstance(u, str) and u.startswith("http"))

        # scraped_data may also carry URLs
        scraped_data = campaign.get("scraped_data") or {}
        if isinstance(scraped_data, str):
            try:
                scraped_data = json.loads(scraped_data)
            except (json.JSONDecodeError, TypeError):
                scraped_data = {}
        extra_urls = scraped_data.get("urls") or []
        if isinstance(extra_urls, list):
            company_urls.extend(u for u in extra_urls if isinstance(u, str) and u.startswith("http"))

        # Deduplicate, limit to 3 URLs to keep latency reasonable
        seen: set[str] = set()
        unique_urls: list[str] = []
        for u in company_urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)
            if len(unique_urls) >= 3:
                break

        if not unique_urls:
            logger.info("research_and_generate: no URLs found, falling back to generate()")
            return await self.generate(campaign, enabled_platforms, day_number, previous_hooks)

        # Scrape URLs
        logger.info("research_and_generate: scraping %d URL(s): %s", len(unique_urls), unique_urls)
        scrape_results: list[dict] = []
        for url in unique_urls:
            data = _scrape_url_deep(url)
            if data:
                scrape_results.append(data)
                logger.debug("Scraped %s — %d chars", url, len(data.get("content", "")))
            else:
                logger.debug("Scrape returned nothing for %s", url)

        if not scrape_results:
            logger.info("research_and_generate: all scrapes failed, falling back to generate()")
            return await self.generate(campaign, enabled_platforms, day_number, previous_hooks)

        # Build research brief and inject into the enriched campaign
        research_brief = _build_research_brief(scrape_results)

        # Merge existing assets string with research brief
        existing_assets = campaign.get("assets", "")
        if isinstance(existing_assets, dict):
            existing_assets = json.dumps(existing_assets)
        enriched_assets = f"{existing_assets}\n\n{research_brief}".strip() if existing_assets else research_brief

        enriched_campaign = {**campaign, "assets": enriched_assets}
        logger.info("research_and_generate: enriched prompt with %d chars of research", len(research_brief))

        return await self.generate(enriched_campaign, enabled_platforms, day_number, previous_hooks)

    async def generate_image(
        self,
        prompt: str,
        platform: str = "default",
        product_image_path: str | None = None,
        campaign_brief: str | None = None,
    ) -> str | None:
        """Generate image for campaign via ImageManager with auto-fallback.

        Supports three modes:
        - text-to-image: generate from prompt (enhanced with UGC framework)
        - image-to-image: transform product photo into UGC scene (if product_image_path set)
        - simple prompt: use raw prompt with minimal enhancement

        Returns path to image file or None on total failure.
        """
        img_dir = ROOT / "data" / "campaign_images"
        img_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(img_dir / f"campaign_{platform}_{id(prompt) % 100000}.jpg")

        manager = _get_image_manager()
        if not manager.has_providers:
            logger.error("No image providers available")
            return None

        try:
            # Mode 1: Image-to-image (campaign has product photos)
            if product_image_path and Path(product_image_path).exists():
                from ai.image_prompts import build_img2img_prompt
                img2img_prompt = build_img2img_prompt(
                    product_name=prompt[:60],
                    campaign_brief=campaign_brief,
                )
                logger.info("Using img2img with product photo: %s", product_image_path)
                return await manager.transform(product_image_path, img2img_prompt, output_path)

            # Mode 2: Text-to-image with UGC enhancement
            from ai.image_prompts import build_simple_prompt, get_negative_prompt
            enhanced_prompt = build_simple_prompt(prompt)
            negative = get_negative_prompt()
            logger.info("Generating text-to-image with UGC-enhanced prompt")
            return await manager.generate(enhanced_prompt, output_path, negative_prompt=negative)

        except Exception as e:
            logger.error("Image generation failed: %s", e)
            return None
