"""Probe — launch Patchright with the project's DNS hardening flags and
exit cleanly. Used by /uat-task 88 AC6 to confirm none of the hardening
flags are rejected by Chromium at startup.

Usage:
    python scripts/uat/probe_dns_hardening.py

Exits 0 on success, 1 on launch failure, 2 on navigation failure.
"""

import asyncio
import sys
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from patchright.async_api import async_playwright

from scripts.utils.browser_config import apply_full_screen, DNS_HARDENING_ARGS


async def main() -> int:
    print(f"DNS_HARDENING_ARGS = {DNS_HARDENING_ARGS}")
    kwargs = dict(headless=True, args=[])
    apply_full_screen(kwargs, headless=True)
    print(f"effective args = {kwargs['args']}")

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True, args=kwargs["args"])
        except Exception as e:
            print(f"FAIL — launch error: {type(e).__name__}: {e}")
            return 1

        try:
            page = await browser.new_page()
            await page.goto("about:blank", timeout=15_000)
            title = await page.title()
            print(f"navigated to about:blank — title={title!r}")
        except Exception as e:
            await browser.close()
            print(f"FAIL — navigation error: {type(e).__name__}: {e}")
            return 2
        finally:
            await browser.close()

    print("PASS — browser launched and closed cleanly with all hardening flags")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
