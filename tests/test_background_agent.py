"""Tests for the Background Agent (Task 22).

Covers:
- Campaign polling stores invitations
- Due post execution calls scheduler correctly
- Post execution syncs to server on success
- Post execution handles individual failures without crashing
- Metric scraping triggers correctly
- Session health check interval (30 min)
- Profile refresh interval (7 days)
- Profile refresh skips when profiles are fresh
- Pause/resume stops/starts execution
- Agent stop terminates the loop
- Notification building from results
- Notification building handles empty/no-op results
- Agent handles errors in individual tasks without crashing
- Agent status reporting
- Sidecar handler integration (start/stop/pause/resume/status)
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


# ── Campaign Polling ─────────────────────────────────────────────────


class TestPollCampaigns:
    """Test poll_campaigns stores invitations in local DB."""

    @pytest.mark.asyncio
    async def test_poll_stores_new_campaigns(self):
        """New campaigns from server are stored in local_db."""
        from background_agent import poll_campaigns

        mock_campaigns = [
            {
                "campaign_id": 1,
                "assignment_id": 10,
                "title": "Test Campaign A",
                "brief": "Brief A",
                "status": "assigned",
            },
            {
                "campaign_id": 2,
                "assignment_id": 20,
                "title": "Test Campaign B",
                "brief": "Brief B",
                "status": "assigned",
            },
        ]

        with patch("background_agent.poll_campaigns.__module__", "background_agent"):
            with patch("utils.server_client.poll_campaigns", return_value=mock_campaigns):
                result = await poll_campaigns()

        assert result["success"] is True
        assert result["total"] == 2
        assert result["new"] == 2

        # Verify stored in local_db
        from utils.local_db import get_campaign
        c1 = get_campaign(1)
        assert c1 is not None
        assert c1["title"] == "Test Campaign A"
        c2 = get_campaign(2)
        assert c2 is not None
        assert c2["title"] == "Test Campaign B"

    @pytest.mark.asyncio
    async def test_poll_returns_zero_new_for_existing(self):
        """Already-known campaigns do not increment new count."""
        from background_agent import poll_campaigns
        from utils.local_db import upsert_campaign

        # Pre-insert campaign
        upsert_campaign({
            "campaign_id": 5,
            "assignment_id": 50,
            "title": "Existing",
            "brief": "Already in DB",
            "status": "assigned",
        })

        mock_campaigns = [
            {
                "campaign_id": 5,
                "assignment_id": 50,
                "title": "Existing Updated",
                "brief": "Already in DB",
                "status": "assigned",
            },
        ]

        with patch("utils.server_client.poll_campaigns", return_value=mock_campaigns):
            result = await poll_campaigns()

        assert result["success"] is True
        assert result["total"] == 1
        assert result["new"] == 0  # Not new — already existed

    @pytest.mark.asyncio
    async def test_poll_handles_server_error(self):
        """Server errors are caught, not propagated."""
        from background_agent import poll_campaigns

        with patch("utils.server_client.poll_campaigns", side_effect=RuntimeError("Server unreachable")):
            result = await poll_campaigns()

        assert result["success"] is False
        assert "error" in result


# ── Due Post Execution ───────────────────────────────────────────────


class TestExecuteDuePosts:
    """Test execute_due_posts calls scheduler correctly and syncs results."""

    @pytest.mark.asyncio
    async def test_no_due_posts_returns_zero(self):
        """When no posts are due, return clean summary."""
        from background_agent import execute_due_posts

        with patch("utils.post_scheduler.get_due_posts", return_value=[]):
            result = await execute_due_posts()

        assert result["success"] is True
        assert result["executed"] == 0
        assert result["succeeded"] == 0
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_executes_due_posts_and_counts(self):
        """Due posts are executed and counted correctly."""
        from background_agent import execute_due_posts

        due_posts = [
            {"id": 1, "platform": "x", "content": "Hello X"},
            {"id": 2, "platform": "linkedin", "content": "Hello LinkedIn"},
        ]

        with patch("utils.post_scheduler.get_due_posts", return_value=due_posts), \
             patch("utils.post_scheduler.execute_scheduled_post", new_callable=AsyncMock, return_value=True), \
             patch("utils.local_db.get_unsynced_posts", return_value=[]), \
             patch("utils.server_client.report_posts", return_value={"count": 0}):
            result = await execute_due_posts()

        assert result["success"] is True
        assert result["executed"] == 2
        assert result["succeeded"] == 2
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_handles_partial_failure(self):
        """One post failing doesn't block others; failures are tracked."""
        from background_agent import execute_due_posts

        due_posts = [
            {"id": 1, "platform": "x", "content": "Hello X"},
            {"id": 2, "platform": "linkedin", "content": "Hello LinkedIn"},
            {"id": 3, "platform": "facebook", "content": "Hello FB"},
        ]

        call_count = 0

        async def mock_execute(schedule_id):
            nonlocal call_count
            call_count += 1
            if schedule_id == 2:
                raise RuntimeError("Session expired")
            return True

        with patch("utils.post_scheduler.get_due_posts", return_value=due_posts), \
             patch("utils.post_scheduler.execute_scheduled_post", side_effect=mock_execute), \
             patch("utils.local_db.get_unsynced_posts", return_value=[]), \
             patch("utils.server_client.report_posts", return_value={"count": 0}):
            result = await execute_due_posts()

        assert result["success"] is True
        assert result["executed"] == 3
        assert result["succeeded"] == 2
        assert result["failed"] == 1
        assert result["failure_details"][0]["platform"] == "linkedin"

    @pytest.mark.asyncio
    async def test_syncs_unsynced_posts_to_server(self):
        """After execution, unsynced posts are reported to the server."""
        from background_agent import execute_due_posts

        due_posts = [{"id": 1, "platform": "x", "content": "Hello"}]
        unsynced = [{
            "id": 100,
            "assignment_id": 10,
            "platform": "x",
            "post_url": "https://x.com/post/123",
            "content_hash": "abc",
            "posted_at": "2026-03-24T12:00:00",
        }]

        report_mock = MagicMock(return_value={"count": 1})
        sync_mock = MagicMock()

        with patch("utils.post_scheduler.get_due_posts", return_value=due_posts), \
             patch("utils.post_scheduler.execute_scheduled_post", new_callable=AsyncMock, return_value=True), \
             patch("utils.local_db.get_unsynced_posts", return_value=unsynced), \
             patch("utils.server_client.report_posts", report_mock), \
             patch("utils.local_db.mark_posts_synced", sync_mock):
            result = await execute_due_posts()

        assert result["succeeded"] == 1
        report_mock.assert_called_once()
        sync_mock.assert_called_once_with([100])


