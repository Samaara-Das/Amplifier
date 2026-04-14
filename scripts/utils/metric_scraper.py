"""Metric scraper — revisits posted URLs to scrape engagement data.

Scraping schedule: once every 24 hours for the lifetime of the campaign
(until campaign status is completed, cancelled, or expired).

Every scrape is stored. The latest scrape is the billing source of truth.
"""

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.local_db import (
    get_posts_for_scraping, add_metric, get_unreported_metrics, mark_metrics_reported,
    update_post_status,
)
from utils.server_client import report_metrics, report_post_deleted
from utils.browser_config import apply_full_screen

logger = logging.getLogger(__name__)

# ── Persistent rate-limit back-off state ──────���─────────────────────────
# Survives across run_metric_scraping() calls (module-level, reset on process restart).
# {platform: datetime} — if now < backoff_until, skip that platform entirely.
_platform_backoff_until: dict[str, datetime] = {}


def _is_platform_backed_off(platform: str) -> bool:
    """Check if a platform is in rate-limit back-off cooldown."""
    until = _platform_backoff_until.get(platform)
    if until and datetime.now(timezone.utc) < until:
        return True
    # Expired — clean up
    _platform_backoff_until.pop(platform, None)
    return False


def _set_platform_backoff(platform: str, hours: int = 1) -> None:
    """Set a platform into back-off cooldown for `hours` hours."""
    _platform_backoff_until[platform] = datetime.now(timezone.utc) + timedelta(hours=hours)
    logger.warning("Platform %s backed off until %s (1 hour)", platform,
                    _platform_backoff_until[platform].isoformat())


def _warn_if_all_zero(post: dict, metrics: dict, scrape_count: int) -> None:
    """Log a warning if scraper returns all zeros on a post that previously had engagement.

    All-zero on a first scrape is normal (post is new). All-zero on a later scrape
    when previous scrapes had engagement could indicate a platform UI change breaking
    the scraper — not a real drop to zero.
    """
    values = [metrics.get("impressions", 0), metrics.get("likes", 0),
              metrics.get("reposts", 0), metrics.get("comments", 0)]
    if any(v != 0 for v in values):
        return  # Not all-zero, nothing to warn about

    if scrape_count == 0:
        return  # First scrape, zeros are normal for new posts

    logger.warning(
        "ALL-ZERO metrics for post %d (%s) on scrape #%d — possible scraper breakage. "
        "URL: %s. Storing zeros but flagging for investigation.",
        post["id"], post.get("platform", "?"), scrape_count + 1, post.get("post_url", "?"),
    )


def _mark_post_deleted(post: dict) -> None:
    """Mark a post as deleted locally and notify the server to void earnings."""
    update_post_status(post["id"], "deleted")
    logger.info("Marked post %d as deleted locally", post["id"])

    server_post_id = post.get("server_post_id")
    if server_post_id:
        try:
            report_post_deleted(server_post_id)
        except Exception as e:
            logger.warning("Failed to notify server about deleted post %d: %s",
                           server_post_id, e)


# Load platform config
with open(ROOT / "config" / "platforms.json", "r", encoding="utf-8") as f:
    PLATFORMS = json.load(f)


async def _launch_context(pw, platform: str):
    """Launch browser context for scraping (reuse posting profiles)."""
    profile_dir = ROOT / "profiles" / f"{platform}-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    headless = os.getenv("HEADLESS", "false").lower() == "true"
    kwargs = dict(
        user_data_dir=str(profile_dir),
        headless=headless,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36"
        ),
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    apply_full_screen(kwargs, headless=headless)

    proxy_url = PLATFORMS.get(platform, {}).get("proxy")
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}

    return await pw.chromium.launch_persistent_context(**kwargs)


