"""Human behavior emulation for browser automation anti-detection."""

import asyncio
import logging
import os
import random

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load config
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "config", ".env"))

BROWSE_MIN = int(os.getenv("BROWSE_MIN_DURATION_SEC", "60"))
BROWSE_MAX = int(os.getenv("BROWSE_MAX_DURATION_SEC", "300"))
POSTS_MIN = int(os.getenv("BROWSE_POSTS_TO_VIEW_MIN", "2"))
POSTS_MAX = int(os.getenv("BROWSE_POSTS_TO_VIEW_MAX", "4"))
PROFILES_MIN = int(os.getenv("BROWSE_PROFILES_TO_CLICK_MIN", "1"))
PROFILES_MAX = int(os.getenv("BROWSE_PROFILES_TO_CLICK_MAX", "2"))


async def human_delay(min_sec: float, max_sec: float) -> None:
    """Sleep for a random duration in the given range."""
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)


async def human_type(page, selector: str, text: str) -> None:
    """Type text character-by-character with human-like timing."""
    element = page.locator(selector).first
    await element.click()
    for char in text:
        await element.press_sequentially(char, delay=0)
        delay_ms = random.uniform(30, 120)
        if random.random() < 0.05:
            delay_ms = random.uniform(300, 800)
        await asyncio.sleep(delay_ms / 1000)


async def human_scroll(page, direction: str = "down", amount: int = 0) -> None:
    """Scroll a random 200-500px in the given direction."""
    pixels = amount if amount else random.randint(200, 500)
    delta = pixels if direction == "down" else -pixels
    await page.mouse.wheel(0, delta)
    await human_delay(0.5, 1.5)


async def random_mouse_movement(page) -> None:
    """Move mouse to a random viewport position in 5-15 intermediate steps."""
    try:
        viewport = page.viewport_size
        if not viewport:
            return
        target_x = random.randint(100, viewport["width"] - 100)
        target_y = random.randint(100, viewport["height"] - 100)
        steps = random.randint(5, 15)
        await page.mouse.move(target_x, target_y, steps=steps)
    except Exception:
        pass


async def browse_feed(page, platform: str) -> None:
    """Spend 1-5 minutes doing realistic browsing on the platform."""
    duration = random.uniform(BROWSE_MIN, BROWSE_MAX)
    logger.info("Browsing %s feed for %.0f seconds", platform, duration)

    end_time = asyncio.get_event_loop().time() + duration
    posts_viewed = 0
    profiles_clicked = 0
    max_posts = random.randint(POSTS_MIN, POSTS_MAX)
    max_profiles = random.randint(PROFILES_MIN, PROFILES_MAX)

    try:
        while asyncio.get_event_loop().time() < end_time:
            # Scroll the feed
            await human_scroll(page, "down")
            await human_delay(1, 3)

            # Random mouse movement
            if random.random() < 0.3:
                await random_mouse_movement(page)

            # Stop and "read" a post
            if posts_viewed < max_posts and random.random() < 0.4:
                read_time = random.uniform(3, 10)
                logger.debug("Reading a post for %.1f seconds", read_time)
                await asyncio.sleep(read_time)
                posts_viewed += 1

            # Click a user profile
            if profiles_clicked < max_profiles and random.random() < 0.15:
                try:
                    links = await _find_profile_links(page, platform)
                    if links:
                        link = random.choice(links)
                        await link.click()
                        await human_delay(5, 15)
                        await human_scroll(page, "down")
                        await human_delay(2, 5)
                        await page.go_back()
                        await human_delay(2, 4)
                        profiles_clicked += 1
                        logger.debug("Visited a profile and returned to feed")
                except Exception:
                    pass

            # Hover over random elements
            if random.random() < 0.2:
                await random_mouse_movement(page)
                await human_delay(0.3, 1.0)

    except Exception as e:
        logger.warning("Browse feed error (non-fatal): %s", e)


async def _find_profile_links(page, platform: str):
    """Find clickable profile links on the feed. Returns a list of locators."""
    selectors = {
        "x": 'a[role="link"][href*="/"]',
        "linkedin": 'a.app-aware-link[href*="/in/"]',
        "facebook": 'a[role="link"][href*="/profile"]',
        "instagram": 'a[href*="/"]',
        "reddit": 'a[href*="/user/"]',
        "tiktok": 'a[href*="/@"]',
    }
    selector = selectors.get(platform, "a")
    try:
        links = page.locator(selector)
        count = await links.count()
        if count == 0:
            return []
        # Pick from first 10 visible links
        result = []
        for i in range(min(count, 10)):
            loc = links.nth(i)
            if await loc.is_visible():
                result.append(loc)
        return result
    except Exception:
        return []
