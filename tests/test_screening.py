"""Tests for prohibited content screening (Task 4).

Covers:
- Screening service: clean pass, keyword detection, multiple categories,
  case insensitivity, word boundary (false positive avoidance)
- Integration: screening log creation on campaign create, flagged campaign
  cannot be activated, admin approve allows activation, admin reject cancels,
  editing a campaign re-screens
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
    """Seed a company with balance and return IDs + session."""
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
async def company_token(seed_data):
    """Create a JWT for the test company."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(seed_data["company_id"]), "type": "company"})


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client for the FastAPI app."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _campaign_payload(**overrides):
    """Helper to build a valid campaign creation payload."""
    now = datetime.now(timezone.utc)
    base = {
        "title": "Clean Product Launch",
        "brief": "Promote our new SaaS product for small businesses.",
        "budget_total": 200.0,
        "payout_rules": {
            "rate_per_1k_impressions": 0.50,
            "rate_per_like": 0.01,
            "rate_per_repost": 0.05,
            "rate_per_click": 0.10,
        },
        "targeting": {
            "min_followers": {},
            "niche_tags": ["tech"],
            "required_platforms": ["x"],
            "target_regions": ["us"],
        },
        "content_guidance": "Keep it professional and concise.",
        "start_date": now.isoformat(),
        "end_date": (now + timedelta(days=30)).isoformat(),
    }
    base.update(overrides)
    return base


# =====================================================================
# 1. Screening service unit tests
# =====================================================================

