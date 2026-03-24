"""Tests for the AI Campaign Creation Wizard (Task 9).

Covers:
- POST /api/company/campaigns/ai-wizard — AI generates campaign draft
- POST /api/company/campaigns/reach-estimate — pre-creation reach estimation
- GET /api/company/campaigns/{id}/reach-estimate — existing campaign reach estimation
- campaign_wizard.py service: URL scraping, AI generation, payout suggestion, reach estimation
- Gemini failure fallback to sensible defaults
- Payout rate variation by niche
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ── Path setup ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _server_env(monkeypatch):
    """Point server to an in-memory SQLite DB for testing."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("GEMINI_API_KEY", "test-fake-key")
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
async def seed_company(db_session):
    """Seed a company and return its ID."""
    from app.models.company import Company
    from app.core.security import hash_password

    company = Company(
        name="TestCo",
        email="company@test.com",
        password_hash=hash_password("pass123"),
        balance=5000.0,
    )
    db_session.add(company)
    await db_session.flush()
    await db_session.commit()
    return {"company_id": company.id}


@pytest_asyncio.fixture
async def seed_users(db_session, seed_company):
    """Seed several users with various profiles for matching tests."""
    from app.models.user import User
    from app.core.security import hash_password

    users = []

    # User 1: finance niche, US, X+LinkedIn, 1000 X followers
    u1 = User(
        email="finance_user@test.com",
        password_hash=hash_password("pass123"),
        platforms={
            "x": {"username": "@fintrader", "connected": True},
            "linkedin": {"username": "fintrader", "connected": True},
        },
        follower_counts={"x": 1000, "linkedin": 500},
        niche_tags=["finance", "crypto"],
        audience_region="us",
        trust_score=70,
        mode="semi_auto",
        scraped_profiles={
            "x": {"engagement_rate": 0.04},
            "linkedin": {"engagement_rate": 0.03},
        },
    )
    db_session.add(u1)
    users.append(u1)

    # User 2: tech niche, US, X only, 2000 X followers
    u2 = User(
        email="tech_user@test.com",
        password_hash=hash_password("pass123"),
        platforms={"x": {"username": "@techguru", "connected": True}},
        follower_counts={"x": 2000},
        niche_tags=["tech"],
        audience_region="us",
        trust_score=80,
        mode="full_auto",
        scraped_profiles={"x": {"engagement_rate": 0.05}},
    )
    db_session.add(u2)
    users.append(u2)

    # User 3: lifestyle niche, UK, X+Facebook, 500 followers
    u3 = User(
        email="lifestyle_user@test.com",
        password_hash=hash_password("pass123"),
        platforms={
            "x": {"username": "@lifestyle", "connected": True},
            "facebook": {"username": "lifestyle", "connected": True},
        },
        follower_counts={"x": 500, "facebook": 800},
        niche_tags=["lifestyle", "fashion"],
        audience_region="uk",
        trust_score=60,
        mode="semi_auto",
    )
    db_session.add(u3)
    users.append(u3)

    # User 4: finance niche, US, X only, 50 followers (below typical minimums)
    u4 = User(
        email="small_fin_user@test.com",
        password_hash=hash_password("pass123"),
        platforms={"x": {"username": "@smallfin", "connected": True}},
        follower_counts={"x": 50},
        niche_tags=["finance"],
        audience_region="us",
        trust_score=50,
        mode="manual",
    )
    db_session.add(u4)
    users.append(u4)

    await db_session.flush()
    await db_session.commit()
    return {
        "company_id": seed_company["company_id"],
        "user_ids": [u.id for u in users],
    }