# ── Metric Scraping ──────────────────────────────────────────────────


class TestMetricScraping:
    """Test metric scraping triggers correctly."""

    @pytest.mark.asyncio
    async def test_calls_scrape_and_sync(self):
        """run_metric_scraping calls both scrape_all_posts and sync_metrics_to_server."""
        from background_agent import run_metric_scraping

        scrape_mock = AsyncMock()
        sync_mock = MagicMock()

        with patch("utils.metric_scraper.scrape_all_posts", scrape_mock), \
             patch("utils.metric_scraper.sync_metrics_to_server", sync_mock):
            result = await run_metric_scraping()

        assert result["success"] is True
        scrape_mock.assert_awaited_once()
        sync_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_scraping_error(self):
        """Scraping errors are caught gracefully."""
        from background_agent import run_metric_scraping

        with patch("utils.metric_scraper.scrape_all_posts", new_callable=AsyncMock, side_effect=Exception("Browser crash")), \
             patch("utils.metric_scraper.sync_metrics_to_server", MagicMock()):
            result = await run_metric_scraping()

        assert result["success"] is False
        assert "Browser crash" in result["error"]


# ── Session Health Check ─────────────────────────────────────────────


class TestCheckSessions:
    """Test session health check."""

    @pytest.mark.asyncio
    async def test_returns_platform_health(self):
        """check_sessions returns per-platform health data."""
        from background_agent import check_sessions

        mock_health = {
            "x": {"status": "green", "details": "Authenticated", "checked_at": "2026-03-24T10:00:00"},
            "linkedin": {"status": "red", "details": "Session expired", "checked_at": "2026-03-24T10:00:00"},
        }

        with patch("utils.session_health.check_all_sessions", new_callable=AsyncMock, return_value=mock_health):
            result = await check_sessions()

        assert result["success"] is True
        assert result["platforms"]["x"]["status"] == "green"
        assert result["platforms"]["linkedin"]["status"] == "red"

    @pytest.mark.asyncio
    async def test_handles_health_check_error(self):
        """Health check errors are caught."""
        from background_agent import check_sessions

        with patch("utils.session_health.check_all_sessions", new_callable=AsyncMock, side_effect=Exception("No profiles")):
            result = await check_sessions()

        assert result["success"] is False


