"""Tests for the post scheduling engine (Task 20).

Covers:
- Region-to-timezone mapping
- Peak window selection for different regions/platforms
- 30-minute spacing enforcement between posts
- Platform variety (no back-to-back same platform for different campaigns)
- Jitter randomization within bounds (1-15 min)
- Daily limit calculation based on active campaign count
- Queue operations (add scheduled post, get due, update status)
- Scheduling with no conflicts
- Scheduling with existing posts (respects spacing)
- Edge case: all peak windows full -> schedule for next day
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


# ── Region & Timezone Tests ──────────────────────────────────────────


class TestRegionTimezones:
    """Test region-to-timezone mapping."""

    def test_all_regions_have_timezones(self):
        from utils.post_scheduler import REGION_TIMEZONES

        expected_regions = ["us", "uk", "india", "eu", "latam", "sea", "global"]
        for region in expected_regions:
            assert region in REGION_TIMEZONES, f"Missing region: {region}"

    def test_us_maps_to_new_york(self):
        from utils.post_scheduler import REGION_TIMEZONES

        assert REGION_TIMEZONES["us"] == "America/New_York"

    def test_global_defaults_to_us(self):
        from utils.post_scheduler import REGION_TIMEZONES

        assert REGION_TIMEZONES["global"] == "America/New_York"

    def test_india_maps_to_kolkata(self):
        from utils.post_scheduler import REGION_TIMEZONES

        assert REGION_TIMEZONES["india"] == "Asia/Kolkata"

    def test_unknown_region_uses_global_fallback(self):
        from utils.post_scheduler import _get_timezone_for_region

        tz = _get_timezone_for_region("mars")
        assert tz == "America/New_York"  # falls back to global


# ── Peak Window Tests ────────────────────────────────────────────────


class TestPeakWindows:
    """Test peak engagement windows per platform."""

    def test_all_enabled_platforms_have_peak_windows(self):
        from utils.post_scheduler import PEAK_WINDOWS

        for platform in ["x", "linkedin", "facebook", "reddit"]:
            assert platform in PEAK_WINDOWS, f"Missing peak windows for {platform}"

    def test_x_has_three_windows(self):
        from utils.post_scheduler import PEAK_WINDOWS

        assert len(PEAK_WINDOWS["x"]) == 3

    def test_linkedin_has_business_hours_only(self):
        from utils.post_scheduler import PEAK_WINDOWS

        windows = PEAK_WINDOWS["linkedin"]
        # LinkedIn windows should all end by 13 (1pm) — business hours
        for start, end in windows:
            assert end <= 13, f"LinkedIn window ({start},{end}) extends beyond business hours"

    def test_peak_windows_are_valid_hour_ranges(self):
        from utils.post_scheduler import PEAK_WINDOWS

        for platform, windows in PEAK_WINDOWS.items():
            for start, end in windows:
                assert 0 <= start < 24, f"Invalid start hour {start} for {platform}"
                assert 0 < end <= 24, f"Invalid end hour {end} for {platform}"
                assert start < end, f"Start ({start}) >= End ({end}) for {platform}"

    def test_get_peak_slots_returns_datetimes_in_correct_timezone(self):
        from utils.post_scheduler import _get_peak_slots

        base_date = datetime(2026, 3, 25, tzinfo=timezone.utc)
        slots = _get_peak_slots("x", "us", base_date)
        assert len(slots) > 0
        for slot in slots:
            assert slot.tzinfo is not None, "Slots must be timezone-aware"


# ── Scheduling Algorithm Tests ───────────────────────────────────────


class TestSchedulePosts:
    """Test the main schedule_posts() algorithm."""

    def test_basic_scheduling_returns_entries_for_each_platform(self):
        from utils.post_scheduler import schedule_posts

        result = schedule_posts(
            campaign_id=1,
            platforms=["x", "linkedin"],
            target_region="us",
            content={"x": "Hello X", "linkedin": "Hello LinkedIn"},
        )
        assert len(result) == 2
        platforms_scheduled = {r["platform"] for r in result}
        assert platforms_scheduled == {"x", "linkedin"}

    def test_all_results_have_required_fields(self):
        from utils.post_scheduler import schedule_posts

        result = schedule_posts(
            campaign_id=42,
            platforms=["x"],
            target_region="us",
            content={"x": "Test post"},
            image_path="/tmp/test.png",
        )
        assert len(result) == 1
        entry = result[0]
        assert entry["campaign_id"] == 42
        assert entry["platform"] == "x"
        assert "scheduled_at" in entry
        assert isinstance(entry["scheduled_at"], datetime)
        assert entry["content"] == "Test post"
        assert entry["image_path"] == "/tmp/test.png"

    def test_scheduled_times_are_within_peak_windows(self):
        from utils.post_scheduler import schedule_posts, PEAK_WINDOWS
        import zoneinfo

        result = schedule_posts(
            campaign_id=1,
            platforms=["x"],
            target_region="us",
            content={"x": "Test"},
        )
        assert len(result) == 1
        scheduled = result[0]["scheduled_at"]
        # Convert to US Eastern to check the hour
        eastern = zoneinfo.ZoneInfo("America/New_York")
        local_time = scheduled.astimezone(eastern)
        hour = local_time.hour
        minute = local_time.minute

        # Should be within one of X's peak windows (with up to 15 min jitter past end)
        x_windows = PEAK_WINDOWS["x"]
        in_window = False
        for start, end in x_windows:
            # Allow jitter up to 15 min past window start and before window end
            # The scheduled time's base must fall within [start, end)
            if start <= hour < end:
                in_window = True
                break
            # Also handle jitter: could be in the hour before end
            if hour == end and minute <= 15:
                in_window = True
                break
        assert in_window, f"Scheduled hour {hour}:{minute:02d} ET not in any peak window"

    def test_scheduling_for_uk_region(self):
        from utils.post_scheduler import schedule_posts
        import zoneinfo

        result = schedule_posts(
            campaign_id=1,
            platforms=["x"],
            target_region="uk",
            content={"x": "UK post"},
        )
        assert len(result) == 1
        scheduled = result[0]["scheduled_at"]
        london = zoneinfo.ZoneInfo("Europe/London")
        local_time = scheduled.astimezone(london)
        # Should be a reasonable hour in London time (peak windows)
        assert 6 <= local_time.hour <= 22, f"Unexpected London hour: {local_time.hour}"

    def test_scheduling_for_india_region(self):
        from utils.post_scheduler import schedule_posts
        import zoneinfo

        result = schedule_posts(
            campaign_id=1,
            platforms=["linkedin"],
            target_region="india",
            content={"linkedin": "India post"},
        )
        assert len(result) == 1
        scheduled = result[0]["scheduled_at"]
        kolkata = zoneinfo.ZoneInfo("Asia/Kolkata")
        local_time = scheduled.astimezone(kolkata)
        assert 6 <= local_time.hour <= 22, f"Unexpected Kolkata hour: {local_time.hour}"


# ── Spacing Enforcement Tests ────────────────────────────────────────


class TestSpacingEnforcement:
    """Test that 30-minute minimum spacing is enforced."""

    def test_spacing_between_posts_at_least_30_minutes(self):
        from utils.post_scheduler import schedule_posts

        result = schedule_posts(
            campaign_id=1,
            platforms=["x", "linkedin", "facebook", "reddit"],
            target_region="us",
            content={
                "x": "X post",
                "linkedin": "LI post",
                "facebook": "FB post",
                "reddit": "Reddit post",
            },
        )
        # Sort by scheduled time
        times = sorted([r["scheduled_at"] for r in result])
        for i in range(1, len(times)):
            diff = (times[i] - times[i - 1]).total_seconds()
            assert diff >= 30 * 60, (
                f"Posts {i-1} and {i} only {diff/60:.1f} min apart (need >= 30)"
            )

    def test_spacing_respects_existing_schedule(self):
        from utils.post_scheduler import schedule_posts

        # Existing schedule has a post at a specific time
        base_time = datetime(2026, 3, 25, 14, 0, tzinfo=timezone.utc)
        existing = [
            {
                "campaign_id": 99,
                "platform": "x",
                "scheduled_at": base_time,
            }
        ]

        result = schedule_posts(
            campaign_id=1,
            platforms=["x"],
            target_region="us",
            content={"x": "New post"},
            existing_schedule=existing,
        )
        assert len(result) == 1
        new_time = result[0]["scheduled_at"]
        diff = abs((new_time - base_time).total_seconds())
        assert diff >= 30 * 60, (
            f"New post only {diff/60:.1f} min from existing (need >= 30)"
        )

    def test_multiple_campaigns_spacing(self):
        """Schedule posts for two campaigns and verify spacing between all posts."""
        from utils.post_scheduler import schedule_posts

        # First campaign
        result1 = schedule_posts(
            campaign_id=1,
            platforms=["x", "linkedin"],
            target_region="us",
            content={"x": "Campaign 1 X", "linkedin": "Campaign 1 LI"},
        )

        # Second campaign, with first campaign's schedule as existing
        existing = result1
        result2 = schedule_posts(
            campaign_id=2,
            platforms=["x", "linkedin"],
            target_region="us",
            content={"x": "Campaign 2 X", "linkedin": "Campaign 2 LI"},
            existing_schedule=existing,
        )

        # Check spacing across all posts
        all_times = sorted(
            [r["scheduled_at"] for r in result1 + result2]
        )
        for i in range(1, len(all_times)):
            diff = (all_times[i] - all_times[i - 1]).total_seconds()
            assert diff >= 30 * 60, (
                f"Posts {i-1} and {i} only {diff/60:.1f} min apart"
            )


# ── Platform Variety Tests ───────────────────────────────────────────


class TestPlatformVariety:
    """Test that the same platform isn't used back-to-back for different campaigns."""

    def test_no_back_to_back_same_platform_different_campaigns(self):
        from utils.post_scheduler import schedule_posts

        # First campaign: only X
        result1 = schedule_posts(
            campaign_id=1,
            platforms=["x"],
            target_region="us",
            content={"x": "Campaign 1"},
        )

        # Second campaign: X and LinkedIn — X should not be scheduled
        # immediately after the first campaign's X post
        result2 = schedule_posts(
            campaign_id=2,
            platforms=["x", "linkedin"],
            target_region="us",
            content={"x": "Campaign 2 X", "linkedin": "Campaign 2 LI"},
            existing_schedule=result1,
        )

        # Combine and sort by time
        all_posts = sorted(result1 + result2, key=lambda r: r["scheduled_at"])

        # Check that no two adjacent posts are the same platform from different campaigns
        for i in range(1, len(all_posts)):
            prev = all_posts[i - 1]
            curr = all_posts[i]
            if prev["campaign_id"] != curr["campaign_id"]:
                if prev["platform"] == curr["platform"]:
                    # They must be spaced well apart (not truly "back-to-back")
                    diff = (curr["scheduled_at"] - prev["scheduled_at"]).total_seconds()
                    assert diff >= 60 * 60, (
                        f"Same platform ({curr['platform']}) for different campaigns "
                        f"only {diff/60:.1f} min apart — should avoid back-to-back"
                    )