async def _scrape_x(page, post_url: str) -> tuple[dict, str | None]:
    """Scrape metrics from an X/Twitter post.

    X exposes views, likes, reposts, replies via aria-labels on the
    engagement button group.

    Returns (metrics_dict, status) where status is 'deleted', 'rate_limited', or None.
    """
    metrics = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0}
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        # Wait for engagement group to render (viral posts can take longer)
        try:
            await page.wait_for_selector('[role="group"]', timeout=8000)
        except Exception:
            pass  # Fall through — page may be deleted or still loading
        await page.wait_for_timeout(1000)

        body_text = await page.inner_text("body")
        title = await page.title()

        # Detect deleted / unavailable posts
        # Normalize unicode: replace curly quotes with straight, ellipsis with dots
        body_lower = body_text.lower().replace("\u2019", "'").replace("\u2018", "'").replace("\u2026", "...")
        unavailable_phrases = [
            "this post is unavailable",
            "this account doesn't exist",
            "this post was deleted",
            "hmm...this page doesn't exist",
            "this page doesn't exist",
            "account suspended",
            "this tweet is unavailable",
            "this tweet has been deleted",
            "page not found",
        ]
        if any(phrase in body_lower for phrase in unavailable_phrases):
            logger.warning("Post deleted/unavailable on X: %s", post_url)
            return metrics, "deleted"

        # Detect rate limiting / CAPTCHA
        rate_phrases = ["rate limit", "try again later", "too many requests"]
        title_lower = title.lower()
        if any(phrase in body_lower or phrase in title_lower for phrase in rate_phrases):
            logger.warning("Rate limited on X while scraping: %s", post_url)
            return metrics, "rate_limited"
        if "captcha" in body_lower or "captcha" in title_lower:
            logger.warning("CAPTCHA detected on X while scraping: %s", post_url)
            return metrics, "rate_limited"

        # Only use the FIRST role="group" — that's the main post's engagement bar.
        # Pages with quoted posts/replies have multiple groups; later ones are NOT the target.
        all_groups = await page.query_selector_all('[role="group"]')
        if all_groups:
            first_group = all_groups[0]
            for el in await first_group.query_selector_all('[aria-label]'):
                label = await el.get_attribute("aria-label") or ""
                label_lower = label.lower()

                numbers = re.findall(r'[\d,]+', label)
                if not numbers:
                    continue
                count = int(numbers[0].replace(",", ""))

                if "view" in label_lower:
                    metrics["impressions"] = count
                elif "like" in label_lower:
                    metrics["likes"] = count
                elif "repost" in label_lower or "retweet" in label_lower:
                    metrics["reposts"] = count
                elif "repl" in label_lower or "comment" in label_lower:
                    metrics["comments"] = count

        # Views fallback: X sometimes puts view count in a separate summary aria-label.
        # Use the FIRST match only (main post summary).
        if metrics["impressions"] == 0:
            view_els = await page.query_selector_all('[aria-label*="views"]')
            if view_els:
                label = await view_els[0].get_attribute("aria-label") or ""
                view_match = re.search(r'([\d,]+)\s*views', label.lower())
                if view_match:
                    metrics["impressions"] = int(view_match.group(1).replace(",", ""))

    except Exception as e:
        logger.warning("Failed to scrape X post %s: %s", post_url, e)

    return metrics, None


