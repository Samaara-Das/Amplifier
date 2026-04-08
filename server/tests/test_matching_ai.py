"""Test AI matching scoring for Task #12.

Creates two test users with mock scraped profiles (finance + cooking),
creates a trading campaign, and verifies scoring behavior.

Run: cd server && python -m pytest tests/test_matching_ai.py -v -s
"""
import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

# ---------- Test data ----------

FINANCE_USER_PROFILE = {
    "x": {
        "display_name": "TraderMike",
        "bio": "Day trader | SPY options | Technical analysis nerd | Not financial advice",
        "follower_count": 450,
        "following_count": 200,
        "posting_frequency": 1.5,
        "recent_posts": [
            {
                "text": "SPY broke through resistance at 520 today. RSI divergence on the 15min confirmed the move. Took profits at 523.",
                "likes": 12, "comments": 3, "views": 890,
                "posted_at": "2h ago"
            },
            {
                "text": "My RSI divergence indicator caught the AAPL reversal before the big move. Backtested it on 500 trades — 68% win rate.",
                "likes": 25, "comments": 8, "views": 2100,
                "posted_at": "1d ago"
            },
            {
                "text": "Stop using moving averages as entry signals. They lag. Use them as trend filters and find entries with structure breaks.",
                "likes": 45, "comments": 15, "views": 5200,
                "posted_at": "3d ago"
            },
            {
                "text": "TSLA earnings play: bought the 250C weeklies before close. Let's see how this plays out tomorrow.",
                "likes": 8, "comments": 4, "views": 650,
                "posted_at": "5d ago"
            },
        ],
        "ai_detected_niches": ["day trading", "technical analysis", "options trading"],
        "profile_data": {
            "content_quality": "high",
            "audience_demographics_estimate": {"interests": ["trading", "finance", "investing"]},
        },
    },
    "reddit": {
        "display_name": "TraderMike",
        "bio": "Options trader sharing what I learn",
        "follower_count": 30,
        "following_count": 0,
        "posting_frequency": 0.3,
        "recent_posts": [
            {
                "title": "My honest review of the Smart Money Indicator after 3 months",
                "text": "I've been using this indicator on SPY and QQQ...",
                "score": 21, "comments": 7, "views": 330,
                "subreddit": "r/Daytrading", "posted_at": "10d ago"
            },
            {
                "title": "Why RSI divergence fails in trending markets — and what to use instead",
                "text": "Most tutorials teach RSI wrong...",
                "score": 45, "comments": 12, "views": 1200,
                "subreddit": "r/SwingTrading", "posted_at": "20d ago"
            },
        ],
        "ai_detected_niches": ["trading", "technical analysis"],
        "profile_data": {"karma": 223, "reddit_age": "6y"},
    },
}

COOKING_USER_PROFILE = {
    "x": {
        "display_name": "ChefLinda",
        "bio": "Home cook | Recipe creator | Food photography | DM for collabs",
        "follower_count": 1200,
        "following_count": 800,
        "posting_frequency": 2.0,
        "recent_posts": [
            {
                "text": "Made the most amazing sourdough bread today! 72-hour cold ferment makes all the difference.",
                "likes": 85, "comments": 20, "views": 3500,
                "posted_at": "4h ago"
            },
            {
                "text": "Quick weeknight pasta: garlic, cherry tomatoes, basil, parmesan. 15 minutes. Better than takeout every time.",
                "likes": 120, "comments": 35, "views": 8900,
                "posted_at": "1d ago"
            },
            {
                "text": "My kitchen gadget tier list: S-tier is the cast iron skillet. Nothing beats it.",
                "likes": 200, "comments": 60, "views": 15000,
                "posted_at": "3d ago"
            },
        ],
        "ai_detected_niches": ["cooking", "food photography", "recipes"],
        "profile_data": {
            "content_quality": "high",
            "audience_demographics_estimate": {"interests": ["food", "cooking", "lifestyle"]},
        },
    },
    "facebook": {
        "display_name": "Linda's Kitchen",
        "bio": "Sharing easy recipes for busy families",
        "follower_count": 350,
        "following_count": 150,
        "posting_frequency": 0.5,
        "recent_posts": [
            {
                "text": "Sunday meal prep ideas that'll save you 5 hours during the week!",
                "likes": 30, "comments": 8, "shares": 5,
                "posted_at": "2d ago"
            },
        ],
        "ai_detected_niches": ["cooking", "meal prep"],
        "profile_data": {},
    },
}