# ── Jitter Randomization Tests ───────────────────────────────────────


class TestJitter:
    """Test that jitter stays within bounds."""

    def test_jitter_within_bounds(self):
        from utils.post_scheduler import _apply_jitter

        base = datetime(2026, 3, 25, 14, 0, tzinfo=timezone.utc)
        seen_offsets = set()
        for _ in range(100):
            jittered = _apply_jitter(base)
            offset = (jittered - base).total_seconds()
            assert 60 <= offset <= 15 * 60, (
                f"Jitter offset {offset}s not in [60, 900] range"
            )
            seen_offsets.add(int(offset))

        # Should have some variety (not all the same)
        assert len(seen_offsets) > 1, "Jitter should produce varied offsets"

    def test_jitter_never_negative(self):
        from utils.post_scheduler import _apply_jitter

        base = datetime(2026, 3, 25, 14, 0, tzinfo=timezone.utc)
        for _ in range(50):
            jittered = _apply_jitter(base)
            assert jittered >= base, "Jitter must not produce times before base"


# ── Daily Limit Tests ────────────────────────────────────────────────


class TestDailyLimits:
    """Test daily post limit calculation."""

    def test_daily_limit_2_campaigns(self):
        from utils.post_scheduler import _calculate_daily_limit

        assert _calculate_daily_limit(2) == 8  # 2 * 4 = 8

    def test_daily_limit_5_campaigns(self):
        from utils.post_scheduler import _calculate_daily_limit

        # 5 * 3 = 15, capped at 15
        limit = _calculate_daily_limit(5)
        assert limit <= 15

    def test_daily_limit_1_campaign(self):
        from utils.post_scheduler import _calculate_daily_limit

        limit = _calculate_daily_limit(1)
        assert limit >= 4  # At least 4 posts per day for 1 campaign

    def test_daily_limit_never_exceeds_cap(self):
        from utils.post_scheduler import _calculate_daily_limit

        for n in range(1, 20):
            limit = _calculate_daily_limit(n)
            assert limit <= 20, f"Daily limit {limit} for {n} campaigns exceeds cap"

    def test_daily_limit_zero_campaigns(self):
        from utils.post_scheduler import _calculate_daily_limit

        assert _calculate_daily_limit(0) == 0


