"""Amplifier Background Agent — always-running process for automated tasks.

Handles campaign polling, scheduled posting, metric scraping, session health
checks, and profile refresh. Runs inside the Python sidecar process as an
asyncio task. Communicates results back via notifications stored in local_db.

Intervals:
- Due posts check: every 60 seconds
- Campaign polling: every 10 minutes
- Metric scraping: every 60 seconds (checks what's due)
- Session health check: every 30 minutes
- Profile refresh: every 7 days
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Interval constants (seconds) ────────────────────────────────────

LOOP_INTERVAL = 60            # Main loop sleeps 60s between iterations
POLL_INTERVAL = 600           # 10 minutes
CONTENT_GEN_INTERVAL = 120    # 2 minutes — check for campaigns needing content
HEALTH_CHECK_INTERVAL = 1800  # 30 minutes
PROFILE_REFRESH_INTERVAL = 604800  # 7 days


# ── Campaign asset helpers ──────────────────────────────────────────


async def _download_campaign_product_images(campaign_data: dict) -> list[str]:
    """Download ALL product images from campaign assets to local disk.

    Returns list of local file paths (may be empty if no images).
    Images are cached — re-downloads are skipped.
    """
    import httpx
    from pathlib import Path

    assets = campaign_data.get("assets") or {}
    if isinstance(assets, str):
        try:
            assets = json.loads(assets)
        except (json.JSONDecodeError, TypeError):
            return []

    image_urls = assets.get("image_urls") or assets.get("images") or []
    if isinstance(image_urls, str):
        image_urls = [image_urls]

    if not image_urls:
        return []

    campaign_id = campaign_data.get("campaign_id", "unknown")
    cache_dir = Path("data") / "product_images" / str(campaign_id)
    cache_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for i, url in enumerate(image_urls):
        if not isinstance(url, str) or not url.startswith("http"):
            continue

        filename = url.split("/")[-1].split("?")[0][:50] or f"product_{i}.jpg"
        local_path = cache_dir / filename
        if local_path.exists():
            downloaded.append(str(local_path))
            continue

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    local_path.write_bytes(resp.content)
                    downloaded.append(str(local_path))
                    logger.info("Downloaded product image: %s", local_path)
        except Exception as e:
            logger.warning("Failed to download product image %s: %s", url, e)

    if downloaded:
        logger.info("Campaign %s: %d product images available", campaign_id, len(downloaded))
    return downloaded


def _pick_daily_image(images: list[str], day_number: int) -> str | None:
    """Pick a product image for today by rotating through the list.

    Day 1 -> image 0, Day 2 -> image 1, ..., wraps around.
    Each day's post features a different product photo.
    """
    if not images:
        return None
    index = (day_number - 1) % len(images)
    return images[index]


# ── Individual task functions ────────────────────────────────────────


async def poll_campaigns() -> dict:
    """Poll server for new campaign invitations and sync assignment statuses.

    Calls server_client.poll_campaigns(), stores new invitations in local_db.
    Also checks for campaigns that were cancelled/completed on the server
    and updates local status accordingly.
    Returns dict with count of new invitations.
    """
    from utils.server_client import poll_campaigns as server_poll
    from utils.local_db import upsert_campaign, get_campaign, get_campaigns, update_campaign_status

    try:
        campaigns = server_poll()
        new_count = 0
        server_campaign_ids = set()

        for campaign in campaigns:
            campaign_id = campaign.get("campaign_id")
            if campaign_id is None:
                continue

            server_campaign_ids.add(campaign_id)

            # Check if we already have this campaign locally
            existing = get_campaign(campaign_id)
            if existing is None:
                upsert_campaign(campaign)
                new_count += 1
            else:
                # Check if server status changed (e.g., company cancelled the campaign)
                server_status = campaign.get("status", "")
                local_status = existing.get("status", "")
                if server_status in ("cancelled", "completed", "expired") and local_status not in ("cancelled", "completed", "expired"):
                    update_campaign_status(campaign_id, server_status)
                    from utils.local_db import add_notification
                    add_notification("campaign", "Campaign Status Changed", f"\"{campaign.get('title', 'Campaign')}\" is now {server_status}.")
                # Update existing campaign data
                upsert_campaign(campaign)

        logger.info("Campaign poll: %d total, %d new", len(campaigns), new_count)
        if new_count > 0:
            from utils.local_db import add_notification
            add_notification("campaign", "New Campaign Invitations", f"{new_count} new campaign invitation(s) received.")
        return {"success": True, "total": len(campaigns), "new": new_count}

    except Exception as e:
        logger.error("Campaign poll failed: %s", e)
        from utils.local_db import add_notification
        add_notification("error", "Campaign Poll Failed", f"Could not reach server: {str(e)[:100]}")
        return {"success": False, "error": str(e), "total": 0, "new": 0}


async def generate_daily_content() -> dict:
    """Generate today's content for all active campaigns that don't have today's drafts yet.

    Runs daily: checks each active campaign, generates per-platform drafts into the
    agent_draft table, and auto-approves in full_auto mode. Replaces the old one-time
    generate_pending_content().
    """
    from utils.local_db import (
        get_campaigns, update_campaign_status, get_setting,
        get_todays_draft_count, add_draft, get_all_drafts, approve_draft,
        add_scheduled_post, get_todays_drafts,
    )
    from utils.content_agent import ContentAgent
    import json as _json

    try:
        all_campaigns = get_campaigns()
        # Only generate content for campaigns the user has ACCEPTED (not pending_invitation)
        accepted_statuses = ('assigned', 'accepted', 'content_generated', 'approved', 'posted', 'active')
        active = [c for c in all_campaigns if c.get('status') in accepted_statuses]

        if not active:
            return {"success": True, "generated": 0}

        gen = ContentAgent()
        generated_count = 0
        platforms = ['x', 'linkedin', 'facebook', 'reddit']
        mode = get_setting("mode", "semi_auto") or "semi_auto"

        for campaign in active:
            campaign_id = campaign.get("server_id")

            # Check if we already generated today's drafts for all platforms
            needs_generation = False
            for platform in platforms:
                if get_todays_draft_count(campaign_id, platform) == 0:
                    needs_generation = True
                    break

            if not needs_generation:
                continue

            # ── Repost campaigns: skip AI gen, use pre-written content ──
            if campaign.get("campaign_type") == "repost":
                repost_content = campaign.get("repost_content") or []
                if not repost_content:
                    # Try loading from local campaign_posts table
                    from utils.local_db import _get_db as _get_repost_db
                    _rconn = _get_repost_db()
                    _rows = _rconn.execute(
                        "SELECT platform, content, image_url FROM campaign_posts WHERE campaign_server_id = ? ORDER BY post_order",
                        (campaign_id,),
                    ).fetchall()
                    _rconn.close()
                    repost_content = [{"platform": r[0], "content": r[1], "image_url": r[2]} for r in _rows]

                if repost_content:
                    draft_ids = []
                    for post_data in repost_content:
                        plat = post_data.get("platform", "")
                        text = post_data.get("content", "")
                        if plat and text and get_todays_draft_count(campaign_id, plat) == 0:
                            did = add_draft(campaign_id, plat, text, iteration=1)
                            draft_ids.append(did)

                    if draft_ids:
                        generated_count += 1
                        logger.info("Repost content loaded for campaign %s (%d drafts)", campaign_id, len(draft_ids))
                        from utils.local_db import add_notification
                        add_notification("content", "Repost Drafts Ready", f"Loaded {len(draft_ids)} pre-written draft(s) for \"{campaign.get('title', 'campaign')}\".")

                        if campaign.get('status') == 'assigned':
                            update_campaign_status(campaign_id, 'content_generated')

                        # Full auto: auto-approve and schedule
                        if mode == "full_auto" and draft_ids:
                            from datetime import datetime as _dt, timedelta as _td
                            import random as _rnd
                            for did in draft_ids:
                                approve_draft(did)
                            base_time = _dt.now() + _td(minutes=5)
                            for i, did in enumerate(draft_ids):
                                draft_data = _get_draft(did) if '_get_draft' in dir() else None
                                if not draft_data:
                                    from utils.local_db import get_draft as _get_draft
                                    draft_data = _get_draft(did)
                                if draft_data:
                                    sched_time = base_time + _td(minutes=30 * i + _rnd.randint(0, 10))
                                    add_scheduled_post(
                                        campaign_server_id=campaign_id,
                                        platform=draft_data.get("platform", ""),
                                        scheduled_at=sched_time.isoformat(),
                                        content=draft_data.get("draft_text", ""),
                                        image_path=draft_data.get("image_path"),
                                        draft_id=did,
                                    )
                            logger.info("Full-auto: approved + scheduled %d repost drafts", len(draft_ids))
                continue  # Skip AI generation for repost campaigns

            # Get previous drafts for anti-repetition
            previous = get_all_drafts(campaign_id)
            previous_hooks = []
            for d in previous[:12]:  # Most recent 12 drafts (~3 days worth, ordered DESC)
                text = d.get('draft_text', '')
                if text:
                    first_line = text.split('\n')[0][:80]
                    previous_hooks.append(first_line)

            # Calculate day number from unique dates in draft history
            unique_dates = set(d.get('created_at', '')[:10] for d in previous if d.get('created_at'))
            day_number = len(unique_dates) + 1

            # Generate content via 4-phase ContentAgent pipeline
            campaign_data = {
                "campaign_id": campaign.get("server_id"),
                "title": campaign.get("title", ""),
                "brief": campaign.get("brief", ""),
                "content_guidance": campaign.get("content_guidance", ""),
                "assets": campaign.get("assets", {}),
                "scraped_data": campaign.get("scraped_data", {}),
                "disclaimer_text": campaign.get("disclaimer_text"),
                "campaign_goal": campaign.get("campaign_goal", "brand_awareness"),
                "tone": campaign.get("tone"),
                "preferred_formats": campaign.get("preferred_formats", {}),
            }
            try:
                result = await asyncio.to_thread(
                    lambda c=campaign_data, dn=day_number, ph=previous_hooks: asyncio.run(
                        gen.generate_content(c, enabled_platforms=platforms, day_number=dn, previous_hooks=ph)
                    )
                )

                if result:
                    content = result.get("content", result) if isinstance(result, dict) else result

                    # ── Image generation (v2/v3 upgrade) ──
                    # Generate an image for this campaign using:
                    # 1. img2img from product photos in campaign assets (preferred, daily rotation)
                    # 2. txt2img from the AI-generated image_prompt (fallback)
                    draft_image_path = None
                    try:
                        image_prompt = content.get("image_prompt", "")
                        all_product_images = await _download_campaign_product_images(campaign_data)
                        product_image = _pick_daily_image(all_product_images, day_number)

                        if image_prompt or product_image:
                            draft_image_path = await asyncio.to_thread(
                                lambda ip=image_prompt, pi=product_image, b=campaign_data.get("brief", ""): asyncio.run(
                                    gen.generate_image(
                                        prompt=ip or campaign_data.get("title", "product lifestyle photo"),
                                        platform="default",
                                        product_image_path=pi,
                                        campaign_brief=b,
                                    )
                                )
                            )
                            if draft_image_path:
                                logger.info("Generated campaign image: %s (img2img=%s)", draft_image_path, bool(product_image))
                    except Exception as img_err:
                        logger.warning("Image generation failed for campaign %s: %s", campaign_id, img_err)

                    draft_ids = []
                    for platform in platforms:
                        text = content.get(platform, '')
                        if text:
                            if isinstance(text, dict):
                                text = _json.dumps(text)
                            did = add_draft(campaign_id, platform, str(text),
                                            iteration=day_number, image_path=draft_image_path)
                            draft_ids.append(did)
                    generated_count += 1
                    logger.info("Daily content generated for campaign %s (day %d)", campaign_id, day_number)
                    from utils.local_db import add_notification
                    add_notification("content", "Drafts Ready", f"Generated {len(draft_ids)} draft(s) for \"{campaign.get('title', 'campaign')}\".")

                    # Send desktop notification for THIS campaign
                    try:
                        from utils.tray import send_notification
                        campaign_title = campaign.get("title", f"Campaign {campaign_id}")
                        send_notification(
                            "Content Ready for Review",
                            f"{campaign_title} — {len(draft_ids)} drafts generated. Open Amplifier to review.",
                        )
                        logger.info("Desktop notification sent for campaign %s", campaign_id)
                    except Exception as notif_err:
                        logger.warning("Desktop notification failed: %s", notif_err)

                    # Update campaign status if it was 'assigned'
                    if campaign.get('status') == 'assigned':
                        update_campaign_status(campaign_id, 'content_generated')
                        try:
                            from utils.server_client import update_assignment
                            assignment_id = campaign.get("assignment_id")
                            if assignment_id:
                                update_assignment(assignment_id, "content_generated")
                        except Exception:
                            pass

                    # Full auto mode: auto-approve all drafts and schedule them
                    if mode == "full_auto" and draft_ids:
                        from utils.local_db import get_draft as _get_draft
                        from datetime import datetime as _dt, timedelta as _td
                        import random as _rnd

                        for did in draft_ids:
                            approve_draft(did)

                        # Schedule approved drafts with 30-min spacing
                        base_time = _dt.now() + _td(minutes=5)
                        for i, did in enumerate(draft_ids):
                            draft_data = _get_draft(did)
                            if draft_data:
                                sched_time = base_time + _td(minutes=30 * i + _rnd.randint(0, 10))
                                add_scheduled_post(
                                    campaign_server_id=campaign_id,
                                    platform=draft_data.get("platform", ""),
                                    scheduled_at=sched_time.isoformat(),
                                    content=draft_data.get("draft_text", ""),
                                    image_path=draft_data.get("image_path"),
                                    draft_id=did,
                                )
                        logger.info("Full-auto: approved + scheduled %d drafts for campaign %s", len(draft_ids), campaign_id)

            except Exception as e:
                logger.error("Daily content gen failed for campaign %s: %s", campaign_id, e)
                from utils.local_db import add_notification
                add_notification("error", "Content Generation Failed", f"Failed for \"{campaign.get('title', 'campaign')}\": {str(e)[:100]}")

        return {"success": True, "generated": generated_count}

    except Exception as e:
        logger.error("Daily content generation task failed: %s", e)
        return {"success": False, "error": str(e), "generated": 0}


async def execute_due_posts() -> dict:
    """Check for and execute any posts that are due.

    Calls post_scheduler.get_due_posts() and executes each one.
    Syncs successful posts to server.
    Returns summary with successes and failures.
    """
    from utils.post_scheduler import get_due_posts, execute_scheduled_post
    from utils.server_client import report_posts
    from utils.local_db import get_scheduled_posts

    try:
        due_posts = get_due_posts()
        if not due_posts:
            return {"success": True, "executed": 0, "succeeded": 0, "failed": 0}

        # Mark all due posts as 'posting' immediately to prevent the next
        # 60s tick from picking them up again (race condition → duplicates)
        from utils.local_db import _get_db
        conn = _get_db()
        for post in due_posts:
            conn.execute(
                "UPDATE post_schedule SET status = 'posting' WHERE id = ? AND status = 'queued'",
                (post["id"],),
            )
        conn.commit()
        conn.close()

        successes = []
        failures = []

        for post in due_posts:
            try:
                result = await execute_scheduled_post(post["id"])
                if result:
                    successes.append(post)
                else:
                    failures.append({
                        "post": post,
                        "error": "execute_scheduled_post returned False",
                    })
            except Exception as e:
                logger.error(
                    "Failed to execute post %d on %s: %s",
                    post["id"], post.get("platform", "unknown"), e,
                )
                failures.append({"post": post, "error": str(e)})

        # Sync successful posts to server
        if successes:
            try:
                # Build server-compatible post list from local_post records
                from utils.local_db import get_unsynced_posts, mark_posts_synced, _get_db
                unsynced = get_unsynced_posts()
                if unsynced:
                    # Resolve assignment_ids from local_campaign
                    conn = _get_db()
                    campaign_assignments = {}
                    for row in conn.execute("SELECT server_id, assignment_id FROM local_campaign").fetchall():
                        campaign_assignments[row[0]] = row[1]
                    conn.close()

                    server_posts = []
                    local_ids_ordered = []
                    for p in unsynced:
                        aid = p.get("assignment_id") or campaign_assignments.get(p.get("campaign_server_id"), 0)
                        server_posts.append({
                            "assignment_id": aid,
                            "platform": p["platform"],
                            "post_url": p["post_url"],
                            "content_hash": p.get("content_hash", ""),
                            "posted_at": p.get("posted_at", ""),
                        })
                        local_ids_ordered.append(p["id"])

                    result = report_posts(server_posts)

                    # Map server post IDs back to local posts
                    server_post_ids = {}
                    for created in result.get("created", []):
                        # Server returns created posts in order
                        idx = result["created"].index(created)
                        if idx < len(local_ids_ordered):
                            server_post_ids[local_ids_ordered[idx]] = created["id"]

                    mark_posts_synced(local_ids_ordered, server_post_ids)
                    logger.info("Synced %d posts to server", len(local_ids_ordered))
            except Exception as e:
                logger.error("Failed to sync posts to server: %s", e)

        summary = {
            "success": True,
            "executed": len(due_posts),
            "succeeded": len(successes),
            "failed": len(failures),
            "failure_details": [
                {"platform": f["post"].get("platform"), "error": f["error"]}
                for f in failures
            ],
        }
        logger.info(
            "Post execution: %d due, %d succeeded, %d failed",
            len(due_posts), len(successes), len(failures),
        )

        # Log notifications for post results
        from utils.local_db import add_notification
        if successes:
            platforms_posted = ", ".join(set(p.get("platform", "?") for p in successes))
            add_notification("post", "Posts Published", f"Successfully posted to {platforms_posted} ({len(successes)} post(s)).")
        if failures:
            platforms_failed = ", ".join(set(f["post"].get("platform", "?") for f in failures))
            add_notification("error", "Posts Failed", f"Failed to post to {platforms_failed}. Will retry automatically.")

        return summary

    except Exception as e:
        logger.error("execute_due_posts failed: %s", e)
        return {"success": False, "error": str(e), "executed": 0, "succeeded": 0, "failed": 0}


async def run_metric_scraping() -> dict:
    """Check which posts need metric scraping and run it.

    Uses existing metric_scraper.scrape_all_posts() and sync_metrics_to_server().
    Returns count of posts scraped and metrics synced.
    """
    from utils.metric_scraper import scrape_all_posts, sync_metrics_to_server

    try:
        await scrape_all_posts()
        sync_metrics_to_server()

        # Self-learning: analyze post performance and update content insights
        try:
            from utils.content_performance import update_insights_from_metrics
            updated = update_insights_from_metrics()
            if updated > 0:
                logger.info("Content insights updated: %d hook/format combos analyzed", updated)
        except Exception as perf_err:
            logger.warning("Content performance analysis failed (non-critical): %s", perf_err)

        return {"success": True}
    except Exception as e:
        logger.error("Metric scraping failed: %s", e)
        return {"success": False, "error": str(e)}


async def check_sessions() -> dict:
    """Check all platform sessions for health.

    Calls session_health.check_all_sessions().
    Returns health status dict keyed by platform.
    """
    from utils.session_health import check_all_sessions

    try:
        results = await check_all_sessions()
        logger.info(
            "Session health: %s",
            {p: r["status"] for p, r in results.items()},
        )
        return {"success": True, "platforms": results}
    except Exception as e:
        logger.error("Session health check failed: %s", e)
        return {"success": False, "error": str(e), "platforms": {}}


async def refresh_profiles() -> dict:
    """Re-scrape all connected platform profiles if stale (>7 days).

    Checks last_scraped_at via local_db. Only runs if profiles are older
    than PROFILE_REFRESH_INTERVAL. After scraping, runs niche classification
    and syncs to server.
    """
    from utils.local_db import get_all_scraped_profiles
    from utils.profile_scraper import scrape_all_profiles, sync_profiles_to_server

    try:
        # Check if any profile is stale
        profiles = get_all_scraped_profiles()
        now = datetime.now(timezone.utc)
        stale_platforms = []

        if not profiles:
            # No profiles at all — scrape everything
            stale_platforms = None  # None = all enabled
        else:
            for p in profiles:
                scraped_at_str = p.get("scraped_at")
                if not scraped_at_str:
                    stale_platforms.append(p["platform"])
                    continue
                try:
                    scraped_at = datetime.fromisoformat(scraped_at_str)
                    if scraped_at.tzinfo is None:
                        scraped_at = scraped_at.replace(tzinfo=timezone.utc)
                    age_seconds = (now - scraped_at).total_seconds()
                    if age_seconds >= PROFILE_REFRESH_INTERVAL:
                        stale_platforms.append(p["platform"])
                except (ValueError, TypeError):
                    stale_platforms.append(p["platform"])

        if stale_platforms is not None and not stale_platforms:
            logger.info("All profiles are fresh — skipping refresh")
            return {"success": True, "refreshed": 0, "skipped": True}

        # Scrape stale platforms (or all if stale_platforms is None)
        results = await scrape_all_profiles(stale_platforms)

        # AI niche classification removed — user selects niches manually

        # Sync to server
        try:
            sync_profiles_to_server()
        except Exception as e:
            logger.warning("Profile sync to server failed: %s", e)

        refreshed_count = len(
            [r for r in results.values() if "error" not in r]
        )
        logger.info("Profile refresh: %d platform(s) refreshed", refreshed_count)
        return {"success": True, "refreshed": refreshed_count, "skipped": False}

    except Exception as e:
        logger.error("Profile refresh failed: %s", e)
        return {"success": False, "error": str(e), "refreshed": 0}


# ── Notification builder ─────────────────────────────────────────────


def _build_notifications(results: dict) -> list[dict]:
    """Build user-facing notifications from agent task results.

    Generates notifications for significant events:
    - New campaign invitations
    - Posts published or failed
    - Session expiration
    - Profile refresh completion

    Returns list of notification dicts ready for local_db.add_notification().
    """
    notifications = []

    # Campaign polling results
    campaigns_result = results.get("campaigns")
    if campaigns_result and campaigns_result.get("new", 0) > 0:
        count = campaigns_result["new"]
        notifications.append({
            "type": "new_campaigns",
            "title": "New Campaign Invitations",
            "message": f"You have {count} new campaign invitation{'s' if count != 1 else ''}",
            "data": json.dumps({"count": count}),
        })

    # Post execution results
    posts_result = results.get("posts")
    if posts_result and posts_result.get("executed", 0) > 0:
        succeeded = posts_result.get("succeeded", 0)
        failed = posts_result.get("failed", 0)

        if succeeded > 0:
            notifications.append({
                "type": "post_published",
                "title": "Posts Published",
                "message": f"Successfully posted to {succeeded} platform{'s' if succeeded != 1 else ''}",
                "data": json.dumps({"succeeded": succeeded}),
            })

        if failed > 0:
            failure_details = posts_result.get("failure_details", [])
            for detail in failure_details:
                platform = detail.get("platform", "unknown")
                error = detail.get("error", "Unknown error")
                notifications.append({
                    "type": "post_failed",
                    "title": f"Post Failed on {platform.title()}",
                    "message": f"Failed to post to {platform}: {error}",
                    "data": json.dumps(detail),
                })

    # Session health results
    health_result = results.get("health")
    if health_result and health_result.get("platforms"):
        for platform, status_data in health_result["platforms"].items():
            if status_data.get("status") == "red":
                notifications.append({
                    "type": "session_expired",
                    "title": f"{platform.title()} Session Expired",
                    "message": f"Your {platform} session has expired. Re-authenticate to continue posting.",
                    "data": json.dumps({"platform": platform}),
                })

    # Profile refresh results
    profiles_result = results.get("profiles")
    if profiles_result and profiles_result.get("refreshed", 0) > 0:
        count = profiles_result["refreshed"]
        notifications.append({
            "type": "profile_refreshed",
            "title": "Profiles Updated",
            "message": f"Refreshed {count} platform profile{'s' if count != 1 else ''}",
            "data": json.dumps({"count": count}),
        })

    return notifications


def _store_notifications(notifications: list[dict]) -> None:
    """Persist notifications to local_db AND send desktop notifications."""
    from utils.local_db import add_notification

    for n in notifications:
        try:
            add_notification(
                notification_type=n["type"],
                title=n["title"],
                message=n["message"],
                data=n.get("data", "{}"),
            )
        except Exception as e:
            logger.error("Failed to store notification: %s", e)

        # Also send desktop notification for important events
        try:
            from utils.tray import send_notification
            send_notification(n["title"], n["message"])
        except Exception:
            pass  # Tray not available — silent


# ── Background Agent class ───────────────────────────────────────────


class BackgroundAgent:
    """Always-running background process that handles all automated tasks.

    Manages a main loop that checks what's due each iteration (every 60s).
    Tasks are staggered by their respective intervals to avoid thundering herd.
    Individual task failures do not crash the agent.
    """

    def __init__(self):
        self.running = True
        self.paused = False
        self.last_poll = 0.0
        self.last_content_gen = 0.0
        self.last_health_check = 0.0
        self.last_profile_refresh = 0.0
        self.last_metric_scrape = 0.0
        self._task: asyncio.Task | None = None
        self._iteration_count = 0

    async def run(self):
        """Main loop -- runs forever, checks what's due each iteration."""
        logger.info("Background agent started")

        while self.running:
            now = time.time()
            results = {}

            if not self.paused:
                self._iteration_count += 1

                # Every 60s: check for due posts
                try:
                    results["posts"] = await execute_due_posts()
                except Exception as e:
                    logger.error("Due posts check crashed: %s", e)
                    results["posts"] = {"success": False, "error": str(e)}

                # Re-queue failed posts for retry (max 3 attempts, 30-min delay)
                try:
                    from utils.local_db import requeue_failed_posts
                    requeued = requeue_failed_posts()
                    if requeued > 0:
                        logger.info("Re-queued %d failed post(s) for retry", requeued)
                except Exception as e:
                    logger.warning("Failed post requeue error: %s", e)

                # Every 10min: poll for campaigns
                if now - self.last_poll >= POLL_INTERVAL:
                    try:
                        results["campaigns"] = await poll_campaigns()
                    except Exception as e:
                        logger.error("Campaign poll crashed: %s", e)
                        results["campaigns"] = {"success": False, "error": str(e)}
                    self.last_poll = now

                # Every 2min: generate daily content for active campaigns
                if now - self.last_content_gen >= CONTENT_GEN_INTERVAL:
                    try:
                        results["content_gen"] = await generate_daily_content()
                    except Exception as e:
                        logger.error("Daily content generation crashed: %s", e)
                        results["content_gen"] = {"success": False, "error": str(e)}
                    self.last_content_gen = now

                # Every 30min: check session health
                if now - self.last_health_check >= HEALTH_CHECK_INTERVAL:
                    try:
                        results["health"] = await check_sessions()
                    except Exception as e:
                        logger.error("Session health check crashed: %s", e)
                        results["health"] = {"success": False, "error": str(e)}
                    self.last_health_check = now

                # Every 7 days: refresh profiles
                if now - self.last_profile_refresh >= PROFILE_REFRESH_INTERVAL:
                    try:
                        results["profiles"] = await refresh_profiles()
                    except Exception as e:
                        logger.error("Profile refresh crashed: %s", e)
                        results["profiles"] = {"success": False, "error": str(e)}
                    self.last_profile_refresh = now

                # Metric scraping: check what's due each iteration
                try:
                    results["metrics"] = await run_metric_scraping()
                except Exception as e:
                    logger.error("Metric scraping crashed: %s", e)
                    results["metrics"] = {"success": False, "error": str(e)}

                # Generate and store notifications from results
                try:
                    notifications = _build_notifications(results)
                    if notifications:
                        _store_notifications(notifications)
                        logger.info(
                            "Generated %d notification(s)", len(notifications)
                        )
                except Exception as e:
                    logger.error("Notification building failed: %s", e)

            await asyncio.sleep(LOOP_INTERVAL)

        logger.info("Background agent stopped")

    def pause(self):
        """Pause all background task execution."""
        self.paused = True
        logger.info("Background agent paused")

    def resume(self):
        """Resume background task execution."""
        self.paused = False
        logger.info("Background agent resumed")

    def stop(self):
        """Stop the agent loop."""
        self.running = False
        logger.info("Background agent stop requested")

    def get_status(self) -> dict:
        """Return current agent status including last run times."""
        now = time.time()
        return {
            "running": self.running,
            "paused": self.paused,
            "iteration_count": self._iteration_count,
            "last_poll_ago": round(now - self.last_poll) if self.last_poll else None,
            "last_health_check_ago": round(now - self.last_health_check) if self.last_health_check else None,
            "last_profile_refresh_ago": round(now - self.last_profile_refresh) if self.last_profile_refresh else None,
        }


# ── Module-level agent instance ──────────────────────────────────────

_agent: BackgroundAgent | None = None


def get_agent() -> BackgroundAgent | None:
    """Get the current background agent instance."""
    return _agent


async def start_background_agent() -> BackgroundAgent:
    """Create and start the background agent as an asyncio task.

    Returns the agent instance. The agent runs in its own task within
    the current event loop.
    """
    global _agent

    if _agent is not None and _agent.running:
        logger.warning("Background agent already running")
        return _agent

    _agent = BackgroundAgent()
    _agent._task = asyncio.create_task(_agent.run())
    logger.info("Background agent task created")
    return _agent


async def stop_background_agent() -> None:
    """Stop the background agent."""
    global _agent

    if _agent is None:
        return

    _agent.stop()
    if _agent._task:
        # Give it time to finish the current iteration
        try:
            await asyncio.wait_for(_agent._task, timeout=5.0)
        except asyncio.TimeoutError:
            _agent._task.cancel()
            try:
                await _agent._task
            except asyncio.CancelledError:
                pass
    _agent = None
    logger.info("Background agent stopped and cleaned up")
