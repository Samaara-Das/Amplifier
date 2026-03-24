"""Tests for the campaign invitation system (Task 2).

Covers:
- GET /api/campaigns/invitations — pending invitations list + auto-expiry
- POST /api/campaigns/invitations/{assignment_id}/accept — accept flow
- POST /api/campaigns/invitations/{assignment_id}/reject — reject flow
- GET /api/campaigns/active — active campaigns list
- Matching creates pending_invitation (not assigned)
- Invitation stats on company campaign detail
- CampaignInvitationLog event logging
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
    # Import all models so they're registered with Base
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
    """Seed a company, campaign, and user. Return their IDs."""
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
        title="Test Campaign",
        brief="Promote our product",
        assets={},
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
            "required_platforms": [],
            "target_regions": [],
        },
        content_guidance="Be creative",
        penalty_rules={},
        status="active",
        start_date=datetime.now(timezone.utc),
        end_date=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(campaign)
    await db_session.flush()

    user = User(
        email="user@test.com",
        password_hash=hash_password("pass123"),
        platforms={"x": {"connected": True}},
        follower_counts={"x": 1000},
        niche_tags=["finance"],
        audience_region="us",
        trust_score=70,
        mode="semi_auto",
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
async def user_token(seed_data):
    """Create a JWT for the test user."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(seed_data["user_id"]), "type": "user"})


@pytest_asyncio.fixture
async def company_token(seed_data):
    """Create a JWT for the test company."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(seed_data["company_id"]), "type": "company"})


@pytest_asyncio.fixture
async def client():
    """Async HTTP client bound to the FastAPI app."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def pending_invitation(db_session, seed_data):
    """Create a pending_invitation assignment and return it."""
    from app.models.assignment import CampaignAssignment

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assignment = CampaignAssignment(
        campaign_id=seed_data["campaign_id"],
        user_id=seed_data["user_id"],
        status="pending_invitation",
        content_mode="ai_generated",
        payout_multiplier=1.0,
        invited_at=now,
        expires_at=now + timedelta(days=3),
    )
    db_session.add(assignment)
    await db_session.flush()
    await db_session.commit()
    return assignment


@pytest_asyncio.fixture
async def expired_invitation(db_session, seed_data):
    """Create an expired invitation assignment."""
    from app.models.assignment import CampaignAssignment

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assignment = CampaignAssignment(
        campaign_id=seed_data["campaign_id"],
        user_id=seed_data["user_id"],
        status="pending_invitation",
        content_mode="ai_generated",
        payout_multiplier=1.0,
        invited_at=now - timedelta(days=4),
        expires_at=now - timedelta(days=1),
    )
    db_session.add(assignment)
    await db_session.flush()
    await db_session.commit()
    return assignment


# ===================================================================
# GET /api/campaigns/invitations
# ===================================================================

