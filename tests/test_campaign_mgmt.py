"""Tests for campaign management improvements (Task 5).

Covers:
- Campaign cloning (POST /api/company/campaigns/{id}/clone)
- Campaign deletion (DELETE /api/company/campaigns/{id})
- Budget top-up (POST /api/company/campaigns/{id}/budget-topup)
- Budget exhaustion action (auto_pause vs auto_complete)
- 80% budget alert flag
- Minimum $50 budget on creation
- Edit increments campaign_version
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

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
    from app.core import config
    config.get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_session():
    """Create tables and yield an async DB session."""
    from app.core.database import engine, async_session, Base
    import app.models  # noqa: F401 — register all models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def seed_data(db_session):
    """Seed a company with balance, a draft campaign, and return IDs."""
    from app.models.company import Company
    from app.models.campaign import Campaign
    from app.core.security import hash_password

    company = Company(
        name="TestCo",
        email="company@test.com",
        password_hash=hash_password("pass123"),
        balance=5000.0,
    )
    db_session.add(company)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    campaign = Campaign(
        company_id=company.id,
        title="Test Campaign",
        brief="Promote our product",
        assets={"logo_url": "https://example.com/logo.png"},
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
            "niche_tags": ["finance"],
            "required_platforms": ["x"],
            "target_regions": ["us"],
        },
        content_guidance="Be creative",
        penalty_rules={},
        status="draft",
        start_date=now,
        end_date=now + timedelta(days=30),
        budget_exhaustion_action="auto_pause",
    )
    db_session.add(campaign)
    await db_session.flush()
    await db_session.commit()

    return {
        "company_id": company.id,
        "campaign_id": campaign.id,
    }


@pytest_asyncio.fixture
async def company_token(seed_data):
    """Create a JWT for the test company."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(seed_data["company_id"]), "type": "company"})


@pytest_asyncio.fixture
async def other_company_token(db_session):
    """Create a second company and its JWT."""
    from app.models.company import Company
    from app.core.security import hash_password, create_access_token

    company2 = Company(
        name="OtherCo",
        email="other@test.com",
        password_hash=hash_password("pass123"),
        balance=1000.0,
    )
    db_session.add(company2)
    await db_session.flush()
    await db_session.commit()

    return create_access_token({"sub": str(company2.id), "type": "company"})


