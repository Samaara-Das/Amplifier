"""One-time manual login helper — launches a persistent browser for manual login."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from utils.browser_config import apply_full_screen
from utils.guard import filter_disabled


async def run_login(platform: str) -> None:
    from patchright.async_api import async_playwright

    # Load platform config
    config_path = ROOT / "config" / "platforms.json"
    with open(config_path, "r", encoding="utf-8") as f:
        platforms = json.load(f)

    if platform not in platforms:
        print(f"Unknown platform: {platform}")
        print(f"Available: {', '.join(platforms.keys())}")
        sys.exit(1)

    platform_cfg = platforms[platform]
    profile_dir = ROOT / "profiles" / f"{platform}-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    home_url = platform_cfg["home_url"]

    print(f"\n--- Login Setup: {platform_cfg['name']} ---")
    print(f"Profile directory: {profile_dir}")
    print(f"A browser window will open to: {home_url}")
    print("Log in manually, complete any 2FA, then CLOSE the browser window.")
    print("Your session will be saved automatically.\n")

    async with async_playwright() as pw:
        kwargs = dict(
            user_data_dir=str(profile_dir),
            headless=False,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/137.0.0.0 Safari/537.36"
            ),
            args=[
                "--no-sandbox",
            ],
        )
        apply_full_screen(kwargs, headless=False)
        # Proxy support for geo-restricted platforms (e.g. TikTok in India)
        proxy_url = platform_cfg.get("proxy")
        if proxy_url:
            print(f"  Using proxy: {proxy_url}")
            kwargs["proxy"] = {"server": proxy_url}

        context = await pw.chromium.launch_persistent_context(**kwargs)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(home_url)
        print("Waiting for you to log in and close the browser...")

        # Wait until user closes the browser
        try:
            await context.pages[0].wait_for_event("close", timeout=0)
            # Wait a moment for context cleanup
            await asyncio.sleep(1)
        except Exception:
            pass

        try:
            await context.close()
        except Exception:
            pass

    print(f"\nSession saved for {platform_cfg['name']}!")
    print(f"Profile stored in: {profile_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Login setup helper for auto-poster")
    parser.add_argument(
        "platform",
        choices=filter_disabled(["x", "linkedin", "facebook", "instagram", "reddit", "tiktok"]),
        help="Platform to log into",
    )
    args = parser.parse_args()
    asyncio.run(run_login(args.platform))


if __name__ == "__main__":
    main()