# ── Profile Refresh ──────────────────────────────────────────────────


class TestRefreshProfiles:
    """Test profile refresh logic, including staleness check."""

    @pytest.mark.asyncio
    async def test_skips_fresh_profiles(self):
        """Profiles scraped recently are not re-scraped."""
        from background_agent import refresh_profiles

        now = datetime.now(timezone.utc).isoformat()
        fresh_profiles = [
            {"platform": "x", "scraped_at": now},
            {"platform": "linkedin", "scraped_at": now},
        ]

        with patch("utils.local_db.get_all_scraped_profiles", return_value=fresh_profiles):
            result = await refresh_profiles()

        assert result["success"] is True
        assert result["skipped"] is True
        assert result["refreshed"] == 0

    @pytest.mark.asyncio
    async def test_scrapes_stale_profiles(self):
        """Profiles older than 7 days are re-scraped."""
        from background_agent import refresh_profiles

        old_date = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        stale_profiles = [
            {"platform": "x", "scraped_at": old_date},
        ]

        scrape_result = {"x": {"platform": "x", "follower_count": 1000}}

        with patch("utils.local_db.get_all_scraped_profiles", return_value=stale_profiles), \
             patch("utils.profile_scraper.scrape_all_profiles", new_callable=AsyncMock, return_value=scrape_result), \
             patch("utils.profile_scraper.sync_profiles_to_server", MagicMock()), \
             patch("utils.niche_classifier.classify_and_store", new_callable=AsyncMock):
            result = await refresh_profiles()

        assert result["success"] is True
        assert result["skipped"] is False
        assert result["refreshed"] == 1

    @pytest.mark.asyncio
    async def test_scrapes_all_when_no_profiles(self):
        """When no profiles exist at all, scrape everything."""
        from background_agent import refresh_profiles

        scrape_result = {
            "x": {"platform": "x", "follower_count": 500},
            "linkedin": {"platform": "linkedin", "follower_count": 300},
        }

        with patch("utils.local_db.get_all_scraped_profiles", return_value=[]), \
             patch("utils.profile_scraper.scrape_all_profiles", new_callable=AsyncMock, return_value=scrape_result) as scrape_mock, \
             patch("utils.profile_scraper.sync_profiles_to_server", MagicMock()), \
             patch("utils.niche_classifier.classify_and_store", new_callable=AsyncMock):
            result = await refresh_profiles()

        assert result["success"] is True
        # Called with None = all platforms
        scrape_mock.assert_awaited_once_with(None)

    @pytest.mark.asyncio
    async def test_handles_refresh_error(self):
        """Profile refresh errors are caught."""
        from background_agent import refresh_profiles

        with patch("utils.local_db.get_all_scraped_profiles", side_effect=Exception("DB locked")):
            result = await refresh_profiles()

        assert result["success"] is False


# ── Notification Building ────────────────────────────────────────────


