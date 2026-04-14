"""Profile scraper — extracts user profile data from connected social media platforms.

Uses Playwright with persistent browser profiles (same sessions as posting).
Runs headlessly. Each platform scraper extracts follower counts, bio, recent posts,
and engagement metrics. Results are stored in local DB and synced to server.

Scraping triggers:
- On platform connect (during onboarding)
- Weekly refresh (background agent)
- Manual refresh (user clicks Refresh in Settings)
"""

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from playwright.async_api import async_playwright, Page, BrowserContext

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.local_db import (
    upsert_scraped_profile,
    get_scraped_profile,
    get_all_scraped_profiles,
)

logger = logging.getLogger(__name__)

# Load platform config
with open(ROOT / "config" / "platforms.json", "r", encoding="utf-8") as f:
    PLATFORMS = json.load(f)


# ── Browser Launch ────────────────────────────────────────────────


# Stealth args to bypass headless detection (Reddit, etc.)
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--disable-browser-side-navigation",
    "--disable-gpu",
    "--lang=en-US,en",
]

# Script injected into every page to hide automation fingerprints
STEALTH_INIT_SCRIPT = 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'


    # Platforms that block headless browsers entirely — must run headed
_HEADED_PLATFORMS = {"reddit"}


async def _launch_context(pw, platform: str) -> BrowserContext:
    """Launch persistent browser context for scraping (reuses posting profiles).

    Most platforms run headless. Reddit blocks headless entirely ("blocked by
    network security"), so it runs headed (visible browser window).
    """
    profile_dir = ROOT / "profiles" / f"{platform}-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    use_headless = platform not in _HEADED_PLATFORMS

    kwargs = dict(
        user_data_dir=str(profile_dir),
        headless=use_headless,
        viewport={"width": 1280, "height": 800},
        args=STEALTH_ARGS,
    )

    proxy_url = PLATFORMS.get(platform, {}).get("proxy")
    if proxy_url:
        logger.info("Using proxy for %s: %s", platform, proxy_url)
        kwargs["proxy"] = {"server": proxy_url}

    context = await pw.chromium.launch_persistent_context(**kwargs)

    # Inject stealth script to hide navigator.webdriver
    for page in context.pages:
        await page.add_init_script(STEALTH_INIT_SCRIPT)
    context.on("page", lambda page: page.add_init_script(STEALTH_INIT_SCRIPT))

    return context


# ── Helpers ───────────────────────────────────────────────────────


def _parse_number(text: str) -> int:
    """Extract first number from text like '1,234 followers' or '1.2K'."""
    if not text:
        return 0
    text = text.strip()

    # Handle abbreviated numbers (1.2K, 3.4M, etc.)
    abbr_match = re.search(r'([\d,.]+)\s*([KkMm])?', text)
    if abbr_match:
        num_str = abbr_match.group(1).replace(",", "")
        suffix = abbr_match.group(2)
        try:
            value = float(num_str)
            if suffix and suffix.upper() == "K":
                value *= 1000
            elif suffix and suffix.upper() == "M":
                value *= 1_000_000
            return int(value)
        except ValueError:
            pass

    # Fallback: extract raw digits
    numbers = re.findall(r'[\d,]+', text)
    if numbers:
        return int(numbers[0].replace(",", ""))
    return 0


async def _safe_text(locator, timeout: int = 5000) -> str | None:
    """Safely get inner text from a locator with timeout."""
    try:
        if await locator.count() > 0:
            await locator.first.wait_for(state="visible", timeout=timeout)
            return (await locator.first.inner_text()).strip()
    except Exception:
        pass
    return None


async def _safe_attr(locator, attr: str, timeout: int = 5000) -> str | None:
    """Safely get an attribute from a locator with timeout."""
    try:
        if await locator.count() > 0:
            await locator.first.wait_for(state="visible", timeout=timeout)
            return await locator.first.get_attribute(attr)
    except Exception:
        pass
    return None


# ── Tab Navigation & Expand Buttons (Spec: 3-tier pipeline prep) ─


async def _click_expand_buttons(page: Page, platform: str):
    """Click all expand/show-more buttons to reveal hidden content.

    Each platform hides content behind different expand triggers.
    Must be called BEFORE text extraction to capture full profile data.
    """
    expand_selectors = {
        "x": [],  # X uses infinite scroll, no expand buttons
        "linkedin": [
            # Only click buttons that toggle content in-place.
            # Do NOT click <a> "Show all" links — they navigate away from
            # the profile page, breaking subsequent text extraction.
            # Experience/education/skills are scraped via dedicated navigation.
            'button:has-text("…more")',
            'button:has-text("...more")',
            'button:has-text("see more")',
        ],
        "facebook": [
            'div[role="button"]:has-text("See more")',
            'span:has-text("See more")',
            'div[role="button"]:has-text("See More")',
        ],
        "reddit": [],  # Reddit loads content on tab click
    }

    selectors = expand_selectors.get(platform, [])
    clicked = 0
    for sel in selectors:
        try:
            buttons = page.locator(sel)
            count = await buttons.count()
            for i in range(min(count, 5)):  # Cap at 5 clicks per selector
                try:
                    await buttons.nth(i).click(timeout=3000)
                    await page.wait_for_timeout(800)
                    clicked += 1
                except Exception:
                    pass
        except Exception:
            pass

    if clicked:
        logger.info("%s: clicked %d expand buttons", platform, clicked)


async def _navigate_tabs_and_collect_text(page: Page, platform: str) -> str:
    """Navigate platform tabs, click expand buttons, collect all text.

    Returns concatenated text from all visited tabs/sections.
    This is the core of Tier 1 — gathering as much text as possible
    before sending to the AI for structured extraction.
    """
    all_text_parts = []

    # Step 1: Click expand buttons on the initial page
    await _click_expand_buttons(page, platform)

    # Step 2: Extract text from current page
    try:
        initial_text = await page.inner_text("body", timeout=10000)
        all_text_parts.append(f"=== {platform.upper()} PROFILE (main page) ===\n{initial_text}")
    except Exception as e:
        logger.warning("%s: failed to extract initial page text: %s", platform, e)

    # Step 3: Scroll down to load below-fold content
    for _ in range(3):
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await page.wait_for_timeout(1500)

    # Click any newly-visible expand buttons
    await _click_expand_buttons(page, platform)

    # Re-extract text after scrolling (captures loaded content)
    try:
        scrolled_text = await page.inner_text("body", timeout=10000)
        if scrolled_text and len(scrolled_text) > len(all_text_parts[0]) + 200:
            all_text_parts[0] = f"=== {platform.upper()} PROFILE (after scroll) ===\n{scrolled_text}"
    except Exception:
        pass

    # Step 4: Platform-specific tab navigation
    if platform == "x":
        await _navigate_x_tabs(page, all_text_parts)
    elif platform == "linkedin":
        await _navigate_linkedin_tabs(page, all_text_parts)
    elif platform == "facebook":
        await _navigate_facebook_tabs(page, all_text_parts)
    elif platform == "reddit":
        await _navigate_reddit_tabs(page, all_text_parts)

    combined = "\n\n".join(all_text_parts)
    logger.info("%s: collected %d chars of text from %d section(s)",
                platform, len(combined), len(all_text_parts))
    return combined


async def _navigate_x_tabs(page: Page, text_parts: list):
    """Navigate X profile tabs: Media (for count), Highlights."""
    profile_url = page.url

    # Media tab — get media count
    try:
        media_tab = page.locator('a[role="tab"]:has-text("Media")')
        if await media_tab.count() > 0:
            await media_tab.first.click(timeout=5000)
            await page.wait_for_timeout(2000)
            media_text = await page.inner_text("body", timeout=5000)
            text_parts.append(f"=== X MEDIA TAB ===\n{media_text[:2000]}")
    except Exception as e:
        logger.debug("X: media tab navigation failed: %s", e)

    # Back to profile
    try:
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
    except Exception:
        pass


async def _navigate_linkedin_tabs(page: Page, text_parts: list):
    """Navigate LinkedIn sections: Activity/Posts tab for recent posts."""
    # Click "Posts" tab in Activity section if visible
    try:
        posts_tab = page.locator('button:has-text("Posts")')
        if await posts_tab.count() > 0:
            await posts_tab.first.click(timeout=5000)
            await page.wait_for_timeout(2000)
            # Scroll the activity section
            await page.evaluate("window.scrollBy(0, 600)")
            await page.wait_for_timeout(1000)
    except Exception as e:
        logger.debug("LinkedIn: posts tab click failed: %s", e)


async def _navigate_facebook_tabs(page: Page, text_parts: list):
    """Navigate Facebook tabs: About (for detailed info)."""
    profile_url = page.url

    # Click About tab
    try:
        about_tab = page.locator('a:has-text("About")')
        if await about_tab.count() > 0:
            await about_tab.first.click(timeout=5000)
            await page.wait_for_timeout(2000)
            about_text = await page.inner_text("body", timeout=10000)
            text_parts.append(f"=== FACEBOOK ABOUT TAB ===\n{about_text[:3000]}")
    except Exception as e:
        logger.debug("Facebook: about tab navigation failed: %s", e)

    # Go back to main profile
    try:
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
    except Exception:
        pass


async def _navigate_reddit_tabs(page: Page, text_parts: list):
    """Navigate Reddit tabs: Posts, Comments."""
    profile_url = page.url

    # Click Posts tab
    try:
        posts_tab = page.locator('a:has-text("Posts"), button:has-text("Posts")')
        if await posts_tab.count() > 0:
            await posts_tab.first.click(timeout=5000)
            await page.wait_for_timeout(2000)
            # Scroll to load posts
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(1500)
            posts_text = await page.inner_text("body", timeout=10000)
            text_parts.append(f"=== REDDIT POSTS TAB ===\n{posts_text[:3000]}")
    except Exception as e:
        logger.debug("Reddit: posts tab navigation failed: %s", e)

    # Click Comments tab
    try:
        comments_tab = page.locator('a:has-text("Comments"), button:has-text("Comments")')
        if await comments_tab.count() > 0:
            await comments_tab.first.click(timeout=5000)
            await page.wait_for_timeout(2000)
            comments_text = await page.inner_text("body", timeout=10000)
            text_parts.append(f"=== REDDIT COMMENTS TAB ===\n{comments_text[:3000]}")
    except Exception as e:
        logger.debug("Reddit: comments tab navigation failed: %s", e)

    # Back to overview
    try:
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
    except Exception:
        pass


# ── X (Twitter) Scraper ──────────────────────────────────────────


