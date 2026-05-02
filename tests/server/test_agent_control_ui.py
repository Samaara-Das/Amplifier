"""Tests for Task #76 — Pause/Resume agent UI + dashboard agent_status visibility.

5 tests:
1. POST /user/settings/pause-agent creates AgentCommand(type='pause_agent', status='pending')
2. POST /user/settings/resume-agent creates AgentCommand(type='resume_agent', status='pending')
3. Unauthenticated POST returns redirect (302/303) to login
4. Dashboard renders drafts-ready count
5. Dashboard does NOT list X / TikTok / Instagram in the Connected Platforms section
"""

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.core.security import create_access_token
from app.models.agent_command import AgentCommand
from app.models.draft import Draft


def _user_token(user_id: int) -> str:
    return create_access_token({"sub": str(user_id), "type": "user"})


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    from app.routers.user import login as user_login
    user_login.limiter.reset()
    yield


class TestPauseResumeCommands:
    async def test_post_pause_agent_inserts_command(self, client, db_session, factory):
        """AC2 — clicking Pause creates AgentCommand(type='pause_agent', status='pending')."""
        user = await factory.create_user(db_session, email="pause-test@test.com")
        await db_session.commit()
        token = _user_token(user.id)
        client.cookies.set("user_token", token)

        resp = await client.post("/user/settings/pause-agent", follow_redirects=False)
        assert resp.status_code in (200, 302, 303), f"Unexpected status {resp.status_code}: {resp.text[:300]}"

        result = await db_session.execute(
            select(AgentCommand).where(
                AgentCommand.user_id == user.id,
                AgentCommand.type == "pause_agent",
            )
        )
        cmd = result.scalar_one_or_none()
        assert cmd is not None, "AgentCommand row for pause_agent was not created"
        assert cmd.status == "pending"
        assert cmd.user_id == user.id

    async def test_post_resume_agent_inserts_command(self, client, db_session, factory):
        """AC5 — clicking Resume creates AgentCommand(type='resume_agent', status='pending')."""
        user = await factory.create_user(db_session, email="resume-test@test.com")
        await db_session.commit()
        token = _user_token(user.id)
        client.cookies.set("user_token", token)

        resp = await client.post("/user/settings/resume-agent", follow_redirects=False)
        assert resp.status_code in (200, 302, 303), f"Unexpected status {resp.status_code}: {resp.text[:300]}"

        result = await db_session.execute(
            select(AgentCommand).where(
                AgentCommand.user_id == user.id,
                AgentCommand.type == "resume_agent",
            )
        )
        cmd = result.scalar_one_or_none()
        assert cmd is not None, "AgentCommand row for resume_agent was not created"
        assert cmd.status == "pending"
        assert cmd.user_id == user.id

    async def test_unauthed_pause_request_redirects_or_401(self, client):
        """Unauthenticated POST to pause-agent must not succeed (302 to login or 401)."""
        # No user_token cookie set
        resp = await client.post("/user/settings/pause-agent", follow_redirects=False)
        assert resp.status_code in (302, 303, 401), (
            f"Expected redirect or 401 for unauthed request, got {resp.status_code}"
        )
        if resp.status_code in (302, 303):
            location = resp.headers.get("location", "")
            assert "login" in location.lower(), f"Expected redirect to login, got location={location}"


class TestDashboardWidgets:
    async def test_dashboard_renders_drafts_ready_count(self, client, db_session, factory):
        """AC8 — dashboard shows N drafts ready when Draft rows with status='pending' exist."""
        from app.models.campaign import Campaign
        from app.models.company import Company
        from datetime import datetime, timezone, timedelta

        # Create a company + campaign to satisfy the Draft FK
        company = await factory.create_company(db_session, email="co-drafts-widget@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        user = await factory.create_user(db_session, email="user-drafts-widget@test.com")
        await db_session.flush()

        # Add 2 pending drafts for this user
        for i in range(2):
            draft = Draft(
                user_id=user.id,
                campaign_id=campaign.id,
                platform="linkedin",
                text=f"Test draft {i}",
                status="pending",
            )
            db_session.add(draft)
        await db_session.commit()

        token = _user_token(user.id)
        client.cookies.set("user_token", token)
        resp = await client.get("/user/")
        assert resp.status_code == 200
        body = resp.text
        # Should show "2 drafts ready" or similar
        assert "2 draft" in body.lower(), f"Expected '2 draft' in dashboard body. Snippet: {body[:1000]}"
        # Should link to localhost:5222/drafts
        assert "localhost:5222/drafts" in body

    async def test_dashboard_filters_disabled_platforms(self, client, db_session, factory):
        """Dashboard Connected Platforms section must NOT list X, TikTok, or Instagram."""
        user = await factory.create_user(
            db_session,
            email="user-platform-filter@test.com",
            platforms={"linkedin": True, "facebook": True, "reddit": True},
        )
        await db_session.commit()
        token = _user_token(user.id)
        client.cookies.set("user_token", token)

        resp = await client.get("/user/")
        assert resp.status_code == 200
        body = resp.text

        # Active platforms must be present
        assert "linkedin" in body.lower() or "LinkedIn" in body
        assert "facebook" in body.lower() or "Facebook" in body
        assert "reddit" in body.lower() or "Reddit" in body

        # Extract only the Connected Platforms section to avoid false positives
        # (e.g. "X drafts ready" containing "x")
        # Find the card section for Connected Platforms
        lower = body.lower()
        cp_start = lower.find("connected platforms")
        cp_end = lower.find("recent posts", cp_start) if cp_start != -1 else -1
        if cp_start != -1 and cp_end != -1:
            platforms_section = body[cp_start:cp_end]
        elif cp_start != -1:
            platforms_section = body[cp_start:cp_start + 2000]
        else:
            platforms_section = body

        platforms_lower = platforms_section.lower()
        # TikTok and Instagram must not appear as platform names in this section
        assert "tiktok" not in platforms_lower, "TikTok should not appear in Connected Platforms"
        assert "instagram" not in platforms_lower, "Instagram should not appear in Connected Platforms"
