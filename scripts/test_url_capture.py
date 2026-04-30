"""Test URL capture selectors for all 4 platforms.

Launches each platform's persistent browser profile, navigates to the
profile/activity page where URL extraction happens after posting, and
tests whether the CSS selectors from the JSON scripts can find post URLs.

Usage:
    python scripts/test_url_capture.py
    python scripts/test_url_capture.py --platform linkedin
"""

import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

with open(ROOT / "config" / "platforms.json", "r", encoding="utf-8") as f:
    PLATFORMS = json.load(f)


async def launch_context(pw, platform: str):
    profile_dir = ROOT / "profiles" / f"{platform}-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    kwargs = dict(
        user_data_dir=str(profile_dir),
        headless=False,
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36"
        ),
        args=["--no-sandbox"],
    )
    proxy_url = PLATFORMS.get(platform, {}).get("proxy")
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}
    return await pw.chromium.launch_persistent_context(**kwargs)


async def test_selectors(page, selectors: list[dict], label: str) -> str | None:
    """Try each selector, report what matches."""
    for sel in selectors:
        by = sel["by"]
        val = sel["value"]
        try:
            if by == "css":
                loc = page.locator(val).first
            elif by == "text":
                loc = page.get_by_text(val).first
            else:
                continue

            visible = await loc.is_visible(timeout=3000)
            if visible:
                href = await loc.get_attribute("href")
                log.info("    [MATCH] %s=%s → href=%s", by, val, href)
                return href
            else:
                log.info("    [MISS]  %s=%s (not visible)", by, val)
        except Exception as e:
            log.info("    [MISS]  %s=%s (%s)", by, val, str(e)[:80])
    return None


async def test_js(page, js_code: str, label: str) -> str | None:
    """Run JavaScript and report result."""
    try:
        result = await page.evaluate(js_code)
        if result and isinstance(result, str) and result.startswith("http"):
            log.info("    [JS OK] %s → %s", label, result)
            return result
        else:
            log.info("    [JS MISS] %s → %s", label, result)
            return None
    except Exception as e:
        log.info("    [JS ERR] %s → %s", label, str(e)[:80])
        return None


