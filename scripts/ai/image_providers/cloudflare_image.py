"""Cloudflare Workers AI image generation (FLUX.2 Klein / FLUX.1 Schnell)."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from ai.image_provider import ImageProvider

logger = logging.getLogger(__name__)


class CloudflareImageProvider(ImageProvider):
    """Cloudflare Workers AI — ~20-50 free images/day from shared neuron budget."""

    MODEL = "@cf/black-forest-labs/flux-1-schnell"

    def __init__(self, account_id: str, api_token: str):
        self._account_id = account_id
        self._api_token = api_token

    @property
    def name(self) -> str:
        return "cloudflare"

    @property
    def is_connected(self) -> bool:
        return bool(self._account_id and self._api_token)

    async def text_to_image(
        self, prompt: str, output_path: str,
        width: int = 1080, height: int = 1080,
        negative_prompt: str | None = None,
    ) -> str:
        url = (f"https://api.cloudflare.com/client/v4/accounts/"
               f"{self._account_id}/ai/run/{self.MODEL}")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {self._api_token}"},
                json={"prompt": prompt, "num_steps": 4},
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Cloudflare AI returned {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            img_b64 = data["result"]["image"]
            Path(output_path).write_bytes(base64.b64decode(img_b64))
        logger.info("Cloudflare: saved image to %s", output_path)
        return output_path
