"""Diagnostic: Use our Reddit session to check shreddit-post 'score' attribute
on a high-engagement user, verifying the scraper extracts scores correctly.
"""
import asyncio
import sys
import os
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

ROOT = Path(__file__).resolve().parent.parent


async def main():
    # Test against a known high-engagement user
    test_users = [
        "https://www.reddit.com/user/spez/submitted/",
        "https://www.reddit.com/user/GallowBoob/submitted/",
    ]

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(ROOT / "profiles" / "reddit-profile"),
            headless=False,  # Reddit blocks headless
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        for url in test_users:
            print(f"\n{'=' * 60}")
            print(f"Testing: {url}")
            print('=' * 60)

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
            # Scroll to load more posts
            for _ in range(3):
                await page.mouse.wheel(0, 800)
                await page.wait_for_timeout(1500)

            # Check shreddit-post attributes
            result = await page.evaluate("""() => {
                const posts = document.querySelectorAll('shreddit-post');
                return Array.from(posts).slice(0, 10).map(p => ({
                    title: (p.getAttribute('post-title') || '').substring(0, 60),
                    score: p.getAttribute('score'),
                    comments: p.getAttribute('comment-count'),
                    permalink: (p.getAttribute('permalink') || '').substring(0, 60),
                    has_score_attr: p.hasAttribute('score'),
                    all_attrs: Array.from(p.attributes).map(a => a.name).filter(n => !n.startsWith('author-')),
                }));
            }""")

            print(f"Found {len(result)} shreddit-post elements")
            for i, p in enumerate(result[:5]):
                print(f"\n  [{i}] {p['title']}...")
                print(f"      score = {p['score']} (attr present: {p['has_score_attr']})")
                print(f"      comments = {p['comments']}")
                print(f"      attrs: {p['all_attrs'][:8]}")

        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
