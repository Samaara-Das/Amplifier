"""Tests for billing v2: payout_multiplier removed from earnings calculation.

Covers:
- Earnings calculated WITHOUT multiplier (raw_earning * (1 - platform_cut))
- Same engagement = same earnings regardless of user mode
- Platform cut (20%) still applied correctly
- Backward compat: old assignments with multiplier != 1.0 are ignored in billing
- Full billing cycle with final metrics
- Payout breakdown does NOT include multiplier key
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

# ── Path setup ────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def _server_env(monkeypatch):
    """Point server to an in-memory SQLite DB for testing."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    from app.core import config
    config.get_settings.cache_clear()


@pytest_asyncio.fixture
async def _async_db(_server_env):
    """Create and tear down all tables in-memory for async tests."""
    from app.core.database import engine, Base
    import app.models  # noqa: F401 — register all models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _create_test_data(session, *, payout_multiplier=1.0, user_mode="full_auto",
                            budget=1000.0, impressions=10000, likes=100,
                            reposts=20, clicks=50):
    """Helper: create company, campaign, user, assignment, post, and final metric.

    Returns (campaign, assignment, post, metric, user).
    """
    from app.models.company import Company
    from app.models.campaign import Campaign
    from app.models.assignment import CampaignAssignment
    from app.models.user import User
    from app.models.post import Post
    from app.models.metric import Metric

    company = Company(
        name="Test Co", email=f"test-{id(session)}@co.com",
        password_hash="hash", balance=5000,
    )
    session.add(company)
    await session.flush()

    now = datetime.now(timezone.utc)
    campaign = Campaign(
        company_id=company.id,
        title="Test Campaign",
        brief="Test brief",
        budget_total=budget,
        budget_remaining=budget,
        payout_rules={
            "rate_per_1k_impressions": 0.50,
            "rate_per_like": 0.01,
            "rate_per_repost": 0.05,
            "rate_per_click": 0.10,
        },
        start_date=now - timedelta(days=7),
        end_date=now + timedelta(days=7),
        status="active",
    )
    session.add(campaign)
    await session.flush()

    user = User(
        email=f"user-{id(session)}@test.com",
        password_hash="hash",
        mode=user_mode,
    )
    session.add(user)
    await session.flush()

    assignment = CampaignAssignment(
        campaign_id=campaign.id,
        user_id=user.id,
        status="posted",
        content_mode="ai_generated",
        payout_multiplier=payout_multiplier,
    )
    session.add(assignment)
    await session.flush()

    post = Post(
        assignment_id=assignment.id,
        platform="x",
        post_url="https://x.com/test/status/123",
        content_hash="abc123",
        posted_at=now - timedelta(hours=73),
        status="live",
    )
    session.add(post)
    await session.flush()

    metric = Metric(
        post_id=post.id,
        impressions=impressions,
        likes=likes,
        reposts=reposts,
        clicks=clicks,
        scraped_at=now,
        is_final=True,
    )
    session.add(metric)
    await session.flush()

    return campaign, assignment, post, metric, user


# ===================================================================
# Test: Earnings calculated WITHOUT multiplier
# ===================================================================

@pytest.mark.asyncio
class TestBillingWithoutMultiplier:

    async def test_earnings_ignore_multiplier(self, _async_db):
        """Earnings = raw_earning * (1 - platform_cut). Multiplier NOT applied."""
        from app.core.database import async_session
        from app.services.billing import calculate_post_earnings

        async with async_session() as session:
            campaign, assignment, post, metric, user = await _create_test_data(
                session,
                payout_multiplier=2.0,  # old multiplier value — should be ignored
                impressions=10000,
                likes=100,
                reposts=20,
                clicks=50,
            )

            earning = await calculate_post_earnings(post, metric, assignment, campaign)

            # raw = (10000/1000 * 0.50) + (100 * 0.01) + (20 * 0.05) + (50 * 0.10)
            #     = 5.00 + 1.00 + 1.00 + 5.00 = 12.00
            # user_earning = 12.00 * 0.80 = 9.60
            # WITHOUT multiplier — even though assignment has 2.0
            assert earning == 9.60

    async def test_earnings_with_default_multiplier(self, _async_db):
        """New assignments (multiplier=1.0) produce same result as ignoring multiplier."""
        from app.core.database import async_session
        from app.services.billing import calculate_post_earnings

        async with async_session() as session:
            campaign, assignment, post, metric, user = await _create_test_data(
                session,
                payout_multiplier=1.0,
                impressions=10000,
                likes=100,
                reposts=20,
                clicks=50,
            )

            earning = await calculate_post_earnings(post, metric, assignment, campaign)
            assert earning == 9.60


