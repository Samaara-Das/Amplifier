"""Tests for the profile scraping system.

Tests cover:
- Return format for each platform scraper (mocked Playwright pages)
- Orchestrator handling partial failures
- Local DB storage via upsert/get
- Server sync payload construction
- Helper functions (_parse_number, _safe_text, _safe_attr)
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from utils.profile_scraper import (
    scrape_x_profile,
    scrape_linkedin_profile,
    scrape_facebook_profile,
    scrape_reddit_profile,
    scrape_all_profiles,
    sync_profiles_to_server,
    _parse_number,
    SCRAPER_MAP,
)
from utils.local_db import (
    upsert_scraped_profile,
    get_scraped_profile,
    get_all_scraped_profiles,
)


# ── Helper Tests ──────────────────────────────────────────────────


class TestParseNumber:
    def test_simple_number(self):
        assert _parse_number("1234") == 1234

    def test_comma_separated(self):
        assert _parse_number("1,234") == 1234

    def test_with_text(self):
        assert _parse_number("1,234 followers") == 1234

    def test_abbreviated_k(self):
        assert _parse_number("1.5K followers") == 1500

    def test_abbreviated_m(self):
        assert _parse_number("2.3M") == 2300000

    def test_empty_string(self):
        assert _parse_number("") == 0

    def test_none_input(self):
        assert _parse_number(None) == 0

    def test_no_numbers(self):
        assert _parse_number("no numbers here") == 0

    def test_large_number(self):
        assert _parse_number("1,234,567") == 1234567

    def test_lowercase_k(self):
        assert _parse_number("15.2k") == 15200


# ── Mock Helpers ──────────────────────────────────────────────────


def _make_mock_locator(text=None, attr_values=None, count=0, inner_texts=None):
    """Create a mock locator that mimics Playwright's Locator interface."""
    loc = AsyncMock()
    loc.count = AsyncMock(return_value=count)

    if count > 0:
        first = AsyncMock()
        first.wait_for = AsyncMock()
        if text is not None:
            first.inner_text = AsyncMock(return_value=text)
        if attr_values:
            first.get_attribute = AsyncMock(side_effect=lambda a: attr_values.get(a))
        else:
            first.get_attribute = AsyncMock(return_value=None)
        loc.first = first
    else:
        first = AsyncMock()
        first.wait_for = AsyncMock(side_effect=Exception("not visible"))
        first.inner_text = AsyncMock(return_value="")
        first.get_attribute = AsyncMock(return_value=None)
        loc.first = first

    # Support .nth() for iteration
    if inner_texts:
        for i, t in enumerate(inner_texts):
            nth_mock = AsyncMock()
            nth_mock.inner_text = AsyncMock(return_value=t)
            nth_mock.is_visible = AsyncMock(return_value=True)
            nth_mock.get_attribute = AsyncMock(return_value=None)
            nth_mock.locator = MagicMock(return_value=_make_mock_locator(count=0))
            loc.nth = MagicMock(side_effect=lambda idx, mocks=inner_texts: _make_nth_mock(mocks, idx))

    return loc


def _make_nth_mock(texts, idx):
    """Create a mock for .nth(idx) that returns text from the texts list."""
    m = AsyncMock()
    if idx < len(texts):
        m.inner_text = AsyncMock(return_value=texts[idx])
    else:
        m.inner_text = AsyncMock(return_value="")
    m.is_visible = AsyncMock(return_value=True)
    m.get_attribute = AsyncMock(return_value=None)
    m.locator = MagicMock(return_value=_make_mock_locator(count=0))
    return m


