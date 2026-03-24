"""Tests for AI-powered matching algorithm (Task 10).

Covers:
- AI relevance scoring (mocked Gemini)
- Score caching (hit, miss, expiry, invalidation)
- Combined scoring formula
- Matching uses AI scores
- Fallback to niche-overlap when AI fails
- Hard filters still enforced
- Invitation flow preserved
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ── Path setup ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _server_env(monkeypatch):
    """Point server to an in-memory SQLite DB for testing."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    from app.core import config
    config.get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_session():
    """Create tables and yield an async DB session."""
    from app.core.database import engine, async_session, Base
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def seed_data(db_session):
    """Seed a company, campaign, and user with rich profile data."""
    from app.models.company import Company
    from app.models.campaign import Campaign
    from app.models.user import User
    from app.core.security import hash_password

    company = Company(
        name="TestCo",
        email="company@test.com",
        password_hash=hash_password("pass123"),
        balance=5000.0,
    )
    db_session.add(company)
    await db_session.flush()

    campaign = Campaign(
        company_id=company.id,
        title="AI Trading Indicator Launch",
        brief="Promote our new AI-powered trading indicator for retail traders.",
        assets={"links": ["https://example.com"]},
        budget_total=500.0,
        budget_remaining=500.0,
        payout_rules={
            "rate_per_1k_impressions": 0.50,
            "rate_per_like": 0.01,
            "rate_per_repost": 0.05,
            "rate_per_click": 0.10,
        },
        targeting={
            "min_followers": {},
            "niche_tags": ["finance", "trading"],
            "required_platforms": [],
            "target_regions": [],
        },
        content_guidance="Target beginner traders. Emphasize ease of use.",
        penalty_rules={},
        status="active",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(campaign)
    await db_session.flush()

    user = User(
        email="creator@test.com",
        password_hash=hash_password("pass123"),
        platforms={"x": {"connected": True}, "linkedin": {"connected": True}},
        follower_counts={"x": 5000, "linkedin": 2000},
        niche_tags=["finance", "crypto"],
        ai_detected_niches=["finance", "crypto", "trading education"],
        audience_region="us",
        trust_score=75,
        mode="semi_auto",
        scraped_profiles={
            "x": {
                "bio": "Helping everyday people understand markets. Building tools, sharing backtests.",
                "follower_count": 5000,
                "avg_engagement_rate": 0.035,
                "recent_posts": [
                    "Here's what happens when you buy the dip without a plan...",
                    "I backtested RSI divergence on SPY over 10 years. Results surprised me.",
                ],
            },
            "linkedin": {
                "bio": "FinTech builder | Market research & automation",
                "follower_count": 2000,
                "avg_engagement_rate": 0.02,
                "recent_posts": [
                    "Why most retail traders lose money on fake breakouts",
                ],
            },
        },
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    return {
        "company_id": company.id,
        "campaign_id": campaign.id,
        "user_id": user.id,
    }


@pytest_asyncio.fixture
async def get_user(db_session, seed_data):
    """Fetch the seeded User ORM object."""
    from app.models.user import User
    from sqlalchemy import select

    result = await db_session.execute(
        select(User).where(User.id == seed_data["user_id"])
    )
    return result.scalar_one()


@pytest_asyncio.fixture
async def get_campaign(db_session, seed_data):
    """Fetch the seeded Campaign ORM object."""
    from app.models.campaign import Campaign
    from sqlalchemy import select

    result = await db_session.execute(
        select(Campaign).where(Campaign.id == seed_data["campaign_id"])
    )
    return result.scalar_one()


# ===================================================================
# AI Relevance Scoring
# ===================================================================

class TestAIRelevanceScoring:

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        """Clear the score cache before each test in this class."""
        from app.services.matching import _score_cache
        _score_cache.clear()

    @pytest.mark.asyncio
    async def test_returns_score_0_to_100(self, get_campaign, get_user):
        """AI scoring should return a float between 0 and 100."""
        from app.services.matching import ai_score_relevance

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "85"
            score = await ai_score_relevance(get_campaign, get_user)
            assert 0 <= score <= 100
            assert score == 85.0

    @pytest.mark.asyncio
    async def test_parses_integer_response(self, get_campaign, get_user):
        """AI response is just a number string — should parse correctly."""
        from app.services.matching import ai_score_relevance

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "72"
            score = await ai_score_relevance(get_campaign, get_user)
            assert score == 72.0

    @pytest.mark.asyncio
    async def test_parses_float_response(self, get_campaign, get_user):
        """AI may return a float like '85.5' — should handle it."""
        from app.services.matching import ai_score_relevance

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "85.5"
            score = await ai_score_relevance(get_campaign, get_user)
            assert score == 85.5

    @pytest.mark.asyncio
    async def test_clamps_score_above_100(self, get_campaign, get_user):
        """If AI returns > 100, clamp to 100."""
        from app.services.matching import ai_score_relevance

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "150"
            score = await ai_score_relevance(get_campaign, get_user)
            assert score == 100.0

    @pytest.mark.asyncio
    async def test_clamps_score_below_0(self, get_campaign, get_user):
        """If AI returns < 0, clamp to 0."""
        from app.services.matching import ai_score_relevance

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "-10"
            score = await ai_score_relevance(get_campaign, get_user)
            assert score == 0.0

    @pytest.mark.asyncio
    async def test_handles_noisy_ai_response(self, get_campaign, get_user):
        """AI might return 'Score: 78' or '78/100' — parse the number."""
        from app.services.matching import ai_score_relevance

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "Score: 78"
            score = await ai_score_relevance(get_campaign, get_user)
            assert score == 78.0

    @pytest.mark.asyncio
    async def test_empty_user_profile_still_works(self, get_campaign, db_session):
        """User with no scraped data or niches should still get a score."""
        from app.models.user import User
        from app.core.security import hash_password
        from app.services.matching import ai_score_relevance

        empty_user = User(
            email="empty@test.com",
            password_hash=hash_password("pass"),
            platforms={"x": {"connected": True}},
            follower_counts={"x": 100},
            niche_tags=[],
            ai_detected_niches=[],
            audience_region="us",
            trust_score=50,
            mode="semi_auto",
            scraped_profiles={},
        )
        db_session.add(empty_user)
        await db_session.flush()

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "30"
            score = await ai_score_relevance(get_campaign, empty_user)
            assert score == 30.0
            # Verify the prompt was still built and sent
            mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_ai_failure(self, get_campaign, get_user):
        """When AI call fails, should return -1 to signal fallback."""
        from app.services.matching import ai_score_relevance

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.side_effect = RuntimeError("API down")
            score = await ai_score_relevance(get_campaign, get_user)
            assert score == -1.0  # sentinel for "use fallback"


# ===================================================================
# Score Caching
# ===================================================================

class TestScoreCaching:

    def test_cache_stores_and_retrieves(self):
        """Cached score should be retrievable."""
        from app.services.matching import cache_score, get_cached_score, _score_cache
        _score_cache.clear()

        cache_score(1, 10, 85.0)
        result = get_cached_score(1, 10)
        assert result == 85.0

    def test_cache_miss_returns_none(self):
        """Non-existent key should return None."""
        from app.services.matching import get_cached_score, _score_cache
        _score_cache.clear()

        result = get_cached_score(999, 999)
        assert result is None

    def test_cache_expiry(self):
        """Scores older than 24h should not be returned."""
        from app.services.matching import get_cached_score, _score_cache
        _score_cache.clear()

        stale_time = datetime.now(timezone.utc) - timedelta(hours=25)
        _score_cache[(1, 10)] = (85.0, stale_time)

        result = get_cached_score(1, 10)
        assert result is None

    def test_cache_not_expired_within_24h(self):
        """Scores within 24h should be returned."""
        from app.services.matching import get_cached_score, _score_cache
        _score_cache.clear()

        fresh_time = datetime.now(timezone.utc) - timedelta(hours=23)
        _score_cache[(1, 10)] = (90.0, fresh_time)

        result = get_cached_score(1, 10)
        assert result == 90.0

    def test_invalidate_by_campaign(self):
        """Invalidating a campaign clears all scores for that campaign."""
        from app.services.matching import (
            cache_score, get_cached_score, invalidate_cache, _score_cache,
        )
        _score_cache.clear()

        cache_score(1, 10, 85.0)
        cache_score(1, 20, 70.0)
        cache_score(2, 10, 60.0)

        invalidate_cache(campaign_id=1)

        assert get_cached_score(1, 10) is None
        assert get_cached_score(1, 20) is None
        assert get_cached_score(2, 10) == 60.0  # untouched

    def test_invalidate_by_user(self):
        """Invalidating a user clears all scores for that user."""
        from app.services.matching import (
            cache_score, get_cached_score, invalidate_cache, _score_cache,
        )
        _score_cache.clear()

        cache_score(1, 10, 85.0)
        cache_score(2, 10, 70.0)
        cache_score(1, 20, 60.0)

        invalidate_cache(user_id=10)

        assert get_cached_score(1, 10) is None
        assert get_cached_score(2, 10) is None
        assert get_cached_score(1, 20) == 60.0  # untouched

    def test_invalidate_both(self):
        """Invalidating both campaign_id and user_id clears matching entries."""
        from app.services.matching import (
            cache_score, get_cached_score, invalidate_cache, _score_cache,
        )
        _score_cache.clear()

        cache_score(1, 10, 85.0)
        cache_score(1, 20, 70.0)
        cache_score(2, 10, 60.0)
        cache_score(2, 20, 50.0)

        invalidate_cache(campaign_id=1, user_id=10)

        # Only (1, 10) should be cleared (matches both)
        assert get_cached_score(1, 10) is None
        assert get_cached_score(1, 20) == 70.0
        assert get_cached_score(2, 10) == 60.0
        assert get_cached_score(2, 20) == 50.0

    @pytest.mark.asyncio
    async def test_cache_hit_avoids_ai_call(self, get_campaign, get_user):
        """When score is cached, AI should not be called."""
        from app.services.matching import (
            ai_score_relevance, cache_score, _score_cache,
        )
        _score_cache.clear()
        cache_score(get_campaign.id, get_user.id, 88.0)

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            score = await ai_score_relevance(get_campaign, get_user)
            assert score == 88.0
            mock.assert_not_called()


# ===================================================================
# Combined Scoring Formula
# ===================================================================

class TestCombinedScoring:

    def test_formula_basic(self):
        """Test the combined scoring formula: ai*0.6 + trust*0.2 + engagement (capped at 20)."""
        from app.services.matching import calculate_combined_score

        # ai_score=80, trust_score=75, engagement_rate=0.035
        # expected: 80*0.6 + 75*0.2 + min(0.035*1000, 20) = 48 + 15 + 20 = 83.0
        score = calculate_combined_score(
            ai_score=80.0, trust_score=75, engagement_rate=0.035
        )
        assert score == pytest.approx(83.0, abs=0.1)

    def test_formula_low_engagement(self):
        """Low engagement rate should contribute less."""
        from app.services.matching import calculate_combined_score

        # ai_score=60, trust_score=50, engagement_rate=0.005
        # expected: 60*0.6 + 50*0.2 + min(5.0, 20) = 36 + 10 + 5 = 51.0
        score = calculate_combined_score(
            ai_score=60.0, trust_score=50, engagement_rate=0.005
        )
        assert score == pytest.approx(51.0, abs=0.1)

    def test_formula_engagement_capped_at_20(self):
        """Engagement bonus should cap at 20 even with high rates."""
        from app.services.matching import calculate_combined_score

        # ai_score=90, trust_score=100, engagement_rate=0.10
        # expected: 90*0.6 + 100*0.2 + min(100, 20) = 54 + 20 + 20 = 94.0
        score = calculate_combined_score(
            ai_score=90.0, trust_score=100, engagement_rate=0.10
        )
        assert score == pytest.approx(94.0, abs=0.1)

    def test_formula_zero_values(self):
        """Zero inputs should produce zero output."""
        from app.services.matching import calculate_combined_score

        score = calculate_combined_score(
            ai_score=0.0, trust_score=0, engagement_rate=0.0
        )
        assert score == pytest.approx(0.0, abs=0.1)

    def test_formula_max_values(self):
        """Maximum reasonable inputs."""
        from app.services.matching import calculate_combined_score

        # ai_score=100, trust_score=100, engagement_rate=1.0
        # expected: 100*0.6 + 100*0.2 + 20 = 60 + 20 + 20 = 100.0
        score = calculate_combined_score(
            ai_score=100.0, trust_score=100, engagement_rate=1.0
        )
        assert score == pytest.approx(100.0, abs=0.1)


# ===================================================================
# Matching Uses AI Scores
# ===================================================================

class TestMatchingWithAI:

    @pytest.mark.asyncio
    async def test_matching_calls_ai_scoring(self, db_session, seed_data):
        """get_matched_campaigns should use AI scoring for candidates."""
        from app.models.user import User
        from app.services.matching import get_matched_campaigns, _score_cache
        from sqlalchemy import select

        _score_cache.clear()

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "85"
            briefs = await get_matched_campaigns(user, db_session)

            # AI should have been called for this user-campaign pair
            mock.assert_called_once()
            # Should still produce invitations
            assert len(briefs) >= 1

    @pytest.mark.asyncio
    async def test_matching_uses_cached_scores(self, db_session, seed_data):
        """Matching should use cached AI scores instead of re-calling AI."""
        from app.models.user import User
        from app.services.matching import (
            get_matched_campaigns, cache_score, _score_cache,
        )
        from sqlalchemy import select

        _score_cache.clear()
        cache_score(seed_data["campaign_id"], seed_data["user_id"], 90.0)

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            briefs = await get_matched_campaigns(user, db_session)
            mock.assert_not_called()
            assert len(briefs) >= 1

    @pytest.mark.asyncio
    async def test_matching_falls_back_on_ai_failure(self, db_session, seed_data):
        """When AI fails, matching should fall back to niche-overlap scoring."""
        from app.models.user import User
        from app.services.matching import get_matched_campaigns, _score_cache
        from sqlalchemy import select

        _score_cache.clear()

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.side_effect = RuntimeError("Gemini down")
            briefs = await get_matched_campaigns(user, db_session)

            # Should still produce matches via fallback scoring
            assert len(briefs) >= 1

    @pytest.mark.asyncio
    async def test_matching_still_creates_invitations(self, db_session, seed_data):
        """AI matching should still create pending_invitation assignments."""
        from app.models.user import User
        from app.models.assignment import CampaignAssignment
        from app.services.matching import get_matched_campaigns, _score_cache
        from sqlalchemy import select

        _score_cache.clear()

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "80"
            await get_matched_campaigns(user, db_session)

        result = await db_session.execute(
            select(CampaignAssignment).where(
                CampaignAssignment.user_id == seed_data["user_id"],
                CampaignAssignment.campaign_id == seed_data["campaign_id"],
            )
        )
        assignment = result.scalar_one_or_none()
        assert assignment is not None
        assert assignment.status == "pending_invitation"
        assert assignment.expires_at is not None

    @pytest.mark.asyncio
    async def test_matching_increments_invitation_count_with_ai(
        self, db_session, seed_data
    ):
        """Invitation counter should still increment with AI scoring."""
        from app.models.user import User
        from app.models.campaign import Campaign
        from app.services.matching import get_matched_campaigns, _score_cache
        from sqlalchemy import select

        _score_cache.clear()

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "75"
            await get_matched_campaigns(user, db_session)

        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        assert campaign.invitation_count >= 1


# ===================================================================
# Hard Filters Still Work
# ===================================================================

class TestHardFiltersWithAI:

    @pytest.mark.asyncio
    async def test_required_platform_filter(self, db_session, seed_data):
        """User missing required platform should be filtered out."""
        from app.models.user import User
        from app.models.campaign import Campaign
        from app.services.matching import get_matched_campaigns, _score_cache
        from sqlalchemy import select

        _score_cache.clear()

        # Update campaign to require 'tiktok' (user doesn't have it)
        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        campaign.targeting = {
            **campaign.targeting,
            "required_platforms": ["tiktok"],
        }
        await db_session.flush()
        await db_session.commit()

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "90"
            briefs = await get_matched_campaigns(user, db_session)

            # AI should NOT be called because hard filter rejects first
            mock.assert_not_called()
            # No new invitations for mismatched campaigns
            new_briefs = [
                b for b in briefs
                if b.campaign_id == seed_data["campaign_id"]
            ]
            assert len(new_briefs) == 0

    @pytest.mark.asyncio
    async def test_follower_minimum_filter(self, db_session, seed_data):
        """User below follower minimum should be filtered out."""
        from app.models.user import User
        from app.models.campaign import Campaign
        from app.services.matching import get_matched_campaigns, _score_cache
        from sqlalchemy import select

        _score_cache.clear()

        # Require 100k followers on X
        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        campaign.targeting = {
            **campaign.targeting,
            "min_followers": {"x": 100000},
        }
        await db_session.flush()
        await db_session.commit()

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "95"
            briefs = await get_matched_campaigns(user, db_session)
            mock.assert_not_called()
            new_briefs = [
                b for b in briefs
                if b.campaign_id == seed_data["campaign_id"]
            ]
            assert len(new_briefs) == 0

    @pytest.mark.asyncio
    async def test_region_filter(self, db_session, seed_data):
        """User outside target region should be filtered out."""
        from app.models.user import User
        from app.models.campaign import Campaign
        from app.services.matching import get_matched_campaigns, _score_cache
        from sqlalchemy import select

        _score_cache.clear()

        # Target only UK
        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        campaign.targeting = {
            **campaign.targeting,
            "target_regions": ["uk"],
        }
        await db_session.flush()
        await db_session.commit()

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()  # audience_region = "us"

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "95"
            briefs = await get_matched_campaigns(user, db_session)
            mock.assert_not_called()
            new_briefs = [
                b for b in briefs
                if b.campaign_id == seed_data["campaign_id"]
            ]
            assert len(new_briefs) == 0

    @pytest.mark.asyncio
    async def test_zero_budget_filter(self, db_session, seed_data):
        """Campaign with zero budget should be filtered out."""
        from app.models.user import User
        from app.models.campaign import Campaign
        from app.services.matching import get_matched_campaigns, _score_cache
        from sqlalchemy import select

        _score_cache.clear()

        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        campaign.budget_remaining = 0
        await db_session.flush()
        await db_session.commit()

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "90"
            briefs = await get_matched_campaigns(user, db_session)
            mock.assert_not_called()
            new_briefs = [
                b for b in briefs
                if b.campaign_id == seed_data["campaign_id"]
            ]
            assert len(new_briefs) == 0

    @pytest.mark.asyncio
    async def test_already_invited_filter(self, db_session, seed_data):
        """User already invited to a campaign should not be re-invited."""
        from app.models.user import User
        from app.models.assignment import CampaignAssignment
        from app.services.matching import get_matched_campaigns, _score_cache
        from sqlalchemy import select

        _score_cache.clear()

        # Create existing assignment
        assignment = CampaignAssignment(
            campaign_id=seed_data["campaign_id"],
            user_id=seed_data["user_id"],
            status="pending_invitation",
            content_mode="ai_generated",
            payout_multiplier=1.0,
            invited_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=3),
        )
        db_session.add(assignment)
        await db_session.flush()
        await db_session.commit()

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        with patch("app.services.matching._call_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = "90"
            briefs = await get_matched_campaigns(user, db_session)
            # Should not call AI for already-invited campaigns
            mock.assert_not_called()


# ===================================================================
# User Average Engagement Rate Helper
# ===================================================================

class TestUserEngagementRate:

    def test_calculates_from_scraped_profiles(self):
        """Should average engagement rates across platforms."""
        from app.services.matching import _get_user_engagement_rate
        from unittest.mock import MagicMock

        user = MagicMock()
        user.scraped_profiles = {
            "x": {"avg_engagement_rate": 0.04},
            "linkedin": {"avg_engagement_rate": 0.02},
        }
        rate = _get_user_engagement_rate(user)
        assert rate == pytest.approx(0.03, abs=0.001)

    def test_empty_profiles_returns_zero(self):
        """No scraped data should return 0."""
        from app.services.matching import _get_user_engagement_rate
        from unittest.mock import MagicMock

        user = MagicMock()
        user.scraped_profiles = {}
        rate = _get_user_engagement_rate(user)
        assert rate == 0.0

    def test_none_profiles_returns_zero(self):
        """None scraped_profiles should return 0."""
        from app.services.matching import _get_user_engagement_rate
        from unittest.mock import MagicMock

        user = MagicMock()
        user.scraped_profiles = None
        rate = _get_user_engagement_rate(user)
        assert rate == 0.0
