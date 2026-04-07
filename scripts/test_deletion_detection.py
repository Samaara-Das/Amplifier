"""Test deleted post detection across all 4 platforms.

Visits known-deleted post URLs and verifies the scraper correctly identifies
each as deleted. Uses the same _scrape_* functions from metric_scraper.py.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from playwright.async_api import async_playwright

# Import the actual scraper functions
from utils.metric_scraper import (
    _scrape_x,
    _scrape_linkedin,
    _scrape_facebook,
    _scrape_reddit,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Deleted post URLs — all confirmed deleted by user
TEST_URLS = [
    ("facebook", "https://www.facebook.com/share/p/1DNzwjPaPn/"),
    ("facebook", "https://www.facebook.com/photo/?fbid=931709233054001&set=a.923621633862761"),
    ("linkedin", "https://www.linkedin.com/feed/update/urn:li:activity:7246599338368413701"),
    ("x", "https://x.com/SamaaraDas/status/2041143197427269750"),
    ("reddit", "https://www.reddit.com/user/SamaaraDas/comments/1sdzj1b/url_capture_test_round_6/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button"),
]

SCRAPER_MAP = {
    "x": _scrape_x,
    "linkedin": _scrape_linkedin,
    "facebook": _scrape_facebook,
    "reddit": _scrape_reddit,
}


async def test_platform(pw, platform: str, url: str) -> dict:
    """Test deletion detection for a single platform."""
    profile_dir = ROOT / "profiles" / f"{platform}-profile"
    if not profile_dir.exists():
        return {"platform": platform, "status": "SKIP", "reason": f"No profile at {profile_dir}"}

    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36"
        ),
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )

    try:
        page = context.pages[0] if context.pages else await context.new_page()
        scraper_fn = SCRAPER_MAP[platform]

        logger.info("Testing %s: %s", platform.upper(), url)
        metrics, scrape_status = await scraper_fn(page, url)

        detected = scrape_status == "deleted"
        return {
            "platform": platform,
            "url": url,
            "detected_deleted": detected,
            "scrape_status": scrape_status,
            "metrics": metrics,
            "status": "PASS" if detected else "FAIL",
        }
    except Exception as e:
        return {
            "platform": platform,
            "url": url,
            "status": "ERROR",
            "error": str(e),
        }
    finally:
        await context.close()


async def main():
    print("\n" + "=" * 70)
    print("  DELETED POST DETECTION TEST — 4 Platforms")
    print("=" * 70 + "\n")

    results = []

    async with async_playwright() as pw:
        # Run each platform sequentially (each needs its own browser context)
        for platform, url in TEST_URLS:
            result = await test_platform(pw, platform, url)
            results.append(result)

            status_icon = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP", "ERROR": "ERR "}[result["status"]]
            print(f"  [{status_icon}] {platform.upper():10s} — detected_deleted={result.get('detected_deleted', 'N/A')}, "
                  f"scrape_status={result.get('scrape_status', 'N/A')}")
            if result["status"] == "ERROR":
                print(f"           Error: {result['error']}")
            if result["status"] == "FAIL":
                print(f"           Metrics returned: {result.get('metrics', {})}")
            print()

    # Summary
    print("\n" + "=" * 70)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")
    skipped = sum(1 for r in results if r["status"] == "SKIP")
    total = len(results)

    print(f"  RESULTS: {passed}/{total} passed, {failed} failed, {errors} errors, {skipped} skipped")

    if failed > 0:
        print("\n  FAILED platforms:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"    - {r['platform'].upper()}: scrape_status={r['scrape_status']}, metrics={r.get('metrics', {})}")

    print("=" * 70 + "\n")

    return all(r["status"] == "PASS" for r in results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
