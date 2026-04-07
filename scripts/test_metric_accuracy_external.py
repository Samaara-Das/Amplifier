"""Test metric scraping against external posts with real engagement."""

import asyncio
import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.metric_scraper import (
    _scrape_x, _scrape_linkedin, _scrape_facebook, _scrape_reddit,
    _launch_context,
)

logging.basicConfig(
    level="INFO",
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)

TESTS = [
    ("x", "https://x.com/Puppieslover/status/2041127179304542616"),
    ("x", "https://x.com/JulianGoldieSEO/status/2041041243560685581"),
    ("facebook", "https://www.facebook.com/share/p/1HpgLoSPYg/"),
    ("facebook", "https://www.facebook.com/permalink.php?story_fbid=pfbid02eWZAPgYy4ShUB4PGN9UD2kp7VCCLjciLyM2bvFzFSZjz651YGWHL52CkwvivFXmTl&id=61560960032768"),
    ("linkedin", "https://www.linkedin.com/posts/vik-gambhir_everyones-suddenly-under-nda-nda-can-share-7443130134724870145-gUA2"),
    ("linkedin", "https://www.linkedin.com/posts/terry-kinder-9a08a23_djia-expected-price-range-for-2026-04-06-share-7446935576618053632-168Q"),
    ("reddit", "https://www.reddit.com/r/IndianTeenagers/comments/1sdtehv/tum_log_gaane_kahan_sunte_ho/"),
    ("reddit", "https://www.reddit.com/r/sidehustleIndia/comments/1se0eex/college_asking_4k_for_exam/"),
]

SCRAPER_MAP = {
    "x": _scrape_x,
    "linkedin": _scrape_linkedin,
    "facebook": _scrape_facebook,
    "reddit": _scrape_reddit,
}


async def main():
    from playwright.async_api import async_playwright

    results = []

    async with async_playwright() as pw:
        # Group by platform so we reuse browser contexts
        by_platform = {}
        for platform, url in TESTS:
            by_platform.setdefault(platform, []).append(url)

        for platform, urls in by_platform.items():
            scraper = SCRAPER_MAP[platform]
            context = await _launch_context(pw, platform)
            page = context.pages[0] if context.pages else await context.new_page()

            for url in urls:
                print(f"\n--- {platform.upper()}: {url[:80]}{'...' if len(url)>80 else ''} ---")

                try:
                    metrics, status = await scraper(page, url)

                    # Screenshot for verification
                    short_name = re.sub(r'[^\w\-]', '_', url.split("/")[-1][:30]) or platform
                    screenshot_path = ROOT / "logs" / f"ext_{platform}_{short_name}.png"
                    screenshot_path.parent.mkdir(exist_ok=True)
                    await page.screenshot(path=str(screenshot_path))

                    print(f"  Status:      {status or 'OK (live)'}")
                    print(f"  Impressions: {metrics.get('impressions', 0)}")
                    print(f"  Likes:       {metrics.get('likes', 0)}")
                    print(f"  Reposts:     {metrics.get('reposts', 0)}")
                    print(f"  Comments:    {metrics.get('comments', 0)}")
                    print(f"  Screenshot:  {screenshot_path}")

                    total = sum(metrics.values())
                    results.append((platform, url, metrics, status, total))

                except Exception as e:
                    print(f"  ERROR: {e}")
                    results.append((platform, url, {}, "error", 0))

            await context.close()

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for platform, url, metrics, status, total in results:
        short = url.split("/status/")[-1][:20] if "/status/" in url else url.split("/")[-1][:20]
        if status == "deleted":
            verdict = "DELETED"
        elif status == "rate_limited":
            verdict = "RATE LIMITED"
        elif status == "error":
            verdict = "ERROR"
        elif total > 0:
            m = metrics
            verdict = f"imp={m.get('impressions',0)} likes={m.get('likes',0)} reposts={m.get('reposts',0)} comments={m.get('comments',0)}"
        else:
            verdict = "ALL ZEROS"
        print(f"  {platform.upper():10s} {short:22s} {verdict}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