async def test_x(pw):
    log.info("\n" + "=" * 60)
    log.info("TESTING X (Twitter)")
    log.info("=" * 60)

    ctx = await launch_context(pw, "x")
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    try:
        # Get username
        await page.goto("https://x.com/home", timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        username = await page.evaluate(
            "() => { const link = document.querySelector('a[data-testid=\"AppTabBar_Profile_Link\"]'); "
            "return link ? link.getAttribute('href').replace('/', '') : ''; }"
        )
        log.info("  Username: %s", username)

        if username:
            await page.goto(f"https://x.com/{username}", timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            log.info("  Testing CSS selectors on profile page:")
            css_result = await test_selectors(page, [
                {"by": "css", "value": "article[data-testid='tweet'] a[href*='/status/']"},
                {"by": "css", "value": "a[href*='/status/']"},
            ], "X profile")

            log.info("  Testing JS extraction:")
            js_result = await test_js(page,
                "() => { const link = document.querySelector(\"article[data-testid='tweet'] a[href*='/status/']\"); "
                "return link ? link.href : null; }",
                "X JS")

            final = css_result or js_result
            log.info("  RESULT: %s", final or "NO URL FOUND")
        else:
            log.info("  RESULT: Could not get username (not logged in?)")
    finally:
        await ctx.close()


async def test_linkedin(pw):
    log.info("\n" + "=" * 60)
    log.info("TESTING LINKEDIN")
    log.info("=" * 60)

    ctx = await launch_context(pw, "linkedin")
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    try:
        # Step 1: Test "View post" dialog selectors (would appear right after posting)
        log.info("  Skipping dialog test (only appears after posting)")

        # Step 2: Test activity page extraction
        log.info("  Navigating to recent activity page...")
        await page.goto("https://www.linkedin.com/in/me/recent-activity/all/",
                        timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        log.info("  Testing CSS selectors on activity page:")
        css_result = await test_selectors(page, [
            {"by": "css", "value": "a[href*='/feed/update/']"},
            {"by": "css", "value": "a[href*='/activity/']"},
        ], "LinkedIn activity")

        log.info("  Testing JS extraction:")
        js_result = await test_js(page,
            "() => { "
            "const links = document.querySelectorAll('a[href*=\"/feed/update/\"]'); "
            "if (links.length > 0) return links[0].href; "
            "const all = document.querySelectorAll('a[href]'); "
            "for (const a of all) { if (a.href.includes('urn:li:activity:')) return a.href; } "
            "return null; }",
            "LinkedIn JS")

        # Also dump what links are actually on the page
        log.info("  Scanning all links containing 'feed' or 'activity':")
        links = await page.evaluate(
            "() => { const all = document.querySelectorAll('a[href]'); "
            "const results = []; "
            "for (const a of all) { "
            "  if (a.href.includes('/feed/') || a.href.includes('/activity/')) "
            "    results.push(a.href.substring(0, 120)); "
            "} return results.slice(0, 10); }"
        )
        for link in (links or []):
            log.info("    → %s", link)

        final = css_result or js_result
        log.info("  RESULT: %s", final or "NO URL FOUND")
    finally:
        await ctx.close()


async def test_facebook(pw):
    log.info("\n" + "=" * 60)
    log.info("TESTING FACEBOOK")
    log.info("=" * 60)

    ctx = await launch_context(pw, "facebook")
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    try:
        log.info("  Navigating to profile...")
        await page.goto("https://www.facebook.com/me", timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # Scroll down to load posts
        await page.mouse.wheel(0, 800)
        await asyncio.sleep(2)

        log.info("  Testing CSS selectors on profile page:")
        css_result = await test_selectors(page, [
            {"by": "css", "value": "a[href*='/posts/']:not([href*='comment'])"},
            {"by": "css", "value": "a[href*='story_fbid=']:not([href*='comment_id'])"},
            {"by": "css", "value": "a[href*='/permalink/']:not([href*='comment'])"},
        ], "Facebook profile")

        log.info("  Testing JS extraction:")
        js_result = await test_js(page,
            "() => { "
            "const links = document.querySelectorAll('a[href]'); "
            "for (const link of links) { "
            "  const h = link.href; "
            "  if (h.includes('comment')) continue; "
            "  if (h.includes('/posts/') || h.includes('story_fbid') || "
            "      h.includes('/permalink') || h.includes('pfbid')) return h; "
            "} return null; }",
            "Facebook JS")

        # Dump candidate links
        log.info("  Scanning all links with post-like patterns:")
        links = await page.evaluate(
            "() => { const all = document.querySelectorAll('a[href]'); "
            "const results = []; "
            "for (const a of all) { "
            "  const h = a.href; "
            "  if (h.includes('/posts/') || h.includes('story_fbid') || "
            "      h.includes('pfbid') || h.includes('/permalink')) "
            "    results.push(h.substring(0, 150)); "
            "} return results.slice(0, 10); }"
        )
        for link in (links or []):
            log.info("    → %s", link)

        if not links:
            log.info("  No post-pattern links found. Dumping timestamp-like links:")
            ts_links = await page.evaluate(
                "() => { const all = document.querySelectorAll('a[href]'); "
                "const results = []; "
                "for (const a of all) { "
                "  const txt = a.textContent.trim(); "
                "  if (txt.match(/^\\d+[hmd]$|^\\w+ \\d+|^Yesterday|^Just now/)) "
                "    results.push({text: txt, href: a.href.substring(0, 150)}); "
                "} return results.slice(0, 10); }"
            )
            for item in (ts_links or []):
                log.info("    → [%s] %s", item.get("text"), item.get("href"))

        final = css_result or js_result
        log.info("  RESULT: %s", final or "NO URL FOUND")
    finally:
        await ctx.close()


async def test_reddit(pw):
    log.info("\n" + "=" * 60)
    log.info("TESTING REDDIT")
    log.info("=" * 60)

    ctx = await launch_context(pw, "reddit")
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    try:
        # Get username
        log.info("  Getting username...")
        await page.goto("https://www.reddit.com/user/me/", timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(5)
        user_match = re.search(r'/user/([^/]+)', page.url)
        username = user_match.group(1) if user_match and user_match.group(1).lower() != "me" else ""
        log.info("  Username: %s", username or "(not found)")

        if username:
            log.info("  Navigating to submitted posts...")
            await page.goto(f"https://www.reddit.com/user/{username}/submitted/",
                            timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(5)

            log.info("  Testing CSS selectors on submitted page:")
            css_result = await test_selectors(page, [
                {"by": "css", "value": "a[href*='/comments/']"},
                {"by": "css", "value": "shreddit-post a[slot='full-post-link']"},
                {"by": "css", "value": "a[data-click-id='body']"},
            ], "Reddit submitted")

            log.info("  Testing JS extraction:")
            js_result = await test_js(page,
                "() => { "
                "const links = document.querySelectorAll('a[href*=\"/comments/\"]'); "
                "if (links.length > 0) return links[0].href; "
                "const posts = document.querySelectorAll('shreddit-post'); "
                "if (posts.length > 0) { "
                "  const pl = posts[0].getAttribute('permalink'); "
                "  if (pl) return pl.startsWith('http') ? pl : 'https://www.reddit.com' + pl; "
                "} return null; }",
                "Reddit JS")

            # Dump what's on the page
            log.info("  Scanning shreddit-post permalink attributes:")
            permalinks = await page.evaluate(
                "() => { const posts = document.querySelectorAll('shreddit-post'); "
                "return Array.from(posts).slice(0, 5).map(p => p.getAttribute('permalink')); }"
            )
            for pl in (permalinks or []):
                log.info("    → %s", pl)

            final = css_result or js_result
            log.info("  RESULT: %s", final or "NO URL FOUND")
        else:
            log.info("  RESULT: Could not get username (not logged in?)")
    finally:
        await ctx.close()


async def main():
    from patchright.async_api import async_playwright

    target = None
    if "--platform" in sys.argv:
        idx = sys.argv.index("--platform")
        if idx + 1 < len(sys.argv):
            target = sys.argv[idx + 1].lower()

    async with async_playwright() as pw:
        platforms = {
            "x": test_x,
            "linkedin": test_linkedin,
            "facebook": test_facebook,
            "reddit": test_reddit,
        }

        if target:
            if target in platforms:
                await platforms[target](pw)
            else:
                log.error("Unknown platform: %s", target)
        else:
            for name, func in platforms.items():
                try:
                    await func(pw)
                except Exception as e:
                    log.error("\n  %s FAILED: %s", name.upper(), e)

    log.info("\n" + "=" * 60)
    log.info("TEST COMPLETE")
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
