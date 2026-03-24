"""Tests for earnings v2: real earnings endpoint + payout withdrawal.

Covers:
- Earnings returns real total_earned and current_balance from user model
- Pending calculation from non-final metrics
- Per-campaign breakdown aggregation from payouts
- Per-platform breakdown from payout data
- Payout history (withdrawal records)
- Payout creation with full balance
- Payout creation with partial amount
- Payout fails below $10
- Payout fails with insufficient balance
- Payout deducts from earnings_balance
- Payout fails for suspended user
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

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


def _make_token(user_id: int) -> str:
    """Create a JWT for the given user_id."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(user_id), "type": "user"})


async def _create_user(session, *, email="user@test.com", earnings_balance=0.0,
                        total_earned=0.0, status="active"):
    """Create a user with specified balance/earnings."""
    from app.models.user import User
    user = User(
        email=email,
        password_hash="hash",
        earnings_balance=earnings_balance,
        total_earned=total_earned,
        status=status,
    )
    session.add(user)
    await session.flush()
    return user


async def _create_company(session, *, name="Test Co", email="co@test.com"):
    from app.models.company import Company
    company = Company(name=name, email=email, password_hash="hash", balance=5000)
    session.add(company)
    await session.flush()
    return company


async def _create_campaign(session, company_id, *, title="Test Campaign",
                            budget=1000.0, payout_rules=None):
    from app.models.campaign import Campaign
    now = datetime.now(timezone.utc)
    campaign = Campaign(
        company_id=company_id,
        title=title,
        brief="Test brief",
        budget_total=budget,
        budget_remaining=budget,
        payout_rules=payout_rules or {
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
    return campaign


async def _create_assignment(session, campaign_id, user_id, *, status="posted"):
    from app.models.assignment import CampaignAssignment
    assignment = CampaignAssignment(
        campaign_id=campaign_id,
        user_id=user_id,
        status=status,
        content_mode="ai_generated",
    )
    session.add(assignment)
    await session.flush()
    return assignment


async def _create_post(session, assignment_id, *, platform="x",
                        status="live", posted_at=None):
    from app.models.post import Post
    post = Post(
        assignment_id=assignment_id,
        platform=platform,
        post_url=f"https://{platform}.com/test/123",
        content_hash="abc123",
        posted_at=posted_at or datetime.now(timezone.utc) - timedelta(hours=73),
        status=status,
    )
    session.add(post)
    await session.flush()
    return post


async def _create_metric(session, post_id, *, impressions=0, likes=0,
                           reposts=0, clicks=0, comments=0, is_final=True):
    from app.models.metric import Metric
    metric = Metric(
        post_id=post_id,
        impressions=impressions,
        likes=likes,
        reposts=reposts,
        comments=comments,
        clicks=clicks,
        scraped_at=datetime.now(timezone.utc),
        is_final=is_final,
    )
    session.add(metric)
    await session.flush()
    return metric


async def _create_payout(session, user_id, *, campaign_id=None, amount=10.0,
                           status="pending", breakdown=None):
    from app.models.payout import Payout
    now = datetime.now(timezone.utc)
    payout = Payout(
        user_id=user_id,
        campaign_id=campaign_id,
        amount=amount,
        period_start=now - timedelta(days=1),
        period_end=now,
        status=status,
        breakdown=breakdown or {},
    )
    session.add(payout)
    await session.flush()
    return payout


@pytest_asyncio.fixture
async def client(_async_db):
    """AsyncClient hitting the real FastAPI app with in-memory DB."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ===================================================================
# Test: GET /api/users/me/earnings — real total_earned and balance
# ===================================================================

@pytest.mark.asyncio
class TestEarningsBasic:

    async def test_returns_real_total_earned_and_balance(self, _async_db, client):
        """total_earned and current_balance come from user model, not hardcoded."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(
                session, earnings_balance=45.00, total_earned=75.98,
            )
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_earned"] == 75.98
        assert data["current_balance"] == 45.00

    async def test_new_user_has_zero_earnings(self, _async_db, client):
        """Brand new user with no activity has all zeros."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session)
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_earned"] == 0.0
        assert data["current_balance"] == 0.0
        assert data["pending"] == 0.0
        assert data["per_campaign"] == []
        assert data["per_platform"] == {}


# ===================================================================
# Test: Pending calculation from non-final metrics
# ===================================================================

@pytest.mark.asyncio
class TestPendingEarnings:

    async def test_pending_from_non_final_metrics(self, _async_db, client):
        """Pending = estimated earnings from metrics where is_final=False."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session, total_earned=0.0, earnings_balance=0.0)
            company = await _create_company(session)
            campaign = await _create_campaign(session, company.id)
            assignment = await _create_assignment(session, campaign.id, user.id)
            post = await _create_post(session, assignment.id, platform="x")
            # Non-final metric: 10k impressions, 100 likes, 20 reposts, 50 clicks
            await _create_metric(
                session, post.id,
                impressions=10000, likes=100, reposts=20, clicks=50,
                is_final=False,
            )
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # raw = (10000/1000 * 0.50) + (100 * 0.01) + (20 * 0.05) + (50 * 0.10)
        #     = 5.00 + 1.00 + 1.00 + 5.00 = 12.00
        # user_earning = 12.00 * 0.80 = 9.60
        assert data["pending"] == pytest.approx(9.60)

    async def test_pending_excludes_final_metrics(self, _async_db, client):
        """Final metrics are NOT included in pending (they're already billed)."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            campaign = await _create_campaign(session, company.id)
            assignment = await _create_assignment(session, campaign.id, user.id)
            post = await _create_post(session, assignment.id)
            # Final metric — should NOT count as pending
            await _create_metric(
                session, post.id,
                impressions=10000, likes=100, reposts=20, clicks=50,
                is_final=True,
            )
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending"] == 0.0

    async def test_pending_sums_across_multiple_posts(self, _async_db, client):
        """Pending aggregates across all non-final metrics for the user."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session)
            company = await _create_company(session)
            campaign = await _create_campaign(session, company.id)
            assignment = await _create_assignment(session, campaign.id, user.id)
            # Post 1: non-final metric
            post1 = await _create_post(session, assignment.id, platform="x")
            await _create_metric(
                session, post1.id,
                impressions=10000, likes=0, reposts=0, clicks=0,
                is_final=False,
            )
            # Post 2: non-final metric
            post2 = await _create_post(session, assignment.id, platform="linkedin")
            await _create_metric(
                session, post2.id,
                impressions=10000, likes=0, reposts=0, clicks=0,
                is_final=False,
            )
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Each post: raw = 5.00, user = 4.00. Two posts = 8.00
        assert data["pending"] == pytest.approx(8.00)


# ===================================================================
# Test: Per-campaign breakdown aggregation
# ===================================================================

@pytest.mark.asyncio
class TestPerCampaignBreakdown:

    async def test_per_campaign_from_payouts(self, _async_db, client):
        """per_campaign groups payout records by campaign with totals."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session, total_earned=20.0, earnings_balance=20.0)
            company = await _create_company(session)
            campaign = await _create_campaign(session, company.id, title="Trading Tools Launch")
            assignment = await _create_assignment(session, campaign.id, user.id, status="paid")

            # Create two posts with payouts for this campaign
            post1 = await _create_post(session, assignment.id, platform="x")
            post2 = await _create_post(session, assignment.id, platform="linkedin")

            await _create_payout(session, user.id, campaign_id=campaign.id, amount=12.00,
                                  status="paid", breakdown={
                                      "metric_id": 1, "post_id": post1.id, "platform": "x",
                                      "impressions": 5000, "likes": 100, "reposts": 10, "clicks": 20,
                                  })
            await _create_payout(session, user.id, campaign_id=campaign.id, amount=8.00,
                                  status="paid", breakdown={
                                      "metric_id": 2, "post_id": post2.id, "platform": "linkedin",
                                      "impressions": 3000, "likes": 50, "reposts": 5, "clicks": 10,
                                  })
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["per_campaign"]) == 1
        camp = data["per_campaign"][0]
        assert camp["campaign_id"] == campaign.id
        assert camp["campaign_title"] == "Trading Tools Launch"
        assert camp["posts"] == 2
        assert camp["impressions"] == 8000  # 5000 + 3000
        assert camp["engagement"] == 195   # (100+50) + (10+5) + (20+10)
        assert camp["earned"] == pytest.approx(20.00)
        assert camp["status"] == "paid"

    async def test_per_campaign_multiple_campaigns(self, _async_db, client):
        """Multiple campaigns each get their own breakdown entry."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session, total_earned=15.0, earnings_balance=15.0)
            company = await _create_company(session)

            camp1 = await _create_campaign(session, company.id, title="Campaign A")
            camp2 = await _create_campaign(session, company.id, title="Campaign B")

            assign1 = await _create_assignment(session, camp1.id, user.id, status="paid")
            assign2 = await _create_assignment(session, camp2.id, user.id, status="posted")

            post1 = await _create_post(session, assign1.id, platform="x")
            post2 = await _create_post(session, assign2.id, platform="reddit")

            await _create_payout(session, user.id, campaign_id=camp1.id, amount=10.0,
                                  status="paid", breakdown={
                                      "metric_id": 1, "post_id": post1.id, "platform": "x",
                                      "impressions": 2000, "likes": 50, "reposts": 5, "clicks": 10,
                                  })
            await _create_payout(session, user.id, campaign_id=camp2.id, amount=5.0,
                                  status="pending", breakdown={
                                      "metric_id": 2, "post_id": post2.id, "platform": "reddit",
                                      "impressions": 1000, "likes": 20, "reposts": 2, "clicks": 5,
                                  })
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["per_campaign"]) == 2
        titles = {c["campaign_title"] for c in data["per_campaign"]}
        assert titles == {"Campaign A", "Campaign B"}


