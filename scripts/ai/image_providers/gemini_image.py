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

    # Models to try in order for text-to-image
    _TXT2IMG_MODELS = ["gemini-2.0-flash-exp", "imagen-3.0-generate-002"]
    # Model for img2img (multimodal — accepts image + text, outputs image)
    _IMG2IMG_MODEL = "gemini-2.0-flash-exp"

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
        """Generate image via Gemini generate_images API."""
        from google.genai import types

        # Determine aspect ratio from dimensions
        aspect = self._get_aspect_ratio(width, height)

        config = types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio=aspect,
            output_mime_type="image/jpeg",
            output_compression_quality=90,
            person_generation="ALLOW_ADULT",
            safety_filter_level="BLOCK_ONLY_HIGH",
            add_watermark=False,
        )
        if negative_prompt:
            config.negative_prompt = negative_prompt

        last_err = None
        for model in self._TXT2IMG_MODELS:
            try:
                response = self._client.models.generate_images(
                    model=model,
                    prompt=prompt,
                    config=config,
                )
                if response.generated_images:
                    img_bytes = response.generated_images[0].image.image_bytes
                    Path(output_path).write_bytes(img_bytes)
                    logger.info("Gemini txt2img: saved %d bytes to %s (model=%s)",
                                len(img_bytes), output_path, model)
                    return output_path
                else:
                    last_err = RuntimeError("Gemini returned no images")
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
        from PIL import Image

        # Load source image as bytes
        with open(source_image_path, "rb") as f:
            source_bytes = f.read()

        try:
            response = self._client.models.generate_content(
                model=self._IMG2IMG_MODEL,
                contents=[
                    types.Part.from_bytes(data=source_bytes, mime_type="image/jpeg"),
                    types.Part.from_text(
                        f"Generate a new lifestyle photograph inspired by this product image. "
                        f"{prompt} "
                        f"The output should be a single photorealistic image that looks like "
                        f"a casual phone photo, not a studio shot. Output ONLY the image."
                    ),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="image/jpeg",
                ),
            )

            # Extract image from response
            if response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "inline_data") and part.inline_data:
                        img_bytes = part.inline_data.data
                        Path(output_path).write_bytes(img_bytes)
                        logger.info("Gemini img2img: saved %d bytes to %s", len(img_bytes), output_path)
                        return output_path

            raise RuntimeError("Gemini img2img returned no image in response")

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                self._rate_limited_until = time.time() + 60
            raise

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