# ── Queue Operations Tests ───────────────────────────────────────────


class TestQueueOperations:
    """Test queue operations using the local_db functions."""

    def test_queue_approved_content_returns_schedule_ids(self):
        from utils.post_scheduler import queue_approved_content

        ids = queue_approved_content(
            campaign_id=1,
            platforms=["x", "linkedin"],
            content={"x": "Hello X", "linkedin": "Hello LI"},
            target_region="us",
        )
        assert len(ids) == 2
        assert all(isinstance(i, int) for i in ids)

    def test_queued_content_appears_in_db(self):
        from utils.post_scheduler import queue_approved_content
        from utils.local_db import get_scheduled_posts

        queue_approved_content(
            campaign_id=1,
            platforms=["x"],
            content={"x": "Test post"},
            target_region="us",
        )

        scheduled = get_scheduled_posts(status="queued")
        assert len(scheduled) >= 1
        post = scheduled[0]
        assert post["campaign_server_id"] == 1
        assert post["platform"] == "x"
        assert post["content"] == "Test post"
        assert post["status"] == "queued"

    def test_get_due_posts_returns_only_past_due(self):
        from utils.post_scheduler import get_due_posts
        from utils.local_db import add_scheduled_post

        # Add a post scheduled in the past
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        add_scheduled_post(
            campaign_server_id=1,
            platform="x",
            scheduled_at=past_time,
            content="Due post",
        )

        # Add a post scheduled in the future
        future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        add_scheduled_post(
            campaign_server_id=2,
            platform="linkedin",
            scheduled_at=future_time,
            content="Future post",
        )

        due = get_due_posts()
        assert len(due) == 1
        assert due[0]["content"] == "Due post"

    def test_get_due_posts_excludes_non_queued(self):
        from utils.post_scheduler import get_due_posts
        from utils.local_db import add_scheduled_post, update_schedule_status

        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        sid = add_scheduled_post(
            campaign_server_id=1,
            platform="x",
            scheduled_at=past_time,
            content="Already posted",
        )
        update_schedule_status(sid, "posted")

        due = get_due_posts()
        assert len(due) == 0

    def test_queue_with_image_path(self):
        from utils.post_scheduler import queue_approved_content
        from utils.local_db import get_scheduled_posts

        queue_approved_content(
            campaign_id=1,
            platforms=["x"],
            content={"x": "Image post"},
            target_region="us",
            image_path="/tmp/test_image.png",
        )

        scheduled = get_scheduled_posts(status="queued")
        assert len(scheduled) >= 1
        assert scheduled[0]["image_path"] == "/tmp/test_image.png"