class TestNotificationBuilding:
    """Test _build_notifications generates correct notifications from results."""

    def test_new_campaigns_notification(self):
        """New campaign invitations generate a notification."""
        from background_agent import _build_notifications

        results = {
            "campaigns": {"success": True, "total": 3, "new": 3},
        }
        notifications = _build_notifications(results)

        assert len(notifications) == 1
        assert notifications[0]["type"] == "new_campaigns"
        assert "3" in notifications[0]["message"]

    def test_single_campaign_notification_grammar(self):
        """Single campaign notification uses singular form."""
        from background_agent import _build_notifications

        results = {
            "campaigns": {"success": True, "total": 1, "new": 1},
        }
        notifications = _build_notifications(results)

        assert len(notifications) == 1
        assert "invitation" in notifications[0]["message"]
        assert "invitations" not in notifications[0]["message"]

    def test_post_published_notification(self):
        """Successful posts generate a published notification."""
        from background_agent import _build_notifications

        results = {
            "posts": {"success": True, "executed": 2, "succeeded": 2, "failed": 0, "failure_details": []},
        }
        notifications = _build_notifications(results)

        assert len(notifications) == 1
        assert notifications[0]["type"] == "post_published"

    def test_post_failure_notification(self):
        """Failed posts generate per-platform failure notifications."""
        from background_agent import _build_notifications

        results = {
            "posts": {
                "success": True, "executed": 2, "succeeded": 1, "failed": 1,
                "failure_details": [
                    {"platform": "x", "error": "Session expired"},
                ],
            },
        }
        notifications = _build_notifications(results)

        # Should have both: 1 success + 1 failure
        types = [n["type"] for n in notifications]
        assert "post_published" in types
        assert "post_failed" in types

        failure = [n for n in notifications if n["type"] == "post_failed"][0]
        assert "x" in failure["message"].lower() or "X" in failure["message"]

    def test_session_expired_notification(self):
        """Expired sessions generate a re-auth notification."""
        from background_agent import _build_notifications

        results = {
            "health": {
                "success": True,
                "platforms": {
                    "x": {"status": "green", "details": "OK"},
                    "linkedin": {"status": "red", "details": "Expired"},
                },
            },
        }
        notifications = _build_notifications(results)

        assert len(notifications) == 1
        assert notifications[0]["type"] == "session_expired"
        assert "linkedin" in notifications[0]["message"].lower()

    def test_profile_refresh_notification(self):
        """Profile refresh generates a notification."""
        from background_agent import _build_notifications

        results = {
            "profiles": {"success": True, "refreshed": 2, "skipped": False},
        }
        notifications = _build_notifications(results)

        assert len(notifications) == 1
        assert notifications[0]["type"] == "profile_refreshed"

    def test_no_notifications_for_empty_results(self):
        """No notifications when nothing happened."""
        from background_agent import _build_notifications

        results = {
            "posts": {"success": True, "executed": 0, "succeeded": 0, "failed": 0},
        }
        notifications = _build_notifications(results)
        assert len(notifications) == 0

    def test_no_notifications_for_zero_new_campaigns(self):
        """No notification when poll returns zero new campaigns."""
        from background_agent import _build_notifications

        results = {
            "campaigns": {"success": True, "total": 5, "new": 0},
        }
        notifications = _build_notifications(results)
        assert len(notifications) == 0

    def test_notifications_stored_in_db(self):
        """Notifications are persisted via local_db.add_notification."""
        from background_agent import _store_notifications
        from utils.local_db import get_notifications

        notifs = [
            {
                "type": "new_campaigns",
                "title": "New Campaigns",
                "message": "You have 2 new campaign invitations",
                "data": json.dumps({"count": 2}),
            },
        ]

        _store_notifications(notifs)

        stored = get_notifications()
        assert len(stored) >= 1
        latest = stored[0]
        assert latest["type"] == "new_campaigns"
        assert latest["title"] == "New Campaigns"
        assert latest["read"] == 0


# ── Background Agent Loop ────────────────────────────────────────────