async def _scrape_linkedin(page, post_url: str) -> tuple[dict, str | None]:
    """Scrape metrics from a LinkedIn post.

    LinkedIn CSS classes change frequently. Uses both CSS selectors and
    body text parsing as fallback for reliable extraction.

    Returns (metrics_dict, status) where status is 'deleted', 'rate_limited', or None.
    """
    metrics = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0}
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        body_text = await page.inner_text("body")
        title = await page.title()

        # Detect deleted / unavailable posts
        body_lower = body_text.lower()
        title_lower = title.lower()
        unavailable_phrases = [
            "this page doesn't exist",
            "page not found",
            "this content isn't available",
            "this post has been removed",
            "this post cannot be displayed",
            "content unavailable",
        ]
        if any(phrase in body_lower for phrase in unavailable_phrases):
            logger.warning("Post deleted/unavailable on LinkedIn: %s", post_url)
            return metrics, "deleted"

        # Detect rate limiting / auth walls
        if "captcha" in body_lower or "captcha" in title_lower:
            logger.warning("CAPTCHA detected on LinkedIn while scraping: %s", post_url)
            return metrics, "rate_limited"
        if "sign in" in title_lower and "linkedin" in title_lower:
            # Auth wall — session may have expired, treat as rate_limited so we don't store zeros
            logger.warning("LinkedIn auth wall detected while scraping: %s", post_url)
            return metrics, "rate_limited"

        # Impressions — LinkedIn shows "X impressions" for post authors
        imp_match = re.search(r'([\d,]+)\s*(?:impressions?|views?)', body_text, re.IGNORECASE)
        if imp_match:
            metrics["impressions"] = _parse_number(imp_match.group(1))

        # Reactions (likes) — multiple strategies since LinkedIn changes CSS frequently
        # Strategy 1: aria-label like "Name and N others" (reaction summary, 2+ reactions)
        react_summary = page.locator('[aria-label*=" and "][aria-label*=" other"]')
        if await react_summary.count() > 0:
            label = await react_summary.first.get_attribute("aria-label") or ""
            # "Soheb Dawoodani and 333 others" → 333 + 1 = 334
            others_match = re.search(r'and\s+([\d,]+)\s+other', label)
            if others_match:
                metrics["likes"] = _parse_number(others_match.group(1)) + 1
        # Strategy 2: standalone number on line before "N comments" in body text
        # Pattern: "5,832\n206 comments\n300 reposts" — the first number is reactions
        if metrics["likes"] == 0:
            lines = [l.strip() for l in body_text.split("\n") if l.strip()]
            for i, line in enumerate(lines):
                if re.match(r'^[\d,]+[KkMm]?$', line) and i + 1 < len(lines):
                    next_line = lines[i + 1].lower()
                    if "comment" in next_line or "repost" in next_line:
                        metrics["likes"] = _parse_number(line)
                        break
        # Strategy 3: old CSS class
        if metrics["likes"] == 0:
            reactions_el = page.locator(".social-details-social-counts__reactions-count")
            if await reactions_el.count() > 0:
                text = await reactions_el.first.inner_text()
                metrics["likes"] = _parse_number(text)
        # Strategy 4: aria-label "See N more reactions"
        if metrics["likes"] == 0:
            see_more = page.locator('[aria-label*="more reaction"]')
            if await see_more.count() > 0:
                label = await see_more.first.get_attribute("aria-label") or ""
                num = _parse_number(label)
                if num > 0:
                    metrics["likes"] = num

        # Comments — aria-label first ("N comments on X's post"), then button text, then regex
        comment_aria = page.locator('[aria-label*="comments on"]')
        if await comment_aria.count() > 0:
            label = await comment_aria.first.get_attribute("aria-label") or ""
            num = _parse_number(label)
            if num > 0:
                metrics["comments"] = num
        if metrics["comments"] == 0:
            comment_match = re.search(r'([\d,]+)\s*comments?', body_text, re.IGNORECASE)
            if comment_match:
                metrics["comments"] = _parse_number(comment_match.group(1))

        # Reposts — aria-label first ("N reposts of X's post"), then button text, then regex
        repost_aria = page.locator('[aria-label*="reposts of"]')
        if await repost_aria.count() > 0:
            label = await repost_aria.first.get_attribute("aria-label") or ""
            num = _parse_number(label)
            if num > 0:
                metrics["reposts"] = num
        if metrics["reposts"] == 0:
            repost_match = re.search(r'([\d,]+)\s*reposts?', body_text, re.IGNORECASE)
            if repost_match:
                metrics["reposts"] = _parse_number(repost_match.group(1))

    except Exception as e:
        logger.warning("Failed to scrape LinkedIn post %s: %s", post_url, e)

    return metrics, None