@pytest_asyncio.fixture
async def client():
    """Async HTTP client bound to the FastAPI app."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ===================================================================
# Campaign Cloning
# ===================================================================

class TestCampaignClone:

    @pytest.mark.asyncio
    async def test_clone_creates_duplicate_with_correct_fields(
        self, client, company_token, seed_data
    ):
        """Clone duplicates all fields, sets status=draft, resets counters."""
        resp = await client.post(
            f"/api/company/campaigns/{seed_data['campaign_id']}/clone",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # New ID, different from original
        assert data["id"] != seed_data["campaign_id"]

        # Fields copied from original
        assert data["title"] == "Test Campaign"
        assert data["brief"] == "Promote our product"
        assert data["content_guidance"] == "Be creative"
        assert data["payout_rules"]["rate_per_1k_impressions"] == 0.50

        # Reset fields
        assert data["status"] == "draft"
        assert data["budget_remaining"] == 500.0
        assert data["budget_total"] == 500.0
        assert data["campaign_version"] == 1
        assert data["budget_alert_sent"] is False

    @pytest.mark.asyncio
    async def test_clone_deducts_budget_from_company(
        self, client, company_token, seed_data, db_session
    ):
        """Cloning deducts budget_total from company balance."""
        from app.models.company import Company
        from sqlalchemy import select

        resp = await client.post(
            f"/api/company/campaigns/{seed_data['campaign_id']}/clone",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200

        # Seed fixture sets balance=5000, campaign was added directly (no API deduction).
        # Clone deducts 500 -> 4500.
        db_session.expire_all()
        result = await db_session.execute(
            select(Company).where(Company.id == seed_data["company_id"])
        )
        company = result.scalar_one()
        assert float(company.balance) == 4500.0

    @pytest.mark.asyncio
    async def test_clone_fails_for_other_companys_campaign(
        self, client, other_company_token, seed_data
    ):
        """Cannot clone a campaign owned by a different company."""
        resp = await client.post(
            f"/api/company/campaigns/{seed_data['campaign_id']}/clone",
            headers={"Authorization": f"Bearer {other_company_token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_clone_fails_with_insufficient_balance(
        self, client, company_token, seed_data, db_session
    ):
        """Clone fails if company doesn't have enough balance."""
        from app.models.company import Company
        from sqlalchemy import select

        # Drain the balance
        result = await db_session.execute(
            select(Company).where(Company.id == seed_data["company_id"])
        )
        company = result.scalar_one()
        company.balance = 10.0  # Less than 500 budget
        await db_session.flush()
        await db_session.commit()

        resp = await client.post(
            f"/api/company/campaigns/{seed_data['campaign_id']}/clone",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 400
        assert "Insufficient" in resp.json()["detail"]


# ===================================================================
# Campaign Deletion
# ===================================================================

class TestCampaignDelete:

    @pytest.mark.asyncio
    async def test_delete_draft_campaign_refunds_budget(
        self, client, company_token, seed_data, db_session
    ):
        """Deleting a draft campaign refunds budget_total to company balance."""
        from app.models.company import Company
        from sqlalchemy import select

        resp = await client.delete(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"

        # Seed fixture sets balance=5000, campaign was added directly (no API deduction).
        # Delete refunds budget_total (500) -> 5500.
        db_session.expire_all()
        result = await db_session.execute(
            select(Company).where(Company.id == seed_data["company_id"])
        )
        company = result.scalar_one()
        assert float(company.balance) == 5500.0

    @pytest.mark.asyncio
    async def test_delete_cancelled_campaign(
        self, client, company_token, seed_data, db_session
    ):
        """Can delete a cancelled campaign (no refund for cancelled)."""
        from app.models.campaign import Campaign
        from sqlalchemy import select

        # First set campaign to cancelled (via draft -> cancelled transition)
        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        campaign.status = "cancelled"
        await db_session.flush()
        await db_session.commit()

        resp = await client.delete(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_active_campaign_returns_400(
        self, client, company_token, seed_data, db_session
    ):
        """Cannot delete an active campaign."""
        from app.models.campaign import Campaign
        from sqlalchemy import select

        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        campaign.status = "active"
        await db_session.flush()
        await db_session.commit()

        resp = await client.delete(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 400
        assert "active" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_paused_campaign_returns_400(
        self, client, company_token, seed_data, db_session
    ):
        """Cannot delete a paused campaign."""
        from app.models.campaign import Campaign
        from sqlalchemy import select

        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        campaign.status = "paused"
        await db_session.flush()
        await db_session.commit()

        resp = await client.delete(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_removes_assignments(
        self, client, company_token, seed_data, db_session
    ):
        """Deleting a campaign also removes associated assignments."""
        from app.models.assignment import CampaignAssignment
        from app.models.user import User
        from app.core.security import hash_password
        from sqlalchemy import select

        # Create a user and assignment
        user = User(
            email="user@test.com",
            password_hash=hash_password("pass123"),
            platforms={},
            follower_counts={},
            niche_tags=[],
        )
        db_session.add(user)
        await db_session.flush()

        assignment = CampaignAssignment(
            campaign_id=seed_data["campaign_id"],
            user_id=user.id,
            status="pending_invitation",
            content_mode="ai_generated",
            payout_multiplier=1.0,
        )
        db_session.add(assignment)
        await db_session.flush()
        await db_session.commit()

        resp = await client.delete(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200

        # Verify assignment was deleted
        db_session.expire_all()
        result = await db_session.execute(
            select(CampaignAssignment).where(
                CampaignAssignment.campaign_id == seed_data["campaign_id"]
            )
        )
        assert result.scalar_one_or_none() is None


# ===================================================================
# Budget Top-Up
# ===================================================================

class TestBudgetTopUp:

    @pytest.mark.asyncio
    async def test_topup_adds_to_remaining_deducts_from_balance(
        self, client, company_token, seed_data, db_session
    ):
        """Top-up adds to campaign budget and deducts from company balance."""
        from app.models.campaign import Campaign
        from sqlalchemy import select

        # First activate the campaign
        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        campaign.status = "active"
        await db_session.flush()
        await db_session.commit()

        resp = await client.post(
            f"/api/company/campaigns/{seed_data['campaign_id']}/budget-topup",
            headers={"Authorization": f"Bearer {company_token}"},
            json={"amount": 100.0},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Budget: 500 + 100 = 600
        assert data["budget_remaining"] == 600.0
        assert data["budget_total"] == 600.0

    @pytest.mark.asyncio
    async def test_topup_resumes_paused_campaign(
        self, client, company_token, seed_data, db_session
    ):
        """Top-up resumes a campaign that was auto-paused due to budget exhaustion."""
        from app.models.campaign import Campaign
        from sqlalchemy import select

        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        campaign.status = "paused"
        campaign.budget_remaining = 0.50
        campaign.budget_exhaustion_action = "auto_pause"
        await db_session.flush()
        await db_session.commit()

        resp = await client.post(
            f"/api/company/campaigns/{seed_data['campaign_id']}/budget-topup",
            headers={"Authorization": f"Bearer {company_token}"},
            json={"amount": 200.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["budget_remaining"] == 200.50

    @pytest.mark.asyncio
    async def test_topup_does_not_resume_manually_paused_campaign(
        self, client, company_token, seed_data, db_session
    ):
        """Top-up does NOT resume a campaign paused with auto_complete action (manually paused)."""
        from app.models.campaign import Campaign
        from sqlalchemy import select

        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        campaign.status = "paused"
        campaign.budget_remaining = 0.50
        campaign.budget_exhaustion_action = "auto_complete"
        await db_session.flush()
        await db_session.commit()

        resp = await client.post(
            f"/api/company/campaigns/{seed_data['campaign_id']}/budget-topup",
            headers={"Authorization": f"Bearer {company_token}"},
            json={"amount": 200.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should stay paused since exhaustion_action is auto_complete
        assert data["status"] == "paused"

    @pytest.mark.asyncio
    async def test_topup_fails_with_insufficient_balance(
        self, client, company_token, seed_data, db_session
    ):
        """Top-up fails if company doesn't have enough balance."""
        resp = await client.post(
            f"/api/company/campaigns/{seed_data['campaign_id']}/budget-topup",
            headers={"Authorization": f"Bearer {company_token}"},
            json={"amount": 99999.0},
        )
        assert resp.status_code == 400
        assert "Insufficient" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_topup_fails_with_zero_amount(
        self, client, company_token, seed_data
    ):
        """Top-up fails with amount <= 0."""
        resp = await client.post(
            f"/api/company/campaigns/{seed_data['campaign_id']}/budget-topup",
            headers={"Authorization": f"Bearer {company_token}"},
            json={"amount": 0},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_topup_fails_with_negative_amount(
        self, client, company_token, seed_data
    ):
        """Top-up fails with negative amount."""
        resp = await client.post(
            f"/api/company/campaigns/{seed_data['campaign_id']}/budget-topup",
            headers={"Authorization": f"Bearer {company_token}"},
            json={"amount": -50.0},
        )
        assert resp.status_code == 400


# ===================================================================
# Budget Exhaustion Action (auto_pause vs auto_complete)
# ===================================================================

class TestBudgetExhaustion:

    @pytest.mark.asyncio
    async def test_auto_complete_sets_completed(self, _server_env):
        """When budget < $1 and action is auto_complete, status becomes completed."""
        from app.core.database import engine, async_session, Base
        import app.models  # noqa: F401
        from app.services.billing import run_billing_cycle
        from app.models.company import Company
        from app.models.campaign import Campaign
        from app.models.user import User
        from app.models.assignment import CampaignAssignment
        from app.models.post import Post
        from app.models.metric import Metric
        from sqlalchemy import select

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        now = datetime.now(timezone.utc)

        async with async_session() as session:
            company = Company(
                name="BillingCo", email="billing-complete@test.com",
                password_hash="hash", balance=5000,
            )
            session.add(company)
            await session.flush()

            campaign = Campaign(
                company_id=company.id,
                title="Low Budget Campaign",
                brief="Brief",
                budget_total=5.0,
                budget_remaining=5.0,
                payout_rules={"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01,
                              "rate_per_repost": 0.05, "rate_per_click": 0.10},
                start_date=now - timedelta(days=7),
                end_date=now + timedelta(days=7),
                status="active",
                budget_exhaustion_action="auto_complete",
            )
            session.add(campaign)
            await session.flush()
            campaign_id = campaign.id

            user = User(email="billing-user-complete@test.com", password_hash="hash")
            session.add(user)
            await session.flush()

            assignment = CampaignAssignment(
                campaign_id=campaign.id, user_id=user.id,
                status="posted", content_mode="ai_generated", payout_multiplier=1.0,
            )
            session.add(assignment)
            await session.flush()

            post = Post(
                assignment_id=assignment.id, platform="x",
                post_url="https://x.com/test/123", content_hash="abc",
                posted_at=now - timedelta(hours=73), status="live",
            )
            session.add(post)
            await session.flush()

            metric = Metric(
                post_id=post.id, impressions=10000, likes=100,
                reposts=20, clicks=50, scraped_at=now, is_final=True,
            )
            session.add(metric)
            await session.flush()
            await session.commit()

        async with async_session() as session:
            await run_billing_cycle(session)
            await session.commit()

        async with async_session() as session:
            result = await session.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            updated_campaign = result.scalar_one()
            assert updated_campaign.status == "completed"

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_auto_pause_sets_paused(self, _server_env):
        """When budget < $1 and action is auto_pause, status becomes paused."""
        from app.core.database import engine, async_session, Base
        import app.models  # noqa: F401
        from app.services.billing import run_billing_cycle
        from app.models.company import Company
        from app.models.campaign import Campaign
        from app.models.user import User
        from app.models.assignment import CampaignAssignment
        from app.models.post import Post
        from app.models.metric import Metric
        from sqlalchemy import select

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        now = datetime.now(timezone.utc)

        async with async_session() as session:
            company = Company(
                name="BillingCo2", email="billing-pause@test.com",
                password_hash="hash", balance=5000,
            )
            session.add(company)
            await session.flush()

            campaign = Campaign(
                company_id=company.id,
                title="Low Budget Pause Campaign",
                brief="Brief",
                budget_total=5.0,
                budget_remaining=5.0,
                payout_rules={"rate_per_1k_impressions": 0.50, "rate_per_like": 0.01,
                              "rate_per_repost": 0.05, "rate_per_click": 0.10},
                start_date=now - timedelta(days=7),
                end_date=now + timedelta(days=7),
                status="active",
                budget_exhaustion_action="auto_pause",
            )
            session.add(campaign)
            await session.flush()
            campaign_id = campaign.id

            user = User(email="billing-user-pause@test.com", password_hash="hash")
            session.add(user)
            await session.flush()

            assignment = CampaignAssignment(
                campaign_id=campaign.id, user_id=user.id,
                status="posted", content_mode="ai_generated", payout_multiplier=1.0,
            )
            session.add(assignment)
            await session.flush()

            post = Post(
                assignment_id=assignment.id, platform="x",
                post_url="https://x.com/test/456", content_hash="def",
                posted_at=now - timedelta(hours=73), status="live",
            )
            session.add(post)
            await session.flush()

            metric = Metric(
                post_id=post.id, impressions=10000, likes=100,
                reposts=20, clicks=50, scraped_at=now, is_final=True,
            )
            session.add(metric)
            await session.flush()
            await session.commit()

        async with async_session() as session:
            await run_billing_cycle(session)
            await session.commit()

        async with async_session() as session:
            result = await session.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            updated_campaign = result.scalar_one()
            assert updated_campaign.status == "paused"

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


# ===================================================================
# 80% Budget Alert
# ===================================================================

class TestBudgetAlert:

    @pytest.mark.asyncio
    async def test_alert_flag_set_when_80_percent_spent(self, _server_env):
        """budget_alert_sent is set to True when remaining < 20% of total."""
        from app.core.database import engine, async_session, Base
        import app.models  # noqa: F401
        from app.services.billing import run_billing_cycle
        from app.models.company import Company
        from app.models.campaign import Campaign
        from app.models.user import User
        from app.models.assignment import CampaignAssignment
        from app.models.post import Post
        from app.models.metric import Metric
        from sqlalchemy import select

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        now = datetime.now(timezone.utc)

        async with async_session() as session:
            company = Company(
                name="AlertCo", email="alert@test.com",
                password_hash="hash", balance=5000,
            )
            session.add(company)
            await session.flush()

            # Campaign with $20 budget. 80% = $16. After billing, if remaining < $4,
            # alert should fire.
            campaign = Campaign(
                company_id=company.id,
                title="Alert Campaign",
                brief="Brief",
                budget_total=20.0,
                budget_remaining=20.0,
                payout_rules={"rate_per_1k_impressions": 5.0, "rate_per_like": 0.0,
                              "rate_per_repost": 0.0, "rate_per_click": 0.0},
                start_date=now - timedelta(days=7),
                end_date=now + timedelta(days=7),
                status="active",
                budget_exhaustion_action="auto_complete",
                budget_alert_sent=False,
            )
            session.add(campaign)
            await session.flush()
            campaign_id = campaign.id

            user = User(email="alert-user@test.com", password_hash="hash")
            session.add(user)
            await session.flush()

            assignment = CampaignAssignment(
                campaign_id=campaign.id, user_id=user.id,
                status="posted", content_mode="ai_generated", payout_multiplier=1.0,
            )
            session.add(assignment)
            await session.flush()

            post = Post(
                assignment_id=assignment.id, platform="x",
                post_url="https://x.com/test/alert", content_hash="alert",
                posted_at=now - timedelta(hours=73), status="live",
            )
            session.add(post)
            await session.flush()

            # 3500 impressions * $5/1000 = $17.50 raw cost
            # Remaining after: $20 - $17.50 = $2.50, which is 12.5% of $20 (< 20%)
            metric = Metric(
                post_id=post.id, impressions=3500, likes=0,
                reposts=0, clicks=0, scraped_at=now, is_final=True,
            )
            session.add(metric)
            await session.flush()
            await session.commit()

        async with async_session() as session:
            await run_billing_cycle(session)
            await session.commit()

        async with async_session() as session:
            result = await session.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            updated_campaign = result.scalar_one()
            assert updated_campaign.budget_alert_sent is True

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_alert_flag_not_set_when_under_80_percent(self, _server_env):
        """budget_alert_sent stays False when less than 80% is spent."""
        from app.core.database import engine, async_session, Base
        import app.models  # noqa: F401
        from app.services.billing import run_billing_cycle
        from app.models.company import Company
        from app.models.campaign import Campaign
        from app.models.user import User
        from app.models.assignment import CampaignAssignment
        from app.models.post import Post
        from app.models.metric import Metric
        from sqlalchemy import select

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        now = datetime.now(timezone.utc)

        async with async_session() as session:
            company = Company(
                name="NoAlertCo", email="noalert@test.com",
                password_hash="hash", balance=5000,
            )
            session.add(company)
            await session.flush()

            # Campaign with $100 budget. 20% threshold = $20.
            campaign = Campaign(
                company_id=company.id,
                title="No Alert Campaign",
                brief="Brief",
                budget_total=100.0,
                budget_remaining=100.0,
                payout_rules={"rate_per_1k_impressions": 0.50, "rate_per_like": 0.0,
                              "rate_per_repost": 0.0, "rate_per_click": 0.0},
                start_date=now - timedelta(days=7),
                end_date=now + timedelta(days=7),
                status="active",
                budget_exhaustion_action="auto_complete",
                budget_alert_sent=False,
            )
            session.add(campaign)
            await session.flush()
            campaign_id = campaign.id

            user = User(email="noalert-user@test.com", password_hash="hash")
            session.add(user)
            await session.flush()

            assignment = CampaignAssignment(
                campaign_id=campaign.id, user_id=user.id,
                status="posted", content_mode="ai_generated", payout_multiplier=1.0,
            )
            session.add(assignment)
            await session.flush()

            post = Post(
                assignment_id=assignment.id, platform="x",
                post_url="https://x.com/test/noalert", content_hash="noalert",
                posted_at=now - timedelta(hours=73), status="live",
            )
            session.add(post)
            await session.flush()

            # 10000 impressions * $0.50/1000 = $5.00 raw cost
            # Remaining: $100 - $5 = $95, which is 95% (>> 20%)
            metric = Metric(
                post_id=post.id, impressions=10000, likes=0,
                reposts=0, clicks=0, scraped_at=now, is_final=True,
            )
            session.add(metric)
            await session.flush()
            await session.commit()

        async with async_session() as session:
            await run_billing_cycle(session)
            await session.commit()

        async with async_session() as session:
            result = await session.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            updated_campaign = result.scalar_one()
            assert updated_campaign.budget_alert_sent is False

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest.mark.asyncio
    async def test_alert_included_in_campaign_response(
        self, client, company_token, seed_data
    ):
        """budget_alert_sent is included in campaign detail API response."""
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "budget_alert_sent" in data
        assert data["budget_alert_sent"] is False


# ===================================================================
# Minimum $50 Budget
# ===================================================================

class TestMinimumBudget:

    @pytest.mark.asyncio
    async def test_create_campaign_below_50_fails(
        self, client, company_token
    ):
        """Creating a campaign with budget < $50 returns 400."""
        resp = await client.post(
            "/api/company/campaigns",
            headers={"Authorization": f"Bearer {company_token}"},
            json={
                "title": "Cheap Campaign",
                "brief": "Too cheap",
                "budget_total": 25.0,
                "payout_rules": {
                    "rate_per_1k_impressions": 0.50,
                    "rate_per_like": 0.01,
                    "rate_per_repost": 0.05,
                    "rate_per_click": 0.10,
                },
                "start_date": "2026-04-01T00:00:00Z",
                "end_date": "2026-04-30T00:00:00Z",
            },
        )
        assert resp.status_code == 400
        assert "50" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_campaign_at_50_succeeds(
        self, client, company_token
    ):
        """Creating a campaign with exactly $50 budget succeeds."""
        resp = await client.post(
            "/api/company/campaigns",
            headers={"Authorization": f"Bearer {company_token}"},
            json={
                "title": "Minimum Campaign",
                "brief": "Just enough",
                "budget_total": 50.0,
                "payout_rules": {
                    "rate_per_1k_impressions": 0.50,
                    "rate_per_like": 0.01,
                    "rate_per_repost": 0.05,
                    "rate_per_click": 0.10,
                },
                "start_date": "2026-04-01T00:00:00Z",
                "end_date": "2026-04-30T00:00:00Z",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["budget_total"] == 50.0


# ===================================================================
# Edit Increments Version
# ===================================================================

class TestEditVersion:

    @pytest.mark.asyncio
    async def test_edit_increments_campaign_version(
        self, client, company_token, seed_data
    ):
        """Editing campaign content increments campaign_version."""
        # First get current version
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        initial_version = resp.json()["campaign_version"]

        # Edit the campaign
        resp = await client.patch(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
            json={"title": "Updated Title"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["campaign_version"] == initial_version + 1
        assert data["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_status_only_change_does_not_increment_version(
        self, client, company_token, seed_data
    ):
        """Changing only status (not content) does NOT increment version."""
        # Get current version
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        initial_version = resp.json()["campaign_version"]

        # Change status only (draft -> active)
        resp = await client.patch(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
            json={"status": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["campaign_version"] == initial_version

    @pytest.mark.asyncio
    async def test_version_in_campaign_list(
        self, client, company_token, seed_data
    ):
        """campaign_version appears in campaign list response."""
        resp = await client.get(
            "/api/company/campaigns",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert "campaign_version" in data[0]

    @pytest.mark.asyncio
    async def test_multiple_edits_increment_version_correctly(
        self, client, company_token, seed_data
    ):
        """Multiple edits increment version each time."""
        # Edit 1
        resp = await client.patch(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
            json={"title": "Edit 1"},
        )
        v1 = resp.json()["campaign_version"]

        # Edit 2
        resp = await client.patch(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
            json={"brief": "Edit 2"},
        )
        v2 = resp.json()["campaign_version"]

        assert v2 == v1 + 1
