"""Test posting to each platform in headed mode.

Usage:
    python scripts/tests/test_posting.py linkedin
    python scripts/tests/test_posting.py x
    python scripts/tests/test_posting.py facebook
    python scripts/tests/test_posting.py reddit
    python scripts/tests/test_posting.py all
"""
import asyncio
import os
import sys
import logging
from pathlib import Path

# Setup
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
os.chdir(str(ROOT))

# Force headed mode for debugging
os.environ["HEADLESS"] = "false"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TEST_CONTENT = {
    "x": "Testing Amplifier posting system. This is an automated test post. Please ignore. #test #amplifier",
    "linkedin": "Testing the Amplifier posting system.\n\nThis is an automated test post to verify that the posting pipeline works correctly.\n\nPlease ignore this post — it will be deleted shortly.\n\n#test #amplifier",
    "facebook": "Testing Amplifier posting system. This is an automated test post. Please ignore.",
    "reddit": '{"title": "Test post from Amplifier - please ignore", "body": "This is an automated test post from the Amplifier posting system. Testing that the posting pipeline works correctly. Will be deleted shortly."}',
}


async def test_platform(platform: str):
    """Test posting to a single platform."""
    from patchright.async_api import async_playwright

    content = TEST_CONTENT.get(platform)
    if not content:
        print(f"Unknown platform: {platform}")
        return

    # Import the posting function
    from post import post_to_x, post_to_linkedin, post_to_facebook, post_to_reddit

    platform_funcs = {
        "x": post_to_x,
        "linkedin": post_to_linkedin,
        "facebook": post_to_facebook,
        "reddit": post_to_reddit,
    }

    func = platform_funcs[platform]
    draft = {
        "content": {platform: content},
        "id": "test-001",
    }

    print(f"\n{'='*60}")
    print(f"TESTING: {platform.upper()}")
    print(f"{'='*60}")
    print(f"Content: {content[:100]}...")
    print(f"Headed mode: {os.environ.get('HEADLESS', 'not set')}")
    print()

    try:
        async with async_playwright() as pw:
            post_url = await func(draft, pw)
            if post_url:
                print(f"\n✓ SUCCESS: Posted to {platform}")
                print(f"  URL: {post_url}")
            else:
                print(f"\n⚠ PARTIAL: Post sent but URL not captured")
    except Exception as e:
        print(f"\n✗ FAILED: {platform}")
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    platform = sys.argv[1] if len(sys.argv) > 1 else "all"

    if platform == "all":
        for p in ["linkedin", "facebook", "reddit", "x"]:
            await test_platform(p)
    else:
        await test_platform(platform)


if __name__ == "__main__":
    asyncio.run(main())
