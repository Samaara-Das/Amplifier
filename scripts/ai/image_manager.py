"""Image generation manager with provider registry and auto-fallback.

Same pattern as ai/manager.py for text. Providers are registered at startup.
The manager picks the best available one and falls back on failure.

After every successful generation, the post-processing pipeline runs
automatically to make images look like authentic UGC.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from ai.image_provider import ImageProvider

logger = logging.getLogger(__name__)


class ImageManager:
    """Registry of image providers with auto-fallback."""

    def __init__(self, postprocess: bool = True):
        self._providers: dict[str, ImageProvider] = {}
        self._order: list[str] = []
        self._postprocess = postprocess

    def register(self, provider: ImageProvider) -> None:
        self._providers[provider.name] = provider
        if provider.name not in self._order:
            self._order.append(provider.name)
        logger.info("Registered image provider: %s (img2img=%s)",
                     provider.name, provider.supports_img2img)

    def get(self, name: str) -> Optional[ImageProvider]:
        return self._providers.get(name)

    @property
    def has_providers(self) -> bool:
        return bool(self._providers)

    async def generate(
        self,
        prompt: str,
        output_path: str,
        width: int = 1080,
        height: int = 1080,
        negative_prompt: str | None = None,
    ) -> str:
        """Text-to-image with auto-fallback across providers.

        Post-processes the result for UGC authenticity.
        Returns path to the final image.
        """
        if not self._providers:
            raise RuntimeError("No image providers registered")

        last_error = None
        for name in self._order:
            provider = self._providers[name]
            if not provider.is_connected or provider.is_rate_limited:
                continue
            try:
                logger.info("Generating image via %s...", provider.name)
                result_path = await provider.text_to_image(
                    prompt, output_path, width, height, negative_prompt
                )
                logger.info("Image generated via %s: %s", provider.name, result_path)
                if self._postprocess:
                    result_path = await self._run_postprocess(result_path, width, height)
                return result_path
            except Exception as e:
                last_error = e
                logger.warning("Image gen via %s failed: %s", provider.name, e)

        raise RuntimeError(f"All image providers failed. Last error: {last_error}")

    async def transform(
        self,
        source_image_path: str,
        prompt: str,
        output_path: str,
        strength: float = 0.7,
    ) -> str:
        """Image-to-image with auto-fallback (only tries providers that support it).

        Post-processes the result for UGC authenticity.
        Returns path to the final image.
        """
        if not self._providers:
            raise RuntimeError("No image providers registered")

        last_error = None
        for name in self._order:
            provider = self._providers[name]
            if not provider.is_connected or provider.is_rate_limited:
                continue
            if not provider.supports_img2img:
                continue
            try:
                logger.info("Transforming image via %s...", provider.name)
                result_path = await provider.image_to_image(
                    source_image_path, prompt, output_path, strength
                )
                logger.info("Image transformed via %s: %s", provider.name, result_path)
                if self._postprocess:
                    result_path = await self._run_postprocess(result_path)
                return result_path
            except NotImplementedError:
                continue
            except Exception as e:
                last_error = e
                logger.warning("Image transform via %s failed: %s", provider.name, e)

        # No img2img providers worked — fall back to txt2img from the prompt
        logger.warning("All img2img providers failed, falling back to txt2img")
        return await self.generate(prompt, output_path)

    async def _run_postprocess(self, image_path: str,
                                width: int | None = None,
                                height: int | None = None) -> str:
        """Apply UGC post-processing pipeline."""
        try:
            from ai.image_postprocess import postprocess_for_ugc
            return postprocess_for_ugc(image_path, width=width, height=height)
        except Exception as e:
            logger.warning("Post-processing failed (keeping original): %s", e)
            return image_path


def create_default_image_manager() -> ImageManager:
    """Create an ImageManager with providers initialized from env vars."""
    from pathlib import Path
    from dotenv import load_dotenv

    root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(root / "config" / ".env")

    manager = ImageManager()

    # 1. Gemini Flash Image (primary — 500/day free, best quality, supports img2img)
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key:
        try:
            from ai.image_providers.gemini_image import GeminiImageProvider
            manager.register(GeminiImageProvider(gemini_key))
        except Exception as e:
            logger.warning("Failed to init Gemini image provider: %s", e)

    # 2. Cloudflare Workers AI (secondary — 20-50/day free)
    cf_account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    cf_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if cf_account and cf_token:
        try:
            from ai.image_providers.cloudflare_image import CloudflareImageProvider
            manager.register(CloudflareImageProvider(cf_account, cf_token))
        except Exception as e:
            logger.warning("Failed to init Cloudflare image provider: %s", e)

    # 3. Together AI (if credit available)
    together_key = os.getenv("TOGETHER_API_KEY", "").strip()
    if together_key:
        try:
            from ai.image_providers.together_image import TogetherImageProvider
            manager.register(TogetherImageProvider(together_key))
        except Exception as e:
            logger.warning("Failed to init Together image provider: %s", e)

    # 4. Pollinations (tertiary — free, no signup)
    try:
        from ai.image_providers.pollinations_image import PollinationsImageProvider
        manager.register(PollinationsImageProvider())
    except Exception as e:
        logger.warning("Failed to init Pollinations image provider: %s", e)

    # 5. PIL fallback (last resort — always available)
    try:
        from ai.image_providers.pil_fallback import PilFallbackProvider
        manager.register(PilFallbackProvider())
    except Exception as e:
        logger.warning("Failed to init PIL fallback: %s", e)

    return manager
