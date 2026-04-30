"""Tests for admin HTMX upgrades — partial swaps, bulk actions, command palette."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.routers.admin import ADMIN_TOKEN_VALUE


# ── Rate limiter reset ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.routers.admin import login as admin_login
    admin_login.limiter.reset()


# ── HTMX partial swap tests ────────────────────────────────────────────────

class TestAdminUsersHtmxPartial:
    async def test_full_page_without_hx_request(self, client):
        """GET /admin/users without HX-Request returns full HTML page."""
        client.cookies.set("admin_token", ADMIN_TOKEN_VALUE)
        resp = await client.get("/admin/users")
        assert resp.status_code == 200
        body = resp.text
        # Full page has the base layout structure
        assert "sidebar" in body or "Admin Dashboard" in body
        assert "users-tbody" in body

    async def test_partial_with_hx_request(self, client):
        """GET /admin/users with HX-Request header returns only tbody partial."""
        client.cookies.set("admin_token", ADMIN_TOKEN_VALUE)
        resp = await client.get("/admin/users", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        body = resp.text
        # Partial should NOT have full page structure
        assert "<!DOCTYPE html>" not in body
        assert "<html" not in body

    async def test_filter_narrows_results(self, client, db_session, factory):
        """Search filter returns only matching users in partial."""
        user = await factory.create_user(db_session, email="htmx-test-unique@example.com")
        await factory.create_user(db_session, email="other-user@example.com")
        await db_session.commit()

        client.cookies.set("admin_token", ADMIN_TOKEN_VALUE)
        resp = await client.get(
            "/admin/users?search=htmx-test-unique",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        body = resp.text
        assert "htmx-test-unique@example.com" in body
        assert "other-user@example.com" not in body

    async def test_pagination_in_partial(self, client, db_session, factory):
        """Page param works in HTMX partial — returns 200 with pagination context."""
        client.cookies.set("admin_token", ADMIN_TOKEN_VALUE)
        resp = await client.get(
            "/admin/users?page=1",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        # No server error
        assert "traceback" not in resp.text.lower()


# ── Bulk suspend tests ─────────────────────────────────────────────────────

class TestBulkSuspend:
    async def test_bulk_suspend_success(self, client, db_session, factory):
        """POST /admin/users/bulk/suspend suspends all targeted active users."""
        from sqlalchemy import select
        from app.models.user import User

        u1 = await factory.create_user(db_session, email="bulk1@test.com")
        u2 = await factory.create_user(db_session, email="bulk2@test.com")
        await db_session.commit()

        client.cookies.set("admin_token", ADMIN_TOKEN_VALUE)
        resp = await client.post(
            "/admin/users/bulk/suspend",
            json={"ids": [u1.id, u2.id]},
        )
        assert resp.status_code == 200

        # Verify DB state
        await db_session.refresh(u1)
        await db_session.refresh(u2)
        assert u1.status == "suspended"
        assert u2.status == "suspended"

    async def test_bulk_suspend_writes_audit_log(self, client, db_session, factory):
        """Bulk suspend writes one audit_log row per suspended user."""
        from sqlalchemy import select
        from app.models.audit_log import AuditLog

        u = await factory.create_user(db_session, email="bulk-audit@test.com")
        await db_session.commit()

        client.cookies.set("admin_token", ADMIN_TOKEN_VALUE)
        await client.post(
            "/admin/users/bulk/suspend",
            json={"ids": [u.id]},
        )

        logs = (await db_session.execute(
            select(AuditLog)
            .where(AuditLog.target_type == "user")
            .where(AuditLog.target_id == u.id)
            .where(AuditLog.action == "user_suspended")
        )).scalars().all()
        assert len(logs) >= 1

    async def test_bulk_suspend_idempotent_already_suspended(self, client, db_session, factory):
        """Bulk suspending an already-suspended user keeps status suspended and doesn't error."""
        from sqlalchemy import select
        from app.models.user import User

        u = await factory.create_user(db_session, email="already-suspended@test.com")
        u.status = "suspended"
        await db_session.commit()

        client.cookies.set("admin_token", ADMIN_TOKEN_VALUE)
        resp = await client.post(
            "/admin/users/bulk/suspend",
            json={"ids": [u.id]},
        )
        assert resp.status_code == 200

        await db_session.refresh(u)
        assert u.status == "suspended"


# ── Command palette test ────────────────────────────────────────────────────

class TestCommandPalette:
    async def test_nav_html_contains_command_palette_items(self, client):
        """Any admin page's HTML includes command palette nav links."""
        client.cookies.set("admin_token", ADMIN_TOKEN_VALUE)
        resp = await client.get("/admin/")
        assert resp.status_code == 200
        body = resp.text
        # Command palette markup should be in the page
        assert "commandPalette" in body
        # Navigation items should be listed
        assert "/admin/users" in body
        assert "/admin/financial" in body
        assert "Run Billing Now" in body