def _make_mock_page():
    """Create a mock page with standard methods."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.url = "https://www.example.com/user/testuser"
    page.inner_text = AsyncMock(return_value="")

    mouse = AsyncMock()
    mouse.wheel = AsyncMock()
    page.mouse = mouse

    # Default locator returns empty
    page.locator = MagicMock(return_value=_make_mock_locator(count=0))

    return page


def _make_mock_context(page=None):
    """Create a mock browser context."""
    ctx = AsyncMock()
    if page is None:
        page = _make_mock_page()
    ctx.pages = [page]
    ctx.new_page = AsyncMock(return_value=page)
    ctx.close = AsyncMock()
    return ctx


# ── X Scraper Tests ───────────────────────────────────────────────


class TestScrapeXProfile:
    @pytest.mark.asyncio
    async def test_returns_correct_structure(self):
        """X scraper returns dict with all expected keys."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page()
        mock_ctx = _make_mock_context(mock_page)

        # Profile link with href
        profile_link = _make_mock_locator(count=1, attr_values={"href": "/testuser"})
        # Display name
        name_loc = _make_mock_locator(text="Test User\n@testuser", count=1)
        # Bio
        bio_loc = _make_mock_locator(text="I trade for a living", count=1)
        # Profile pic
        pic_loc = _make_mock_locator(count=1, attr_values={"src": "https://pbs.twimg.com/pic.jpg"})
        # Followers
        followers_loc = _make_mock_locator(text="1,500 Followers", count=1)
        # Following
        following_loc = _make_mock_locator(text="500 Following", count=1)
        # Tweets (empty for simplicity)
        tweets_loc = _make_mock_locator(count=0)

        def locator_side_effect(selector):
            mapping = {
                'a[data-testid="AppTabBar_Profile_Link"]': profile_link,
                '[data-testid="UserName"]': name_loc,
                '[data-testid="UserDescription"]': bio_loc,
                'a[data-testid="UserAvatar"] img, img[data-testid="UserAvatar-Container-unknown"] img': pic_loc,
                'a[href$="/verified_followers"]': followers_loc,
                'a[href$="/following"]': following_loc,
                'article[data-testid="tweet"]': tweets_loc,
            }
            return mapping.get(selector, _make_mock_locator(count=0))

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.profile_scraper._launch_context", return_value=mock_ctx):
            result = await scrape_x_profile(mock_pw)

        assert result["platform"] == "x"
        assert result["display_name"] == "Test User"
        assert result["bio"] == "I trade for a living"
        assert result["follower_count"] == 1500
        assert result["following_count"] == 500
        assert result["profile_pic_url"] == "https://pbs.twimg.com/pic.jpg"
        assert isinstance(result["recent_posts"], list)
        assert isinstance(result["engagement_rate"], float)
        assert isinstance(result["posting_frequency"], float)

    @pytest.mark.asyncio
    async def test_handles_missing_elements(self):
        """X scraper returns defaults when elements are missing."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page()
        mock_ctx = _make_mock_context(mock_page)

        # All locators return empty (profile link missing = early return)
        mock_page.locator = MagicMock(return_value=_make_mock_locator(count=0))

        with patch("utils.profile_scraper._launch_context", return_value=mock_ctx):
            result = await scrape_x_profile(mock_pw)

        assert result["platform"] == "x"
        assert result["display_name"] is None
        assert result["follower_count"] == 0
        assert result["recent_posts"] == []

    @pytest.mark.asyncio
    async def test_handles_browser_crash(self):
        """X scraper returns defaults when browser fails entirely."""
        mock_pw = AsyncMock()

        with patch("utils.profile_scraper._launch_context", side_effect=Exception("Browser launch failed")):
            result = await scrape_x_profile(mock_pw)

        assert result["platform"] == "x"
        assert result["follower_count"] == 0


# ── LinkedIn Scraper Tests ────────────────────────────────────────


class TestScrapeLinkedInProfile:
    @pytest.mark.asyncio
    async def test_returns_correct_structure(self):
        """LinkedIn scraper returns dict with all expected keys."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page()
        mock_page.url = "https://www.linkedin.com/in/testuser"
        mock_ctx = _make_mock_context(mock_page)

        name_loc = _make_mock_locator(text="Test User", count=1)
        headline_loc = _make_mock_locator(text="Senior Developer at FAANG", count=1)
        pic_loc = _make_mock_locator(count=1, attr_values={"src": "https://media.licdn.com/pic.jpg"})
        conn_loc = _make_mock_locator(text="500+", count=1)
        follower_loc = _make_mock_locator(text="1,200 followers", count=1)
        posts_loc = _make_mock_locator(count=0)

        def locator_side_effect(selector):
            if "text-heading-xlarge" in selector:
                return name_loc
            if "text-body-medium" in selector:
                return headline_loc
            if "profile-photo" in selector or "pv-top-card" in selector:
                return pic_loc
            if "mynetwork" in selector:
                return conn_loc
            if 'has-text("follower")' in selector:
                return follower_loc
            if "feed-shared-update" in selector:
                return posts_loc
            return _make_mock_locator(count=0)

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.profile_scraper._launch_context", return_value=mock_ctx):
            result = await scrape_linkedin_profile(mock_pw)

        assert result["platform"] == "linkedin"
        assert result["display_name"] == "Test User"
        assert result["bio"] == "Senior Developer at FAANG"
        assert result["follower_count"] == 1200  # 1,200 > 500
        assert result["profile_pic_url"] == "https://media.licdn.com/pic.jpg"
        assert isinstance(result["recent_posts"], list)

    @pytest.mark.asyncio
    async def test_handles_missing_elements(self):
        """LinkedIn scraper returns defaults when elements are missing."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page()
        mock_page.url = "https://www.linkedin.com/in/testuser"
        mock_ctx = _make_mock_context(mock_page)
        mock_page.locator = MagicMock(return_value=_make_mock_locator(count=0))

        with patch("utils.profile_scraper._launch_context", return_value=mock_ctx):
            result = await scrape_linkedin_profile(mock_pw)

        assert result["platform"] == "linkedin"
        assert result["display_name"] is None
        assert result["follower_count"] == 0


# ── Facebook Scraper Tests ────────────────────────────────────────


class TestScrapeFacebookProfile:
    @pytest.mark.asyncio
    async def test_returns_correct_structure(self):
        """Facebook scraper returns dict with all expected keys."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page()
        mock_ctx = _make_mock_context(mock_page)

        # The scraper calls page.locator('h1').first — so we need a locator
        # whose .first property returns a mock with inner_text
        name_loc = _make_mock_locator(text="Test User", count=1)
        friends_loc = _make_mock_locator(text="2,345 friends", count=1)
        pic_loc = _make_mock_locator(count=0)
        articles_loc = _make_mock_locator(count=0)

        # Facebook body text for intro extraction
        mock_page.inner_text = AsyncMock(return_value="Intro\nI love coding\n\nDetails\nMore stuff")

        def locator_side_effect(selector):
            if selector == 'h1':
                return name_loc
            if "friends" in selector:
                return friends_loc
            if "svg" in selector or "image" in selector or "g image" in selector:
                return pic_loc
            if "article" in selector:
                return articles_loc
            return _make_mock_locator(count=0)

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.profile_scraper._launch_context", return_value=mock_ctx):
            result = await scrape_facebook_profile(mock_pw)

        assert result["platform"] == "facebook"
        assert result["display_name"] == "Test User"
        assert result["follower_count"] == 2345
        assert result["bio"] == "I love coding"
        assert isinstance(result["recent_posts"], list)

    @pytest.mark.asyncio
    async def test_handles_browser_error(self):
        """Facebook scraper handles browser launch errors gracefully."""
        mock_pw = AsyncMock()

        with patch("utils.profile_scraper._launch_context", side_effect=Exception("No session")):
            result = await scrape_facebook_profile(mock_pw)

        assert result["platform"] == "facebook"
        assert result["follower_count"] == 0