# A user who posts finance on X but food on Facebook
CROSS_PLATFORM_USER_PROFILE = {
    "x": {
        "display_name": "Alex M",
        "bio": "Swing trader | Chart analysis | Building indicators on TradingView",
        "follower_count": 300,
        "following_count": 180,
        "posting_frequency": 1.0,
        "recent_posts": [
            {
                "text": "QQQ looking bearish on the weekly. Head and shoulders pattern forming. Watch 440 support.",
                "likes": 8, "comments": 2, "views": 400,
                "posted_at": "1d ago"
            },
        ],
        "ai_detected_niches": ["swing trading", "technical analysis"],
        "profile_data": {"content_quality": "medium"},
    },
    "facebook": {
        "display_name": "Alex's Food Adventures",
        "bio": "Trying every restaurant in NYC",
        "follower_count": 500,
        "following_count": 400,
        "posting_frequency": 1.5,
        "recent_posts": [
            {
                "text": "Best ramen I've had outside of Japan. This spot in Brooklyn is unreal.",
                "likes": 45, "comments": 12, "shares": 3,
                "posted_at": "2d ago"
            },
        ],
        "ai_detected_niches": ["food", "restaurants", "travel"],
        "profile_data": {},
    },
}


# ---------- Mock campaign + user factories ----------

class MockCampaign:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 100)
        self.title = kwargs.get("title", "Trading Indicator Campaign")
        self.brief = kwargs.get("brief", (
            "Promote our Smart Money Indicator for TradingView. "
            "It detects institutional order flow in real-time on SPY, QQQ, AAPL, and TSLA. "
            "Backtested with a 72% win rate over 2 years. "
            "Target audience: retail traders who use TradingView for technical analysis."
        ))
        self.content_guidance = kwargs.get("content_guidance",
            "Share your honest experience. Show a chart screenshot if possible. "
            "Mention the indicator name and that it's on TradingView."
        )
        self.targeting = kwargs.get("targeting", {
            "niche_tags": ["trading", "finance", "technical analysis"],
            "required_platforms": ["x"],
            "target_regions": [],
            "min_followers": {},
            "min_engagement": 0,
        })
        self.budget_remaining = kwargs.get("budget_remaining", 500.0)
        self.campaign_goal = kwargs.get("campaign_goal", "leads")
        self.tone = kwargs.get("tone", "conversational")
        self.status = "active"
        self.accepted_count = 0


class MockUser:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.email = kwargs.get("email", "test@test.com")
        self.platforms = kwargs.get("platforms", {"x": True})
        self.follower_counts = kwargs.get("follower_counts", {"x": 450})
        self.niche_tags = kwargs.get("niche_tags", [])
        self.ai_detected_niches = kwargs.get("ai_detected_niches", [])
        self.audience_region = kwargs.get("audience_region", "us")
        self.trust_score = kwargs.get("trust_score", 50)
        self.mode = kwargs.get("mode", "semi_auto")
        self.tier = kwargs.get("tier", "seedling")
        self.scraped_profiles = kwargs.get("scraped_profiles", {})


# ---------- Tests ----------

from app.services.matching import (
    _build_scoring_prompt,
    _fallback_niche_score,
    _parse_score,
    _passes_hard_filters,
    ai_score_relevance,
    cache_score,
    get_cached_score,
    invalidate_cache,
    _score_cache,
)


