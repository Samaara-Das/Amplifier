"""Smoke tests for company HTML dashboard routes — authentication and rendering."""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.core.security import create_access_token


# ── Rate limiter reset ─────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    from app.routers.company import login as company_login
    company_login.limiter.reset()
    yield


# ── Route lists ────────────────────────────────────────────────────────────

# All 10 company GET HTML routes (from grep)
_COMPANY_GET_ROUTES = [
    "/company/",
    "/company/login",
    "/company/campaigns",
    "/company/campaigns/new",
    "/company/billing",
    "/company/billing/success",
    "/company/influencers",
    "/company/stats",
    "/company/settings",
]

# Routes requiring auth (everything except /login — no GET /register page)
_COMPANY_PROTECTED_ROUTES = [r for r in _COMPANY_GET_ROUTES if r != "/company/login"]


# ── Helpers ────────────────────────────────────────────────────────────────

async def _get_csrf_token(client, url: str) -> str:
    resp = await client.get(url)
    return resp.cookies.get("csrf_token") or ""


def _make_company_token(company_id: int) -> str:
    return create_access_token({"sub": str(company_id), "type": "company"})


# ── Tests ──────────────────────────────────────────────────────────────────

class TestCompanyLoginPage:
    async def test_login_page_renders_unauthenticated(self, client):
        resp = await client.get("/company/login")
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "password" in body or "login" in body or "email" in body


class TestCompanyUnauthenticated:
    @pytest.mark.parametrize("route", [r for r in _COMPANY_PROTECTED_ROUTES if r != "/company/billing/success"])
    async def test_protected_routes_redirect_without_token(self, client, route):
        resp = await client.get(route, follow_redirects=False)
        assert resp.status_code in (302, 303)
        location = resp.headers.get("location", "")
        assert "login" in location.lower() or "/company" in location.lower()

    async def test_billing_success_redirects_without_token(self, client):
        # /billing/success requires session_id query param; without it FastAPI returns 422
        # With a dummy session_id: auth check runs, should redirect to login
        resp = await client.get("/company/billing/success?session_id=test_sess", follow_redirects=False)
        assert resp.status_code in (302, 303)
        location = resp.headers.get("location", "")
        assert "login" in location.lower() or "/company" in location.lower()


class TestCompanyAuthenticated:
    @pytest.mark.parametrize("route", [
        "/company/",
        "/company/campaigns",
        "/company/campaigns/new",
        "/company/billing",
        "/company/influencers",
        "/company/stats",
        "/company/settings",
    ])
    async def test_pages_render_200_with_token(self, client, db_session, factory, route):
        company = await factory.create_company(db_session, email=f"smoke-{route.replace('/', '-')}@co.com")
        await db_session.commit()
        token = _make_company_token(company.id)
        client.cookies.set("company_token", token)
        resp = await client.get(route)
        assert resp.status_code == 200, f"Expected 200 for {route}, got {resp.status_code}: {resp.text[:200]}"
        assert "traceback" not in resp.text.lower()

    async def test_billing_success_with_token_redirects(self, client, db_session, factory):
        # /billing/success with authenticated user + dummy session_id → should redirect
        # (Stripe verify will fail and redirect to billing page with error — not a 5xx)
        company = await factory.create_company(db_session, email="billing-success@co.com")
        await db_session.commit()
        token = _make_company_token(company.id)
        client.cookies.set("company_token", token)
        resp = await client.get("/company/billing/success?session_id=cs_test_dummy", follow_redirects=False)
        # Should redirect (to billing with error), not 5xx
        assert resp.status_code in (200, 302, 303)
        assert "traceback" not in resp.text.lower() if resp.status_code == 200 else True

    async def test_campaign_detail_renders_with_seeded_data(self, client, db_session, factory):
        company = await factory.create_company(db_session, email="co-detail@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        await db_session.commit()
        token = _make_company_token(company.id)
        client.cookies.set("company_token", token)
        resp = await client.get(f"/company/campaigns/{campaign.id}")
        assert resp.status_code == 200
        assert "traceback" not in resp.text.lower()


class TestCompanyRegisterLoginFlow:
    async def test_register_then_login_full_flow(self, client):
        # Get initial CSRF token
        r_login = await client.get("/company/login")
        csrf = r_login.cookies.get("csrf_token") or ""

        # Register (include csrf_token in both cookie header and form body)
        resp = await client.post(
            "/company/register",
            data={
                "name": "FlowCorp",
                "email": "flowcorp-flow@test.com",
                "password": "testpass123",
                "csrf_token": csrf,
            },
            cookies={"csrf_token": csrf},
            follow_redirects=False,
        )
        # Should redirect to /company/ after registration
        assert resp.status_code in (302, 303)
        # company_token cookie is set on successful register
        assert "company_token" in resp.cookies or "company_token" in resp.headers.get("set-cookie", "")

        # Reset limiter and get fresh CSRF for login
        from app.routers.company import login as company_login
        company_login.limiter.reset()
        r_login2 = await client.get("/company/login")
        csrf2 = r_login2.cookies.get("csrf_token") or csrf

        # Login with same creds
        resp2 = await client.post(
            "/company/login",
            data={
                "email": "flowcorp-flow@test.com",
                "password": "testpass123",
                "csrf_token": csrf2,
            },
            cookies={"csrf_token": csrf2},
            follow_redirects=False,
        )
        assert resp2.status_code in (302, 303)
        assert "company_token" in resp2.cookies or "company_token" in resp2.headers.get("set-cookie", "")