async def scrape_x_profile(playwright) -> dict:
    """Scrape the logged-in user's X profile.

    Extracts: display_name, bio, follower_count, following_count,
    profile_pic_url, recent posts with engagement metrics.
    """
    # Selectors
    X_HOME_URL = "https://x.com/home"
    X_PROFILE_LINK = 'a[data-testid="AppTabBar_Profile_Link"]'
    X_DISPLAY_NAME = '[data-testid="UserName"]'
    X_BIO = '[data-testid="UserDescription"]'
    X_PROFILE_PIC = 'img[src*="profile_images"][alt*="Opens profile photo"], img[src*="profile_images"]'
    X_FOLLOWERS = 'a[href$="/verified_followers"]'
    X_FOLLOWING = 'a[href$="/following"]'
    X_TWEET_ARTICLE = 'article[data-testid="tweet"]'
    X_TWEET_TEXT = '[data-testid="tweetText"]'
    X_TWEET_ENGAGEMENT = '[role="group"]'

    result = {
        "platform": "x",
        "display_name": None,
        "bio": None,
        "follower_count": 0,
        "following_count": 0,
        "profile_pic_url": None,
        "recent_posts": [],
        "engagement_rate": 0.0,
        "posting_frequency": 0.0,
    }

    context = None
    try:
        context = await _launch_context(playwright, "x")
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to home, then find profile link
        logger.info("X: navigating to home page")
        await page.goto(X_HOME_URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        # Get profile URL from navigation
        profile_link = page.locator(X_PROFILE_LINK)
        profile_url = await _safe_attr(profile_link, "href", timeout=10000)
        if profile_url:
            if not profile_url.startswith("http"):
                profile_url = f"https://x.com{profile_url}"
            logger.info("X: navigating to profile: %s", profile_url)
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=20000)
        else:
            logger.warning("X: could not find profile link, trying /home redirect")
            # Fallback: try getting username from the URL/page
            await page.goto("https://x.com/settings/account", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            # Try to extract username from page content
            current_url = page.url
            logger.warning("X: fell back to %s, cannot determine profile URL", current_url)
            await context.close()
            return result

        await page.wait_for_timeout(3000)

        # ── 3-Tier Pipeline ──
        # Tier 1: Navigate tabs, extract text, send to AI (cheapest)
        try:
            from utils.ai_profile_scraper import (
                ai_scrape_profile_from_text, ai_scrape_profile, is_missing_key_fields,
            )
            collected_text = await _navigate_tabs_and_collect_text(page, "x")
            # Navigate back to profile for CSS fallback
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            ai_result = await ai_scrape_profile_from_text("x", page, collected_text)
            if ai_result and not is_missing_key_fields(ai_result):
                logger.info("X: Tier 1 (text) extraction succeeded")
                await context.close()
                return ai_result

            # Tier 3: Screenshot + Vision (last resort)
            if is_missing_key_fields(ai_result):
                logger.info("X: Tier 1 missing key fields, escalating to Tier 3 (screenshot)")
                vision_result = await ai_scrape_profile("x", page)
                if vision_result and not is_missing_key_fields(vision_result):
                    logger.info("X: Tier 3 (screenshot) extraction succeeded")
                    await context.close()
                    return vision_result
        except Exception as e:
            logger.warning("X: AI pipeline failed, falling back to CSS selectors: %s", e)

        # Tier 2: CSS selectors (fallback / supplement)

        # Extract display name
        name_el = page.locator(X_DISPLAY_NAME)
        name_text = await _safe_text(name_el)
        if name_text:
            # X shows "Display Name\n@username" — take first line
            lines = name_text.split("\n")
            result["display_name"] = lines[0].strip() if lines else name_text

        # Extract bio
        bio_text = await _safe_text(page.locator(X_BIO))
        if bio_text:
            result["bio"] = bio_text

        # Extract profile picture
        pic_url = await _safe_attr(page.locator(X_PROFILE_PIC), "src")
        if pic_url:
            result["profile_pic_url"] = pic_url

        # Extract follower count
        followers_el = page.locator(X_FOLLOWERS)
        followers_text = await _safe_text(followers_el)
        if followers_text:
            result["follower_count"] = _parse_number(followers_text)
            logger.info("X: follower_count=%d", result["follower_count"])

        # Extract following count
        following_el = page.locator(X_FOLLOWING)
        following_text = await _safe_text(following_el)
        if following_text:
            result["following_count"] = _parse_number(following_text)

        # Scrape recent tweets
        logger.info("X: scraping recent tweets")
        posts = []
        seen_texts = set()

        for scroll_round in range(8):  # Scroll up to 8 times to collect tweets
            articles = page.locator(X_TWEET_ARTICLE)
            count = await articles.count()

            for i in range(count):
                if len(posts) >= 30:
                    break
                try:
                    article = articles.nth(i)

                    # Skip retweets — only count original posts
                    social_ctx = article.locator('span[data-testid="socialContext"]')
                    if await social_ctx.count() > 0:
                        ctx_text = (await social_ctx.first.inner_text()).lower()
                        if "repost" in ctx_text or "retweeted" in ctx_text:
                            continue

                    # Get tweet text
                    tweet_text_el = article.locator(X_TWEET_TEXT)
                    tweet_text = ""
                    if await tweet_text_el.count() > 0:
                        tweet_text = (await tweet_text_el.first.inner_text()).strip()

                    # Skip duplicates
                    if tweet_text in seen_texts:
                        continue
                    seen_texts.add(tweet_text)

                    # Get engagement metrics from aria-labels
                    likes = 0
                    retweets = 0
                    replies = 0

                    engagement_group = article.locator(X_TWEET_ENGAGEMENT)
                    if await engagement_group.count() > 0:
                        for el_idx in range(await engagement_group.locator('[aria-label]').count()):
                            el = engagement_group.locator('[aria-label]').nth(el_idx)
                            label = (await el.get_attribute("aria-label") or "").lower()
                            nums = re.findall(r'[\d,]+', label)
                            if not nums:
                                continue
                            val = int(nums[0].replace(",", ""))
                            if "like" in label:
                                likes = val
                            elif "repost" in label or "retweet" in label:
                                retweets = val
                            elif "repl" in label or "comment" in label:
                                replies = val

                    posts.append({
                        "text": tweet_text[:500],  # Truncate long tweets
                        "likes": likes,
                        "retweets": retweets,
                        "replies": replies,
                    })

                except Exception as e:
                    logger.debug("X: error parsing tweet %d: %s", i, e)

            if len(posts) >= 30:
                break

            # Scroll down for more tweets
            await page.mouse.wheel(0, 800)
            await page.wait_for_timeout(2000)

        result["recent_posts"] = posts
        logger.info("X: scraped %d tweets", len(posts))

        # Calculate engagement rate
        if posts and result["follower_count"] > 0:
            total_engagement = sum(
                p["likes"] + p["retweets"] + p["replies"] for p in posts
            )
            avg_engagement = total_engagement / len(posts)
            result["engagement_rate"] = round(avg_engagement / result["follower_count"], 6)

        # Calculate posting frequency (posts per day, estimated from sample)
        if posts:
            # Rough estimate: if we got N posts from scrolling, assume ~30 day window
            result["posting_frequency"] = round(len(posts) / 30, 2)

    except Exception as e:
        logger.error("X: scraping failed: %s", e)
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass

    return result


# ── LinkedIn Body-Text Parsers ────────────────────────────────────


def _parse_linkedin_experience_body(body: str) -> list[dict]:
    """Parse experience entries from LinkedIn /details/experience/ page body text.

    The page renders one job per card. Body text has no reliable CSS anchors
    (obfuscated classes), so we use the known structural pattern:

    Job block (loosely):
        <Title>
        <Company> · <Employment type>       (dot-separated, optional type)
        <Duration>  (contains month/year + "·" + "X yrs Y mos")
        <Location>  (optional, "City · On-site / Hybrid / Remote")
        <description paragraphs>
        <Skills: "Skills: ...">

    Blocks are separated by the "Show credential" / next-job signals.
    We walk line-by-line and group into jobs using date-range lines as anchors.
    """
    jobs = []
    lines = [l.strip() for l in body.split("\n") if l.strip()]

    # Date-range pattern: "MMM YYYY - MMM YYYY" or "MMM YYYY - Present"
    DATE_RE = re.compile(
        r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}'
        r'\s*[-–]\s*'
        r'(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}|Present)',
        re.IGNORECASE,
    )
    # Employment type keywords
    EMP_TYPES = {"full-time", "part-time", "self-employed", "freelance",
                 "contract", "internship", "apprenticeship", "seasonal"}
    # Navigation noise to skip
    NOISE = {
        "experience", "add experience", "edit", "save", "cancel", "back",
        "show all", "see more", "see less", "skip to main", "linkedin",
        "home", "my network", "jobs", "messaging", "notifications",
    }
    # Location suffixes
    LOCATION_MODES = {"on-site", "hybrid", "remote"}

    i = 0
    while i < len(lines):
        line = lines[i]
        low = line.lower()

        # Skip nav noise and short lines
        if low in NOISE or len(line) < 3:
            i += 1
            continue

        # Detect a date-range line — this is the anchor for a new job block
        if DATE_RE.match(line):
            # The job title is 1-2 lines BEFORE the date line
            title = None
            company = None
            emp_type = None
            if i >= 1:
                prev = lines[i - 1]
                if prev.lower() not in NOISE and len(prev) > 2:
                    # Could be "Company · Part-time" or just company
                    if "·" in prev:
                        parts = [p.strip() for p in prev.split("·")]
                        company = parts[0]
                        for p in parts[1:]:
                            if p.lower().strip() in EMP_TYPES:
                                emp_type = p.strip()
                    else:
                        company = prev
            if i >= 2:
                prev2 = lines[i - 2]
                if prev2.lower() not in NOISE and len(prev2) > 2:
                    if company and prev2 != company:
                        title = prev2
                    elif not company:
                        title = prev2

            # Duration is the date-range line itself, may continue on next line
            duration = line
            if i + 1 < len(lines) and "·" in lines[i + 1] and "yr" in lines[i + 1].lower():
                duration = line + " · " + lines[i + 1].split("·")[-1].strip()
                i += 1

            # Next line may be location
            location = None
            if i + 1 < len(lines):
                nxt = lines[i + 1]
                if any(m in nxt.lower() for m in LOCATION_MODES) or (
                    "," in nxt and not DATE_RE.match(nxt) and len(nxt) < 60
                ):
                    location = nxt
                    i += 1

            # Collect description lines until next date block or skills line or noise
            desc_lines = []
            skills = None
            i += 1
            while i < len(lines):
                nxt = lines[i]
                nxt_low = nxt.lower()
                if DATE_RE.match(nxt):
                    break
                if nxt_low in NOISE:
                    i += 1
                    continue
                if nxt_low.startswith("skills:") or nxt_low.startswith("skills :"):
                    skills = nxt.split(":", 1)[-1].strip()
                    i += 1
                    break
                if len(nxt) > 3:
                    desc_lines.append(nxt)
                i += 1

            description = " ".join(desc_lines).strip() if desc_lines else None

            if title or company:
                jobs.append({
                    "title": title,
                    "company": company,
                    "employment_type": emp_type,
                    "duration": duration,
                    "location": location,
                    "description": description,
                    "skills": skills,
                })
            continue

        i += 1

    return jobs


