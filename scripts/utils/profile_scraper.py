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


async def _launch_context(pw, platform: str) -> BrowserContext:
    """Launch persistent browser context for scraping (reuses posting profiles).

    All platforms run headless with stealth flags to bypass automation detection.
    """
    profile_dir = ROOT / "profiles" / f"{platform}-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    kwargs = dict(
        user_data_dir=str(profile_dir),
        headless=True,
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


# ── LinkedIn Profile Scraper ─────────────────────────────────────


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
        "profile_pic_url": None,
        "recent_posts": [],
        "engagement_rate": 0.0,
        "posting_frequency": 0.0,
    }

    context = None
    try:
        context = await _launch_context(playwright, "linkedin")
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to own profile
        logger.info("LinkedIn: navigating to profile")
        await page.goto(LI_PROFILE_URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        # Try CSS selectors first, then fall back to body text parsing.
        # LinkedIn frequently changes CSS classes, so body text is more reliable.

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

        # Navigate to activity page for recent posts
        # Strip query params (e.g., ?isSelfProfile=true) before appending suffix
        from urllib.parse import urlparse, urlunparse
        parsed_profile = urlparse(page.url)
        clean_profile_url = urlunparse((parsed_profile.scheme, parsed_profile.netloc, parsed_profile.path.rstrip("/"), "", "", ""))
        activity_url = clean_profile_url + LI_ACTIVITY_SUFFIX
        logger.info("LinkedIn: navigating to activity: %s", activity_url)
        await page.goto(activity_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(5000)  # LinkedIn needs extra time to render posts

        # Scroll down to trigger lazy-loading of posts
        for _ in range(3):
            await page.mouse.wheel(0, 800)
            await page.wait_for_timeout(2000)

        # Scrape recent posts
        posts = []
        seen_texts = set()

        for scroll_round in range(8):
            post_containers = page.locator(LI_POST_CONTAINER)
            count = await post_containers.count()

            for i in range(count):
                if len(posts) >= 30:
                    break
                try:
                    container = post_containers.nth(i)

                    # Get post text
                    text_el = container.locator('span.break-words, div.feed-shared-update-v2__description')
                    post_text = ""
                    if await text_el.count() > 0:
                        post_text = (await text_el.first.inner_text()).strip()

                    if not post_text or post_text in seen_texts:
                        continue
                    seen_texts.add(post_text)

                    # Get reactions (likes)
                    likes = 0
                    reactions_el = container.locator(LI_REACTIONS_COUNT)
                    if await reactions_el.count() > 0:
                        likes_text = await reactions_el.first.inner_text()
                        likes = _parse_number(likes_text)

                    # Get comments count
                    comments = 0
                    comments_el = container.locator('button[aria-label*="comment"]')
                    if await comments_el.count() > 0:
                        comments_label = await comments_el.first.get_attribute("aria-label") or ""
                        comments = _parse_number(comments_label)

                    # Get reposts count
                    reposts = 0
                    reposts_el = container.locator('button[aria-label*="repost"]')
                    if await reposts_el.count() > 0:
                        reposts_label = await reposts_el.first.get_attribute("aria-label") or ""
                        reposts = _parse_number(reposts_label)

                    # Get timestamp
                    posted_at = ""
                    time_el = container.locator('span.update-components-actor__sub-description, time')
                    if await time_el.count() > 0:
                        posted_at = (await time_el.first.inner_text()).strip()
                        # Clean up: "1yr • \n..." → "1yr"
                        posted_at = posted_at.split("•")[0].split("\n")[0].strip()

                    posts.append({
                        "text": post_text[:500],
                        "likes": likes,
                        "comments": comments,
                        "reposts": reposts,
                        "posted_at": posted_at,
                    })

                except Exception as e:
                    logger.debug("LinkedIn: error parsing post %d: %s", i, e)

            if len(posts) >= 30:
                break

            await page.mouse.wheel(0, 800)
            await page.wait_for_timeout(2000)

        result["recent_posts"] = posts
        logger.info("LinkedIn: scraped %d posts", len(posts))

        # Calculate engagement rate
        if posts and result["follower_count"] > 0:
            total_engagement = sum(
                p["likes"] + p["comments"] + p.get("reposts", 0) for p in posts
            )
            avg_engagement = total_engagement / len(posts)
            result["engagement_rate"] = round(avg_engagement / result["follower_count"], 6)

        # Posting frequency estimate
        if posts:
            result["posting_frequency"] = round(len(posts) / 30, 2)

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
    }

    context = None
    try:
        context = await _launch_context(playwright, "facebook")
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to own profile
        logger.info("Facebook: navigating to profile")
        await page.goto(FB_PROFILE_URL, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

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

        # Scrape recent posts
        posts = []
        seen_texts = set()

        for scroll_round in range(8):
            articles = page.locator('[role="article"]')
            count = await articles.count()

            for i in range(count):
                if len(posts) >= 30:
                    break
                try:
                    article = articles.nth(i)
                    article_text = (await article.inner_text()).strip()

                    # Extract meaningful text content (skip very short or navigation text)
                    if len(article_text) < 20:
                        continue

                    # Take first 500 chars as post text
                    post_text = article_text[:500]
                    text_key = post_text[:100]  # dedup on first 100 chars
                    if text_key in seen_texts:
                        continue
                    seen_texts.add(text_key)

                    # Extract reactions from article text
                    likes = 0
                    comments = 0
                    shares = 0

                    # Look for reaction counts in aria-labels within the article
                    reaction_el = article.locator('[aria-label*="reaction"], [aria-label*="like"]')
                    if await reaction_el.count() > 0:
                        reaction_label = await reaction_el.first.get_attribute("aria-label") or ""
                        likes = _parse_number(reaction_label)

                    # Comment/share counts from text
                    comment_match = re.search(r'(\d+)\s*comment', article_text, re.IGNORECASE)
                    if comment_match:
                        comments = int(comment_match.group(1))
                    share_match = re.search(r'(\d+)\s*share', article_text, re.IGNORECASE)
                    if share_match:
                        shares = int(share_match.group(1))

                    posts.append({
                        "text": post_text,
                        "likes": likes,
                        "comments": comments,
                        "shares": shares,
                    })

                except Exception as e:
                    logger.debug("Facebook: error parsing post %d: %s", i, e)

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
        "follower_count": 0,  # karma stored as follower_count for consistency
        "following_count": 0,
        "profile_pic_url": None,
        "recent_posts": [],
        "engagement_rate": 0.0,
        "posting_frequency": 0.0,
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

        # Reddit may redirect to /user/{username}/ — read actual username from URL
        current_url = page.url
        logger.info("Reddit: landed on %s", current_url)

        # Extract display name from heading
        name_text = await _safe_text(page.locator('h1, h2'))
        if name_text:
            result["display_name"] = name_text.strip()

        # Extract karma — try multiple selectors
        karma_text = await _safe_text(page.locator('[id="karma"], [data-testid="karma"]'))
        if karma_text:
            result["follower_count"] = _parse_number(karma_text)
            logger.info("Reddit: karma=%d", result["follower_count"])

        # Try getting karma from page body as fallback
        if result["follower_count"] == 0:
            try:
                body_text = await page.inner_text("body")
                karma_match = re.search(r'([\d,]+)\s*karma', body_text, re.IGNORECASE)
                if karma_match:
                    result["follower_count"] = _parse_number(karma_match.group(1))
            except Exception:
                pass

        # Extract follower count (Reddit shows "X followers" on profile)
        try:
            body_text = await page.inner_text("body") if 'body_text' not in dir() else body_text
            follower_match = re.findall(r'([\d,]+)\s*followers?', body_text, re.IGNORECASE)
            if follower_match:
                result["following_count"] = _parse_number(follower_match[0])
                logger.info("Reddit: followers=%d", result["following_count"])
        except Exception:
            pass

        # Extract cake day
        try:
            body_text = await page.inner_text("body")
            cake_match = re.search(r'Cake day\s*[:\-]?\s*(\w+\s+\d+,?\s*\d{4})', body_text, re.IGNORECASE)
            if cake_match:
                result["cake_day"] = cake_match.group(1).strip()
        except Exception:
            pass

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

                    posts.append({
                        "title": title[:300],
                        "score": score,
                        "comments": comment_count,
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
                        posts.append({"title": title[:300], "score": 0, "comments": 0, "subreddit": ""})
                    except Exception:
                        pass

            if len(posts) >= 30:
                break

            await page.mouse.wheel(0, 800)
            await page.wait_for_timeout(2000)

        result["recent_posts"] = posts
        logger.info("Reddit: scraped %d posts", len(posts))

        # Calculate engagement rate (score-based)
        if posts and result["follower_count"] > 0:
            total_score = sum(p["score"] + p["comments"] for p in posts)
            avg_score = total_score / len(posts)
            result["engagement_rate"] = round(avg_score / result["follower_count"], 6)

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
                    ai_niches="[]",  # Filled later by AI niche classification
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
        scraped_summary[platform] = {
            "follower_count": p.get("follower_count", 0),
            "following_count": p.get("following_count", 0),
            "display_name": p.get("display_name"),
            "bio": p.get("bio"),
            "engagement_rate": p.get("engagement_rate", 0.0),
            "posting_frequency": p.get("posting_frequency", 0.0),
            "scraped_at": p.get("scraped_at"),
        }

    try:
        result = update_profile(
            follower_counts=follower_counts,
            scraped_profiles=scraped_summary,
        )
        logger.info("Synced profile data to server for %d platform(s)", len(profiles))
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