class TestScreeningService:
    """Unit tests for the screen_campaign function."""

    def test_clean_campaign_passes(self):
        """A campaign with no prohibited content should not be flagged."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="New SaaS Product Launch",
            brief="We are launching a project management tool for remote teams.",
            content_guidance="Keep it professional.",
        )
        assert result["flagged"] is False
        assert result["flagged_keywords"] == []
        assert result["categories"] == []

    def test_adult_keywords_flagged(self):
        """Campaign with adult content keywords should be flagged."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="Amazing content platform",
            brief="Join our escort service for exclusive adult entertainment.",
        )
        assert result["flagged"] is True
        assert "escort" in result["flagged_keywords"]
        assert "adult entertainment" in result["flagged_keywords"]
        assert "adult" in result["categories"]

    def test_gambling_keywords_flagged(self):
        """Campaign with gambling keywords should be flagged."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="Best casino bonuses",
            brief="Sign up at our online betting platform for free slots.",
        )
        assert result["flagged"] is True
        assert "casino" in result["flagged_keywords"]
        assert "betting" in result["flagged_keywords"] or "online betting" in result["flagged_keywords"]
        assert "gambling" in result["categories"]

    def test_drugs_keywords_flagged(self):
        """Campaign with drug-related keywords should be flagged."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="Natural wellness products",
            brief="Buy our cannabis-derived products and marijuana accessories.",
        )
        assert result["flagged"] is True
        assert "cannabis" in result["flagged_keywords"]
        assert "marijuana" in result["flagged_keywords"]
        assert "drugs" in result["categories"]

    def test_weapons_keywords_flagged(self):
        """Campaign with weapons-related keywords should be flagged."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="Defense equipment",
            brief="Browse our ammunition selection and firearms dealer network.",
        )
        assert result["flagged"] is True
        assert "ammunition" in result["flagged_keywords"]
        assert "firearms dealer" in result["flagged_keywords"]
        assert "weapons" in result["categories"]

    def test_financial_fraud_keywords_flagged(self):
        """Campaign with financial fraud keywords should be flagged."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="Investment opportunity",
            brief="Get guaranteed returns with our pyramid scheme structure.",
        )
        assert result["flagged"] is True
        assert "guaranteed returns" in result["flagged_keywords"]
        assert "pyramid scheme" in result["flagged_keywords"]
        assert "financial_fraud" in result["categories"]

    def test_hate_speech_keywords_flagged(self):
        """Campaign with hate speech keywords should be flagged."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="Political movement",
            brief="Join our white supremacy group today.",
        )
        assert result["flagged"] is True
        assert "white supremacy" in result["flagged_keywords"]
        assert "hate_speech" in result["categories"]

    def test_multiple_categories_flagged(self):
        """Campaign with content from multiple prohibited categories."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="Everything goes",
            brief="Guaranteed returns from our casino and escort service.",
        )
        assert result["flagged"] is True
        assert len(result["categories"]) >= 2
        assert "financial_fraud" in result["categories"]
        assert "gambling" in result["categories"]
        assert "adult" in result["categories"]

    def test_case_insensitivity(self):
        """Screening should be case-insensitive."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="GUARANTEED RETURNS opportunity",
            brief="Join our CASINO platform with PYRAMID SCHEME rewards.",
        )
        assert result["flagged"] is True
        assert "guaranteed returns" in result["flagged_keywords"]
        assert "casino" in result["flagged_keywords"]
        assert "pyramid scheme" in result["flagged_keywords"]

    def test_word_boundary_no_false_positive_grass(self):
        """'grass' should NOT match 'ass' or any adult keyword."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="Lawn care service",
            brief="We help you grow beautiful grass in your backyard.",
        )
        assert result["flagged"] is False

    def test_word_boundary_no_false_positive_therapist(self):
        """'therapist' should NOT trigger any false match."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="Mental health services",
            brief="Our licensed therapist helps with anxiety and depression.",
        )
        assert result["flagged"] is False

    def test_word_boundary_no_false_positive_scasino(self):
        """'scasino' or 'casinography' should NOT match 'casino'."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="Documentary review",
            brief="Watch the casinography of Las Vegas history.",
        )
        assert result["flagged"] is False

    def test_word_boundary_no_false_positive_assassination(self):
        """'assassination' should NOT match weapon-related single words."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="History documentary",
            brief="The assassination of a historical figure changed the world.",
        )
        assert result["flagged"] is False

    def test_content_guidance_also_screened(self):
        """Content guidance field is included in screening."""
        from app.services.content_screening import screen_campaign
        result = screen_campaign(
            title="Clean title",
            brief="Clean brief about our tech product.",
            content_guidance="Emphasize the guaranteed returns angle.",
        )
        assert result["flagged"] is True
        assert "guaranteed returns" in result["flagged_keywords"]
        assert "financial_fraud" in result["categories"]


# =====================================================================
# 2. Integration tests via API
# =====================================================================

class TestScreeningIntegration:
    """Integration tests: screening runs on campaign CRUD, admin review works."""

    @pytest.mark.asyncio
    async def test_clean_campaign_creation(self, client, company_token):
        """Clean campaign should be created with screening_status='approved'."""
        payload = _campaign_payload()
        resp = await client.post(
            "/api/company/campaigns",
            json=payload,
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["screening_status"] == "approved"
        assert data.get("screening_warning") is None

    @pytest.mark.asyncio
    async def test_flagged_campaign_creation(self, client, company_token):
        """Campaign with prohibited keywords should be flagged + return warning."""
        payload = _campaign_payload(
            title="Amazing Casino Returns",
            brief="Get guaranteed returns at our casino platform.",
        )
        resp = await client.post(
            "/api/company/campaigns",
            json=payload,
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["screening_status"] == "flagged"
        assert "screening_warning" in data

    @pytest.mark.asyncio
    async def test_screening_creates_log_entry(self, client, company_token, db_session):
        """Flagged campaign should create a ContentScreeningLog entry."""
        from app.models.screening_log import ContentScreeningLog
        from sqlalchemy import select

        payload = _campaign_payload(
            title="Hot deals",
            brief="Our escort service offers premium adult entertainment.",
        )
        resp = await client.post(
            "/api/company/campaigns",
            json=payload,
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        campaign_id = resp.json()["id"]

        # Query the DB for the screening log
        result = await db_session.execute(
            select(ContentScreeningLog).where(
                ContentScreeningLog.campaign_id == campaign_id
            )
        )
        log = result.scalar_one_or_none()
        assert log is not None
        assert log.flagged is True
        assert "escort" in log.flagged_keywords
        assert "adult" in log.screening_categories

    @pytest.mark.asyncio
    async def test_flagged_campaign_cannot_be_activated(self, client, company_token):
        """A flagged campaign should not transition to active status."""
        # Create flagged campaign
        payload = _campaign_payload(
            title="Poker night",
            brief="Join our casino and betting platform.",
        )
        resp = await client.post(
            "/api/company/campaigns",
            json=payload,
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        campaign_id = resp.json()["id"]
        assert resp.json()["screening_status"] == "flagged"

        # Try to activate
        resp2 = await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp2.status_code == 400
        assert "flagged" in resp2.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_admin_approve_allows_activation(self, client, company_token):
        """After admin approves, the flagged campaign can be activated."""
        # Create flagged campaign
        payload = _campaign_payload(
            title="Poker strategy guide",
            brief="Learn poker strategies at our casino.",
        )
        resp = await client.post(
            "/api/company/campaigns",
            json=payload,
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        assert resp.json()["screening_status"] == "flagged"

        # Admin approves via API
        approve_resp = await client.post(
            f"/api/admin/flagged-campaigns/{campaign_id}/approve",
            json={"notes": "Reviewed, acceptable with context."},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["screening_status"] == "approved"

        # Now activate should work
        activate_resp = await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert activate_resp.status_code == 200
        assert activate_resp.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_admin_reject_cancels_campaign(self, client, company_token, db_session):
        """After admin rejects, campaign is cancelled and budget refunded."""
        from app.models.company import Company
        from sqlalchemy import select

        # Check initial balance
        company_result = await db_session.execute(select(Company))
        initial_balance = float(company_result.scalar_one().balance)

        # Create flagged campaign (deducts 200 from balance)
        payload = _campaign_payload(
            title="Quick money",
            brief="Get rich quick with our pyramid scheme.",
        )
        resp = await client.post(
            "/api/company/campaigns",
            json=payload,
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        assert resp.json()["screening_status"] == "flagged"

        # Admin rejects
        reject_resp = await client.post(
            f"/api/admin/flagged-campaigns/{campaign_id}/reject",
            json={"reason": "Promotes pyramid scheme. Rejected."},
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["screening_status"] == "rejected"

        # Campaign should now be cancelled
        campaign_resp = await client.get(
            f"/api/company/campaigns/{campaign_id}",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert campaign_resp.json()["status"] == "cancelled"
        assert campaign_resp.json()["screening_status"] == "rejected"

        # Budget should be refunded
        db_session.expire_all()
        company_result2 = await db_session.execute(select(Company))
        final_balance = float(company_result2.scalar_one().balance)
        assert final_balance == initial_balance

    @pytest.mark.asyncio
    async def test_editing_campaign_re_screens(self, client, company_token):
        """Editing a campaign's brief should re-run screening."""
        # Create a clean campaign
        payload = _campaign_payload()
        resp = await client.post(
            "/api/company/campaigns",
            json=payload,
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        assert resp.json()["screening_status"] == "approved"

        # Edit brief to include prohibited content
        patch_resp = await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"brief": "Updated: now with guaranteed returns from our casino."},
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["screening_status"] == "flagged"

    @pytest.mark.asyncio
    async def test_editing_clean_to_clean_stays_approved(self, client, company_token):
        """Editing a clean campaign to still-clean content keeps approved status."""
        payload = _campaign_payload()
        resp = await client.post(
            "/api/company/campaigns",
            json=payload,
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]
        assert resp.json()["screening_status"] == "approved"

        # Edit with clean content
        patch_resp = await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"brief": "Updated: our amazing SaaS tool helps teams collaborate."},
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["screening_status"] == "approved"

    @pytest.mark.asyncio
    async def test_admin_list_flagged_campaigns(self, client, company_token):
        """GET /api/admin/flagged-campaigns returns flagged campaigns."""
        # Create two flagged campaigns
        for title in ["Casino night", "Poker club"]:
            await client.post(
                "/api/company/campaigns",
                json=_campaign_payload(
                    title=title,
                    brief=f"Join our {title.lower()} gambling platform.",
                ),
                headers={"Authorization": f"Bearer {company_token}"},
            )

        resp = await client.get("/api/admin/flagged-campaigns")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        # Each item should have expected fields
        for item in data:
            assert "campaign_id" in item
            assert "company_name" in item
            assert "screening_flags" in item
            assert "screening_status" in item

    @pytest.mark.asyncio
    async def test_rejected_campaign_cannot_be_activated(self, client, company_token):
        """A rejected campaign should not be activatable even after status change attempts."""
        payload = _campaign_payload(
            title="Drug marketplace",
            brief="Buy cocaine and heroin on our platform.",
        )
        resp = await client.post(
            "/api/company/campaigns",
            json=payload,
            headers={"Authorization": f"Bearer {company_token}"},
        )
        campaign_id = resp.json()["id"]

        # Admin rejects
        await client.post(
            f"/api/admin/flagged-campaigns/{campaign_id}/reject",
            json={"reason": "Prohibited drugs content."},
        )

        # Try to activate — should fail (campaign is cancelled + rejected)
        resp2 = await client.patch(
            f"/api/company/campaigns/{campaign_id}",
            json={"status": "active"},
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp2.status_code == 400
