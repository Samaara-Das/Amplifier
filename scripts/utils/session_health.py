"""Session health monitoring — checks if browser sessions for each platform are valid.

Launches headless browser with the platform's persistent profile, navigates to the
home/feed URL, and looks for authenticated elements (green) vs login page (red).
If neither is confirmed, returns yellow.

Results are cached in local_db settings under key "session_health".
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.local_db import get_setting, set_setting

logger = logging.getLogger(__name__)

# Load platform config
with open(ROOT / "config" / "platforms.json", "r", encoding="utf-8") as f:
    PLATFORMS = json.load(f)


# ── Platform-Specific Selectors ──────────────────────────────────
# Auth selectors: if ANY of these exist on the page, the user is logged in.
# Login indicators: if ANY of these exist, the session has expired.

PLATFORM_AUTH_SELECTORS: dict[str, list[str]] = {
    "x": [
        'a[data-testid="SideNav_NewTweet_Button"]',       # Compose button in sidebar
        'a[data-testid="AppTabBar_Profile_Link"]',         # Profile tab in nav
        '[data-testid="primaryColumn"]',                    # Main feed column (logged-in only)
    ],
    "linkedin": [
        'div.feed-identity-module',                         # Profile card in left sidebar
        'button.share-box-feed-entry__trigger',             # "Start a post" button
        'img.global-nav__me-photo',                         # Profile icon in top nav
        '.feed-shared-update-v2',                           # Feed posts (only visible when logged in)
    ],
    "facebook": [
        '[aria-label="Create a post"]',                     # Composer area
        '[aria-label="Your profile"]',                      # Profile link in nav
        '[role="navigation"] [data-testid="Keychain"]',     # Nav bar with user elements
        'div[role="feed"]',                                 # Main feed (only visible when logged in)
    ],
    "reddit": [
        '[data-testid="create-post"]',                      # Create post button
        'button[aria-label="Open chat"]',                   # Chat button (logged-in only)
        'faceplate-tracker[noun="user_menu"]',              # User menu in header
        '#USER_DROPDOWN_ID',                                # User dropdown (old Reddit)
    ],
}

PLATFORM_LOGIN_INDICATORS: dict[str, list[str]] = {
    "x": [
        '[data-testid="loginButton"]',                      # Login button on X
        'input[name="text"][autocomplete="username"]',      # Username input on login form
        'a[href="/login"]',                                 # Login link
    ],
    "linkedin": [
        'form.login__form',                                 # LinkedIn login form
        'input#username',                                   # Email input on login page
        '.sign-in-form__sign-in-cta',                       # Sign in CTA button
    ],
    "facebook": [
        'input[name="email"]',                              # Email input on login page
        'button[name="login"]',                             # Login button
        '#loginbutton',                                     # Alternative login button ID
    ],
    "reddit": [
        'input[name="username"]',                           # Username input on login
        'a[href="https://www.reddit.com/login/"]',          # Login link
        'faceplate-tracker[noun="login"]',                  # Login tracker element
    ],
}

# Timeout for waiting on selectors during session check (ms)
CHECK_TIMEOUT_MS = 8000
PAGE_LOAD_TIMEOUT_MS = 20000


# ── Browser Launch ───────────────────────────────────────────────


async def _launch_context(pw, platform: str, headless: bool = True):
    """Launch persistent browser context (same pattern as post.py / profile_scraper.py)."""
    profile_dir = ROOT / "profiles" / f"{platform}-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    kwargs = dict(
        user_data_dir=str(profile_dir),
        headless=headless,
        viewport={"width": 1280, "height": 800},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )

    proxy_url = PLATFORMS.get(platform, {}).get("proxy")
    if proxy_url:
        logger.info("Using proxy for %s: %s", platform, proxy_url)
        kwargs["proxy"] = {"server": proxy_url}

    return await pw.chromium.launch_persistent_context(**kwargs)


# ── Single Platform Check ────────────────────────────────────────


async def check_session(platform: str, playwright) -> dict:
    """Check if the browser session for a platform is still valid.

    Launches headless persistent context, navigates to home URL,
    checks for authenticated elements vs login page indicators.

    Returns:
        {
            "platform": str,
            "status": "green" | "yellow" | "red",
            "details": str,
        }
    """
    result = {
        "platform": platform,
        "status": "yellow",
        "details": "Check not completed",
    }

    context = None
    try:
        context = await _launch_context(playwright, platform, headless=True)
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to platform home URL
        home_url = PLATFORMS.get(platform, {}).get("home_url", "")
        if not home_url:
            result["details"] = f"No home_url configured for {platform}"
            return result

        logger.info("Session check %s: navigating to %s", platform, home_url)
        await page.goto(home_url, wait_until="domcontentloaded",
                        timeout=PAGE_LOAD_TIMEOUT_MS)
        await page.wait_for_timeout(3000)  # Let page settle

        # Check for authenticated elements
        auth_selectors = PLATFORM_AUTH_SELECTORS.get(platform, [])
        login_selectors = PLATFORM_LOGIN_INDICATORS.get(platform, [])

        auth_found = False
        login_found = False

        # Check auth selectors — any one match = logged in
        for selector in auth_selectors:
            try:
                locator = page.locator(selector)
                if await locator.count() > 0:
                    auth_found = True
                    logger.info("Session check %s: auth element found (%s)",
                                platform, selector)
                    break
            except Exception:
                continue

        # Check login indicators — any one match = session expired
        for selector in login_selectors:
            try:
                locator = page.locator(selector)
                if await locator.count() > 0:
                    login_found = True
                    logger.info("Session check %s: login indicator found (%s)",
                                platform, selector)
                    break
            except Exception:
                continue

        # Determine status
        if auth_found and not login_found:
            result["status"] = "green"
            result["details"] = f"Session authenticated — logged in to {platform}"
        elif login_found and not auth_found:
            result["status"] = "red"
            result["details"] = f"Session expired — {platform} login page detected"
        elif auth_found and login_found:
            # Unlikely but possible — treat as green (auth takes precedence)
            result["status"] = "green"
            result["details"] = (
                f"Session authenticated — logged in to {platform} "
                f"(login elements also detected, possibly part of page layout)"
            )
        else:
            # Neither found — uncertain state
            result["status"] = "yellow"
            result["details"] = (
                f"Could not confirm session state for {platform} — "
                f"page loaded but no auth or login elements detected"
            )

    except Exception as e:
        logger.error("Session check %s failed: %s", platform, e)
        result["status"] = "yellow"
        result["details"] = f"Session check error for {platform}: {e}"
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass

    return result


# ── Check All Platforms ──────────────────────────────────────────


async def check_all_sessions() -> dict:
    """Check sessions for all connected platforms (those with profile directories).

    Runs checks sequentially (not parallel) to avoid resource contention.
    Stores results in local_db settings under key "session_health".

    Returns:
        {platform: {"status": ..., "details": ..., "checked_at": ...}}
    """
    profiles_dir = ROOT / "profiles"
    results = {}

    # Discover which platforms have profile directories
    connected_platforms = []
    for platform in PLATFORMS:
        profile_path = profiles_dir / f"{platform}-profile"
        if profile_path.exists() and profile_path.is_dir():
            connected_platforms.append(platform)

    if not connected_platforms:
        logger.info("No connected platform profiles found")
        return results

    logger.info("Checking sessions for: %s", ", ".join(connected_platforms))

    async with async_playwright() as pw:
        for platform in connected_platforms:
            try:
                check_result = await check_session(platform, pw)
                now = datetime.now(timezone.utc).isoformat()
                results[platform] = {
                    "status": check_result["status"],
                    "details": check_result["details"],
                    "checked_at": now,
                }
            except Exception as e:
                logger.error("Session check for %s crashed: %s", platform, e)
                results[platform] = {
                    "status": "yellow",
                    "details": f"Check failed: {e}",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }

    # Persist to local_db
    try:
        set_setting("session_health", json.dumps(results))
        logger.info("Session health stored: %s",
                     {p: r["status"] for p, r in results.items()})
    except Exception as e:
        logger.error("Failed to store session health: %s", e)

    return results


# ── Health Storage ───────────────────────────────────────────────


def get_session_health() -> dict:
    """Read cached session health from local_db settings.

    Returns:
        {platform: {"status": ..., "details": ..., "checked_at": ...}}
        Empty dict if no data stored.
    """
    raw = get_setting("session_health")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def update_session_health(platform: str, status: str, details: str) -> None:
    """Update session health for a single platform.

    Merges with existing data (preserves other platforms).
    """
    current = get_session_health()
    current[platform] = {
        "status": status,
        "details": details,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    set_setting("session_health", json.dumps(current))


# ── Re-Authentication ────────────────────────────────────────────


async def reauthenticate_platform(platform: str) -> dict:
    """Open a visible browser window for the user to manually re-login.

    Same pattern as login_setup.py but callable from the app.
    After the user closes the browser, re-checks session health.

    Returns the session check result after re-auth.
    """
    result = {
        "platform": platform,
        "status": "yellow",
        "details": "Re-authentication not completed",
    }

    try:
        async with async_playwright() as pw:
            profile_dir = ROOT / "profiles" / f"{platform}-profile"
            profile_dir.mkdir(parents=True, exist_ok=True)

            home_url = PLATFORMS.get(platform, {}).get("home_url", "")

            kwargs = dict(
                user_data_dir=str(profile_dir),
                headless=False,  # Visible for manual login
                viewport={"width": 1280, "height": 800},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )

            proxy_url = PLATFORMS.get(platform, {}).get("proxy")
            if proxy_url:
                kwargs["proxy"] = {"server": proxy_url}

            logger.info("Re-auth %s: opening visible browser to %s", platform, home_url)

            context = await pw.chromium.launch_persistent_context(**kwargs)
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(home_url)

            # Wait for user to close the browser
            logger.info("Re-auth %s: waiting for user to log in and close browser...",
                        platform)
            try:
                await page.wait_for_event("close", timeout=0)
                await asyncio.sleep(1)
            except Exception:
                pass

            try:
                await context.close()
            except Exception:
                pass

            # Re-check session health
            logger.info("Re-auth %s: re-checking session health...", platform)
            result = await check_session(platform, pw)

            # Update stored health
            update_session_health(platform, result["status"], result["details"])

    except Exception as e:
        logger.error("Re-auth %s failed: %s", platform, e)
        result = {
            "platform": platform,
            "status": "yellow",
            "details": f"Re-authentication failed: {e}",
        }

    return result


# ── CLI Entry Point ──────────────────────────────────────────────


async def _main():
    """Run session health checks for all connected platforms."""
    import argparse

    parser = argparse.ArgumentParser(description="Check social media session health")
    parser.add_argument(
        "--platform", type=str, default=None,
        help="Check specific platform (default: all connected)",
    )
    parser.add_argument(
        "--reauth", action="store_true",
        help="Open visible browser for re-authentication",
    )
    args = parser.parse_args()

    if args.reauth and args.platform:
        print(f"\nRe-authenticating {args.platform}...")
        result = await reauthenticate_platform(args.platform)
        print(f"  {result['platform']}: {result['status']} — {result['details']}")
        return

    if args.platform:
        # Check single platform
        async with async_playwright() as pw:
            result = await check_session(args.platform, pw)
            update_session_health(args.platform, result["status"], result["details"])
            print(f"  {result['platform']}: {result['status']} — {result['details']}")
    else:
        # Check all
        results = await check_all_sessions()
        if not results:
            print("  No connected platforms found (no profile directories)")
        for platform, data in results.items():
            status_emoji = {"green": "[OK]", "yellow": "[??]", "red": "[!!]"}
            print(f"  {status_emoji.get(data['status'], '[??]')} "
                  f"{platform}: {data['status']} — {data['details']}")


if __name__ == "__main__":
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(ROOT / "logs" / "session_health.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    asyncio.run(_main())
