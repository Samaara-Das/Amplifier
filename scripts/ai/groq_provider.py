"""Groq text generation provider (fast inference)."""

from __future__ import annotations

import logging

from ai.provider import AiProvider

logger = logging.getLogger(__name__)


class GroqProvider(AiProvider):

    def __init__(self, api_key: str):
        from groq import Groq
        self._client = Groq(api_key=api_key)
        self._connected = True

    @property
    def name(self) -> str:
        return "groq"

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def generate_text(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
