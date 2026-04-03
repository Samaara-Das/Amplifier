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


# ── Text Providers (via AiManager) ───────────────────────────────
# v2/v3 upgrade: providers extracted to scripts/ai/ with pluggable interface.
# ContentGenerator now uses AiManager for text generation with auto-fallback.

def _get_ai_manager():
    """Lazy-initialize the global AiManager singleton."""
    global _ai_manager
    if _ai_manager is None:
        from ai.manager import create_default_manager
        _ai_manager = create_default_manager()
    return _ai_manager

_ai_manager = None


# ── Image providers ──────────────────────────────────────────────


async def _cloudflare_image(prompt: str, output_path: str) -> str:
    """Generate image via Cloudflare Workers AI (free tier — 10k neurons/day)."""
    import base64
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id or not api_token:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN not set")
    model = "@cf/black-forest-labs/flux-1-schnell"
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_token}"},
            json={"prompt": prompt, "num_steps": 4},
        )
        if resp.status_code != 200:
            error_detail = resp.text[:200]
            raise RuntimeError(f"Cloudflare AI returned {resp.status_code}: {error_detail}")
        # Response is JSON with base64-encoded JPEG in result.image
        data = resp.json()
        img_b64 = data["result"]["image"]
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(img_b64))
    return output_path


async def _together_image(prompt: str, output_path: str) -> str:
    """Generate image via Together AI FLUX.1 schnell (free tier)."""
    api_key = os.getenv("TOGETHER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TOGETHER_API_KEY not set")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.together.xyz/v1/images/generations",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "black-forest-labs/FLUX.1-schnell-Free",
                "prompt": prompt,
                "width": 1024,
                "height": 1024,
                "steps": 4,
                "n": 1,
                "response_format": "b64_json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        import base64
        img_b64 = data["data"][0]["b64_json"]
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(img_b64))
    return output_path


async def _pollinations_image(prompt: str, output_path: str) -> str:
    """Generate image via Pollinations AI (requires API key)."""
    import urllib.parse
    api_key = os.getenv("POLLINATIONS_API_KEY", "").strip()
    encoded = urllib.parse.quote(prompt)
    url = f"https://gen.pollinations.ai/image/{encoded}?width=1080&height=1080&nologo=true&model=turbo"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)
    return output_path


def _pil_fallback_image(campaign_title: str, output_path: str) -> str:
    """Generate a branded image using PIL (last resort)."""
    try:
        from utils.image_generator import generate_landscape_image
        return str(generate_landscape_image(campaign_title, output_path))
    except Exception:
        # Minimal PIL fallback if image_generator fails
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1080, 1080), color=(26, 26, 46))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 48)
        except OSError:
            font = ImageFont.load_default()
        draw.text((100, 450), campaign_title[:60], fill="white", font=font)
        img.save(output_path)
        return output_path


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
        return _parse_json_response(raw_text)

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

    async def generate_image(self, prompt: str, platform: str = "default") -> str | None:
        """Generate image for campaign. Returns path to image file or None."""
        # Output path
        img_dir = ROOT / "data" / "campaign_images"
        img_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(img_dir / f"campaign_{platform}_{id(prompt) % 100000}.png")

        # 1. Try Cloudflare Workers AI (free tier)
        try:
            logger.info("Generating image via Cloudflare Workers AI...")
            return await _cloudflare_image(prompt, output_path)
        except Exception as e:
            logger.warning("Cloudflare AI image gen failed: %s", e)

        # 2. Try Together AI FLUX (free tier)
        try:
            logger.info("Generating image via Together AI FLUX...")
            return await _together_image(prompt, output_path)
        except Exception as e:
            logger.warning("Together AI image gen failed: %s", e)

        # 3. Try Pollinations
        try:
            logger.info("Generating image via Pollinations...")
            return await _pollinations_image(prompt, output_path)
        except Exception as e:
            logger.warning("Pollinations image gen failed: %s", e)

        # 4. PIL branded template (last resort)
        try:
            logger.info("Falling back to PIL branded image...")
            return _pil_fallback_image(prompt[:60], output_path)
        except Exception as e:
            logger.error("All image generation failed: %s", e)
            return None