# ===================================================================
# Test: Per-platform breakdown from payout data
# ===================================================================

@pytest.mark.asyncio
class TestPerPlatformBreakdown:

    async def test_per_platform_from_payout_breakdown(self, _async_db, client):
        """per_platform sums earned per platform from payout breakdown JSON."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session, total_earned=30.0, earnings_balance=30.0)
            company = await _create_company(session)
            campaign = await _create_campaign(session, company.id)
            assignment = await _create_assignment(session, campaign.id, user.id)

            post1 = await _create_post(session, assignment.id, platform="x")
            post2 = await _create_post(session, assignment.id, platform="linkedin")
            post3 = await _create_post(session, assignment.id, platform="x")

            await _create_payout(session, user.id, campaign_id=campaign.id, amount=10.0,
                                  status="paid", breakdown={"platform": "x"})
            await _create_payout(session, user.id, campaign_id=campaign.id, amount=12.0,
                                  status="paid", breakdown={"platform": "linkedin"})
            await _create_payout(session, user.id, campaign_id=campaign.id, amount=8.0,
                                  status="paid", breakdown={"platform": "x"})
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["per_platform"]["x"] == pytest.approx(18.0)
        assert data["per_platform"]["linkedin"] == pytest.approx(12.0)

    async def test_per_platform_excludes_withdrawal_payouts(self, _async_db, client):
        """Withdrawal payouts (no platform in breakdown) don't appear in per_platform."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session, total_earned=10.0, earnings_balance=0.0)
            company = await _create_company(session)
            campaign = await _create_campaign(session, company.id)
            assignment = await _create_assignment(session, campaign.id, user.id)

            await _create_payout(session, user.id, campaign_id=campaign.id, amount=10.0,
                                  status="paid", breakdown={"platform": "x"})
            # Withdrawal payout — no platform
            await _create_payout(session, user.id, campaign_id=None, amount=10.0,
                                  status="pending", breakdown={"withdrawal": True})
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Only the campaign payout counted
        assert data["per_platform"] == {"x": pytest.approx(10.0)}