class TestBackgroundAgentLoop:
    """Test the main agent loop — pause, resume, stop, intervals."""

    @pytest.mark.asyncio
    async def test_pause_prevents_execution(self):
        """When paused, no tasks are executed."""
        from background_agent import BackgroundAgent

        agent = BackgroundAgent()
        agent.paused = True

        # Set all "last" timestamps to now so no interval-based tasks fire
        now = time.time()
        agent.last_poll = now
        agent.last_health_check = now
        agent.last_profile_refresh = now

        call_log = []

        async def mock_execute():
            call_log.append("executed")
            return {"success": True, "executed": 0, "succeeded": 0, "failed": 0}

        with patch("background_agent.execute_due_posts", new_callable=AsyncMock, side_effect=mock_execute), \
             patch("background_agent.LOOP_INTERVAL", 0.02):
            agent.running = True
            agent.paused = True

            task = asyncio.create_task(agent.run())
            await asyncio.sleep(0.15)
            agent.stop()
            await asyncio.wait_for(task, timeout=3.0)

        # No tasks should have been called because agent was paused
        assert "executed" not in call_log

    @pytest.mark.asyncio
    async def test_resume_restarts_execution(self):
        """After resume, tasks execute again."""
        from background_agent import BackgroundAgent

        agent = BackgroundAgent()
        agent.paused = True

        # Set all "last" timestamps to now so no interval-based tasks fire
        now = time.time()
        agent.last_poll = now
        agent.last_health_check = now
        agent.last_profile_refresh = now

        executed = []

        async def mock_execute():
            executed.append(True)
            return {"success": True, "executed": 0, "succeeded": 0, "failed": 0}

        with patch("background_agent.execute_due_posts", new_callable=AsyncMock, side_effect=mock_execute), \
             patch("background_agent.run_metric_scraping", new_callable=AsyncMock, return_value={"success": True}), \
             patch("background_agent.LOOP_INTERVAL", 0.02):
            task = asyncio.create_task(agent.run())
            await asyncio.sleep(0.1)
            assert len(executed) == 0  # paused

            agent.resume()
            await asyncio.sleep(0.2)
            agent.stop()
            await asyncio.wait_for(task, timeout=3.0)

        assert len(executed) > 0  # executed after resume

    @pytest.mark.asyncio
    async def test_stop_terminates_loop(self):
        """Calling stop() causes run() to exit."""
        from background_agent import BackgroundAgent

        agent = BackgroundAgent()

        # Set all "last" timestamps to now so no interval-based tasks fire
        now = time.time()
        agent.last_poll = now
        agent.last_health_check = now
        agent.last_profile_refresh = now

        with patch("background_agent.execute_due_posts", new_callable=AsyncMock,
                    return_value={"success": True, "executed": 0, "succeeded": 0, "failed": 0}), \
             patch("background_agent.run_metric_scraping", new_callable=AsyncMock, return_value={"success": True}), \
             patch("background_agent.LOOP_INTERVAL", 0.02):
            task = asyncio.create_task(agent.run())
            await asyncio.sleep(0.1)
            agent.stop()
            await asyncio.wait_for(task, timeout=3.0)

        assert agent.running is False

    @pytest.mark.asyncio
    async def test_agent_status_while_running(self):
        """get_status returns correct state while agent runs."""
        from background_agent import BackgroundAgent

        agent = BackgroundAgent()
        status = agent.get_status()

        assert status["running"] is True
        assert status["paused"] is False
        assert status["iteration_count"] == 0
        assert status["last_poll_ago"] is None

    @pytest.mark.asyncio
    async def test_agent_status_after_iteration(self):
        """After an iteration, last_poll_ago is populated."""
        from background_agent import BackgroundAgent

        agent = BackgroundAgent()
        agent.last_poll = time.time() - 120  # 2 minutes ago

        status = agent.get_status()
        assert status["last_poll_ago"] is not None
        assert status["last_poll_ago"] >= 119  # approximately 120s


# ── Interval Enforcement ─────────────────────────────────────────────