def _parse_linkedin_education_body(body: str) -> list[dict]:
    """Parse education entries from LinkedIn /details/education/ page body text.

    Each education block has the pattern:
        <School name>
        <Degree> · <Field of study>     (optional)
        <Year range>                    (YYYY - YYYY or similar)
        <Activities / Grade / Description lines>
    """
    schools = []
    lines = [l.strip() for l in body.split("\n") if l.strip()]

    # Broad year pattern: handles "2020 - 2024", "Jan 2020 - Jun 2024",
    # "January 2020 - Present", "2020" alone, with any dash variant (-, –, —)
    YEAR_RE = re.compile(
        r'(?:'
        r'(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+)?\d{4}'
        r'\s*[-–—]\s*'
        r'(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+)?(?:\d{4}|Present)'
        r'|^\d{4}$'
        r')',
        re.IGNORECASE,
    )
    INSTITUTION_KEYWORDS = re.compile(
        r'\b(university|college|school|institute|academy|polytechnic|iit|iim|nit)\b',
        re.IGNORECASE,
    )
    NOISE = {
        "education", "add education", "edit", "save", "cancel", "back",
        "show all", "see more", "see less", "skip to main", "linkedin",
        "home", "my network", "jobs", "messaging", "notifications",
    }

    i = 0
    while i < len(lines):
        line = lines[i]
        low = line.lower()

        if low in NOISE or len(line) < 3:
            i += 1
            continue

        # Year-range line is the anchor
        if YEAR_RE.match(line):
            year_range = line
            school = None
            degree = None
            field = None

            # School is typically 1-2 lines before year
            if i >= 1 and lines[i - 1].lower() not in NOISE:
                candidate = lines[i - 1]
                if "\u00b7" in candidate or " · " in candidate:
                    # "Bachelor of Technology · Computer Science" pattern
                    parts = [p.strip() for p in re.split(r'\s*\u00b7\s*', candidate, maxsplit=1)]
                    degree = parts[0]
                    field = parts[1] if len(parts) > 1 else None
                    # School is one more line back
                    if i >= 2 and lines[i - 2].lower() not in NOISE and len(lines[i - 2]) > 3:
                        school = lines[i - 2]
                else:
                    # No separator — could be school or degree
                    if i >= 2 and lines[i - 2].lower() not in NOISE and len(lines[i - 2]) > 3:
                        school = lines[i - 2]
                        degree = candidate
                    else:
                        school = candidate

            # Collect extra description lines
            desc_lines = []
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if YEAR_RE.match(nxt) or nxt.lower() in NOISE:
                    break
                if len(nxt) > 3:
                    desc_lines.append(nxt)
                i += 1

            description = " ".join(desc_lines).strip() if desc_lines else None

            if school or degree:
                schools.append({
                    "school": school,
                    "degree": degree,
                    "field": field,
                    "year_range": year_range,
                    "description": description,
                })
            continue

        i += 1

    # Fallback: if no entries found via year anchor, look for institution-name lines
    if not schools:
        for j, line in enumerate(lines):
            if line.lower() in NOISE or len(line) < 5:
                continue
            if INSTITUTION_KEYWORDS.search(line):
                # Try to find a degree on the next non-noise line
                degree = None
                for k in range(j + 1, min(j + 3, len(lines))):
                    nxt = lines[k]
                    if nxt.lower() in NOISE or YEAR_RE.match(nxt):
                        break
                    if "\u00b7" in nxt or " · " in nxt:
                        parts = [p.strip() for p in re.split(r'\s*\u00b7\s*', nxt, maxsplit=1)]
                        degree = parts[0]
                        break
                    if len(nxt) > 3 and not INSTITUTION_KEYWORDS.search(nxt):
                        degree = nxt
                        break
                schools.append({
                    "school": line,
                    "degree": degree,
                    "field": None,
                    "year_range": None,
                    "description": None,
                })

    return schools


def _parse_linkedin_featured_body(body: str) -> list[dict]:
    """Parse featured items from LinkedIn /details/featured/ page body text.

    Supports two formats:
    1. Post-style (with engagement):
        <Post title>
        <preview>
        N reactions · N comments
    2. Link-style (featured external links, no engagement):
        Link
        <Title>
        <Source>       (optional, e.g., "TradingView", "GitHub")
        <Description>  (optional)

    Returns list of {title, type, source, reactions, comments}.
    """
    items = []
    lines = [l.strip() for l in body.split("\n") if l.strip()]

    NOISE = {
        "featured", "add featured", "edit", "delete", "save", "cancel", "back",
        "show all", "see more", "see less", "skip to main", "linkedin",
        "home", "my network", "jobs", "messaging", "notifications",
        "for business", "me",
    }

    REACTIONS_RE = re.compile(r'^([\d,]+)\s*reactions?', re.IGNORECASE)
    COMMENTS_RE = re.compile(r'([\d,]+)\s*comments?', re.IGNORECASE)
    seen_titles = set()

    i = 0
    while i < len(lines):
        line = lines[i]
        low = line.lower()

        # Link-style entry: "Link" marker → next non-noise line is title
        if low == "link":
            # Find next non-noise line for title
            j = i + 1
            title = None
            while j < len(lines) and j < i + 4:
                cand = lines[j]
                clow = cand.lower()
                if clow in NOISE or len(cand) < 2:
                    j += 1
                    continue
                if clow == "link":
                    break
                title = cand
                break
            if title and title not in seen_titles:
                # Source is the next short line (e.g., "TradingView", "GitHub")
                source = None
                k = j + 1
                while k < len(lines) and k < j + 3:
                    cand = lines[k]
                    clow = cand.lower()
                    if clow in NOISE or clow == "link":
                        break
                    if len(cand) <= 40:  # Short line = likely source
                        source = cand
                        break
                    break  # Long line = description, stop
                items.append({
                    "title": title,
                    "type": "link",
                    "source": source,
                    "reactions": 0,
                    "comments": 0,
                })
                seen_titles.add(title)
            i = j + 1
            continue

        # Post-style entry: anchored on "N reactions"
        m = REACTIONS_RE.match(line)
        if m:
            reactions = _parse_number(m.group(1))
            comments = 0
            cm = COMMENTS_RE.search(line)
            if cm:
                comments = _parse_number(cm.group(1))
            else:
                for adj in range(max(0, i - 1), min(len(lines), i + 2)):
                    if adj == i:
                        continue
                    ca = COMMENTS_RE.search(lines[adj])
                    if ca:
                        comments = _parse_number(ca.group(1))
                        break

            # Title is 1-4 lines above
            title = None
            candidates = []
            for back in range(1, 5):
                if i - back < 0:
                    break
                candidate = lines[i - back]
                clow = candidate.lower()
                if clow in NOISE:
                    continue
                if REACTIONS_RE.match(candidate) or COMMENTS_RE.search(candidate):
                    break
                if re.match(r'^\d+[hdwmo]|^\d+yr', candidate):
                    continue
                if len(candidate) < 4:
                    continue
                candidates.append(candidate)
            if candidates:
                title = candidates[-1]

            if title and title not in seen_titles:
                items.append({
                    "title": title,
                    "type": "post",
                    "source": None,
                    "reactions": reactions,
                    "comments": comments,
                })
                seen_titles.add(title)

        i += 1

    return items


def _parse_linkedin_honors_body(body: str) -> list[dict]:
    """Parse honors/awards from LinkedIn /details/honors/ page body text.

    Body structure (approximate):
        Honors & awards
        <Award name>
        Issued by <Issuer> · <Date>
        <Description lines>
        <Award name 2>
        ...

    We use "Issued by" lines as anchors; award name is the line immediately before.
    """
    awards = []
    lines = [l.strip() for l in body.split("\n") if l.strip()]

    NOISE = {
        "honors & awards", "honors and awards", "honors", "awards",
        "add honors", "edit", "save", "cancel", "back",
        "show all", "see more", "see less", "skip to main", "linkedin",
        "home", "my network", "jobs", "messaging", "notifications",
    }

    ISSUED_RE = re.compile(r'^issued\s+by\s+(.+)', re.IGNORECASE)

    for i, line in enumerate(lines):
        m = ISSUED_RE.match(line)
        if not m:
            continue

        issuer_part = m.group(1).strip()
        issuer = issuer_part
        issue_date = None

        # "Issuer · Date" or "Issuer · Month YYYY"
        if "·" in issuer_part:
            parts = [p.strip() for p in issuer_part.split("·", 1)]
            issuer = parts[0]
            issue_date = parts[1] if len(parts) > 1 else None

        # Award name is the closest non-noise line above
        award_name = None
        for back in range(1, 4):
            if i - back < 0:
                break
            candidate = lines[i - back]
            if candidate.lower() in NOISE or len(candidate) < 3:
                continue
            award_name = candidate
            break

        if award_name or issuer:
            awards.append({
                "award_name": award_name,
                "issuer": issuer,
                "issue_date": issue_date,
            })

    return awards


def _parse_linkedin_interests_body(body: str) -> list[dict]:
    """Parse interests from LinkedIn /details/interests/ page body text.

    The Interests detail page has 5 tabs: Top Voices, Companies, Groups,
    Newsletters, Schools. When the page loads, ALL 5 tab names appear
    consecutively as navigation, then the ACTIVE tab's content follows.
    The active tab is typically "Top Voices" (default).

    To avoid misclassifying entries, detect the tab-navigation block (3+ tab
    names within 6 consecutive non-noise lines) and treat content after it
    as the default category ("top_voice").

    Returns list of {name, category}. Capped at 10 per category.
    """
    interests = []
    lines = [l.strip() for l in body.split("\n") if l.strip()]

    CATEGORY_MAP = {
        "top voices": "top_voice",
        "companies": "company",
        "groups": "group",
        "newsletters": "newsletter",
        "schools": "school",
    }
    CATEGORY_HEADINGS = set(CATEGORY_MAP.keys())

    NOISE = {
        "interests", "add interests", "edit", "save", "cancel", "back",
        "show all", "see more", "see less", "skip to main", "linkedin",
        "home", "my network", "jobs", "messaging", "notifications",
        "follow", "following", "unfollow", "join", "joined", "subscribe",
        "view", "private to you", "for business", "me",
    }
    COUNT_RE = re.compile(r'^[\d,\.]+[KkMm]?\s*(followers?|members?|subscribers?)', re.IGNORECASE)
    NUMBER_RE = re.compile(r'^[\d,]+$')
    CONNECTION_RE = re.compile(r'^·\s*\d+(?:st|nd|rd|th)?\+?$|^\d+(?:st|nd|rd|th)?\+?$', re.IGNORECASE)

    # Step 1: Detect tab-navigation block. If 3+ CATEGORY_HEADINGS appear
    # within a 6-line window, those lines are tabs (not category markers).
    tab_block_end = -1
    heading_positions = [i for i, l in enumerate(lines) if l.lower() in CATEGORY_HEADINGS]
    for i in range(len(heading_positions)):
        # Count headings within the next 6 positions starting from heading_positions[i]
        start = heading_positions[i]
        window_headings = [p for p in heading_positions if start <= p <= start + 8]
        if len(window_headings) >= 3:
            tab_block_end = window_headings[-1]
            break

    # Determine active category: default to "top_voice" if tab block detected
    active_category = "top_voice" if tab_block_end >= 0 else None

    # Step 2: Walk lines AFTER the tab block (or from start if no tab block)
    start_idx = tab_block_end + 1 if tab_block_end >= 0 else 0
    counts: dict[str, int] = {}
    i = start_idx
    skip_next_short = False  # Track if we just added a name (skip the "· 3rd" connection line)

    while i < len(lines):
        line = lines[i]
        low = line.lower()

        # If we encounter a category heading OUTSIDE the tab block, switch category
        if low in CATEGORY_HEADINGS and i > tab_block_end:
            active_category = CATEGORY_MAP[low]
            counts.setdefault(active_category, 0)
            i += 1
            continue

        if active_category is None or low in NOISE:
            i += 1
            continue
        if COUNT_RE.match(line) or NUMBER_RE.match(line):
            i += 1
            continue
        if CONNECTION_RE.match(line):
            i += 1
            continue
        if len(line) < 3:
            i += 1
            continue

        # Skip title/description lines — they typically contain commas,
        # job-title keywords, or are long-form descriptions.
        # Real names (top voices, companies, schools) are short and clean.
        if active_category == "top_voice":
            # Names are typically <= 40 chars, no commas, no job title keywords
            JOB_KEYWORDS = re.compile(
                r'\b(ceo|cto|cfo|coo|founder|co-founder|president|chairman|'
                r'chief|director|manager|partner|vp|head\s+of|owner)\b',
                re.IGNORECASE,
            )
            if len(line) > 40 or "," in line or JOB_KEYWORDS.search(line):
                i += 1
                continue
        elif len(line) > 80:
            # For other categories, skip very long lines (likely descriptions)
            i += 1
            continue

        # This line is a candidate name
        if counts.get(active_category, 0) < 10:
            interests.append({"name": line, "category": active_category})
            counts[active_category] = counts.get(active_category, 0) + 1

        i += 1

    return interests


