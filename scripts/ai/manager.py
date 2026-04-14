"""AI provider manager with registry and auto-fallback.

Inspired by AmpliFire v3's AiManager.kt. Providers are registered at startup.
The manager picks the best available one (connected + not rate-limited) and
falls back to the next if one fails.

Usage:
    manager = AiManager()
    manager.register(GeminiProvider(key))
    manager.register(MistralProvider(key))

    result = await manager.generate("Write a tweet about ...")
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from ai.provider import AiProvider

logger = logging.getLogger(__name__)


class AiManager:
    """Registry of AI providers with auto-fallback on failure."""

    def __init__(self):
        self._providers: dict[str, AiProvider] = {}
        self._order: list[str] = []  # insertion order = priority

    def register(self, provider: AiProvider) -> None:
        """Register a provider. First registered = highest priority."""
        self._providers[provider.name] = provider
        if provider.name not in self._order:
            self._order.append(provider.name)
        logger.info("Registered AI provider: %s", provider.name)

    def get(self, name: str) -> Optional[AiProvider]:
        return self._providers.get(name)

    def get_default(self) -> Optional[AiProvider]:
        """Return the highest-priority provider that is connected and not rate-limited."""
        for name in self._order:
            p = self._providers[name]
            if p.is_connected and not p.is_rate_limited:
                return p
        # Fallback: any connected provider (even if rate-limited)
        for name in self._order:
            p = self._providers[name]
            if p.is_connected:
                return p
        return None

    @property
    def provider_names(self) -> list[str]:
        return list(self._order)

    @property
    def has_providers(self) -> bool:
        return bool(self._providers)

    async def generate(self, prompt: str, preferred: str | None = None) -> str:
        """Generate text using the best available provider.

        Tries preferred provider first (if specified), then falls back through
        all registered providers in order. Raises RuntimeError if all fail.
        """
        if not self._providers:
            raise RuntimeError("No AI providers registered. Set API keys in config/.env")

        providers_to_try = []
        if preferred and preferred in self._providers:
            providers_to_try.append(self._providers[preferred])
        for name in self._order:
            p = self._providers[name]
            if p not in providers_to_try:
                providers_to_try.append(p)

        last_error = None
        for provider in providers_to_try:
            if not provider.is_connected:
                continue
            try:
                logger.info("Generating via %s...", provider.name)
                result = await provider.generate_text(prompt)
                logger.info("Generated via %s (%d chars)", provider.name, len(result))
                return result
            except Exception as e:
                last_error = e
                logger.warning("%s failed: %s. Trying next provider...", provider.name, e)

        raise RuntimeError(f"All AI providers failed. Last error: {last_error}")


def create_default_manager() -> AiManager:
    """Create an AiManager with providers initialized from environment variables.

    Reads GEMINI_API_KEY, MISTRAL_API_KEY, GROQ_API_KEY from config/.env.
    """
    from pathlib import Path
    from dotenv import load_dotenv

    root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(root / "config" / ".env")

    manager = AiManager()

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key:
        try:
            from ai.gemini_provider import GeminiProvider
            manager.register(GeminiProvider(gemini_key))
        except Exception as e:
            logger.warning("Failed to init Gemini: %s", e)

    mistral_key = os.getenv("MISTRAL_API_KEY", "").strip()
    if mistral_key:
        try:
            from ai.mistral_provider import MistralProvider
            manager.register(MistralProvider(mistral_key))
        except Exception as e:
            logger.warning("Failed to init Mistral: %s", e)

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            from ai.groq_provider import GroqProvider
            manager.register(GroqProvider(groq_key))
        except Exception as e:
            logger.warning("Failed to init Groq: %s", e)

    if not manager.has_providers:
        logger.error("No AI providers available. Set GEMINI_API_KEY in config/.env")

    return manager


def create_manager_from_settings() -> AiManager:
    """Create an AiManager with providers from local_db settings.

    Used by user app components (profile scraper, etc.) where API keys
    are stored encrypted in local SQLite, not in config/.env.
    Falls back to create_default_manager() if no keys found in local_db.
    """
    from utils.local_db import get_setting

    manager = AiManager()

    gemini_key = get_setting("gemini_api_key") or ""
    if gemini_key.strip():
        try:
            from ai.gemini_provider import GeminiProvider
            manager.register(GeminiProvider(gemini_key.strip()))
        except Exception as e:
            logger.warning("Failed to init Gemini from settings: %s", e)

    mistral_key = get_setting("mistral_api_key") or ""
    if mistral_key.strip():
        try:
            from ai.mistral_provider import MistralProvider
            manager.register(MistralProvider(mistral_key.strip()))
        except Exception as e:
            logger.warning("Failed to init Mistral from settings: %s", e)

    groq_key = get_setting("groq_api_key") or ""
    if groq_key.strip():
        try:
            from ai.groq_provider import GroqProvider
            manager.register(GroqProvider(groq_key.strip()))
        except Exception as e:
            logger.warning("Failed to init Groq from settings: %s", e)

    # Fall back to env-based manager if local_db has no keys
    if not manager.has_providers:
        logger.info("No AI keys in local_db, falling back to config/.env")
        return create_default_manager()

    return manager