class TestGetInvitations:

    @pytest.mark.asyncio
    async def test_returns_pending_invitations(
        self, client, user_token, pending_invitation, seed_data
    ):
        resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        inv = data[0]
        assert inv["assignment_id"] == pending_invitation.id
        assert inv["campaign_id"] == seed_data["campaign_id"]
        assert inv["title"] == "Test Campaign"
        assert inv["brief"] == "Promote our product"
        assert inv["content_guidance"] == "Be creative"
        assert "payout_rules" in inv
        assert "expires_at" in inv
        assert "invited_at" in inv

    @pytest.mark.asyncio
    async def test_does_not_return_expired(
        self, client, user_token, expired_invitation
    ):
        """Expired invitations should not appear in the list."""
        resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_auto_expiry_sets_status(
        self, client, user_token, expired_invitation
    ):
        """Fetching invitations should auto-expire past-due ones.

        After auto-expiry, the expired invitation should not appear in pending
        and should not appear in active campaigns either.
        """
        # Trigger auto-expiry via GET
        resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        # The expired invitation should not appear in the pending list
        assert len(resp.json()) == 0

        # Trying to accept the expired invitation should fail
        resp2 = await client.post(
            f"/api/campaigns/invitations/{expired_invitation.id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # Should be 400 (expired or already transitioned to expired status)
        assert resp2.status_code == 400

    @pytest.mark.asyncio
    async def test_auto_expiry_increments_campaign_expired_count(
        self, client, user_token, expired_invitation, db_session, seed_data
    ):
        """Auto-expiry should increment campaign.expired_count."""
        from app.models.campaign import Campaign
        from sqlalchemy import select

        resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200

        db_session.expire_all()
        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        assert campaign.expired_count >= 1

    @pytest.mark.asyncio
    async def test_does_not_return_accepted(
        self, client, user_token, pending_invitation, db_session
    ):
        """Accepted invitations should not appear in pending list."""
        pending_invitation.status = "accepted"
        await db_session.flush()
        await db_session.commit()

        resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    @pytest.mark.asyncio
    async def test_does_not_return_rejected(
        self, client, user_token, pending_invitation, db_session
    ):
        """Rejected invitations should not appear in pending list."""
        pending_invitation.status = "rejected"
        await db_session.flush()
        await db_session.commit()

        resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    @pytest.mark.asyncio
    async def test_empty_when_no_invitations(self, client, user_token):
        resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_requires_auth(self, client):
        resp = await client.get("/api/campaigns/invitations")
        assert resp.status_code in (401, 403)


# ===================================================================
# POST /api/campaigns/invitations/{assignment_id}/accept
# ===================================================================

class TestAcceptInvitation:

    @pytest.mark.asyncio
    async def test_accept_success(
        self, client, user_token, pending_invitation, db_session
    ):
        resp = await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["assignment_id"] == pending_invitation.id

    @pytest.mark.asyncio
    async def test_accept_updates_status_in_db(
        self, client, user_token, pending_invitation
    ):
        """After accepting, the invitation should appear in active campaigns."""
        resp = await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200

        # Verify via GET active — the accepted campaign should now appear
        active_resp = await client.get(
            "/api/campaigns/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert active_resp.status_code == 200
        active = active_resp.json()
        assert len(active) == 1
        assert active[0]["assignment_id"] == pending_invitation.id
        assert active[0]["assignment_status"] == "accepted"

        # Verify it no longer appears in pending invitations
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert inv_resp.status_code == 200
        assert len(inv_resp.json()) == 0

    @pytest.mark.asyncio
    async def test_accept_increments_campaign_accepted_count(
        self, client, user_token, pending_invitation, db_session, seed_data
    ):
        await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        from app.models.campaign import Campaign
        from sqlalchemy import select

        db_session.expire_all()
        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        assert campaign.accepted_count >= 1

    @pytest.mark.asyncio
    async def test_accept_creates_log_entry(
        self, client, user_token, pending_invitation, db_session, seed_data
    ):
        await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        from app.models.invitation_log import CampaignInvitationLog
        from sqlalchemy import select

        db_session.expire_all()
        result = await db_session.execute(
            select(CampaignInvitationLog).where(
                CampaignInvitationLog.campaign_id == seed_data["campaign_id"],
                CampaignInvitationLog.user_id == seed_data["user_id"],
                CampaignInvitationLog.event == "accepted",
            )
        )
        log = result.scalar_one_or_none()
        assert log is not None

    @pytest.mark.asyncio
    async def test_accept_expired_invitation_returns_400(
        self, client, user_token, expired_invitation
    ):
        resp = await client.post(
            f"/api/campaigns/invitations/{expired_invitation.id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_already_accepted_returns_400(
        self, client, user_token, pending_invitation, db_session
    ):
        pending_invitation.status = "accepted"
        await db_session.flush()
        await db_session.commit()

        resp = await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_already_rejected_returns_400(
        self, client, user_token, pending_invitation, db_session
    ):
        pending_invitation.status = "rejected"
        await db_session.flush()
        await db_session.commit()

        resp = await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_nonexistent_returns_404(self, client, user_token):
        resp = await client.post(
            "/api/campaigns/invitations/99999/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_accept_other_users_invitation_returns_404(
        self, client, pending_invitation, db_session
    ):
        """A different user should not be able to accept someone else's invitation."""
        from app.models.user import User
        from app.core.security import hash_password, create_access_token

        other_user = User(
            email="other@test.com",
            password_hash=hash_password("pass123"),
            platforms={},
            follower_counts={},
            niche_tags=[],
        )
        db_session.add(other_user)
        await db_session.flush()
        await db_session.commit()

        other_token = create_access_token(
            {"sub": str(other_user.id), "type": "user"}
        )
        resp = await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/accept",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_accept_max_5_active_campaigns(
        self, client, user_token, seed_data, db_session
    ):
        """User with 5 active campaigns cannot accept a 6th."""
        from app.models.assignment import CampaignAssignment
        from app.models.campaign import Campaign

        # Create 5 more campaigns + accepted assignments
        for i in range(5):
            camp = Campaign(
                company_id=seed_data["company_id"],
                title=f"Campaign {i}",
                brief=f"Brief {i}",
                assets={},
                budget_total=100.0,
                budget_remaining=100.0,
                payout_rules={"rate_per_1k_impressions": 0.50},
                targeting={},
                penalty_rules={},
                status="active",
                start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc) + timedelta(days=30),
            )
            db_session.add(camp)
            await db_session.flush()

            assgn = CampaignAssignment(
                campaign_id=camp.id,
                user_id=seed_data["user_id"],
                status="accepted",
                content_mode="ai_generated",
                payout_multiplier=1.0,
            )
            db_session.add(assgn)

        # Create the invitation to try to accept (6th)
        sixth_camp = Campaign(
            company_id=seed_data["company_id"],
            title="Sixth Campaign",
            brief="Brief sixth",
            assets={},
            budget_total=100.0,
            budget_remaining=100.0,
            payout_rules={"rate_per_1k_impressions": 0.50},
            targeting={},
            penalty_rules={},
            status="active",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db_session.add(sixth_camp)
        await db_session.flush()

        invitation = CampaignAssignment(
            campaign_id=sixth_camp.id,
            user_id=seed_data["user_id"],
            status="pending_invitation",
            content_mode="ai_generated",
            payout_multiplier=1.0,
            invited_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=3),
        )
        db_session.add(invitation)
        await db_session.flush()
        await db_session.commit()

        resp = await client.post(
            f"/api/campaigns/invitations/{invitation.id}/accept",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 400
        assert "5" in resp.json()["detail"] or "limit" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_requires_auth(self, client, pending_invitation):
        resp = await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/accept"
        )
        assert resp.status_code in (401, 403)


