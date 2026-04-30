"""Smoke tests for creator HTML dashboard routes — authentication and rendering."""

import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.core.security import create_access_token


# ── Rate limiter reset ─────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    from app.routers.user import login as user_login
    user_login.limiter.reset()
    yield


# ── Route lists ────────────────────────────────────────────────────────────

_USER_GET_ROUTES = [
    "/user/",
    "/user/dashboard",
    "/user/campaigns",
    "/user/posts",
    "/user/earnings",
    "/user/settings",
]

_USER_LOGIN_ROUTE = "/user/login"
_USER_PROTECTED_ROUTES = _USER_GET_ROUTES  # all require auth


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_user_token(user_id: int) -> str:
    return create_access_token({"sub": str(user_id), "type": "user"})


# ── Tests ──────────────────────────────────────────────────────────────────

class TestUserLoginPage:
    async def test_login_page_renders_unauthenticated(self, client):
        resp = await client.get("/user/login")
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "password" in body or "login" in body or "email" in body

    async def test_login_page_shows_no_register(self, client):
        """Users register via desktop app, not web."""
        resp = await client.get("/user/login")
        assert resp.status_code == 200
        # Should not have a register form pointing to /user/register
        assert "/user/register" not in resp.text

    async def test_login_page_has_html5_validation(self, client):
        """Login form fields must have type=email and required attributes."""
        resp = await client.get("/user/login")
        assert resp.status_code == 200
        body = resp.text
        assert 'type="email"' in body
        assert "required" in body


class TestUserUnauthenticated:
    @pytest.mark.parametrize("route", _USER_PROTECTED_ROUTES)
    async def test_protected_routes_redirect_without_token(self, client, route):
        resp = await client.get(route, follow_redirects=False)
        assert resp.status_code in (302, 303), f"Expected redirect for {route}, got {resp.status_code}"
        location = resp.headers.get("location", "")
        assert "login" in location.lower() or "/user" in location.lower()


