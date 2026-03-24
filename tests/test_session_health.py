"""Tests for session health monitoring.

Tests cover:
- check_session detects logged-in state (mock page with authenticated elements)
- check_session detects expired session (mock login page redirect)
- check_session handles timeout gracefully (returns yellow)
- check_all_sessions skips platforms without profiles
- check_all_sessions handles one platform failing without blocking others
- Health storage in local_db (get/update)
- Re-auth opens visible browser (mock)
- All Playwright interactions are mocked — no real browsers in tests.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.session_health import (
    check_session,
    check_all_sessions,
    get_session_health,
    update_session_health,
    reauthenticate_platform,
    PLATFORM_AUTH_SELECTORS,
    PLATFORM_LOGIN_INDICATORS,
)
from utils.local_db import get_setting, set_setting


# ── Mock Helpers ──────────────────────────────────────────────────


def _make_mock_locator(count=0, text=None, visible=True):
    """Create a mock Playwright locator."""
    loc = AsyncMock()
    loc.count = AsyncMock(return_value=count)
    first = AsyncMock()
    first.wait_for = AsyncMock()
    if text is not None:
        first.inner_text = AsyncMock(return_value=text)
    first.is_visible = AsyncMock(return_value=visible and count > 0)
    loc.first = first
    return loc


def _make_mock_page(url="https://x.com/home"):
    """Create a mock Playwright page."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.url = url
    page.wait_for_selector = AsyncMock()
    page.locator = MagicMock(return_value=_make_mock_locator(count=0))
    page.wait_for_event = AsyncMock()
    return page


def _make_mock_context(page=None):
    """Create a mock persistent browser context."""
    ctx = AsyncMock()
    if page is None:
        page = _make_mock_page()
    ctx.pages = [page]
    ctx.new_page = AsyncMock(return_value=page)
    ctx.close = AsyncMock()
    return ctx


# ── check_session: Logged-In Detection ──────────────────────────


class TestCheckSessionLoggedIn:
    """Test that check_session returns green when authenticated elements are found."""

    @pytest.mark.asyncio
    async def test_x_logged_in(self):
        """X: compose button present -> green."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page(url="https://x.com/home")
        mock_ctx = _make_mock_context(mock_page)

        # X auth selector (compose button) found
        auth_locator = _make_mock_locator(count=1)
        # X login indicator not found
        login_locator = _make_mock_locator(count=0)

        def locator_side_effect(selector):
            for sel in PLATFORM_AUTH_SELECTORS["x"]:
                if selector == sel:
                    return auth_locator
            for sel in PLATFORM_LOGIN_INDICATORS["x"]:
                if selector == sel:
                    return login_locator
            return _make_mock_locator(count=0)

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.session_health._launch_context", return_value=mock_ctx):
            result = await check_session("x", mock_pw)

        assert result["platform"] == "x"
        assert result["status"] == "green"
        assert "logged in" in result["details"].lower() or "authenticated" in result["details"].lower()

    @pytest.mark.asyncio
    async def test_linkedin_logged_in(self):
        """LinkedIn: nav profile icon present -> green."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page(url="https://www.linkedin.com/feed/")
        mock_ctx = _make_mock_context(mock_page)

        auth_locator = _make_mock_locator(count=1)
        login_locator = _make_mock_locator(count=0)

        def locator_side_effect(selector):
            for sel in PLATFORM_AUTH_SELECTORS["linkedin"]:
                if selector == sel:
                    return auth_locator
            for sel in PLATFORM_LOGIN_INDICATORS["linkedin"]:
                if selector == sel:
                    return login_locator
            return _make_mock_locator(count=0)

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.session_health._launch_context", return_value=mock_ctx):
            result = await check_session("linkedin", mock_pw)

        assert result["platform"] == "linkedin"
        assert result["status"] == "green"

    @pytest.mark.asyncio
    async def test_facebook_logged_in(self):
        """Facebook: composer area present -> green."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page(url="https://www.facebook.com/")
        mock_ctx = _make_mock_context(mock_page)

        auth_locator = _make_mock_locator(count=1)
        login_locator = _make_mock_locator(count=0)

        def locator_side_effect(selector):
            for sel in PLATFORM_AUTH_SELECTORS["facebook"]:
                if selector == sel:
                    return auth_locator
            for sel in PLATFORM_LOGIN_INDICATORS["facebook"]:
                if selector == sel:
                    return login_locator
            return _make_mock_locator(count=0)

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.session_health._launch_context", return_value=mock_ctx):
            result = await check_session("facebook", mock_pw)

        assert result["platform"] == "facebook"
        assert result["status"] == "green"

    @pytest.mark.asyncio
    async def test_reddit_logged_in(self):
        """Reddit: user menu or create post button present -> green."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page(url="https://www.reddit.com/")
        mock_ctx = _make_mock_context(mock_page)

        auth_locator = _make_mock_locator(count=1)
        login_locator = _make_mock_locator(count=0)

        def locator_side_effect(selector):
            for sel in PLATFORM_AUTH_SELECTORS["reddit"]:
                if selector == sel:
                    return auth_locator
            for sel in PLATFORM_LOGIN_INDICATORS["reddit"]:
                if selector == sel:
                    return login_locator
            return _make_mock_locator(count=0)

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.session_health._launch_context", return_value=mock_ctx):
            result = await check_session("reddit", mock_pw)

        assert result["platform"] == "reddit"
        assert result["status"] == "green"