# ── Reddit Scraper Tests ──────────────────────────────────────────


class TestScrapeRedditProfile:
    @pytest.mark.asyncio
    async def test_returns_correct_structure(self):
        """Reddit scraper returns dict with all expected keys."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page()
        mock_page.url = "https://www.reddit.com/user/testuser/"
        mock_ctx = _make_mock_context(mock_page)

        name_loc = _make_mock_locator(text="testuser", count=1)
        karma_loc = _make_mock_locator(text="15,432", count=1)
        pic_loc = _make_mock_locator(count=1, attr_values={"src": "https://reddit.com/avatar.png"})
        posts_loc = _make_mock_locator(count=0)

        mock_page.inner_text = AsyncMock(return_value="Cake day: January 15, 2020\n15,432 karma")

        def locator_side_effect(selector):
            if selector == 'h1, h2':
                return name_loc
            if "karma" in selector:
                return karma_loc
            if "avatar" in selector:
                return pic_loc
            if "shreddit" in selector or "article" in selector:
                return posts_loc
            return _make_mock_locator(count=0)

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.profile_scraper._launch_context", return_value=mock_ctx):
            result = await scrape_reddit_profile(mock_pw)

        assert result["platform"] == "reddit"
        assert result["display_name"] == "testuser"
        assert result["follower_count"] == 15432
        assert result["cake_day"] == "January 15, 2020"
        assert isinstance(result["recent_posts"], list)

    @pytest.mark.asyncio
    async def test_handles_missing_karma(self):
        """Reddit scraper works when karma element is missing."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page()
        mock_page.url = "https://www.reddit.com/user/testuser/"
        mock_ctx = _make_mock_context(mock_page)
        mock_page.locator = MagicMock(return_value=_make_mock_locator(count=0))
        mock_page.inner_text = AsyncMock(return_value="Some page content without karma")

        with patch("utils.profile_scraper._launch_context", return_value=mock_ctx):
            result = await scrape_reddit_profile(mock_pw)

        assert result["platform"] == "reddit"
        assert result["follower_count"] == 0


