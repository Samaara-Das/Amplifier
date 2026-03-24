"""End-to-end integration tests for the full Amplifier cycle.

Tests the complete user journey through API calls:
  Company creates campaign -> User onboards -> Invitation -> Accept/Reject ->
  Posting -> Metrics -> Billing -> Earnings -> Payout -> Company results

All tests use FastAPI test client (httpx AsyncClient + ASGITransport) with
in-memory SQLite. Each test class gets a fresh database.
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


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _server_env(monkeypatch):
    """Point server at in-memory SQLite for every test."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    from app.core import config
    config.get_settings.cache_clear()


@pytest_asyncio.fixture
async def db():
    """Create all tables, yield a session, then tear down."""
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
async def client():
    """Async HTTP test client bound to the FastAPI app."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Helpers ───────────────────────────────────────────────────────

NOW = datetime.now(timezone.utc)


def _campaign_payload(**overrides) -> dict:
    """Build a valid campaign creation payload."""
    base = {
        "title": "AI Trading Indicator Launch",
        "brief": "Promote our new AI-powered trading indicator for retail traders.",
        "budget_total": 200.0,
        "payout_rules": {
            "rate_per_1k_impressions": 0.50,
            "rate_per_like": 0.01,
            "rate_per_repost": 0.05,
            "rate_per_click": 0.10,
        },
        "targeting": {
            "min_followers": {},
            "niche_tags": ["finance"],
            "required_platforms": ["x"],
            "target_regions": ["us"],
        },
        "content_guidance": "Target beginner traders. Emphasize ease of use.",
        "start_date": NOW.isoformat(),
        "end_date": (NOW + timedelta(days=30)).isoformat(),
    }
    base.update(overrides)
    return base


async def _register_company(client: AsyncClient) -> tuple[str, dict]:
    """Register a company and return (token, response_json)."""
    resp = await client.post("/api/auth/company/register", json={
        "name": "TestCorp",
        "email": "corp@test.com",
        "password": "pass1234",
    })
    assert resp.status_code == 200, f"Company register failed: {resp.text}"
    data = resp.json()
    return data["access_token"], data


async def _register_user(client: AsyncClient, email: str = "user@test.com") -> tuple[str, dict]:
    """Register a user and return (token, response_json)."""
    resp = await client.post("/api/auth/register", json={
        "email": email,
        "password": "pass1234",
    })
    assert resp.status_code == 200, f"User register failed: {resp.text}"
    data = resp.json()
    return data["access_token"], data


async def _update_user_profile(client: AsyncClient, token: str) -> dict:
    """Update user profile with platform/niche/region data for matching."""
    resp = await client.patch("/api/users/me", json={
        "platforms": {"x": {"connected": True, "username": "@testuser"}},
        "follower_counts": {"x": 5000},
        "niche_tags": ["finance", "tech"],
        "audience_region": "us",
        "mode": "semi_auto",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"Profile update failed: {resp.text}"
    return resp.json()


async def _topup_company_balance(db, company_id: int, amount: float):
    """Directly set company balance via DB (simulates Stripe top-up)."""
    from app.models.company import Company
    from sqlalchemy import select
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one()
    company.balance = float(company.balance) + amount
    await db.flush()
    await db.commit()


async def _get_company_id_from_token(token: str) -> int:
    """Decode the JWT to extract company_id."""
    from app.core.security import decode_token
    payload = decode_token(token)
    return int(payload["sub"])


async def _get_user_id_from_token(token: str) -> int:
    """Decode the JWT to extract user_id."""
    from app.core.security import decode_token
    payload = decode_token(token)
    return int(payload["sub"])


# ══════════════════════════════════════════════════════════════════
# 1. Company creates campaign
# ══════════════════════════════════════════════════════════════════


class TestCompanyCreatesCampaign:

    @pytest.mark.asyncio
    async def test_full_campaign_creation_flow(self, client, db):
        # Register company
        company_token, _ = await _register_company(client)

        # Top up balance so we can afford campaigns
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        # Create campaign — should be in draft status with approved screening
        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        campaign = resp.json()
        assert campaign["status"] == "draft"
        assert campaign["screening_status"] == "approved"
        assert campaign["budget_total"] == 200.0
        assert campaign["budget_remaining"] == 200.0
        campaign_id = campaign["id"]

        # Activate campaign
        resp2 = await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_clean_campaign_screening_passes(self, client, db):
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["screening_status"] == "approved"


# ══════════════════════════════════════════════════════════════════
# 2. User onboards and gets invitation
# ══════════════════════════════════════════════════════════════════


class TestUserOnboardsAndGetsInvitation:

    @pytest.mark.asyncio
    async def test_user_registration_and_profile_update(self, client, db):
        user_token, _ = await _register_user(client)

        # Update profile
        profile = await _update_user_profile(client, user_token)
        assert profile["platforms"]["x"]["connected"] is True
        assert profile["follower_counts"]["x"] == 5000
        assert "finance" in profile["niche_tags"]
        assert profile["audience_region"] == "us"

    @pytest.mark.asyncio
    async def test_user_sees_matching_campaign_invitation(self, client, db):
        # Set up company + campaign
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]

        # Activate
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        # Register user with matching profile
        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)

        # Poll for campaigns (triggers matching)
        poll_resp = await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert poll_resp.status_code == 200
        campaigns = poll_resp.json()
        assert len(campaigns) >= 1
        matched = campaigns[0]
        assert matched["title"] == "AI Trading Indicator Launch"

        # Now check invitations endpoint
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert inv_resp.status_code == 200
        invitations = inv_resp.json()
        assert len(invitations) >= 1
        assert invitations[0]["title"] == "AI Trading Indicator Launch"
        assert invitations[0]["expires_at"] is not None


# ══════════════════════════════════════════════════════════════════
# 3. User accepts invitation
# ══════════════════════════════════════════════════════════════════


class TestUserAcceptsInvitation:

    @pytest.mark.asyncio
    async def test_accept_invitation_full_flow(self, client, db):
        # Setup: company + campaign + user
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)

        # Trigger matching
        await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Get invitation
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        invitations = inv_resp.json()
        assert len(invitations) >= 1
        assignment_id = invitations[0]["assignment_id"]

        # Accept
        accept_resp = await client.post(
            f"/api/campaigns/invitations/{assignment_id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert accept_resp.status_code == 200
        assert accept_resp.json()["status"] == "accepted"

        # Verify it appears in active campaigns
        active_resp = await client.get(
            "/api/campaigns/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert active_resp.status_code == 200
        active = active_resp.json()
        assert len(active) == 1
        assert active[0]["assignment_status"] == "accepted"

        # Verify campaign accepted_count incremented
        campaign_resp = await client.get(
            f"/api/company/campaigns/{campaign_id}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert campaign_resp.status_code == 200
        assert campaign_resp.json()["invitation_stats"]["accepted"] >= 1

        # Verify invitation log entry
        from app.models.invitation_log import CampaignInvitationLog
        from sqlalchemy import select
        result = await db.execute(
            select(CampaignInvitationLog).where(
                CampaignInvitationLog.event == "accepted",
                CampaignInvitationLog.campaign_id == campaign_id,
            )
        )
        log = result.scalar_one_or_none()
        assert log is not None


# ══════════════════════════════════════════════════════════════════
# 4. User rejects invitation
# ══════════════════════════════════════════════════════════════════


class TestUserRejectsInvitation:

    @pytest.mark.asyncio
    async def test_reject_invitation(self, client, db):
        # Setup
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(title="Reject Me Campaign"),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)

        # Trigger matching
        await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Get and reject
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        invitations = inv_resp.json()
        assert len(invitations) >= 1
        assignment_id = invitations[0]["assignment_id"]

        reject_resp = await client.post(
            f"/api/campaigns/invitations/{assignment_id}/reject",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "rejected"

        # Not in pending or active
        inv_resp2 = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert len(inv_resp2.json()) == 0

        active_resp = await client.get(
            "/api/campaigns/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert len(active_resp.json()) == 0

        # Double-reject returns 400
        reject2 = await client.post(
            f"/api/campaigns/invitations/{assignment_id}/reject",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert reject2.status_code == 400


# ══════════════════════════════════════════════════════════════════
# 5. Campaign edit propagation
# ══════════════════════════════════════════════════════════════════


class TestCampaignEditPropagation:

    @pytest.mark.asyncio
    async def test_edit_increments_version(self, client, db):
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        assert resp.json()["campaign_version"] == 1

        # Activate
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        # Edit brief
        patch_resp = await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"brief": "Updated: now targeting advanced traders too."},
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["campaign_version"] == 2

    @pytest.mark.asyncio
    async def test_user_sees_updated_campaign(self, client, db):
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        # Create and activate campaign
        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        # User onboards and accepts
        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)
        await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assignment_id = inv_resp.json()[0]["assignment_id"]
        await client.post(
            f"/api/campaigns/invitations/{assignment_id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Company edits campaign
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"brief": "UPDATED BRIEF: now targeting advanced traders."},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        # User fetches active campaigns and sees the update
        active_resp = await client.get(
            "/api/campaigns/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert active_resp.status_code == 200
        active = active_resp.json()
        assert len(active) == 1
        assert active[0]["campaign_updated_at"] is not None


# ══════════════════════════════════════════════════════════════════
# 6. Billing cycle
# ══════════════════════════════════════════════════════════════════


class TestBillingCycle:

    @pytest.mark.asyncio
    async def test_full_billing_cycle(self, client, db):
        """Full cycle: create post, add final metrics, run billing, verify earnings."""
        from app.services.billing import run_billing_cycle
        from app.core.database import async_session
        from app.models.user import User
        from app.models.campaign import Campaign
        from app.models.payout import Payout
        from sqlalchemy import select

        # Setup: company + campaign + user + accept
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(budget_total=500.0),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)
        user_id = await _get_user_id_from_token(user_token)

        # Trigger matching + accept
        await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assignment_id = inv_resp.json()[0]["assignment_id"]
        await client.post(
            f"/api/campaigns/invitations/{assignment_id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Register a post
        posted_at = (NOW - timedelta(hours=73)).isoformat()
        post_resp = await client.post(
            "/api/posts",
            json={"posts": [{
                "assignment_id": assignment_id,
                "platform": "x",
                "post_url": "https://x.com/testuser/status/12345",
                "content_hash": "abc123hash",
                "posted_at": posted_at,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert post_resp.status_code == 200
        post_id = post_resp.json()["created"][0]["id"]

        # Submit final metrics
        metric_resp = await client.post(
            "/api/metrics",
            json={"metrics": [{
                "post_id": post_id,
                "impressions": 10000,
                "likes": 100,
                "reposts": 20,
                "comments": 5,
                "clicks": 50,
                "scraped_at": NOW.isoformat(),
                "is_final": True,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert metric_resp.status_code == 200
        assert metric_resp.json()["accepted"] == 1

        # The metrics endpoint already triggers billing for final metrics.
        # Verify earnings:
        # raw = (10000/1000 * 0.50) + (100 * 0.01) + (20 * 0.05) + (50 * 0.10)
        #     = 5.00 + 1.00 + 1.00 + 5.00 = 12.00
        # user_earning = 12.00 * 0.80 = 9.60
        billing = metric_resp.json().get("billing")
        if billing:
            assert billing["posts_processed"] == 1
            assert billing["total_earned"] == pytest.approx(9.60)

        # Verify user balance
        profile_resp = await client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert profile_resp.status_code == 200
        assert float(profile_resp.json()["earnings_balance"]) == pytest.approx(9.60)
        assert float(profile_resp.json()["total_earned"]) == pytest.approx(9.60)

        # Verify campaign budget decremented
        campaign_resp = await client.get(
            f"/api/company/campaigns/{campaign_id}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert campaign_resp.status_code == 200
        # budget_remaining = 500 - 12.00 (gross cost) = 488.00
        assert float(campaign_resp.json()["budget_remaining"]) == pytest.approx(488.00)

    @pytest.mark.asyncio
    async def test_billing_no_multiplier(self, client, db):
        """Verify billing does not apply multiplier (pure metrics)."""
        from app.services.billing import run_billing_cycle
        from app.core.database import async_session

        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(budget_total=500.0),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)

        await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assignment_id = inv_resp.json()[0]["assignment_id"]
        await client.post(
            f"/api/campaigns/invitations/{assignment_id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Register post + final metrics
        posted_at = (NOW - timedelta(hours=73)).isoformat()
        post_resp = await client.post(
            "/api/posts",
            json={"posts": [{
                "assignment_id": assignment_id,
                "platform": "x",
                "post_url": "https://x.com/test/status/999",
                "content_hash": "def456",
                "posted_at": posted_at,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        post_id = post_resp.json()["created"][0]["id"]

        metric_resp = await client.post(
            "/api/metrics",
            json={"metrics": [{
                "post_id": post_id,
                "impressions": 20000,
                "likes": 0,
                "reposts": 0,
                "comments": 0,
                "clicks": 0,
                "scraped_at": NOW.isoformat(),
                "is_final": True,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert metric_resp.status_code == 200

        # raw = 20000/1000 * 0.50 = 10.00, user = 10.00 * 0.80 = 8.00
        profile = await client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert float(profile.json()["earnings_balance"]) == pytest.approx(8.00)


# ══════════════════════════════════════════════════════════════════
# 7. User earnings
# ══════════════════════════════════════════════════════════════════


class TestUserEarnings:

    @pytest.mark.asyncio
    async def test_earnings_endpoint_and_payout(self, client, db):
        """Verify GET /me/earnings returns correct data, and POST /me/payout works."""
        # Setup full cycle: company -> campaign -> user -> accept -> post -> billing
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(budget_total=500.0),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)

        await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assignment_id = inv_resp.json()[0]["assignment_id"]
        await client.post(
            f"/api/campaigns/invitations/{assignment_id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Post + metrics to generate earnings
        posted_at = (NOW - timedelta(hours=73)).isoformat()
        post_resp = await client.post(
            "/api/posts",
            json={"posts": [{
                "assignment_id": assignment_id,
                "platform": "x",
                "post_url": "https://x.com/test/status/earnings1",
                "content_hash": "earn1",
                "posted_at": posted_at,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        post_id = post_resp.json()["created"][0]["id"]

        await client.post(
            "/api/metrics",
            json={"metrics": [{
                "post_id": post_id,
                "impressions": 10000,
                "likes": 100,
                "reposts": 20,
                "comments": 5,
                "clicks": 50,
                "scraped_at": NOW.isoformat(),
                "is_final": True,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Check earnings endpoint
        earnings_resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert earnings_resp.status_code == 200
        earnings = earnings_resp.json()
        assert earnings["total_earned"] == pytest.approx(9.60)
        assert earnings["current_balance"] == pytest.approx(9.60)
        # Per-campaign breakdown should exist
        assert len(earnings["per_campaign"]) >= 1
        assert earnings["per_campaign"][0]["campaign_title"] == "AI Trading Indicator Launch"

        # Payout: minimum is $10, we have $9.60 — should fail
        payout_resp = await client.post(
            "/api/users/me/payout",
            json={"amount": 9.60},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert payout_resp.status_code == 400  # Below $10 minimum

    @pytest.mark.asyncio
    async def test_payout_succeeds_with_sufficient_balance(self, client, db):
        """When balance >= $10, payout should succeed."""
        # Setup full cycle with higher metrics to earn > $10
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 10000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(budget_total=2000.0),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)

        await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assignment_id = inv_resp.json()[0]["assignment_id"]
        await client.post(
            f"/api/campaigns/invitations/{assignment_id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        posted_at = (NOW - timedelta(hours=73)).isoformat()
        post_resp = await client.post(
            "/api/posts",
            json={"posts": [{
                "assignment_id": assignment_id,
                "platform": "x",
                "post_url": "https://x.com/test/status/bigearnings",
                "content_hash": "bigearnings",
                "posted_at": posted_at,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        post_id = post_resp.json()["created"][0]["id"]

        # High metrics to earn > $10
        # raw = (50000/1000 * 0.50) + (500 * 0.01) + (100 * 0.05) + (200 * 0.10)
        #     = 25.00 + 5.00 + 5.00 + 20.00 = 55.00
        # user = 55.00 * 0.80 = 44.00
        await client.post(
            "/api/metrics",
            json={"metrics": [{
                "post_id": post_id,
                "impressions": 50000,
                "likes": 500,
                "reposts": 100,
                "comments": 50,
                "clicks": 200,
                "scraped_at": NOW.isoformat(),
                "is_final": True,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Request payout
        payout_resp = await client.post(
            "/api/users/me/payout",
            json={"amount": 20.00},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert payout_resp.status_code == 200
        payout = payout_resp.json()
        assert payout["amount"] == 20.00
        assert payout["status"] == "pending"
        assert payout["new_balance"] == pytest.approx(24.00)

        # Verify balance deducted
        profile = await client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert float(profile.json()["earnings_balance"]) == pytest.approx(24.00)


# ══════════════════════════════════════════════════════════════════
# 8. Company sees results
# ══════════════════════════════════════════════════════════════════


class TestCompanySeesResults:

    @pytest.mark.asyncio
    async def test_campaign_detail_shows_stats(self, client, db):
        """After posting and billing, company campaign detail shows metrics."""
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(budget_total=500.0),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)

        await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assignment_id = inv_resp.json()[0]["assignment_id"]
        await client.post(
            f"/api/campaigns/invitations/{assignment_id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Post + metrics
        posted_at = (NOW - timedelta(hours=73)).isoformat()
        post_resp = await client.post(
            "/api/posts",
            json={"posts": [{
                "assignment_id": assignment_id,
                "platform": "x",
                "post_url": "https://x.com/test/status/company_view",
                "content_hash": "cv1",
                "posted_at": posted_at,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        post_id = post_resp.json()["created"][0]["id"]

        await client.post(
            "/api/metrics",
            json={"metrics": [{
                "post_id": post_id,
                "impressions": 10000,
                "likes": 100,
                "reposts": 20,
                "comments": 5,
                "clicks": 50,
                "scraped_at": NOW.isoformat(),
                "is_final": True,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Company gets campaign detail
        detail_resp = await client.get(
            f"/api/company/campaigns/{campaign_id}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert detail_resp.status_code == 200
        detail = detail_resp.json()

        # Invitation stats
        assert "invitation_stats" in detail
        assert detail["invitation_stats"]["accepted"] >= 1

        # Per-user breakdown
        assert "invited_users" in detail
        assert len(detail["invited_users"]) >= 1

        # Budget should be decremented
        assert float(detail["budget_remaining"]) < 500.0

    @pytest.mark.asyncio
    async def test_campaign_list_shows_invitation_stats(self, client, db):
        """Campaign list includes invitation_stats for each campaign."""
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]

        # List campaigns
        list_resp = await client.get(
            "/api/company/campaigns",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert list_resp.status_code == 200
        campaigns = list_resp.json()
        assert len(campaigns) >= 1
        assert "invitation_stats" in campaigns[0]


# ══════════════════════════════════════════════════════════════════
# 9. Max 5 campaigns enforcement
# ══════════════════════════════════════════════════════════════════


class TestMax5CampaignsEnforcement:

    @pytest.mark.asyncio
    async def test_cannot_accept_6th_campaign(self, client, db):
        """User with 5 accepted campaigns cannot accept a 6th."""
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 50000.0)

        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)
        user_id = await _get_user_id_from_token(user_token)

        # Create 6 campaigns and activate them
        campaign_ids = []
        for i in range(6):
            resp = await client.post(
                "/api/company/campaigns",
                json=_campaign_payload(
                    title=f"Campaign {i+1}",
                    budget_total=100.0,
                ),
                headers={"Authorization": f"Bearer {company_token}"},
            )
            cid = resp.json()["id"]
            campaign_ids.append(cid)
            await client.patch(
                f"/api/company/campaigns/{cid}",
                json={"status": "active"},
                headers={"Authorization": f"Bearer {company_token}"},
            )

        # Create assignments directly for 5 campaigns + invitation for 6th
        from app.models.assignment import CampaignAssignment
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(5):
            assignment = CampaignAssignment(
                campaign_id=campaign_ids[i],
                user_id=user_id,
                status="accepted",
                content_mode="ai_generated",
                payout_multiplier=1.0,
                invited_at=now,
            )
            db.add(assignment)

        # Create the 6th as a pending invitation
        sixth_invitation = CampaignAssignment(
            campaign_id=campaign_ids[5],
            user_id=user_id,
            status="pending_invitation",
            content_mode="ai_generated",
            payout_multiplier=1.0,
            invited_at=now,
            expires_at=now + timedelta(days=3),
        )
        db.add(sixth_invitation)
        await db.flush()
        await db.commit()

        # Try to accept the 6th — should fail
        resp6 = await client.post(
            f"/api/campaigns/invitations/{sixth_invitation.id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp6.status_code == 400
        detail = resp6.json()["detail"].lower()
        assert "5" in detail or "limit" in detail or "maximum" in detail


# ══════════════════════════════════════════════════════════════════
# 10. Invitation expiry
# ══════════════════════════════════════════════════════════════════


class TestInvitationExpiry:

    @pytest.mark.asyncio
    async def test_expired_invitation_auto_dismissed(self, client, db):
        """An expired invitation is auto-expired on GET /invitations."""
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)
        user_id = await _get_user_id_from_token(user_token)

        # Create campaign
        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        # Create an expired assignment directly in DB
        from app.models.assignment import CampaignAssignment

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expired_assignment = CampaignAssignment(
            campaign_id=campaign_id,
            user_id=user_id,
            status="pending_invitation",
            content_mode="ai_generated",
            payout_multiplier=1.0,
            invited_at=now - timedelta(days=4),
            expires_at=now - timedelta(days=1),
        )
        db.add(expired_assignment)
        await db.flush()
        await db.commit()

        # GET invitations — should auto-expire and return empty
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert inv_resp.status_code == 200
        assert len(inv_resp.json()) == 0

        # Verify campaign expired_count incremented
        from app.models.campaign import Campaign
        from sqlalchemy import select
        db.expire_all()
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one()
        assert campaign.expired_count >= 1

        # Try to accept the expired invitation — should fail
        accept_resp = await client.post(
            f"/api/campaigns/invitations/{expired_assignment.id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert accept_resp.status_code == 400


# ══════════════════════════════════════════════════════════════════
# 11. Budget exhaustion
# ══════════════════════════════════════════════════════════════════


class TestBudgetExhaustion:

    @pytest.mark.asyncio
    async def test_budget_exhaustion_auto_completes(self, client, db):
        """When budget runs out, campaign auto-completes (default action)."""
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        # Create campaign with very low budget
        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(budget_total=50.0),  # Minimum $50
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)

        await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assignment_id = inv_resp.json()[0]["assignment_id"]
        await client.post(
            f"/api/campaigns/invitations/{assignment_id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Post with high metrics that will exhaust the $50 budget
        posted_at = (NOW - timedelta(hours=73)).isoformat()
        post_resp = await client.post(
            "/api/posts",
            json={"posts": [{
                "assignment_id": assignment_id,
                "platform": "x",
                "post_url": "https://x.com/test/status/exhaust",
                "content_hash": "exhaust1",
                "posted_at": posted_at,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        post_id = post_resp.json()["created"][0]["id"]

        # Metrics that would normally cost $55 (raw) — budget is only $50
        # raw = (100000/1000 * 0.50) + (500 * 0.01) = 50.00 + 5.00 = 55.00
        await client.post(
            "/api/metrics",
            json={"metrics": [{
                "post_id": post_id,
                "impressions": 100000,
                "likes": 500,
                "reposts": 0,
                "comments": 0,
                "clicks": 0,
                "scraped_at": NOW.isoformat(),
                "is_final": True,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Campaign should be completed (or paused) due to budget exhaustion
        from app.models.campaign import Campaign
        from sqlalchemy import select
        db.expire_all()
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one()
        assert campaign.status in ("completed", "paused")
        assert float(campaign.budget_remaining) < 1.0

    @pytest.mark.asyncio
    async def test_budget_exhaustion_auto_pause(self, client, db):
        """When budget_exhaustion_action is auto_pause, campaign pauses."""
        from app.models.campaign import Campaign
        from sqlalchemy import select

        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(budget_total=50.0),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]

        # Set budget_exhaustion_action to auto_pause directly in DB
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one()
        campaign.budget_exhaustion_action = "auto_pause"
        await db.flush()
        await db.commit()

        await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )

        user_token, _ = await _register_user(client)
        await _update_user_profile(client, user_token)

        await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assignment_id = inv_resp.json()[0]["assignment_id"]
        await client.post(
            f"/api/campaigns/invitations/{assignment_id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        posted_at = (NOW - timedelta(hours=73)).isoformat()
        post_resp = await client.post(
            "/api/posts",
            json={"posts": [{
                "assignment_id": assignment_id,
                "platform": "x",
                "post_url": "https://x.com/test/status/autopause",
                "content_hash": "autopause1",
                "posted_at": posted_at,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        post_id = post_resp.json()["created"][0]["id"]

        await client.post(
            "/api/metrics",
            json={"metrics": [{
                "post_id": post_id,
                "impressions": 100000,
                "likes": 500,
                "reposts": 0,
                "comments": 0,
                "clicks": 0,
                "scraped_at": NOW.isoformat(),
                "is_final": True,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        db.expire_all()
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one()
        assert campaign.status == "paused"


# ══════════════════════════════════════════════════════════════════
# 12. Content screening
# ══════════════════════════════════════════════════════════════════


class TestContentScreening:

    @pytest.mark.asyncio
    async def test_flagged_campaign_cannot_activate(self, client, db):
        """Campaign with prohibited keywords is flagged and cannot activate."""
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(
                title="Casino Bonuses",
                brief="Get guaranteed returns at our casino platform.",
            ),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        campaign_id = resp.json()["id"]
        assert resp.json()["screening_status"] == "flagged"
        assert "screening_warning" in resp.json()

        # Try to activate — should fail
        activate_resp = await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert activate_resp.status_code == 400
        assert "flagged" in activate_resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_screening_log_created(self, client, db):
        """Flagged campaign creates a ContentScreeningLog entry."""
        from app.models.screening_log import ContentScreeningLog
        from sqlalchemy import select

        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(
                title="Quick money",
                brief="Join our escort service and adult entertainment platform.",
            ),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]

        result = await db.execute(
            select(ContentScreeningLog).where(
                ContentScreeningLog.campaign_id == campaign_id
            )
        )
        log = result.scalar_one_or_none()
        assert log is not None
        assert log.flagged is True

    @pytest.mark.asyncio
    async def test_admin_approve_allows_activation(self, client, db):
        """After admin approves a flagged campaign, it can be activated."""
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(
                title="Poker strategies",
                brief="Learn poker strategies at our casino.",
            ),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        assert resp.json()["screening_status"] == "flagged"

        # Admin approves
        approve_resp = await client.post(
            f"/api/admin/flagged-campaigns/{campaign_id}/approve",
            json={"notes": "Acceptable content with context."},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["screening_status"] == "approved"

        # Now activation should work
        activate_resp = await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert activate_resp.status_code == 200
        assert activate_resp.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_admin_reject_cancels_campaign(self, client, db):
        """Admin reject sets campaign to cancelled and refunds budget."""
        from app.models.company import Company
        from sqlalchemy import select

        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        # Check balance before
        db.expire_all()
        result = await db.execute(select(Company).where(Company.id == company_id))
        initial_balance = float(result.scalar_one().balance)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(
                title="Drug marketplace",
                brief="Buy cannabis and marijuana accessories.",
                budget_total=200.0,
            ),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]

        # Admin rejects
        reject_resp = await client.post(
            f"/api/admin/flagged-campaigns/{campaign_id}/reject",
            json={"reason": "Prohibited drugs content."},
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["screening_status"] == "rejected"

        # Campaign should be cancelled
        detail_resp = await client.get(
            f"/api/company/campaigns/{campaign_id}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert detail_resp.json()["status"] == "cancelled"
        assert detail_resp.json()["screening_status"] == "rejected"

        # Budget should be refunded
        db.expire_all()
        result2 = await db.execute(select(Company).where(Company.id == company_id))
        final_balance = float(result2.scalar_one().balance)
        assert final_balance == pytest.approx(initial_balance)


# ══════════════════════════════════════════════════════════════════
# 13. Minimum budget enforcement
# ══════════════════════════════════════════════════════════════════


class TestMinimumBudgetEnforcement:

    @pytest.mark.asyncio
    async def test_budget_below_50_rejected(self, client, db):
        """Campaign with budget < $50 should be rejected."""
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(budget_total=25.0),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 400
        assert "50" in resp.json()["detail"] or "minimum" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_budget_exactly_50_accepted(self, client, db):
        """Campaign with budget = $50 should be accepted."""
        company_token, _ = await _register_company(client)
        company_id = await _get_company_id_from_token(company_token)
        await _topup_company_balance(db, company_id, 5000.0)

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(budget_total=50.0),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_insufficient_balance_rejected(self, client, db):
        """Campaign creation should fail if company balance is too low."""
        company_token, _ = await _register_company(client)
        # Company has $0 balance — don't top up

        resp = await client.post(
            "/api/company/campaigns",
            json=_campaign_payload(budget_total=200.0),
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 400
        assert "balance" in resp.json()["detail"].lower() or "insufficient" in resp.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════════
# 14. Full cycle end-to-end (single test)
# ══════════════════════════════════════════════════════════════════


class TestFullCycleE2E:
    """One big test that walks through the entire cycle in sequence."""

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, client, db):
        """
        Company registers -> tops up -> creates campaign -> activates ->
        User registers -> updates profile -> polls -> gets invitation -> accepts ->
        Posts content -> Submits metrics -> Billing runs -> Earnings credited ->
        User checks earnings -> Company sees results
        """
        # ── Step 1: Company onboards ──────────────────────────────
        company_resp = await client.post("/api/auth/company/register", json={
            "name": "Acme Inc",
            "email": "acme@test.com",
            "password": "secure123",
        })
        assert company_resp.status_code == 200
        company_token = company_resp.json()["access_token"]
        company_id = await _get_company_id_from_token(company_token)

        # Top up balance
        await _topup_company_balance(db, company_id, 10000.0)

        # ── Step 2: Company creates campaign ──────────────────────
        campaign_resp = await client.post(
            "/api/company/campaigns",
            json={
                "title": "SaaS Product Launch",
                "brief": "Promote our new project management tool for remote teams.",
                "budget_total": 500.0,
                "payout_rules": {
                    "rate_per_1k_impressions": 1.00,
                    "rate_per_like": 0.02,
                    "rate_per_repost": 0.10,
                    "rate_per_click": 0.20,
                },
                "targeting": {
                    "min_followers": {"x": 100},
                    "niche_tags": ["tech", "business"],
                    "required_platforms": ["x"],
                    "target_regions": ["us"],
                },
                "content_guidance": "Professional tone, highlight remote work benefits.",
                "start_date": NOW.isoformat(),
                "end_date": (NOW + timedelta(days=30)).isoformat(),
            },
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert campaign_resp.status_code == 200
        campaign_id = campaign_resp.json()["id"]
        assert campaign_resp.json()["status"] == "draft"
        assert campaign_resp.json()["screening_status"] == "approved"

        # Activate
        activate_resp = await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert activate_resp.status_code == 200
        assert activate_resp.json()["status"] == "active"

        # ── Step 3: User onboards ─────────────────────────────────
        user_resp = await client.post("/api/auth/register", json={
            "email": "creator@test.com",
            "password": "userpass123",
        })
        assert user_resp.status_code == 200
        user_token = user_resp.json()["access_token"]

        # Update profile to match campaign targeting
        profile_resp = await client.patch("/api/users/me", json={
            "platforms": {"x": {"connected": True, "username": "@creator"}},
            "follower_counts": {"x": 10000},
            "niche_tags": ["tech", "business", "lifestyle"],
            "audience_region": "us",
            "mode": "semi_auto",
        }, headers={"Authorization": f"Bearer {user_token}"})
        assert profile_resp.status_code == 200

        # ── Step 4: User polls and gets invitation ────────────────
        poll_resp = await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert poll_resp.status_code == 200
        assert len(poll_resp.json()) >= 1

        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert inv_resp.status_code == 200
        invitations = inv_resp.json()
        assert len(invitations) >= 1
        invitation = invitations[0]
        assert invitation["title"] == "SaaS Product Launch"
        assert invitation["expires_at"] is not None
        assignment_id = invitation["assignment_id"]

        # ── Step 5: User accepts invitation ───────────────────────
        accept_resp = await client.post(
            f"/api/campaigns/invitations/{assignment_id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert accept_resp.status_code == 200
        assert accept_resp.json()["status"] == "accepted"

        # Verify in active campaigns
        active_resp = await client.get(
            "/api/campaigns/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert active_resp.status_code == 200
        assert len(active_resp.json()) == 1
        assert active_resp.json()[0]["assignment_status"] == "accepted"

        # ── Step 6: User posts content ────────────────────────────
        posted_at = (NOW - timedelta(hours=73)).isoformat()
        post_resp = await client.post(
            "/api/posts",
            json={"posts": [{
                "assignment_id": assignment_id,
                "platform": "x",
                "post_url": "https://x.com/creator/status/lifecycle_post_1",
                "content_hash": "lifecycle_hash_1",
                "posted_at": posted_at,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert post_resp.status_code == 200
        assert post_resp.json()["count"] == 1
        post_id = post_resp.json()["created"][0]["id"]

        # ── Step 7: Metrics collected at T+72h (final) ────────────
        metric_resp = await client.post(
            "/api/metrics",
            json={"metrics": [{
                "post_id": post_id,
                "impressions": 25000,
                "likes": 300,
                "reposts": 50,
                "comments": 20,
                "clicks": 100,
                "scraped_at": NOW.isoformat(),
                "is_final": True,
            }]},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert metric_resp.status_code == 200
        assert metric_resp.json()["accepted"] == 1

        # Billing runs automatically on final metric submission
        # raw = (25000/1000 * 1.00) + (300 * 0.02) + (50 * 0.10) + (100 * 0.20)
        #     = 25.00 + 6.00 + 5.00 + 20.00 = 56.00
        # user_earning = 56.00 * 0.80 = 44.80
        expected_earning = 44.80

        # ── Step 8: User checks earnings ──────────────────────────
        profile_after = await client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert profile_after.status_code == 200
        assert float(profile_after.json()["earnings_balance"]) == pytest.approx(expected_earning)
        assert float(profile_after.json()["total_earned"]) == pytest.approx(expected_earning)

        earnings_resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert earnings_resp.status_code == 200
        earnings = earnings_resp.json()
        assert earnings["total_earned"] == pytest.approx(expected_earning)
        assert earnings["current_balance"] == pytest.approx(expected_earning)
        assert len(earnings["per_campaign"]) >= 1
        campaign_earning = earnings["per_campaign"][0]
        assert campaign_earning["campaign_title"] == "SaaS Product Launch"
        assert campaign_earning["earned"] == pytest.approx(expected_earning)

        # ── Step 9: User requests payout ──────────────────────────
        payout_resp = await client.post(
            "/api/users/me/payout",
            json={"amount": 20.00},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert payout_resp.status_code == 200
        assert payout_resp.json()["amount"] == 20.00
        assert payout_resp.json()["status"] == "pending"
        remaining = expected_earning - 20.00
        assert payout_resp.json()["new_balance"] == pytest.approx(remaining)

        # ── Step 10: Company sees results ─────────────────────────
        company_detail = await client.get(
            f"/api/company/campaigns/{campaign_id}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert company_detail.status_code == 200
        detail = company_detail.json()

        # Budget decremented
        # gross_cost = 56.00, so remaining = 500.00 - 56.00 = 444.00
        assert float(detail["budget_remaining"]) == pytest.approx(444.00)

        # Invitation stats
        assert detail["invitation_stats"]["accepted"] >= 1

        # Per-user breakdown
        assert len(detail["invited_users"]) >= 1

        # Campaign list also shows stats
        list_resp = await client.get(
            "/api/company/campaigns",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1
        assert "invitation_stats" in list_resp.json()[0]
