"""Delete a UAT-posted social media post using the user's persistent Playwright profile.

Used by AC17 cleanup. Each platform has different delete UIs; this script tries
each platform's known affordances and falls back to "find anything labeled
delete" if the named selector misses.

Usage:
    python scripts/uat/delete_post.py --url <post_url> --platform <linkedin|facebook|reddit>

Exit codes:
    0 = post deleted (verified)
    1 = could not delete (post still live or unreachable)
    2 = bad arguments / missing profile
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout

ROOT = Path(__file__).resolve().parent.parent.parent
PROFILES = ROOT / "profiles"
SCREENSHOTS = ROOT / "data" / "uat" / "screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)


async def _try_click(page: Page, selectors: list[str], timeout: int = 5000) -> bool:
    """Try a list of selectors; click the first that matches and is visible."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=timeout)
            await loc.click()
            return True
        except (PWTimeout, Exception):
            continue
    return False


async def delete_linkedin(page: Page, url: str) -> bool:
    """LinkedIn: click overflow menu (Open control menu / 3-dot) → Delete post → Delete."""
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    # Overflow menu — multiple selectors LinkedIn may use
    if not await _try_click(page, [
        'button[aria-label*="control menu" i]',
        'button[aria-label*="open control" i]',
        'button[aria-label*="more" i]:visible',
        '[data-test-icon="ellipsis-horizontal"]',
        'button:has(svg[data-test-icon="ellipsis-horizontal"])',
    ]):
        return False
    await page.wait_for_timeout(1500)
    # Delete option in the dropdown
    if not await _try_click(page, [
        'div[role="menuitem"]:has-text("Delete")',
        'button:has-text("Delete post")',
        'span:has-text("Delete post")',
        '[role="menuitem"]:has-text("Delete")',
    ]):
        return False
    await page.wait_for_timeout(1500)
    # Confirmation modal
    if not await _try_click(page, [
        'button:has-text("Delete"):visible',
        'button[data-control-name="delete_confirm" i]',
    ]):
        return False
    await page.wait_for_timeout(3000)
    # Verify: navigate back to the URL, expect "this content is not available" or 404
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    body = (await page.content()).lower()
    return any(s in body for s in [
        "this content isn't available", "this content is no longer available",
        "this post has been removed", "page not found",
        "post not found", "this post was deleted or removed",
    ])


async def delete_facebook(page: Page, url: str) -> bool:
    """Facebook: 3-dot overflow → Move to trash → Move to trash. Tries multiple selector variants."""
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(4000)
    # Try several patterns for the overflow button. FB localizes aria-labels.
    overflow_selectors = [
        'div[aria-label="Actions for this post"]',
        'div[aria-label*="actions" i]',
        '[role="button"][aria-label*="Actions" i]',
        '[aria-label*="Menu" i][role="button"]',
        # Inside dialog/permalink view
        'div[role="dialog"] [aria-label*="actions" i]',
        # Generic horizontal-3-dots SVG button
        'div[role="button"]:has(svg[aria-label*="more" i])',
        'div[role="button"]:has(i[data-visualcompletion="css-img"][style*="-13"])',
    ]
    clicked = False
    for sel in overflow_selectors:
        try:
            await page.locator(sel).first.click(timeout=4000)
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        # Last resort: try keyboard shortcut (FB has 'a' for actions on focused post)
        try:
            await page.keyboard.press("a")
            await page.wait_for_timeout(1000)
        except Exception:
            return False
    await page.wait_for_timeout(2000)
    # Click "Move to trash" or "Delete post"
    delete_clicked = False
    for sel in [
        'div[role="menuitem"]:has-text("Move to trash")',
        'div[role="menuitem"]:has-text("Delete")',
        'span:has-text("Move to trash")',
        'span:has-text("Delete post")',
        'span:has-text("Delete")',
    ]:
        try:
            await page.locator(sel).first.click(timeout=3000)
            delete_clicked = True
            break
        except Exception:
            continue
    if not delete_clicked:
        try:
            await page.get_by_text("Move to trash", exact=False).first.click(timeout=3000)
            delete_clicked = True
        except Exception:
            try:
                await page.get_by_text("Delete", exact=True).first.click(timeout=3000)
                delete_clicked = True
            except Exception:
                return False
    await page.wait_for_timeout(2000)
    # Confirm modal
    confirm_clicked = False
    for sel in [
        'div[aria-label="Move to trash"][role="button"]',
        'div[aria-label="Move"][role="button"]',
        'div[aria-label="Delete"][role="button"]',
        'button:has-text("Move to trash"):visible',
        'button:has-text("Move"):visible',
        'button:has-text("Delete"):visible',
    ]:
        try:
            await page.locator(sel).first.click(timeout=3000)
            confirm_clicked = True
            break
        except Exception:
            continue
    if not confirm_clicked:
        try:
            await page.get_by_role("button", name="Move to trash").last.click(timeout=3000)
            confirm_clicked = True
        except Exception:
            try:
                await page.get_by_role("button", name="Delete").last.click(timeout=3000)
                confirm_clicked = True
            except Exception:
                pass
    await page.wait_for_timeout(4000)
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(2500)
    body = (await page.content()).lower()
    return any(s in body for s in [
        "this content isn't available", "the link you followed",
        "this post is no longer available", "content not found",
        "this content is no longer available",
        "you've moved this post to your trash",
    ])