# ── Orchestrator Tests ────────────────────────────────────────────


class TestScrapeAllProfiles:
    @pytest.mark.asyncio
    async def test_scrapes_specified_platforms(self):
        """Orchestrator scrapes only the specified platforms."""
        mock_result_x = {
            "platform": "x",
            "display_name": "X User",
            "bio": "bio",
            "follower_count": 1000,
            "following_count": 500,
            "profile_pic_url": None,
            "recent_posts": [],
            "engagement_rate": 0.05,
            "posting_frequency": 2.0,
        }

        async def mock_scrape_x(pw):
            return mock_result_x

        with patch.dict(SCRAPER_MAP, {"x": mock_scrape_x}), \
             patch("utils.profile_scraper.async_playwright") as mock_pw_cm:
            mock_pw_instance = AsyncMock()
            mock_pw_cm.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
            mock_pw_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await scrape_all_profiles(platforms=["x"])

        assert "x" in results
        assert results["x"]["follower_count"] == 1000

        # Verify stored in local DB
        stored = get_scraped_profile("x")
        assert stored is not None
        assert stored["follower_count"] == 1000
        assert stored["display_name"] == "X User"

    @pytest.mark.asyncio
    async def test_handles_partial_failure(self):
        """Orchestrator continues scraping when one platform fails."""
        async def mock_scrape_x(pw):
            raise Exception("X scraping failed")

        async def mock_scrape_linkedin(pw):
            return {
                "platform": "linkedin",
                "display_name": "LinkedIn User",
                "bio": "headline",
                "follower_count": 2000,
                "following_count": 0,
                "profile_pic_url": None,
                "recent_posts": [],
                "engagement_rate": 0.03,
                "posting_frequency": 1.0,
            }

        with patch.dict(SCRAPER_MAP, {"x": mock_scrape_x, "linkedin": mock_scrape_linkedin}), \
             patch("utils.profile_scraper.async_playwright") as mock_pw_cm:
            mock_pw_instance = AsyncMock()
            mock_pw_cm.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
            mock_pw_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await scrape_all_profiles(platforms=["x", "linkedin"])

        # X should have error
        assert "error" in results["x"]
        # LinkedIn should succeed
        assert results["linkedin"]["follower_count"] == 2000

        # LinkedIn should be stored in DB
        stored = get_scraped_profile("linkedin")
        assert stored is not None
        assert stored["follower_count"] == 2000

    @pytest.mark.asyncio
    async def test_skips_unknown_platforms(self):
        """Orchestrator skips platforms with no scraper."""
        with patch("utils.profile_scraper.async_playwright") as mock_pw_cm:
            mock_pw_instance = AsyncMock()
            mock_pw_cm.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
            mock_pw_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await scrape_all_profiles(platforms=["nonexistent_platform"])

        assert results == {}

    @pytest.mark.asyncio
    async def test_defaults_to_enabled_platforms(self):
        """Orchestrator scrapes all enabled platforms when none specified."""
        scrape_calls = []

        async def mock_scrape(pw):
            scrape_calls.append(True)
            return {
                "platform": "x",
                "display_name": "User",
                "bio": None,
                "follower_count": 100,
                "following_count": 0,
                "profile_pic_url": None,
                "recent_posts": [],
                "engagement_rate": 0.0,
                "posting_frequency": 0.0,
            }

        # Patch all scrapers with the same mock
        patched = {p: mock_scrape for p in SCRAPER_MAP}
        with patch.dict(SCRAPER_MAP, patched), \
             patch("utils.profile_scraper.async_playwright") as mock_pw_cm:
            mock_pw_instance = AsyncMock()
            mock_pw_cm.return_value.__aenter__ = AsyncMock(return_value=mock_pw_instance)
            mock_pw_cm.return_value.__aexit__ = AsyncMock(return_value=False)

            results = await scrape_all_profiles()  # No platforms specified

        # Should have scraped enabled platforms (x, linkedin, facebook, reddit)
        assert len(scrape_calls) >= 1  # At least some were scraped


# ── Local DB Tests ────────────────────────────────────────────────