class TestIntervalEnforcement:
    """Test that tasks run at their correct intervals."""

    @pytest.mark.asyncio
    async def test_campaign_poll_interval(self):
        """Campaigns are polled every 10 minutes (POLL_INTERVAL)."""
        from background_agent import BackgroundAgent, POLL_INTERVAL

        agent = BackgroundAgent()
        poll_calls = []

        async def mock_poll():
            poll_calls.append(time.time())
            return {"success": True, "total": 0, "new": 0}

        # Simulate: last poll was 5 minutes ago (not due)
        now = time.time()
        agent.last_poll = now - 300  # 5 min ago
        agent.last_health_check = now  # not due
        agent.last_profile_refresh = now  # not due

        with patch("background_agent.poll_campaigns", new_callable=AsyncMock, side_effect=mock_poll), \
             patch("background_agent.execute_due_posts", new_callable=AsyncMock,
                   return_value={"success": True, "executed": 0, "succeeded": 0, "failed": 0}), \
             patch("background_agent.run_metric_scraping", new_callable=AsyncMock, return_value={"success": True}), \
             patch("background_agent.LOOP_INTERVAL", 0.02):
            task = asyncio.create_task(agent.run())
            await asyncio.sleep(0.15)
            agent.stop()
            await asyncio.wait_for(task, timeout=3.0)

        # Should NOT have polled (5 min < 10 min interval)
        assert len(poll_calls) == 0

    @pytest.mark.asyncio
    async def test_campaign_poll_fires_when_due(self):
        """Campaign poll fires when enough time has elapsed."""
        from background_agent import BackgroundAgent, POLL_INTERVAL

        agent = BackgroundAgent()
        poll_calls = []

        async def mock_poll():
            poll_calls.append(time.time())
            return {"success": True, "total": 0, "new": 0}

        # Simulate: last poll was 11 minutes ago (overdue)
        now = time.time()
        agent.last_poll = now - 660
        agent.last_health_check = now  # not due
        agent.last_profile_refresh = now  # not due

        with patch("background_agent.poll_campaigns", new_callable=AsyncMock, side_effect=mock_poll), \
             patch("background_agent.execute_due_posts", new_callable=AsyncMock,
                   return_value={"success": True, "executed": 0, "succeeded": 0, "failed": 0}), \
             patch("background_agent.run_metric_scraping", new_callable=AsyncMock, return_value={"success": True}), \
             patch("background_agent.LOOP_INTERVAL", 0.02):
            task = asyncio.create_task(agent.run())
            await asyncio.sleep(0.15)
            agent.stop()
            await asyncio.wait_for(task, timeout=3.0)

        assert len(poll_calls) >= 1

    @pytest.mark.asyncio
    async def test_health_check_interval(self):
        """Session health check runs every 30 minutes."""
        from background_agent import BackgroundAgent

        agent = BackgroundAgent()
        health_calls = []

        async def mock_health():
            health_calls.append(True)
            return {"success": True, "platforms": {}}

        # Last check was 31 minutes ago
        now = time.time()
        agent.last_health_check = now - 1860
        agent.last_poll = now  # not due
        agent.last_profile_refresh = now  # not due

        with patch("background_agent.check_sessions", new_callable=AsyncMock, side_effect=mock_health), \
             patch("background_agent.execute_due_posts", new_callable=AsyncMock,
                   return_value={"success": True, "executed": 0, "succeeded": 0, "failed": 0}), \
             patch("background_agent.run_metric_scraping", new_callable=AsyncMock, return_value={"success": True}), \
             patch("background_agent.LOOP_INTERVAL", 0.02):
            task = asyncio.create_task(agent.run())
            await asyncio.sleep(0.15)
            agent.stop()
            await asyncio.wait_for(task, timeout=3.0)

        assert len(health_calls) >= 1

    @pytest.mark.asyncio
    async def test_profile_refresh_interval(self):
        """Profile refresh runs every 7 days."""
        from background_agent import BackgroundAgent

        agent = BackgroundAgent()
        refresh_calls = []

        async def mock_refresh():
            refresh_calls.append(True)
            return {"success": True, "refreshed": 2, "skipped": False}

        # Last refresh was 8 days ago
        agent.last_profile_refresh = time.time() - (8 * 86400)
        agent.last_poll = time.time()
        agent.last_health_check = time.time()

        with patch("background_agent.refresh_profiles", new_callable=AsyncMock, side_effect=mock_refresh), \
             patch("background_agent.execute_due_posts", new_callable=AsyncMock,
                   return_value={"success": True, "executed": 0, "succeeded": 0, "failed": 0}), \
             patch("background_agent.run_metric_scraping", new_callable=AsyncMock, return_value={"success": True}), \
             patch("background_agent.LOOP_INTERVAL", 0.02), \
             patch("background_agent.POLL_INTERVAL", 999999), \
             patch("background_agent.HEALTH_CHECK_INTERVAL", 999999):
            task = asyncio.create_task(agent.run())
            await asyncio.sleep(0.15)
            agent.stop()
            await asyncio.wait_for(task, timeout=3.0)

        assert len(refresh_calls) >= 1

    @pytest.mark.asyncio
    async def test_profile_refresh_skipped_when_not_due(self):
        """Profile refresh does not run if < 7 days since last refresh."""
        from background_agent import BackgroundAgent

        agent = BackgroundAgent()
        refresh_calls = []

        async def mock_refresh():
            refresh_calls.append(True)
            return {"success": True, "refreshed": 0, "skipped": True}

        # Last refresh was 3 days ago (not due)
        agent.last_profile_refresh = time.time() - (3 * 86400)
        agent.last_poll = time.time()
        agent.last_health_check = time.time()

        with patch("background_agent.refresh_profiles", new_callable=AsyncMock, side_effect=mock_refresh), \
             patch("background_agent.execute_due_posts", new_callable=AsyncMock,
                   return_value={"success": True, "executed": 0, "succeeded": 0, "failed": 0}), \
             patch("background_agent.run_metric_scraping", new_callable=AsyncMock, return_value={"success": True}), \
             patch("background_agent.LOOP_INTERVAL", 0.02), \
             patch("background_agent.POLL_INTERVAL", 999999), \
             patch("background_agent.HEALTH_CHECK_INTERVAL", 999999):
            task = asyncio.create_task(agent.run())
            await asyncio.sleep(0.15)
            agent.stop()
            await asyncio.wait_for(task, timeout=3.0)

        # refresh_profiles should NOT have been called (interval not elapsed)
        assert len(refresh_calls) == 0


