"""Content generation via free AI APIs with fallback chain.

Replaces PowerShell + Claude CLI for campaign content generation.
Providers (text): Gemini → Mistral → Groq
Providers (image): Gemini → Pollinations → PIL templates
"""

import json
import logging
import os
import re
import tempfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent

# ── Prompt template ──────────────────────────────────────────────

CONTENT_PROMPT = """Generate social media content for a brand campaign.

CAMPAIGN BRIEF:
Title: {title}
Brief: {brief}
Content Guidance: {content_guidance}
Assets/Links: {assets}

Generate content for these platforms: {platforms}

OUTPUT FORMAT: Return ONLY a valid JSON object (no markdown fences, no extra text) with these keys:
- "x": Tweet text (max 280 chars, punchy, native to X)
- "linkedin": Post text (800-1300 chars, professional tone, line breaks for readability, 3-5 hashtags)
- "facebook": Post text (200-800 chars, conversational, engagement-driving)
- "reddit": Object with "title" (60-120 chars) and "body" (500-1500 chars, no hashtags, value-first)
- "image_prompt": A detailed description for generating a campaign image (1 sentence)

Only include keys for the requested platforms.

RULES:
- Each platform version must feel native to that platform
- Content must promote the campaign naturally — not feel like an ad
- Include relevant hashtags where appropriate (not Reddit)
- Be authentic and conversational, not salesy
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


# ── Providers ────────────────────────────────────────────────────


class _GeminiProvider:
    """Google Gemini — text + image generation."""

    def __init__(self, api_key: str):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.name = "gemini"

    async def generate_text(self, prompt: str) -> dict:
        response = self.client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        return _parse_json_response(response.text)

    async def generate_image(self, prompt: str, output_path: str) -> str:
        response = self.client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=prompt,
            config={"number_of_images": 1},
        )
        if response.generated_images:
            image = response.generated_images[0]
            image.image.save(output_path)
            return output_path
        raise RuntimeError("Gemini returned no images")


class _MistralProvider:
    """Mistral AI — text only."""

    def __init__(self, api_key: str):
        from mistralai import Mistral
        self.client = Mistral(api_key=api_key)
        self.name = "mistral"

    async def generate_text(self, prompt: str) -> dict:
        response = self.client.chat.complete(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json_response(response.choices[0].message.content)


class _GroqProvider:
    """Groq — text only (fast inference)."""

    def __init__(self, api_key: str):
        from groq import Groq
        self.client = Groq(api_key=api_key)
        self.name = "groq"

    async def generate_text(self, prompt: str) -> dict:
        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json_response(response.choices[0].message.content)


# ── Image fallbacks ──────────────────────────────────────────────


async def _pollinations_image(prompt: str, output_path: str) -> str:
    """Generate image via Pollinations AI (free, no signup)."""
    import urllib.parse
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&nologo=true"
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url)
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


# ── Main class ───────────────────────────────────────────────────


class ContentGenerator:
    """Generate campaign content using free AI APIs with fallback chain."""

    def __init__(self):
        self.text_providers = []
        self.gemini_provider = None

        # Build provider chain based on available API keys
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        mistral_key = os.getenv("MISTRAL_API_KEY", "").strip()
        groq_key = os.getenv("GROQ_API_KEY", "").strip()

        if gemini_key:
            try:
                provider = _GeminiProvider(gemini_key)
                self.text_providers.append(provider)
                self.gemini_provider = provider
                logger.info("Gemini provider initialized")
            except Exception as e:
                logger.warning("Failed to init Gemini: %s", e)

        if mistral_key:
            try:
                self.text_providers.append(_MistralProvider(mistral_key))
                logger.info("Mistral provider initialized")
            except Exception as e:
                logger.warning("Failed to init Mistral: %s", e)

        if groq_key:
            try:
                self.text_providers.append(_GroqProvider(groq_key))
                logger.info("Groq provider initialized")
            except Exception as e:
                logger.warning("Failed to init Groq: %s", e)

        if not self.text_providers:
            logger.error("No AI providers available. Set GEMINI_API_KEY in config/.env")

    async def generate(self, campaign: dict, enabled_platforms: list[str] = None) -> dict:
        """Generate per-platform content from campaign brief.

        Returns: {
            "x": "tweet text",
            "linkedin": "post text",
            "facebook": "post text",
            "reddit": {"title": "...", "body": "..."},
            "image_prompt": "description for image generation"
        }
        """
        if not self.text_providers:
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

        last_error = None
        for provider in self.text_providers:
            try:
                logger.info("Generating content via %s...", provider.name)
                result = await provider.generate_text(prompt)
                logger.info("Content generated via %s", provider.name)
                return result
            except Exception as e:
                last_error = e
                logger.warning("%s failed: %s. Trying next provider...", provider.name, e)

        raise RuntimeError(f"All text providers failed. Last error: {last_error}")

    async def generate_image(self, prompt: str, platform: str = "default") -> str | None:
        """Generate image for campaign. Returns path to image file or None."""
        # Output path
        img_dir = ROOT / "data" / "campaign_images"
        img_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(img_dir / f"campaign_{platform}_{id(prompt) % 100000}.png")

        # 1. Try Gemini Imagen
        if self.gemini_provider:
            try:
                logger.info("Generating image via Gemini Imagen...")
                return await self.gemini_provider.generate_image(prompt, output_path)
            except Exception as e:
                logger.warning("Gemini image gen failed: %s", e)

        # 2. Try Pollinations (free, no signup)
        try:
            logger.info("Generating image via Pollinations...")
            return await _pollinations_image(prompt, output_path)
        except Exception as e:
            logger.warning("Pollinations image gen failed: %s", e)

        # 3. PIL branded template (last resort)
        try:
            logger.info("Falling back to PIL branded image...")
            return _pil_fallback_image(prompt[:60], output_path)
        except Exception as e:
            logger.error("All image generation failed: %s", e)
            return None