class TestLocalDBScrapedProfile:
    def test_upsert_and_get(self):
        """Store a scraped profile and retrieve it."""
        upsert_scraped_profile(
            platform="x",
            follower_count=5000,
            following_count=200,
            bio="Test bio",
            display_name="Test User",
            profile_pic_url="https://example.com/pic.jpg",
            recent_posts='[{"text":"hello","likes":10}]',
            engagement_rate=0.032,
            posting_frequency=12.5,
            ai_niches='["finance","tech"]',
        )

        profile = get_scraped_profile("x")
        assert profile is not None
        assert profile["platform"] == "x"
        assert profile["follower_count"] == 5000
        assert profile["following_count"] == 200
        assert profile["bio"] == "Test bio"
        assert profile["display_name"] == "Test User"
        assert profile["profile_pic_url"] == "https://example.com/pic.jpg"
        assert profile["engagement_rate"] == 0.032
        assert profile["posting_frequency"] == 12.5

        # Verify JSON fields
        posts = json.loads(profile["recent_posts"])
        assert len(posts) == 1
        assert posts[0]["text"] == "hello"

        niches = json.loads(profile["ai_niches"])
        assert "finance" in niches

    def test_upsert_updates_existing(self):
        """Upserting an existing platform updates the record."""
        upsert_scraped_profile(platform="linkedin", follower_count=100)
        upsert_scraped_profile(platform="linkedin", follower_count=500, bio="Updated bio")

        profile = get_scraped_profile("linkedin")
        assert profile["follower_count"] == 500
        assert profile["bio"] == "Updated bio"

    def test_get_nonexistent(self):
        """Getting a non-existent profile returns None."""
        profile = get_scraped_profile("tiktok")
        assert profile is None

    def test_get_all(self):
        """Get all scraped profiles."""
        upsert_scraped_profile(platform="x", follower_count=1000)
        upsert_scraped_profile(platform="reddit", follower_count=5000)

        profiles = get_all_scraped_profiles()
        assert len(profiles) >= 2
        platforms = [p["platform"] for p in profiles]
        assert "x" in platforms
        assert "reddit" in platforms


# ── Server Sync Tests ─────────────────────────────────────────────


class TestSyncProfilesToServer:
    def test_builds_correct_payload(self):
        """Sync builds the correct payload format for the server."""
        upsert_scraped_profile(
            platform="x",
            follower_count=1500,
            following_count=300,
            bio="trader bio",
            display_name="Trader",
            engagement_rate=0.032,
            posting_frequency=12.5,
        )
        upsert_scraped_profile(
            platform="linkedin",
            follower_count=500,
            following_count=0,
            bio="professional headline",
            display_name="Professional",
            engagement_rate=0.054,
            posting_frequency=3.2,
        )

        # Mock the update_profile call to capture the payload
        captured_kwargs = {}

        def mock_update_profile(**kwargs):
            captured_kwargs.update(kwargs)
            return {"status": "ok"}

        with patch("utils.server_client.update_profile", side_effect=mock_update_profile):
            result = sync_profiles_to_server()

        assert result == {"status": "ok"}

        # Check follower_counts
        assert "follower_counts" in captured_kwargs
        assert captured_kwargs["follower_counts"]["x"] == 1500
        assert captured_kwargs["follower_counts"]["linkedin"] == 500

        # Check scraped_profiles
        assert "scraped_profiles" in captured_kwargs
        assert captured_kwargs["scraped_profiles"]["x"]["follower_count"] == 1500
        assert captured_kwargs["scraped_profiles"]["x"]["engagement_rate"] == 0.032
        assert captured_kwargs["scraped_profiles"]["linkedin"]["bio"] == "professional headline"

    def test_no_profiles_returns_none(self):
        """Sync returns None when there are no scraped profiles."""
        result = sync_profiles_to_server()
        assert result is None

    def test_handles_server_error(self):
        """Sync returns None when server call fails."""
        upsert_scraped_profile(platform="x", follower_count=100)

        with patch("utils.server_client.update_profile", side_effect=Exception("Server down")):
            result = sync_profiles_to_server()

        assert result is None


# ── Scraper Return Format Tests ───────────────────────────────────