async def _scrape_facebook(page, post_url: str) -> tuple[dict, str | None]:
    """Scrape metrics from a Facebook post.

    Facebook does not expose impressions/views on personal profile posts.
    Only reactions, comments, and shares are available.

    Returns (metrics_dict, status) where status is 'deleted', 'rate_limited', or None.
    """
    metrics = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0}
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        body_text = await page.inner_text("body")
        title = await page.title()

        # Detect deleted / unavailable posts
        body_lower = body_text.lower()
        title_lower = title.lower()
        unavailable_phrases = [
            "this content isn't available",
            "this page isn't available",
            "the link you followed may be broken",
            "content not found",
            "this post is no longer available",
            "content isn't available right now",
        ]
        if any(phrase in body_lower for phrase in unavailable_phrases):
            logger.warning("Post deleted/unavailable on Facebook: %s", post_url)
            return metrics, "deleted"

        # Facebook serves empty feed when author visits their own deleted post via permalink.
        # The post content is gone but no explicit deletion message appears.
        # Detect: permalink/posts URL + "no more posts" + no post engagement indicators.
        is_permalink = any(x in post_url for x in ["/permalink", "/posts/", "story_fbid", "pfbid"])
        if is_permalink and "no more posts" in body_lower:
            logger.warning("Post appears deleted on Facebook (empty feed on permalink): %s", post_url)
            return metrics, "deleted"

        # Detect rate limiting / auth walls
        if "captcha" in body_lower or "captcha" in title_lower:
            logger.warning("CAPTCHA detected on Facebook while scraping: %s", post_url)
            return metrics, "rate_limited"
        if "log in" in title_lower and "facebook" in title_lower:
            logger.warning("Facebook auth wall detected while scraping: %s", post_url)
            return metrics, "rate_limited"

        # ── Extract metrics from engagement bar ──
        # Facebook's engagement bar shows likes/comments/shares as consecutive
        # short numeric lines in body text (e.g. "8.5K\n470\n131").
        # Find the LAST group of 2-3 consecutive numeric-only lines — that's the bar.
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
        num_pattern = re.compile(r'^[\d,.]+[KkMm]?$')
        bar_groups = []  # list of [(index, value), ...]
        current_group = []
        for i, line in enumerate(lines):
            if num_pattern.match(line) and len(line) < 10:
                current_group.append((i, _parse_number(line)))
            else:
                if len(current_group) >= 2:
                    bar_groups.append(current_group)
                current_group = []
        if len(current_group) >= 2:
            bar_groups.append(current_group)

        # Use the LAST group — it's closest to the comment section (the target post's bar).
        # Earlier groups may be from related posts in the sidebar/feed.
        if bar_groups:
            best = bar_groups[-1]
            if len(best) >= 1:
                metrics["likes"] = best[0][1]
            if len(best) >= 2:
                metrics["comments"] = best[1][1]
            if len(best) >= 3:
                metrics["reposts"] = best[2][1]

        # Fallback: aria-label "Like: N people" if engagement bar not found
        if metrics["likes"] == 0:
            reactions = page.locator('[aria-label*="reaction"]')
            if await reactions.count() > 0:
                text = await reactions.first.get_attribute("aria-label") or ""
                metrics["likes"] = _parse_number(text)
            else:
                like_count_els = page.locator('[aria-label^="Like:"]')
                if await like_count_els.count() > 0:
                    for i in range(await like_count_els.count()):
                        label = await like_count_els.nth(i).get_attribute("aria-label") or ""
                        num = _parse_number(label)
                        if num > metrics["likes"]:
                            metrics["likes"] = num

        # Views (video posts only)
        view_match = re.search(r'([\d,.]+[KkMm]?)\s*views?', body_text, re.IGNORECASE)
        if view_match:
            metrics["impressions"] = _parse_number(view_match.group(1))

    except Exception as e:
        logger.warning("Failed to scrape Facebook post %s: %s", post_url, e)

    return metrics, None