@pytest_asyncio.fixture
async def seed_campaign(db_session, seed_users):
    """Seed a campaign for testing reach-estimate on existing campaigns."""
    from app.models.campaign import Campaign

    campaign = Campaign(
        company_id=seed_users["company_id"],
        title="Test Finance Campaign",
        brief="Promote our product",
        assets={},
        budget_total=500.0,
        budget_remaining=500.0,
        payout_rules={
            "rate_per_1k_impressions": 0.75,
            "rate_per_like": 0.02,
            "rate_per_repost": 0.05,
            "rate_per_click": 0.15,
        },
        targeting={
            "niche_tags": ["finance"],
            "target_regions": ["us"],
            "required_platforms": ["x"],
            "min_followers": {"x": 100},
        },
        content_guidance="Be creative",
        penalty_rules={},
        status="active",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(campaign)
    await db_session.flush()
    await db_session.commit()
    return {
        **seed_users,
        "campaign_id": campaign.id,
    }


@pytest_asyncio.fixture
async def company_token(seed_company):
    """Create a JWT for the test company."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(seed_company["company_id"]), "type": "company"})


@pytest_asyncio.fixture
async def company_token_with_users(seed_users):
    """Create a JWT for the test company (after users are seeded)."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(seed_users["company_id"]), "type": "company"})


@pytest_asyncio.fixture
async def company_token_with_campaign(seed_campaign):
    """Create a JWT for the test company (after campaign is seeded)."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(seed_campaign["company_id"]), "type": "company"})


@pytest_asyncio.fixture
async def client():
    """Async HTTP client bound to the FastAPI app."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Mock helpers ──────────────────────────────────────────────────

MOCK_AI_RESPONSE = {
    "title": "Smart Money Indicator Launch",
    "brief": "Promote our AI-powered trading indicator that detects smart money movements before they happen. Highlight ease of use and accuracy.",
    "content_guidance": "Tone: professional but accessible. Must include link to product page. Avoid guaranteed return claims.",
}


def _mock_gemini_generate(*args, **kwargs):
    """Mock Gemini generate_content to return a valid JSON response."""
    import json
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(MOCK_AI_RESPONSE)
    return mock_resp


# ===================================================================
# Service-level tests: campaign_wizard.py
# ===================================================================


class TestSuggestPayoutRates:
    """Test payout rate suggestions vary by niche."""

    def test_finance_niche_gets_premium_rates(self):
        from app.services.campaign_wizard import suggest_payout_rates
        rates = suggest_payout_rates(["finance"])
        assert rates["rate_per_1k_impressions"] == 0.75
        assert rates["rate_per_like"] == 0.02

    def test_tech_niche_gets_higher_than_default(self):
        from app.services.campaign_wizard import suggest_payout_rates
        rates = suggest_payout_rates(["tech"])
        assert rates["rate_per_1k_impressions"] == 0.60
        assert rates["rate_per_click"] == 0.12

    def test_lifestyle_niche_gets_standard_rates(self):
        from app.services.campaign_wizard import suggest_payout_rates
        rates = suggest_payout_rates(["lifestyle"])
        assert rates["rate_per_1k_impressions"] == 0.50
        assert rates["rate_per_like"] == 0.01

    def test_gaming_niche_gets_lower_rates(self):
        from app.services.campaign_wizard import suggest_payout_rates
        rates = suggest_payout_rates(["gaming"])
        assert rates["rate_per_1k_impressions"] == 0.45
        assert rates["rate_per_click"] == 0.08

    def test_multiple_niches_picks_highest_value(self):
        from app.services.campaign_wizard import suggest_payout_rates
        rates = suggest_payout_rates(["gaming", "finance", "lifestyle"])
        # Finance has the highest CPM (0.75)
        assert rates["rate_per_1k_impressions"] == 0.75

    def test_unknown_niche_gets_defaults(self):
        from app.services.campaign_wizard import suggest_payout_rates
        rates = suggest_payout_rates(["underwater_basket_weaving"])
        assert rates["rate_per_1k_impressions"] == 0.50

    def test_empty_niches_gets_defaults(self):
        from app.services.campaign_wizard import suggest_payout_rates
        rates = suggest_payout_rates([])
        assert rates["rate_per_1k_impressions"] == 0.50

    def test_crypto_equals_finance_rates(self):
        from app.services.campaign_wizard import suggest_payout_rates
        finance = suggest_payout_rates(["finance"])
        crypto = suggest_payout_rates(["crypto"])
        assert finance["rate_per_1k_impressions"] == crypto["rate_per_1k_impressions"]


class TestDefaultCampaignContent:
    """Test sensible defaults when AI generation fails."""

    def test_defaults_include_product_description(self):
        from app.services.campaign_wizard import get_default_campaign_content
        result = get_default_campaign_content(
            "AI trading indicator", "brand_awareness", "professional"
        )
        assert "AI trading indicator" in result["title"]
        assert "AI trading indicator" in result["brief"]

    def test_defaults_include_goal(self):
        from app.services.campaign_wizard import get_default_campaign_content
        result = get_default_campaign_content(
            "Product X", "product_launch", "casual"
        )
        assert "product launch" in result["brief"]

    def test_defaults_include_tone(self):
        from app.services.campaign_wizard import get_default_campaign_content
        result = get_default_campaign_content(
            "Product X", "brand_awareness", "funny"
        )
        assert "funny" in result["content_guidance"]

    def test_defaults_truncate_long_title(self):
        from app.services.campaign_wizard import get_default_campaign_content
        long_desc = "A" * 200
        result = get_default_campaign_content(long_desc, "brand_awareness", "professional")
        assert len(result["title"]) <= 80


class TestSuggestBudget:

    def test_minimum_budget_is_50(self):
        from app.services.campaign_wizard import suggest_budget
        result = suggest_budget({"estimated_cost": {"low": 10, "high": 20}})
        assert result >= 50.0

    def test_budget_is_midpoint_of_cost_range(self):
        from app.services.campaign_wizard import suggest_budget
        result = suggest_budget({"estimated_cost": {"low": 200, "high": 400}})
        assert result == 300.0

    def test_budget_with_empty_estimate(self):
        from app.services.campaign_wizard import suggest_budget
        result = suggest_budget({})
        # Falls back to defaults: (50 + 200) / 2 = 125
        assert result >= 50.0


# ===================================================================
# Service-level tests: URL scraping
# ===================================================================


class TestScrapeCompanyUrls:

    @pytest.mark.asyncio
    async def test_scrape_returns_content(self):
        from app.services.campaign_wizard import scrape_company_urls
        with patch("app.services.campaign_wizard.asyncio.to_thread") as mock_thread:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "# Acme Trading\nBest trading signals in the market."
            mock_thread.return_value = mock_result

            content = await scrape_company_urls(["https://example.com"])
            assert "Acme Trading" in content
            assert "example.com" in content

    @pytest.mark.asyncio
    async def test_scrape_empty_urls_returns_empty(self):
        from app.services.campaign_wizard import scrape_company_urls
        content = await scrape_company_urls([])
        assert content == ""

    @pytest.mark.asyncio
    async def test_scrape_handles_failure_gracefully(self):
        from app.services.campaign_wizard import scrape_company_urls
        with patch("app.services.campaign_wizard.asyncio.to_thread", side_effect=OSError("timeout")):
            content = await scrape_company_urls(["https://unreachable.example.com"])
            assert content == ""

    @pytest.mark.asyncio
    async def test_scrape_truncates_to_2000_chars(self):
        from app.services.campaign_wizard import scrape_company_urls
        with patch("app.services.campaign_wizard.asyncio.to_thread") as mock_thread:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "A" * 5000
            mock_thread.return_value = mock_result

            content = await scrape_company_urls(["https://example.com"])
            assert len(content) <= 2000

    @pytest.mark.asyncio
    async def test_scrape_limits_to_3_urls(self):
        from app.services.campaign_wizard import scrape_company_urls
        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.returncode = 0
            result.stdout = f"Content {call_count}"
            return result

        with patch("app.services.campaign_wizard.asyncio.to_thread", side_effect=mock_run):
            urls = [f"https://example{i}.com" for i in range(5)]
            await scrape_company_urls(urls)
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_scrape_skips_failed_urls(self):
        """If one URL fails but another succeeds, return the successful content."""
        from app.services.campaign_wizard import scrape_company_urls

        call_idx = 0

        def mock_run(*args, **kwargs):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                raise OSError("connection refused")
            result = MagicMock()
            result.returncode = 0
            result.stdout = "Good content from URL 2"
            return result

        with patch("app.services.campaign_wizard.asyncio.to_thread", side_effect=mock_run):
            content = await scrape_company_urls(["https://fail.com", "https://ok.com"])
            assert "Good content" in content


# ===================================================================
# Service-level tests: AI generation
# ===================================================================


class TestGenerateCampaignWithAI:

    @pytest.mark.asyncio
    async def test_generate_returns_required_fields(self):
        from app.services.campaign_wizard import generate_campaign_with_ai

        mock_client = MagicMock()
        mock_client.models.generate_content = _mock_gemini_generate

        with patch("google.genai.Client", return_value=mock_client):
            with patch("app.services.campaign_wizard.asyncio.to_thread", side_effect=lambda fn, *a, **kw: fn(*a, **kw)):
                result = await generate_campaign_with_ai(
                    product_description="AI trading indicator",
                    goal="brand_awareness",
                    tone="professional",
                    must_include=["Visit example.com"],
                    must_avoid=["competitors"],
                    target_niches=["finance"],
                    target_regions=["us"],
                    scraped_content="",
                )

            assert "title" in result
            assert "brief" in result
            assert "content_guidance" in result

    @pytest.mark.asyncio
    async def test_generate_with_list_must_include(self):
        from app.services.campaign_wizard import generate_campaign_with_ai

        mock_client = MagicMock()
        mock_client.models.generate_content = _mock_gemini_generate

        with patch("google.genai.Client", return_value=mock_client):
            with patch("app.services.campaign_wizard.asyncio.to_thread", side_effect=lambda fn, *a, **kw: fn(*a, **kw)):
                result = await generate_campaign_with_ai(
                    product_description="Product X",
                    goal="lead_generation",
                    tone="casual",
                    must_include=["#hashtag1", "#hashtag2"],
                    must_avoid=["bad stuff"],
                    target_niches=["tech"],
                    target_regions=["us", "uk"],
                    scraped_content="Some scraped data",
                )

            assert "title" in result

    @pytest.mark.asyncio
    async def test_generate_raises_without_api_key(self, monkeypatch):
        from app.services.campaign_wizard import generate_campaign_with_ai
        monkeypatch.setenv("GEMINI_API_KEY", "")

        with pytest.raises(RuntimeError, match="GEMINI_API_KEY not set"):
            await generate_campaign_with_ai(
                product_description="X",
                goal="brand_awareness",
                tone="professional",
                must_include=None,
                must_avoid=None,
                target_niches=[],
                target_regions=[],
                scraped_content="",
            )


# ===================================================================
# Service-level tests: reach estimation
# ===================================================================


class TestEstimateReach:

    @pytest.mark.asyncio
    async def test_matching_users_with_finance_niche(self, db_session, seed_users):
        from app.services.campaign_wizard import estimate_reach
        result = await estimate_reach(
            db=db_session,
            niche_tags=["finance"],
            target_regions=["us"],
            required_platforms=["x"],
            min_followers={"x": 100},
        )
        # User 1 (finance, US, x+linkedin, 1000 followers) matches
        # User 4 (finance, US, x, 50 followers) fails min_followers
        assert result["matching_users"] == 1
        assert result["estimated_reach"]["low"] > 0
        assert result["estimated_reach"]["high"] > result["estimated_reach"]["low"]

    @pytest.mark.asyncio
    async def test_no_matching_users(self, db_session, seed_users):
        from app.services.campaign_wizard import estimate_reach
        result = await estimate_reach(
            db=db_session,
            niche_tags=["astronomy"],
            target_regions=["us"],
        )
        assert result["matching_users"] == 0
        assert result["estimated_reach"]["low"] == 0
        assert result["estimated_reach"]["high"] == 0

    @pytest.mark.asyncio
    async def test_reach_without_niche_filter(self, db_session, seed_users):
        """Without niche filter, all active users should match."""
        from app.services.campaign_wizard import estimate_reach
        result = await estimate_reach(db=db_session)
        # All 4 users should match (no filters)
        assert result["matching_users"] == 4

    @pytest.mark.asyncio
    async def test_reach_filters_by_region(self, db_session, seed_users):
        from app.services.campaign_wizard import estimate_reach
        result = await estimate_reach(
            db=db_session,
            target_regions=["uk"],
        )
        # User 3 is UK, user 4 doesn't match because it's US only
        # Users without matching region are filtered out
        assert result["matching_users"] >= 1

    @pytest.mark.asyncio
    async def test_reach_filters_by_platform(self, db_session, seed_users):
        from app.services.campaign_wizard import estimate_reach
        result = await estimate_reach(
            db=db_session,
            required_platforms=["linkedin"],
        )
        # Only User 1 has linkedin connected
        assert result["matching_users"] == 1

    @pytest.mark.asyncio
    async def test_reach_filters_by_min_followers(self, db_session, seed_users):
        from app.services.campaign_wizard import estimate_reach
        result = await estimate_reach(
            db=db_session,
            min_followers={"x": 1500},
        )
        # Only User 2 has 2000 X followers
        assert result["matching_users"] == 1

    @pytest.mark.asyncio
    async def test_reach_includes_per_platform_breakdown(self, db_session, seed_users):
        from app.services.campaign_wizard import estimate_reach
        result = await estimate_reach(
            db=db_session,
            required_platforms=["x"],
            niche_tags=["finance"],
        )
        assert "per_platform" in result
        if result["matching_users"] > 0:
            assert "x" in result["per_platform"]
            assert "users" in result["per_platform"]["x"]

    @pytest.mark.asyncio
    async def test_reach_uses_scraped_engagement_rates(self, db_session, seed_users):
        from app.services.campaign_wizard import estimate_reach
        result = await estimate_reach(
            db=db_session,
            niche_tags=["finance"],
            required_platforms=["x"],
            min_followers={"x": 100},
        )
        # User 1 has scraped engagement_rate of 0.04
        assert result["avg_engagement_rate"] == 0.04

    @pytest.mark.asyncio
    async def test_reach_default_engagement_when_no_scraped_data(self, db_session, seed_users):
        from app.services.campaign_wizard import estimate_reach
        result = await estimate_reach(
            db=db_session,
            niche_tags=["lifestyle"],
        )
        # User 3 has no engagement_rate in scraped_profiles
        assert result["avg_engagement_rate"] == 0.035  # default

    @pytest.mark.asyncio
    async def test_cost_estimates_use_payout_rates(self, db_session, seed_users):
        from app.services.campaign_wizard import estimate_reach
        result = await estimate_reach(
            db=db_session,
            niche_tags=["finance"],
            required_platforms=["x"],
            min_followers={"x": 100},
            payout_rates={
                "rate_per_1k_impressions": 1.00,
                "rate_per_like": 0.05,
                "rate_per_repost": 0.10,
                "rate_per_click": 0.20,
            },
        )
        assert result["estimated_cost"]["low"] > 0
        assert result["estimated_cost"]["high"] > result["estimated_cost"]["low"]


# ===================================================================
# API endpoint tests: POST /api/company/campaigns/ai-wizard
# ===================================================================


class TestAIWizardEndpoint:

    @pytest.mark.asyncio
    async def test_wizard_generates_all_required_fields(
        self, client, company_token_with_users
    ):
        """Wizard response should contain generated_campaign, scraped_data, reach_estimate."""
        with patch("app.services.campaign_wizard.generate_campaign_with_ai") as mock_ai:
            mock_ai.return_value = MOCK_AI_RESPONSE.copy()

            resp = await client.post(
                "/api/company/campaigns/ai-wizard",
                json={
                    "product_description": "AI trading indicator",
                    "campaign_goal": "brand_awareness",
                    "target_niches": ["finance"],
                    "target_regions": ["us"],
                    "required_platforms": ["x"],
                    "min_followers": {"x": 100},
                    "tone": "professional",
                },
                headers={"Authorization": f"Bearer {company_token_with_users}"},
            )

        assert resp.status_code == 200
        data = resp.json()

        # Top-level keys
        assert "generated_campaign" in data
        assert "scraped_data" in data
        assert "reach_estimate" in data

        # Campaign fields
        campaign = data["generated_campaign"]
        assert "title" in campaign
        assert "brief" in campaign
        assert "content_guidance" in campaign
        assert "payout_rules" in campaign
        assert "targeting" in campaign
        assert "budget_total" in campaign

        # Payout rules structure
        payout = campaign["payout_rules"]
        assert "rate_per_1k_impressions" in payout
        assert "rate_per_like" in payout
        assert "rate_per_repost" in payout
        assert "rate_per_click" in payout

        # Targeting preserved
        targeting = campaign["targeting"]
        assert targeting["niche_tags"] == ["finance"]
        assert targeting["target_regions"] == ["us"]
        assert targeting["required_platforms"] == ["x"]
        assert targeting["min_followers"] == {"x": 100}

    @pytest.mark.asyncio
    async def test_wizard_with_company_urls(self, client, company_token_with_users):
        """Wizard should scrape URLs and include scraped_data in response."""
        with patch("app.services.campaign_wizard.generate_campaign_with_ai") as mock_ai, \
             patch("app.services.campaign_wizard.scrape_company_urls") as mock_scrape:
            mock_ai.return_value = MOCK_AI_RESPONSE.copy()
            mock_scrape.return_value = "# Acme Corp\nBest trading platform."

            resp = await client.post(
                "/api/company/campaigns/ai-wizard",
                json={
                    "product_description": "AI trading indicator",
                    "campaign_goal": "brand_awareness",
                    "company_urls": ["https://example.com", "https://example.com/product"],
                    "target_niches": ["finance"],
                },
                headers={"Authorization": f"Bearer {company_token_with_users}"},
            )

        assert resp.status_code == 200
        data = resp.json()

        # scraped_data should have info about the scraping
        assert data["scraped_data"]["urls_scraped"] == 2
        assert data["scraped_data"]["content_length"] > 0

        # AI should have been called
        mock_ai.assert_called_once()

    @pytest.mark.asyncio
    async def test_wizard_without_urls(self, client, company_token_with_users):
        """Wizard works with just product_description, no company URLs."""
        with patch("app.services.campaign_wizard.generate_campaign_with_ai") as mock_ai:
            mock_ai.return_value = MOCK_AI_RESPONSE.copy()

            resp = await client.post(
                "/api/company/campaigns/ai-wizard",
                json={
                    "product_description": "A new fitness tracker",
                    "campaign_goal": "product_launch",
                    "target_niches": ["fitness"],
                    "tone": "casual",
                },
                headers={"Authorization": f"Bearer {company_token_with_users}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["generated_campaign"]["title"]  # non-empty
        assert data["scraped_data"] == {}  # no URLs, no scraped data

    @pytest.mark.asyncio
    async def test_wizard_gemini_failure_returns_defaults(
        self, client, company_token_with_users
    ):
        """When Gemini fails, wizard should return sensible default content."""
        with patch("app.services.campaign_wizard.generate_campaign_with_ai",
                    side_effect=RuntimeError("Gemini API error")):
            resp = await client.post(
                "/api/company/campaigns/ai-wizard",
                json={
                    "product_description": "AI trading indicator",
                    "campaign_goal": "brand_awareness",
                },
                headers={"Authorization": f"Bearer {company_token_with_users}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        campaign = data["generated_campaign"]

        # Should still have all fields, just with default content
        assert campaign["title"]
        assert campaign["brief"]
        assert campaign["content_guidance"]
        assert "AI trading indicator" in campaign["title"] or "AI trading indicator" in campaign["brief"]

    @pytest.mark.asyncio
    async def test_wizard_payout_rates_vary_by_niche(
        self, client, company_token_with_users
    ):
        """Finance campaign should get higher rates than lifestyle."""
        with patch("app.services.campaign_wizard.generate_campaign_with_ai") as mock_ai:
            mock_ai.return_value = MOCK_AI_RESPONSE.copy()

            # Finance campaign
            resp_fin = await client.post(
                "/api/company/campaigns/ai-wizard",
                json={
                    "product_description": "Trading tool",
                    "campaign_goal": "brand_awareness",
                    "target_niches": ["finance"],
                },
                headers={"Authorization": f"Bearer {company_token_with_users}"},
            )

            # Lifestyle campaign
            resp_life = await client.post(
                "/api/company/campaigns/ai-wizard",
                json={
                    "product_description": "Fashion brand",
                    "campaign_goal": "brand_awareness",
                    "target_niches": ["lifestyle"],
                },
                headers={"Authorization": f"Bearer {company_token_with_users}"},
            )

        fin_rates = resp_fin.json()["generated_campaign"]["payout_rules"]
        life_rates = resp_life.json()["generated_campaign"]["payout_rules"]
        assert fin_rates["rate_per_1k_impressions"] > life_rates["rate_per_1k_impressions"]

    @pytest.mark.asyncio
    async def test_wizard_includes_reach_estimate(
        self, client, company_token_with_users
    ):
        """Wizard response should include reach_estimate with matching users."""
        with patch("app.services.campaign_wizard.generate_campaign_with_ai") as mock_ai:
            mock_ai.return_value = MOCK_AI_RESPONSE.copy()

            resp = await client.post(
                "/api/company/campaigns/ai-wizard",
                json={
                    "product_description": "AI trading indicator",
                    "campaign_goal": "brand_awareness",
                    "target_niches": ["finance"],
                    "target_regions": ["us"],
                    "required_platforms": ["x"],
                    "min_followers": {"x": 100},
                },
                headers={"Authorization": f"Bearer {company_token_with_users}"},
            )

        assert resp.status_code == 200
        reach = resp.json()["reach_estimate"]
        assert "matching_users" in reach
        assert "estimated_reach" in reach
        assert "estimated_cost" in reach
        assert reach["matching_users"] >= 1  # At least user 1 matches

    @pytest.mark.asyncio
    async def test_wizard_respects_budget_range(self, client, company_token_with_users):
        """Budget suggestion should be clamped to the provided budget_range."""
        with patch("app.services.campaign_wizard.generate_campaign_with_ai") as mock_ai:
            mock_ai.return_value = MOCK_AI_RESPONSE.copy()

            resp = await client.post(
                "/api/company/campaigns/ai-wizard",
                json={
                    "product_description": "Product X",
                    "campaign_goal": "brand_awareness",
                    "budget_range": {"min": 200, "max": 500},
                },
                headers={"Authorization": f"Bearer {company_token_with_users}"},
            )

        budget = resp.json()["generated_campaign"]["budget_total"]
        assert 200 <= budget <= 500

    @pytest.mark.asyncio
    async def test_wizard_requires_auth(self, client):
        resp = await client.post(
            "/api/company/campaigns/ai-wizard",
            json={
                "product_description": "Test",
                "campaign_goal": "brand_awareness",
            },
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_wizard_rejects_user_token(self, client, seed_users, db_session):
        """User tokens should not be able to call the wizard."""
        from app.core.security import create_access_token
        user_token = create_access_token(
            {"sub": str(seed_users["user_ids"][0]), "type": "user"}
        )
        resp = await client.post(
            "/api/company/campaigns/ai-wizard",
            json={
                "product_description": "Test",
                "campaign_goal": "brand_awareness",
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_wizard_missing_required_field(self, client, company_token_with_users):
        """Missing product_description should return 422."""
        resp = await client.post(
            "/api/company/campaigns/ai-wizard",
            json={
                "campaign_goal": "brand_awareness",
            },
            headers={"Authorization": f"Bearer {company_token_with_users}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_wizard_preserves_dates(self, client, company_token_with_users):
        """If start_date and end_date provided, they should be in the response."""
        with patch("app.services.campaign_wizard.generate_campaign_with_ai") as mock_ai:
            mock_ai.return_value = MOCK_AI_RESPONSE.copy()

            resp = await client.post(
                "/api/company/campaigns/ai-wizard",
                json={
                    "product_description": "Product X",
                    "campaign_goal": "brand_awareness",
                    "start_date": "2026-04-01T00:00:00Z",
                    "end_date": "2026-04-30T23:59:59Z",
                },
                headers={"Authorization": f"Bearer {company_token_with_users}"},
            )

        campaign = resp.json()["generated_campaign"]
        assert campaign["start_date"] == "2026-04-01T00:00:00Z"
        assert campaign["end_date"] == "2026-04-30T23:59:59Z"


# ===================================================================
# API endpoint tests: POST /api/company/campaigns/reach-estimate
# ===================================================================


class TestReachEstimateEndpoint:

    @pytest.mark.asyncio
    async def test_reach_estimate_with_matching_users(
        self, client, company_token_with_users
    ):
        resp = await client.post(
            "/api/company/campaigns/reach-estimate",
            json={
                "target_niches": ["finance"],
                "target_regions": ["us"],
                "required_platforms": ["x"],
                "min_followers": {"x": 100},
            },
            headers={"Authorization": f"Bearer {company_token_with_users}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matching_users"] >= 1
        assert data["estimated_reach"]["low"] > 0
        assert data["estimated_reach"]["high"] > data["estimated_reach"]["low"]
        assert data["estimated_cost"]["low"] > 0

    @pytest.mark.asyncio
    async def test_reach_estimate_with_no_matching_users(
        self, client, company_token_with_users
    ):
        resp = await client.post(
            "/api/company/campaigns/reach-estimate",
            json={
                "target_niches": ["underwater_photography"],
                "target_regions": ["us"],
            },
            headers={"Authorization": f"Bearer {company_token_with_users}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matching_users"] == 0
        assert data["estimated_reach"]["low"] == 0
        assert data["estimated_reach"]["high"] == 0

    @pytest.mark.asyncio
    async def test_reach_estimate_empty_filters(
        self, client, company_token_with_users
    ):
        """With no filters, all users should match."""
        resp = await client.post(
            "/api/company/campaigns/reach-estimate",
            json={},
            headers={"Authorization": f"Bearer {company_token_with_users}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matching_users"] == 4  # All seeded users

    @pytest.mark.asyncio
    async def test_reach_estimate_includes_per_platform(
        self, client, company_token_with_users
    ):
        resp = await client.post(
            "/api/company/campaigns/reach-estimate",
            json={
                "required_platforms": ["x"],
                "target_niches": ["finance"],
            },
            headers={"Authorization": f"Bearer {company_token_with_users}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "per_platform" in data

    @pytest.mark.asyncio
    async def test_reach_estimate_requires_auth(self, client):
        resp = await client.post(
            "/api/company/campaigns/reach-estimate",
            json={"target_niches": ["finance"]},
        )
        assert resp.status_code in (401, 403)


# ===================================================================
# API endpoint tests: GET /api/company/campaigns/{id}/reach-estimate
# ===================================================================


class TestCampaignReachEstimateEndpoint:

    @pytest.mark.asyncio
    async def test_campaign_reach_estimate(
        self, client, company_token_with_campaign, seed_campaign
    ):
        """GET reach-estimate for an existing campaign."""
        campaign_id = seed_campaign["campaign_id"]
        resp = await client.get(
            f"/api/company/campaigns/{campaign_id}/reach-estimate",
            headers={"Authorization": f"Bearer {company_token_with_campaign}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matching_users"] >= 1
        assert "estimated_reach" in data
        assert "estimated_cost" in data

    @pytest.mark.asyncio
    async def test_campaign_reach_estimate_with_overrides(
        self, client, company_token_with_campaign, seed_campaign
    ):
        """Query param overrides should change the estimate."""
        campaign_id = seed_campaign["campaign_id"]
        resp = await client.get(
            f"/api/company/campaigns/{campaign_id}/reach-estimate",
            params={
                "niche_tags": "astronomy",
            },
            headers={"Authorization": f"Bearer {company_token_with_campaign}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # No users in "astronomy" niche
        assert data["matching_users"] == 0

    @pytest.mark.asyncio
    async def test_campaign_reach_estimate_nonexistent(
        self, client, company_token_with_campaign
    ):
        resp = await client.get(
            "/api/company/campaigns/99999/reach-estimate",
            headers={"Authorization": f"Bearer {company_token_with_campaign}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_campaign_reach_estimate_min_follower_overrides(
        self, client, company_token_with_campaign, seed_campaign
    ):
        """Override min_followers via query params."""
        campaign_id = seed_campaign["campaign_id"]

        # Very high min followers -- should filter out everyone
        resp = await client.get(
            f"/api/company/campaigns/{campaign_id}/reach-estimate",
            params={"min_followers_x": 100000},
            headers={"Authorization": f"Bearer {company_token_with_campaign}"},
        )
        assert resp.status_code == 200
        assert resp.json()["matching_users"] == 0

    @pytest.mark.asyncio
    async def test_campaign_reach_estimate_requires_auth(self, client, seed_campaign):
        campaign_id = seed_campaign["campaign_id"]
        resp = await client.get(
            f"/api/company/campaigns/{campaign_id}/reach-estimate",
        )
        assert resp.status_code in (401, 403)


# ===================================================================
# Integration test: full wizard pipeline
# ===================================================================


class TestWizardIntegration:

    @pytest.mark.asyncio
    async def test_wizard_output_can_feed_campaign_create(
        self, client, company_token_with_users
    ):
        """The wizard output should be directly usable as input to create_campaign."""
        with patch("app.services.campaign_wizard.generate_campaign_with_ai") as mock_ai:
            mock_ai.return_value = MOCK_AI_RESPONSE.copy()

            resp = await client.post(
                "/api/company/campaigns/ai-wizard",
                json={
                    "product_description": "AI trading indicator",
                    "campaign_goal": "brand_awareness",
                    "target_niches": ["finance"],
                    "required_platforms": ["x"],
                    "start_date": "2026-04-01T00:00:00Z",
                    "end_date": "2026-04-30T23:59:59Z",
                },
                headers={"Authorization": f"Bearer {company_token_with_users}"},
            )

        assert resp.status_code == 200
        generated = resp.json()["generated_campaign"]

        # The generated campaign should have all fields needed for CampaignCreate
        assert "title" in generated
        assert "brief" in generated
        assert "budget_total" in generated
        assert "payout_rules" in generated
        assert "targeting" in generated
        assert generated["budget_total"] >= 50.0  # minimum budget

    @pytest.mark.asyncio
    async def test_reach_estimate_consistency(
        self, client, company_token_with_users
    ):
        """Wizard reach_estimate should match standalone reach-estimate for same criteria."""
        targeting = {
            "target_niches": ["finance"],
            "target_regions": ["us"],
            "required_platforms": ["x"],
            "min_followers": {"x": 100},
        }

        with patch("app.services.campaign_wizard.generate_campaign_with_ai") as mock_ai:
            mock_ai.return_value = MOCK_AI_RESPONSE.copy()

            wizard_resp = await client.post(
                "/api/company/campaigns/ai-wizard",
                json={
                    "product_description": "AI trading indicator",
                    "campaign_goal": "brand_awareness",
                    **targeting,
                },
                headers={"Authorization": f"Bearer {company_token_with_users}"},
            )

        standalone_resp = await client.post(
            "/api/company/campaigns/reach-estimate",
            json=targeting,
            headers={"Authorization": f"Bearer {company_token_with_users}"},
        )

        wizard_reach = wizard_resp.json()["reach_estimate"]
        standalone_reach = standalone_resp.json()

        assert wizard_reach["matching_users"] == standalone_reach["matching_users"]