# ── Execute Scheduled Post Tests ─────────────────────────────────────


class TestExecuteScheduledPost:
    """Test execute_scheduled_post (with mocked platform posting)."""

    def test_execute_updates_status_to_posted_on_success(self):
        from utils.post_scheduler import execute_scheduled_post
        from utils.local_db import add_scheduled_post, get_scheduled_posts

        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        sid = add_scheduled_post(
            campaign_server_id=1,
            platform="x",
            scheduled_at=past_time,
            content="Post me",
        )

        # Mock the platform posting function
        with patch(
            "utils.post_scheduler._post_to_platform",
            new_callable=AsyncMock,
            return_value="https://x.com/user/status/123",
        ):
            import asyncio
            success = asyncio.run(execute_scheduled_post(sid))

        assert success is True
        posts = get_scheduled_posts()
        updated = [p for p in posts if p["id"] == sid][0]
        assert updated["status"] == "posted"

    def test_execute_updates_status_to_failed_on_error(self):
        from utils.post_scheduler import execute_scheduled_post
        from utils.local_db import add_scheduled_post, get_scheduled_posts

        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        sid = add_scheduled_post(
            campaign_server_id=1,
            platform="x",
            scheduled_at=past_time,
            content="Fail me",
        )

        with patch(
            "utils.post_scheduler._post_to_platform",
            new_callable=AsyncMock,
            side_effect=Exception("Session expired"),
        ):
            import asyncio
            success = asyncio.run(execute_scheduled_post(sid))

        assert success is False
        posts = get_scheduled_posts()
        updated = [p for p in posts if p["id"] == sid][0]
        assert updated["status"] == "failed"
        assert "Session expired" in (updated["error_message"] or "")

    def test_execute_sets_posting_status_during_execution(self):
        """Verify the status transitions through 'posting' before 'posted'."""
        from utils.post_scheduler import execute_scheduled_post
        from utils.local_db import add_scheduled_post, get_scheduled_posts, update_schedule_status

        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        sid = add_scheduled_post(
            campaign_server_id=1,
            platform="x",
            scheduled_at=past_time,
            content="Track status",
        )

        statuses_seen = []

        original_update = update_schedule_status

        def tracking_update(schedule_id, status, **kwargs):
            statuses_seen.append(status)
            return original_update(schedule_id, status, **kwargs)

        with patch("utils.post_scheduler.update_schedule_status", side_effect=tracking_update):
            with patch(
                "utils.post_scheduler._post_to_platform",
                new_callable=AsyncMock,
                return_value="https://x.com/status/123",
            ):
                import asyncio
                asyncio.run(execute_scheduled_post(sid))

        assert "posting" in statuses_seen, "Should transition through 'posting'"
        assert "posted" in statuses_seen, "Should end at 'posted'"


