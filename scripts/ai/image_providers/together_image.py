"""Together AI image generation (FLUX.1 Schnell free tier)."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from ai.image_provider import ImageProvider

logger = logging.getLogger(__name__)


class TogetherImageProvider(ImageProvider):
    """Together AI — $25 signup credit, FLUX.1 Schnell at $0.003/image."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "together"

    @property
    def is_connected(self) -> bool:
        return bool(self._api_key)

    async def text_to_image(
        self, prompt: str, output_path: str,
        width: int = 1080, height: int = 1080,
        negative_prompt: str | None = None,
    ) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.together.xyz/v1/images/generations",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": "black-forest-labs/FLUX.1-schnell-Free",
                    "prompt": prompt,
                    "width": min(width, 1024),
                    "height": min(height, 1024),
                    "steps": 4,
                    "n": 1,
                    "response_format": "b64_json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            img_b64 = data["data"][0]["b64_json"]
            Path(output_path).write_bytes(base64.b64decode(img_b64))
        logger.info("Together: saved image to %s", output_path)
        return output_path
