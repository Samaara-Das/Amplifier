"""Post scheduling engine for Amplifier v2.

Determines optimal posting times based on campaign target region,
peak engagement windows, spacing rules, and daily limits.
Manages the schedule queue and executes posts via the existing post.py functions.
"""

import logging
import random
import zoneinfo
from datetime import datetime, timedelta, timezone

from utils.local_db import (
    add_post,
    add_scheduled_post,
    get_scheduled_posts,
    update_schedule_status,
)

logger = logging.getLogger(__name__)


# ── Region-to-Timezone Mapping ───────────────────────────────────────


REGION_TIMEZONES: dict[str, str] = {
    "us": "America/New_York",
    "uk": "Europe/London",
    "india": "Asia/Kolkata",
    "eu": "Europe/Berlin",
    "latam": "America/Sao_Paulo",
    "sea": "Asia/Singapore",
    "global": "America/New_York",  # default to US
}


# ── Peak Engagement Windows (hours in local timezone) ────────────────


PEAK_WINDOWS: dict[str, list[tuple[int, int]]] = {
    "x": [(8, 10), (12, 13), (17, 19)],        # morning, lunch, evening
    "linkedin": [(8, 10), (12, 13)],              # business hours
    "facebook": [(12, 14), (19, 21)],             # lunch, evening
    "reddit": [(8, 11), (18, 21)],                # morning, evening
}


# ── Constants ────────────────────────────────────────────────────────


MIN_SPACING_MINUTES = 30
BACK_TO_BACK_PLATFORM_SPACING_MINUTES = 60
JITTER_MIN_SECONDS = 60       # 1 minute
JITTER_MAX_SECONDS = 15 * 60  # 15 minutes
DAILY_LIMIT_CAP = 20
SCHEDULE_LOOKAHEAD_DAYS = 3   # How many days ahead to look for free slots


# ── Helpers ──────────────────────────────────────────────────────────


def _get_timezone_for_region(region: str) -> str:
    """Get timezone string for a region. Falls back to global (US) for unknown regions."""
    return REGION_TIMEZONES.get(region, REGION_TIMEZONES["global"])


def _apply_jitter(dt: datetime) -> datetime:
    """Add random jitter of 1-15 minutes to a datetime to avoid exact scheduling patterns."""
    offset_seconds = random.randint(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)
    return dt + timedelta(seconds=offset_seconds)


def _calculate_daily_limit(active_campaign_count: int) -> int:
    """Calculate max posts per day based on active campaign count.

    Formula: min(campaigns * 4, DAILY_LIMIT_CAP) for low campaign counts,
    scaling down per-campaign as count increases.
    - 0 campaigns: 0
    - 1 campaign: 4
    - 2 campaigns: 8
    - 3 campaigns: 12
    - 4 campaigns: 14 (capped start)
    - 5+: min(campaigns * 3, DAILY_LIMIT_CAP)
    """
    if active_campaign_count == 0:
        return 0
    if active_campaign_count <= 3:
        return active_campaign_count * 4
    return min(active_campaign_count * 3, DAILY_LIMIT_CAP)


def _get_peak_slots(
    platform: str,
    region: str,
    base_date: datetime,
) -> list[datetime]:
    """Generate candidate peak-window slot start times for a platform and region.

    Returns timezone-aware datetimes in UTC for the given date.
    Each peak window generates one candidate slot at the window start.
    """
    tz_name = _get_timezone_for_region(region)
    tz = zoneinfo.ZoneInfo(tz_name)
    windows = PEAK_WINDOWS.get(platform, [(9, 17)])  # fallback: 9-5

    slots = []
    # Use the base_date's date in the local timezone
    local_date = base_date.astimezone(tz).date()

    for start_hour, end_hour in windows:
        # Create a datetime at the start of the window in local time
        local_dt = datetime(
            local_date.year, local_date.month, local_date.day,
            start_hour, 0, 0,
            tzinfo=tz,
        )
        # Convert to UTC
        utc_dt = local_dt.astimezone(timezone.utc)
        slots.append(utc_dt)

    return slots


def _has_conflict(
    candidate: datetime,
    occupied: list[dict],
    candidate_platform: str,
    candidate_campaign_id: int,
) -> bool:
    """Check if a candidate time conflicts with existing schedule.

    Conflicts:
    1. Any post within MIN_SPACING_MINUTES
    2. Same platform for a different campaign within BACK_TO_BACK_PLATFORM_SPACING_MINUTES
    """
    for entry in occupied:
        entry_time = entry["scheduled_at"]
        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time)
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)

        diff_seconds = abs((candidate - entry_time).total_seconds())

        # Rule 1: minimum spacing
        if diff_seconds < MIN_SPACING_MINUTES * 60:
            return True

        # Rule 2: same platform, different campaign, too close
        if (
            entry.get("platform") == candidate_platform
            and entry.get("campaign_id") != candidate_campaign_id
            and diff_seconds < BACK_TO_BACK_PLATFORM_SPACING_MINUTES * 60
        ):
            return True

    return False