class TestFallbackNicheScore:
    """Test the fallback niche-overlap scoring (spec: 25 per overlap, base 50, min 10)."""

    def test_no_targeting_returns_base_50(self):
        campaign = MockCampaign(targeting={"niche_tags": []})
        user = MockUser(niche_tags=["finance"], ai_detected_niches=[])
        score = _fallback_niche_score(campaign, user)
        assert score == 50.0

    def test_one_overlap_returns_25(self):
        campaign = MockCampaign(targeting={"niche_tags": ["finance", "tech"]})
        user = MockUser(niche_tags=["finance"], ai_detected_niches=[])
        score = _fallback_niche_score(campaign, user)
        assert score == 25.0

    def test_two_overlaps_returns_50(self):
        campaign = MockCampaign(targeting={"niche_tags": ["finance", "tech"]})
        user = MockUser(niche_tags=["finance", "tech"], ai_detected_niches=[])
        score = _fallback_niche_score(campaign, user)
        assert score == 50.0

    def test_no_overlap_returns_min_10(self):
        campaign = MockCampaign(targeting={"niche_tags": ["finance"]})
        user = MockUser(niche_tags=["cooking"], ai_detected_niches=[])
        score = _fallback_niche_score(campaign, user)
        assert score == 10.0

    def test_ai_detected_niches_used_if_available(self):
        campaign = MockCampaign(targeting={"niche_tags": ["trading"]})
        user = MockUser(niche_tags=["general"], ai_detected_niches=["trading", "finance"])
        score = _fallback_niche_score(campaign, user)
        assert score == 25.0  # 1 overlap ("trading") * 25


class TestPromptContent:
    """Test that the scoring prompt includes all required elements from spec."""

    def test_prompt_includes_weighted_criteria(self):
        campaign = MockCampaign()
        user = MockUser(
            niche_tags=["trading"],
            scraped_profiles=FINANCE_USER_PROFILE,
        )
        prompt = _build_scoring_prompt(campaign, user)

        assert "TOPIC RELEVANCE (40%" in prompt
        assert "AUDIENCE FIT (25%" in prompt
        assert "AUTHENTICITY FIT (20%" in prompt
        assert "CONTENT QUALITY (15%" in prompt

    def test_prompt_includes_brand_safety(self):
        campaign = MockCampaign()
        user = MockUser(scraped_profiles=FINANCE_USER_PROFILE)
        prompt = _build_scoring_prompt(campaign, user)
        assert "BRAND SAFETY" in prompt
        assert "controversial" in prompt.lower()

    def test_prompt_includes_self_selected_niches_section(self):
        campaign = MockCampaign()
        user = MockUser(niche_tags=["lifestyle", "food"], scraped_profiles={})
        prompt = _build_scoring_prompt(campaign, user)
        assert "SELF-SELECTED NICHES" in prompt
        assert "lifestyle" in prompt
        assert "food" in prompt
        assert "expand into new topics" in prompt

    def test_prompt_includes_niche_depth(self):
        campaign = MockCampaign()
        user = MockUser(scraped_profiles=FINANCE_USER_PROFILE)
        prompt = _build_scoring_prompt(campaign, user)
        assert "NICHE DEPTH" in prompt or "specificity" in prompt.lower()

    def test_prompt_includes_cross_platform_instruction(self):
        campaign = MockCampaign(targeting={"niche_tags": ["trading"], "required_platforms": ["x"]})
        user = MockUser(
            platforms={"x": True, "facebook": True},
            scraped_profiles=CROSS_PLATFORM_USER_PROFILE,
        )
        prompt = _build_scoring_prompt(campaign, user)
        assert "do NOT average across all platforms" in prompt or "THOSE platforms" in prompt

    def test_prompt_includes_scoring_scale_80_100(self):
        campaign = MockCampaign()
        user = MockUser(scraped_profiles={})
        prompt = _build_scoring_prompt(campaign, user)
        assert "80-100" in prompt
        assert "Strong fit" in prompt

    def test_prompt_includes_creator_posts(self):
        campaign = MockCampaign()
        user = MockUser(scraped_profiles=FINANCE_USER_PROFILE)
        prompt = _build_scoring_prompt(campaign, user)
        assert "SPY broke through resistance" in prompt
        assert "RSI divergence indicator" in prompt


