"""Main poster orchestrator — picks up drafts and posts to enabled platforms."""

import argparse
import asyncio
from datetime import datetime
import json
import logging
import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

load_dotenv(ROOT / "config" / ".env")
os.environ.setdefault("AUTO_POSTER_ROOT", str(ROOT))

from utils.draft_manager import get_next_draft, mark_failed, mark_posted
from utils.human_behavior import browse_feed, human_delay, human_type

# Logging setup
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "poster.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Config
POST_INTERVAL_MIN = int(os.getenv("POST_INTERVAL_MIN_SEC", "30"))
POST_INTERVAL_MAX = int(os.getenv("POST_INTERVAL_MAX_SEC", "90"))
PAGE_LOAD_TIMEOUT = int(os.getenv("PAGE_LOAD_TIMEOUT_SEC", "30")) * 1000
COMPOSE_TIMEOUT = int(os.getenv("COMPOSE_FIND_TIMEOUT_SEC", "15")) * 1000

# Load platform config
with open(ROOT / "config" / "platforms.json", "r", encoding="utf-8") as f:
    PLATFORMS = json.load(f)


async def _launch_context(pw, platform: str):
    """Launch a persistent browser context for the given platform.

    If the platform has a "proxy" key in platforms.json, it will be used.
    Example: "proxy": "socks5://127.0.0.1:1080" (local VPN/SOCKS proxy)
    """
    profile_dir = ROOT / "profiles" / f"{platform}-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    headless = os.getenv("HEADLESS", "false").lower() == "true"

    kwargs = dict(
        user_data_dir=str(profile_dir),
        headless=headless,
        viewport={"width": 1280, "height": 800},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )

    # Per-platform proxy support (for geo-restricted platforms like TikTok in India)
    proxy_url = PLATFORMS.get(platform, {}).get("proxy")
    if proxy_url:
        logger.info("Using proxy for %s: %s", platform, proxy_url)
        kwargs["proxy"] = {"server": proxy_url}

    context = await pw.chromium.launch_persistent_context(**kwargs)
    return context


# ─── Helpers ────────────────────────────────────────────────────────────────


def _extract_content(draft_content: dict, platform: str) -> tuple[str, str | None]:
    """Extract text and optional image_text from draft content for a platform.

    Returns (text, image_text) where image_text is None for text-only posts.
    """
    content = draft_content.get(platform, "")
    if isinstance(content, str):
        return content, None
    elif isinstance(content, dict):
        text = content.get("text") or content.get("caption", "")
        image_text = content.get("image_text")
        return text, image_text
    return str(content), None


# ─── X (Twitter) ────────────────────────────────────────────────────────────

X_COMPOSE_URL = "https://x.com/compose/post"
X_TEXTBOX = '[role="textbox"]'
X_POST_BUTTON = '[data-testid="tweetButton"]'


