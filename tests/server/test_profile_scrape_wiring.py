"""Tests for Task #86 — Profile Scraping Pipeline wiring.

Covers:
1. post_agent_command helper exists in server_client with expected signature
2. Admin refresh-profile endpoint inserts AgentCommand row with correct type + payload
3. AMPLIFIER_UAT_PROFILE_REFRESH_NOW=1 shortens PROFILE_REFRESH_INTERVAL to 30s
4. _handle_scrape_profiles calls scrape_all_profiles directly (bypassing staleness) when
   platforms are specified in the payload — not refresh_profiles()
"""

import importlib
import inspect
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci")

from app.routers.admin import ADMIN_TOKEN_VALUE


# ---------------------------------------------------------------------------
# Test 1: post_agent_command helper exists in server_client
# ---------------------------------------------------------------------------

class TestPostAgentCommandHelper:
    def test_post_agent_command_helper_exists(self):
        """post_agent_command must be importable and accept (command_type, payload)."""
        scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
        sys.path.insert(0, str(scripts_dir))
        try:
            from utils.server_client import post_agent_command
        except ImportError as exc:
            pytest.fail(f"Could not import post_agent_command from utils.server_client: {exc}")

        sig = inspect.signature(post_agent_command)
        params = list(sig.parameters.keys())
        assert "command_type" in params, (
            f"post_agent_command must have 'command_type' parameter, got: {params}"
        )
        assert "payload" in params, (
            f"post_agent_command must have 'payload' parameter, got: {params}"
        )


# ---------------------------------------------------------------------------
# Test 2: Admin refresh-profile endpoint inserts AgentCommand row
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_engine_t2():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool
    from app.core.database import Base
    from app.models.agent_command import AgentCommand  # noqa: F401 ensure table registered

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client_t2(db_engine_t2):
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from app.core.database import get_db
    from app.main import app

    session_factory = async_sessionmaker(
        db_engine_t2, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session_t2(db_engine_t2):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    session_factory = async_sessionmaker(
        db_engine_t2, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


class TestAdminRefreshProfileEndpoint:
    async def test_admin_refresh_profile_endpoint_inserts_agent_command(
        self, client_t2, db_session_t2
    ):
        """POST /admin/users/<id>/refresh-profile must return 302 and insert AgentCommand row."""
        from app.core.security import hash_password
        from app.models.user import User
        from app.models.agent_command import AgentCommand
        from sqlalchemy import select

        # Seed a user
        user = User(
            email="profile-refresh-test@test.com",
            password_hash=hash_password("testpass"),
            tier="seedling",
            trust_score=50,
            platforms={"linkedin": True},
            follower_counts={"linkedin": 100},
            niche_tags=["finance"],
            audience_region="us",
            successful_post_count=0,
            earnings_balance=0.0,
            earnings_balance_cents=0,
            total_earned=0.0,
            total_earned_cents=0,
        )
        db_session_t2.add(user)
        await db_session_t2.flush()
        user_id = user.id

        client_t2.cookies.set("admin_token", ADMIN_TOKEN_VALUE)
        resp = await client_t2.post(
            f"/admin/users/{user_id}/refresh-profile", follow_redirects=False
        )
        assert resp.status_code in (302, 303), (
            f"Expected redirect, got {resp.status_code}: {resp.text[:200]}"
        )
        assert "error" not in resp.headers.get("location", ""), (
            f"Redirect location contains error: {resp.headers.get('location')}"
        )

        # Verify AgentCommand row was created
        result = await db_session_t2.execute(
            select(AgentCommand)
            .where(AgentCommand.user_id == user_id)
            .where(AgentCommand.type == "scrape_profiles")
        )
        cmd = result.scalar_one_or_none()
        assert cmd is not None, "AgentCommand row not created after admin refresh-profile POST"
        assert cmd.status == "pending"
        payload = cmd.payload or {}
        assert "platforms" in payload, f"Command payload missing 'platforms' key: {payload}"
        assert isinstance(payload["platforms"], list)
        assert len(payload["platforms"]) > 0


# ---------------------------------------------------------------------------
# Test 3: AMPLIFIER_UAT_PROFILE_REFRESH_NOW=1 shortens PROFILE_REFRESH_INTERVAL
# ---------------------------------------------------------------------------

class TestUatProfileRefreshNowFlag:
    def test_uat_profile_refresh_now_flag_shortens_interval(self):
        """When AMPLIFIER_UAT_PROFILE_REFRESH_NOW=1, PROFILE_REFRESH_INTERVAL must be 30."""
        scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        # Set the flag and force re-import
        os.environ["AMPLIFIER_UAT_PROFILE_REFRESH_NOW"] = "1"
        try:
            import background_agent
            importlib.reload(background_agent)
            assert background_agent.PROFILE_REFRESH_INTERVAL == 30, (
                f"Expected PROFILE_REFRESH_INTERVAL=30 when flag is set, "
                f"got {background_agent.PROFILE_REFRESH_INTERVAL}"
            )
        finally:
            del os.environ["AMPLIFIER_UAT_PROFILE_REFRESH_NOW"]
            # Reload back to default so other tests aren't affected
            import background_agent as _ba
            importlib.reload(_ba)


# ---------------------------------------------------------------------------
# Test 4: _handle_scrape_profiles bypasses staleness when platforms specified
# ---------------------------------------------------------------------------

class TestHandleScrapeProfilesBypassesStaleness:
    async def test_handle_scrape_profiles_calls_scrape_all_directly_when_platforms_given(self):
        """_handle_scrape_profiles must call scrape_all_profiles directly (bypassing staleness)
        when platforms are provided in the payload — NOT route through refresh_profiles().

        Without this, connecting a platform and immediately requesting a scrape would be
        a no-op because refresh_profiles() skips fresh rows (age 0s < 604800s threshold).
        """
        scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        import background_agent

        # Build a minimal fake agent (only .paused is checked in the handler)
        fake_agent = MagicMock()
        fake_agent.paused = False

        handlers = background_agent._get_command_handlers(fake_agent)
        handler = handlers["scrape_profiles"]

        mock_scrape_all = AsyncMock(return_value={"linkedin": {"display_name": "Test"}})
        mock_sync = MagicMock()
        mock_refresh = AsyncMock()

        with (
            patch("utils.profile_scraper.scrape_all_profiles", mock_scrape_all),
            patch("utils.profile_scraper.sync_profiles_to_server", mock_sync),
            patch.object(background_agent, "refresh_profiles", mock_refresh),
        ):
            cmd = {"payload": {"platforms": ["linkedin"]}}
            await handler(cmd)

        mock_scrape_all.assert_called_once_with(["linkedin"])
        mock_sync.assert_called_once()
        mock_refresh.assert_not_called()

    async def test_handle_scrape_profiles_falls_back_to_refresh_profiles_when_no_payload(self):
        """When no platforms in payload, handler should route through refresh_profiles()
        (the stale-check path) rather than unconditionally scraping all platforms.
        """
        scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        import background_agent

        fake_agent = MagicMock()
        fake_agent.paused = False

        handlers = background_agent._get_command_handlers(fake_agent)
        handler = handlers["scrape_profiles"]

        mock_refresh = AsyncMock(return_value={"success": True, "refreshed": 0, "skipped": True})

        with patch.object(background_agent, "refresh_profiles", mock_refresh):
            await handler({"payload": {}})

        mock_refresh.assert_called_once()
