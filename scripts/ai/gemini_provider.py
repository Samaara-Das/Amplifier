"""Google Gemini text generation provider."""

from __future__ import annotations

import logging
import time

from ai.provider import AiProvider

logger = logging.getLogger(__name__)


class GeminiProvider(AiProvider):
    """Google Gemini with model fallback chain (2.5-flash → 2.0-flash → 2.5-flash-lite)."""

    MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]

    def __init__(self, api_key: str):
        from google import genai
        self._client = genai.Client(api_key=api_key)
        self._connected = True
        self._rate_limited_until = 0.0

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_rate_limited(self) -> bool:
        if self._rate_limited_until > time.time():
            return True
        self._rate_limited_until = 0.0
        return False

    async def generate_text(self, prompt: str) -> str:
        last_err = None
        for model in self.MODELS:
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                return response.text
            except Exception as e:
                last_err = e
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    logger.warning("Gemini %s rate-limited, trying next model...", model)
                    self._rate_limited_until = time.time() + 60
                    continue
                raise
        raise last_err
