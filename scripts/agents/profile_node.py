"""Profile extraction node — scrapes user's social media profiles for personalization.

Reads from existing Playwright browser profiles. Caches in local DB (weekly refresh).
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent


def profile_node(state: dict) -> dict:
    """Load cached user profiles for enabled platforms.

    If profiles are stale (>7 days), marks them for refresh.
    Actual Playwright scraping is done separately (expensive, async).
    For now, returns whatever we have cached.
    """
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from utils.local_db import get_user_profiles

    platforms = state.get("enabled_platforms", [])
    profiles = {}

    cached = get_user_profiles(platforms) if platforms else get_user_profiles()
    for p in cached:
        platform = p["platform"]
        # Check if stale (>7 days)
        extracted_at = p.get("extracted_at")
        is_stale = True
        if extracted_at:
            try:
                ext_dt = datetime.fromisoformat(extracted_at)
                if ext_dt.tzinfo is None:
                    ext_dt = ext_dt.replace(tzinfo=timezone.utc)
                is_stale = (datetime.now(timezone.utc) - ext_dt) > timedelta(days=7)
            except (ValueError, TypeError):
                pass

        profiles[platform] = {
            "bio": p.get("bio", ""),
            "recent_posts": json.loads(p["recent_posts"]) if p.get("recent_posts") else [],
            "style_notes": p.get("style_notes", ""),
            "follower_count": p.get("follower_count", 0),
            "stale": is_stale,
        }

    if not profiles:
        logger.info("No cached user profiles found — drafts will use generic voice")
    else:
        logger.info("Loaded profiles for %d platform(s): %s",
                     len(profiles), list(profiles.keys()))

    return {"user_profiles": profiles}
