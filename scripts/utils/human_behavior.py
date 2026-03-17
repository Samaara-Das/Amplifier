"""Human behavior emulation for browser automation anti-detection."""

import asyncio
import json
import logging
import os
import random
from datetime import date
from pathlib import Path

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

    engaged = False
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

            # Auto-engage once during the browsing session (midway through)
            if not engaged and asyncio.get_event_loop().time() > (end_time - duration / 2):
                await auto_engage(page, platform)
                engaged = True

    except Exception as e:
        logger.warning("Browse feed error (non-fatal): %s", e)


ROOT = Path(__file__).resolve().parent.parent.parent
ENGAGEMENT_TRACKER_PATH = ROOT / "logs" / "engagement-tracker.json"

# Daily engagement caps per platform (from .env)
ENGAGEMENT_CAPS = {
    "x": {
        "likes": int(os.getenv("MAX_LIKES_X", "15")),
        "retweets": int(os.getenv("MAX_RETWEETS_X", "3")),
    },
    "linkedin": {
        "likes": int(os.getenv("MAX_LIKES_LINKEDIN", "8")),
        "reposts": int(os.getenv("MAX_REPOSTS_LINKEDIN", "2")),
    },
    "facebook": {
        "likes": int(os.getenv("MAX_LIKES_FACEBOOK", "8")),
        "shares": int(os.getenv("MAX_SHARES_FACEBOOK", "2")),
    },
    "instagram": {
        "likes": int(os.getenv("MAX_LIKES_INSTAGRAM", "15")),
    },
    "reddit": {
        "upvotes": int(os.getenv("MAX_UPVOTES_REDDIT", "15")),
    },
    "tiktok": {
        "likes": int(os.getenv("MAX_LIKES_TIKTOK", "8")),
    },
}

# Blocklist — skip posts containing these keywords (case-insensitive)
ENGAGEMENT_BLOCKLIST = [
    "politics", "political", "election", "democrat", "republican", "trump", "biden",
    "abortion", "gun control", "vaccine", "conspiracy", "extremist", "terrorism",
    "hate speech", "racist", "sexist", "nsfw", "porn", "suicide", "self-harm",
]


def _load_engagement_tracker() -> dict:
    """Load today's engagement counts. Resets daily."""
    today = date.today().isoformat()
    try:
        if ENGAGEMENT_TRACKER_PATH.exists():
            data = json.loads(ENGAGEMENT_TRACKER_PATH.read_text(encoding="utf-8"))
            if data.get("date") == today:
                return data
    except Exception:
        pass
    return {"date": today}