async def _scrape_reddit(page, post_url: str) -> tuple[dict, str | None]:
    """Scrape metrics from a Reddit post.

    Reddit shows views in body text (e.g. '3.2K views'), upvotes via
    shreddit-post 'score' attribute, and comments via 'comment-count'.
    Reddit blocks headless browsers, so this runs in headed mode.

    Returns (metrics_dict, status) where status is 'deleted', 'rate_limited', or None.
    """
    metrics = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0}
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        body_text = await page.inner_text("body")
        title = await page.title()

        # Detect deleted / removed posts
        body_lower = body_text.lower()
        title_lower = title.lower()
        unavailable_phrases = [
            "sorry, this post was removed",
            "sorry, this post was deleted",
            "this post was removed by",
            "this post was deleted by",
            "this post has been removed",
            "this post is no longer available",
            "page not found",
            "sorry, this page isn't available",
            # NOTE: [deleted] and [removed] NOT checked here — they appear in deleted
            # COMMENTS too, causing false positives. Post deletion is caught by the
            # shreddit-post[removed="true"] attribute check below.
        ]
        if any(phrase in body_lower for phrase in unavailable_phrases):
            logger.warning("Post deleted/removed on Reddit: %s", post_url)
            return metrics, "deleted"

        # Check shreddit-post attributes for removal/deletion
        sp = page.locator("shreddit-post")
        if await sp.count() > 0:
            removed_attr = await sp.first.get_attribute("removed")
            if removed_attr and removed_attr.lower() == "true":
                logger.warning("Post marked as removed on Reddit: %s", post_url)
                return metrics, "deleted"
            # User-deleted posts: author="[deleted]" or is-author-deleted attribute present
            author_attr = await sp.first.get_attribute("author")
            if author_attr and author_attr == "[deleted]":
                logger.warning("Post deleted by author on Reddit: %s", post_url)
                return metrics, "deleted"
            is_author_deleted = await sp.first.get_attribute("is-author-deleted")
            if is_author_deleted is not None:  # boolean attribute — presence means true
                logger.warning("Post author deleted on Reddit: %s", post_url)
                return metrics, "deleted"
        elif "reddit" in title_lower and len(body_text.strip()) < 100:
            # Page loaded but no post content — likely removed
            logger.warning("Post appears removed on Reddit (empty page): %s", post_url)
            return metrics, "deleted"

        # Detect rate limiting
        if "captcha" in body_lower or "captcha" in title_lower:
            logger.warning("CAPTCHA detected on Reddit while scraping: %s", post_url)
            return metrics, "rate_limited"
        rate_phrases = ["rate limit", "too many requests", "try again later"]
        if any(phrase in body_lower or phrase in title_lower for phrase in rate_phrases):
            logger.warning("Rate limited on Reddit while scraping: %s", post_url)
            return metrics, "rate_limited"

        # Views from body text (e.g. "3.2K views")
        view_match = re.search(r'([\d,.]+[KkMm]?)\s*views?', body_text, re.IGNORECASE)
        if view_match:
            metrics["impressions"] = _parse_number(view_match.group(1))

        # Upvotes — prefer shreddit-post attribute (most reliable)
        if await sp.count() > 0:
            score = await sp.first.get_attribute("score")
            if score:
                metrics["likes"] = _parse_number(score)
            comment_count = await sp.first.get_attribute("comment-count")
            if comment_count:
                metrics["comments"] = _parse_number(comment_count)
        else:
            # Fallback to data-testid selectors
            score_el = page.locator('[data-testid="post-unit-score"]')
            if await score_el.count() > 0:
                text = await score_el.first.inner_text()
                metrics["likes"] = _parse_number(text)

            comments_el = page.locator('[data-testid="post-comment-count"]')
            if await comments_el.count() > 0:
                text = await comments_el.first.inner_text()
                metrics["comments"] = _parse_number(text)

    except Exception as e:
        logger.warning("Failed to scrape Reddit post %s: %s", post_url, e)

    return metrics, None