class TestUserAuthenticated:
    @pytest.mark.parametrize("route", [
        "/user/",
        "/user/dashboard",
        "/user/campaigns",
        "/user/posts",
        "/user/earnings",
        "/user/settings",
    ])
    async def test_pages_render_200_with_token(self, client, db_session, factory, route):
        user = await factory.create_user(db_session, email=f"user-smoke{route.replace('/', '-')}@test.com")
        await db_session.commit()
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        resp = await client.get(route)
        assert resp.status_code == 200, f"Expected 200 for {route}, got {resp.status_code}: {resp.text[:400]}"
        assert "traceback" not in resp.text.lower()

    async def test_dashboard_contains_nav_items(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="user-nav@test.com")
        await db_session.commit()
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        resp = await client.get("/user/")
        assert resp.status_code == 200
        body = resp.text.lower()
        # Check all 5 nav items are present
        assert "campaigns" in body
        assert "posts" in body
        assert "earnings" in body
        assert "settings" in body

    async def test_campaigns_page_has_tabs(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="user-tabs@test.com")
        await db_session.commit()
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        resp = await client.get("/user/campaigns")
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "invitations" in body
        assert "active" in body
        assert "completed" in body

    async def test_earnings_page_shows_stripe_gate_when_no_account(self, client, db_session, factory):
        """AC27: no stripe_account_id → show 'Connect Bank Account' gate."""
        user = await factory.create_user(db_session, email="user-earnings-nostripe@test.com")
        await db_session.commit()
        assert user.stripe_account_id is None
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        resp = await client.get("/user/earnings")
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "connect" in body  # "Connect Bank Account" or similar

    async def test_earnings_page_shows_withdraw_when_stripe_connected(self, client, db_session, factory):
        """AC27: stripe_account_id present → show withdraw form."""
        user = await factory.create_user(db_session, email="user-earnings-stripe@test.com")
        user.stripe_account_id = "acct_test_123"
        await db_session.commit()
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        resp = await client.get("/user/earnings")
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "withdraw" in body

    async def test_campaign_detail_requires_assignment(self, client, db_session, factory):
        """Campaign detail for a campaign the user isn't assigned to should not 5xx."""
        company = await factory.create_company(db_session, email="co-for-user-detail@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        user = await factory.create_user(db_session, email="user-noassign@test.com")
        await db_session.commit()
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        resp = await client.get(f"/user/campaigns/{campaign.id}")
        # Should return 200 (with error message) not 5xx
        assert resp.status_code == 200
        assert "traceback" not in resp.text.lower()

    async def test_campaign_detail_with_assignment(self, client, db_session, factory):
        """Campaign detail renders with user's own assignment."""
        company = await factory.create_company(db_session, email="co-for-user-detail2@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        user = await factory.create_user(db_session, email="user-withassign@test.com")
        await factory.create_assignment(db_session, campaign_id=campaign.id, user_id=user.id)
        await db_session.commit()
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        resp = await client.get(f"/user/campaigns/{campaign.id}")
        assert resp.status_code == 200
        assert "traceback" not in resp.text.lower()
        assert campaign.title.lower() in resp.text.lower() or campaign.title in resp.text

    async def test_campaigns_tab_partial_htmx(self, client, db_session, factory):
        """HTMX tab partial returns 200."""
        user = await factory.create_user(db_session, email="user-htmx-tab@test.com")
        await db_session.commit()
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        for tab in ("invitations", "active", "completed"):
            resp = await client.get(f"/user/campaigns/_tab/{tab}",
                                    headers={"HX-Request": "true"})
            assert resp.status_code == 200, f"Tab {tab} failed: {resp.text[:200]}"

    async def test_draft_review_links_to_desktop_app(self, client, db_session, factory):
        """AC8: campaign detail links to localhost:5222/drafts/{id}."""
        company = await factory.create_company(db_session, email="co-ac8@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        user = await factory.create_user(db_session, email="user-ac8@test.com")
        await factory.create_assignment(db_session, campaign_id=campaign.id, user_id=user.id)
        await db_session.commit()
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        resp = await client.get(f"/user/campaigns/{campaign.id}")
        assert resp.status_code == 200
        assert f"localhost:5222/drafts/{campaign.id}" in resp.text

    async def test_posts_page_has_copy_button(self, client, db_session, factory):
        """AC14: posts table includes copyButton Alpine component for post URLs."""
        company = await factory.create_company(db_session, email="co-copy-btn@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        user = await factory.create_user(db_session, email="user-copy-btn@test.com")
        assignment = await factory.create_assignment(db_session, campaign_id=campaign.id, user_id=user.id)
        await factory.create_post(db_session, assignment_id=assignment.id, platform="linkedin",
                                  post_url="https://linkedin.com/posts/test123")
        await db_session.commit()
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        resp = await client.get("/user/posts")
        assert resp.status_code == 200
        assert "copyButton" in resp.text

    async def test_status_display_labels(self, client, db_session, factory):
        """AC13: status labels use display names not raw values."""
        company = await factory.create_company(db_session, email="co-labels@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        user = await factory.create_user(db_session, email="user-labels@test.com")
        await factory.create_assignment(db_session, campaign_id=campaign.id, user_id=user.id,
                                        status="content_generated")
        await db_session.commit()
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        # content_generated assignments appear in the "active" tab
        resp = await client.get("/user/campaigns?tab=active")
        assert resp.status_code == 200
        # "Draft Ready" should appear, not "content_generated"
        assert "Draft Ready" in resp.text

    async def test_settings_shows_platforms(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="user-settings-plat@test.com",
                                         platforms={"linkedin": True, "facebook": True})
        await db_session.commit()
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        resp = await client.get("/user/settings")
        assert resp.status_code == 200
        assert "linkedin" in resp.text.lower() or "LinkedIn" in resp.text


class TestUserLoginFlow:
    async def test_login_with_valid_creds_sets_cookie(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="user-login-flow@test.com",
                                         password="testpass123")
        await db_session.commit()

        r_login = await client.get("/user/login")
        csrf = r_login.cookies.get("csrf_token") or ""

        from app.routers.user import login as user_login
        user_login.limiter.reset()

        resp = await client.post(
            "/user/login",
            data={
                "email": "user-login-flow@test.com",
                "password": "testpass123",
                "csrf_token": csrf,
            },
            cookies={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303), f"Expected redirect, got {resp.status_code}: {resp.text[:200]}"
        assert "user_token" in resp.cookies or "user_token" in resp.headers.get("set-cookie", "")

    async def test_login_with_invalid_creds_returns_401(self, client, db_session, factory):
        await factory.create_user(db_session, email="user-bad-login@test.com",
                                  password="correctpass")
        await db_session.commit()

        r_login = await client.get("/user/login")
        csrf = r_login.cookies.get("csrf_token") or ""

        from app.routers.user import login as user_login
        user_login.limiter.reset()

        resp = await client.post(
            "/user/login",
            data={
                "email": "user-bad-login@test.com",
                "password": "wrongpass",
                "csrf_token": csrf,
            },
            cookies={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 401

    async def test_logout_clears_cookie(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="user-logout@test.com")
        await db_session.commit()
        token = _make_user_token(user.id)
        client.cookies.set("user_token", token)
        resp = await client.get("/user/logout", follow_redirects=False)
        assert resp.status_code in (302, 303)
        location = resp.headers.get("location", "")
        assert "login" in location.lower()
