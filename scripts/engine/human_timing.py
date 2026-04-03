"""Human-like timing engine with per-step configuration.

Inspired by AmpliFire v3's HumanLikeTiming.kt. Each script step defines its own
delay ranges and typing speeds — different actions simulate different human behaviors.

Replaces the flat human_delay/human_type helpers in post.py.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from engine.script_parser import DelayRange

if TYPE_CHECKING:
    from playwright.async_api import Page


async def random_delay(delay_range: DelayRange | None) -> None:
    """Sleep for a random duration within the given range (milliseconds)."""
    if delay_range is None or delay_range.max <= 0:
        return
    ms = random.randint(delay_range.min, delay_range.max)
    await asyncio.sleep(ms / 1000)


async def type_text(
    page: Page,
    text: str,
    typing_speed: DelayRange | None = None,
) -> None:
    """Type text character-by-character with human-like timing.

    Uses page.keyboard.type() which fires proper keydown/keypress/keyup events.
    The per-character delay is randomized within the typing_speed range.
    """
    if not text:
        return

    if typing_speed is None:
        typing_speed = DelayRange(min=30, max=100)

    # Playwright's keyboard.type() accepts a delay param but it's fixed.
    # For truly random per-character delays, we type one char at a time.
    for char in text:
        await page.keyboard.type(char, delay=0)
        delay_ms = random.randint(typing_speed.min, typing_speed.max)
        await asyncio.sleep(delay_ms / 1000)


async def type_text_in_locator(
    page: Page,
    locator,
    text: str,
    typing_speed: DelayRange | None = None,
    clear_first: bool = False,
) -> None:
    """Click a locator to focus it, optionally clear, then type text with human timing."""
    await locator.click(force=True)
    await asyncio.sleep(random.uniform(0.2, 0.5))

    if clear_first:
        await page.keyboard.press("Control+a")
        await asyncio.sleep(0.1)
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.2)

    await type_text(page, text, typing_speed)


async def browse_feed(page: Page, duration_ms: int | None = None) -> None:
    """Simulate brief feed browsing — wait and optionally scroll."""
    if duration_ms is None:
        duration_ms = random.randint(1000, 3000)
    await asyncio.sleep(duration_ms / 1000)
