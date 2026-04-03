"""Mistral AI text generation provider."""

from __future__ import annotations

import logging

from ai.provider import AiProvider

logger = logging.getLogger(__name__)


class MistralProvider(AiProvider):

    def __init__(self, api_key: str):
        from mistralai.client import Mistral
        self._client = Mistral(api_key=api_key)
        self._connected = True

    @property
    def name(self) -> str:
        return "mistral"

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def generate_text(self, prompt: str) -> str:
        response = self._client.chat.complete(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