async def delete_reddit(page: Page, url: str) -> bool:
    """Reddit: prefer old.reddit.com which has a flat 'delete' link. Fall back to new UI."""
    # old.reddit.com has a simple "delete" link visible directly under the post
    old_url = url.replace("www.reddit.com", "old.reddit.com").replace("//reddit.com", "//old.reddit.com")
    await page.goto(old_url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(2500)
    # Click the "delete" link
    try:
        await page.locator('a:has-text("delete")').first.click(timeout=5000)
        await page.wait_for_timeout(1500)
        # Old reddit shows "yes / no" — click yes
        await page.locator('a.yes:has-text("yes"), a:has-text("yes")').first.click(timeout=5000)
        await page.wait_for_timeout(3000)
        # Verify
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        body = (await page.content()).lower()
        if any(s in body for s in [
            "sorry, this post was removed", "sorry, this post was deleted",
            "this post was removed", "this post was deleted", "page not found",
            "post not found", "[deleted]",
        ]):
            return True
    except Exception as e:
        print(f"old.reddit.com path failed: {e}, falling back to new UI", file=sys.stderr)
    # Fallback to new UI
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    if not await _try_click(page, [
        'button[aria-label="More options"]',
        'shreddit-post button[aria-label="More options"]',
        'button[aria-label*="post overflow" i]',
        'button:has(svg[icon-name="overflow-horizontal-outline"])',
        'faceplate-dropdown-menu button',
    ]):
        return False
    await page.wait_for_timeout(1500)
    # Reddit's menu items are rendered as buttons/divs with specific data-testid or just text.
    clicked = False
    for sel in [
        'button:has-text("Delete"):visible',
        '[role="menuitem"]:has-text("Delete"):visible',
        'a:has-text("Delete"):visible',
        'div:has-text("Delete"):visible',
    ]:
        try:
            loc = page.locator(sel).filter(has_text="Delete").first
            await loc.wait_for(state="visible", timeout=3000)
            await loc.click(force=True)
            clicked = True
            break
        except Exception:
            continue
    if not clicked:
        # Last resort: click by text
        try:
            await page.get_by_text("Delete", exact=True).first.click(force=True, timeout=3000)
            clicked = True
        except Exception:
            return False
    await page.wait_for_timeout(2000)
    # Confirmation modal — Reddit's confirm button text is typically "Delete"
    confirm_clicked = False
    for sel in [
        'shreddit-async-loader[bundlename="confirm_delete_modal"] button:has-text("Delete")',
        'button[name="delete"]',
        'faceplate-dialog button:has-text("Delete")',
    ]:
        try:
            await page.locator(sel).first.click(timeout=3000)
            confirm_clicked = True
            break
        except Exception:
            continue
    if not confirm_clicked:
        try:
            # Look for any "Delete" button that's NOT the menu item we just clicked
            await page.get_by_role("button", name="Delete").last.click(timeout=3000)
            confirm_clicked = True
        except Exception:
            pass
    await page.wait_for_timeout(3000)
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    body = (await page.content()).lower()
    return any(s in body for s in [
        "sorry, this post was removed", "sorry, this post was deleted",
        "this post was removed", "this post was deleted", "page not found",
        "post not found", "[deleted]", "this post is no longer available",
    ])


HANDLERS = {
    "linkedin": delete_linkedin,
    "facebook": delete_facebook,
    "reddit": delete_reddit,
}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--platform", required=True, choices=list(HANDLERS))
    parser.add_argument("--headless", action="store_true", default=False)
    parser.add_argument(
        "--update-local-db",
        action="store_true",
        help="On verified deletion, set local_post.status='deleted' for the matching post_url. "
             "Keeps the dashboard's post count honest after UAT cleanup.",
    )
    args = parser.parse_args()

    profile_dir = PROFILES / f"{args.platform}-profile"
    if not profile_dir.exists():
        print(f"ERROR: profile not found at {profile_dir}", file=sys.stderr)
        return 2

    handler = HANDLERS[args.platform]

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=args.headless,
            viewport={"width": 1920, "height": 1080},
            args=["--start-maximized"] if not args.headless else [],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            ok = await handler(page, args.url)
            ts = int(time.time())
            shot = SCREENSHOTS / f"task14_ac17_deleted_{args.platform}_{ts}.png"
            await page.screenshot(path=str(shot), full_page=False)
            print(f"deletion_verified={ok} screenshot={shot}")
            if ok and args.update_local_db:
                try:
                    sys.path.insert(0, str(ROOT / "scripts"))
                    from utils.local_db import _get_db
                    conn = _get_db()
                    n = conn.execute(
                        "UPDATE local_post SET status='deleted' WHERE post_url = ?",
                        (args.url,),
                    ).rowcount
                    conn.commit()
                    print(f"local_post: marked {n} row(s) status='deleted' for url")
                except Exception as e:
                    print(f"local_db update warning: {e}", file=sys.stderr)
            return 0 if ok else 1
        except Exception as e:
            print(f"ERROR during {args.platform} delete: {e}", file=sys.stderr)
            try:
                ts = int(time.time())
                shot = SCREENSHOTS / f"task14_ac17_delete_failed_{args.platform}_{ts}.png"
                await page.screenshot(path=str(shot), full_page=False)
                print(f"failure_screenshot={shot}", file=sys.stderr)
            except Exception:
                pass
            return 1
        finally:
            await ctx.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
