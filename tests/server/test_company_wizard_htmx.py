"""Tests for company campaign wizard HTMX upgrade (Chunk 4, Task #66).

AC4: campaign wizard autosave wired up in template (presence of x-data="autosave" + localStorage key)
AC5: multi-step wizard uses Alpine x-show (not page reloads) — verified by single-form structure
AC19: manual creation E2E — POST /company/campaigns/new with all required fields creates Campaign row
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.core.security import create_access_token


def _make_company_token(company_id: int) -> str:
    return create_access_token({"sub": str(company_id), "type": "company"})


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.routers.company import login as company_login
    company_login.limiter.reset()
    yield


# ── Tests ────────────────────────────────────────────────────────────────────


class TestCompanyWizardPage:
    """GET /company/campaigns/new — manual wizard page renders."""

    async def test_wizard_page_renders_200(self, client, db_session, factory):
        company = await factory.create_company(db_session, email="wiz1@co.com")
        await db_session.commit()
        client.cookies.set("company_token", _make_company_token(company.id))
        resp = await client.get("/company/campaigns/new")
        assert resp.status_code == 200
        assert "traceback" not in resp.text.lower()

    async def test_wizard_page_contains_autosave_directive(self, client, db_session, factory):
        """AC4: autosave Alpine component wired to the wizard form."""
        company = await factory.create_company(db_session, email="wiz2@co.com")
        await db_session.commit()
        client.cookies.set("company_token", _make_company_token(company.id))
        resp = await client.get("/company/campaigns/new")
        assert resp.status_code == 200
        assert "autosave" in resp.text
        assert "wizard_draft" in resp.text

    async def test_wizard_page_contains_all_four_steps(self, client, db_session, factory):
        """AC5: all 4 steps are in one form (Alpine x-show, no page reloads)."""
        company = await factory.create_company(db_session, email="wiz3@co.com")
        await db_session.commit()
        client.cookies.set("company_token", _make_company_token(company.id))
        resp = await client.get("/company/campaigns/new")
        assert resp.status_code == 200
        # All 4 step sections should be present as x-show divs
        assert resp.text.count('x-show="currentStep') >= 4
        # Single form posts to /company/campaigns/new
        assert 'action="/company/campaigns/new"' in resp.text

    async def test_wizard_unauthenticated_redirects(self, client):
        resp = await client.get("/company/campaigns/new", follow_redirects=False)
        assert resp.status_code in (302, 303)


class TestCampaignCreateE2E:
    """AC19: POST /company/campaigns/new with all required fields creates a Campaign row.

    The route redirects to /company/campaigns/{id}?success=... only when a Campaign
    row is created. A redirect with a numeric ID in the path proves the row exists.
    """

    async def test_create_campaign_e2e(self, client, db_session, factory):
        company = await factory.create_company(db_session, email="wiz-e2e@co.com", balance=5000.0)
        await db_session.commit()
        client.cookies.set("company_token", _make_company_token(company.id))

        # Get CSRF token first (required by CSRFMiddleware for form POSTs)
        get_resp = await client.get("/company/campaigns/new")
        csrf = get_resp.cookies.get("csrf_token") or ""

        now = datetime.now(timezone.utc)
        start = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        end = (now + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M")

        resp = await client.post(
            "/company/campaigns/new",
            data={
                "title": "Wizard E2E Campaign",
                "brief": "Test brief for wizard E2E campaign creation.",
                "budget": "200.00",
                "start_date": start,
                "end_date": end,
                "campaign_type": "ai_generated",
                "rate_per_1k_impressions": "0.50",
                "rate_per_like": "0.01",
                "rate_per_repost": "0",
                "min_followers_json": "{}",
                "csrf_token": csrf,
            },
            cookies={"csrf_token": csrf},
            follow_redirects=False,
        )
        # Route only redirects to /company/campaigns/{numeric_id} when the Campaign
        # row is successfully committed. Any error (quality gate, missing fields,
        # insufficient balance) returns a 4xx response, not a redirect.
        assert resp.status_code in (302, 303), f"Expected redirect, got {resp.status_code}: {resp.text[:300]}"
        location = resp.headers.get("location", "")
        # Location must be /company/campaigns/{integer} (detail page), not list page
        assert "/company/campaigns/" in location
        # Extract the campaign ID segment
        path_parts = location.split("/company/campaigns/")
        assert len(path_parts) == 2
        campaign_id_part = path_parts[1].split("?")[0]  # strip query string
        assert campaign_id_part.isdigit(), f"Expected numeric campaign ID in redirect, got: {location}"