class TestHardFilters:
    """Verify hard filters work as expected (unchanged from v1 but good to confirm)."""

    def test_user_with_required_platform_passes(self):
        campaign = MockCampaign(targeting={"required_platforms": ["x"]})
        user = MockUser(platforms={"x": True})
        assert _passes_hard_filters(campaign, user) is True

    def test_user_without_required_platform_fails(self):
        campaign = MockCampaign(targeting={"required_platforms": ["linkedin"]})
        user = MockUser(platforms={"x": True})
        assert _passes_hard_filters(campaign, user) is False

    def test_no_platform_requirement_passes(self):
        campaign = MockCampaign(targeting={})
        user = MockUser(platforms={"x": True})
        assert _passes_hard_filters(campaign, user) is True

    def test_min_followers_met(self):
        campaign = MockCampaign(targeting={"min_followers": {"x": 100}})
        user = MockUser(platforms={"x": True}, follower_counts={"x": 450})
        assert _passes_hard_filters(campaign, user) is True

    def test_min_followers_not_met(self):
        campaign = MockCampaign(targeting={"min_followers": {"x": 1000}})
        user = MockUser(platforms={"x": True}, follower_counts={"x": 450})
        assert _passes_hard_filters(campaign, user) is False


class TestScoreCache:
    """Test caching behavior."""

    def setup_method(self):
        _score_cache.clear()

    def test_cache_hit(self):
        cache_score(1, 1, 85.0)
        assert get_cached_score(1, 1) == 85.0

    def test_cache_miss(self):
        assert get_cached_score(999, 999) is None

    def test_invalidate_by_campaign(self):
        cache_score(1, 1, 85.0)
        cache_score(1, 2, 60.0)
        cache_score(2, 1, 70.0)
        invalidate_cache(campaign_id=1)
        assert get_cached_score(1, 1) is None
        assert get_cached_score(1, 2) is None
        assert get_cached_score(2, 1) == 70.0

    def test_invalidate_by_user(self):
        cache_score(1, 1, 85.0)
        cache_score(2, 1, 70.0)
        cache_score(1, 2, 60.0)
        invalidate_cache(user_id=1)
        assert get_cached_score(1, 1) is None
        assert get_cached_score(2, 1) is None
        assert get_cached_score(1, 2) == 60.0


class TestParseScore:
    """Test score parsing from AI response."""

    def test_plain_number(self):
        assert _parse_score("85") == 85.0

    def test_score_prefix(self):
        assert _parse_score("Score: 78") == 78.0

    def test_out_of_100(self):
        assert _parse_score("78/100") == 78.0

    def test_clamp_high(self):
        assert _parse_score("150") == 100.0

    def test_clamp_low(self):
        assert _parse_score("-10") == 0.0

    def test_decimal(self):
        assert _parse_score("85.5") == 85.5


class TestMinimumScoreThreshold:
    """Verify that the min score = 40 threshold is enforced."""

    def test_fallback_no_overlap_returns_10_below_threshold(self):
        """A user with zero niche overlap gets score 10 from fallback — below 40 threshold."""
        campaign = MockCampaign(targeting={"niche_tags": ["finance"]})
        user = MockUser(niche_tags=["cooking"], ai_detected_niches=[])
        score = _fallback_niche_score(campaign, user)
        assert score == 10.0
        assert score < 40, "Score should be below invitation threshold"

    def test_fallback_one_overlap_returns_25_below_threshold(self):
        """One niche overlap = 25, still below 40 threshold."""
        campaign = MockCampaign(targeting={"niche_tags": ["finance", "tech", "crypto"]})
        user = MockUser(niche_tags=["finance"], ai_detected_niches=[])
        score = _fallback_niche_score(campaign, user)
        assert score == 25.0
        assert score < 40

    def test_fallback_two_overlaps_returns_50_above_threshold(self):
        """Two niche overlaps = 50, above 40 threshold — gets invited."""
        campaign = MockCampaign(targeting={"niche_tags": ["finance", "tech"]})
        user = MockUser(niche_tags=["finance", "tech"], ai_detected_niches=[])
        score = _fallback_niche_score(campaign, user)
        assert score == 50.0
        assert score >= 40
