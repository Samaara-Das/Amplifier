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

# draft_manager and human_behavior removed — campaign posting managed by background_agent
# Stubs for any remaining references in platform functions
async def human_delay(min_ms=500, max_ms=2000):
    """Minimal delay between actions."""
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

async def human_type(page, selector, text, **kwargs):
    """Type text character by character with small delays."""
    el = page.locator(selector).first
    await el.fill("")
    for char in text:
        await el.press_sequentially(char, delay=random.randint(30, 80))

async def browse_feed(page, platform, **kwargs):
    """Minimal feed browsing — just wait briefly."""
    await page.wait_for_timeout(random.randint(1000, 3000))

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
RETRY_DELAY_SEC = int(os.getenv("RETRY_DELAY_SEC", "300"))  # 5 minutes

# Load platform config
with open(ROOT / "config" / "platforms.json", "r", encoding="utf-8") as f:
    PLATFORMS = json.load(f)

# Draft directories
DRAFT_DIRS = {
    "pending": ROOT / "drafts" / "pending",
    "posted": ROOT / "drafts" / "posted",
    "failed": ROOT / "drafts" / "failed",
}
for d in DRAFT_DIRS.values():
    d.mkdir(parents=True, exist_ok=True)


def get_next_draft(slot: int = None) -> dict | None:
    """Get the next pending draft. If slot is given, prefer drafts matching that slot."""
    pending = DRAFT_DIRS["pending"]
    drafts = sorted(pending.glob("*.json"))
    if not drafts:
        return None

    # Prefer drafts matching the slot
    if slot is not None:
        for path in drafts:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("slot") == slot:
                    data["_path"] = str(path)
                    return data
            except (json.JSONDecodeError, OSError):
                continue

    # Fall back to the oldest draft (any slot or unslotted)
    for path in drafts:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_path"] = str(path)
            return data
        except (json.JSONDecodeError, OSError):
            continue
    return None


def mark_posted(draft: dict, platforms: list[str]) -> None:
    """Move draft from pending to posted, recording which platforms succeeded."""
    draft["status"] = "posted"
    draft["posted_at"] = datetime.now(tz=__import__('datetime').timezone.utc).isoformat()
    draft["platforms_posted"] = platforms
    src = Path(draft.pop("_path", ""))
    dest = DRAFT_DIRS["posted"] / src.name
    dest.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    if src.exists():
        src.unlink()
    logger.info("Draft %s marked as posted → %s", draft.get("id"), dest.name)


def mark_failed(draft: dict, error: str) -> None:
    """Move draft from pending to failed with error info."""
    draft["status"] = "failed"
    draft["error"] = error
    draft["failed_at"] = datetime.now(tz=__import__('datetime').timezone.utc).isoformat()
    src = Path(draft.pop("_path", ""))
    dest = DRAFT_DIRS["failed"] / src.name
    dest.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    if src.exists():
        src.unlink()
    logger.info("Draft %s marked as failed → %s", draft.get("id"), dest.name)


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
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
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


# ─── Script-Driven Posting Engine ──────────────────────────────────────────
# Declarative JSON scripts replace hardcoded platform functions (v2/v3 upgrade).
# Falls back to legacy functions for platforms without scripts (TikTok, Instagram).

SCRIPTS_DIR = ROOT / "config" / "scripts"


def _get_script_path(platform: str) -> Path | None:
    """Find the JSON script for a platform. Returns None if no script exists."""
    script_path = SCRIPTS_DIR / f"{platform}_post.json"
    if script_path.exists():
        return script_path
    return None