# ===================================================================
# Test: Payout history (withdrawal records)
# ===================================================================

@pytest.mark.asyncio
class TestPayoutHistory:

    async def test_payout_history_shows_withdrawals(self, _async_db, client):
        """payout_history includes withdrawal records (breakdown.withdrawal=true)."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session, total_earned=50.0, earnings_balance=0.0)
            # Create a withdrawal payout
            await _create_payout(session, user.id, campaign_id=None, amount=50.0,
                                  status="paid", breakdown={"withdrawal": True})
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["payout_history"]) == 1
        assert data["payout_history"][0]["amount"] == 50.0
        assert data["payout_history"][0]["status"] == "paid"

    async def test_payout_history_excludes_campaign_payouts(self, _async_db, client):
        """Campaign-linked billing payouts don't show in payout_history."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session, total_earned=10.0, earnings_balance=10.0)
            company = await _create_company(session)
            campaign = await _create_campaign(session, company.id)
            # Campaign payout (billing) — not a withdrawal
            await _create_payout(session, user.id, campaign_id=campaign.id, amount=10.0,
                                  status="paid", breakdown={"platform": "x"})
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["payout_history"] == []


# ===================================================================
# Test: POST /api/users/me/payout — creation
# ===================================================================

@pytest.mark.asyncio
class TestPayoutCreation:

    async def test_payout_full_balance(self, _async_db, client):
        """Withdraw full balance when amount equals balance."""
        from app.core.database import async_session
        from app.models.user import User
        from sqlalchemy import select

        async with async_session() as session:
            user = await _create_user(session, earnings_balance=50.0, total_earned=50.0)
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.post(
            "/api/users/me/payout",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 50.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["amount"] == 50.0
        assert data["new_balance"] == 0.0
        assert "payout_id" in data

        # Verify DB
        async with async_session() as session:
            u = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
            assert float(u.earnings_balance) == 0.0

    async def test_payout_partial_amount(self, _async_db, client):
        """Withdraw partial amount, remainder stays in balance."""
        from app.core.database import async_session
        from app.models.user import User
        from sqlalchemy import select

        async with async_session() as session:
            user = await _create_user(session, earnings_balance=100.0, total_earned=100.0)
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.post(
            "/api/users/me/payout",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 30.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["amount"] == 30.0
        assert data["new_balance"] == pytest.approx(70.0)

        # Verify DB
        async with async_session() as session:
            u = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
            assert float(u.earnings_balance) == pytest.approx(70.0)

    async def test_payout_creates_payout_record(self, _async_db, client):
        """Payout creates a Payout record with withdrawal=True in breakdown."""
        from app.core.database import async_session
        from app.models.payout import Payout
        from sqlalchemy import select

        async with async_session() as session:
            user = await _create_user(session, earnings_balance=25.0, total_earned=25.0)
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.post(
            "/api/users/me/payout",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 25.0},
        )
        assert resp.status_code == 200
        payout_id = resp.json()["payout_id"]

        async with async_session() as session:
            payout = (await session.execute(
                select(Payout).where(Payout.id == payout_id)
            )).scalar_one()
            assert payout.user_id == user_id
            assert payout.campaign_id is None
            assert float(payout.amount) == 25.0
            assert payout.status == "pending"
            assert payout.breakdown.get("withdrawal") is True


# ===================================================================
# Test: POST /api/users/me/payout — validation failures
# ===================================================================

@pytest.mark.asyncio
class TestPayoutValidation:

    async def test_payout_fails_below_10_minimum(self, _async_db, client):
        """Amount below $10 minimum returns 400."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session, earnings_balance=50.0, total_earned=50.0)
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.post(
            "/api/users/me/payout",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 5.0},
        )
        assert resp.status_code == 400
        assert "Minimum withdrawal is $10.00" in resp.json()["detail"]

    async def test_payout_fails_insufficient_balance(self, _async_db, client):
        """Amount > balance returns 400."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session, earnings_balance=15.0, total_earned=15.0)
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.post(
            "/api/users/me/payout",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 20.0},
        )
        assert resp.status_code == 400
        assert "Insufficient balance" in resp.json()["detail"]

    async def test_payout_fails_balance_below_minimum(self, _async_db, client):
        """Balance < $10 can't withdraw anything."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(session, earnings_balance=5.0, total_earned=5.0)
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.post(
            "/api/users/me/payout",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 5.0},
        )
        assert resp.status_code == 400

    async def test_payout_fails_suspended_user(self, _async_db, client):
        """Suspended user gets 403 from get_current_user dependency."""
        from app.core.database import async_session

        async with async_session() as session:
            user = await _create_user(
                session, earnings_balance=50.0, total_earned=50.0, status="suspended",
            )
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        resp = await client.post(
            "/api/users/me/payout",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 25.0},
        )
        assert resp.status_code == 403

    async def test_payout_deducts_from_earnings_balance(self, _async_db, client):
        """After payout, earnings_balance is decremented in DB."""
        from app.core.database import async_session
        from app.models.user import User
        from sqlalchemy import select

        async with async_session() as session:
            user = await _create_user(session, earnings_balance=100.0, total_earned=100.0)
            await session.commit()
            user_id = user.id

        token = _make_token(user_id)
        await client.post(
            "/api/users/me/payout",
            headers={"Authorization": f"Bearer {token}"},
            json={"amount": 40.0},
        )

        async with async_session() as session:
            u = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
            assert float(u.earnings_balance) == pytest.approx(60.0)
            # total_earned should NOT change on withdrawal
            assert float(u.total_earned) == pytest.approx(100.0)