def _save_engagement_tracker(tracker: dict) -> None:
    """Persist engagement tracker to disk."""
    try:
        ENGAGEMENT_TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
        ENGAGEMENT_TRACKER_PATH.write_text(
            json.dumps(tracker, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.warning("Could not save engagement tracker: %s", e)


def _get_remaining(tracker: dict, platform: str, action: str) -> int:
    """How many more actions of this type we can do today for this platform."""
    cap = ENGAGEMENT_CAPS.get(platform, {}).get(action, 0)
    if cap == 0:
        return 0
    done = tracker.get(f"{platform}_{action}", 0)
    return max(0, cap - done)


def _record_action(tracker: dict, platform: str, action: str, count: int = 1) -> None:
    """Record that we performed N engagement actions."""
    key = f"{platform}_{action}"
    tracker[key] = tracker.get(key, 0) + count


async def _contains_blocked_content(element) -> bool:
    """Check if an element's text contains blocklisted keywords."""
    try:
        text = (await element.inner_text()).lower()
        return any(word in text for word in ENGAGEMENT_BLOCKLIST)
    except Exception:
        return False


async def auto_engage(page, platform: str) -> None:
    """Like/react to and optionally repost other people's content on the platform.

    Called during browse_feed phases. Respects daily caps and blocklist.
    """
    tracker = _load_engagement_tracker()

    try:
        if platform == "x":
            await _engage_x(page, tracker)
        elif platform == "linkedin":
            await _engage_linkedin(page, tracker)
        elif platform == "facebook":
            await _engage_facebook(page, tracker)
        elif platform == "instagram":
            await _engage_instagram(page, tracker)
        elif platform == "reddit":
            await _engage_reddit(page, tracker)
        elif platform == "tiktok":
            await _engage_tiktok(page, tracker)
    except Exception as e:
        logger.warning("Auto-engage error on %s (non-fatal): %s", platform, e)

    _save_engagement_tracker(tracker)


async def _engage_x(page, tracker: dict) -> None:
    """Like tweets and retweet on X."""
    likes_left = _get_remaining(tracker, "x", "likes")
    retweets_left = _get_remaining(tracker, "x", "retweets")
    if likes_left == 0 and retweets_left == 0:
        logger.info("X: daily engagement cap reached, skipping")
        return

    target_likes = random.randint(5, min(10, likes_left)) if likes_left > 0 else 0
    target_retweets = random.randint(1, min(2, retweets_left)) if retweets_left > 0 else 0

    liked = 0
    retweeted = 0
    # Scroll and engage
    for _ in range(15):
        await human_scroll(page, "down")
        await human_delay(1, 3)

        if liked < target_likes:
            try:
                like_buttons = page.locator('[data-testid="like"]')
                count = await like_buttons.count()
                for i in range(min(count, 3)):
                    btn = like_buttons.nth(i)
                    if not await btn.is_visible():
                        continue
                    # Check parent article for blocklist
                    article = page.locator(f'article:has([data-testid="like"]:nth-match({i+1}))')
                    if await _contains_blocked_content(article):
                        continue
                    await btn.dispatch_event("click")
                    liked += 1
                    _record_action(tracker, "x", "likes")
                    logger.info("X: liked tweet (%d/%d)", liked, target_likes)
                    await human_delay(2, 5)
                    if liked >= target_likes:
                        break
            except Exception:
                pass

        if retweeted < target_retweets and random.random() < 0.3:
            try:
                rt_buttons = page.locator('[data-testid="retweet"]')
                count = await rt_buttons.count()
                if count > 0:
                    btn = rt_buttons.nth(0)
                    if await btn.is_visible():
                        await btn.dispatch_event("click")
                        await human_delay(1, 2)
                        # Click "Repost" in the popup menu
                        repost_option = page.locator('[data-testid="retweetConfirm"]')
                        try:
                            await repost_option.wait_for(timeout=3000)
                            await repost_option.click()
                            retweeted += 1
                            _record_action(tracker, "x", "retweets")
                            logger.info("X: retweeted (%d/%d)", retweeted, target_retweets)
                            await human_delay(3, 6)
                        except Exception:
                            pass
            except Exception:
                pass

        if liked >= target_likes and retweeted >= target_retweets:
            break

    logger.info("X: engagement done — %d likes, %d retweets", liked, retweeted)


async def _engage_linkedin(page, tracker: dict) -> None:
    """Like posts and repost on LinkedIn."""
    likes_left = _get_remaining(tracker, "linkedin", "likes")
    reposts_left = _get_remaining(tracker, "linkedin", "reposts")
    if likes_left == 0 and reposts_left == 0:
        logger.info("LinkedIn: daily engagement cap reached, skipping")
        return

    target_likes = random.randint(3, min(5, likes_left)) if likes_left > 0 else 0
    target_reposts = random.randint(0, min(1, reposts_left)) if reposts_left > 0 else 0

    liked = 0
    reposted = 0
    for _ in range(12):
        await human_scroll(page, "down")
        await human_delay(1, 3)

        if liked < target_likes:
            try:
                # LinkedIn like button — the reaction button (first one is Like)
                like_buttons = page.locator('button[aria-label*="Like"]:not([aria-pressed="true"])')
                count = await like_buttons.count()
                for i in range(min(count, 2)):
                    btn = like_buttons.nth(i)
                    if not await btn.is_visible():
                        continue
                    await btn.click()
                    liked += 1
                    _record_action(tracker, "linkedin", "likes")
                    logger.info("LinkedIn: liked post (%d/%d)", liked, target_likes)
                    await human_delay(2, 5)
                    if liked >= target_likes:
                        break
            except Exception:
                pass

        if reposted < target_reposts and random.random() < 0.2:
            try:
                repost_buttons = page.locator('button[aria-label*="Repost"]')
                count = await repost_buttons.count()
                if count > 0:
                    btn = repost_buttons.nth(0)
                    if await btn.is_visible():
                        await btn.click()
                        await human_delay(1, 2)
                        # Click "Repost" in the dropdown (instant repost, no quote)
                        instant = page.locator('button:has-text("Repost"), span:has-text("Repost")').first
                        try:
                            await instant.wait_for(timeout=3000)
                            await instant.click()
                            reposted += 1
                            _record_action(tracker, "linkedin", "reposts")
                            logger.info("LinkedIn: reposted (%d/%d)", reposted, target_reposts)
                            await human_delay(3, 6)
                        except Exception:
                            pass
            except Exception:
                pass

        if liked >= target_likes and reposted >= target_reposts:
            break

    logger.info("LinkedIn: engagement done — %d likes, %d reposts", liked, reposted)


async def _engage_facebook(page, tracker: dict) -> None:
    """React to posts and share on Facebook."""
    likes_left = _get_remaining(tracker, "facebook", "likes")
    shares_left = _get_remaining(tracker, "facebook", "shares")
    if likes_left == 0 and shares_left == 0:
        logger.info("Facebook: daily engagement cap reached, skipping")
        return

    target_likes = random.randint(3, min(5, likes_left)) if likes_left > 0 else 0
    target_shares = random.randint(0, min(1, shares_left)) if shares_left > 0 else 0

    liked = 0
    shared = 0
    for _ in range(12):
        await human_scroll(page, "down")
        await human_delay(1, 3)

        if liked < target_likes:
            try:
                like_buttons = page.locator('[aria-label="Like"]')
                count = await like_buttons.count()
                for i in range(min(count, 2)):
                    btn = like_buttons.nth(i)
                    if not await btn.is_visible():
                        continue
                    await btn.click()
                    liked += 1
                    _record_action(tracker, "facebook", "likes")
                    logger.info("Facebook: liked post (%d/%d)", liked, target_likes)
                    await human_delay(2, 5)
                    if liked >= target_likes:
                        break
            except Exception:
                pass

        if shared < target_shares and random.random() < 0.15:
            try:
                share_buttons = page.locator('[aria-label="Send this to friends or post it on your timeline."], [aria-label="Share"]')
                count = await share_buttons.count()
                if count > 0:
                    btn = share_buttons.nth(0)
                    if await btn.is_visible():
                        await btn.click()
                        await human_delay(1, 2)
                        # Click "Share now" in the popup
                        share_now = page.locator('span:has-text("Share now"), [role="menuitem"]:has-text("Share now")').first
                        try:
                            await share_now.wait_for(timeout=3000)
                            await share_now.click()
                            shared += 1
                            _record_action(tracker, "facebook", "shares")
                            logger.info("Facebook: shared post (%d/%d)", shared, target_shares)
                            await human_delay(3, 6)
                        except Exception:
                            pass
            except Exception:
                pass

        if liked >= target_likes and shared >= target_shares:
            break

    logger.info("Facebook: engagement done — %d likes, %d shares", liked, shared)


async def _engage_instagram(page, tracker: dict) -> None:
    """Like posts on Instagram."""
    likes_left = _get_remaining(tracker, "instagram", "likes")
    if likes_left == 0:
        logger.info("Instagram: daily engagement cap reached, skipping")
        return

    target_likes = random.randint(5, min(10, likes_left))
    liked = 0
    for _ in range(15):
        await human_scroll(page, "down")
        await human_delay(1, 3)

        if liked < target_likes:
            try:
                # Instagram heart/like buttons in the feed
                like_buttons = page.locator('svg[aria-label="Like"]')
                count = await like_buttons.count()
                for i in range(min(count, 2)):
                    btn = like_buttons.nth(i)
                    if not await btn.is_visible():
                        continue
                    await btn.click()
                    liked += 1
                    _record_action(tracker, "instagram", "likes")
                    logger.info("Instagram: liked post (%d/%d)", liked, target_likes)
                    await human_delay(2, 5)
                    if liked >= target_likes:
                        break
            except Exception:
                pass

        if liked >= target_likes:
            break

    logger.info("Instagram: engagement done — %d likes", liked)


async def _engage_reddit(page, tracker: dict) -> None:
    """Upvote posts on Reddit."""
    upvotes_left = _get_remaining(tracker, "reddit", "upvotes")
    if upvotes_left == 0:
        logger.info("Reddit: daily engagement cap reached, skipping")
        return

    target_upvotes = random.randint(5, min(10, upvotes_left))
    upvoted = 0
    for _ in range(15):
        await human_scroll(page, "down")
        await human_delay(1, 3)

        if upvoted < target_upvotes:
            try:
                # Reddit upvote button — faceplate-tracker shadow DOM, Playwright pierces
                upvote_buttons = page.locator('button[aria-label="Upvote"], button[upvote]')
                count = await upvote_buttons.count()
                for i in range(min(count, 3)):
                    btn = upvote_buttons.nth(i)
                    if not await btn.is_visible():
                        continue
                    # Check if already upvoted (aria-pressed="true")
                    pressed = await btn.get_attribute("aria-pressed")
                    if pressed == "true":
                        continue
                    await btn.click()
                    upvoted += 1
                    _record_action(tracker, "reddit", "upvotes")
                    logger.info("Reddit: upvoted post (%d/%d)", upvoted, target_upvotes)
                    await human_delay(2, 5)
                    if upvoted >= target_upvotes:
                        break
            except Exception:
                pass

        if upvoted >= target_upvotes:
            break

    logger.info("Reddit: engagement done — %d upvotes", upvoted)


async def _engage_tiktok(page, tracker: dict) -> None:
    """Like videos on TikTok."""
    likes_left = _get_remaining(tracker, "tiktok", "likes")
    if likes_left == 0:
        logger.info("TikTok: daily engagement cap reached, skipping")
        return

    target_likes = random.randint(3, min(5, likes_left))
    liked = 0
    for _ in range(10):
        await human_scroll(page, "down")
        await human_delay(1, 3)

        if liked < target_likes:
            try:
                # TikTok like button — heart icon on the side of videos
                like_buttons = page.locator('[data-e2e="like-icon"], span[data-e2e="undefined-count"]')
                count = await like_buttons.count()
                for i in range(min(count, 2)):
                    btn = like_buttons.nth(i)
                    if not await btn.is_visible():
                        continue
                    await btn.click()
                    liked += 1
                    _record_action(tracker, "tiktok", "likes")
                    logger.info("TikTok: liked video (%d/%d)", liked, target_likes)
                    await human_delay(2, 5)
                    if liked >= target_likes:
                        break
            except Exception:
                pass

        if liked >= target_likes:
            break

    logger.info("TikTok: engagement done — %d likes", liked)


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