async def post_via_script(draft: dict, pw, platform: str) -> str | None:
    """Post content using a declarative JSON script + ScriptExecutor.

    This is the primary posting path for platforms with JSON scripts.
    Falls back to None (caller should use legacy function) if no script exists.

    Returns post URL on success, None on failure.
    """
    script_path = _get_script_path(platform)
    if script_path is None:
        return None  # No script — caller should use legacy function

    from engine.script_parser import load_script
    from engine.script_executor import ScriptExecutor

    context = None
    image_path = None
    try:
        # Parse draft content
        text, image_text = _extract_content(draft["content"], platform)

        # Handle Reddit's special JSON format
        title = ""
        body = ""
        if platform == "reddit":
            reddit_content = draft["content"].get("reddit", "")
            if isinstance(reddit_content, str):
                try:
                    parsed = json.loads(reddit_content)
                    title = parsed.get("title", reddit_content[:120])
                    body = parsed.get("body", "")
                except (ValueError, TypeError):
                    title = reddit_content[:120]
                    body = reddit_content
            elif isinstance(reddit_content, dict):
                title = reddit_content.get("title", "")
                body = reddit_content.get("body", "")

        # Resolve image path
        generated_image = False
        ext_image = draft.get("image_path")
        if ext_image and Path(str(ext_image)).exists():
            image_path = Path(str(ext_image))
        elif image_text:
            try:
                from ai.image_manager import create_default_image_manager as _create_img_mgr
                _mgr = _create_img_mgr()
                image_path = ROOT / "drafts" / "pending" / f"{platform}-{draft.get('id', 'temp')}.jpg"
                await _mgr.generate(image_text, str(image_path))
                generated_image = True
            except Exception as e:
                logger.warning("%s: image generation failed: %s", platform, e)

        # Prepare image as base64 for clipboard paste (LinkedIn, Facebook)
        image_b64 = ""
        if image_path and image_path.exists():
            import base64
            with open(str(image_path), "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()

        # Get Reddit username if needed
        reddit_username = ""
        if platform == "reddit":
            context = await _launch_context(pw, "reddit")
            page = context.pages[0] if context.pages else await context.new_page()
            import re as _re
            await page.goto("https://www.reddit.com/user/me/", timeout=PAGE_LOAD_TIMEOUT)
            await page.wait_for_load_state("domcontentloaded")
            try:
                await page.wait_for_url(lambda url: "/user/me" not in url.lower(), timeout=10000)
            except Exception:
                pass
            user_match = _re.search(r'/user/([^/]+)', page.url)
            if user_match and user_match.group(1).lower() != "me":
                reddit_username = user_match.group(1)
            if not reddit_username:
                try:
                    api_page = await context.new_page()
                    await api_page.goto("https://www.reddit.com/api/v1/me.json", timeout=PAGE_LOAD_TIMEOUT)
                    me_data = json.loads(await api_page.locator("body").inner_text())
                    reddit_username = me_data.get("name", "")
                    await api_page.close()
                except Exception:
                    pass
            if not reddit_username:
                logger.error("Reddit: could not determine username")
                return None
        else:
            context = await _launch_context(pw, platform)
            page = context.pages[0] if context.pages else await context.new_page()

        # Build variables for template substitution
        variables = {
            "text": text or "",
            "title": title,
            "body": body,
            "image_path": str(image_path) if image_path and image_path.exists() else "",
            "image_b64": image_b64,
            "reddit_username": reddit_username,
        }

        # Load and execute script
        script = load_script(script_path)
        executor = ScriptExecutor(page, variables)
        execution = await executor.execute(script)

        if execution.success:
            post_url = execution.post_url
            logger.info("Script posting to %s succeeded (URL: %s)", platform, post_url)
            return post_url or f"https://{platform}.com/posted"
        else:
            logger.error(
                "Script posting to %s failed at step '%s': %s",
                platform, execution.failed_step, execution.error,
            )
            # Log execution trace
            for step_result in execution.log:
                status = "OK" if step_result.success else "FAIL"
                logger.debug("  [%s] %s: %s", status, step_result.step_id, step_result.message)
            return None

    except Exception as e:
        logger.error("Script posting to %s failed: %s", platform, e, exc_info=True)
        return None
    finally:
        if image_path and generated_image:
            try:
                image_path.unlink(missing_ok=True)
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass


async def post_to_platform(draft: dict, pw, platform: str) -> str | None:
    """Unified posting function — tries script-driven first, falls back to legacy.

    This is the single entry point for all platform posting.
    """
    # Try script-driven posting first
    script_path = _get_script_path(platform)
    if script_path:
        logger.info("Using JSON script for %s: %s", platform, script_path.name)
        result = await post_via_script(draft, pw, platform)
        if result is not None:
            return result
        logger.warning("Script posting failed for %s, falling back to legacy", platform)

    # Fall back to legacy hardcoded function
    legacy_func = _LEGACY_PLATFORM_POSTERS.get(platform)
    if legacy_func:
        logger.info("Using legacy poster for %s", platform)
        return await legacy_func(draft, pw)

    logger.error("No posting method available for %s", platform)
    return None


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


async def post_to_x(draft: dict, pw) -> str | None:
    """Post content to X (Twitter). Returns post URL on success, None on failure."""
    context = None
    image_path = None
    try:
        text, image_text = _extract_content(draft["content"], "x")

        # Check for external image path first, then generate from prompt
        generated_image = False
        ext_image = draft.get("image_path")
        if ext_image and Path(str(ext_image)).exists():
            image_path = Path(str(ext_image))
            logger.info("X: using provided image: %s", image_path)
        elif image_text:
            from ai.image_manager import create_default_image_manager as _create_img_mgr
            image_path = ROOT / "drafts" / "pending" / f"x-{draft.get('id', 'temp')}.png"
            generate_landscape_image(image_text, image_path)
            generated_image = True
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
                uploaded = False
                abs_image = str(Path(str(image_path)).resolve())
                logger.info("X: absolute image path: %s", abs_image)

                # Use the hidden file input directly — this is the most reliable way on X
                fi = page.locator('input[data-testid="fileInput"]').first
                if await fi.count() > 0:
                    await fi.set_input_files(abs_image)
                    logger.info("X: set file on input[data-testid=fileInput]")
                    # Wait for image to process and appear in attachments
                    try:
                        await page.locator('[data-testid="attachments"]').wait_for(timeout=15000)
                        # Extra wait for X to fully process the image
                        await page.wait_for_timeout(3000)
                        logger.info("X: image attachment preview confirmed")
                        uploaded = True
                    except Exception:
                        logger.error("X: attachments preview never appeared after set_input_files")

                if not uploaded:
                    logger.warning("X: image upload FAILED")
                    if not (text and text.strip()):
                        logger.error("X: no text and no image — nothing to post")
                        return None
                else:
                    await human_delay(2, 4)
            except Exception as e:
                logger.warning("X: image upload failed: %s", e)
                if not (text and text.strip()):
                    return None

        # Type content (skip if empty — image-only post)
        if text and text.strip():
            # Click to focus first — triggers React's onFocus which is required
            # for the contenteditable textbox to accept input (especially in headless)
            textbox = page.locator(X_TEXTBOX).first
            await textbox.click(force=True)
            await page.wait_for_timeout(500)
            await page.keyboard.type(text, delay=random.randint(30, 80))
            await human_delay(1, 3)

        # Submit post — try multiple methods since X's overlay blocks standard clicks
        post_btn = page.locator(X_POST_BUTTON)
        await post_btn.wait_for(timeout=COMPOSE_TIMEOUT)

        # Check if button is actually enabled
        is_disabled = await post_btn.get_attribute("aria-disabled")
        if is_disabled == "true":
            logger.error("X: post button is DISABLED — no content to post (image may not have attached)")
            return None

        logger.info("X: post button is enabled, attempting to submit...")

        # Take screenshot before clicking post to verify state
        await page.screenshot(path=str(ROOT / "logs" / "x_before_post.png"))
        logger.info("X: screenshot saved to logs/x_before_post.png")

        # Ctrl+Enter keyboard shortcut (bypasses overlay div that intercepts pointer events)
        # Focus textbox with force=True (overlay blocks normal click)
        textbox = page.locator(X_TEXTBOX).first
        if await textbox.count() > 0:
            await textbox.click(force=True)
        await page.keyboard.press("Control+Enter")
        logger.info("X: pressed Ctrl+Enter")

        # Wait for post to process
        await page.wait_for_timeout(5000)

        # Take screenshot after to verify post went through
        await page.screenshot(path=str(ROOT / "logs" / "x_after_post.png"))
        logger.info("X: screenshot saved to logs/x_after_post.png")

        await human_delay(3, 5)

        # Extract post URL — go to profile, find the newest tweet (not a stale one)
        post_url = None
        try:
            profile_link = page.locator('a[data-testid="AppTabBar_Profile_Link"]')
            if await profile_link.count() > 0:
                profile_href = await profile_link.get_attribute("href")
                profile_url = f"https://x.com{profile_href}" if profile_href.startswith("/") else profile_href
                logger.info("X: navigating to profile %s", profile_url)

                # Hard refresh to avoid stale cache
                await page.goto(profile_url + "?t=" + str(int(asyncio.get_event_loop().time())), timeout=PAGE_LOAD_TIMEOUT)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(3000)

                # Wait for tweets to load
                try:
                    await page.locator('article[data-testid="tweet"]').first.wait_for(timeout=10000)
                except Exception:
                    logger.warning("X: timed out waiting for tweet articles to load")

                # Get the first tweet's status link — with retries and scroll
                for attempt in range(5):
                    link = page.locator('article[data-testid="tweet"] a[href*="/status/"]').first
                    if await link.count() > 0:
                        href = await link.get_attribute("href")
                        if href:
                            post_url = f"https://x.com{href}" if href.startswith("/") else href
                            logger.info("X: captured post URL (attempt %d): %s", attempt + 1, post_url)
                            break
                    logger.info("X: no status link on attempt %d, waiting...", attempt + 1)
                    await page.wait_for_timeout(2000)
            else:
                logger.warning("X: profile link not found in sidebar")
        except Exception as e:
            logger.warning("X: could not extract post URL: %s", e)

        # Post-post browsing
        await browse_feed(page, "x")

        logger.info("Successfully posted to X")
        return post_url or "https://x.com/posted"

    except Exception as e:
        logger.error("Failed to post to X: %s", e, exc_info=True)
        return None
    finally:
        if image_path and generated_image:
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


async def post_to_linkedin(draft: dict, pw) -> str | None:
    """Post content to LinkedIn. Returns post URL on success, None on failure.

    Flow: Open compose → paste image (if any) → type text (if any) → Post → grab URL from success dialog.
    """
    context = None
    image_path = None
    try:
        text, image_text = _extract_content(draft["content"], "linkedin")

        # Check for external image path first, then generate from prompt
        generated_image = False
        ext_image = draft.get("image_path")
        if ext_image and Path(str(ext_image)).exists():
            image_path = Path(str(ext_image))
            logger.info("LinkedIn: using provided image: %s", image_path)
        elif image_text:
            from ai.image_manager import create_default_image_manager as _create_img_mgr
            image_path = ROOT / "drafts" / "pending" / f"linkedin-{draft.get('id', 'temp')}.png"
            generate_landscape_image(image_text, image_path)
            generated_image = True
            logger.info("LinkedIn: generated branded image at %s", image_path)

        context = await _launch_context(pw, "linkedin")
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to feed
        await page.goto(PLATFORMS["linkedin"]["home_url"], wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_timeout(3000)
        await browse_feed(page, "linkedin")

        # Open compose modal (retry if modal doesn't appear)
        for compose_attempt in range(3):
            compose_btn = page.locator(LI_COMPOSE_TRIGGER).first
            await compose_btn.wait_for(timeout=COMPOSE_TIMEOUT)
            await compose_btn.click()
            logger.info("LinkedIn: clicked compose trigger (attempt %d)", compose_attempt + 1)
            await human_delay(2, 3)

            # Verify modal opened
            textbox = page.locator(LI_TEXTBOX).first
            try:
                await textbox.wait_for(timeout=5000)
                logger.info("LinkedIn: compose modal open")
                break
            except Exception:
                logger.warning("LinkedIn: compose modal didn't open, retrying...")
                await page.wait_for_timeout(2000)

        # Step 1: Paste image into composer (if available)
        if image_path and image_path.exists():
            abs_image = str(Path(str(image_path)).resolve())
            import base64
            with open(abs_image, "rb") as img_f:
                img_bytes = img_f.read()
            img_b64 = base64.b64encode(img_bytes).decode()

            # Focus textbox, then paste image via ClipboardEvent
            textbox = page.locator(LI_TEXTBOX).first
            await textbox.click()
            await human_delay(0.5, 1)

            # Use locator.evaluate to pierce shadow DOM (document.querySelector can't)
            textbox_el = page.locator(LI_TEXTBOX).first
            paste_result = await textbox_el.evaluate("""
                (el, b64) => {
                    const byteChars = atob(b64);
                    const byteNums = new Array(byteChars.length);
                    for (let i = 0; i < byteChars.length; i++) {
                        byteNums[i] = byteChars.charCodeAt(i);
                    }
                    const byteArray = new Uint8Array(byteNums);
                    const blob = new Blob([byteArray], { type: 'image/png' });
                    const file = new File([blob], 'image.png', { type: 'image/png' });

                    const dt = new DataTransfer();
                    dt.items.add(file);

                    const pasteEvent = new ClipboardEvent('paste', {
                        bubbles: true,
                        cancelable: true,
                        clipboardData: dt
                    });
                    el.dispatchEvent(pasteEvent);
                    return 'pasted';
                }
            """, img_b64)
            logger.info("LinkedIn: clipboard paste result: %s", paste_result)

            if paste_result == "pasted":
                # Wait for image to appear in composer
                await page.wait_for_timeout(3000)
                logger.info("LinkedIn: image pasted into composer")
            else:
                logger.warning("LinkedIn: image paste failed (%s)", paste_result)
                if not (text and text.strip()):
                    logger.error("LinkedIn: no text and no image — nothing to post")
                    return None
            await human_delay(1, 2)

        # Step 2: Type text (skip if empty — image-only post)
        if text and text.strip():
            textbox = page.locator(LI_TEXTBOX).first
            await textbox.click(force=True)
            await page.wait_for_timeout(500)
            # Type via keyboard (more reliable for shadow DOM contenteditable)
            await page.keyboard.type(text, delay=50)
            logger.info("LinkedIn: typed %d chars of text", len(text))
            await page.screenshot(path=str(ROOT / "logs" / "li_after_typing.png"))
            await human_delay(1, 2)

        # Step 3: Click Post button
        post_btn = page.get_by_role("button", name="Post", exact=True)
        await post_btn.wait_for(timeout=COMPOSE_TIMEOUT)
        await post_btn.click()
        logger.info("LinkedIn: post button clicked")

        # Step 4: Wait for "Post successful" dialog and extract URL from "View post" link
        post_url = None
        try:
            # Wait for success dialog (up to 10 seconds)
            view_post = page.locator('a:has-text("View post")')
            await view_post.wait_for(timeout=30000)
            href = await view_post.get_attribute("href")
            if href:
                post_url = href if href.startswith("http") else f"https://www.linkedin.com{href}"
                logger.info("LinkedIn: captured URL from success dialog: %s", post_url)

            # Dismiss the dialog
            try:
                not_now = page.locator('button:has-text("Not now")')
                if await not_now.count() > 0:
                    await not_now.click()
                    logger.info("LinkedIn: dismissed success dialog")
            except Exception:
                pass
        except Exception:
            # Text-only posts may not show success dialog — fall back to activity page
            logger.info("LinkedIn: no success dialog, checking activity page for URL...")
            try:
                await page.goto("https://www.linkedin.com/in/me/recent-activity/all/", wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                await page.wait_for_timeout(3000)
                activity_link = page.locator('a[href*="/feed/update/"]').first
                if await activity_link.count() > 0:
                    href = await activity_link.get_attribute("href")
                    if href:
                        post_url = href if href.startswith("http") else f"https://www.linkedin.com{href}"
                        logger.info("LinkedIn: captured URL from activity page: %s", post_url)
            except Exception as e:
                logger.warning("LinkedIn: could not get URL from activity page: %s", e)

        # Post-post browsing
        await browse_feed(page, "linkedin")

        logger.info("Successfully posted to LinkedIn")
        return post_url  # None if URL capture failed — don't return fake placeholder

    except Exception as e:
        logger.error("Failed to post to LinkedIn: %s", e, exc_info=True)
        return None
    finally:
        if image_path and generated_image:
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


async def post_to_facebook(draft: dict, pw) -> str | None:
    """Post content to Facebook. Returns post URL on success, None on failure.

    Flow: Open composer → paste image (if any) → type text (if any) → Post → capture URL from profile.
    """
    context = None
    image_path = None
    try:
        text, image_text = _extract_content(draft["content"], "facebook")

        # Check for external image path first, then generate from prompt
        generated_image = False
        ext_image = draft.get("image_path")
        if ext_image and Path(str(ext_image)).exists():
            image_path = Path(str(ext_image))
            logger.info("Facebook: using provided image: %s", image_path)
        elif image_text:
            from ai.image_manager import create_default_image_manager as _create_img_mgr
            image_path = ROOT / "drafts" / "pending" / f"facebook-{draft.get('id', 'temp')}.png"
            generate_landscape_image(image_text, image_path)
            generated_image = True
            logger.info("Facebook: generated branded image at %s", image_path)

        context = await _launch_context(pw, "facebook")
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to Facebook
        await page.goto(PLATFORMS["facebook"]["home_url"], wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_timeout(3000)
        await browse_feed(page, "facebook")

        # Open composer modal
        await page.click(FB_COMPOSER_TRIGGER, timeout=COMPOSE_TIMEOUT)
        await page.wait_for_selector(FB_TEXTBOX, timeout=COMPOSE_TIMEOUT)
        logger.info("Facebook: composer modal open")
        await human_delay(1, 2)

        # Step 1: Paste image into composer (if available)
        if image_path and image_path.exists():
            abs_image = str(Path(str(image_path)).resolve())
            import base64
            with open(abs_image, "rb") as img_f:
                img_bytes = img_f.read()
            img_b64 = base64.b64encode(img_bytes).decode()

            # Focus textbox, then paste image via ClipboardEvent
            textbox = page.locator(FB_TEXTBOX).first
            await textbox.click()
            await page.wait_for_timeout(500)

            paste_result = await textbox.evaluate("""
                (el, b64) => {
                    const byteChars = atob(b64);
                    const byteNums = new Array(byteChars.length);
                    for (let i = 0; i < byteChars.length; i++) {
                        byteNums[i] = byteChars.charCodeAt(i);
                    }
                    const byteArray = new Uint8Array(byteNums);
                    const blob = new Blob([byteArray], { type: 'image/png' });
                    const file = new File([blob], 'image.png', { type: 'image/png' });

                    const dt = new DataTransfer();
                    dt.items.add(file);

                    const pasteEvent = new ClipboardEvent('paste', {
                        bubbles: true,
                        cancelable: true,
                        clipboardData: dt
                    });
                    el.dispatchEvent(pasteEvent);
                    return 'pasted';
                }
            """, img_b64)
            logger.info("Facebook: clipboard paste result: %s", paste_result)

            if paste_result == "pasted":
                await page.wait_for_timeout(3000)
                logger.info("Facebook: image pasted into composer")
            else:
                logger.warning("Facebook: image paste failed (%s)", paste_result)
                if not (text and text.strip()):
                    logger.error("Facebook: no text and no image — nothing to post")
                    return None
            await human_delay(1, 2)

        # Step 2: Type text (skip if empty — image-only post)
        if text and text.strip():
            textbox = page.locator(FB_TEXTBOX).first
            await textbox.click()
            await page.wait_for_timeout(500)
            await page.keyboard.type(text, delay=50)
            logger.info("Facebook: typed %d chars of text", len(text))
            await human_delay(1, 2)

        # Step 3: Click Post button
        post_btn = page.locator(FB_POST_BUTTON)
        await post_btn.wait_for(timeout=COMPOSE_TIMEOUT)
        await post_btn.click()
        logger.info("Facebook: post button clicked")

        # Wait for post to process
        await page.wait_for_timeout(5000)

        # Step 4: Capture URL
        # Facebook's modern React UI doesn't expose post permalinks as <a> links.
        # Use profile URL as reliable fallback — the post is visible at the top of the profile.
        post_url = None
        try:
            await page.goto("https://www.facebook.com/me", wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
            await page.wait_for_timeout(2000)
            profile_url = page.url
            # Use profile URL as the post reference
            post_url = profile_url
            logger.info("Facebook: using profile URL: %s", post_url)
        except Exception as e:
            logger.warning("Facebook: could not get profile URL: %s", e)

        # Post-post browsing
        await browse_feed(page, "facebook")

        logger.info("Successfully posted to Facebook")
        return post_url or "https://facebook.com/posted"

    except Exception as e:
        logger.error("Failed to post to Facebook: %s", e, exc_info=True)
        return None
    finally:
        if image_path and generated_image:
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

async def post_to_reddit(draft: dict, pw) -> str | None:
    """Post content to Reddit via user profile. Supports text, image+text, and image-only posts.

    Post types:
      - text-only: Text tab → title + body
      - image-only: Images & Video tab → title + upload image
      - image+text: Images & Video tab → title + upload image + body

    Returns post URL on success, None on failure.
    """
    context = None
    try:
        reddit_content = draft["content"]["reddit"]
        if isinstance(reddit_content, str):
            try:
                import json as _json
                parsed = _json.loads(reddit_content)
                title = parsed.get("title", reddit_content[:120])
                body = parsed.get("body", "")
            except (ValueError, TypeError):
                title = reddit_content[:120]
                body = reddit_content
        else:
            title = reddit_content.get("title", "")
            body = reddit_content.get("body", "")

        # Check for external image path
        image_path = None
        ext_image = draft.get("image_path")
        if ext_image and Path(str(ext_image)).exists():
            image_path = Path(str(ext_image))
            logger.info("Reddit: using provided image: %s", image_path)

        context = await _launch_context(pw, "reddit")
        page = context.pages[0] if context.pages else await context.new_page()

        # Get username — /user/me/ redirects via client-side JS which may not fire in headless
        import re as _re
        username = None

        await page.goto("https://www.reddit.com/user/me/", timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded")

        # Wait for the JS redirect to change URL from /user/me/ to /user/<actual>/
        try:
            await page.wait_for_url(lambda url: "/user/me" not in url.lower(), timeout=10000)
        except Exception:
            pass  # redirect may not fire in headless — fall through to fallback

        current_url = page.url
        user_match = _re.search(r'/user/([^/]+)', current_url)
        if user_match and user_match.group(1).lower() != "me":
            username = user_match.group(1)

        # Fallback: hit Reddit's JSON API to get username (no JS redirect needed)
        if not username:
            logger.info("Reddit: /user/me/ redirect didn't resolve, trying API fallback")
            try:
                api_page = await context.new_page()
                await api_page.goto("https://www.reddit.com/api/v1/me.json", timeout=PAGE_LOAD_TIMEOUT)
                import json as _json2
                body_text = await api_page.locator("body").inner_text()
                me_data = _json2.loads(body_text)
                username = me_data.get("name")
                await api_page.close()
                if username:
                    logger.info("Reddit: got username from API: %s", username)
            except Exception as e:
                logger.warning("Reddit: API fallback failed: %s", e)

        if not username:
            logger.error("Reddit: could not determine username")
            return None

        # Navigate to submit page on user profile
        submit_url = f"https://www.reddit.com/user/{username}/submit"
        logger.info("Reddit: submitting to u/%s", username)
        await page.goto(submit_url, timeout=PAGE_LOAD_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded")
        await human_delay(2, 4)

        has_image = image_path is not None

        # ── Image posts: switch to "Images & Video" tab and upload ──
        if has_image:
            img_tab = page.locator('button:has-text("Images & Video")')
            await img_tab.first.wait_for(timeout=COMPOSE_TIMEOUT)
            await img_tab.first.click()
            await human_delay(1, 2)
            logger.info("Reddit: switched to Images & Video tab")

            # Upload image via "Upload files" button → file chooser
            upload_btn = page.get_by_text("Upload files").first
            async with page.expect_file_chooser() as fc_info:
                await upload_btn.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(str(image_path))
            logger.info("Reddit: uploaded image via file chooser")

            # Wait for image to fully upload (thumbnail should appear)
            await page.wait_for_timeout(5000)
            logger.info("Reddit: waited for image upload to complete")

        # ── Fill title (always required) ──
        title_sel = 'textarea[name="title"], textarea[placeholder*="Title"]'
        title_el = page.locator(title_sel).first
        await title_el.wait_for(timeout=COMPOSE_TIMEOUT)
        await title_el.click()
        await title_el.fill(title)
        logger.info("Reddit: filled title: %s", title[:60])
        await human_delay(1, 2)

        # ── Fill body if provided ──
        if body and body.strip():
            try:
                # Lexical editor is inside shadow DOM — focus it via JS then type
                focused = await page.evaluate('''() => {
                    // Search through all shadow roots for the contenteditable
                    function findInShadow(root) {
                        const el = root.querySelector('div[contenteditable="true"][data-lexical-editor="true"]');
                        if (el) return el;
                        for (const child of root.querySelectorAll('*')) {
                            if (child.shadowRoot) {
                                const found = findInShadow(child.shadowRoot);
                                if (found) return found;
                            }
                        }
                        return null;
                    }
                    const editor = findInShadow(document);
                    if (editor) {
                        editor.focus();
                        return true;
                    }
                    return false;
                }''')
                if focused:
                    await human_delay(0.3, 0.5)
                    await page.keyboard.type(body, delay=random.randint(20, 50))
                    logger.info("Reddit: filled body text via JS focus")
                else:
                    logger.info("Reddit: Lexical editor not found in shadow DOM")
            except Exception as e:
                logger.info("Reddit: body field not available: %s", e)
        await human_delay(1, 3)

        # ── Click Post button ──
        post_btn = page.locator('button:has-text("Post")').last
        await post_btn.wait_for(state="visible", timeout=COMPOSE_TIMEOUT)
        # Wait for button to become enabled (image may still be uploading)
        for _ in range(15):
            if await post_btn.is_enabled():
                break
            logger.info("Reddit: waiting for Post button to enable...")
            await page.wait_for_timeout(1000)
        await post_btn.click()
        logger.info("Reddit: clicked Post")

        # Wait for redirect — Reddit goes to /submitted/?created=t3_XXXXX
        post_url = None
        try:
            await page.wait_for_url("**/submitted/**created=**", timeout=20000)
            current = page.url
            logger.info("Reddit: redirected to: %s", current)
            # Extract post ID from ?created=t3_XXXXX query param
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(current).query)
            created = qs.get("created", [None])[0]  # e.g., "t3_1s9nt35"
            if created and created.startswith("t3_"):
                post_id = created[3:]  # strip "t3_" prefix
                post_url = f"https://www.reddit.com/user/{username}/comments/{post_id}/"
                logger.info("Reddit: constructed post URL: %s", post_url)
        except Exception:
            # Fallback: poll for URL change
            for attempt in range(8):
                current = page.url
                if "/comments/" in current:
                    post_url = current
                    break
                if "created=" in current:
                    from urllib.parse import urlparse, parse_qs
                    qs = parse_qs(urlparse(current).query)
                    created = qs.get("created", [None])[0]
                    if created and created.startswith("t3_"):
                        post_url = f"https://www.reddit.com/user/{username}/comments/{created[3:]}/"
                        break
                await page.wait_for_timeout(2000)

        # Post-post browsing
        await page.goto(PLATFORMS["reddit"]["home_url"], timeout=PAGE_LOAD_TIMEOUT)
        await browse_feed(page, "reddit")

        logger.info("Successfully posted to Reddit (u/%s)", username)
        return post_url or f"https://reddit.com/user/{username}/submitted"

    except Exception as e:
        logger.error("Failed to post to Reddit: %s", e, exc_info=True)
        return None
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
        tiktok_content = draft["content"]["tiktok"]
        if isinstance(tiktok_content, str):
            caption = tiktok_content
            image_text = tiktok_content[:100]
        else:
            caption = tiktok_content["caption"]
            image_text = tiktok_content["image_text"]

        # Generate a short video from the branded image
        # Note: generate_tiktok_video was in the now-missing image_generator.py.
        # TikTok is disabled in platforms.json — this code is preserved but non-functional.
        video_path = ROOT / "drafts" / "pending" / f"tiktok-{draft.get('id', 'temp')}.mp4"
        try:
            from utils.image_generator import generate_tiktok_video
            generate_tiktok_video(image_text, video_path)
        except ImportError:
            logger.error("TikTok: image_generator module not available")
            return False
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
        # Note: generate_instagram_image was in the now-missing image_generator.py.
        # Instagram is disabled — this code is preserved but non-functional.
        try:
            from utils.image_generator import generate_instagram_image
        except ImportError:
            logger.error("Instagram: image_generator module not available")
            return False

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

# Legacy poster functions — used as fallback when JSON scripts don't exist or fail
_LEGACY_PLATFORM_POSTERS = {
    "x": post_to_x,
    "linkedin": post_to_linkedin,
    "facebook": post_to_facebook,
    "instagram": post_to_instagram,
    "reddit": post_to_reddit,
    "tiktok": post_to_tiktok,
}

# Unified poster dict — uses post_to_platform() which tries script-driven first
# Keeping this dict for backward compatibility with existing callers
PLATFORM_POSTERS = _LEGACY_PLATFORM_POSTERS.copy()

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
    parser = argparse.ArgumentParser(description="Amplifier: post drafts to social platforms")
    parser.add_argument("--slot", type=int, choices=range(1, 7), default=None,
                        help="Posting slot (1-6). Auto-detects from current IST time if omitted.")
    args = parser.parse_args()

    slot = args.slot if args.slot else _auto_detect_slot()
    platforms_for_slot = get_slot_platforms(slot)

    logger.info("=== Amplifier started (slot %d) ===", slot)
    logger.info("Platforms for slot %d today: %s", slot, platforms_for_slot or "(none)")

    if not platforms_for_slot:
        logger.info("No platforms to post to for slot %d today. Exiting.", slot)
        return

    draft = get_next_draft(slot=slot)
    if draft is None:
        logger.warning("No pending drafts for slot %d. Exiting.", slot)
        return

    logger.info("Processing draft: %s (topic: %s)", draft.get("id"), draft.get("topic"))

    # If draft specifies target platforms, intersect with slot platforms
    draft_platforms = draft.get("platforms")
    if draft_platforms:
        platforms_for_slot = [p for p in platforms_for_slot if p in draft_platforms]
        if not platforms_for_slot:
            logger.warning(
                "Draft targets %s but slot %d has %s today. No overlap — skipping.",
                draft_platforms, slot, get_slot_platforms(slot),
            )
            return
        logger.info("Filtered to draft's target platforms: %s", platforms_for_slot)

    # Randomize order within slot
    random.shuffle(platforms_for_slot)
    logger.info("Posting order: %s", platforms_for_slot)

    from playwright.async_api import async_playwright

    results = {}
    retry_results = {}
    async with async_playwright() as pw:
        for i, platform in enumerate(platforms_for_slot):
            if platform not in PLATFORM_POSTERS:
                logger.warning("No poster function for %s, skipping", platform)
                continue
            logger.info("Posting to %s...", platform)
            poster = PLATFORM_POSTERS[platform]
            success = await poster(draft, pw)
            results[platform] = success

            # Retry once on failure after RETRY_DELAY_SEC
            if not success:
                logger.warning(
                    "%s failed. Retrying in %d seconds...", platform, RETRY_DELAY_SEC
                )
                await asyncio.sleep(RETRY_DELAY_SEC)
                logger.info("Retrying %s (attempt 2)...", platform)
                retry_success = await poster(draft, pw)
                retry_results[platform] = retry_success
                if retry_success:
                    results[platform] = True
                    logger.info("Retry succeeded for %s", platform)
                else:
                    logger.error("Retry also failed for %s", platform)

            # Wait between platforms (not after last one)
            if i < len(platforms_for_slot) - 1:
                wait = random.uniform(POST_INTERVAL_MIN, POST_INTERVAL_MAX)
                logger.info("Waiting %.0f seconds before next platform...", wait)
                await asyncio.sleep(wait)

    succeeded = [p for p, ok in results.items() if ok]
    failed = [p for p, ok in results.items() if not ok]

    # Track retry info on the draft
    if retry_results:
        draft["retry_count"] = draft.get("retry_count", 0) + 1
        draft["retried_platforms"] = {
            p: "success" if ok else "failed" for p, ok in retry_results.items()
        }

    if succeeded:
        mark_posted(draft, succeeded)
        if failed:
            logger.warning("Partial success. Failed platforms (after retry): %s", failed)
    else:
        errors = ", ".join(f"{p}: failed (after retry)" for p in failed)
        mark_failed(draft, f"All platforms failed: {errors}")

    logger.info("=== Amplifier finished (slot %d) ===", slot)


if __name__ == "__main__":
    asyncio.run(main())
