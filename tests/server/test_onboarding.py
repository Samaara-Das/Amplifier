"""Tests for Task #75 — Web onboarding flow.

Covers:
- GET /register renders the registration form
- POST /register without ToS returns 400 and re-renders form
- POST /register valid creates user and sets user_token cookie
- GET /user/onboarding redirects to /user/onboarding/step2
"""

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci")
# Use direct-to-step2 path so tests don't attempt localhost:5222 redirects
os.environ["AMPLIFIER_UAT_SKIP_LOCAL_HANDOFF"] = "1"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_get_renders_form(client):
    """GET /register returns 200 and form fields are present."""
    resp = await client.get("/register")
    assert resp.status_code == 200
    body = resp.text
    assert "Create Account" in body or "Register" in body
    assert 'name="email"' in body
    assert 'name="password"' in body
    assert 'name="accept_tos"' in body
    # ToS links present
    assert "/terms" in body
    assert "/privacy" in body


@pytest.mark.asyncio
async def test_register_get_with_agent_param(client):
    """GET /register?agent=true preserves agent param for form POST action."""
    resp = await client.get("/register?agent=true")
    assert resp.status_code == 200
    body = resp.text
    assert "agent=true" in body


@pytest.mark.asyncio
async def test_register_post_without_tos_returns_400(client):
    """POST /register without ToS returns 400 and shows inline error."""
    # First GET to get CSRF cookie
    get_resp = await client.get("/register")
    csrf = get_resp.cookies.get("csrf_token") or ""

    resp = await client.post(
        "/register",
        data={
            "email": "test-tos@example.com",
            "password": "testpassword123",
            "csrf_token": csrf,
            # accept_tos intentionally omitted (defaults to False)
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        cookies={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    body = resp.text
    # Error message must match (?i)(must accept|terms of service|required)
    lower = body.lower()
    assert any(phrase in lower for phrase in ["must accept", "terms of service", "required"]), \
        f"Expected ToS error in body, got: {body[:500]}"
    # No JWT cookie set
    assert "user_token" not in resp.cookies


@pytest.mark.asyncio
async def test_register_post_valid_creates_user_and_sets_cookie(client):
    """POST /register with valid data creates user, sets user_token cookie, redirects."""
    get_resp = await client.get("/register")
    csrf = get_resp.cookies.get("csrf_token") or ""

    resp = await client.post(
        "/register",
        data={
            "email": "newuser-onboarding@example.com",
            "password": "validpassword123",
            "accept_tos": "true",
            "csrf_token": csrf,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        cookies={"csrf_token": csrf},
        follow_redirects=False,
    )
    # Should redirect (302)
    assert resp.status_code == 302
    # Cookie must be set
    assert "user_token" in resp.cookies
    # With AMPLIFIER_UAT_SKIP_LOCAL_HANDOFF=1, redirect target is /user/onboarding/step2
    location = resp.headers.get("location", "")
    assert "/user/onboarding/step2" in location


@pytest.mark.asyncio
async def test_register_post_duplicate_email_returns_400(client):
    """POST /register with already-registered email returns 400 with error."""
    get_resp = await client.get("/register")
    csrf = get_resp.cookies.get("csrf_token") or ""

    # Register once
    await client.post(
        "/register",
        data={
            "email": "dup-test@example.com",
            "password": "password123",
            "accept_tos": "true",
            "csrf_token": csrf,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        cookies={"csrf_token": csrf},
        follow_redirects=False,
    )

    # Need fresh CSRF for second request
    get_resp2 = await client.get("/register")
    csrf2 = get_resp2.cookies.get("csrf_token") or csrf

    resp = await client.post(
        "/register",
        data={
            "email": "dup-test@example.com",
            "password": "password123",
            "accept_tos": "true",
            "csrf_token": csrf2,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        cookies={"csrf_token": csrf2},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    lower = resp.text.lower()
    assert any(phrase in lower for phrase in ["already registered", "email", "taken", "exists"]), \
        f"Expected duplicate-email error, got: {resp.text[:500]}"


@pytest.mark.asyncio
async def test_legacy_onboarding_redirect(client):
    """GET /user/onboarding redirects to /user/onboarding/step2."""
    resp = await client.get("/user/onboarding", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("location", "")
    assert "/user/onboarding/step2" in location


@pytest.mark.asyncio
async def test_onboarding_step2_renders(client):
    """GET /user/onboarding/step2 returns 200 with platform list (no X)."""
    resp = await client.get("/user/onboarding/step2")
    assert resp.status_code == 200
    body = resp.text
    assert "LinkedIn" in body
    assert "Facebook" in body
    assert "Reddit" in body
    # X must NOT appear
    assert "badge-x" not in body
    assert "id=\"badge-x\"" not in body


@pytest.mark.asyncio
async def test_onboarding_step3_renders_with_keys_link(client):
    """GET /user/onboarding/step3 renders with link to localhost:5222/keys."""
    resp = await client.get("/user/onboarding/step3")
    assert resp.status_code == 200
    body = resp.text
    assert "Configure API" in body or "API Keys" in body
    assert "localhost:5222/keys" in body


@pytest.mark.asyncio
async def test_onboarding_step4_redirects_to_campaigns(client):
    """GET /user/onboarding/step4 redirects to /user/campaigns."""
    resp = await client.get("/user/onboarding/step4", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers.get("location", "")
    assert "/user/campaigns" in location


@pytest.mark.asyncio
async def test_register_post_agent_redirects_to_daemon_when_no_skip_flag(client):
    """POST /register?agent=true without skip flag redirects to localhost:5222/auth/callback."""
    # Remove skip flag so the daemon handoff path is active
    prev = os.environ.pop("AMPLIFIER_UAT_SKIP_LOCAL_HANDOFF", None)
    try:
        get_resp = await client.get("/register?agent=true")
        csrf = get_resp.cookies.get("csrf_token") or ""

        resp = await client.post(
            "/register?agent=true",
            data={
                "email": "daemon-redirect-test@example.com",
                "password": "validpassword123",
                "accept_tos": "true",
                "csrf_token": csrf,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            cookies={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        location = resp.headers.get("location", "")
        assert location.startswith("http://localhost:5222/auth/callback?token="), \
            f"Expected daemon callback URL, got: {location}"
        # user_token cookie must still be set
        assert "user_token" in resp.cookies
    finally:
        if prev is not None:
            os.environ["AMPLIFIER_UAT_SKIP_LOCAL_HANDOFF"] = prev
