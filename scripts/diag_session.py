"""Quick diagnostic: check if browser sessions are alive for each platform."""
import asyncio, json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from pathlib import Path
from patchright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent

with open(ROOT / "config" / "platforms.json") as f:
    PLATFORMS = json.load(f)

STEALTH_ARGS = [
    "--no-sandbox", "--disable-infobars", "--disable-dev-shm-usage",
    "--disable-gpu", "--lang=en-US,en",
]
STEALTH_JS = 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'

HEADED_PLATFORMS = {"reddit"}

URLS = {
    "linkedin": "https://www.linkedin.com/in/me/",
    "facebook": "https://www.facebook.com/me",
    "reddit": "https://www.reddit.com/user/me/",
}

async def check(platform):
    url = URLS[platform]
    profile_dir = ROOT / "profiles" / f"{platform}-profile"
    if not profile_dir.exists():
        print(f"  {platform}: NO PROFILE DIR")
        return

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=platform not in HEADED_PLATFORMS,
            viewport={"width": 1280, "height": 800},
            args=STEALTH_ARGS,
        )
        for p in ctx.pages:
            await p.add_init_script(STEALTH_JS)
        ctx.on("page", lambda p: p.add_init_script(STEALTH_JS))

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(4000)
        except Exception as e:
            print(f"  {platform}: NAVIGATION FAILED — {e}")
            await ctx.close()
            return

        final_url = page.url
        body = ""
        try:
            body = await page.inner_text("body", timeout=10000)
        except:
            body = "(failed to get body text)"

        # Save screenshot
        ss_path = ROOT / f"diag_{platform}.png"
        await page.screenshot(path=str(ss_path), full_page=False)

        print(f"\n  {platform}:")
        print(f"    Final URL: {final_url}")
        print(f"    Body length: {len(body)} chars")
        print(f"    First 300 chars: {body[:300]}")
        print(f"    Screenshot: {ss_path}")

        # Check for login/block indicators
        body_lower = body.lower()
        if "sign in" in body_lower or "log in" in body_lower or "join now" in body_lower:
            print(f"    WARNING: SESSION EXPIRED -- login page detected")
        elif "captcha" in body_lower or "verify" in body_lower or "security check" in body_lower:
            print(f"    WARNING: CAPTCHA/VERIFICATION -- blocked")
        elif len(body) < 100:
            print(f"    WARNING: VERY SHORT BODY -- possible error page")
        else:
            print(f"    OK: Session looks alive")

        await ctx.close()

async def main():
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["linkedin", "facebook", "reddit"]
    for p in targets:
        await check(p)

if __name__ == "__main__":
    asyncio.run(main())
