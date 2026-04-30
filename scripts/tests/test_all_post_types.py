"""Test all post types (text-only, image+text, image-only) on all platforms.

Usage: python scripts/tests/test_all_post_types.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
os.chdir(str(ROOT))
os.environ["HEADLESS"] = "false"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from post import post_to_x, post_to_linkedin, post_to_facebook, post_to_reddit

IMAGE_PATH = str(ROOT / "image.png")
RESULTS = []


async def test_post(platform: str, post_type: str, draft: dict):
    """Test a single post and record the result."""
    from patchright.async_api import async_playwright

    func_map = {
        "x": post_to_x,
        "linkedin": post_to_linkedin,
        "facebook": post_to_facebook,
        "reddit": post_to_reddit,
    }
    func = func_map[platform]
    label = f"{platform.upper()} {post_type}"

    print(f"\n{'='*60}")
    print(f"TESTING: {label}")
    print(f"{'='*60}")

    try:
        async with async_playwright() as pw:
            url = await func(draft, pw)
            result = "SUCCESS" if url else "PARTIAL (no URL)"
            print(f"\n{result}: {label}")
            print(f"  URL: {url}")
            RESULTS.append({"platform": platform, "type": post_type, "status": result, "url": url})
    except Exception as e:
        print(f"\nFAILED: {label}")
        print(f"  Error: {e}")
        RESULTS.append({"platform": platform, "type": post_type, "status": f"FAILED: {e}", "url": None})


async def main():
    # ── X Tests ──
    await test_post("x", "text-only", {
        "content": {"x": "Amplifier test: text-only post on X. Will delete. #test"},
        "id": "test-x-text",
    })
    await test_post("x", "image+text", {
        "content": {"x": "Amplifier test: image+text on X. Will delete. #test"},
        "id": "test-x-imgtext",
        "image_path": IMAGE_PATH,
    })
    await test_post("x", "image-only", {
        "content": {"x": ""},  # Empty text = image-only
        "id": "test-x-imgonly",
        "image_path": IMAGE_PATH,
    })

    # ── LinkedIn Tests ──
    await test_post("linkedin", "text-only", {
        "content": {"linkedin": "Amplifier test: text-only on LinkedIn.\n\nWill delete. #test"},
        "id": "test-li-text",
    })
    await test_post("linkedin", "image+text", {
        "content": {"linkedin": "Amplifier test: image+text on LinkedIn.\n\nWill delete. #test"},
        "id": "test-li-imgtext",
        "image_path": IMAGE_PATH,
    })
    await test_post("linkedin", "image-only", {
        "content": {"linkedin": ""},  # Empty text = image-only (LinkedIn might need some text)
        "id": "test-li-imgonly",
        "image_path": IMAGE_PATH,
    })

    # ── Facebook Tests ──
    await test_post("facebook", "text-only", {
        "content": {"facebook": "Amplifier test: text-only on Facebook. Will delete."},
        "id": "test-fb-text",
    })
    await test_post("facebook", "image+text", {
        "content": {"facebook": "Amplifier test: image+text on Facebook. Will delete."},
        "id": "test-fb-imgtext",
        "image_path": IMAGE_PATH,
    })
    await test_post("facebook", "image-only", {
        "content": {"facebook": ""},  # Empty text = image-only
        "id": "test-fb-imgonly",
        "image_path": IMAGE_PATH,
    })

    # ── Reddit Tests ──
    await test_post("reddit", "text-only", {
        "content": {"reddit": json.dumps({"title": "Amplifier test: text-only on Reddit - will delete", "body": "Automated test post. Please ignore."})},
        "id": "test-rd-text",
    })
    await test_post("reddit", "image+text", {
        "content": {"reddit": json.dumps({"title": "Amplifier test: image+text on Reddit - will delete", "body": "This post has an image. Automated test."})},
        "id": "test-rd-imgtext",
        "image_path": IMAGE_PATH,
    })
    await test_post("reddit", "image-only", {
        "content": {"reddit": json.dumps({"title": "Amplifier test: image-only on Reddit - will delete", "body": ""})},
        "id": "test-rd-imgonly",
        "image_path": IMAGE_PATH,
    })

    # ── Summary ──
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"{'Platform':<12} {'Type':<14} {'Status':<20} {'URL'}")
    print("-" * 90)
    for r in RESULTS:
        url_short = (r["url"] or "None")[:50]
        print(f"{r['platform']:<12} {r['type']:<14} {r['status']:<20} {url_short}")

    passed = sum(1 for r in RESULTS if "SUCCESS" in r["status"] or "PARTIAL" in r["status"])
    failed = sum(1 for r in RESULTS if "FAILED" in r["status"])
    print(f"\n{passed} passed, {failed} failed out of {len(RESULTS)} tests")


if __name__ == "__main__":
    asyncio.run(main())
