"""Tests for campaign CRUD, matching hard filters, and invitation accept/reject."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.user import User
from app.services.matching import _passes_hard_filters


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    """Reset slowapi rate limiter storage before every test to prevent cross-test contamination."""
    from app.routers import auth as auth_router
    auth_router.limiter.reset()
    yield


# ---------------------------------------------------------------------------
# Campaign CRUD via HTTP (uses the FastAPI test client)
# ---------------------------------------------------------------------------


class TestCampaignCRUD:
    """Test campaign creation and listing via the API."""

    async def _register_company(self, client, email="co@test.com") -> str:
        resp = await client.post("/api/auth/company/register", json={
            "name": "TestCo",
            "email": email,
            "password": "pass123",
        })
        return resp.json()["access_token"]

    async def test_create_campaign(self, client):
        token = await self._register_company(client)
        now = datetime.now(timezone.utc)

        resp = await client.post(
            "/api/company/campaigns",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": "Test Campaign",
                "brief": "Buy our widgets",
                "budget_total": 500.0,
                "payout_rules": {
                    "rate_per_1k_impressions": 0.50,
                    "rate_per_like": 0.01,
                    "rate_per_repost": 0.05,
                    "rate_per_click": 0.10,
                },
                "targeting": {
                    "required_platforms": ["linkedin"],
                    "niche_tags": ["tech"],
                },
                "start_date": now.isoformat(),
                "end_date": (now + timedelta(days=30)).isoformat(),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test Campaign"
        assert data["status"] == "draft"
        assert data["budget_total"] == 500.0

    async def test_create_campaign_minimum_budget(self, client):
        """Budget minimum is enforced at activation, not draft creation (Task #15 quality gate).
        A $10 draft should be saved successfully; the quality gate blocks activation."""
        token = await self._register_company(client, email="minbudget@test.com")
        now = datetime.now(timezone.utc)

        resp = await client.post(
            "/api/company/campaigns",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": "Cheap Campaign",
                "brief": "Too cheap",
                "budget_total": 10.0,  # Below $50 minimum — allowed as draft
                "payout_rules": {"rate_per_1k_impressions": 0.50},
                "start_date": now.isoformat(),
                "end_date": (now + timedelta(days=7)).isoformat(),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "draft"

    async def test_list_campaigns(self, client):
        token = await self._register_company(client, email="list@test.com")
        now = datetime.now(timezone.utc)

        # Create two campaigns
        for i in range(2):
            await client.post(
                "/api/company/campaigns",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "title": f"Campaign {i}",
                    "brief": f"Brief {i}",
                    "budget_total": 100.0,
                    "payout_rules": {"rate_per_1k_impressions": 0.50},
                    "start_date": now.isoformat(),
                    "end_date": (now + timedelta(days=30)).isoformat(),
                },
            )

        resp = await client.get(
            "/api/company/campaigns",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_delete_draft_campaign(self, client):
        token = await self._register_company(client, email="del@test.com")
        now = datetime.now(timezone.utc)

        # Create a campaign (status=draft by default)
        create_resp = await client.post(
            "/api/company/campaigns",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": "To Delete",
                "brief": "Will be deleted",
                "budget_total": 100.0,
                "payout_rules": {"rate_per_1k_impressions": 0.50},
                "start_date": now.isoformat(),
                "end_date": (now + timedelta(days=30)).isoformat(),
            },
        )
        campaign_id = create_resp.json()["id"]

        # Delete it
        del_resp = await client.delete(
            f"/api/company/campaigns/{campaign_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "deleted"


# ---------------------------------------------------------------------------
# Matching hard filters — unit tests (no HTTP, direct function calls)
# ---------------------------------------------------------------------------


class TestMatchingHardFilters:
    """Test _passes_hard_filters() with various targeting criteria."""

    def _make_user(self, platforms=None, follower_counts=None, audience_region="us",
                   niche_tags=None):
        from types import SimpleNamespace
        return SimpleNamespace(
            platforms=platforms or {"linkedin": True, "facebook": True},
            follower_counts=follower_counts or {"linkedin": 500, "facebook": 200},
            audience_region=audience_region,
            niche_tags=niche_tags or ["finance"],
            scraped_profiles={},
        )

    def _make_campaign(self, targeting=None, max_users=None, accepted_count=0):
        from types import SimpleNamespace
        return SimpleNamespace(
            targeting=targeting or {},
            max_users=max_users,
            accepted_count=accepted_count,
        )

    def test_no_targeting_passes(self):
        """No targeting filters — everyone passes."""
        user = self._make_user()
        campaign = self._make_campaign(targeting={})
        assert _passes_hard_filters(campaign, user) is True

    def test_required_platform_match(self):
        """User has required platform."""
        user = self._make_user(platforms={"linkedin": True})
        campaign = self._make_campaign(targeting={"required_platforms": ["linkedin"]})
        assert _passes_hard_filters(campaign, user) is True

    def test_required_platform_missing(self):
        """User lacks the required platform."""
        user = self._make_user(platforms={"linkedin": True})
        campaign = self._make_campaign(targeting={"required_platforms": ["tiktok"]})
        assert _passes_hard_filters(campaign, user) is False

    def test_required_platform_dict_format(self):
        """User has platform in dict format: {"linkedin": {"connected": true}}."""
        user = self._make_user(platforms={"linkedin": {"connected": True, "username": "@test"}})
        campaign = self._make_campaign(targeting={"required_platforms": ["linkedin"]})
        assert _passes_hard_filters(campaign, user) is True

    def test_min_followers_pass(self):
        """User meets minimum follower threshold."""
        user = self._make_user(follower_counts={"linkedin": 500})
        campaign = self._make_campaign(targeting={"min_followers": {"linkedin": 100}})
        assert _passes_hard_filters(campaign, user) is True

    def test_min_followers_fail(self):
        """User below minimum follower threshold."""
        user = self._make_user(follower_counts={"linkedin": 50})
        campaign = self._make_campaign(targeting={"min_followers": {"linkedin": 100}})
        assert _passes_hard_filters(campaign, user) is False

    def test_target_region_match(self):
        user = self._make_user(audience_region="us")
        campaign = self._make_campaign(targeting={"target_regions": ["us", "uk"]})
        assert _passes_hard_filters(campaign, user) is True

    def test_target_region_mismatch(self):
        user = self._make_user(audience_region="india")
        campaign = self._make_campaign(targeting={"target_regions": ["us", "uk"]})
        assert _passes_hard_filters(campaign, user) is False

    def test_global_region_always_passes(self):
        """Users with 'global' region should pass any region filter."""
        user = self._make_user(audience_region="global")
        campaign = self._make_campaign(targeting={"target_regions": ["us"]})
        assert _passes_hard_filters(campaign, user) is True

    def test_max_users_cap_not_reached(self):
        campaign = self._make_campaign(max_users=10, accepted_count=5)
        user = self._make_user()
        assert _passes_hard_filters(campaign, user) is True

    def test_max_users_cap_reached(self):
        campaign = self._make_campaign(max_users=10, accepted_count=10)
        user = self._make_user()
        assert _passes_hard_filters(campaign, user) is False

    def test_combined_filters(self):
        """All filters together — user must pass all."""
        user = self._make_user(
            platforms={"linkedin": True, "facebook": True},
            follower_counts={"linkedin": 500, "facebook": 200},
            audience_region="us",
        )
        campaign = self._make_campaign(targeting={
            "required_platforms": ["linkedin"],
            "min_followers": {"linkedin": 100},
            "target_regions": ["us"],
        })
        assert _passes_hard_filters(campaign, user) is True

    def test_combined_filters_fail_one(self):
        """Failing any single filter should reject."""
        user = self._make_user(
            platforms={"linkedin": True},
            follower_counts={"linkedin": 50},  # Below minimum
            audience_region="us",
        )
        campaign = self._make_campaign(targeting={
            "required_platforms": ["linkedin"],
            "min_followers": {"linkedin": 100},  # User has only 50
            "target_regions": ["us"],
        })
        assert _passes_hard_filters(campaign, user) is False


# ---------------------------------------------------------------------------
# Invitation accept/reject (via HTTP)
# ---------------------------------------------------------------------------


class TestInvitationFlow:
    """Test the invitation accept/reject endpoints."""

    async def _setup_invitation(self, client):
        """Helper: create company, campaign, user, and a pending assignment.
        Returns (user_token, assignment_id, campaign_id).
        """
        # Register company and create campaign
        co_resp = await client.post("/api/auth/company/register", json={
            "name": "InvCo",
            "email": "inv@test.com",
            "password": "pass123",
        })
        co_token = co_resp.json()["access_token"]

        now = datetime.now(timezone.utc)
        camp_resp = await client.post(
            "/api/company/campaigns",
            headers={"Authorization": f"Bearer {co_token}"},
            json={
                "title": "Invitation Test Campaign",
                "brief": "Test brief",
                "budget_total": 200.0,
                "payout_rules": {"rate_per_1k_impressions": 0.50},
                "start_date": now.isoformat(),
                "end_date": (now + timedelta(days=30)).isoformat(),
            },
        )
        campaign_id = camp_resp.json()["id"]

        # Register user
        user_resp = await client.post("/api/auth/register", json={
            "email": "invuser@test.com",
            "password": "pass123",
        })
        user_token = user_resp.json()["access_token"]

        # Poll for matched campaigns — this triggers matching and creates assignments
        # For a clean test, we just verify the invitation endpoints work with
        # an existing assignment. Let's get user's invitations first.
        inv_resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # The matching algorithm may or may not match (depends on campaign status).
        # Return what we have for the endpoints that don't depend on matching.
        return user_token, campaign_id

    async def test_get_invitations_empty(self, client):
        """New user with no invitations should get an empty list."""
        user_resp = await client.post("/api/auth/register", json={
            "email": "noinv@test.com",
            "password": "pass123",
        })
        token = user_resp.json()["access_token"]

        resp = await client.get(
            "/api/campaigns/invitations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_accept_nonexistent_invitation(self, client):
        """Accepting a non-existent invitation should return 404."""
        user_resp = await client.post("/api/auth/register", json={
            "email": "ghost@test.com",
            "password": "pass123",
        })
        token = user_resp.json()["access_token"]

        resp = await client.post(
            "/api/campaigns/invitations/99999/accept",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_reject_nonexistent_invitation(self, client):
        """Rejecting a non-existent invitation should return 404."""
        user_resp = await client.post("/api/auth/register", json={
            "email": "ghost2@test.com",
            "password": "pass123",
        })
        token = user_resp.json()["access_token"]

        resp = await client.post(
            "/api/campaigns/invitations/99999/reject",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


class TestCampaignAssetUpload:
    """Bug #64: POST /api/company/campaigns/assets — Bearer-auth image upload endpoint."""

    async def _register_company(self, client, email="assetco@test.com") -> str:
        resp = await client.post("/api/auth/company/register", json={
            "name": "AssetCo",
            "email": email,
            "password": "pass123",
        })
        return resp.json()["access_token"]

    async def test_upload_asset_rejects_unauthenticated(self, client):
        """Asset upload without Bearer token returns 401/403."""
        import io
        resp = await client.post(
            "/api/company/campaigns/assets",
            files={"file": ("test.jpg", io.BytesIO(b"fake-jpeg"), "image/jpeg")},
        )
        assert resp.status_code in (401, 403)

    async def test_upload_asset_rejects_unsupported_type(self, client):
        """Asset upload with unsupported MIME type returns 400."""
        import io
        token = await self._register_company(client, email="assetco2@test.com")
        resp = await client.post(
            "/api/company/campaigns/assets",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("malware.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]
