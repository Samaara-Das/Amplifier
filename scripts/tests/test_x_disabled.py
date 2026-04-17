"""Tests for the X/disabled-platform safety guard (Task #40).

Verifies that X cannot be posted to, scraped, or collected metrics for,
regardless of config flags or API tokens. If any of these tests fail
the guard has been weakened and X posting/scraping may resume —
which would suspend user accounts. Treat these tests as blockers.
"""

import os
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.guard import (
    DISABLED_PLATFORMS,
    filter_disabled,
    guard_platform,
    is_platform_disabled,
)


# ── guard.py primitives ──────────────────────────────────────────────


class TestGuardPrimitives:
    def test_x_is_disabled(self):
        assert is_platform_disabled("x") is True

    def test_x_uppercase_is_disabled(self):
        assert is_platform_disabled("X") is True

    def test_x_mixed_case_is_disabled(self):
        assert is_platform_disabled("X ") is True
        assert is_platform_disabled(" x") is True

    def test_active_platforms_not_disabled(self):
        assert is_platform_disabled("linkedin") is False
        assert is_platform_disabled("facebook") is False
        assert is_platform_disabled("reddit") is False

    def test_none_is_not_disabled(self):
        assert is_platform_disabled(None) is False
        assert is_platform_disabled("") is False

    def test_unknown_platform_is_not_disabled(self):
        assert is_platform_disabled("bluesky") is False

    def test_disabled_constant_contains_x(self):
        assert "x" in DISABLED_PLATFORMS

    def test_guard_raises_on_x(self):
        with pytest.raises(ValueError, match="permanently disabled"):
            guard_platform("x", "post")

    def test_guard_raises_on_x_uppercase(self):
        with pytest.raises(ValueError):
            guard_platform("X", "scrape")

    def test_guard_message_includes_action(self):
        with pytest.raises(ValueError, match="action: post"):
            guard_platform("x", "post")

    def test_guard_message_points_to_memory_doc(self):
        with pytest.raises(ValueError, match="project_x_account_locked"):
            guard_platform("x")

    def test_guard_passes_active_platforms(self):
        guard_platform("linkedin", "post")
        guard_platform("facebook", "scrape")
        guard_platform("reddit", "metrics")
        guard_platform(None)

    def test_filter_strips_x(self):
        assert filter_disabled(["x", "linkedin", "facebook"]) == ["linkedin", "facebook"]

    def test_filter_preserves_order(self):
        assert filter_disabled(["linkedin", "x", "facebook"]) == ["linkedin", "facebook"]

    def test_filter_strips_x_case_insensitive(self):
        assert filter_disabled(["X", "LinkedIn"]) == ["LinkedIn"]

    def test_filter_handles_empty(self):
        assert filter_disabled([]) == []
        assert filter_disabled(None) == []

    def test_filter_handles_set(self):
        result = filter_disabled({"x", "linkedin"})
        assert "x" not in result
        assert "linkedin" in result


# ── Integration: guard at entry points ───────────────────────────────


class TestEntryPointGuards:
    """Verify that production entry points actually call the guard."""

    def test_metric_collector_refuses_x_even_with_bearer(self, monkeypatch):
        """Task #40 critical: the X_BEARER_TOKEN bypass path must be closed."""
        monkeypatch.setenv("X_BEARER_TOKEN", "fake_token_for_test")
        from utils.metric_collector import MetricCollector

        collector = MetricCollector()
        # MetricCollector.collect is async; use asyncio to drive it
        import asyncio

        with pytest.raises(ValueError, match="disabled"):
            asyncio.run(collector.collect("https://x.com/any/status/1", "x"))

    def test_profile_scraper_skips_x(self, monkeypatch, tmp_path):
        """scrape_all_profiles must skip X even if passed explicitly."""
        from utils import profile_scraper

        async def _fake_scraper(*args, **kwargs):
            raise AssertionError("scrape_x_profile should never run")

        monkeypatch.setitem(profile_scraper.SCRAPER_MAP, "x", _fake_scraper)

        import asyncio

        # Explicitly pass ["x"] — should result in 0 scrapes, no assertion
        results = asyncio.run(profile_scraper.scrape_all_profiles(["x"]))
        assert "x" not in results or results.get("x") == {}

    def test_post_engine_refuses_x(self):
        """Calling post_to_x directly must raise."""
        from post import post_to_x  # noqa: E402

        import asyncio

        with pytest.raises(ValueError, match="disabled"):
            asyncio.run(post_to_x({"content": "fake", "platform": "x"}))


# ── Server-side guard parity ──────────────────────────────────────────


class TestServerGuard:
    """Ensure server/app/utils/platform_guard.py matches client guard."""

    def test_server_disables_x(self):
        server_path = ROOT / "server"
        sys.path.insert(0, str(server_path))
        try:
            from app.utils.platform_guard import (  # noqa: E402
                DISABLED_PLATFORMS as SERVER_DISABLED,
                is_platform_disabled as server_is_disabled,
                contains_disabled,
            )

            assert "x" in SERVER_DISABLED
            assert server_is_disabled("x") is True
            assert server_is_disabled("linkedin") is False
            assert contains_disabled(["linkedin", "x"]) is True
            assert contains_disabled(["linkedin", "reddit"]) is False
        finally:
            sys.path.remove(str(server_path))

    def test_server_and_client_agree(self):
        server_path = ROOT / "server"
        sys.path.insert(0, str(server_path))
        try:
            from app.utils.platform_guard import DISABLED_PLATFORMS as SERVER_DISABLED

            assert set(SERVER_DISABLED) == set(DISABLED_PLATFORMS), (
                "Server and client DISABLED_PLATFORMS are out of sync — "
                "they must match or campaigns will be accepted for platforms "
                "that users cannot post to."
            )
        finally:
            sys.path.remove(str(server_path))
