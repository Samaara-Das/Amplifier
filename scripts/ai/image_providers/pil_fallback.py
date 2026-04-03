"""PIL branded template fallback — last resort when all API providers fail."""

from __future__ import annotations

import logging
from pathlib import Path

from ai.image_provider import ImageProvider

logger = logging.getLogger(__name__)


class PilFallbackProvider(ImageProvider):
    """PIL-based branded image: dark gradient background with white text overlay."""

    @property
    def name(self) -> str:
        return "pil_fallback"

    @property
    def is_connected(self) -> bool:
        return True  # Always available

    async def text_to_image(
        self, prompt: str, output_path: str,
        width: int = 1080, height: int = 1080,
        negative_prompt: str | None = None,
    ) -> str:
        from PIL import Image, ImageDraw, ImageFont

        # Dark gradient background
        img = Image.new("RGB", (width, height), color=(26, 26, 46))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("arial.ttf", max(24, width // 22))
        except OSError:
            font = ImageFont.load_default()

        # Word-wrap the prompt to fit
        text = prompt[:120]
        margin = width // 10
        y = height // 3
        draw.text((margin, y), text, fill="white", font=font)

        img.save(output_path, "JPEG", quality=85)
        logger.info("PIL fallback: saved branded image to %s", output_path)
        return output_path