# ── LinkedIn Profile Scraper ─────────────────────────────────────


async def _scrape_linkedin_posts(
    page,
    profile_url_base: str | None = None,
    follower_count: int = 0,
) -> tuple[list, float, float, int]:
    """Navigate to LinkedIn activity page and scrape recent posts with engagement.

    Args:
        page: Playwright page object (must already have an active LinkedIn session).
        profile_url_base: If provided, navigate here first before building the
            activity URL.  Pass the canonical /in/me/ URL when calling after Tier 1
            (which may have left the page on a different URL).
        follower_count: User's follower/connection count used to compute engagement_rate.

    Returns:
        (posts list, engagement_rate, posting_frequency, total_post_count)
    """
    # Selector constants — duplicated here since they can't access the parent function's locals
    _POST_CONTAINER = 'div.feed-shared-update-v2'
    _POST_TEXT = 'div.feed-shared-update-v2__description, span.break-words'
    _ACTIVITY_SUFFIX = "/recent-activity/all/"

    if profile_url_base:
        logger.info("LinkedIn posts helper: navigating to profile before activity scrape")
        await page.goto(profile_url_base, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

    # Build activity URL from current page URL (strips query params cleanly)
    parsed = urlparse(page.url)
    clean_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
    activity_url = clean_url + _ACTIVITY_SUFFIX
    logger.info("LinkedIn posts helper: navigating to activity: %s", activity_url)

    try:
        await page.goto(activity_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(5000)
    except Exception as e:
        logger.warning("LinkedIn posts helper: activity page navigation failed: %s", e)
        return [], 0.0, 0.0, 0

    # Extract total post count from activity page header before scrolling
    total_post_count = 0
    try:
        activity_body = await page.inner_text("body")
        m = re.search(r'([\d,]+)\s*(?:posts?|articles?|activities?)', activity_body, re.IGNORECASE)
        if m:
            total_post_count = _parse_number(m.group(1))
    except Exception:
        pass

    # Initial scroll to trigger lazy-loading
    for _ in range(3):
        await page.mouse.wheel(0, 800)
        await page.wait_for_timeout(2000)

    # Additional scrolls to load more posts
    for _ in range(5):
        await page.mouse.wheel(0, 1000)
        await page.wait_for_timeout(2000)

    posts = []
    seen_texts: set[str] = set()

    post_containers = page.locator(_POST_CONTAINER)
    count = await post_containers.count()
    logger.info("LinkedIn posts helper: found %d post containers on activity page", count)

    for i in range(min(count, 30)):
        try:
            container = post_containers.nth(i)
            container_text = (await container.inner_text()).strip()

            if not container_text or len(container_text) < 20:
                continue

            lines = [l.strip() for l in container_text.split("\n") if l.strip()]

            # Try CSS selector first — targets actual post description
            post_text = ""
            try:
                desc_el = container.locator(_POST_TEXT)
                if await desc_el.count() > 0:
                    post_text = (await desc_el.first.inner_text()).strip()
            except Exception:
                pass

            if not post_text:
                SKIP_WORDS = {"Like", "Comment", "Repost", "Send", "Share", "More"}
                candidate_lines = []
                for line in lines:
                    if line in SKIP_WORDS:
                        continue
                    if re.match(r'^\d+\s*(reaction|comment|repost|like)', line, re.IGNORECASE):
                        continue
                    if re.match(r'^\d+[hdwmo]|^\d+yr', line):
                        continue
                    if len(line) < 10:
                        continue
                    candidate_lines.append(line)
                substantial = [l for l in candidate_lines[1:] if len(l) > 20]
                post_text = substantial[0] if substantial else (candidate_lines[0] if candidate_lines else "")

            if not post_text or post_text[:80] in seen_texts:
                continue
            seen_texts.add(post_text[:80])

            likes = 0
            comments_count = 0
            reposts_count = 0

            for line in lines:
                r_match = re.match(r'^([\d,]+)\s*reaction', line, re.IGNORECASE)
                if r_match:
                    likes = _parse_number(r_match.group(1))
                c_match = re.match(r'^([\d,]+)\s*comment', line, re.IGNORECASE)
                if c_match:
                    comments_count = _parse_number(c_match.group(1))
                rp_match = re.match(r'^([\d,]+)\s*repost', line, re.IGNORECASE)
                if rp_match:
                    reposts_count = _parse_number(rp_match.group(1))

            posted_at = ""
            for line in lines:
                if re.match(r'^\d+[hdwmo]|^\d+yr', line):
                    posted_at = line.split("•")[0].strip()
                    break

            # Detect media (image or video) in the post container
            has_media = False
            try:
                media_el = container.locator(
                    'img[class*="update-components-image"], video, '
                    'div[class*="update-components-image"], '
                    'div[class*="update-components-video"]'
                )
                has_media = await media_el.count() > 0
            except Exception:
                pass

            # Extract impressions/views if shown on the post
            views = 0
            for line in lines:
                vm = re.search(r'([\d,.]+[KkMm]?)\s*(?:impressions?|views?)', line, re.IGNORECASE)
                if vm:
                    views = _parse_number(vm.group(1))
                    break

            posts.append({
                "text": post_text[:500],
                "likes": likes,
                "comments": comments_count,
                "reposts": reposts_count,
                "views": views,
                "has_media": has_media,
                "posted_at": posted_at,
            })

        except Exception as e:
            logger.debug("LinkedIn posts helper: error parsing post %d: %s", i, e)

    # Compute engagement_rate and posting_frequency
    engagement_rate = 0.0
    posting_frequency = 0.0

    if posts and follower_count > 0:
        total_engagement = sum(p["likes"] + p["comments"] + p.get("reposts", 0) for p in posts)
        avg_engagement = total_engagement / len(posts)
        engagement_rate = round(avg_engagement / follower_count, 6)

    if posts:
        posting_frequency = round(len(posts) / 30, 2)

    logger.info("LinkedIn posts helper: scraped %d posts (eng_rate=%.6f, total_count=%d)",
                len(posts), engagement_rate, total_post_count)
    return posts, engagement_rate, posting_frequency, total_post_count


async def _scrape_linkedin_experience_education(
    page,
    profile_url_base: str,
) -> tuple[list, list]:
    """Navigate to LinkedIn experience and education detail pages and parse them.

    Args:
        page: Playwright page object with an active LinkedIn session.
        profile_url_base: Canonical profile URL (e.g. https://www.linkedin.com/in/me/).
            Navigation starts here so URLs are built from a clean base.

    Returns:
        (experience_list, education_list) — either may be empty on failure.
    """
    # Navigate to profile base first to get a clean resolved URL
    logger.info("LinkedIn exp/edu helper: navigating to profile base")
    await page.goto(profile_url_base, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(2000)

    parsed = urlparse(page.url)
    clean_base = urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))

    experience_list: list = []
    education_list: list = []

    # Experience details page
    try:
        exp_url = clean_base + "/details/experience/"
        logger.info("LinkedIn exp/edu helper: navigating to experience: %s", exp_url)
        await page.goto(exp_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        for _ in range(3):
            await page.mouse.wheel(0, 600)
            await page.wait_for_timeout(1000)
        exp_body = await page.inner_text("body")
        experience_list = _parse_linkedin_experience_body(exp_body)
        logger.info("LinkedIn exp/edu helper: extracted %d experience entries", len(experience_list))
    except Exception as e:
        logger.debug("LinkedIn exp/edu helper: experience scraping failed: %s", e)

    # Education details page — build from the clean profile base (not from experience URL)
    try:
        edu_url = clean_base + "/details/education/"
        logger.info("LinkedIn exp/edu helper: navigating to education: %s", edu_url)
        await page.goto(edu_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)
        for _ in range(2):
            await page.mouse.wheel(0, 600)
            await page.wait_for_timeout(1000)
        edu_body = await page.inner_text("body")
        education_list = _parse_linkedin_education_body(edu_body)
        logger.info("LinkedIn exp/edu helper: extracted %d education entries", len(education_list))
    except Exception as e:
        logger.debug("LinkedIn exp/edu helper: education scraping failed: %s", e)

    return experience_list, education_list


async def _scrape_linkedin_extras(
    page,
    profile_url_base: str,
) -> tuple[list, list, list]:
    """Navigate to LinkedIn featured/honors/interests detail pages and parse them.

    Args:
        page: Playwright page object with an active LinkedIn session.
        profile_url_base: Canonical profile URL (e.g. https://www.linkedin.com/in/me/).

    Returns:
        (featured_list, honors_list, interests_list) — any may be empty on failure
        or if the section doesn't exist on the profile.
    """
    logger.info("LinkedIn extras helper: navigating to profile base")
    await page.goto(profile_url_base, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(2000)

    parsed = urlparse(page.url)
    clean_base = urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))

    async def _fetch_and_parse(url: str, parser) -> list:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)
            for _ in range(2):
                await page.mouse.wheel(0, 600)
                await page.wait_for_timeout(1000)
            body = await page.inner_text("body")
            return parser(body)
        except Exception as e:
            logger.warning("LinkedIn extras helper: failed to fetch %s: %s", url, e)
            return []

    featured_list = await _fetch_and_parse(
        clean_base + "/details/featured/",
        _parse_linkedin_featured_body,
    )
    logger.info("LinkedIn extras helper: extracted %d featured items", len(featured_list))

    honors_list = await _fetch_and_parse(
        clean_base + "/details/honors/",
        _parse_linkedin_honors_body,
    )
    logger.info("LinkedIn extras helper: extracted %d honors entries", len(honors_list))

    interests_list = await _fetch_and_parse(
        clean_base + "/details/interests/",
        _parse_linkedin_interests_body,
    )
    logger.info("LinkedIn extras helper: extracted %d interests entries", len(interests_list))

    return featured_list, honors_list, interests_list


