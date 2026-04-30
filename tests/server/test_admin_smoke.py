"""Smoke tests for admin HTML dashboard routes — authentication and rendering."""

import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.routers.admin import ADMIN_TOKEN_VALUE, ADMIN_PASSWORD
from app.core.security import create_access_token


# ── Rate limiter reset ─────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    from app.routers.admin import login as admin_login
    admin_login.limiter.reset()
    yield


# ── Route lists ────────────────────────────────────────────────────────────

# All 14 admin GET HTML routes (from grep -hE '@router.get.*HTMLResponse' server/app/routers/admin/*.py)
_ADMIN_GET_ROUTES = [
    "/admin/",
    "/admin/login",
    "/admin/users",
    "/admin/companies",
    "/admin/campaigns",
    "/admin/financial",
    "/admin/fraud",
    "/admin/analytics",
    "/admin/review-queue",
    "/admin/audit-log",
    "/admin/settings",
]

# Routes that require auth (everything except /admin/login)
_ADMIN_PROTECTED_ROUTES = [r for r in _ADMIN_GET_ROUTES if r != "/admin/login"]

# Detail routes need an ID; we parametrize them separately
_ADMIN_DETAIL_ROUTES = [
    "/admin/users/1",
    "/admin/companies/1",
    "/admin/campaigns/1",
]

_ADMIN_ALL_AUTHENTICATED_ROUTES = _ADMIN_PROTECTED_ROUTES + _ADMIN_DETAIL_ROUTES


# ── Helpers ────────────────────────────────────────────────────────────────

async def _get_csrf_token(client, url: str) -> str:
    """GET a page, extract csrf_token from Set-Cookie header."""
    resp = await client.get(url)
    csrf = resp.cookies.get("csrf_token") or ""
    return csrf


# ── Tests ──────────────────────────────────────────────────────────────────

class TestAdminLoginPage:
    async def test_login_page_renders_unauthenticated(self, client):
        resp = await client.get("/admin/login")
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "password" in body or "login" in body


class TestAdminUnauthenticated:
    @pytest.mark.parametrize("route", _ADMIN_PROTECTED_ROUTES)
    async def test_protected_routes_redirect_without_token(self, client, route):
        resp = await client.get(route, follow_redirects=False)
        # Must redirect to login — not serve real content
        assert resp.status_code in (302, 303)
        location = resp.headers.get("location", "")
        assert "login" in location.lower() or "/admin" in location.lower()


class TestAdminAuthenticated:
    @pytest.mark.parametrize("route", _ADMIN_PROTECTED_ROUTES)
    async def test_pages_render_200_with_token(self, client, route):
        client.cookies.set("admin_token", ADMIN_TOKEN_VALUE)
        resp = await client.get(route)
        assert resp.status_code == 200
        assert "traceback" not in resp.text.lower()

    async def test_detail_routes_render_with_seeded_data(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="admin-smoke@test.com")
        company = await factory.create_company(db_session, email="admin-smoke-co@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        await db_session.commit()

        client.cookies.set("admin_token", ADMIN_TOKEN_VALUE)
        for route in [
            f"/admin/users/{user.id}",
            f"/admin/companies/{company.id}",
            f"/admin/campaigns/{campaign.id}",
        ]:
            resp = await client.get(route)
            assert resp.status_code == 200, f"Expected 200 for {route}, got {resp.status_code}"
            assert "traceback" not in resp.text.lower()


class TestAdminLoginPost:
    async def test_correct_password_redirects_and_sets_cookie(self, client):
        csrf = await _get_csrf_token(client, "/admin/login")
        client.cookies.set("csrf_token", csrf)
        resp = await client.post(
            "/admin/login",
            data={"password": ADMIN_PASSWORD, "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)
        assert "admin_token" in resp.cookies

    async def test_wrong_password_does_not_set_cookie(self, client):
        csrf = await _get_csrf_token(client, "/admin/login")
        client.cookies.set("csrf_token", csrf)
        resp = await client.post(
            "/admin/login",
            data={"password": "wrong-password-xyz", "csrf_token": csrf},
            follow_redirects=False,
        )
        # No admin_token cookie should be set on wrong password
        assert "admin_token" not in resp.cookies
