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
HEALTH_CHECK_INTERVAL = 1800  # 30 minutes
PROFILE_REFRESH_INTERVAL = 604800  # 7 days


# ── Individual task functions ────────────────────────────────────────


async def poll_campaigns() -> dict:
    """Poll server for new campaign invitations.

    Calls server_client.poll_campaigns(), stores new invitations in local_db.
    Returns dict with count of new invitations.
    """
    from utils.server_client import poll_campaigns as server_poll
    from utils.local_db import upsert_campaign, get_campaign

    try:
        campaigns = server_poll()
        new_count = 0

        for campaign in campaigns:
            campaign_id = campaign.get("campaign_id")
            if campaign_id is None:
                continue

            # Check if we already have this campaign locally
            existing = get_campaign(campaign_id)
            if existing is None:
                upsert_campaign(campaign)
                new_count += 1
            else:
                # Update existing campaign data
                upsert_campaign(campaign)

        logger.info("Campaign poll: %d total, %d new", len(campaigns), new_count)
        return {"success": True, "total": len(campaigns), "new": new_count}

    except Exception as e:
        logger.error("Campaign poll failed: %s", e)
        return {"success": False, "error": str(e), "total": 0, "new": 0}


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
                from utils.local_db import get_unsynced_posts, mark_posts_synced
                unsynced = get_unsynced_posts()
                if unsynced:
                    server_posts = []
                    for p in unsynced:
                        server_posts.append({
                            "assignment_id": p.get("assignment_id", 0),
                            "platform": p["platform"],
                            "post_url": p["post_url"],
                            "content_hash": p.get("content_hash", ""),
                            "posted_at": p.get("posted_at", ""),
                        })
                    result = report_posts(server_posts)
                    post_ids = [p["id"] for p in unsynced]
                    mark_posts_synced(post_ids)
                    logger.info("Synced %d posts to server", len(post_ids))
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

        # Run niche classification if available
        try:
            from utils.niche_classifier import classify_and_store
            await classify_and_store(
                stale_platforms if stale_platforms else None
            )
        except ImportError:
            logger.debug("Niche classifier not available")
        except Exception as e:
            logger.warning("Niche classification failed: %s", e)

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
    """Persist notifications to local_db."""
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

                # Every 10min: poll for campaigns
                if now - self.last_poll >= POLL_INTERVAL:
                    try:
                        results["campaigns"] = await poll_campaigns()
                    except Exception as e:
                        logger.error("Campaign poll crashed: %s", e)
                        results["campaigns"] = {"success": False, "error": str(e)}
                    self.last_poll = now

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