# ── check_session: Expired Session Detection ─────────────────────


class TestCheckSessionExpired:
    """Test that check_session returns red when login page elements are found."""

    @pytest.mark.asyncio
    async def test_x_session_expired(self):
        """X: login form visible, no auth elements -> red."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page(url="https://x.com/i/flow/login")
        mock_ctx = _make_mock_context(mock_page)

        # No auth selectors found, login indicator found
        auth_locator = _make_mock_locator(count=0)
        login_locator = _make_mock_locator(count=1)

        def locator_side_effect(selector):
            for sel in PLATFORM_AUTH_SELECTORS["x"]:
                if selector == sel:
                    return auth_locator
            for sel in PLATFORM_LOGIN_INDICATORS["x"]:
                if selector == sel:
                    return login_locator
            return _make_mock_locator(count=0)

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.session_health._launch_context", return_value=mock_ctx):
            result = await check_session("x", mock_pw)

        assert result["platform"] == "x"
        assert result["status"] == "red"
        assert "expired" in result["details"].lower() or "login" in result["details"].lower()

    @pytest.mark.asyncio
    async def test_linkedin_session_expired(self):
        """LinkedIn: redirected to login page -> red."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page(url="https://www.linkedin.com/login")
        mock_ctx = _make_mock_context(mock_page)

        auth_locator = _make_mock_locator(count=0)
        login_locator = _make_mock_locator(count=1)

        def locator_side_effect(selector):
            for sel in PLATFORM_AUTH_SELECTORS["linkedin"]:
                if selector == sel:
                    return auth_locator
            for sel in PLATFORM_LOGIN_INDICATORS["linkedin"]:
                if selector == sel:
                    return login_locator
            return _make_mock_locator(count=0)

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.session_health._launch_context", return_value=mock_ctx):
            result = await check_session("linkedin", mock_pw)

        assert result["platform"] == "linkedin"
        assert result["status"] == "red"

    @pytest.mark.asyncio
    async def test_facebook_session_expired(self):
        """Facebook: login form present, no auth elements -> red."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page(url="https://www.facebook.com/login")
        mock_ctx = _make_mock_context(mock_page)

        auth_locator = _make_mock_locator(count=0)
        login_locator = _make_mock_locator(count=1)

        def locator_side_effect(selector):
            for sel in PLATFORM_AUTH_SELECTORS["facebook"]:
                if selector == sel:
                    return auth_locator
            for sel in PLATFORM_LOGIN_INDICATORS["facebook"]:
                if selector == sel:
                    return login_locator
            return _make_mock_locator(count=0)

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.session_health._launch_context", return_value=mock_ctx):
            result = await check_session("facebook", mock_pw)

        assert result["platform"] == "facebook"
        assert result["status"] == "red"

    @pytest.mark.asyncio
    async def test_reddit_session_expired(self):
        """Reddit: login prompt present, no auth elements -> red."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page(url="https://www.reddit.com/login")
        mock_ctx = _make_mock_context(mock_page)

        auth_locator = _make_mock_locator(count=0)
        login_locator = _make_mock_locator(count=1)

        def locator_side_effect(selector):
            for sel in PLATFORM_AUTH_SELECTORS["reddit"]:
                if selector == sel:
                    return auth_locator
            for sel in PLATFORM_LOGIN_INDICATORS["reddit"]:
                if selector == sel:
                    return login_locator
            return _make_mock_locator(count=0)

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.session_health._launch_context", return_value=mock_ctx):
            result = await check_session("reddit", mock_pw)

        assert result["platform"] == "reddit"
        assert result["status"] == "red"


# ── check_session: Timeout / Yellow State ────────────────────────