# ── Error Resilience ─────────────────────────────────────────────────


class TestErrorResilience:
    """Test that individual task errors don't crash the whole agent."""

    @pytest.mark.asyncio
    async def test_agent_continues_after_post_execution_error(self):
        """If execute_due_posts crashes, the agent loop continues."""
        from background_agent import BackgroundAgent

        agent = BackgroundAgent()
        iterations = []

        async def crashing_execute():
            iterations.append("post_crash")
            raise RuntimeError("Playwright exploded")

        async def ok_metrics():
            iterations.append("metrics_ok")
            return {"success": True}

        # All intervals set to never fire except posts/metrics
        agent.last_poll = time.time()
        agent.last_health_check = time.time()
        agent.last_profile_refresh = time.time()

        with patch("background_agent.execute_due_posts", new_callable=AsyncMock, side_effect=crashing_execute), \
             patch("background_agent.run_metric_scraping", new_callable=AsyncMock, side_effect=ok_metrics), \
             patch("background_agent.LOOP_INTERVAL", 0.02), \
             patch("background_agent.POLL_INTERVAL", 999999), \
             patch("background_agent.HEALTH_CHECK_INTERVAL", 999999), \
             patch("background_agent.PROFILE_REFRESH_INTERVAL", 999999):
            task = asyncio.create_task(agent.run())
            await asyncio.sleep(0.2)
            agent.stop()
            await asyncio.wait_for(task, timeout=3.0)

        # Agent should have continued to metric scraping despite post crash
        assert "metrics_ok" in iterations

    @pytest.mark.asyncio
    async def test_agent_continues_after_metric_scraping_error(self):
        """If run_metric_scraping crashes, the agent loop continues."""
        from background_agent import BackgroundAgent

        agent = BackgroundAgent()
        iteration_count_before_stop = 0

        async def ok_posts():
            return {"success": True, "executed": 0, "succeeded": 0, "failed": 0}

        async def crashing_metrics():
            raise RuntimeError("Browser timeout")

        agent.last_poll = time.time()
        agent.last_health_check = time.time()
        agent.last_profile_refresh = time.time()

        with patch("background_agent.execute_due_posts", new_callable=AsyncMock, side_effect=ok_posts), \
             patch("background_agent.run_metric_scraping", new_callable=AsyncMock, side_effect=crashing_metrics), \
             patch("background_agent.LOOP_INTERVAL", 0.02), \
             patch("background_agent.POLL_INTERVAL", 999999), \
             patch("background_agent.HEALTH_CHECK_INTERVAL", 999999), \
             patch("background_agent.PROFILE_REFRESH_INTERVAL", 999999):
            task = asyncio.create_task(agent.run())
            await asyncio.sleep(0.2)
            iteration_count_before_stop = agent._iteration_count
            agent.stop()
            await asyncio.wait_for(task, timeout=3.0)

        # Agent ran multiple iterations despite metrics crashing every time
        assert iteration_count_before_stop >= 1

    @pytest.mark.asyncio
    async def test_agent_continues_after_notification_error(self):
        """If notification building fails, the agent loop continues."""
        from background_agent import BackgroundAgent

        agent = BackgroundAgent()

        agent.last_poll = time.time()
        agent.last_health_check = time.time()
        agent.last_profile_refresh = time.time()

        with patch("background_agent.execute_due_posts", new_callable=AsyncMock,
                    return_value={"success": True, "executed": 0, "succeeded": 0, "failed": 0}), \
             patch("background_agent.run_metric_scraping", new_callable=AsyncMock, return_value={"success": True}), \
             patch("background_agent._build_notifications", side_effect=Exception("JSON error")), \
             patch("background_agent.LOOP_INTERVAL", 0.02), \
             patch("background_agent.POLL_INTERVAL", 999999), \
             patch("background_agent.HEALTH_CHECK_INTERVAL", 999999), \
             patch("background_agent.PROFILE_REFRESH_INTERVAL", 999999):
            task = asyncio.create_task(agent.run())
            await asyncio.sleep(0.2)
            agent.stop()
            await asyncio.wait_for(task, timeout=3.0)

        # Agent should have completed multiple iterations
        assert agent._iteration_count >= 1


