"""Tests for server/app/routers/auth.py — user/company register, login, error cases."""

import sys
from pathlib import Path

import pytest
import pytest_asyncio

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
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_register_duplicate_email(self, client):
        """Registering the same email twice should return 400."""
        payload = {"email": "dup@example.com", "password": "pass123"}
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
        })
        assert resp.status_code == 422  # Validation error


class TestUserLogin:
    async def test_login_success(self, client):
        """Register then login with correct credentials."""
        await client.post("/api/auth/register", json={
            "email": "login@example.com",
            "password": "mypassword",
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
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data

    async def test_company_register_duplicate_email(self, client):
        payload = {
            "name": "DupCo",
            "email": "dupco@example.com",
            "password": "pass123",
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
        })
        token = reg_resp.json()["access_token"]

        resp = await client.get(
            "/api/campaigns/mine",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Should succeed (may return empty list, but 200)
        assert resp.status_code == 200
