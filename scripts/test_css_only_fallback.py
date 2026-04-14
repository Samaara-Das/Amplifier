"""Task #5 P2.2 — Verify CSS-only fallback when no AI keys.

Temporarily clears Gemini/Mistral/Groq keys from both local_db and
process env, runs the scraper for LinkedIn/Facebook/Reddit, checks that
CSS fallback returns usable data, then RESTORES the keys.

Safety: keys are backed up in memory only and restored in a finally block.
If this script is killed mid-run, restore by re-running onboarding or
setting keys manually via the settings page.
"""
import asyncio
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

from utils.local_db import get_setting, set_setting

KEYS = ["gemini_api_key", "mistral_api_key", "groq_api_key"]
ENV_KEYS = ["GEMINI_API_KEY", "MISTRAL_API_KEY", "GROQ_API_KEY"]


def backup_and_clear():
    """Back up all API keys (in memory) and clear them."""
    local_backup = {}
    for k in KEYS:
        v = get_setting(k)
        local_backup[k] = v
        set_setting(k, "")

    env_backup = {}
    for k in ENV_KEYS:
        v = os.environ.get(k)
        env_backup[k] = v
        if v:
            os.environ.pop(k, None)

    return local_backup, env_backup


def restore(local_backup, env_backup):
    """Restore all API keys."""
    for k, v in local_backup.items():
        if v:
            set_setting(k, v)
    for k, v in env_backup.items():
        if v:
            os.environ[k] = v


def check_result(platform: str, data: dict) -> dict:
    """Return a pass/fail summary for CSS-only result."""
    if not isinstance(data, dict) or "error" in data:
        return {"status": "ERROR", "error": data.get("error") if isinstance(data, dict) else "no data"}
    summary = {
        "display_name": data.get("display_name"),
        "follower_count": data.get("follower_count", 0),
        "recent_posts_count": len(data.get("recent_posts", [])),
        "status": "OK" if data.get("display_name") else "MISSING display_name",
    }
    return summary


async def main():
    local_backup, env_backup = backup_and_clear()
    try:
        print("=" * 60)
        print("API KEYS CLEARED — Testing CSS-only fallback")
        print("=" * 60)

        # Verify keys are actually cleared
        print(f"\nlocal_db gemini: {repr(get_setting('gemini_api_key'))}")
        print(f"env GEMINI_API_KEY: {repr(os.environ.get('GEMINI_API_KEY'))}")

        from utils.profile_scraper import scrape_all_profiles

        results = await scrape_all_profiles(["linkedin", "facebook", "reddit"])

        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)

        all_pass = True
        for platform in ["linkedin", "facebook", "reddit"]:
            data = results.get(platform, {})
            summary = check_result(platform, data)
            print(f"\n{platform}: {summary}")
            if summary.get("status") != "OK":
                all_pass = False

        print("\n" + "=" * 60)
        print(f"OVERALL: {'PASS' if all_pass else 'FAIL'}")
        print("=" * 60)
    finally:
        restore(local_backup, env_backup)
        # Verify restored
        print(f"\nKeys restored. gemini: {'SET' if get_setting('gemini_api_key') else 'STILL EMPTY'}")


if __name__ == "__main__":
    asyncio.run(main())
