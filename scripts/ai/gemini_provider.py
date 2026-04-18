"""Google Gemini text generation provider."""

from __future__ import annotations

import logging
import time

from ai.provider import AiProvider

logger = logging.getLogger(__name__)


class GeminiProvider(AiProvider):
    """Google Gemini with model fallback chain (2.5-flash → 2.0-flash → 2.5-flash-lite)."""

    MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-flash-lite"]
    EMBED_MODEL = "gemini-embedding-001"

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

    async def generate_with_search(self, prompt: str) -> str:
        """Generate text with grounded web search (Gemini Google Search tool).

        Uses Google Search grounding to fetch real-time information. Only
        supported on gemini-2.0-flash and later. Falls back to gemini-2.5-flash
        if grounding is unavailable on the first model.

        Returns:
            Generated text with web-grounded context.

        Raises:
            Exception: Propagated to caller for graceful handling.
        """
        from google.genai import types
        search_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(tools=[search_tool])
        for model in self.MODELS:
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                return response.text
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    logger.warning("Gemini %s rate-limited during search call", model)
                    continue
                # Some models may not support grounding — try next
                if "not supported" in err_str.lower() or "invalid" in err_str.lower():
                    logger.warning("Gemini %s does not support search grounding: %s", model, e)
                    continue
                raise
        raise RuntimeError("All Gemini models failed for generate_with_search")

    async def generate_with_vision(self, prompt: str, image_paths: list[str]) -> str:
        """Generate text from a prompt + one or more local image files.

        Uses Gemini's multimodal capability to analyze product images and
        return a textual description. Images are loaded as bytes + MIME type.

        Args:
            prompt: Text instruction for the model.
            image_paths: Local file paths to images (JPEG/PNG/WEBP).

        Returns:
            Generated text describing or reasoning about the images.

        Raises:
            Exception: Propagated to caller for graceful handling.
        """
        import mimetypes
        from google.genai import types as gtypes

        parts = []
        for path in image_paths:
            try:
                with open(path, "rb") as f:
                    data = f.read()
                mime, _ = mimetypes.guess_type(path)
                mime = mime or "image/jpeg"
                parts.append(gtypes.Part.from_bytes(data=data, mime_type=mime))
            except Exception as e:
                logger.warning("Could not load image %s for vision: %s", path, e)
        parts.append(gtypes.Part.from_text(text=prompt))

        if len(parts) == 1:
            # Only the text prompt — no images loaded
            raise ValueError("No images could be loaded for vision call")

        contents = [gtypes.Content(parts=parts, role="user")]
        for model in self.MODELS:
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=contents,
                )
                return response.text
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    logger.warning("Gemini %s rate-limited during vision call", model)
                    continue
                raise
        raise RuntimeError("All Gemini models failed for generate_with_vision")

    async def embed(self, text: str) -> list[float]:
        """Generate a text embedding using gemini-embedding-001 (3072 dimensions).

        Free-tier. Used for diversity checks — cosine similarity between
        new content and previous drafts.

        Returns:
            List of 768 floats (unit-normalized).

        Raises:
            Exception: Propagated to caller; caller falls back to SequenceMatcher.
        """
        response = self._client.models.embed_content(
            model=self.EMBED_MODEL,
            contents=text,
        )
        return list(response.embeddings[0].values)