# ── Start / Stop Agent ───────────────────────────────────────────────


class TestStartStopAgent:
    """Test module-level start/stop functions."""

    @pytest.mark.asyncio
    async def test_start_creates_running_agent(self):
        """start_background_agent creates and starts an agent."""
        import background_agent

        # Reset module state
        background_agent._agent = None

        with patch("background_agent.execute_due_posts", new_callable=AsyncMock,
                    return_value={"success": True, "executed": 0, "succeeded": 0, "failed": 0}), \
             patch("background_agent.run_metric_scraping", new_callable=AsyncMock, return_value={"success": True}), \
             patch("background_agent.LOOP_INTERVAL", 0.01), \
             patch("background_agent.POLL_INTERVAL", 999999), \
             patch("background_agent.HEALTH_CHECK_INTERVAL", 999999), \
             patch("background_agent.PROFILE_REFRESH_INTERVAL", 999999):
            agent = await background_agent.start_background_agent()
            assert agent is not None
            assert agent.running is True

            await asyncio.sleep(0.05)
            await background_agent.stop_background_agent()

        assert background_agent._agent is None

    @pytest.mark.asyncio
    async def test_double_start_returns_same_agent(self):
        """Calling start twice returns the existing agent."""
        import background_agent

        background_agent._agent = None

        with patch("background_agent.execute_due_posts", new_callable=AsyncMock,
                    return_value={"success": True, "executed": 0, "succeeded": 0, "failed": 0}), \
             patch("background_agent.run_metric_scraping", new_callable=AsyncMock, return_value={"success": True}), \
             patch("background_agent.LOOP_INTERVAL", 0.01), \
             patch("background_agent.POLL_INTERVAL", 999999), \
             patch("background_agent.HEALTH_CHECK_INTERVAL", 999999), \
             patch("background_agent.PROFILE_REFRESH_INTERVAL", 999999):
            agent1 = await background_agent.start_background_agent()
            agent2 = await background_agent.start_background_agent()
            assert agent1 is agent2

            await background_agent.stop_background_agent()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Stopping when no agent is running is a no-op."""
        import background_agent

        background_agent._agent = None
        await background_agent.stop_background_agent()  # Should not raise


# ── Local DB Notification Functions ──────────────────────────────────


class TestNotificationDB:
    """Test notification CRUD in local_db."""

    def test_add_and_get_notification(self):
        from utils.local_db import add_notification, get_notifications

        nid = add_notification("test_type", "Test Title", "Test message", '{"key": "val"}')
        assert nid > 0

        notifs = get_notifications()
        assert len(notifs) >= 1
        found = [n for n in notifs if n["id"] == nid][0]
        assert found["type"] == "test_type"
        assert found["title"] == "Test Title"
        assert found["message"] == "Test message"
        assert found["read"] == 0

    def test_get_unread_only(self):
        from utils.local_db import add_notification, get_notifications, mark_notifications_read

        nid1 = add_notification("type1", "Title 1", "Msg 1")
        nid2 = add_notification("type2", "Title 2", "Msg 2")

        mark_notifications_read([nid1])

        unread = get_notifications(unread_only=True)
        unread_ids = [n["id"] for n in unread]
        assert nid2 in unread_ids
        assert nid1 not in unread_ids

    def test_notification_limit(self):
        from utils.local_db import add_notification, get_notifications

        for i in range(10):
            add_notification("batch", f"Title {i}", f"Msg {i}")

        limited = get_notifications(limit=5)
        assert len(limited) == 5