class TestCheckSessionTimeout:
    """Test that check_session returns yellow when neither state is confirmed."""

    @pytest.mark.asyncio
    async def test_timeout_returns_yellow(self):
        """Neither auth nor login elements found -> yellow."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page(url="https://x.com/home")
        mock_ctx = _make_mock_context(mock_page)

        # Nothing found at all
        mock_page.locator = MagicMock(return_value=_make_mock_locator(count=0))

        with patch("utils.session_health._launch_context", return_value=mock_ctx):
            result = await check_session("x", mock_pw)

        assert result["platform"] == "x"
        assert result["status"] == "yellow"
        assert "could not confirm" in result["details"].lower() or "uncertain" in result["details"].lower()

    @pytest.mark.asyncio
    async def test_page_load_exception_returns_yellow(self):
        """Page navigation throws exception -> yellow (not crash)."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page()
        mock_page.goto = AsyncMock(side_effect=Exception("Navigation timeout"))
        mock_ctx = _make_mock_context(mock_page)

        with patch("utils.session_health._launch_context", return_value=mock_ctx):
            result = await check_session("x", mock_pw)

        assert result["platform"] == "x"
        assert result["status"] == "yellow"

    @pytest.mark.asyncio
    async def test_browser_launch_failure_returns_yellow(self):
        """Browser context fails to launch -> yellow."""
        mock_pw = AsyncMock()

        with patch("utils.session_health._launch_context",
                    side_effect=Exception("Browser launch failed")):
            result = await check_session("x", mock_pw)

        assert result["platform"] == "x"
        assert result["status"] == "yellow"
        assert "error" in result["details"].lower() or "failed" in result["details"].lower()


# ── check_all_sessions: Orchestrator ─────────────────────────────


class TestCheckAllSessions:

    @pytest.mark.asyncio
    async def test_skips_platforms_without_profiles(self, tmp_path):
        """Only checks platforms that have profile directories."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        # Create only x-profile
        (profiles_dir / "x-profile").mkdir()
        # linkedin-profile does NOT exist

        async def mock_check(platform, pw):
            return {
                "platform": platform,
                "status": "green",
                "details": "Authenticated",
            }

        with patch("utils.session_health.ROOT", tmp_path), \
             patch("utils.session_health.check_session", side_effect=mock_check), \
             patch("utils.session_health.async_playwright") as mock_pw_cm:
            mock_pw_instance = AsyncMock()
            mock_pw_cm.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
            mock_pw_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await check_all_sessions()

        # Only x should be checked (has profile dir)
        assert "x" in results
        assert results["x"]["status"] == "green"
        # linkedin should NOT be in results (no profile dir)
        platforms_checked = list(results.keys())
        for p in platforms_checked:
            profile_path = profiles_dir / f"{p}-profile"
            assert profile_path.exists(), f"Platform {p} checked but has no profile dir"

    @pytest.mark.asyncio
    async def test_handles_one_platform_failing(self, tmp_path):
        """One platform failure does not block others."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "x-profile").mkdir()
        (profiles_dir / "linkedin-profile").mkdir()

        call_count = {"x": 0, "linkedin": 0}

        async def mock_check(platform, pw):
            call_count[platform] = call_count.get(platform, 0) + 1
            if platform == "x":
                raise Exception("X check crashed")
            return {
                "platform": platform,
                "status": "green",
                "details": "Authenticated",
            }

        with patch("utils.session_health.ROOT", tmp_path), \
             patch("utils.session_health.check_session", side_effect=mock_check), \
             patch("utils.session_health.async_playwright") as mock_pw_cm:
            mock_pw_instance = AsyncMock()
            mock_pw_cm.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
            mock_pw_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await check_all_sessions()

        # X should have error status (yellow fallback)
        assert "x" in results
        assert results["x"]["status"] == "yellow"
        # LinkedIn should succeed
        assert "linkedin" in results
        assert results["linkedin"]["status"] == "green"

    @pytest.mark.asyncio
    async def test_stores_results_in_local_db(self, tmp_path):
        """Results are persisted to local_db settings."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "x-profile").mkdir()

        async def mock_check(platform, pw):
            return {
                "platform": platform,
                "status": "green",
                "details": "Authenticated",
            }

        with patch("utils.session_health.ROOT", tmp_path), \
             patch("utils.session_health.check_session", side_effect=mock_check), \
             patch("utils.session_health.async_playwright") as mock_pw_cm:
            mock_pw_instance = AsyncMock()
            mock_pw_cm.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
            mock_pw_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            await check_all_sessions()

        # Verify stored in local_db
        stored = get_setting("session_health")
        assert stored is not None
        data = json.loads(stored)
        assert "x" in data
        assert data["x"]["status"] == "green"

    @pytest.mark.asyncio
    async def test_no_profiles_returns_empty(self, tmp_path):
        """No profile directories -> empty results."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        # No platform profile dirs created

        with patch("utils.session_health.ROOT", tmp_path), \
             patch("utils.session_health.async_playwright") as mock_pw_cm:
            mock_pw_instance = AsyncMock()
            mock_pw_cm.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
            mock_pw_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await check_all_sessions()

        assert results == {}