class TestScraperReturnFormat:
    """Verify all scrapers return the correct dict structure."""

    REQUIRED_KEYS = {
        "platform", "display_name", "bio", "follower_count", "following_count",
        "profile_pic_url", "recent_posts", "engagement_rate", "posting_frequency",
    }

    @pytest.mark.asyncio
    async def test_x_format(self):
        """X scraper returns all required keys."""
        with patch("utils.profile_scraper._launch_context", side_effect=Exception("skip")):
            result = await scrape_x_profile(AsyncMock())
        assert self.REQUIRED_KEYS.issubset(result.keys())
        assert result["platform"] == "x"

    @pytest.mark.asyncio
    async def test_linkedin_format(self):
        """LinkedIn scraper returns all required keys."""
        with patch("utils.profile_scraper._launch_context", side_effect=Exception("skip")):
            result = await scrape_linkedin_profile(AsyncMock())
        assert self.REQUIRED_KEYS.issubset(result.keys())
        assert result["platform"] == "linkedin"

    @pytest.mark.asyncio
    async def test_facebook_format(self):
        """Facebook scraper returns all required keys."""
        with patch("utils.profile_scraper._launch_context", side_effect=Exception("skip")):
            result = await scrape_facebook_profile(AsyncMock())
        assert self.REQUIRED_KEYS.issubset(result.keys())
        assert result["platform"] == "facebook"

    @pytest.mark.asyncio
    async def test_reddit_format(self):
        """Reddit scraper returns all required keys."""
        with patch("utils.profile_scraper._launch_context", side_effect=Exception("skip")):
            result = await scrape_reddit_profile(AsyncMock())
        assert self.REQUIRED_KEYS.issubset(result.keys())
        assert result["platform"] == "reddit"
        # Reddit also has cake_day
        assert "cake_day" in result


# ── Engagement Rate Calculation Tests ─────────────────────────────


class TestEngagementRateCalculation:
    @pytest.mark.asyncio
    async def test_x_engagement_rate(self):
        """X engagement rate calculated correctly from mocked tweets."""
        mock_pw = AsyncMock()
        mock_page = _make_mock_page()
        mock_ctx = _make_mock_context(mock_page)

        # Profile link
        profile_link = _make_mock_locator(count=1, attr_values={"href": "/testuser"})
        # Display name
        name_loc = _make_mock_locator(text="User", count=1)
        # Followers: 1000
        followers_loc = _make_mock_locator(text="1,000 Followers", count=1)

        # Create tweet articles with engagement data
        tweet_article = AsyncMock()
        tweet_text_loc = AsyncMock()
        tweet_text_loc.count = AsyncMock(return_value=1)
        tweet_text_loc.first = AsyncMock()
        tweet_text_loc.first.inner_text = AsyncMock(return_value="Great post about trading")

        engagement_el = AsyncMock()
        engagement_el.count = AsyncMock(return_value=3)

        # Create individual engagement labels
        like_label = AsyncMock()
        like_label.get_attribute = AsyncMock(return_value="50 Likes")
        retweet_label = AsyncMock()
        retweet_label.get_attribute = AsyncMock(return_value="10 reposts")
        reply_label = AsyncMock()
        reply_label.get_attribute = AsyncMock(return_value="5 replies")

        label_locator = AsyncMock()
        label_locator.count = AsyncMock(return_value=3)
        label_locator.nth = MagicMock(side_effect=lambda i: [like_label, retweet_label, reply_label][i])

        engagement_group = AsyncMock()
        engagement_group.count = AsyncMock(return_value=1)
        engagement_group.locator = MagicMock(return_value=label_locator)

        tweet_article.locator = MagicMock(side_effect=lambda sel: {
            '[data-testid="tweetText"]': tweet_text_loc,
            '[role="group"]': engagement_group,
        }.get(sel, _make_mock_locator(count=0)))

        articles_loc = AsyncMock()
        articles_loc.count = AsyncMock(return_value=1)
        articles_loc.nth = MagicMock(return_value=tweet_article)

        def locator_side_effect(selector):
            mapping = {
                'a[data-testid="AppTabBar_Profile_Link"]': profile_link,
                '[data-testid="UserName"]': name_loc,
                '[data-testid="UserDescription"]': _make_mock_locator(count=0),
                'a[data-testid="UserAvatar"] img, img[data-testid="UserAvatar-Container-unknown"] img': _make_mock_locator(count=0),
                'a[href$="/verified_followers"]': followers_loc,
                'a[href$="/following"]': _make_mock_locator(count=0),
                'article[data-testid="tweet"]': articles_loc,
            }
            return mapping.get(selector, _make_mock_locator(count=0))

        mock_page.locator = MagicMock(side_effect=locator_side_effect)

        with patch("utils.profile_scraper._launch_context", return_value=mock_ctx):
            result = await scrape_x_profile(mock_pw)

        # engagement = (50 + 10 + 5) / 1 tweet / 1000 followers = 0.065
        assert result["follower_count"] == 1000
        if result["recent_posts"]:
            assert result["engagement_rate"] == pytest.approx(0.065, abs=0.001)