def _find_slot_in_windows(
    platform: str,
    region: str,
    campaign_id: int,
    occupied: list[dict],
    search_start: datetime,
) -> datetime | None:
    """Find the first available slot in peak windows within SCHEDULE_LOOKAHEAD_DAYS.

    Iterates over days starting from search_start, checks each peak window slot,
    applies jitter, and returns the first non-conflicting time.
    """
    for day_offset in range(SCHEDULE_LOOKAHEAD_DAYS + 1):
        day = search_start + timedelta(days=day_offset)
        candidate_slots = _get_peak_slots(platform, region, day)

        # Shuffle windows so we don't always pick the first one
        random.shuffle(candidate_slots)

        for base_slot in candidate_slots:
            # Skip slots that are in the past
            if base_slot < search_start - timedelta(minutes=15):
                # Check if jittered version could still be in the future
                max_jittered = base_slot + timedelta(seconds=JITTER_MAX_SECONDS)
                if max_jittered < search_start:
                    continue

            # Try multiple jitter offsets for this window
            for _ in range(10):
                candidate = _apply_jitter(base_slot)

                # Must be in the future (or very near future)
                if candidate < search_start:
                    continue

                if not _has_conflict(candidate, occupied, platform, campaign_id):
                    return candidate

    return None


# ── Main Scheduling Algorithm ────────────────────────────────────────


def schedule_posts(
    campaign_id: int,
    platforms: list[str],
    target_region: str,
    content: dict,  # {platform: text}
    image_path: str | None = None,
    existing_schedule: list[dict] | None = None,
) -> list[dict]:
    """Determine optimal posting times for each platform.

    Rules:
    - Post during peak engagement windows for the campaign's target region
    - Minimum 30 minutes between any two posts (across all campaigns)
    - Don't post to same platform back-to-back for different campaigns
    - Randomize exact time within the peak window (jitter +/- 1-15 min)
    - Max posts per day based on active campaign count

    Returns: list of {campaign_id, platform, scheduled_at (datetime), content, image_path}
    """
    if not platforms:
        return []

    # Filter platforms to only those with content
    platforms = [p for p in platforms if content.get(p)]
    if not platforms:
        return []

    # Build the occupied slots list from existing schedule
    occupied = list(existing_schedule) if existing_schedule else []

    now = datetime.now(timezone.utc)
    result = []

    # Shuffle platform order to avoid deterministic ordering
    platforms_shuffled = list(platforms)
    random.shuffle(platforms_shuffled)

    for platform in platforms_shuffled:
        slot = _find_slot_in_windows(
            platform=platform,
            region=target_region,
            campaign_id=campaign_id,
            occupied=occupied,
            search_start=now,
        )

        if slot is None:
            # Absolute fallback: schedule far enough in the future
            logger.warning(
                "No peak window slot found for %s/%s — using fallback",
                platform, target_region,
            )
            fallback_offset = timedelta(hours=24 + random.randint(1, 12))
            slot = now + fallback_offset

        entry = {
            "campaign_id": campaign_id,
            "platform": platform,
            "scheduled_at": slot,
            "content": content[platform],
            "image_path": image_path,
        }
        result.append(entry)

        # Add this to occupied so subsequent platforms respect it
        occupied.append(entry)

    return result


# ── Queue Operations ─────────────────────────────────────────────────


def queue_approved_content(
    campaign_id: int,
    platforms: list[str],
    content: dict,
    target_region: str,
    image_path: str | None = None,
) -> list[int]:
    """Schedule approved content for posting.

    Calls schedule_posts() to determine times, then adds to post_schedule table.
    Returns list of schedule IDs.
    """
    # Get existing queued posts to avoid conflicts
    existing_queued = get_scheduled_posts(status="queued")
    existing_schedule = [
        {
            "campaign_id": p["campaign_server_id"],
            "platform": p["platform"],
            "scheduled_at": p["scheduled_at"],
        }
        for p in existing_queued
    ]

    scheduled = schedule_posts(
        campaign_id=campaign_id,
        platforms=platforms,
        target_region=target_region,
        content=content,
        image_path=image_path,
        existing_schedule=existing_schedule,
    )

    schedule_ids = []
    for entry in scheduled:
        scheduled_at = entry["scheduled_at"]
        if isinstance(scheduled_at, datetime):
            scheduled_at = scheduled_at.isoformat()

        sid = add_scheduled_post(
            campaign_server_id=campaign_id,
            platform=entry["platform"],
            scheduled_at=scheduled_at,
            content=entry["content"],
            image_path=entry.get("image_path"),
        )
        schedule_ids.append(sid)
        logger.info(
            "Queued post: campaign=%d platform=%s at=%s (id=%d)",
            campaign_id, entry["platform"], scheduled_at, sid,
        )

    return schedule_ids


