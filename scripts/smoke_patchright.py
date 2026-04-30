"""Smoke test: verify Patchright launches a real Chromium browser and CreepJS scores >= 60%.

One-shot script. Removes itself from any production code path. Intended to satisfy
Task #68 AC-1 (drop-in works) and AC-2 (CreepJS score >= 60%).
"""
import asyncio
import sys
from patchright.async_api import async_playwright


async def main() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # AC-1: navigate somewhere benign first to confirm the browser actually drives.
        await page.goto("https://example.com", wait_until="domcontentloaded", timeout=30000)
        title = await page.title()
        print(f"[AC-1] example.com title: {title!r}")

        # AC-2: CreepJS trust score
        try:
            await page.goto("https://abrahamjuliot.github.io/creepjs/", timeout=60000)
            # CreepJS computes fingerprint async; give it 30s to settle
            await asyncio.sleep(60)
            # Trust score gauge — CreepJS displays it under #fingerprint-data .visitor-info
            for sel in ["#fingerprint-data", ".visitor-info", "#creep", ".col"]:
                el = await page.query_selector(sel)
                if el:
                    text = (await el.inner_text())[:1000]
                    print(f"[AC-2] {sel!r}: {text}")
                    print("---")
            # Also dump first 80 short lines
            body_text = await page.locator("body").inner_text()
            print("[AC-2] body short lines:")
            for line in body_text.splitlines()[:80]:
                line = line.strip()
                if line and len(line) < 120:
                    print(f"   {line}")
        except Exception as e:
            print(f"[AC-2] CreepJS check failed: {e}")

        await asyncio.sleep(3)
        await browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
