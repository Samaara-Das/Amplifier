"""Abstract image provider interface.

Same pattern as ai/provider.py for text — pluggable providers with a uniform
interface so ImageManager can swap them transparently.

Two capabilities:
- text_to_image: prompt → generated image
- image_to_image: source image + prompt → transformed image (not all providers support this)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ImageProvider(ABC):
    """Base class for image generation providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier (e.g. 'gemini_image', 'cloudflare')."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True if this provider has valid credentials and is ready."""
        ...

    @property
    def is_rate_limited(self) -> bool:
        """True if currently rate-limited. Override to track."""
        return False

    @property
    def supports_img2img(self) -> bool:
        """True if this provider supports image-to-image transformation."""
        return False

    @abstractmethod
    async def text_to_image(
        self,
        prompt: str,
        output_path: str,
        width: int = 1080,
        height: int = 1080,
        negative_prompt: str | None = None,
    ) -> str:
        """Generate image from text prompt.

        Args:
            prompt: Text description of the image to generate.
            output_path: Where to save the generated image.
            width: Target width in pixels.
            height: Target height in pixels.
            negative_prompt: What to avoid in the image (if provider supports it).

        Returns: Path to the saved image file.
        Raises: On generation failure.
        """
        ...

    async def image_to_image(
        self,
        source_image_path: str,
        prompt: str,
        output_path: str,
        strength: float = 0.7,
    ) -> str:
        """Transform a source image guided by a text prompt.

        Args:
            source_image_path: Path to the input image (e.g. product photo).
            prompt: Text describing the desired transformation.
            output_path: Where to save the result.
            strength: How much to transform (0.0 = identical, 1.0 = completely new).

        Returns: Path to the saved image file.
        Raises: NotImplementedError if provider doesn't support img2img.
        """
        raise NotImplementedError(f"{self.name} does not support image-to-image")