def get_due_posts() -> list[dict]:
    """Get posts that are due for execution (scheduled_at <= now, status=queued).

    Uses local time for comparison since scheduled_at is stored in local time
    (set by _schedule_draft in user_app.py using datetime.now()).
    """
    now = datetime.now().isoformat()
    all_queued = get_scheduled_posts(status="queued")

    due = []
    for post in all_queued:
        scheduled_at = post["scheduled_at"]
        # Compare ISO strings (works because ISO format is lexicographically sortable)
        if scheduled_at <= now:
            due.append(post)

    return due


async def _post_to_platform(platform: str, draft: dict, image_path: str | None = None) -> str | None:
    """Post content to a specific platform using the existing post.py functions.

    This function imports post.py functions lazily to avoid heavy dependency loading
    at module import time.

    Returns post URL on success, None on failure.
    """
    # Lazy import to avoid loading Playwright and other heavy deps at module level
    from playwright.async_api import async_playwright

    # Import platform posting functions
    from post import (
        post_to_x,
        post_to_linkedin,
        post_to_facebook,
        post_to_reddit,
    )

    platform_funcs = {
        "x": post_to_x,
        "linkedin": post_to_linkedin,
        "facebook": post_to_facebook,
        "reddit": post_to_reddit,
    }

    func = platform_funcs.get(platform)
    if not func:
        raise ValueError(f"Unsupported platform: {platform}")

    # Build a draft dict compatible with post.py functions
    post_draft = {
        "content": {platform: draft["content"]},
        "id": draft.get("id", "scheduled"),
    }

    async with async_playwright() as pw:
        post_url = await func(post_draft, pw)

    return post_url


async def execute_scheduled_post(schedule_id: int) -> bool:
    """Execute a single scheduled post.

    1. Update status to 'posting'
    2. Call the appropriate platform posting function from post.py
    3. On success: update status to 'posted', create local_post entry
    4. On failure: update status to 'failed', record error

    Returns success boolean.
    """
    # Get the scheduled post details
    all_posts = get_scheduled_posts()
    post = None
    for p in all_posts:
        if p["id"] == schedule_id:
            post = p
            break

    if post is None:
        logger.error("Scheduled post %d not found", schedule_id)
        return False

    # Mark as posting
    update_schedule_status(schedule_id, "posting")

    try:
        post_url = await _post_to_platform(
            platform=post["platform"],
            draft=post,
            image_path=post.get("image_path"),
        )

        if post_url is not None:
            # Platform function returned a URL (may be real URL or fallback placeholder)
            local_post_id = add_post(
                campaign_server_id=post["campaign_server_id"],
                assignment_id=0,  # will be resolved by sync
                platform=post["platform"],
                post_url=post_url,
                content=post.get("content", ""),
                content_hash="",
            )
            update_schedule_status(schedule_id, "posted", local_post_id=local_post_id)
            # Mark the agent_draft as posted so the UI shows "Posted" instead of "Approved"
            if post.get("draft_id"):
                from utils.local_db import mark_draft_posted
                mark_draft_posted(post["draft_id"])
            logger.info(
                "Successfully posted schedule_id=%d to %s: %s",
                schedule_id, post["platform"], post_url,
            )
            return True
        else:
            # Platform function raised no exception but returned None — post likely sent,
            # URL capture failed. Store with placeholder so we don't lose the post record.
            placeholder_url = f"posted_but_url_unknown:{post['platform']}:{schedule_id}"
            local_post_id = add_post(
                campaign_server_id=post["campaign_server_id"],
                assignment_id=0,
                platform=post["platform"],
                post_url=placeholder_url,
                content=post.get("content", ""),
                content_hash="",
            )
            update_schedule_status(
                schedule_id, "posted_no_url",
                local_post_id=local_post_id,
                error_message="Post sent but URL capture failed — metric scraper will retry",
            )
            # Mark draft as posted even without URL — the post was sent
            if post.get("draft_id"):
                from utils.local_db import mark_draft_posted
                mark_draft_posted(post["draft_id"])
            logger.warning(
                "Post to %s sent but URL unknown for schedule_id=%d (local_post_id=%d)",
                post["platform"], schedule_id, local_post_id,
            )
            return True  # Post was sent — treat as success for campaign runner

    except Exception as e:
        error_msg = str(e)
        update_schedule_status(schedule_id, "failed", error_message=error_msg)
        logger.error(
            "Failed to execute schedule_id=%d on %s: %s",
            schedule_id, post["platform"], error_msg,
        )
        return False
