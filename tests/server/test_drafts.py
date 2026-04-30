"""Tests for server/app/routers/drafts.py — draft CRUD, upsert, image upload."""

import io
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.core.security import create_access_token
from app.models.draft import Draft


def _user_token(user_id: int) -> str:
    return create_access_token({"sub": str(user_id), "type": "user"})


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    from app.routers import auth as auth_router
    auth_router.limiter.reset()
    yield


class TestDraftCreate:
    async def test_post_creates_draft(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="draft-create@test.com")
        company = await factory.create_company(db_session, email="draft-create-co@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        await db_session.commit()

        resp = await client.post(
            "/api/drafts",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={
                "campaign_id": campaign.id,
                "platform": "linkedin",
                "text": "Test draft text",
                "iteration": 1,
                "local_id": 42,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "linkedin"
        assert data["text"] == "Test draft text"
        assert data["status"] == "pending"
        assert data["local_id"] == 42
        assert data["user_id"] == user.id

    async def test_post_same_local_id_updates_not_duplicates(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="draft-upsert@test.com")
        company = await factory.create_company(db_session, email="draft-upsert-co@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        await db_session.commit()

        auth = {"Authorization": f"Bearer {_user_token(user.id)}"}
        payload = {
            "campaign_id": campaign.id,
            "platform": "reddit",
            "text": "Original text",
            "iteration": 1,
            "local_id": 99,
        }

        resp1 = await client.post("/api/drafts", headers=auth, json=payload)
        assert resp1.status_code == 200
        draft_id = resp1.json()["id"]

        # Update same local_id — should UPDATE not INSERT
        payload["text"] = "Updated text"
        resp2 = await client.post("/api/drafts", headers=auth, json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["id"] == draft_id  # same row
        assert resp2.json()["text"] == "Updated text"

        # Verify only 1 row in DB
        result = await db_session.execute(
            select(Draft).where(Draft.user_id == user.id, Draft.local_id == 99)
        )
        rows = result.scalars().all()
        assert len(rows) == 1

    async def test_post_null_local_id_always_inserts(self, client, db_session, factory):
        """local_id=None should always insert a new row (no upsert key)."""
        user = await factory.create_user(db_session, email="draft-nolocalid@test.com")
        company = await factory.create_company(db_session, email="draft-nolocalid-co@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        await db_session.commit()

        auth = {"Authorization": f"Bearer {_user_token(user.id)}"}
        payload = {
            "campaign_id": campaign.id,
            "platform": "facebook",
            "text": "No local id",
            "iteration": 1,
            # local_id omitted → None
        }

        resp1 = await client.post("/api/drafts", headers=auth, json=payload)
        assert resp1.status_code == 200
        resp2 = await client.post("/api/drafts", headers=auth, json=payload)
        assert resp2.status_code == 200
        assert resp1.json()["id"] != resp2.json()["id"]

    async def test_post_without_auth_returns_401(self, client, db_session, factory):
        company = await factory.create_company(db_session, email="draft-noauth-co@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        await db_session.commit()

        resp = await client.post(
            "/api/drafts",
            json={"campaign_id": campaign.id, "platform": "linkedin", "text": "x", "iteration": 1},
        )
        assert resp.status_code in (401, 403)  # HTTPBearer returns 403 for missing credentials


class TestDraftList:
    async def test_get_returns_user_drafts_only(self, client, db_session, factory):
        user1 = await factory.create_user(db_session, email="draft-list-u1@test.com")
        user2 = await factory.create_user(db_session, email="draft-list-u2@test.com")
        company = await factory.create_company(db_session, email="draft-list-co@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        await db_session.commit()

        # Create drafts for both users directly
        d1 = Draft(user_id=user1.id, campaign_id=campaign.id, platform="linkedin",
                   text="u1 draft", status="pending", iteration=1)
        d2 = Draft(user_id=user2.id, campaign_id=campaign.id, platform="reddit",
                   text="u2 draft", status="pending", iteration=1)
        db_session.add(d1)
        db_session.add(d2)
        await db_session.commit()

        resp = await client.get(
            "/api/drafts",
            headers={"Authorization": f"Bearer {_user_token(user1.id)}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["user_id"] == user1.id
        assert data[0]["text"] == "u1 draft"

    async def test_get_filtered_by_campaign_id(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="draft-filter@test.com")
        company = await factory.create_company(db_session, email="draft-filter-co@test.com")
        c1 = await factory.create_campaign(db_session, company_id=company.id, title="Camp A")
        c2 = await factory.create_campaign(db_session, company_id=company.id, title="Camp B")
        await db_session.commit()

        d1 = Draft(user_id=user.id, campaign_id=c1.id, platform="linkedin",
                   text="for c1", status="pending", iteration=1)
        d2 = Draft(user_id=user.id, campaign_id=c2.id, platform="reddit",
                   text="for c2", status="pending", iteration=1)
        db_session.add(d1)
        db_session.add(d2)
        await db_session.commit()

        resp = await client.get(
            f"/api/drafts?campaign_id={c1.id}",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["campaign_id"] == c1.id

    async def test_get_nonexistent_campaign_returns_empty(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="draft-empty@test.com")
        await db_session.commit()

        resp = await client.get(
            "/api/drafts?campaign_id=99999",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestDraftPatch:
    async def test_patch_updates_status_valid_transition(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="draft-patch@test.com")
        company = await factory.create_company(db_session, email="draft-patch-co@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        await db_session.commit()

        draft = Draft(user_id=user.id, campaign_id=campaign.id, platform="linkedin",
                      text="patch me", status="pending", iteration=1)
        db_session.add(draft)
        await db_session.commit()

        resp = await client.patch(
            f"/api/drafts/{draft.id}",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"status": "approved"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    async def test_patch_rejects_invalid_transition(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="draft-badtrans@test.com")
        company = await factory.create_company(db_session, email="draft-badtrans-co@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        await db_session.commit()

        draft = Draft(user_id=user.id, campaign_id=campaign.id, platform="linkedin",
                      text="posted draft", status="posted", iteration=1)
        db_session.add(draft)
        await db_session.commit()

        # posted → pending is not allowed
        resp = await client.patch(
            f"/api/drafts/{draft.id}",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"status": "pending"},
        )
        assert resp.status_code == 422

    async def test_patch_rejects_other_user_draft(self, client, db_session, factory):
        owner = await factory.create_user(db_session, email="draft-owner@test.com")
        attacker = await factory.create_user(db_session, email="draft-attacker@test.com")
        company = await factory.create_company(db_session, email="draft-sec-co@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        await db_session.commit()

        draft = Draft(user_id=owner.id, campaign_id=campaign.id, platform="linkedin",
                      text="owner draft", status="pending", iteration=1)
        db_session.add(draft)
        await db_session.commit()

        resp = await client.patch(
            f"/api/drafts/{draft.id}",
            headers={"Authorization": f"Bearer {_user_token(attacker.id)}"},
            json={"status": "approved"},
        )
        assert resp.status_code == 403


class TestDraftImageUpload:
    async def test_upload_image_returns_url(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="draft-img@test.com")
        await db_session.commit()

        fake_image = io.BytesIO(b"\x89PNG\r\n\x1a\nfakedata")
        resp = await client.post(
            "/api/drafts/upload-image",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            files={"file": ("test.png", fake_image, "image/png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "url" in data
        assert data["url"].startswith("/draft-images/")
        assert data["url"].endswith(".png")