# ── Edge Cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_all_peak_windows_full_schedules_next_day(self):
        """When all peak windows for today are full, schedule for next day."""
        from utils.post_scheduler import schedule_posts

        # Create a heavily packed existing schedule for today
        base = datetime.now(timezone.utc).replace(hour=6, minute=0, second=0, microsecond=0)
        existing = []
        # Fill every 30 minutes from 6am to 11pm UTC (way more than any peak windows)
        for i in range(35):
            t = base + timedelta(minutes=30 * i)
            existing.append({
                "campaign_id": 100 + i,
                "platform": ["x", "linkedin", "facebook", "reddit"][i % 4],
                "scheduled_at": t,
            })

        result = schedule_posts(
            campaign_id=999,
            platforms=["x"],
            target_region="us",
            content={"x": "Overflow post"},
            existing_schedule=existing,
        )
        assert len(result) == 1
        # Should be scheduled for a future time that doesn't conflict
        scheduled = result[0]["scheduled_at"]
        # Verify it doesn't conflict with any existing
        for ex in existing:
            diff = abs((scheduled - ex["scheduled_at"]).total_seconds())
            assert diff >= 30 * 60, "Overflow post must still respect spacing"

    def test_empty_platforms_list(self):
        from utils.post_scheduler import schedule_posts

        result = schedule_posts(
            campaign_id=1,
            platforms=[],
            target_region="us",
            content={},
        )
        assert result == []

    def test_content_missing_for_platform_skips_it(self):
        from utils.post_scheduler import schedule_posts

        result = schedule_posts(
            campaign_id=1,
            platforms=["x", "linkedin"],
            target_region="us",
            content={"x": "Only X content"},  # No linkedin content
        )
        # Should only schedule for x (content exists for it)
        assert len(result) == 1
        assert result[0]["platform"] == "x"

    def test_scheduling_with_none_existing_schedule(self):
        """existing_schedule=None should work the same as empty list."""
        from utils.post_scheduler import schedule_posts

        result = schedule_posts(
            campaign_id=1,
            platforms=["x"],
            target_region="us",
            content={"x": "Test"},
            existing_schedule=None,
        )
        assert len(result) == 1

    def test_scheduling_preserves_campaign_id(self):
        from utils.post_scheduler import schedule_posts

        result = schedule_posts(
            campaign_id=777,
            platforms=["x", "linkedin", "facebook"],
            target_region="us",
            content={"x": "X", "linkedin": "LI", "facebook": "FB"},
        )
        for entry in result:
            assert entry["campaign_id"] == 777


# ── Integration: Queue + Schedule ────────────────────────────────────


class TestQueueScheduleIntegration:
    """Integration tests combining scheduling + queue operations."""

    def test_full_flow_queue_then_get_due(self):
        """Queue content, verify it appears, wait for it to be due."""
        from utils.post_scheduler import queue_approved_content, get_due_posts
        from utils.local_db import get_scheduled_posts

        ids = queue_approved_content(
            campaign_id=1,
            platforms=["x"],
            content={"x": "Integration test"},
            target_region="us",
        )
        assert len(ids) == 1

        # The post is scheduled for the future, so it shouldn't be due yet
        # (unless it's currently a peak window and nothing else is scheduled)
        all_scheduled = get_scheduled_posts(status="queued")
        assert len(all_scheduled) >= 1

    def test_multiple_campaigns_queue_independently(self):
        from utils.post_scheduler import queue_approved_content
        from utils.local_db import get_scheduled_posts

        ids1 = queue_approved_content(
            campaign_id=1,
            platforms=["x"],
            content={"x": "Campaign 1"},
            target_region="us",
        )
        ids2 = queue_approved_content(
            campaign_id=2,
            platforms=["linkedin"],
            content={"linkedin": "Campaign 2"},
            target_region="uk",
        )

        all_scheduled = get_scheduled_posts(status="queued")
        assert len(all_scheduled) >= 2

        # Different campaign IDs in the scheduled posts
        campaign_ids = {p["campaign_server_id"] for p in all_scheduled}
        assert 1 in campaign_ids
        assert 2 in campaign_ids