# ── Health Storage: get/update ───────────────────────────────────


class TestHealthStorage:
    """Test get_session_health and update_session_health with local_db."""

    def test_get_empty_returns_empty_dict(self):
        """No stored health data -> empty dict."""
        result = get_session_health()
        assert result == {}

    def test_update_and_get_single_platform(self):
        """Store health for one platform and retrieve it."""
        update_session_health("x", "green", "Session confirmed active")
        result = get_session_health()

        assert "x" in result
        assert result["x"]["status"] == "green"
        assert result["x"]["details"] == "Session confirmed active"
        assert "checked_at" in result["x"]

    def test_update_multiple_platforms(self):
        """Store health for multiple platforms and retrieve all."""
        update_session_health("x", "green", "Active")
        update_session_health("linkedin", "red", "Session expired")
        update_session_health("facebook", "yellow", "Uncertain state")

        result = get_session_health()

        assert len(result) == 3
        assert result["x"]["status"] == "green"
        assert result["linkedin"]["status"] == "red"
        assert result["facebook"]["status"] == "yellow"

    def test_update_overwrites_existing(self):
        """Updating the same platform overwrites previous status."""
        update_session_health("x", "green", "Active")
        update_session_health("x", "red", "Session expired after check")

        result = get_session_health()
        assert result["x"]["status"] == "red"
        assert result["x"]["details"] == "Session expired after check"

    def test_get_preserves_other_platforms(self):
        """Updating one platform preserves other platforms' data."""
        update_session_health("x", "green", "Active")
        update_session_health("linkedin", "green", "Active")
        # Now update only x
        update_session_health("x", "red", "Expired")

        result = get_session_health()
        assert result["x"]["status"] == "red"
        assert result["linkedin"]["status"] == "green"

    def test_checked_at_is_iso_format(self):
        """checked_at should be ISO 8601 format."""
        update_session_health("x", "green", "Active")
        result = get_session_health()
        checked_at = result["x"]["checked_at"]
        # Should not raise
        datetime.fromisoformat(checked_at)


# ── reauthenticate_platform ──────────────────────────────────────


class TestReauthenticate:

    @pytest.mark.asyncio
    async def test_opens_visible_browser(self):
        """Re-auth launches with headless=False (visible window)."""
        captured_kwargs = {}

        async def mock_launch_persistent_context(**kwargs):
            captured_kwargs.update(kwargs)
            page = _make_mock_page()
            # Simulate user closing the browser
            page.wait_for_event = AsyncMock(return_value=None)
            ctx = _make_mock_context(page)
            return ctx

        mock_pw = AsyncMock()
        mock_pw.chromium.launch_persistent_context = mock_launch_persistent_context

        # Mock async_playwright context manager
        with patch("utils.session_health.async_playwright") as mock_pw_cm:
            mock_pw_cm.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
            mock_pw_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock the post-reauth session check
            with patch("utils.session_health.check_session", return_value={
                "platform": "x", "status": "green", "details": "Authenticated"
            }):
                result = await reauthenticate_platform("x")

        # Verify headless=False was passed
        assert captured_kwargs.get("headless") is False

    @pytest.mark.asyncio
    async def test_navigates_to_platform_url(self):
        """Re-auth navigates to the platform's home URL."""
        goto_calls = []

        async def mock_goto(url, **kwargs):
            goto_calls.append(url)

        mock_page = _make_mock_page()
        mock_page.goto = mock_goto
        mock_page.wait_for_event = AsyncMock(return_value=None)

        async def mock_launch(**kwargs):
            return _make_mock_context(mock_page)

        mock_pw = AsyncMock()
        mock_pw.chromium.launch_persistent_context = mock_launch

        with patch("utils.session_health.async_playwright") as mock_pw_cm:
            mock_pw_cm.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
            mock_pw_cm.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("utils.session_health.check_session", return_value={
                "platform": "x", "status": "green", "details": "Authenticated"
            }):
                await reauthenticate_platform("x")

        assert len(goto_calls) >= 1
        # Should navigate to x home URL
        assert any("x.com" in url for url in goto_calls)

    @pytest.mark.asyncio
    async def test_rechecks_session_after_reauth(self):
        """After browser close, session health is re-checked."""
        check_calls = []

        async def mock_check(platform, pw):
            check_calls.append(platform)
            return {"platform": platform, "status": "green", "details": "Re-authenticated"}

        mock_page = _make_mock_page()
        mock_page.wait_for_event = AsyncMock(return_value=None)

        async def mock_launch(**kwargs):
            return _make_mock_context(mock_page)

        mock_pw = AsyncMock()
        mock_pw.chromium.launch_persistent_context = mock_launch

        with patch("utils.session_health.async_playwright") as mock_pw_cm:
            mock_pw_cm.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
            mock_pw_cm.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch("utils.session_health.check_session", side_effect=mock_check):
                result = await reauthenticate_platform("linkedin")

        assert "linkedin" in check_calls
        assert result["status"] == "green"

    @pytest.mark.asyncio
    async def test_reauth_handles_browser_crash(self):
        """Re-auth handles browser crash gracefully."""
        with patch("utils.session_health.async_playwright") as mock_pw_cm:
            mock_pw = AsyncMock()
            mock_pw.chromium.launch_persistent_context = AsyncMock(
                side_effect=Exception("Browser failed")
            )
            mock_pw_cm.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
            mock_pw_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await reauthenticate_platform("x")

        assert result["platform"] == "x"
        assert result["status"] == "yellow"
        assert "error" in result["details"].lower() or "failed" in result["details"].lower()


