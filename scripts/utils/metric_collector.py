"""Hybrid metric collection — APIs where available, Playwright scrapers as fallback.

Priority per platform:
- X: API v2 (bearer token) → Playwright scraper
- Reddit: PRAW API → Playwright scraper
- LinkedIn: Playwright scraper (Browser Use post-MVP)
- Facebook: Playwright scraper (Browser Use post-MVP)
"""

import logging
import os
import re
import sys
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.guard import guard_platform


class MetricCollector:
    """Collect post metrics using the best available method per platform."""

    def __init__(self):
        self._x_bearer = os.getenv("X_BEARER_TOKEN", "").strip()
        self._reddit_client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
        self._reddit_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
        self._reddit = None

        if self._reddit_client_id and self._reddit_secret:
            try:
                import praw
                self._reddit = praw.Reddit(
                    client_id=self._reddit_client_id,
                    client_secret=self._reddit_secret,
                    user_agent="Amplifier/1.0",
                )
                logger.info("Reddit API initialized")
            except Exception as e:
                logger.warning("Failed to init Reddit API: %s", e)

        if self._x_bearer:
            logger.info("X API bearer token available")

    async def collect(self, post_url: str, platform: str) -> dict:
        """Collect metrics for a post. Routes to the best method per platform.

        Returns: {"impressions": int, "likes": int, "reposts": int, "comments": int, "clicks": int}
        """
        # Guard BEFORE try/except — must not be swallowed by the fallback handler
        guard_platform(platform, "metrics_collection")

        default = {"impressions": 0, "likes": 0, "reposts": 0, "comments": 0, "clicks": 0}

        try:
            if platform == "x" and self._x_bearer:
                return await self._collect_x_api(post_url)
            elif platform == "reddit":
                # Prefer Playwright for Reddit — it gets view counts. PRAW doesn't.
                return await self._collect_playwright(post_url, platform)
            else:
                # Fallback to Playwright scrapers
                return await self._collect_playwright(post_url, platform)
        except Exception as e:
            logger.warning("Primary collection failed for %s (%s): %s. Trying fallback...",
                          platform, post_url, e)
            try:
                return await self._collect_playwright(post_url, platform)
            except Exception as e2:
                logger.error("Fallback also failed for %s: %s", platform, e2)
                return default

    async def _collect_x_api(self, post_url: str) -> dict:
        """Use X API v2 to read tweet metrics."""
        tweet_id = self._extract_tweet_id(post_url)
        if not tweet_id:
            raise ValueError(f"Could not extract tweet ID from {post_url}")

        url = f"https://api.twitter.com/2/tweets/{tweet_id}"
        params = {"tweet.fields": "public_metrics"}
        headers = {"Authorization": f"Bearer {self._x_bearer}"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            # Detect deleted tweets: X API returns 404 for deleted/suspended tweets
            if resp.status_code == 404:
                raise ValueError(f"Post deleted/unavailable: {post_url}")
            # Detect rate limiting: X API returns 429
            if resp.status_code == 429:
                raise ValueError(f"Rate limited while scraping: {post_url}")
            resp.raise_for_status()

        data = resp.json().get("data", {})
        if not data:
            # API returned 200 but no data — tweet may have been deleted or is not accessible
            errors = resp.json().get("errors", [])
            if errors:
                raise ValueError(f"Post deleted/unavailable: {post_url}")

        pm = data.get("public_metrics", {})

        return {
            "impressions": pm.get("impression_count", 0),
            "likes": pm.get("like_count", 0),
            "reposts": pm.get("retweet_count", 0),
            "comments": pm.get("reply_count", 0),
            "clicks": 0,
        }

    def _collect_reddit_api(self, post_url: str) -> dict:
        """Use Reddit API (PRAW) to read post metrics.

        Note: PRAW does not expose view counts. For views, use Playwright scraping.
        """
        submission = self._reddit.submission(url=post_url)
        return {
            "impressions": 0,  # PRAW doesn't expose views — Playwright scraper gets them
            "likes": submission.score,
            "reposts": 0,
            "comments": submission.num_comments,
            "clicks": 0,
        }

    async def _collect_playwright(self, post_url: str, platform: str) -> dict:
        """Fallback: use existing Playwright scrapers from metric_scraper.py."""
        from utils.metric_scraper import SCRAPER_MAP, _launch_context
        from playwright.async_api import async_playwright

        scraper = SCRAPER_MAP.get(platform)
        if not scraper:
            raise ValueError(f"No scraper for platform: {platform}")

        async with async_playwright() as pw:
            context = await _launch_context(pw, platform)
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                result = await scraper(page, post_url)
                # Scrapers now return (metrics_dict, status) tuple
                if isinstance(result, tuple):
                    metrics, scrape_status = result
                    if scrape_status == "deleted":
                        raise ValueError(f"Post deleted/unavailable: {post_url}")
                    if scrape_status == "rate_limited":
                        raise ValueError(f"Rate limited while scraping: {post_url}")
                    return metrics
                return result  # Backward compatibility
            finally:
                await context.close()

    @staticmethod
    def _extract_tweet_id(url: str) -> str | None:
        """Extract tweet ID from X/Twitter URL."""
        match = re.search(r'/status/(\d+)', url)
        return match.group(1) if match else None
