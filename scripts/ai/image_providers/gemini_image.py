"""Google Gemini image generation provider.

Primary provider: 500 free images/day, best quality among free tiers.
Supports both text-to-image (generate_images) and image-to-image
(generate_content with image input for multimodal transformation).
"""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path

from ai.image_provider import ImageProvider

logger = logging.getLogger(__name__)


class GeminiImageProvider(ImageProvider):
    """Gemini Flash Image — txt2img via generate_images, img2img via multimodal generate_content."""

    # Unified model list for both txt2img and img2img — Gemini native image
    # models (free-tier) accept text-only OR image+text input via generate_content
    # with response_modalities=["IMAGE"]. Imagen 4 requires paid plan so we
    # cannot use it on the free tier.
    _IMAGE_MODELS = ["gemini-2.5-flash-image", "gemini-3.1-flash-image-preview"]

    def __init__(self, api_key: str):
        from google import genai
        self._client = genai.Client(api_key=api_key)
        self._connected = True
        self._rate_limited_until = 0.0

    @property
    def name(self) -> str:
        return "gemini_image"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_rate_limited(self) -> bool:
        if self._rate_limited_until > time.time():
            return True
        self._rate_limited_until = 0.0
        return False

    @property
    def supports_img2img(self) -> bool:
        return True

    async def text_to_image(
        self, prompt: str, output_path: str,
        width: int = 1080, height: int = 1080,
        negative_prompt: str | None = None,
    ) -> str:
        """Generate image via Gemini native image model (free-tier)."""
        from google.genai import types

        full_prompt = prompt
        if negative_prompt:
            full_prompt = f"{prompt}\n\nAvoid: {negative_prompt}"

        config = types.GenerateContentConfig(response_modalities=["IMAGE"])
        contents = [types.Part.from_text(text=full_prompt)]

        last_err = None
        for model in self._IMAGE_MODELS:
            try:
                response = self._client.models.generate_content(
                    model=model, contents=contents, config=config,
                )
                if response.candidates:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, "inline_data") and part.inline_data and part.inline_data.data:
                            img_bytes = part.inline_data.data
                            Path(output_path).write_bytes(img_bytes)
                            logger.info("Gemini txt2img: saved %d bytes to %s (model=%s)",
                                        len(img_bytes), output_path, model)
                            return output_path
                last_err = RuntimeError(f"Gemini returned no image (model={model})")
            except Exception as e:
                last_err = e
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    self._rate_limited_until = time.time() + 60
                    logger.warning("Gemini image rate-limited on %s", model)
                    continue
                if "not found" in err_str.lower() or "not supported" in err_str.lower():
                    logger.warning("Gemini model %s not available, trying next", model)
                    continue
                raise

        raise last_err or RuntimeError("All Gemini image models failed")

    async def image_to_image(
        self, source_image_path: str, prompt: str,
        output_path: str, strength: float = 0.7,
    ) -> str:
        """Transform image via Gemini multimodal generate_content.

        Sends the source image + prompt to Gemini's multimodal model and asks
        it to generate a new image based on both. This uses the same API and
        quota as text generation but with image output enabled.
        """
        from google.genai import types

        # Load source image as bytes
        with open(source_image_path, "rb") as f:
            source_bytes = f.read()

        # Detect mime from extension; default to jpeg
        ext = Path(source_image_path).suffix.lower()
        source_mime = {
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(ext, "image/jpeg")

        contents = [
            types.Part.from_bytes(data=source_bytes, mime_type=source_mime),
            types.Part.from_text(text=(
                f"Generate a new lifestyle photograph inspired by this product image. "
                f"{prompt} "
                f"The output should be a single photorealistic image that looks like "
                f"a casual phone photo, not a studio shot. Output ONLY the image."
            )),
        ]

        # Gemini native image models need response_modalities=["IMAGE"] so they
        # return an image as inline_data instead of text.
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        )

        last_err = None
        for model in self._IMAGE_MODELS:
            try:
                response = self._client.models.generate_content(
                    model=model, contents=contents, config=config,
                )
                if response.candidates:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, "inline_data") and part.inline_data and part.inline_data.data:
                            img_bytes = part.inline_data.data
                            Path(output_path).write_bytes(img_bytes)
                            logger.info("Gemini img2img: saved %d bytes to %s (model=%s)",
                                        len(img_bytes), output_path, model)
                            return output_path
                last_err = RuntimeError(f"Gemini img2img returned no image (model={model})")
            except Exception as e:
                last_err = e
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    self._rate_limited_until = time.time() + 60
                    logger.warning("Gemini img2img rate-limited on %s", model)
                    continue
                if "not found" in err_str.lower() or "not supported" in err_str.lower():
                    logger.warning("Gemini img2img model %s not available, trying next", model)
                    continue
                raise

        raise last_err or RuntimeError("All Gemini img2img models failed")

    @staticmethod
    def _get_aspect_ratio(width: int, height: int) -> str:
        ratio = width / height
        if ratio > 1.5:
            return "16:9"
        elif ratio > 1.2:
            return "3:2"
        elif ratio < 0.67:
            return "9:16"
        elif ratio < 0.83:
            return "2:3"
        else:
            return "1:1"