async def scrape_linkedin_profile(playwright) -> dict:
    """Scrape the logged-in user's LinkedIn profile.

    Extracts: display_name, headline (bio), connections_count,
    recent posts with engagement metrics.
    """
    # Selectors — LinkedIn uses Shadow DOM, page.locator() pierces automatically
    LI_PROFILE_URL = "https://www.linkedin.com/in/me/"
    LI_ACTIVITY_SUFFIX = "/recent-activity/all/"
    LI_DISPLAY_NAME = "h1.inline, h1.text-heading-xlarge"
    LI_HEADLINE = "div.text-body-medium"
    LI_CONNECTIONS = 'a[href*="/mynetwork/"] span.t-bold, li.text-body-small a span.t-bold'
    LI_PROFILE_PIC = 'img.pv-top-card-profile-picture__image--show, img.profile-photo-edit__preview'
    LI_POST_CONTAINER = 'div.feed-shared-update-v2'
    LI_POST_TEXT = 'div.feed-shared-update-v2__description, span.break-words'
    LI_REACTIONS_COUNT = 'span.social-details-social-counts__reactions-count'
    LI_COMMENTS_COUNT = 'button[aria-label*="comment"]'

    result = {
        "platform": "linkedin",
        "display_name": None,
        "bio": None,
        "follower_count": 0,
        "following_count": 0,
        "post_count": 0,
        "profile_pic_url": None,
        "recent_posts": [],
        "engagement_rate": 0.0,
        "posting_frequency": 0.0,
        # Extended profile fields (location removed — not needed for matching)
        "about": None,
        "experience": [],
        "education": [],
        # LinkedIn analytics (from home page sidebar)
        "profile_viewers": 0,
        "post_impressions": 0,
    }

    context = None
    try:
        context = await _launch_context(playwright, "linkedin")
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to own profile
        logger.info("LinkedIn: navigating to profile")
        await page.goto(LI_PROFILE_URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        # ── 3-Tier Pipeline ──
        try:
            from utils.ai_profile_scraper import (
                ai_scrape_profile_from_text, ai_scrape_profile, is_missing_key_fields,
            )
            collected_text = await _navigate_tabs_and_collect_text(page, "linkedin")
            # Stay on profile page (LinkedIn tabs don't navigate away)

            ai_result = await ai_scrape_profile_from_text("linkedin", page, collected_text)
            if ai_result and not is_missing_key_fields(ai_result):
                logger.info("LinkedIn: Tier 1 (text) extraction succeeded")

                # Initialise profile_data for supplements
                pd = ai_result.get("profile_data") or {}
                if not isinstance(pd, dict):
                    pd = {}

                # Order by criticality:
                # 1. Experience/education (acceptance criterion #3)
                # 2. Featured/honors/interests (spec richness)
                # 3. Posts (already partially supplemented by AI; least critical
                #    since post scraping is the most likely to time out)

                # 1. Experience and education from details pages
                if not pd.get("experience") or not pd.get("education"):
                    try:
                        exp, edu = await _scrape_linkedin_experience_education(page, LI_PROFILE_URL)
                        if exp and not pd.get("experience"):
                            pd["experience"] = exp
                        if edu and not pd.get("education"):
                            pd["education"] = edu
                        logger.info(
                            "LinkedIn: supplemented profile_data with %d experience, %d education",
                            len(exp) if exp else 0,
                            len(edu) if edu else 0,
                        )
                    except Exception as e:
                        logger.warning("LinkedIn: experience/education supplement failed: %s", e)

                # 2. Featured, honors, interests from detail pages
                try:
                    featured, honors, interests = await _scrape_linkedin_extras(page, LI_PROFILE_URL)
                    if featured and not pd.get("featured"):
                        pd["featured"] = featured
                    if honors and not pd.get("honors"):
                        pd["honors"] = honors
                    if interests and not pd.get("interests"):
                        pd["interests"] = interests
                    logger.info(
                        "LinkedIn: supplemented profile_data with %d featured, %d honors, %d interests",
                        len(featured) if featured else 0,
                        len(honors) if honors else 0,
                        len(interests) if interests else 0,
                    )
                except Exception as e:
                    logger.warning("LinkedIn: featured/honors/interests supplement failed: %s", e)

                # Write back profile_data now that all non-post supplements are in
                if pd:
                    ai_result["profile_data"] = pd

                # 3. Posts (most likely to time out — run last so failure
                #    doesn't block the more important supplements above)
                existing_posts = ai_result.get("recent_posts", [])
                if len(existing_posts) == 0:
                    logger.info("LinkedIn: Tier 1 returned 0 posts, supplementing with CSS post scrape")
                    try:
                        li_follower_count = ai_result.get("follower_count", 0) or 0
                        posts, eng_rate, post_freq, scraped_count = await _scrape_linkedin_posts(
                            page,
                            profile_url_base=LI_PROFILE_URL,
                            follower_count=li_follower_count,
                        )
                        if posts:
                            ai_result["recent_posts"] = posts
                            if eng_rate > 0:
                                ai_result["engagement_rate"] = eng_rate
                            if post_freq > 0:
                                ai_result["posting_frequency"] = post_freq
                            logger.info("LinkedIn: supplemented %d posts from CSS", len(posts))
                        if scraped_count > 0 and not ai_result.get("post_count"):
                            ai_result["post_count"] = scraped_count
                    except Exception as e:
                        logger.warning("LinkedIn: CSS post supplement failed: %s", e)

                # Extract username from URL when AI didn't return one
                if not ai_result.get("username"):
                    url_match = re.search(r'/in/([^/?]+)', page.url)
                    if url_match:
                        ai_result["username"] = url_match.group(1)
                        logger.info("LinkedIn: username from URL: %s", ai_result["username"])

                await context.close()
                return ai_result

            if is_missing_key_fields(ai_result):
                logger.info("LinkedIn: Tier 1 missing key fields, escalating to Tier 3")
                vision_result = await ai_scrape_profile("linkedin", page)
                if vision_result and not is_missing_key_fields(vision_result):
                    logger.info("LinkedIn: Tier 3 (screenshot) extraction succeeded")
                    await context.close()
                    return vision_result
        except Exception as e:
            logger.warning("LinkedIn: AI pipeline failed, falling back to CSS: %s", e)

        # Tier 2: CSS selectors (fallback)

        # Extract display name
        name_text = await _safe_text(page.locator(LI_DISPLAY_NAME))
        if name_text:
            result["display_name"] = name_text
            logger.info("LinkedIn: display_name=%s", name_text)

        # Extract headline (used as bio)
        headline = await _safe_text(page.locator(LI_HEADLINE))
        if headline:
            result["bio"] = headline

        # Extract profile picture
        pic_url = await _safe_attr(page.locator(LI_PROFILE_PIC), "src")
        if pic_url:
            result["profile_pic_url"] = pic_url

        # Extract connections/follower count via selectors
        connections_el = page.locator(LI_CONNECTIONS)
        connections_text = await _safe_text(connections_el)
        if connections_text:
            result["follower_count"] = _parse_number(connections_text)

        follower_el = page.locator('span:has-text("follower")')
        follower_text = await _safe_text(follower_el, timeout=3000)
        if follower_text:
            count = _parse_number(follower_text)
            if count > result["follower_count"]:
                result["follower_count"] = count

        # ── Body text fallback (LinkedIn changes CSS classes frequently) ──
        if not result["display_name"] or result["follower_count"] == 0:
            try:
                body = await page.inner_text("body")
                lines = [l.strip() for l in body.split("\n") if l.strip()]

                # Name: usually appears after "Skip to main content" or nav items
                # It's the first non-navigation line that isn't a number
                if not result["display_name"]:
                    # LinkedIn profile URL contains the name slug
                    # e.g. /in/samaara-das/ → "Samaara Das"
                    url_match = re.search(r'/in/([^/?]+)', page.url)
                    if url_match:
                        slug = url_match.group(1).replace('-', ' ').replace('?', '')
                        # Find the line in body that matches the slug (case-insensitive)
                        slug_lower = slug.lower()
                        for line in lines:
                            if line.lower().replace('\xa0', ' ').strip() == slug_lower:
                                result["display_name"] = line
                                break
                            # Partial match — slug is "samaara das", line is "Samaara Das"
                            if slug_lower in line.lower() and len(line) < 40:
                                result["display_name"] = line
                                break

                    # Fallback: first line that appears exactly 2x and looks like a name
                    if not result["display_name"]:
                        from collections import Counter
                        line_counts = Counter(lines)
                        noise = {"show all", "connect", "view", "link", "follow", "more",
                                 "see all", "home", "jobs", "messaging", "notifications",
                                 "enhance profile", "add section", "open to", "me",
                                 "for business", "people you may know"}
                        for line, count in line_counts.most_common():
                            if count != 2:
                                continue
                            low = line.lower().strip()
                            if low in noise or len(line) < 3 or len(line) > 40:
                                continue
                            if line.isdigit() or line.endswith("+"):
                                continue
                            # Skip lines with special chars that aren't names
                            if any(c in line for c in ['@', '#', '/', '\\', '{', '}']):
                                continue
                            result["display_name"] = line
                            break

                    if result["display_name"]:
                        logger.info("LinkedIn: display_name (from body)=%s", result["display_name"])

                # Bio/headline: line right after the name, must be longer (a headline)
                if result["display_name"] and not result["bio"]:
                    try:
                        idx = lines.index(result["display_name"])
                        if idx + 1 < len(lines):
                            candidate = lines[idx + 1]
                            # Must look like a headline (> 15 chars, not a UI element)
                            if len(candidate) > 15 and not candidate.isdigit():
                                result["bio"] = candidate
                    except (ValueError, IndexError):
                        pass

                # Follower count from body text
                if result["follower_count"] == 0:
                    follower_matches = re.findall(r'([\d,]+)\s*followers?', body)
                    if follower_matches:
                        # Take the first match (user's own followers)
                        result["follower_count"] = _parse_number(follower_matches[0])

                # Connections count
                conn_matches = re.findall(r'([\d,]+)\+?\s*connections?', body)
                if conn_matches:
                    conn_count = _parse_number(conn_matches[0])
                    if conn_count > result["follower_count"]:
                        result["follower_count"] = conn_count

                # Following/connections count
                conn_matches = re.findall(r'([\d,]+)\+?\s*connections?', body)
                if conn_matches and result["following_count"] == 0:
                    result["following_count"] = _parse_number(conn_matches[0])

                logger.info("LinkedIn: body fallback — name=%s, followers=%d, following=%d",
                            result["display_name"], result["follower_count"], result["following_count"])
            except Exception as e:
                logger.debug("LinkedIn: body text fallback failed: %s", e)

        # Profile pic fallback — look for any profile-related image
        if not result["profile_pic_url"]:
            pic = page.locator('img[src*="profile-displayphoto"], img[alt*="photo"]')
            pic_url = await _safe_attr(pic, "src")
            if pic_url:
                result["profile_pic_url"] = pic_url

        # ── Extended profile data: about, experience, education ──
        # Location scraping removed — not needed for matching

        try:
            body = await page.inner_text("body")

            # About section: text after "About" header in the body.
            # LinkedIn renders "About" as a section heading; the content follows.
            about_match = re.search(r'\bAbout\b\n+([\s\S]+?)(?=\n(?:Experience|Education|Skills|Licenses|Featured|Activity|More profiles|You might also know)\b)', body)
            if about_match:
                about_text = about_match.group(1).strip()
                # Remove "…see more" / "see less" suffixes
                about_text = re.sub(r'\s*…?see\s+(more|less)\s*$', '', about_text, flags=re.IGNORECASE).strip()
                if about_text and len(about_text) > 20:
                    result["about"] = about_text
                    logger.info("LinkedIn: about (len=%d)", len(about_text))
        except Exception as e:
            logger.debug("LinkedIn: body parse for location/about failed: %s", e)

        # Experience + Education — navigate to detail pages via shared helper
        try:
            exp_list, edu_list = await _scrape_linkedin_experience_education(page, LI_PROFILE_URL)
            result["experience"] = exp_list
            result["education"] = edu_list
        except Exception as e:
            logger.debug("LinkedIn: experience/education scraping failed: %s", e)

        # Featured, Honors, Interests — navigate to detail pages via shared helper
        try:
            featured_list, honors_list, interests_list = await _scrape_linkedin_extras(page, LI_PROFILE_URL)
            if featured_list:
                result["featured"] = featured_list
            if honors_list:
                result["honors"] = honors_list
            if interests_list:
                result["interests"] = interests_list
            logger.info(
                "LinkedIn: extras — %d featured, %d honors, %d interests",
                len(featured_list), len(honors_list), len(interests_list),
            )
        except Exception as e:
            logger.debug("LinkedIn: featured/honors/interests scraping failed: %s", e)

        # Scrape recent posts via the shared helper (navigates to activity page internally)
        posts, eng_rate, post_freq, scraped_count = await _scrape_linkedin_posts(
            page,
            profile_url_base=LI_PROFILE_URL,
            follower_count=result["follower_count"],
        )
        result["recent_posts"] = posts
        if eng_rate > 0:
            result["engagement_rate"] = eng_rate
        if post_freq > 0:
            result["posting_frequency"] = post_freq
        if scraped_count > 0 and result["post_count"] == 0:
            result["post_count"] = scraped_count

        # Scrape profile viewers + post impressions from home page sidebar
        try:
            logger.info("LinkedIn: navigating to home for analytics sidebar")
            await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)

            home_body = await page.inner_text("body")

            # "Profile viewers" and "Post impressions" appear in the left sidebar
            pv_match = re.search(r'Profile viewers?\s*\n?\s*([\d,]+)', home_body)
            if pv_match:
                result["profile_viewers"] = _parse_number(pv_match.group(1))
                logger.info("LinkedIn: profile_viewers=%d", result["profile_viewers"])

            pi_match = re.search(r'Post impressions?\s*\n?\s*([\d,]+)', home_body)
            if pi_match:
                result["post_impressions"] = _parse_number(pi_match.group(1))
                logger.info("LinkedIn: post_impressions=%d", result["post_impressions"])
        except Exception as e:
            logger.debug("LinkedIn: home page analytics scraping failed: %s", e)

    except Exception as e:
        logger.error("LinkedIn: scraping failed: %s", e)
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass

    return result


