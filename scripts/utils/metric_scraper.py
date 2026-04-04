"""Metric scraper — revisits posted URLs to scrape engagement data.

Scraping schedule per post:
- T+1h: verify post is live
- T+6h: early engagement
- T+24h: primary metric
- T+72h: final metric (used for billing)
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
)
from utils.server_client import report_metrics

logger = logging.getLogger(__name__)

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
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36"
        ),
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )

    proxy_url = PLATFORMS.get(platform, {}).get("proxy")
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}

    return await pw.chromium.launch_persistent_context(**kwargs)


async def _scrape_x(page, post_url: str) -> dict:
    """Scrape metrics from an X/Twitter post.

    X exposes views, likes, reposts, replies via aria-labels on the
    engagement button group.
    """
    metrics = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0}
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        for el in await page.query_selector_all('[role="group"] [aria-label]'):
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

    except Exception as e:
        logger.warning("Failed to scrape X post %s: %s", post_url, e)

    return metrics


async def _scrape_linkedin(page, post_url: str) -> dict:
    """Scrape metrics from a LinkedIn post.

    LinkedIn CSS classes change frequently. Uses both CSS selectors and
    body text parsing as fallback for reliable extraction.
    """
    metrics = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0}
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        body_text = await page.inner_text("body")

        # Impressions — LinkedIn shows "X impressions" for post authors
        imp_match = re.search(r'([\d,]+)\s*(?:impressions?|views?)', body_text, re.IGNORECASE)
        if imp_match:
            metrics["impressions"] = _parse_number(imp_match.group(1))

        # Reactions (likes) — try selector first, body text fallback
        reactions_el = page.locator(".social-details-social-counts__reactions-count")
        if await reactions_el.count() > 0:
            text = await reactions_el.first.inner_text()
            metrics["likes"] = _parse_number(text)
        else:
            reaction_match = re.search(r'([\d,]+)\s*reactions?', body_text, re.IGNORECASE)
            if reaction_match:
                metrics["likes"] = _parse_number(reaction_match.group(1))

        # Comments — try selector first, body text fallback
        comments_el = page.locator("button:has-text('comment')")
        if await comments_el.count() > 0:
            text = await comments_el.first.inner_text()
            metrics["comments"] = _parse_number(text)
        else:
            comment_match = re.search(r'([\d,]+)\s*comments?', body_text, re.IGNORECASE)
            if comment_match:
                metrics["comments"] = _parse_number(comment_match.group(1))

        # Reposts
        reposts_el = page.locator("button:has-text('repost')")
        if await reposts_el.count() > 0:
            text = await reposts_el.first.inner_text()
            metrics["reposts"] = _parse_number(text)
        else:
            repost_match = re.search(r'([\d,]+)\s*reposts?', body_text, re.IGNORECASE)
            if repost_match:
                metrics["reposts"] = _parse_number(repost_match.group(1))

    except Exception as e:
        logger.warning("Failed to scrape LinkedIn post %s: %s", post_url, e)

    return metrics


async def _scrape_facebook(page, post_url: str) -> dict:
    """Scrape metrics from a Facebook post.

    Facebook does not expose impressions/views on personal profile posts.
    Only reactions, comments, and shares are available.
    """
    metrics = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0}
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        body_text = await page.inner_text("body")

        # Reactions via aria-label
        reactions = page.locator('[aria-label*="reaction"]')
        if await reactions.count() > 0:
            text = await reactions.first.get_attribute("aria-label") or ""
            metrics["likes"] = _parse_number(text)
        else:
            # Fallback: "X people reacted" or just a number near like button
            reaction_match = re.search(r'([\d,]+)\s*(?:people reacted|reactions?)', body_text, re.IGNORECASE)
            if reaction_match:
                metrics["likes"] = _parse_number(reaction_match.group(1))

        # Comments
        comment_match = re.search(r'(\d+)\s*comments?', body_text, re.IGNORECASE)
        if comment_match:
            metrics["comments"] = int(comment_match.group(1))

        # Shares
        share_match = re.search(r'(\d+)\s*shares?', body_text, re.IGNORECASE)
        if share_match:
            metrics["reposts"] = int(share_match.group(1))

        # Views (video posts only)
        view_match = re.search(r'([\d,.]+[KkMm]?)\s*views?', body_text, re.IGNORECASE)
        if view_match:
            metrics["impressions"] = _parse_number(view_match.group(1))

    except Exception as e:
        logger.warning("Failed to scrape Facebook post %s: %s", post_url, e)

    return metrics


async def _scrape_reddit(page, post_url: str) -> dict:
    """Scrape metrics from a Reddit post.

    Reddit shows views in body text (e.g. '3.2K views'), upvotes via
    shreddit-post 'score' attribute, and comments via 'comment-count'.
    Reddit blocks headless browsers, so this runs in headed mode.
    """
    metrics = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0}
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        # Views from body text (e.g. "3.2K views")
        body_text = await page.inner_text("body")
        view_match = re.search(r'([\d,.]+[KkMm]?)\s*views?', body_text, re.IGNORECASE)
        if view_match:
            metrics["impressions"] = _parse_number(view_match.group(1))

        # Upvotes — prefer shreddit-post attribute (most reliable)
        sp = page.locator("shreddit-post")
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

    return metrics


async def _scrape_tiktok(page, post_url: str) -> dict:
    """Scrape metrics from a TikTok post."""
    metrics = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0}
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        # Views
        views_el = page.locator('[data-e2e="browser-nickname"] + span, strong[data-e2e="like-count"]')
        body_text = await page.inner_text("body")

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

    return metrics


async def _scrape_instagram(page, post_url: str) -> dict:
    """Scrape metrics from an Instagram post."""
    metrics = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0}
    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(3000)

        # Likes
        likes_el = page.locator('section span:has-text("like")')
        if await likes_el.count() > 0:
            text = await likes_el.first.inner_text()
            metrics["likes"] = _parse_number(text)

        # Comments
        body_text = await page.inner_text("body")
        comment_match = re.search(r'View all (\d+) comments?', body_text)
        if comment_match:
            metrics["comments"] = int(comment_match.group(1))

    except Exception as e:
        logger.warning("Failed to scrape Instagram post %s: %s", post_url, e)

    return metrics


def _parse_number(text: str) -> int:
    """Extract first number from text like '1,234 likes'."""
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


def _should_scrape(posted_at_str: str, existing_scrape_count: int = 0) -> tuple[bool, bool]:
    """Check if a post should be scraped based on time since posting.

    Uses cumulative tiers — scrapes the next due tier regardless of when
    the scraper runs. No rigid time windows that can be missed.

    Early tiers: T+1h, T+6h, T+24h, T+72h (high frequency early on)
    The T+72h scrape is marked as is_final=True for billing.
    After T+72h: optional recurring scrapes every 24h (not final).

    Returns (should_scrape, is_final).
    """
    try:
        posted_at = datetime.fromisoformat(posted_at_str)
    except (ValueError, TypeError):
        return False, False

    now = datetime.now(timezone.utc)
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)

    hours_since = (now - posted_at).total_seconds() / 3600

    # Early tiers (first 72 hours — scrape frequently)
    early_tiers = [1, 6, 24, 72]

    if existing_scrape_count < len(early_tiers):
        # Still in early tier phase
        due_tier_index = -1
        for i, threshold in enumerate(early_tiers):
            if hours_since >= threshold:
                due_tier_index = i

        if due_tier_index >= existing_scrape_count:
            # Mark as final only when this is the LAST early tier scrape (T+72h)
            # existing_scrape_count == 3 means we're about to do the 4th scrape (index 3 = 72h tier)
            is_final = (existing_scrape_count == len(early_tiers) - 1)
            return True, is_final
        return False, False

    # Past early tiers — optional recurring scrapes every 24h
    # These are NOT final — the T+72h scrape already provided the final metric
    hours_since_72h = hours_since - 72
    if hours_since_72h < 0:
        return False, False

    recurring_scrapes_due = int(hours_since_72h / 24) + 1
    recurring_scrapes_done = existing_scrape_count - len(early_tiers)

    if recurring_scrapes_due > recurring_scrapes_done:
        return True, False

    return False, False


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
        should, is_final = _should_scrape(p["posted_at"], scrape_count)
        if should:
            posts_to_scrape.append((p, is_final))

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
    for post, is_final in posts_to_scrape:
        platform = post["platform"]
        if not post["post_url"]:
            continue

        if platform in api_platforms and collector:
            logger.info("Collecting %s via API: %s", platform, post["post_url"])
            try:
                metrics = await collector.collect(post["post_url"], platform)
                add_metric(
                    post_id=post["id"],
                    impressions=metrics.get("impressions", 0),
                    likes=metrics.get("likes", 0),
                    reposts=metrics.get("reposts", 0),
                    comments=metrics.get("comments", 0),
                    clicks=0,
                    is_final=is_final,
                )
                logger.info("  imp=%d, likes=%d, reposts=%d, comments=%d%s",
                            metrics.get("impressions", 0), metrics.get("likes", 0),
                            metrics.get("reposts", 0), metrics.get("comments", 0),
                            " [FINAL]" if is_final else "")
                continue  # Skip Playwright scraping for this post
            except Exception as e:
                logger.warning("API collection failed for %s, falling back to Playwright: %s",
                             platform, e)

    # Collect remaining posts via Playwright
    remaining = [(p, f) for p, f in posts_to_scrape
                 if p["platform"] not in api_platforms and p["post_url"]]
    # Also include API platform posts that failed (already handled above via fallback)

    if not remaining:
        return

    # Group by platform for Playwright
    by_platform = {}
    for post, is_final in remaining:
        platform = post["platform"]
        if platform not in by_platform:
            by_platform[platform] = []
        by_platform[platform].append((post, is_final))

    async with async_playwright() as pw:
        for platform, post_list in by_platform.items():
            scraper = SCRAPER_MAP.get(platform)
            if not scraper:
                logger.warning("No scraper for platform: %s", platform)
                continue

            try:
                context = await _launch_context(pw, platform)
                page = context.pages[0] if context.pages else await context.new_page()

                for post, is_final in post_list:
                    if not post["post_url"]:
                        continue
                    logger.info("Scraping %s: %s", platform, post["post_url"])
                    metrics = await scraper(page, post["post_url"])

                    add_metric(
                        post_id=post["id"],
                        impressions=metrics.get("impressions", 0),
                        likes=metrics.get("likes", 0),
                        reposts=metrics.get("reposts", 0),
                        comments=metrics.get("comments", 0),
                        clicks=0,
                        is_final=is_final,
                    )
                    logger.info("  imp=%d, likes=%d, reposts=%d, comments=%d%s",
                                metrics.get("impressions", 0), metrics.get("likes", 0),
                                metrics.get("reposts", 0), metrics.get("comments", 0),
                                " [FINAL]" if is_final else "")

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
            "is_final": bool(m["is_final"]),
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