async def post_to_x(draft: dict, pw) -> bool:
    """Post content to X (Twitter). Supports text-only and text+image."""
    context = None
    image_path = None
    try:
        text, image_text = _extract_content(draft["content"], "x")

        # Generate image if needed
        if image_text:
            from utils.image_generator import generate_landscape_image
            image_path = ROOT / "drafts" / "pending" / f"x-{draft.get('id', 'temp')}.png"
            generate_landscape_image(image_text, image_path)
            logger.info("X: generated branded image at %s", image_path)

        context = await _launch_context(pw, "x")
        page = context.pages[0] if context.pages else await context.new_page()

        # Pre-post browsing
        await page.goto(PLATFORMS["x"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded")
        await browse_feed(page, "x")

        # Navigate to compose
        await page.goto(X_COMPOSE_URL, timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_selector(X_TEXTBOX, timeout=COMPOSE_TIMEOUT)
        await human_delay(1, 2)

        # Upload image if available
        if image_path and image_path.exists():
            try:
                file_input_selectors = [
                    'input[data-testid="fileInput"]',
                    'input[type="file"][accept*="image"]',
                    'input[type="file"]',
                ]
                uploaded = False
                for sel in file_input_selectors:
                    try:
                        fi = page.locator(sel).first
                        if await fi.count() > 0:
                            await fi.set_input_files(str(image_path))
                            logger.info("X: uploaded image via %s", sel)
                            uploaded = True
                            break
                    except Exception:
                        continue
                if uploaded:
                    # Wait for image preview to appear
                    try:
                        await page.locator('[data-testid="attachments"]').wait_for(timeout=15000)
                    except Exception:
                        pass
                    await human_delay(2, 4)
                else:
                    logger.warning("X: could not find file input, posting text-only")
            except Exception as e:
                logger.warning("X: image upload failed, posting text-only: %s", e)

        # Type content
        await human_type(page, X_TEXTBOX, text)
        await human_delay(1, 3)

        # Click post — use JS click to bypass overlay div that intercepts pointer events
        post_btn = page.locator(X_POST_BUTTON)
        await post_btn.wait_for(timeout=COMPOSE_TIMEOUT)
        await post_btn.dispatch_event("click")
        await human_delay(3, 5)

        # Post-post browsing
        await page.goto(PLATFORMS["x"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await browse_feed(page, "x")

        logger.info("Successfully posted to X")
        return True

    except Exception as e:
        logger.error("Failed to post to X: %s", e, exc_info=True)
        return False
    finally:
        if image_path:
            try:
                image_path.unlink(missing_ok=True)
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass


# ─── LinkedIn ───────────────────────────────────────────────────────────────

# LinkedIn uses shadow DOM — must use Playwright locators (pierce shadow) not wait_for_selector
LI_COMPOSE_TRIGGER = '[role="button"]:has-text("Start a post")'
LI_TEXTBOX = '[role="textbox"]'


async def post_to_linkedin(draft: dict, pw) -> bool:
    """Post content to LinkedIn. Supports text-only and text+image."""
    context = None
    image_path = None
    try:
        text, image_text = _extract_content(draft["content"], "linkedin")

        # Generate image if needed
        if image_text:
            from utils.image_generator import generate_landscape_image
            image_path = ROOT / "drafts" / "pending" / f"linkedin-{draft.get('id', 'temp')}.png"
            generate_landscape_image(image_text, image_path)
            logger.info("LinkedIn: generated branded image at %s", image_path)

        context = await _launch_context(pw, "linkedin")
        page = context.pages[0] if context.pages else await context.new_page()

        # Pre-post browsing
        await page.goto(PLATFORMS["linkedin"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded")
        await browse_feed(page, "linkedin")

        # Open compose modal
        compose_btn = page.locator(LI_COMPOSE_TRIGGER).first
        await compose_btn.wait_for(timeout=COMPOSE_TIMEOUT)
        await compose_btn.click()
        logger.info("LinkedIn: clicked compose trigger")
        await human_delay(3, 5)

        # Upload image BEFORE typing text (if available)
        if image_path and image_path.exists():
            try:
                uploaded = False
                # Strategy 1: hidden file input
                try:
                    fi = page.locator('input[type="file"]').first
                    if await fi.count() > 0:
                        await fi.set_input_files(str(image_path))
                        uploaded = True
                        logger.info("LinkedIn: uploaded image via file input")
                except Exception:
                    pass
                # Strategy 2: click media button → file chooser
                if not uploaded:
                    media_selectors = [
                        'button[aria-label="Add a photo"]',
                        'button[aria-label="Add media"]',
                        'button:has(li-icon[type="image"])',
                    ]
                    for sel in media_selectors:
                        try:
                            btn = page.locator(sel).first
                            if await btn.is_visible(timeout=3000):
                                async with page.expect_file_chooser(timeout=5000) as fc_info:
                                    await btn.click()
                                fc = await fc_info.value
                                await fc.set_files(str(image_path))
                                uploaded = True
                                logger.info("LinkedIn: uploaded image via file chooser (%s)", sel)
                                break
                        except Exception:
                            continue
                if uploaded:
                    await human_delay(3, 5)
                else:
                    logger.warning("LinkedIn: could not upload image, posting text-only")
            except Exception as e:
                logger.warning("LinkedIn: image upload failed, posting text-only: %s", e)

        # Wait for textbox (in shadow DOM — locator pierces it, wait_for_selector does not)
        textbox = page.locator(LI_TEXTBOX).first
        await textbox.wait_for(timeout=COMPOSE_TIMEOUT)
        await human_delay(1, 2)

        # Type content
        await human_type(page, LI_TEXTBOX, text)
        await human_delay(1, 3)

        # Click Post button
        post_btn = page.get_by_role("button", name="Post", exact=True)
        await post_btn.wait_for(timeout=COMPOSE_TIMEOUT)
        await post_btn.click()
        await human_delay(3, 5)

        # Post-post browsing
        await page.goto(PLATFORMS["linkedin"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await browse_feed(page, "linkedin")

        logger.info("Successfully posted to LinkedIn")
        return True

    except Exception as e:
        logger.error("Failed to post to LinkedIn: %s", e, exc_info=True)
        return False
    finally:
        if image_path:
            try:
                image_path.unlink(missing_ok=True)
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass


# ─── Facebook ───────────────────────────────────────────────────────────────

FB_COMPOSER_TRIGGER = '[aria-label="What\'s on your mind?"], [role="button"]:has-text("What\'s on your mind")'
FB_TEXTBOX = '[role="textbox"]'
FB_POST_BUTTON = '[aria-label="Post"]'


async def post_to_facebook(draft: dict, pw) -> bool:
    """Post content to Facebook. Supports text-only and text+image."""
    context = None
    image_path = None
    try:
        text, image_text = _extract_content(draft["content"], "facebook")

        # Generate image if needed
        if image_text:
            from utils.image_generator import generate_landscape_image
            image_path = ROOT / "drafts" / "pending" / f"facebook-{draft.get('id', 'temp')}.png"
            generate_landscape_image(image_text, image_path)
            logger.info("Facebook: generated branded image at %s", image_path)

        context = await _launch_context(pw, "facebook")
        page = context.pages[0] if context.pages else await context.new_page()

        # Pre-post browsing
        await page.goto(PLATFORMS["facebook"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded")
        await browse_feed(page, "facebook")

        # Open composer
        await page.click(FB_COMPOSER_TRIGGER, timeout=COMPOSE_TIMEOUT)
        await page.wait_for_selector(FB_TEXTBOX, timeout=COMPOSE_TIMEOUT)
        await human_delay(1, 2)

        # Upload image if available
        if image_path and image_path.exists():
            try:
                uploaded = False
                # Try clicking "Photo/video" button to open media area
                photo_selectors = [
                    '[aria-label="Photo/video"]',
                    '[aria-label="Photo/Video"]',
                    'div[role="button"]:has-text("Photo/video")',
                    'div[role="button"]:has-text("Photo/Video")',
                ]
                for sel in photo_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=3000):
                            await btn.click()
                            logger.info("Facebook: clicked photo/video button via %s", sel)
                            await human_delay(1, 2)
                            break
                    except Exception:
                        continue

                # Now find file input
                fi_selectors = [
                    'input[type="file"][accept*="image"]',
                    'input[type="file"][accept*="video"]',
                    'input[type="file"]',
                ]
                for sel in fi_selectors:
                    try:
                        fi = page.locator(sel).first
                        if await fi.count() > 0:
                            await fi.set_input_files(str(image_path))
                            uploaded = True
                            logger.info("Facebook: uploaded image via %s", sel)
                            break
                    except Exception:
                        continue

                if uploaded:
                    await human_delay(3, 5)
                else:
                    logger.warning("Facebook: could not upload image, posting text-only")
            except Exception as e:
                logger.warning("Facebook: image upload failed, posting text-only: %s", e)

        # Type content
        textbox = page.locator(FB_TEXTBOX).last
        await textbox.click()
        for char in text:
            await textbox.press_sequentially(char, delay=0)
            delay_ms = random.uniform(30, 120)
            if random.random() < 0.05:
                delay_ms = random.uniform(300, 800)
            await asyncio.sleep(delay_ms / 1000)
        await human_delay(1, 3)

        # Click post
        await page.click(FB_POST_BUTTON, timeout=COMPOSE_TIMEOUT)
        await human_delay(3, 5)

        # Post-post browsing
        await page.goto(PLATFORMS["facebook"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await browse_feed(page, "facebook")

        logger.info("Successfully posted to Facebook")
        return True

    except Exception as e:
        logger.error("Failed to post to Facebook: %s", e, exc_info=True)
        return False
    finally:
        if image_path:
            try:
                image_path.unlink(missing_ok=True)
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass


# ─── Reddit ────────────────────────────────────────────────────────────────

REDDIT_SUBMIT_URL = "https://www.reddit.com/r/{subreddit}/submit"


async def post_to_reddit(draft: dict, pw) -> bool:
    """Post content to Reddit (text post to configured subreddits)."""
    context = None
    try:
        reddit_content = draft["content"]["reddit"]
        if isinstance(reddit_content, str):
            # Fallback if not structured
            title = reddit_content[:120]
            body = reddit_content
        else:
            title = reddit_content["title"]
            body = reddit_content["body"]

        subreddits = PLATFORMS.get("reddit", {}).get("subreddits", ["programming"])
        # Pick one random subreddit per post to avoid spam
        subreddit = random.choice(subreddits)

        context = await _launch_context(pw, "reddit")
        page = context.pages[0] if context.pages else await context.new_page()

        # Pre-post browsing
        await page.goto(PLATFORMS["reddit"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded")
        await browse_feed(page, "reddit")

        # Navigate to submit page
        submit_url = REDDIT_SUBMIT_URL.format(subreddit=subreddit)
        logger.info("Reddit: submitting to r/%s", subreddit)
        await page.goto(submit_url, timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded")
        await human_delay(2, 4)

        # Fill title — textarea inside faceplate-textarea-input shadow component
        # Playwright locators pierce shadow DOM automatically
        title_el = page.locator('textarea[name="title"]').first
        await title_el.wait_for(timeout=COMPOSE_TIMEOUT)
        await title_el.click()
        await human_type(page, 'textarea[name="title"]', title)
        logger.info("Reddit: filled title")
        await human_delay(1, 2)

        # Fill body — contenteditable div with role="textbox"
        body_el = page.locator('[role="textbox"][name="body"], div[contenteditable="true"][name="body"]').first
        await body_el.wait_for(timeout=COMPOSE_TIMEOUT)
        await body_el.click()
        await human_type(page, '[role="textbox"][name="body"]', body)
        logger.info("Reddit: filled body")
        await human_delay(1, 3)

        # Click Post button
        post_btn = page.locator('button:has-text("Post")').first
        await post_btn.wait_for(timeout=COMPOSE_TIMEOUT)
        await post_btn.click()
        logger.info("Reddit: clicked Post")

        await human_delay(3, 6)

        # Post-post browsing
        await page.goto(PLATFORMS["reddit"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await browse_feed(page, "reddit")

        logger.info("Successfully posted to Reddit (r/%s)", subreddit)
        return True

    except Exception as e:
        logger.error("Failed to post to Reddit: %s", e, exc_info=True)
        return False
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass


# ─── TikTok ────────────────────────────────────────────────────────────────


async def post_to_tiktok(draft: dict, pw) -> bool:
    """Post a short branded video to TikTok (web only supports video uploads)."""
    context = None
    video_path = None
    try:
        from utils.image_generator import generate_tiktok_video

        tiktok_content = draft["content"]["tiktok"]
        if isinstance(tiktok_content, str):
            caption = tiktok_content
            image_text = tiktok_content[:100]
        else:
            caption = tiktok_content["caption"]
            image_text = tiktok_content["image_text"]

        # Generate a short video from the branded image
        video_path = ROOT / "drafts" / "pending" / f"tiktok-{draft.get('id', 'temp')}.mp4"
        generate_tiktok_video(image_text, video_path)
        logger.info("TikTok: generated video at %s", video_path)

        context = await _launch_context(pw, "tiktok")
        page = context.pages[0] if context.pages else await context.new_page()

        # Pre-post browsing
        await page.goto(PLATFORMS["tiktok"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded")
        await browse_feed(page, "tiktok")

        # Navigate to upload page
        upload_url = PLATFORMS["tiktok"].get("upload_url", "https://www.tiktok.com/creator#/upload?scene=creator_center")
        await page.goto(upload_url, timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded")
        await human_delay(3, 5)

        # Upload video via the hidden file input (no need for visibility check)
        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(str(video_path))
        logger.info("TikTok: uploaded video")
        await human_delay(5, 10)

        # Dismiss any popups/dialogs that appear after upload
        # "Turn on automatic content checks?" dialog
        for dismiss_sel in ['button:has-text("Cancel")', 'button:has-text("Got it")']:
            try:
                dismiss_btn = page.locator(dismiss_sel).first
                if await dismiss_btn.is_visible(timeout=3000):
                    await dismiss_btn.click()
                    logger.info("TikTok: dismissed dialog via %s", dismiss_sel)
                    await human_delay(1, 2)
            except Exception:
                pass

        # Wait for video processing — post editor should be visible
        await human_delay(3, 5)

        # Fill caption — TikTok uses Draft.js editor (role="combobox", contenteditable)
        caption_filled = False
        caption_selectors = [
            'div.public-DraftEditor-content',
            'div[role="combobox"][contenteditable="true"]',
            'div[contenteditable="true"]',
        ]
        for sel in caption_selectors:
            try:
                cap_el = page.locator(sel).first
                if await cap_el.is_visible(timeout=10000):
                    await cap_el.click()
                    # Clear any existing text first (TikTok may pre-fill with filename)
                    await page.keyboard.press("Control+a")
                    await human_delay(0.5, 1)
                    await page.keyboard.press("Backspace")
                    await human_delay(0.5, 1)
                    # Type caption char by char for human emulation
                    await human_type(page, sel, caption)
                    caption_filled = True
                    logger.info("TikTok: filled caption via %s", sel)
                    break
            except Exception:
                continue

        if not caption_filled:
            logger.warning("TikTok: could not find caption field, posting without caption")

        await human_delay(2, 4)

        # Click Post button
        post_btn = page.locator('[data-e2e="post_video_button"]')
        try:
            await post_btn.wait_for(timeout=10000)
            await post_btn.scroll_into_view_if_needed()
            await human_delay(1, 2)
            await post_btn.click()
            logger.info("TikTok: clicked Post button")
        except Exception:
            # Fallback: try generic Post button text
            post_btn = page.locator('button:has-text("Post")').first
            await post_btn.scroll_into_view_if_needed()
            await post_btn.click()
            logger.info("TikTok: clicked Post button (fallback)")

        await human_delay(5, 10)

        # Post-post browsing
        await page.goto(PLATFORMS["tiktok"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await browse_feed(page, "tiktok")

        logger.info("Successfully posted to TikTok")
        return True

    except Exception as e:
        logger.error("Failed to post to TikTok: %s", e, exc_info=True)
        return False
    finally:
        # Cleanup video file
        if video_path:
            try:
                video_path.unlink(missing_ok=True)
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass


# ─── Instagram ─────────────────────────────────────────────────────────────


async def post_to_instagram(draft: dict, pw) -> bool:
    """Post a photo with caption to Instagram (desktop web).

    Instagram requires an image — we generate a branded image from the caption text.
    Flow: Click Create → Upload image → Next → Next → Add caption → Share
    """
    context = None
    try:
        from utils.image_generator import generate_instagram_image

        caption = draft["content"]["instagram"]

        # Generate branded image from caption
        image_path = ROOT / "drafts" / "pending" / f"instagram-{draft.get('id', 'temp')}.png"
        generate_instagram_image(caption, image_path)
        logger.info("Instagram: generated image at %s", image_path)

        context = await _launch_context(pw, "instagram")
        page = context.pages[0] if context.pages else await context.new_page()

        # Pre-post browsing
        await page.goto(PLATFORMS["instagram"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded")
        await browse_feed(page, "instagram")

        # Re-navigate to home after browsing to ensure clean sidebar state
        await page.goto(PLATFORMS["instagram"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded")
        await human_delay(2, 4)

        # Click "Create" / "New post" in sidebar — try multiple selectors
        create_selectors = [
            '[aria-label="New post"]',
            '[aria-label="Create"]',
            'svg[aria-label="New post"]',
            'svg[aria-label="Create"]',
        ]
        create_clicked = False
        for sel in create_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    create_clicked = True
                    logger.info("Instagram: clicked create via %s", sel)
                    break
            except Exception:
                continue

        if not create_clicked:
            raise Exception("Could not find Instagram Create/New post button")
        await human_delay(1, 2)

        # Create expands a submenu with Post, Live video, Ad
        # The "Post" item is a DIV containing an SVG with aria-label="Post"
        post_svg = page.locator('svg[aria-label="Post"]').first
        await post_svg.wait_for(timeout=COMPOSE_TIMEOUT)
        await post_svg.click()
        logger.info("Instagram: clicked 'Post' SVG from submenu")
        await human_delay(2, 4)

        # The "Create new post" dialog should now be open
        # Wait for the dialog to appear
        dialog = page.locator('[role="dialog"]')
        await dialog.wait_for(timeout=COMPOSE_TIMEOUT)
        logger.info("Instagram: dialog appeared")

        # Look for "Select from computer" button inside dialog
        select_btn = dialog.locator(
            'button:has-text("Select from computer"), '
            'button:has-text("Select From Computer"), '
            'button:has-text("Select from your computer")'
        ).first
        try:
            await select_btn.wait_for(timeout=10000)
            logger.info("Instagram: found 'Select from computer' button")
        except Exception:
            logger.info("Instagram: no 'Select from computer' button in dialog")

        # Look for file input (may be hidden in dialog or page)
        file_input = page.locator('input[type="file"]')
        count = await file_input.count()
        logger.info("Instagram: found %d file input(s)", count)
        if count > 0:
            await file_input.first.set_input_files(str(image_path))
        else:
            # Try clicking the Select button to trigger file chooser
            async with page.expect_file_chooser(timeout=COMPOSE_TIMEOUT) as fc_info:
                await select_btn.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(str(image_path))
        logger.info("Instagram: uploaded image")
        await human_delay(3, 5)

        # Click "Next" — crop step
        # The "Next" in dialog header is a DIV, not a <button>
        # Use get_by_text scoped to the dialog for precise matching
        dialog = page.locator('[role="dialog"]')
        next_el = dialog.get_by_text("Next", exact=True)
        await next_el.wait_for(timeout=COMPOSE_TIMEOUT)
        await next_el.click(force=True)
        logger.info("Instagram: clicked Next (crop)")
        await human_delay(3, 5)

        # Click "Next" again — filter/edit step
        dialog2 = page.locator('[role="dialog"]')
        next_el2 = dialog2.get_by_text("Next", exact=True)
        await next_el2.wait_for(timeout=COMPOSE_TIMEOUT)
        await next_el2.click(force=True)
        logger.info("Instagram: clicked Next (filter)")
        await human_delay(3, 5)

        # Type caption — try multiple selectors for the caption field
        caption_selectors = [
            'textarea[aria-label="Write a caption..."]',
            'div[aria-label="Write a caption..."]',
            'textarea[placeholder="Write a caption..."]',
            '[role="textbox"][contenteditable="true"]',
            '[role="textbox"]',
            'div[contenteditable="true"]',
            'textarea',
        ]
        caption_el = None
        for sel in caption_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=3000):
                    caption_el = el
                    logger.info("Instagram: found caption field via %s", sel)
                    break
            except Exception:
                continue

        if caption_el is None:
            raise Exception("Could not find Instagram caption field")

        await caption_el.dispatch_event("click")
        await caption_el.focus()
        # Type caption char by char
        for char in caption:
            await caption_el.press_sequentially(char, delay=0)
            delay_ms = random.uniform(30, 120)
            if random.random() < 0.05:
                delay_ms = random.uniform(300, 800)
            await asyncio.sleep(delay_ms / 1000)
        logger.info("Instagram: typed caption")
        await human_delay(1, 3)

        # Click "Share" — it's a DIV with role="button", not a <button>
        dialog3 = page.locator('[role="dialog"]')
        share_el = dialog3.get_by_role("button", name="Share", exact=True)
        await share_el.wait_for(timeout=COMPOSE_TIMEOUT)
        await share_el.click(force=True)
        logger.info("Instagram: clicked Share (get_by_role)")

        # Wait for Instagram to process the upload
        # After clicking Share, Instagram shows "Sharing" spinner, then a confirmation
        # Wait for dialog title to change from "Sharing" or dialog to close
        try:
            # First check for "Sharing" to confirm Share click worked
            sharing_text = page.locator('text="Sharing"')
            await sharing_text.wait_for(timeout=10000)
            logger.info("Instagram: sharing in progress...")

            # Now wait for it to finish — dialog closes or shows confirmation
            await page.locator('[role="dialog"]').wait_for(state="hidden", timeout=120000)
            logger.info("Instagram: sharing complete (dialog closed)")
        except Exception:
            # Even without perfect detection, wait long enough for upload to finish
            logger.info("Instagram: waiting for upload to complete...")
            await human_delay(15, 20)

        await human_delay(3, 5)

        # Post-post browsing
        await page.goto(PLATFORMS["instagram"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await browse_feed(page, "instagram")

        # Cleanup image
        try:
            image_path.unlink()
        except Exception:
            pass

        logger.info("Successfully posted to Instagram")
        return True

    except Exception as e:
        logger.error("Failed to post to Instagram: %s", e, exc_info=True)
        return False
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass


# ─── Orchestrator ───────────────────────────────────────────────────────────

PLATFORM_POSTERS = {
    "x": post_to_x,
    "linkedin": post_to_linkedin,
    "facebook": post_to_facebook,
    "instagram": post_to_instagram,
    "reddit": post_to_reddit,
    "tiktok": post_to_tiktok,
}

# ─── Slot → Platform Mapping ──────────────────────────────────────────────
# Per the workflow spec in docs/auto-poster-workflow.md Phase 4
# IST posting times and platform assignments per slot.
# Some platforms only post on certain days of the week (0=Mon, 6=Sun).

SLOT_SCHEDULE = {
    1: {  # 18:30 IST = 8:00 AM EST
        "time_ist": "18:30",
        "platforms": {
            "x": {"days": [0, 1, 2, 3, 4, 5, 6]},          # daily
            "linkedin": {"days": [1, 2, 3, 4]},              # Tue-Fri
        },
    },
    2: {  # 20:30 IST = 10:00 AM EST
        "time_ist": "20:30",
        "platforms": {
            "facebook": {"days": [0, 1, 2, 3, 4, 5, 6]},    # daily
        },
    },
    3: {  # 23:30 IST = 1:00 PM EST
        "time_ist": "23:30",
        "platforms": {
            "x": {"days": [0, 1, 2, 3, 4, 5, 6]},          # daily
            "reddit": {"days": [1, 3, 5]},                   # Tue, Thu, Sat (2-3x/week)
        },
    },
    4: {  # 01:30 IST = 3:00 PM EST
        "time_ist": "01:30",
        "platforms": {
            "x": {"days": [0, 1, 2, 3, 4, 5, 6]},          # daily
        },
    },
    5: {  # 04:30 IST = 6:00 PM EST
        "time_ist": "04:30",
        "platforms": {
            "tiktok": {"days": [0, 1, 2, 3, 4, 5, 6]},     # daily
        },
    },
    6: {  # 06:30 IST = 8:00 PM EST
        "time_ist": "06:30",
        "platforms": {
            "instagram": {"days": [0, 1, 2, 3, 4, 5, 6]},  # daily
        },
    },
}

# IST slot times in minutes from midnight for auto-detection
_SLOT_TIMES_MIN = {
    slot: int(info["time_ist"].split(":")[0]) * 60 + int(info["time_ist"].split(":")[1])
    for slot, info in SLOT_SCHEDULE.items()
}


def _auto_detect_slot() -> int:
    """Find the closest slot to the current IST time."""
    # IST = UTC + 5:30
    from datetime import timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    now_min = now_ist.hour * 60 + now_ist.minute

    best_slot = 1
    best_diff = float("inf")
    for slot, slot_min in _SLOT_TIMES_MIN.items():
        diff = abs(now_min - slot_min)
        # Handle wrap-around midnight
        diff = min(diff, 1440 - diff)
        if diff < best_diff:
            best_diff = diff
            best_slot = slot
    return best_slot


def get_slot_platforms(slot: int) -> list[str]:
    """Return the list of platforms to post to for a given slot and today's day of week."""
    if slot not in SLOT_SCHEDULE:
        logger.warning("Unknown slot %d, falling back to all enabled platforms", slot)
        return [p for p in PLATFORM_POSTERS if PLATFORMS.get(p, {}).get("enabled", False)]

    from datetime import timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(ist).weekday()  # 0=Mon, 6=Sun

    slot_info = SLOT_SCHEDULE[slot]
    platforms = []
    for platform, rules in slot_info["platforms"].items():
        if not PLATFORMS.get(platform, {}).get("enabled", False):
            continue
        if today in rules["days"]:
            platforms.append(platform)

    return platforms


async def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-Poster: post drafts to social platforms")
    parser.add_argument("--slot", type=int, choices=range(1, 7), default=None,
                        help="Posting slot (1-6). Auto-detects from current IST time if omitted.")
    args = parser.parse_args()

    slot = args.slot if args.slot else _auto_detect_slot()
    platforms_for_slot = get_slot_platforms(slot)

    logger.info("=== Auto-Poster started (slot %d) ===", slot)
    logger.info("Platforms for slot %d today: %s", slot, platforms_for_slot or "(none)")

    if not platforms_for_slot:
        logger.info("No platforms to post to for slot %d today. Exiting.", slot)
        return

    draft = get_next_draft()
    if draft is None:
        logger.info("No pending drafts. Exiting.")
        return

    logger.info("Processing draft: %s (topic: %s)", draft.get("id"), draft.get("topic"))

    # Randomize order within slot
    random.shuffle(platforms_for_slot)
    logger.info("Posting order: %s", platforms_for_slot)

    from playwright.async_api import async_playwright

    results = {}
    async with async_playwright() as pw:
        for i, platform in enumerate(platforms_for_slot):
            if platform not in PLATFORM_POSTERS:
                logger.warning("No poster function for %s, skipping", platform)
                continue
            logger.info("Posting to %s...", platform)
            poster = PLATFORM_POSTERS[platform]
            success = await poster(draft, pw)
            results[platform] = success

            # Wait between platforms (not after last one)
            if i < len(platforms_for_slot) - 1:
                wait = random.uniform(POST_INTERVAL_MIN, POST_INTERVAL_MAX)
                logger.info("Waiting %.0f seconds before next platform...", wait)
                await asyncio.sleep(wait)

    succeeded = [p for p, ok in results.items() if ok]
    failed = [p for p, ok in results.items() if not ok]

    if succeeded:
        mark_posted(draft, succeeded)
        if failed:
            logger.warning("Partial success. Failed platforms: %s", failed)
    else:
        errors = ", ".join(f"{p}: failed" for p in failed)
        mark_failed(draft, f"All platforms failed: {errors}")

    logger.info("=== Auto-Poster finished (slot %d) ===", slot)


if __name__ == "__main__":
    asyncio.run(main())