# ── Facebook Profile Scraper ─────────────────────────────────────


async def scrape_facebook_profile(playwright) -> dict:
    """Scrape the logged-in user's Facebook profile.

    Extracts: display_name, bio/intro, friends_count,
    recent posts with engagement metrics.
    """
    # Selectors — Facebook DOM is heavily obfuscated
    FB_PROFILE_URL = "https://www.facebook.com/me"
    FB_DISPLAY_NAME = 'h1'  # Main profile heading
    FB_INTRO = '[data-pagelet="ProfileTilesFeed_0"], div:has-text("Intro")'
    FB_FRIENDS_LINK = 'a[href*="/friends"]'
    FB_PROFILE_PIC = 'svg[aria-label="Profile picture"] image, image[preserveAspectRatio]'
    FB_POST_CONTAINER = '[data-pagelet*="ProfileTimeline"] [role="article"], div[role="article"]'

    result = {
        "platform": "facebook",
        "display_name": None,
        "bio": None,
        "follower_count": 0,  # friends_count stored as follower_count for consistency
        "following_count": 0,
        "profile_pic_url": None,
        "recent_posts": [],
        "engagement_rate": 0.0,
        "posting_frequency": 0.0,
        # Facebook personal details (from About tab)
        "personal_details": {},  # location, hometown, relationship, gender, language, work, education, links, contact_info
    }

    context = None
    try:
        context = await _launch_context(playwright, "facebook")
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to own profile
        logger.info("Facebook: navigating to profile")
        await page.goto(FB_PROFILE_URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        # ── 3-Tier Pipeline ──
        try:
            from utils.ai_profile_scraper import (
                ai_scrape_profile_from_text, ai_scrape_profile, is_missing_key_fields,
            )
            collected_text = await _navigate_tabs_and_collect_text(page, "facebook")
            # Navigate back to main profile for CSS fallback
            await page.goto(FB_PROFILE_URL, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            ai_result = await ai_scrape_profile_from_text("facebook", page, collected_text)
            if ai_result and not is_missing_key_fields(ai_result):
                logger.info("Facebook: Tier 1 (text) extraction succeeded")

                # Extract username from URL when AI didn't return one
                if not ai_result.get("username"):
                    fb_url = page.url
                    vanity_match = re.search(r'facebook\.com/([^/?]+)', fb_url)
                    if vanity_match and vanity_match.group(1) not in ("profile.php", "me", "home.php"):
                        ai_result["username"] = vanity_match.group(1)
                        logger.info("Facebook: username from URL (vanity): %s", ai_result["username"])
                    else:
                        id_match = re.search(r'[?&]id=(\d+)', fb_url)
                        if id_match:
                            ai_result["username"] = f"fb_{id_match.group(1)}"
                            logger.info("Facebook: username from URL (id): %s", ai_result["username"])

                await context.close()
                return ai_result

            if is_missing_key_fields(ai_result):
                logger.info("Facebook: Tier 1 missing key fields, escalating to Tier 3")
                vision_result = await ai_scrape_profile("facebook", page)
                if vision_result and not is_missing_key_fields(vision_result):
                    logger.info("Facebook: Tier 3 (screenshot) extraction succeeded")
                    await context.close()
                    return vision_result
        except Exception as e:
            logger.warning("Facebook: AI pipeline failed, falling back to CSS: %s", e)

        # Tier 2: CSS selectors (fallback)

        # Extract display name — skip hidden h1 elements (e.g. "Notifications")
        h1_elements = page.locator('h1')
        h1_count = await h1_elements.count()
        for i in range(h1_count):
            try:
                h1 = h1_elements.nth(i)
                if await h1.is_visible():
                    text = (await h1.inner_text()).strip().replace("\xa0", "")
                    if text and text.lower() not in ("notifications", "new", ""):
                        result["display_name"] = text
                        logger.info("Facebook: display_name=%s", text)
                        break
            except Exception:
                continue

        # Extract profile picture
        pic_el = page.locator('svg[aria-label*="rofile"] image, g image')
        pic_url = await _safe_attr(pic_el, "xlink:href")
        if not pic_url:
            pic_url = await _safe_attr(pic_el, "href")
        if pic_url:
            result["profile_pic_url"] = pic_url

        # Extract friends count
        friends_link = page.locator(FB_FRIENDS_LINK)
        friends_text = await _safe_text(friends_link, timeout=5000)
        if friends_text:
            result["follower_count"] = _parse_number(friends_text)
            logger.info("Facebook: friends=%d", result["follower_count"])

        # Friends count from body text fallback
        if result["follower_count"] == 0:
            try:
                body_text = await page.inner_text("body")
                friends_matches = re.findall(r'([\d,]+)\s*friends?', body_text, re.IGNORECASE)
                if friends_matches:
                    result["follower_count"] = _parse_number(friends_matches[0])
                    # Also store as following_count (Facebook friends = mutual follow)
                    result["following_count"] = result["follower_count"]
            except Exception:
                pass
        else:
            result["following_count"] = result["follower_count"]

        # Try to extract bio/intro from the intro section
        try:
            body_text = await page.inner_text("body")
            intro_match = re.search(r'Intro\s*\n(.*?)(?:\n\n|\nDetails|\nFeatured)', body_text, re.DOTALL)
            if intro_match:
                bio_text = intro_match.group(1).strip()
                # Filter out UI artifacts
                ui_noise = ["add bio", "edit details", "add featured", "add hobbies"]
                bio_lines = [l.strip() for l in bio_text.split("\n")
                             if l.strip() and l.strip().lower() not in ui_noise]
                if bio_lines:
                    result["bio"] = "\n".join(bio_lines)[:500]
        except Exception:
            pass

        # ── Scrape personal details from About tab ──
        try:
            # Navigate to the About page (personal details are under /about)
            about_url = page.url.rstrip("/") + "/about"
            logger.info("Facebook: navigating to about page: %s", about_url)
            await page.goto(about_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            about_text = await page.inner_text("body")
            details = {}

            # Location: "Lives in ..."
            loc_match = re.search(r'Lives in\s+(.+?)(?:\n|$)', about_text)
            if loc_match:
                details["location"] = loc_match.group(1).strip()

            # Hometown: "From ..."
            from_match = re.search(r'From\s+(.+?)(?:\n|$)', about_text)
            if from_match:
                details["hometown"] = from_match.group(1).strip()

            # Relationship status: "Single", "In a relationship", "Married", etc.
            for status in ["Single", "In a relationship", "Engaged", "Married", "Divorced",
                           "Widowed", "In a domestic partnership", "In a civil union",
                           "In an open relationship", "It's complicated", "Separated"]:
                if status in about_text:
                    details["relationship"] = status
                    break

            # Gender
            gender_match = re.search(r'(?:^|\n)(Male|Female|Non-binary|Custom)(?:\n|$)', about_text)
            if gender_match:
                details["gender"] = gender_match.group(1)

            # Language
            lang_match = re.search(r'(.+?)\s+language', about_text)
            if lang_match:
                details["language"] = lang_match.group(1).strip()

            # Work — extract from "Work" section
            work_entries = []
            work_section = re.search(r'Work\n([\s\S]*?)(?:\nEducation\b|\nLinks\b|\nContact info\b|\nBasic info\b|\nPlaces lived\b|$)', about_text)
            if work_section:
                work_lines = [l.strip() for l in work_section.group(1).split("\n") if l.strip() and len(l.strip()) > 3]
                # Filter out UI noise
                ui_noise = {"shared with public", "shared with friends", "add a workplace", "edit", "highlights", "·"}
                work_lines = [l for l in work_lines if l.lower() not in ui_noise and not l.startswith("·")]
                for line in work_lines[:5]:
                    work_entries.append(line)
            if work_entries:
                details["work"] = work_entries

            # Education — extract from "Education" section
            edu_entries = []
            edu_section = re.search(r'Education\n([\s\S]*?)(?:\nLinks\b|\nContact info\b|\nBasic info\b|\nWork\b|\nPlaces lived\b|$)', about_text)
            if edu_section:
                edu_lines = [l.strip() for l in edu_section.group(1).split("\n") if l.strip() and len(l.strip()) > 3]
                ui_noise = {"see more education", "see more", "edit", "add", "highlights",
                            "add highlights", "shared with public", "shared with friends",
                            "friends", "see all friends", "·"}
                edu_lines = [l for l in edu_lines
                             if l.lower() not in ui_noise
                             and not l.startswith("·")
                             and not re.match(r'^\d+ friends?$', l, re.IGNORECASE)]
                for line in edu_lines[:5]:
                    edu_entries.append(line)
            if edu_entries:
                details["education"] = edu_entries

            # Links (github, personal websites, etc.)
            links_section = re.search(r'Links\n([\s\S]*?)(?:\nContact info\b|\nBasic info\b|$)', about_text)
            if links_section:
                link_lines = [l.strip() for l in links_section.group(1).split("\n") if l.strip()]
                # Filter to things that look like URLs or domain names
                links = [l for l in link_lines if "." in l and len(l) < 100 and "edit" not in l.lower()]
                if links:
                    details["links"] = links

            # Contact info (other social media handles)
            contact_section = re.search(r'Contact info\n([\s\S]*?)(?:\nBasic info\b|\nLife events\b|$)', about_text)
            if contact_section:
                contact_lines = [l.strip() for l in contact_section.group(1).split("\n") if l.strip()]
                contacts = [l for l in contact_lines if len(l) < 100 and "edit" not in l.lower() and "add" not in l.lower()]
                if contacts:
                    details["contact_info"] = contacts

            if details:
                result["personal_details"] = details
                logger.info("Facebook: scraped personal details: %s", list(details.keys()))

            # Navigate back to profile for post scraping
            await page.goto(FB_PROFILE_URL, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

        except Exception as e:
            logger.debug("Facebook: personal details scraping failed: %s", e)

        # Scrape recent posts using body text parsing.
        # Facebook's DOM is heavily obfuscated — role="article" no longer works.
        # Instead, parse body text and find posts by the "Comment as {name}" marker.
        # Pattern: [noise] → "Shared with ..." → [post content] → Like → Comment → Share → "Comment as ..."
        posts = []
        seen_texts = set()

        for scroll_round in range(8):
            if len(posts) >= 30:
                break

            try:
                body_text = await page.inner_text("body")
                lines = [l.strip() for l in body_text.split("\n") if l.strip()]

                # Find all "Comment as" markers — each one ends a post block
                for idx, line in enumerate(lines):
                    if len(posts) >= 30:
                        break
                    if not line.startswith("Comment as"):
                        continue

                    # Walk backwards from "Comment as" to find post content
                    # Structure: ... "Shared with ..." → content lines → "Like" → "Comment" → "Share" → "Comment as ..."
                    content_lines = []
                    shared_with = None
                    for back_idx in range(idx - 1, max(0, idx - 20), -1):
                        back_line = lines[back_idx]
                        if back_line in ("Like", "Comment", "Share"):
                            continue
                        if back_line.startswith("Shared with"):
                            shared_with = back_line
                            break
                        # Skip noise (single chars, garbled text)
                        if len(back_line) <= 2:
                            continue
                        # Skip common UI elements
                        if back_line in ("Facebook", "·"):
                            continue
                        content_lines.insert(0, back_line)

                    if not content_lines:
                        continue

                    post_text = "\n".join(content_lines)[:500]
                    text_key = post_text[:80]
                    if text_key in seen_texts:
                        continue
                    seen_texts.add(text_key)

                    # Extract engagement counts from lines near the post
                    likes = 0
                    comments_count = 0
                    shares = 0
                    for near_idx in range(max(0, idx - 5), min(len(lines), idx + 3)):
                        near = lines[near_idx]
                        like_match = re.search(r'^(\d+)\s*$', near)  # Standalone number before "Like"
                        if like_match and near_idx < idx:
                            likes = int(like_match.group(1))
                        c_match = re.search(r'(\d+)\s*comment', near, re.IGNORECASE)
                        if c_match:
                            comments_count = int(c_match.group(1))
                        s_match = re.search(r'(\d+)\s*share', near, re.IGNORECASE)
                        if s_match:
                            shares = int(s_match.group(1))

                    posts.append({
                        "text": post_text,
                        "likes": likes,
                        "comments": comments_count,
                        "shares": shares,
                    })

            except Exception as e:
                logger.debug("Facebook: error parsing posts from body text: %s", e)

            if len(posts) >= 30:
                break

            await page.mouse.wheel(0, 800)
            await page.wait_for_timeout(2000)

        result["recent_posts"] = posts
        logger.info("Facebook: scraped %d posts", len(posts))

        # Calculate engagement rate
        if posts and result["follower_count"] > 0:
            total_engagement = sum(
                p["likes"] + p["comments"] + p.get("shares", 0) for p in posts
            )
            avg_engagement = total_engagement / len(posts)
            result["engagement_rate"] = round(avg_engagement / result["follower_count"], 6)

        if posts:
            result["posting_frequency"] = round(len(posts) / 30, 2)

    except Exception as e:
        logger.error("Facebook: scraping failed: %s", e)
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass

    return result


# ── Reddit Profile Scraper ───────────────────────────────────────


async def scrape_reddit_profile(playwright) -> dict:
    """Scrape the logged-in user's Reddit profile.

    Extracts: display_name, total_karma, cake_day,
    recent posts/comments with scores.
    """
    # Selectors
    RD_PROFILE_URL = "https://www.reddit.com/user/me"
    RD_KARMA = '[id="karma"]'
    RD_DISPLAY_NAME = 'h1'
    RD_POST_CONTAINER = 'article, shreddit-post, [data-testid="post-container"]'
    RD_POST_TITLE = 'a[slot="title"], [data-testid="post-title"]'
    RD_POST_SCORE = '[data-testid="post-unit-score"], faceplate-number'

    result = {
        "platform": "reddit",
        "display_name": None,
        "bio": None,
        "follower_count": 0,
        "following_count": 0,
        "profile_pic_url": None,
        "recent_posts": [],
        "engagement_rate": 0.0,
        "posting_frequency": 0.0,
        # Reddit-specific extended fields
        "karma": 0,
        "contributions": 0,
        "reddit_age": None,
        "active_communities": 0,
        "cake_day": None,
    }

    context = None
    try:
        context = await _launch_context(playwright, "reddit")
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to own profile
        logger.info("Reddit: navigating to profile")
        await page.goto(RD_PROFILE_URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        # ── 3-Tier Pipeline ──
        try:
            from utils.ai_profile_scraper import (
                ai_scrape_profile_from_text, ai_scrape_profile, is_missing_key_fields,
            )
            collected_text = await _navigate_tabs_and_collect_text(page, "reddit")
            # Navigate back to overview for CSS fallback
            await page.goto(RD_PROFILE_URL, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            ai_result = await ai_scrape_profile_from_text("reddit", page, collected_text)
            # Use shared lenient check — accepts posts/niches/bio as valid data
            # even when follower_count is 0 (common for Reddit accounts)
            if ai_result and not is_missing_key_fields(ai_result):
                logger.info("Reddit: Tier 1 (text) extraction succeeded")

                # Supplement profile_data with karma/age/subreddits parsed from
                # the collected text — the AI often misses these Reddit-specific
                # sidebar fields, but they're always in the page text.
                try:
                    pd = ai_result.get("profile_data") or {}
                    if not isinstance(pd, dict):
                        pd = {}
                    # Karma: "Karma\n<number>" or "<number>\nKarma" patterns
                    if not pd.get("karma"):
                        km = re.search(r'Karma\s*\n\s*([\d,.]+[KkMm]?)', collected_text)
                        if not km:
                            km = re.search(r'([\d,.]+[KkMm]?)\s*\n\s*Karma', collected_text)
                        if km:
                            pd["karma"] = _parse_number(km.group(1))
                    # Reddit age: "Reddit Age\n<value>" or similar
                    if not pd.get("reddit_age"):
                        ra = re.search(r'Reddit Age\s*\n\s*([^\n]+)', collected_text)
                        if not ra:
                            ra = re.search(r'([^\n]+?)\s*\n\s*Reddit Age', collected_text)
                        if ra:
                            pd["reddit_age"] = ra.group(1).strip()
                    # Active subreddits from Posts/Comments tab text (r/foo patterns)
                    if not pd.get("active_subreddits"):
                        subs = re.findall(r'r/([A-Za-z0-9_]+)', collected_text)
                        if subs:
                            # Dedup + keep top 10 by frequency
                            from collections import Counter
                            counts = Counter(subs)
                            pd["active_subreddits"] = [
                                f"r/{s}" for s, _ in counts.most_common(10)
                            ]
                    if pd:
                        ai_result["profile_data"] = pd
                        logger.info("Reddit: supplemented profile_data with karma=%s, age=%s, %d subreddits",
                                    pd.get("karma"), pd.get("reddit_age"),
                                    len(pd.get("active_subreddits", [])))
                except Exception as e:
                    logger.warning("Reddit: profile_data supplement failed: %s", e)

                await context.close()
                return ai_result

            if is_missing_key_fields(ai_result):
                logger.info("Reddit: Tier 1 missing key fields, escalating to Tier 3")
                vision_result = await ai_scrape_profile("reddit", page)
                if vision_result and not is_missing_key_fields(vision_result):
                    logger.info("Reddit: Tier 3 (screenshot) extraction succeeded")
                    await context.close()
                    return vision_result
        except Exception as e:
            logger.warning("Reddit: AI pipeline failed, falling back to CSS: %s", e)

        # Tier 2: CSS selectors (fallback)

        # Reddit may redirect to /user/{username}/ — read actual username from URL
        current_url = page.url
        logger.info("Reddit: landed on %s", current_url)

        # Extract display name from heading
        name_text = await _safe_text(page.locator('h1, h2'))
        if name_text:
            result["display_name"] = name_text.strip()

        # Parse sidebar data from body text
        try:
            body_text = await page.inner_text("body")

            # Followers
            follower_match = re.search(r'([\d,]+)\s*followers?', body_text, re.IGNORECASE)
            if follower_match:
                result["follower_count"] = _parse_number(follower_match.group(1))
                logger.info("Reddit: followers=%d", result["follower_count"])

            # Parse sidebar fields — numbers appear on separate lines before labels
            body_lines = [l.strip() for l in body_text.split("\n") if l.strip()]

            for i, line in enumerate(body_lines):
                prev = body_lines[i - 1] if i > 0 else ""

                if line == "Karma" and prev:
                    result["karma"] = _parse_number(prev)
                    logger.info("Reddit: karma=%d", result["karma"])
                elif line == "Contributions" and prev:
                    result["contributions"] = _parse_number(prev)
                elif line == "Reddit Age" and prev:
                    result["reddit_age"] = prev.strip()
                    logger.info("Reddit: age=%s", result["reddit_age"])
                elif line.startswith("Active in"):
                    # "Active in >" with number on next or previous line
                    if i + 1 < len(body_lines):
                        next_line = body_lines[i + 1]
                        num = _parse_number(next_line)
                        if num > 0:
                            result["active_communities"] = num
                    # Or try extracting from the line itself "Active in > 2"
                    active_match = re.search(r'>?\s*(\d+)', line)
                    if active_match:
                        result["active_communities"] = int(active_match.group(1))

            # Cake day
            cake_match = re.search(r'Cake day\s*[:\-]?\s*(\w+\s+\d+,?\s*\d{4})', body_text, re.IGNORECASE)
            if cake_match:
                result["cake_day"] = cake_match.group(1).strip()
        except Exception as e:
            logger.debug("Reddit: body text parsing failed: %s", e)

        # Karma fallback via selector
        if result["karma"] == 0:
            karma_text = await _safe_text(page.locator('[id="karma"], [data-testid="karma"]'))
            if karma_text:
                result["karma"] = _parse_number(karma_text)

        # Extract profile picture
        pic_el = page.locator('img[alt*="avatar"], img[alt*="User avatar"]')
        pic_url = await _safe_attr(pic_el, "src")
        if pic_url:
            result["profile_pic_url"] = pic_url

        # Scrape recent posts — prefer shreddit-post attributes (most reliable)
        posts = []
        seen_titles = set()

        for scroll_round in range(8):
            # shreddit-post elements have score, comment-count, post-title, permalink as attributes
            shreddit_posts = page.locator('shreddit-post')
            sp_count = await shreddit_posts.count()

            for i in range(sp_count):
                if len(posts) >= 30:
                    break
                try:
                    el = shreddit_posts.nth(i)
                    title = await el.get_attribute("post-title") or ""
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)

                    score = _parse_number(await el.get_attribute("score") or "0")
                    comment_count = _parse_number(await el.get_attribute("comment-count") or "0")
                    permalink = await el.get_attribute("permalink") or ""
                    # Extract subreddit from permalink like /r/fintech/comments/...
                    subreddit = ""
                    sub_match = re.search(r'/r/([^/]+)/', permalink)
                    if sub_match:
                        subreddit = f"r/{sub_match.group(1)}"
                    # Extract timestamp
                    created = await el.get_attribute("created-timestamp") or ""

                    # Try to get view count from post body text
                    views = 0
                    try:
                        post_text = await el.inner_text()
                        views_match = re.search(r'([\d,.]+[KkMm]?)\s*views?', post_text)
                        if views_match:
                            views = _parse_number(views_match.group(1))
                    except Exception:
                        pass

                    posts.append({
                        "text": title[:300],
                        "title": title[:300],
                        "likes": score,
                        "score": score,
                        "comments": comment_count,
                        "views": views,
                        "subreddit": subreddit,
                        "permalink": permalink,
                        "created_at": created,
                    })
                except Exception as e:
                    logger.debug("Reddit: error parsing shreddit-post %d: %s", i, e)

            # Fallback: parse article elements if no shreddit-posts found
            if sp_count == 0:
                articles = page.locator('article')
                a_count = await articles.count()
                for i in range(a_count):
                    if len(posts) >= 30:
                        break
                    try:
                        article = articles.nth(i)
                        text = (await article.inner_text()).strip()
                        # First line is usually the title
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        title = lines[0] if lines else ""
                        if not title or title in seen_titles or len(title) < 10:
                            continue
                        seen_titles.add(title)
                        posts.append({"text": title[:300], "title": title[:300], "likes": 0, "score": 0, "comments": 0, "subreddit": ""})
                    except Exception:
                        pass

            if len(posts) >= 30:
                break

            await page.mouse.wheel(0, 800)
            await page.wait_for_timeout(2000)

        result["recent_posts"] = posts
        logger.info("Reddit: scraped %d posts", len(posts))

        # Calculate engagement rate (score + comments per post / followers)
        # Use followers if available, fall back to karma
        denominator = result["follower_count"] or result["karma"] or 1
        if posts:
            total_score = sum(p["score"] + p["comments"] for p in posts)
            avg_score = total_score / len(posts)
            result["engagement_rate"] = round(avg_score / denominator, 6)

        if posts:
            result["posting_frequency"] = round(len(posts) / 30, 2)

    except Exception as e:
        logger.error("Reddit: scraping failed: %s", e)
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass

    return result


# ── Orchestrator ──────────────────────────────────────────────────


SCRAPER_MAP = {
    "x": scrape_x_profile,
    "linkedin": scrape_linkedin_profile,
    "facebook": scrape_facebook_profile,
    "reddit": scrape_reddit_profile,
}


async def scrape_all_profiles(platforms: list[str] | None = None) -> dict:
    """Scrape profiles for all connected platforms (or specified ones).

    For each platform: runs the scraper, stores result in local_db.
    One platform failing does NOT block others.

    Returns dict of {platform: scrape_result}.
    """
    if platforms is None:
        # Default to all enabled platforms
        platforms = [p for p, cfg in PLATFORMS.items() if cfg.get("enabled", False)]

    results = {}

    async with async_playwright() as pw:
        for platform in platforms:
            scraper = SCRAPER_MAP.get(platform)
            if not scraper:
                logger.warning("No scraper for platform: %s, skipping", platform)
                continue

            logger.info("Scraping %s profile...", platform)
            try:
                data = await scraper(pw)
                results[platform] = data

                # Store in local DB
                # Pack extended fields into a JSON blob
                # LinkedIn: about, experience, education
                # Facebook: personal_details
                # Reddit: karma, contributions, reddit_age, active_communities, cake_day
                # AI extraction: profile_data dict, content_quality, audience_demographics_estimate
                profile_data_dict = {}

                # If AI extraction returned profile_data as a dict, merge it in
                ai_profile_data = data.get("profile_data")
                if isinstance(ai_profile_data, dict):
                    profile_data_dict.update(ai_profile_data)

                # Also pick up top-level extended keys (CSS scraper pattern)
                for ext_key in ("about", "experience", "education",
                                "personal_details",
                                "karma", "contributions", "reddit_age", "active_communities", "cake_day",
                                "profile_viewers", "post_impressions"):
                    if ext_key in data and data[ext_key]:
                        profile_data_dict[ext_key] = data[ext_key]

                # Store AI-enriched fields in profile_data blob
                if data.get("content_quality"):
                    profile_data_dict["content_quality"] = data["content_quality"]
                if data.get("audience_demographics_estimate"):
                    profile_data_dict["audience_demographics_estimate"] = data["audience_demographics_estimate"]

                profile_data_json = json.dumps(profile_data_dict) if profile_data_dict else None

                # AI-detected niches: from AI extraction or empty
                ai_niches = data.get("ai_detected_niches", [])
                ai_niches_json = json.dumps(ai_niches) if ai_niches else "[]"

                upsert_scraped_profile(
                    platform=platform,
                    follower_count=data.get("follower_count", 0),
                    following_count=data.get("following_count", 0),
                    bio=data.get("bio"),
                    display_name=data.get("display_name"),
                    profile_pic_url=data.get("profile_pic_url"),
                    recent_posts=json.dumps(data.get("recent_posts", [])),
                    engagement_rate=data.get("engagement_rate", 0.0),
                    posting_frequency=data.get("posting_frequency", 0.0),
                    ai_niches=ai_niches_json,
                    profile_data=profile_data_json,
                )
                logger.info(
                    "%s: stored profile — followers=%d, posts=%d, engagement=%.4f",
                    platform,
                    data.get("follower_count", 0),
                    len(data.get("recent_posts", [])),
                    data.get("engagement_rate", 0.0),
                )

            except Exception as e:
                logger.error("Failed to scrape %s: %s", platform, e)
                results[platform] = {"platform": platform, "error": str(e)}

    return results


# ── Server Sync ──────────────────────────────────────────────────


def sync_profiles_to_server() -> dict | None:
    """Read all scraped profiles from local_db and sync summary data to server.

    Builds the payload format the server expects:
    - follower_counts: {"x": 1500, "linkedin": 500, ...}
    - scraped_profiles: full per-platform dicts
    - engagement_rates: {"x": 0.032, ...}
    - posting_frequency: {"x": 12.5, ...}

    Returns server response or None on failure.
    """
    from utils.server_client import update_profile

    profiles = get_all_scraped_profiles()
    if not profiles:
        logger.info("No scraped profiles to sync")
        return None

    follower_counts = {}
    scraped_summary = {}
    engagement_rates = {}
    posting_frequencies = {}

    for p in profiles:
        platform = p["platform"]
        follower_counts[platform] = p.get("follower_count", 0)
        engagement_rates[platform] = p.get("engagement_rate", 0.0)
        posting_frequencies[platform] = p.get("posting_frequency", 0.0)

        # Build scraped_profiles summary (no raw post content — stays local)
        summary = {
            "follower_count": p.get("follower_count", 0),
            "following_count": p.get("following_count", 0),
            "display_name": p.get("display_name"),
            "bio": p.get("bio"),
            "engagement_rate": p.get("engagement_rate", 0.0),
            "posting_frequency": p.get("posting_frequency", 0.0),
            "scraped_at": p.get("scraped_at"),
        }

        # Include profile_data (extended fields + AI-enriched data) for server matching
        profile_data_raw = p.get("profile_data")
        if profile_data_raw:
            try:
                pd = json.loads(profile_data_raw) if isinstance(profile_data_raw, str) else profile_data_raw
                if isinstance(pd, dict) and pd:
                    summary["profile_data"] = pd
            except (json.JSONDecodeError, TypeError):
                pass

        # Include AI-detected niches
        ai_niches_raw = p.get("ai_niches")
        if ai_niches_raw:
            try:
                niches = json.loads(ai_niches_raw) if isinstance(ai_niches_raw, str) else ai_niches_raw
                if isinstance(niches, list) and niches:
                    summary["ai_detected_niches"] = niches
            except (json.JSONDecodeError, TypeError):
                pass

        scraped_summary[platform] = summary

    # Aggregate AI-detected niches from all platforms into a flat set.
    # matching.py's fallback niche-overlap scoring reads user.ai_detected_niches
    # (top-level). Without this, fallback scoring sees an empty set even when
    # each platform has niches populated.
    aggregated_niches = []
    seen = set()
    for summary in scraped_summary.values():
        for niche in (summary.get("ai_detected_niches") or []):
            n = str(niche).strip().lower()
            if n and n not in seen:
                seen.add(n)
                aggregated_niches.append(n)

    try:
        result = update_profile(
            follower_counts=follower_counts,
            scraped_profiles=scraped_summary,
            ai_detected_niches=aggregated_niches if aggregated_niches else None,
        )
        logger.info("Synced profile data to server for %d platform(s), %d aggregated niches",
                    len(profiles), len(aggregated_niches))
        return result
    except Exception as e:
        logger.error("Failed to sync profiles to server: %s", e)
        return None


# ── CLI Entry Point ──────────────────────────────────────────────


async def _main():
    """Run profile scraping for all enabled platforms and sync to server."""
    import argparse

    parser = argparse.ArgumentParser(description="Scrape social media profiles")
    parser.add_argument(
        "--platforms", nargs="*",
        help="Platforms to scrape (default: all enabled)",
    )
    parser.add_argument(
        "--sync", action="store_true",
        help="Sync results to server after scraping",
    )
    args = parser.parse_args()

    results = await scrape_all_profiles(args.platforms)

    for platform, data in results.items():
        if "error" in data:
            print(f"  {platform}: FAILED — {data['error']}")
        else:
            print(f"  {platform}: followers={data.get('follower_count', 0)}, "
                  f"posts={len(data.get('recent_posts', []))}, "
                  f"engagement={data.get('engagement_rate', 0.0):.4f}")

    if args.sync:
        sync_profiles_to_server()


if __name__ == "__main__":
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(ROOT / "logs" / "profile_scraper.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    asyncio.run(_main())
