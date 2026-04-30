"""Tests for server/app/routers/users.py — profile, earnings, payout endpoints."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.core.security import create_access_token
from app.models.payout import Payout


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    from app.routers import auth as auth_router
    auth_router.limiter.reset()
    yield


def _user_token(user_id: int) -> str:
    return create_access_token({"sub": str(user_id), "type": "user"})


class TestGetMe:
    async def test_get_me_returns_profile(self, client, db_session, factory):
        user = await factory.create_user(
            db_session,
            email="getme@test.com",
            niche_tags=["tech", "finance"],
            audience_region="us",
        )
        await db_session.commit()

        resp = await client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "getme@test.com"
        assert data["tier"] == "seedling"
        assert data["audience_region"] == "us"
        assert "tech" in data["niche_tags"]

    async def test_unauthenticated_returns_401(self, client):
        resp = await client.get("/api/users/me")
        assert resp.status_code == 401 or resp.status_code == 403


class TestPatchMe:
    async def test_patch_niche_tags_and_region(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="patchme@test.com")
        await db_session.commit()

        resp = await client.patch(
            "/api/users/me",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"niche_tags": ["lifestyle", "travel"], "audience_region": "eu"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["audience_region"] == "eu"
        assert "lifestyle" in data["niche_tags"]

        # Verify DB updated
        await db_session.refresh(user)
        assert user.audience_region == "eu"
        assert "lifestyle" in user.niche_tags

    async def test_patch_invalid_mode_returns_400(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="patch-mode@test.com")
        await db_session.commit()

        resp = await client.patch(
            "/api/users/me",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"mode": "warp_speed"},
        )
        assert resp.status_code == 400


class TestGetEarnings:
    async def test_earnings_returns_all_fields(self, client, db_session, factory):
        user = await factory.create_user(
            db_session,
            email="earnings@test.com",
        )
        # Set balances directly
        user.earnings_balance = 50.00
        user.total_earned = 100.00
        await db_session.commit()

        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total_earned" in data
        assert "current_balance" in data
        assert "available_balance" in data
        assert "pending" in data
        assert "per_campaign" in data
        assert "per_platform" in data
        assert "payout_history" in data
        assert data["total_earned"] == 100.0
        assert data["current_balance"] == 50.0

    async def test_earnings_with_no_payouts_returns_zeros(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="earnings-zero@test.com")
        await db_session.commit()

        resp = await client.get(
            "/api/users/me/earnings",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending"] == 0.0
        assert data["per_campaign"] == []
        assert data["payout_history"] == []


class TestPayoutRequest:
    async def test_payout_with_stripe_account_creates_record(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="payout-ok@test.com")
        user.earnings_balance = 50.00
        user.stripe_account_id = "acct_test_123456"
        await db_session.commit()

        resp = await client.post(
            "/api/users/me/payout",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"amount": 25.00},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert abs(data["amount"] - 25.0) < 0.01
        assert abs(data["new_balance"] - 25.0) < 0.01

        # Verify DB record
        await db_session.refresh(user)
        assert float(user.earnings_balance) < 50.0

    async def test_payout_without_stripe_connect_returns_400(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="payout-no-stripe@test.com")
        user.earnings_balance = 50.00
        user.stripe_account_id = None
        await db_session.commit()

        resp = await client.post(
            "/api/users/me/payout",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"amount": 25.00},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "stripe" in detail or "connect" in detail or "bank" in detail

    async def test_payout_below_minimum_returns_400(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="payout-min@test.com")
        user.earnings_balance = 50.00
        user.stripe_account_id = "acct_test_min"
        await db_session.commit()

        resp = await client.post(
            "/api/users/me/payout",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"amount": 5.00},  # Below $10 minimum
        )
        assert resp.status_code == 400

    async def test_payout_exceeds_balance_returns_400(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="payout-exceed@test.com")
        user.earnings_balance = 15.00
        user.stripe_account_id = "acct_test_exceed"
        await db_session.commit()

        resp = await client.post(
            "/api/users/me/payout",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"amount": 50.00},
        )
        assert resp.status_code == 400
