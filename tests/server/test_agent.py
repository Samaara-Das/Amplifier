"""Tests for server/app/routers/agent.py — commands and status endpoints."""

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.core.security import create_access_token
from app.models.agent_command import AgentCommand
from app.models.agent_status import AgentStatus


def _user_token(user_id: int) -> str:
    return create_access_token({"sub": str(user_id), "type": "user"})


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    from app.routers import auth as auth_router
    auth_router.limiter.reset()
    yield


class TestAgentCommands:
    async def test_get_commands_empty_initially(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="agent-empty@test.com")
        await db_session.commit()

        resp = await client.get(
            "/api/agent/commands?status=pending",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_post_command_creates_pending(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="agent-create@test.com")
        await db_session.commit()

        resp = await client.post(
            "/api/agent/commands",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"type": "pause_agent", "payload": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "pause_agent"
        assert data["status"] == "pending"
        assert data["user_id"] == user.id

    async def test_post_command_invalid_type_returns_422(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="agent-badtype@test.com")
        await db_session.commit()

        resp = await client.post(
            "/api/agent/commands",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"type": "not_a_real_command", "payload": {}},
        )
        assert resp.status_code == 422

    async def test_ack_transitions_to_done(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="agent-ack@test.com")
        await db_session.commit()

        # Create a command directly
        cmd = AgentCommand(user_id=user.id, type="force_poll", payload={}, status="pending")
        db_session.add(cmd)
        await db_session.commit()

        resp = await client.post(
            f"/api/agent/commands/{cmd.id}/ack",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"result": "done"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "done"
        assert data["processed_at"] is not None

    async def test_ack_done_command_returns_400(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="agent-reack@test.com")
        await db_session.commit()

        cmd = AgentCommand(user_id=user.id, type="force_poll", payload={}, status="done")
        db_session.add(cmd)
        await db_session.commit()

        resp = await client.post(
            f"/api/agent/commands/{cmd.id}/ack",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"result": "done"},
        )
        assert resp.status_code == 400

    async def test_ack_other_user_command_returns_403(self, client, db_session, factory):
        owner = await factory.create_user(db_session, email="agent-cmdowner@test.com")
        attacker = await factory.create_user(db_session, email="agent-cmdattacker@test.com")
        await db_session.commit()

        cmd = AgentCommand(user_id=owner.id, type="pause_agent", payload={}, status="pending")
        db_session.add(cmd)
        await db_session.commit()

        resp = await client.post(
            f"/api/agent/commands/{cmd.id}/ack",
            headers={"Authorization": f"Bearer {_user_token(attacker.id)}"},
            json={"result": "done"},
        )
        assert resp.status_code == 403


class TestAgentStatus:
    async def test_get_status_404_if_never_pushed(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="agent-nostatus@test.com")
        await db_session.commit()

        resp = await client.get(
            "/api/agent/status",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
        )
        assert resp.status_code == 404

    async def test_push_status_creates_row(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="agent-pushstatus@test.com")
        await db_session.commit()

        resp = await client.post(
            "/api/agent/status",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={
                "running": True,
                "paused": False,
                "platform_health": {"linkedin": {"connected": True}},
                "ai_keys_configured": {"gemini": True},
                "version": "1.0.0",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert data["version"] == "1.0.0"
        assert data["user_id"] == user.id

    async def test_push_status_second_time_updates_same_row(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="agent-upsert-status@test.com")
        await db_session.commit()

        auth = {"Authorization": f"Bearer {_user_token(user.id)}"}
        await client.post(
            "/api/agent/status",
            headers=auth,
            json={"running": True, "paused": False, "platform_health": {}, "ai_keys_configured": {}, "version": "1.0.0"},
        )
        await client.post(
            "/api/agent/status",
            headers=auth,
            json={"running": False, "paused": True, "platform_health": {}, "ai_keys_configured": {}, "version": "1.0.1"},
        )

        # Only one row in DB
        result = await db_session.execute(
            select(AgentStatus).where(AgentStatus.user_id == user.id)
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].running is False
        assert rows[0].version == "1.0.1"

    async def test_get_status_returns_row_after_push(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="agent-getstatus@test.com")
        await db_session.commit()

        auth = {"Authorization": f"Bearer {_user_token(user.id)}"}
        await client.post(
            "/api/agent/status",
            headers=auth,
            json={"running": True, "paused": False, "platform_health": {"reddit": {"connected": False}},
                  "ai_keys_configured": {"groq": True}, "version": "2.0.0"},
        )

        resp = await client.get("/api/agent/status", headers=auth)
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert data["platform_health"] == {"reddit": {"connected": False}}
