"""Abstract AI provider interface.

Inspired by AmpliFire v3's AiProvider.kt. Every text generation provider
implements this interface so the AiManager can swap them transparently.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AiProvider(ABC):
    """Base class for text generation providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this provider (e.g. 'gemini', 'mistral')."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True if this provider is initialized and has valid credentials."""
        ...

    @property
    def is_rate_limited(self) -> bool:
        """True if this provider is currently rate-limited. Override to track."""
        return False

    @abstractmethod
    async def generate_text(self, prompt: str) -> str:
        """Generate text from a prompt. Returns raw text response.

        Raises on failure (network, auth, rate limit, etc.).
        """
        ...