# ===================================================================
# Test: Same engagement = same earnings regardless of user mode
# ===================================================================

@pytest.mark.asyncio
class TestEarningsEqualAcrossModes:

    async def test_full_auto_and_manual_earn_same(self, _async_db):
        """full_auto and manual users with same engagement earn identically."""
        from app.core.database import async_session
        from app.services.billing import calculate_post_earnings

        async with async_session() as session:
            # full_auto user (old multiplier would have been 1.5)
            campaign1, assign1, post1, metric1, _ = await _create_test_data(
                session,
                payout_multiplier=1.5,
                user_mode="full_auto",
                impressions=5000,
                likes=200,
                reposts=10,
                clicks=30,
            )

        async with async_session() as session:
            # manual user (old multiplier would have been 2.0)
            campaign2, assign2, post2, metric2, _ = await _create_test_data(
                session,
                payout_multiplier=2.0,
                user_mode="manual",
                impressions=5000,
                likes=200,
                reposts=10,
                clicks=30,
            )

        # Both should earn the same
        from app.services.billing import calculate_post_earnings
        earning1 = await calculate_post_earnings(post1, metric1, assign1, campaign1)
        earning2 = await calculate_post_earnings(post2, metric2, assign2, campaign2)

        assert earning1 == earning2
        # raw = (5000/1000 * 0.50) + (200 * 0.01) + (10 * 0.05) + (30 * 0.10)
        #     = 2.50 + 2.00 + 0.50 + 3.00 = 8.00
        # user_earning = 8.00 * 0.80 = 6.40
        assert earning1 == 6.40


# ===================================================================
# Test: Platform cut (20%) still applied correctly
# ===================================================================

@pytest.mark.asyncio
class TestPlatformCut:

    async def test_20_percent_cut_applied(self, _async_db):
        """Platform keeps 20%, user gets 80% of raw earnings."""
        from app.core.database import async_session
        from app.services.billing import calculate_post_earnings

        async with async_session() as session:
            campaign, assignment, post, metric, user = await _create_test_data(
                session,
                impressions=20000,  # 20000/1000 * 0.50 = 10.00
                likes=0,
                reposts=0,
                clicks=0,
            )

            earning = await calculate_post_earnings(post, metric, assignment, campaign)

            # raw = 10.00, platform cut = 20%, user gets 80% = 8.00
            assert earning == 8.00

    async def test_zero_engagement_zero_earning(self, _async_db):
        """No engagement = no earnings."""
        from app.core.database import async_session
        from app.services.billing import calculate_post_earnings

        async with async_session() as session:
            campaign, assignment, post, metric, user = await _create_test_data(
                session,
                impressions=0,
                likes=0,
                reposts=0,
                clicks=0,
            )

            earning = await calculate_post_earnings(post, metric, assignment, campaign)
            assert earning == 0.0


# ===================================================================
# Test: Backward compat — old assignments with multiplier != 1.0
# ===================================================================

@pytest.mark.asyncio
class TestBackwardCompat:

    async def test_old_assignment_multiplier_1_5_ignored(self, _async_db):
        """Assignment with old 1.5x multiplier earns same as 1.0x."""
        from app.core.database import async_session
        from app.services.billing import calculate_post_earnings

        async with async_session() as session:
            campaign, assignment, post, metric, user = await _create_test_data(
                session,
                payout_multiplier=1.5,
                impressions=10000,
                likes=0,
                reposts=0,
                clicks=0,
            )

            earning = await calculate_post_earnings(post, metric, assignment, campaign)
            # raw = 5.00, user = 5.00 * 0.80 = 4.00 (NOT 5.00 * 1.5 * 0.80 = 6.00)
            assert earning == 4.00

    async def test_old_assignment_multiplier_2_0_ignored(self, _async_db):
        """Assignment with old 2.0x multiplier earns same as 1.0x."""
        from app.core.database import async_session
        from app.services.billing import calculate_post_earnings

        async with async_session() as session:
            campaign, assignment, post, metric, user = await _create_test_data(
                session,
                payout_multiplier=2.0,
                impressions=10000,
                likes=0,
                reposts=0,
                clicks=0,
            )

            earning = await calculate_post_earnings(post, metric, assignment, campaign)
            # raw = 5.00, user = 5.00 * 0.80 = 4.00 (NOT 5.00 * 2.0 * 0.80 = 8.00)
            assert earning == 4.00


