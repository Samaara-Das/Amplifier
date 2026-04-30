"""Debug script to test Facebook post extraction."""
import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from patchright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent.parent

JS_EXTRACT_POSTS = """() => {
    const results = [];
    // Find all "Comment" buttons - more reliable than Like for post detection
    const commentBtns = document.querySelectorAll('div[aria-label="Leave a comment"], div[aria-label="Write a comment"]');
    const seen = new Set();

    // Also try: divs containing "Comment as" text
    const allDivs = document.querySelectorAll('div');
    const commentAsEls = [];
    for (const d of allDivs) {
        if (d.getAttribute('aria-label') && d.getAttribute('aria-label').startsWith('Comment as')) {
            commentAsEls.push(d);
        }
    }

    const anchors = commentAsEls.length > 0 ? commentAsEls : commentBtns;

    for (const anchor of anchors) {
        let el = anchor;
        // Walk up to find a container that has substantial content
        for (let i = 0; i < 20; i++) {
            el = el.parentElement;
            if (!el) break;
            const text = el.innerText || "";
            // A real post container: has substantial text, "Like", not too large
            if (text.length > 100 && text.length < 5000 && !seen.has(text.substring(0, 80))) {
                if ((text.includes("Like") || text.includes("like")) && text.includes("Comment")) {
                    seen.add(text.substring(0, 80));
                    results.push({
                        text: text.substring(0, 800),
                        full_length: text.length
                    });
                    break;
                }
            }
        }
    }
    return results;
}"""


async def main():
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(ROOT / "profiles" / "facebook-profile"),
            headless=True,
            viewport={"width": 1280, "height": 900},
            args=[],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.facebook.com/me", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(4000)
        for _ in range(3):
            await page.mouse.wheel(0, 800)
            await page.wait_for_timeout(1500)

        # Dump body text to find post patterns
        body = await page.inner_text("body")
        lines = [l.strip() for l in body.split("\n") if l.strip()]

        # Find "Comment as" markers — each one follows a post
        for i, line in enumerate(lines):
            if "Comment as" in line:
                # Print surrounding context (the post content is above this marker)
                start = max(0, i - 15)
                print(f"\n=== Post block ending at line {i} ===")
                for j in range(start, min(i + 2, len(lines))):
                    print(f"  [{j}] {lines[j][:150]}")
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