async def _scrape_tiktok(page, post_url: str) -> tuple[dict, str | None]:
    """Scrape metrics from a TikTok post.

    Returns (metrics_dict, status) where status is 'deleted', 'rate_limited', or None.
    """
    metrics = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0}
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        body_text = await page.inner_text("body")
        title = await page.title()
        body_lower = body_text.lower()
        title_lower = title.lower()

        # Detect deleted / unavailable
        unavailable_phrases = [
            "this video is unavailable",
            "couldn't find this account",
            "video currently unavailable",
            "page not available",
        ]
        if any(phrase in body_lower for phrase in unavailable_phrases):
            logger.warning("Post deleted/unavailable on TikTok: %s", post_url)
            return metrics, "deleted"

        # Detect rate limiting / CAPTCHA
        if "captcha" in body_lower or "captcha" in title_lower:
            logger.warning("CAPTCHA detected on TikTok while scraping: %s", post_url)
            return metrics, "rate_limited"

        like_match = re.search(r'([\d.]+[KkMm]?)\s*(?:Likes?|likes?)', body_text)
        if like_match:
            metrics["likes"] = _parse_abbreviated(like_match.group(1))

        comment_match = re.search(r'([\d.]+[KkMm]?)\s*(?:Comments?|comments?)', body_text)
        if comment_match:
            metrics["comments"] = _parse_abbreviated(comment_match.group(1))

        share_match = re.search(r'([\d.]+[KkMm]?)\s*(?:Shares?|shares?)', body_text)
        if share_match:
            metrics["reposts"] = _parse_abbreviated(share_match.group(1))

    except Exception as e:
        logger.warning("Failed to scrape TikTok post %s: %s", post_url, e)

    return metrics, None


async def _scrape_instagram(page, post_url: str) -> tuple[dict, str | None]:
    """Scrape metrics from an Instagram post.

    Returns (metrics_dict, status) where status is 'deleted', 'rate_limited', or None.
    """
    metrics = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0}
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        body_text = await page.inner_text("body")
        title = await page.title()
        body_lower = body_text.lower()
        title_lower = title.lower()

        # Detect deleted / unavailable
        unavailable_phrases = [
            "this page isn't available",
            "the link you followed may be broken",
            "sorry, this page isn't available",
            "content isn't available",
        ]
        if any(phrase in body_lower for phrase in unavailable_phrases):
            logger.warning("Post deleted/unavailable on Instagram: %s", post_url)
            return metrics, "deleted"

        # Detect rate limiting / auth walls
        if "captcha" in body_lower or "captcha" in title_lower:
            logger.warning("CAPTCHA detected on Instagram while scraping: %s", post_url)
            return metrics, "rate_limited"
        if "log in" in title_lower and "instagram" in title_lower:
            logger.warning("Instagram auth wall detected while scraping: %s", post_url)
            return metrics, "rate_limited"

        # Likes
        likes_el = page.locator('section span:has-text("like")')
        if await likes_el.count() > 0:
            text = await likes_el.first.inner_text()
            metrics["likes"] = _parse_number(text)

        # Comments
        comment_match = re.search(r'View all (\d+) comments?', body_text)
        if comment_match:
            metrics["comments"] = int(comment_match.group(1))

    except Exception as e:
        logger.warning("Failed to scrape Instagram post %s: %s", post_url, e)

    return metrics, None


def _parse_number(text: str) -> int:
    """Extract first number from text like '1,234 likes' or '8K people' or '3.4M views'."""
    # Try abbreviated format first (8K, 3.4M, 1.2K)
    abbrev_match = re.search(r'([\d,.]+)\s*([KkMm])', text)
    if abbrev_match:
        num_str = abbrev_match.group(1).replace(",", "")
        suffix = abbrev_match.group(2).upper()
        multiplier = 1000 if suffix == "K" else 1000000
        try:
            return int(float(num_str) * multiplier)
        except ValueError:
            pass
    # Plain number (1,234 or 1234)
    numbers = re.findall(r'[\d,]+', text)
    if numbers:
        return int(numbers[0].replace(",", ""))
    return 0


def _parse_abbreviated(text: str) -> int:
    """Parse abbreviated numbers like 1.2K, 3.4M."""
    text = text.strip()
    multiplier = 1
    if text.endswith(("K", "k")):
        multiplier = 1000
        text = text[:-1]
    elif text.endswith(("M", "m")):
        multiplier = 1000000
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