# ── Selector Constants ───────────────────────────────────────────


class TestSelectorConstants:
    """Verify selector constant maps have entries for all supported platforms."""

    SUPPORTED_PLATFORMS = ["x", "linkedin", "facebook", "reddit"]

    def test_auth_selectors_exist_for_all_platforms(self):
        """Every supported platform has auth selectors defined."""
        for p in self.SUPPORTED_PLATFORMS:
            assert p in PLATFORM_AUTH_SELECTORS, f"Missing auth selectors for {p}"
            assert len(PLATFORM_AUTH_SELECTORS[p]) > 0, f"Empty auth selectors for {p}"

    def test_login_indicators_exist_for_all_platforms(self):
        """Every supported platform has login indicators defined."""
        for p in self.SUPPORTED_PLATFORMS:
            assert p in PLATFORM_LOGIN_INDICATORS, f"Missing login indicators for {p}"
            assert len(PLATFORM_LOGIN_INDICATORS[p]) > 0, f"Empty login indicators for {p}"

    def test_selectors_are_strings(self):
        """All selectors should be strings (valid CSS selectors)."""
        for platform, selectors in PLATFORM_AUTH_SELECTORS.items():
            for sel in selectors:
                assert isinstance(sel, str), f"Non-string auth selector for {platform}: {sel}"

        for platform, selectors in PLATFORM_LOGIN_INDICATORS.items():
            for sel in selectors:
                assert isinstance(sel, str), f"Non-string login indicator for {platform}: {sel}"


# ── Return Format ────────────────────────────────────────────────


class TestReturnFormat:
    """Verify check_session always returns the expected dict shape."""

    REQUIRED_KEYS = {"platform", "status", "details"}
    VALID_STATUSES = {"green", "yellow", "red"}

    @pytest.mark.asyncio
    async def test_green_return_format(self):
        """Green result has correct shape."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page(url="https://x.com/home")
        mock_ctx = _make_mock_context(mock_page)

        auth_locator = _make_mock_locator(count=1)

        def locator_side_effect(selector):
            for sel in PLATFORM_AUTH_SELECTORS["x"]:
                if selector == sel:
                    return auth_locator
            return _make_mock_locator(count=0)

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.session_health._launch_context", return_value=mock_ctx):
            result = await check_session("x", mock_pw)

        assert self.REQUIRED_KEYS.issubset(result.keys())
        assert result["status"] in self.VALID_STATUSES

    @pytest.mark.asyncio
    async def test_error_return_format(self):
        """Error result still has correct shape."""
        mock_pw = AsyncMock()

        with patch("utils.session_health._launch_context",
                    side_effect=Exception("crash")):
            result = await check_session("reddit", mock_pw)

        assert self.REQUIRED_KEYS.issubset(result.keys())
        assert result["status"] in self.VALID_STATUSES
        assert result["platform"] == "reddit"