# ===================================================================
# Test: Full billing cycle with final metrics
# ===================================================================

@pytest.mark.asyncio
class TestFullBillingCycle:

    async def test_billing_cycle_credits_user_without_multiplier(self, _async_db):
        """Full billing cycle: final metric triggers billing, user gets credited correctly."""
        from app.core.database import async_session
        from app.services.billing import run_billing_cycle
        from app.models.user import User
        from app.models.payout import Payout
        from sqlalchemy import select

        async with async_session() as session:
            campaign, assignment, post, metric, user = await _create_test_data(
                session,
                payout_multiplier=1.5,  # legacy multiplier — should be ignored
                impressions=10000,
                likes=100,
                reposts=20,
                clicks=50,
            )
            await session.commit()

        async with async_session() as session:
            result = await run_billing_cycle(session)
            await session.commit()

        assert result["posts_processed"] == 1
        # raw = 12.00, user = 12.00 * 0.80 = 9.60
        assert result["total_earned"] == 9.60

        # Verify user balance updated
        async with async_session() as session:
            u = (await session.execute(select(User))).scalar_one()
            assert float(u.earnings_balance) == 9.60
            assert float(u.total_earned) == 9.60

    async def test_billing_cycle_payout_breakdown_no_multiplier(self, _async_db):
        """Payout breakdown should NOT include 'multiplier' key."""
        from app.core.database import async_session
        from app.services.billing import run_billing_cycle
        from app.models.payout import Payout
        from sqlalchemy import select

        async with async_session() as session:
            await _create_test_data(
                session,
                payout_multiplier=2.0,
                impressions=10000,
                likes=100,
                reposts=20,
                clicks=50,
            )
            await session.commit()

        async with async_session() as session:
            await run_billing_cycle(session)
            await session.commit()

        async with async_session() as session:
            payout = (await session.execute(select(Payout))).scalar_one()
            breakdown = payout.breakdown

            assert "multiplier" not in breakdown
            assert "platform_cut_pct" in breakdown
            assert "metric_id" in breakdown
            assert "post_id" in breakdown

    async def test_billing_cycle_deducts_budget_correctly(self, _async_db):
        """Campaign budget deducted = gross cost (user_earning / 0.80)."""
        from app.core.database import async_session
        from app.services.billing import run_billing_cycle
        from app.models.campaign import Campaign
        from sqlalchemy import select

        async with async_session() as session:
            await _create_test_data(
                session,
                budget=1000.0,
                impressions=10000,
                likes=100,
                reposts=20,
                clicks=50,
            )
            await session.commit()

        async with async_session() as session:
            result = await run_billing_cycle(session)
            await session.commit()

        # raw = 12.00, user = 9.60, budget_cost = 12.00
        assert result["total_budget_deducted"] == pytest.approx(12.00)

        async with async_session() as session:
            c = (await session.execute(select(Campaign))).scalar_one()
            assert float(c.budget_remaining) == pytest.approx(988.00)

    async def test_billing_cycle_skips_already_billed(self, _async_db):
        """Running billing twice doesn't double-count."""
        from app.core.database import async_session
        from app.services.billing import run_billing_cycle

        async with async_session() as session:
            await _create_test_data(session, impressions=10000)
            await session.commit()

        async with async_session() as session:
            result1 = await run_billing_cycle(session)
            await session.commit()

        async with async_session() as session:
            result2 = await run_billing_cycle(session)
            await session.commit()

        assert result1["posts_processed"] == 1
        assert result2["posts_processed"] == 0

    async def test_billing_cycle_caps_to_remaining_budget(self, _async_db):
        """Earning capped when campaign budget is almost exhausted."""
        from app.core.database import async_session
        from app.services.billing import run_billing_cycle
        from app.models.user import User
        from sqlalchemy import select

        async with async_session() as session:
            await _create_test_data(
                session,
                budget=5.00,  # Only $5 left — less than $12 raw cost
                impressions=10000,
                likes=100,
                reposts=20,
                clicks=50,
            )
            await session.commit()

        async with async_session() as session:
            result = await run_billing_cycle(session)
            await session.commit()

        # Budget is $5.00, user gets 80% = $4.00
        assert result["total_earned"] == 4.00
        assert result["total_budget_deducted"] == 5.00
