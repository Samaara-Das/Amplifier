"""Pollinations AI image generation (free, no signup required)."""

from __future__ import annotations

import logging
import os
import urllib.parse
from pathlib import Path

import httpx

from ai.image_provider import ImageProvider

logger = logging.getLogger(__name__)


class PollinationsImageProvider(ImageProvider):
    """Pollinations — free, rate-limited, variable quality. No signup needed."""

    @property
    def name(self) -> str:
        return "pollinations"

    @property
    def is_connected(self) -> bool:
        return True  # Always available (no credentials needed)

    async def text_to_image(
        self, prompt: str, output_path: str,
        width: int = 1080, height: int = 1080,
        negative_prompt: str | None = None,
    ) -> str:
        encoded = urllib.parse.quote(prompt)
        url = (f"https://gen.pollinations.ai/image/{encoded}"
               f"?width={width}&height={height}&nologo=true&model=turbo")
        headers = {}
        api_key = os.getenv("POLLINATIONS_API_KEY", "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            Path(output_path).write_bytes(resp.content)
        logger.info("Pollinations: saved image to %s", output_path)
        return output_path
