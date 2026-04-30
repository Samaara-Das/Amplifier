"""Tests for server/app/routers/auth.py — user/company register, login, error cases."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    from app.routers import auth as auth_router
    auth_router.limiter.reset()
    yield


class TestUserRegistration:
    async def test_register_returns_token(self, client):
        resp = await client.post("/api/auth/register", json={
            "email": "new@example.com",
            "password": "securepass123",
            "accept_tos": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_register_duplicate_email(self, client):
        """Registering the same email twice should return 400."""
        payload = {"email": "dup@example.com", "password": "pass123", "accept_tos": True}
        resp1 = await client.post("/api/auth/register", json=payload)
        assert resp1.status_code == 200

        resp2 = await client.post("/api/auth/register", json=payload)
        assert resp2.status_code == 400
        assert "already registered" in resp2.json()["detail"].lower()

    async def test_register_invalid_email(self, client):
        """Invalid email format should be rejected by Pydantic validation."""
        resp = await client.post("/api/auth/register", json={
            "email": "not-an-email",
            "password": "pass123",
            "accept_tos": True,
        })
        assert resp.status_code == 422  # Validation error


class TestUserLogin:
    async def test_login_success(self, client):
        """Register then login with correct credentials."""
        await client.post("/api/auth/register", json={
            "email": "login@example.com",
            "password": "mypassword",
            "accept_tos": True,
        })

        resp = await client.post("/api/auth/login", json={
            "email": "login@example.com",
            "password": "mypassword",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data

    async def test_login_wrong_password(self, client):
        """Wrong password should return 401."""
        await client.post("/api/auth/register", json={
            "email": "wrongpw@example.com",
            "password": "correctpass",
            "accept_tos": True,
        })

        resp = await client.post("/api/auth/login", json={
            "email": "wrongpw@example.com",
            "password": "wrongpass",
        })
        assert resp.status_code == 401
        assert "invalid credentials" in resp.json()["detail"].lower()

    async def test_login_nonexistent_user(self, client):
        """Logging in with a non-existent email should return 401."""
        resp = await client.post("/api/auth/login", json={
            "email": "ghost@example.com",
            "password": "anypass",
        })
        assert resp.status_code == 401


class TestCompanyRegistration:
    async def test_company_register_returns_token(self, client):
        resp = await client.post("/api/auth/company/register", json={
            "name": "AcmeCo",
            "email": "acme@example.com",
            "password": "corppass",
            "accept_tos": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data

    async def test_company_register_duplicate_email(self, client):
        payload = {
            "name": "DupCo",
            "email": "dupco@example.com",
            "password": "pass123",
            "accept_tos": True,
        }
        resp1 = await client.post("/api/auth/company/register", json=payload)
        assert resp1.status_code == 200

        resp2 = await client.post("/api/auth/company/register", json=payload)
        assert resp2.status_code == 400


class TestCompanyLogin:
    async def test_company_login_success(self, client):
        await client.post("/api/auth/company/register", json={
            "name": "LoginCo",
            "email": "loginco@example.com",
            "password": "corppass",
            "accept_tos": True,
        })

        resp = await client.post("/api/auth/company/login", json={
            "email": "loginco@example.com",
            "password": "corppass",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_company_login_wrong_password(self, client):
        await client.post("/api/auth/company/register", json={
            "name": "WrongCo",
            "email": "wrongco@example.com",
            "password": "correctpass",
            "accept_tos": True,
        })

        resp = await client.post("/api/auth/company/login", json={
            "email": "wrongco@example.com",
            "password": "wrongpass",
        })
        assert resp.status_code == 401


class TestAuthTokenUsage:
    async def test_authenticated_endpoint_requires_token(self, client):
        """Hitting an authenticated endpoint without a token should fail."""
        resp = await client.get("/api/campaigns/mine")
        assert resp.status_code in (401, 403)

    async def test_authenticated_endpoint_with_valid_token(self, client):
        """Register, get token, use it to access a protected endpoint."""
        reg_resp = await client.post("/api/auth/register", json={
            "email": "auth@example.com",
            "password": "pass123",
            "accept_tos": True,
        })
        token = reg_resp.json()["access_token"]

        resp = await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Should succeed (may return empty list, but 200)
        assert resp.status_code == 200


class TestTosGate:
    async def test_register_user_without_tos_returns_400(self, client):
        """POST with accept_tos=false returns 400 with ToS error. No user row created."""
        resp = await client.post("/api/auth/register", json={
            "email": "notos@example.com",
            "password": "securepass123",
            "accept_tos": False,
        })
        assert resp.status_code == 400
        assert "terms of service" in resp.json()["detail"].lower()

    async def test_register_user_with_tos_sets_timestamp(self, client, db_session):
        """POST with accept_tos=true returns 200 and tos_accepted_at is set."""
        from app.models.user import User

        resp = await client.post("/api/auth/register", json={
            "email": "yestos@example.com",
            "password": "securepass123",
            "accept_tos": True,
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

        result = await db_session.execute(select(User).where(User.email == "yestos@example.com"))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.tos_accepted_at is not None
        # Should be recent (within 10 seconds of now)
        now = datetime.now(timezone.utc)
        delta = abs((now - user.tos_accepted_at.replace(tzinfo=timezone.utc) if user.tos_accepted_at.tzinfo is None else now - user.tos_accepted_at).total_seconds())
        assert delta < 10

    async def test_register_company_without_tos_returns_400(self, client):
        """POST with accept_tos=false returns 400 with ToS error. No company row created."""
        resp = await client.post("/api/auth/company/register", json={
            "name": "NoTosCo",
            "email": "notos-co@example.com",
            "password": "corppass",
            "accept_tos": False,
        })
        assert resp.status_code == 400
        assert "terms of service" in resp.json()["detail"].lower()

    async def test_register_company_with_tos_sets_timestamp(self, client, db_session):
        """POST with accept_tos=true returns 200 and tos_accepted_at is set."""
        from app.models.company import Company

        resp = await client.post("/api/auth/company/register", json={
            "name": "YesTosCo",
            "email": "yestos-co@example.com",
            "password": "corppass",
            "accept_tos": True,
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

        result = await db_session.execute(select(Company).where(Company.email == "yestos-co@example.com"))
        company = result.scalar_one_or_none()
        assert company is not None
        assert company.tos_accepted_at is not None
        now = datetime.now(timezone.utc)
        delta = abs((now - company.tos_accepted_at.replace(tzinfo=timezone.utc) if company.tos_accepted_at.tzinfo is None else now - company.tos_accepted_at).total_seconds())
        assert delta < 10

    async def test_get_terms_returns_200_with_terms_text(self, client):
        """GET /terms returns 200 and HTML body contains 'Terms' and 'Amplifier'."""
        resp = await client.get("/terms")
        assert resp.status_code == 200
        body = resp.text
        assert "Terms" in body
        assert "Amplifier" in body

    async def test_get_privacy_returns_200_with_privacy_text(self, client):
        """GET /privacy returns 200 and HTML body contains 'Privacy' and 'Amplifier'."""
        resp = await client.get("/privacy")
        assert resp.status_code == 200
        body = resp.text
        assert "Privacy" in body
        assert "Amplifier" in body