SCRAPER_MAP = {
    "x": _scrape_x,
    "linkedin": _scrape_linkedin,
    "facebook": _scrape_facebook,
    "reddit": _scrape_reddit,
    "tiktok": _scrape_tiktok,
    "instagram": _scrape_instagram,
}


def _should_scrape(posted_at_str: str, existing_scrape_count: int = 0) -> bool:
    """Check if a post is due for its next 24-hour scrape.

    Simple schedule: one scrape every 24 hours, starting 24h after posting.
    The latest scrape is always the billing source of truth — no "final" concept.

    Returns True if enough time has passed for the next scrape.
    """
    try:
        posted_at = datetime.fromisoformat(posted_at_str)
    except (ValueError, TypeError):
        return False

    now = datetime.now(timezone.utc)
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)

    hours_since = (now - posted_at).total_seconds() / 3600

    # How many 24h scrapes should have happened by now?
    # First scrape due at T+24h, then every 24h after that.
    scrapes_due = int(hours_since / 24)

    return scrapes_due > existing_scrape_count


async def scrape_all_posts():
    """Scrape metrics for all posts that are due for a scrape cycle.

    Uses MetricCollector (APIs for X/Reddit) when available, falls back to
    Playwright scrapers for all platforms.
    """
    posts = get_posts_for_scraping()
    if not posts:
        logger.info("No posts due for scraping")
        return

    # Get existing metric counts per post to determine completed tiers
    from utils.local_db import _get_db
    db_conn = _get_db()
    metric_counts = {}
    for row in db_conn.execute("SELECT post_id, COUNT(*) as cnt FROM local_metric GROUP BY post_id").fetchall():
        metric_counts[row["post_id"]] = row["cnt"]
    db_conn.close()

    posts_to_scrape = []
    for p in posts:
        scrape_count = metric_counts.get(p["id"], 0)
        if _should_scrape(p["posted_at"], scrape_count):
            posts_to_scrape.append(p)

    if not posts_to_scrape:
        logger.info("No posts due for scraping at this time")
        return

    logger.info("Scraping metrics for %d post(s)...", len(posts_to_scrape))

    # Try to use MetricCollector (API-based for X/Reddit)
    collector = None
    try:
        from utils.metric_collector import MetricCollector
        collector = MetricCollector()
    except Exception as e:
        logger.info("MetricCollector not available, using Playwright scrapers: %s", e)

    # Platforms that have API collection available
    api_platforms = set()
    if collector:
        if collector._x_bearer:
            api_platforms.add("x")
        if collector._reddit:
            api_platforms.add("reddit")

    # Collect via API for supported platforms
    for post in posts_to_scrape:
        platform = post["platform"]
        if not post["post_url"]:
            continue

        # Skip platforms in rate-limit back-off cooldown
        if _is_platform_backed_off(platform):
            logger.info("Skipping %s (rate-limit back-off active)", platform)
            continue

        if platform in api_platforms and collector:
            logger.info("Collecting %s via API: %s", platform, post["post_url"])
            try:
                metrics = await collector.collect(post["post_url"], platform)
                scrape_count = metric_counts.get(post["id"], 0)
                _warn_if_all_zero(post, metrics, scrape_count)
                add_metric(
                    post_id=post["id"],
                    impressions=metrics.get("impressions", 0),
                    likes=metrics.get("likes", 0),
                    reposts=metrics.get("reposts", 0),
                    comments=metrics.get("comments", 0),
                    clicks=0,
                )
                logger.info("  imp=%d, likes=%d, reposts=%d, comments=%d",
                            metrics.get("impressions", 0), metrics.get("likes", 0),
                            metrics.get("reposts", 0), metrics.get("comments", 0))
                continue  # Skip Playwright scraping for this post
            except Exception as e:
                err_msg = str(e).lower()
                # Check if the failure was due to a deleted post
                if "deleted" in err_msg or "unavailable" in err_msg:
                    _mark_post_deleted(post)
                    logger.info("  Marked post %d as deleted via API detection", post["id"])
                    continue
                logger.warning("API collection failed for %s, falling back to Playwright: %s",
                             platform, e)

    # Collect remaining posts via Playwright
    remaining = [p for p in posts_to_scrape
                 if p["platform"] not in api_platforms and p["post_url"]]

    if not remaining:
        return

    # Group by platform for Playwright
    by_platform = {}
    for post in remaining:
        platform = post["platform"]
        if platform not in by_platform:
            by_platform[platform] = []
        by_platform[platform].append(post)

    async with async_playwright() as pw:
        for platform, post_list in by_platform.items():
            # Skip platforms in rate-limit back-off cooldown
            if _is_platform_backed_off(platform):
                logger.info("Skipping %s Playwright scraping (rate-limit back-off active)", platform)
                continue

            scraper = SCRAPER_MAP.get(platform)
            if not scraper:
                logger.warning("No scraper for platform: %s", platform)
                continue

            try:
                context = await _launch_context(pw, platform)
                page = context.pages[0] if context.pages else await context.new_page()
                consecutive_rate_limits = 0

                for post in post_list:
                    if not post["post_url"]:
                        continue

                    # If we hit 3+ consecutive rate limits, set persistent 1-hour back-off
                    if consecutive_rate_limits >= 3:
                        _set_platform_backoff(platform, hours=1)
                        break

                    logger.info("Scraping %s: %s", platform, post["post_url"])
                    metrics, scrape_status = await scraper(page, post["post_url"])

                    # Handle deleted posts — mark as deleted, skip metric insert
                    if scrape_status == "deleted":
                        _mark_post_deleted(post)
                        logger.info("  Marked post %d as deleted, skipping metric insert", post["id"])
                        consecutive_rate_limits = 0
                        await page.wait_for_timeout(2000)
                        continue

                    # Handle rate limiting — don't store zeros, count consecutive hits
                    if scrape_status == "rate_limited":
                        consecutive_rate_limits += 1
                        logger.info("  Rate limited, skipping metric insert (consecutive: %d)",
                                    consecutive_rate_limits)
                        await page.wait_for_timeout(5000)  # Longer pause on rate limit
                        continue

                    consecutive_rate_limits = 0

                    scrape_count = metric_counts.get(post["id"], 0)
                    _warn_if_all_zero(post, metrics, scrape_count)
                    add_metric(
                        post_id=post["id"],
                        impressions=metrics.get("impressions", 0),
                        likes=metrics.get("likes", 0),
                        reposts=metrics.get("reposts", 0),
                        comments=metrics.get("comments", 0),
                        clicks=0,
                    )
                    logger.info("  imp=%d, likes=%d, reposts=%d, comments=%d",
                                metrics.get("impressions", 0), metrics.get("likes", 0),
                                metrics.get("reposts", 0), metrics.get("comments", 0))

                    await page.wait_for_timeout(2000)  # Brief pause between scrapes

                await context.close()

            except Exception as e:
                logger.error("Error scraping %s: %s", platform, e)


def sync_metrics_to_server():
    """Report unreported metrics to the server."""
    unreported = get_unreported_metrics()
    if not unreported:
        return

    server_metrics = []
    metric_ids = []
    for m in unreported:
        server_metrics.append({
            "post_id": m["server_post_id"],
            "impressions": m["impressions"],
            "likes": m["likes"],
            "reposts": m["reposts"],
            "comments": m["comments"],
            "clicks": 0,
            "scraped_at": m["scraped_at"],
        })
        metric_ids.append(m["id"])

    try:
        result = report_metrics(server_metrics)
        mark_metrics_reported(metric_ids)
        logger.info("Synced %d metrics to server", result.get("accepted", 0))
    except Exception as e:
        logger.error("Failed to sync metrics: %s", e)


async def run_scrape_cycle():
    """Run one full scrape cycle: scrape all due posts, then sync to server."""
    await scrape_all_posts()
    sync_metrics_to_server()


if __name__ == "__main__":
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(ROOT / "logs" / "metric_scraper.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    asyncio.run(run_scrape_cycle())
