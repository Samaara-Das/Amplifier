"""Test script for Task #6 — Metrics Accuracy verification.

Phase 1: Live scraping — scrape one real post per platform, verify metrics extracted.
Phase 2: Deletion detection — scrape known-deleted posts, verify detection.

Run: python scripts/test_metric_accuracy.py [phase1|phase2]
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.metric_scraper import (
    _scrape_x, _scrape_linkedin, _scrape_facebook, _scrape_reddit,
    _launch_context, _warn_if_all_zero,
)

logging.basicConfig(
    level="INFO",
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ── Test URLs ──────────────────────────────────────────────────────────
# Phase 1: Live posts (should return real metrics)
LIVE_POSTS = {
    "x": {
        "id": 72,
        "url": "https://x.com/SamaaraDas/status/2041144200289464455",
    },
    "linkedin": {
        "id": 48,
        "url": "https://www.linkedin.com/feed/update/urn:li:share:7446191607688671232/",
    },
    "facebook": {
        "id": 84,
        "url": "https://www.facebook.com/permalink.php?story_fbid=pfbid0TNU9kgoLRJfVbMA2ej8nhjq2jshiKwcx2t2A9Ei8rSpQqeB4cCtorAdZCYnknYK6l&id=100086447984609",
    },
    "reddit": {
        "id": 83,
        "url": "https://www.reddit.com/user/SamaaraDas/comments/1sdzj1b/url_capture_test_round_6/",
    },
}

# Phase 2: Posts the user will delete before running this phase
DELETE_POSTS = {
    "x": {
        "id": 71,
        "url": "https://x.com/SamaaraDas/status/2041143912233082899",
    },
    "linkedin": {
        "id": 73,
        "url": "https://www.linkedin.com/feed/update/urn:li:share:7446910068303953920/",
    },
    "facebook": {
        "id": 80,
        "url": "https://www.facebook.com/permalink.php?story_fbid=pfbid031Sryo9T3buHibS23ZAby7A9tUfYXHx6UP35mrF13zQHAMh5XyUo7MH2qk6TZnv8xl&id=100086447984609",
    },
    "reddit": {
        "id": 81,
        "url": "https://www.reddit.com/r/fintech/comments/1rngxtn/the_most_underused_feature_of_ai_coding/",
    },
}

SCRAPER_MAP = {
    "x": _scrape_x,
    "linkedin": _scrape_linkedin,
    "facebook": _scrape_facebook,
    "reddit": _scrape_reddit,
}


async def run_phase(posts: dict, phase_name: str):
    """Scrape each platform and report results."""
    from playwright.async_api import async_playwright

    results = {}
    print(f"\n{'='*60}")
    print(f"  {phase_name}")
    print(f"{'='*60}\n")

    async with async_playwright() as pw:
        for platform, post_info in posts.items():
            print(f"\n--- {platform.upper()} ---")
            print(f"URL: {post_info['url']}")

            scraper = SCRAPER_MAP.get(platform)
            if not scraper:
                print(f"  SKIP: No scraper for {platform}")
                continue

            try:
                context = await _launch_context(pw, platform)
                page = context.pages[0] if context.pages else await context.new_page()

                metrics, status = await scraper(page, post_info["url"])

                # Debug: capture page title and screenshot for diagnosis
                title = await page.title()
                print(f"  Page title: {title}")
                screenshot_path = ROOT / "logs" / f"scrape_test_{platform}.png"
                screenshot_path.parent.mkdir(exist_ok=True)
                await page.screenshot(path=str(screenshot_path))
                print(f"  Screenshot: {screenshot_path}")

                results[platform] = {
                    "metrics": metrics,
                    "status": status,
                }

                if status == "deleted":
                    print(f"  STATUS: DELETED detected")
                elif status == "rate_limited":
                    print(f"  STATUS: RATE LIMITED")
                else:
                    print(f"  STATUS: OK (live post)")

                print(f"  Impressions: {metrics.get('impressions', 0)}")
                print(f"  Likes:       {metrics.get('likes', 0)}")
                print(f"  Reposts:     {metrics.get('reposts', 0)}")
                print(f"  Comments:    {metrics.get('comments', 0)}")

                # Check if all zeros (warning test)
                all_zero = all(v == 0 for v in [
                    metrics.get("impressions", 0),
                    metrics.get("likes", 0),
                    metrics.get("reposts", 0),
                    metrics.get("comments", 0),
                ])
                if all_zero and status is None:
                    print(f"  WARNING: All metrics are zero on a live post!")

                await context.close()

            except Exception as e:
                print(f"  ERROR: {e}")
                results[platform] = {"error": str(e)}

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY -- {phase_name}")
    print(f"{'='*60}")
    for platform, result in results.items():
        if "error" in result:
            print(f"  {platform.upper():10s} ERROR: {result['error']}")
        else:
            status = result["status"]
            m = result["metrics"]
            total = sum(m.values())
            if status == "deleted":
                print(f"  {platform.upper():10s} DELETED detected [PASS]")
            elif status == "rate_limited":
                print(f"  {platform.upper():10s} RATE LIMITED (skip)")
            elif total > 0:
                print(f"  {platform.upper():10s} OK -- imp={m['impressions']} likes={m['likes']} reposts={m['reposts']} comments={m['comments']} [PASS]")
            else:
                print(f"  {platform.upper():10s} ALL ZEROS -- possible scraper issue or expired session [CHECK]")
    print()


async def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "phase1"

    if phase == "phase1":
        await run_phase(LIVE_POSTS, "PHASE 1: Live Scraping Accuracy")
    elif phase == "phase2":
        await run_phase(DELETE_POSTS, "PHASE 2: Deleted Post Detection")
    elif phase == "both":
        await run_phase(LIVE_POSTS, "PHASE 1: Live Scraping Accuracy")
        await run_phase(DELETE_POSTS, "PHASE 2: Deleted Post Detection")
    else:
        print(f"Usage: python {sys.argv[0]} [phase1|phase2|both]")
        print("  phase1: Test live scraping on real posts")
        print("  phase2: Test deletion detection (delete posts first!)")


if __name__ == "__main__":
    asyncio.run(main())