# ===================================================================
# POST /api/campaigns/invitations/{assignment_id}/reject
# ===================================================================

class TestRejectInvitation:

    @pytest.mark.asyncio
    async def test_reject_success(
        self, client, user_token, pending_invitation
    ):
        resp = await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/reject",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["assignment_id"] == pending_invitation.id

    @pytest.mark.asyncio
    async def test_reject_updates_status_in_db(
        self, client, user_token, pending_invitation
    ):
        """After rejecting, the invitation should not appear in pending or active."""
        resp = await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/reject",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200

        # Verify not in pending
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert inv_resp.status_code == 200
        assert len(inv_resp.json()) == 0

        # Verify not in active
        active_resp = await client.get(
            "/api/campaigns/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert active_resp.status_code == 200
        assert len(active_resp.json()) == 0

        # Verify double-reject returns 400
        resp2 = await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/reject",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp2.status_code == 400

    @pytest.mark.asyncio
    async def test_reject_increments_campaign_rejected_count(
        self, client, user_token, pending_invitation, db_session, seed_data
    ):
        await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/reject",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        from app.models.campaign import Campaign
        from sqlalchemy import select

        db_session.expire_all()
        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        assert campaign.rejected_count >= 1

    @pytest.mark.asyncio
    async def test_reject_creates_log_entry(
        self, client, user_token, pending_invitation, db_session, seed_data
    ):
        await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/reject",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        from app.models.invitation_log import CampaignInvitationLog
        from sqlalchemy import select

        db_session.expire_all()
        result = await db_session.execute(
            select(CampaignInvitationLog).where(
                CampaignInvitationLog.campaign_id == seed_data["campaign_id"],
                CampaignInvitationLog.user_id == seed_data["user_id"],
                CampaignInvitationLog.event == "rejected",
            )
        )
        log = result.scalar_one_or_none()
        assert log is not None

    @pytest.mark.asyncio
    async def test_reject_expired_invitation_returns_400(
        self, client, user_token, expired_invitation
    ):
        resp = await client.post(
            f"/api/campaigns/invitations/{expired_invitation.id}/reject",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reject_already_accepted_returns_400(
        self, client, user_token, pending_invitation, db_session
    ):
        pending_invitation.status = "accepted"
        await db_session.flush()
        await db_session.commit()

        resp = await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/reject",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reject_already_rejected_returns_400(
        self, client, user_token, pending_invitation, db_session
    ):
        pending_invitation.status = "rejected"
        await db_session.flush()
        await db_session.commit()

        resp = await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/reject",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reject_nonexistent_returns_404(self, client, user_token):
        resp = await client.post(
            "/api/campaigns/invitations/99999/reject",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_requires_auth(self, client, pending_invitation):
        resp = await client.post(
            f"/api/campaigns/invitations/{pending_invitation.id}/reject"
        )
        assert resp.status_code in (401, 403)


# ===================================================================
# GET /api/campaigns/active
# ===================================================================

class TestGetActiveCampaigns:

    @pytest.mark.asyncio
    async def test_returns_accepted_campaigns(
        self, client, user_token, pending_invitation, db_session
    ):
        # Accept the invitation first
        pending_invitation.status = "accepted"
        pending_invitation.responded_at = datetime.now(timezone.utc)
        await db_session.flush()
        await db_session.commit()

        resp = await client.get(
            "/api/campaigns/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["assignment_id"] == pending_invitation.id
        assert data[0]["assignment_status"] == "accepted"
        assert data[0]["title"] == "Test Campaign"
        assert "campaign_updated_at" in data[0]

    @pytest.mark.asyncio
    async def test_returns_content_generated_campaigns(
        self, client, user_token, pending_invitation, db_session
    ):
        pending_invitation.status = "content_generated"
        await db_session.flush()
        await db_session.commit()

        resp = await client.get(
            "/api/campaigns/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_returns_posted_campaigns(
        self, client, user_token, pending_invitation, db_session
    ):
        pending_invitation.status = "posted"
        await db_session.flush()
        await db_session.commit()

        resp = await client.get(
            "/api/campaigns/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_excludes_pending_invitations(
        self, client, user_token, pending_invitation
    ):
        """Pending invitations should not appear in active campaigns."""
        resp = await client.get(
            "/api/campaigns/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    @pytest.mark.asyncio
    async def test_excludes_rejected(
        self, client, user_token, pending_invitation, db_session
    ):
        pending_invitation.status = "rejected"
        await db_session.flush()
        await db_session.commit()

        resp = await client.get(
            "/api/campaigns/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    @pytest.mark.asyncio
    async def test_empty_when_no_active(self, client, user_token):
        resp = await client.get(
            "/api/campaigns/active",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_requires_auth(self, client):
        resp = await client.get("/api/campaigns/active")
        assert resp.status_code in (401, 403)


# ===================================================================
# Matching creates pending_invitation
# ===================================================================

class TestMatchingCreatesInvitations:

    @pytest.mark.asyncio
    async def test_matching_creates_pending_invitation_status(
        self, db_session, seed_data
    ):
        """get_matched_campaigns should create assignments with pending_invitation status."""
        from app.models.user import User
        from app.services.matching import get_matched_campaigns
        from app.models.assignment import CampaignAssignment
        from sqlalchemy import select

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

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

    @pytest.mark.asyncio
    async def test_matching_sets_expires_at(self, db_session, seed_data):
        """Matched campaigns should have expires_at set to ~3 days from now."""
        from app.models.user import User
        from app.services.matching import get_matched_campaigns
        from app.models.assignment import CampaignAssignment
        from sqlalchemy import select

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        await get_matched_campaigns(user, db_session)

        result = await db_session.execute(
            select(CampaignAssignment).where(
                CampaignAssignment.user_id == seed_data["user_id"],
                CampaignAssignment.campaign_id == seed_data["campaign_id"],
            )
        )
        assignment = result.scalar_one()
        assert assignment.expires_at is not None
        # expires_at should be approximately 3 days from now
        delta = assignment.expires_at.replace(tzinfo=None) - datetime.now(timezone.utc).replace(tzinfo=None)
        assert timedelta(days=2, hours=23) < delta < timedelta(days=3, hours=1)

    @pytest.mark.asyncio
    async def test_matching_sets_invited_at(self, db_session, seed_data):
        from app.models.user import User
        from app.services.matching import get_matched_campaigns
        from app.models.assignment import CampaignAssignment
        from sqlalchemy import select

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        await get_matched_campaigns(user, db_session)

        result = await db_session.execute(
            select(CampaignAssignment).where(
                CampaignAssignment.user_id == seed_data["user_id"],
                CampaignAssignment.campaign_id == seed_data["campaign_id"],
            )
        )
        assignment = result.scalar_one()
        assert assignment.invited_at is not None

    @pytest.mark.asyncio
    async def test_matching_increments_invitation_count(self, db_session, seed_data):
        from app.models.user import User
        from app.models.campaign import Campaign
        from app.services.matching import get_matched_campaigns
        from sqlalchemy import select

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        await get_matched_campaigns(user, db_session)

        result = await db_session.execute(
            select(Campaign).where(Campaign.id == seed_data["campaign_id"])
        )
        campaign = result.scalar_one()
        assert campaign.invitation_count >= 1

    @pytest.mark.asyncio
    async def test_matching_creates_sent_log(self, db_session, seed_data):
        from app.models.user import User
        from app.services.matching import get_matched_campaigns
        from app.models.invitation_log import CampaignInvitationLog
        from sqlalchemy import select

        result = await db_session.execute(
            select(User).where(User.id == seed_data["user_id"])
        )
        user = result.scalar_one()

        await get_matched_campaigns(user, db_session)

        result = await db_session.execute(
            select(CampaignInvitationLog).where(
                CampaignInvitationLog.campaign_id == seed_data["campaign_id"],
                CampaignInvitationLog.user_id == seed_data["user_id"],
                CampaignInvitationLog.event == "sent",
            )
        )
        log = result.scalar_one_or_none()
        assert log is not None


# ===================================================================
# Company campaign detail — invitation stats
# ===================================================================

class TestCompanyCampaignInvitationStats:

    @pytest.mark.asyncio
    async def test_campaign_detail_includes_invitation_stats(
        self, client, company_token, seed_data, pending_invitation
    ):
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "invitation_stats" in data

    @pytest.mark.asyncio
    async def test_campaign_list_includes_invitation_stats(
        self, client, company_token, seed_data, pending_invitation
    ):
        resp = await client.get(
            "/api/company/campaigns",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert "invitation_stats" in data[0]

    @pytest.mark.asyncio
    async def test_campaign_detail_shows_invited_users(
        self, client, company_token, seed_data, pending_invitation
    ):
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "invited_users" in data
        assert len(data["invited_users"]) >= 1
        user_entry = data["invited_users"][0]
        assert "user_id" in user_entry
        assert "status" in user_entry
