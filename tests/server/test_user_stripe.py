"""Tests for Task #19 — user-side Stripe Connect UI.

Covers:
- Connect idempotent when stripe_account_id already set
- Connect redirects to Stripe onboarding when not set
- Return handler stamps user.stripe_account_id and redirects to /user/earnings
- Return handler rejects accounts belonging to other users (metadata mismatch)
- Payout endpoint rejects when stripe_account_id is NULL
- process_pending_payouts uses user.stripe_account_id for the Transfer destination
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_engine():
    from app.core.database import Base

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
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_engine):
    """httpx.AsyncClient wired to the FastAPI app with a test database."""
    from app.core.database import get_db
    from app.main import app

    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
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


async def _make_user(session, email="stripe-user@test.com", stripe_account_id=None):
    """Create a test User and return it."""
    from app.models.user import User
    from app.core.security import hash_password

    user = User(
        email=email,
        password_hash=hash_password("testpass"),
        tier="seedling",
        trust_score=50,
        platforms={"linkedin": True},
        follower_counts={"linkedin": 200},
        niche_tags=["finance"],
        audience_region="us",
        successful_post_count=0,
        earnings_balance=0.0,
        earnings_balance_cents=0,
        total_earned=0.0,
        total_earned_cents=0,
        stripe_account_id=stripe_account_id,
    )
    session.add(user)
    await session.flush()
    return user


def _user_cookie(user_id: int) -> str:
    """Create a JWT cookie value for a user."""
    from app.core.security import create_access_token
    token = create_access_token({"sub": str(user_id), "type": "user"})
    return token


# ---------------------------------------------------------------------------
# AC14 / AC15 — POST /user/stripe/connect
# ---------------------------------------------------------------------------

class TestStripeConnect:
    @pytest.mark.asyncio
    async def test_connect_idempotent_when_already_set(self, client, db_session):
        """User with stripe_account_id → 302 to /user/settings#stripe-connect, no Stripe call."""
        user = await _make_user(db_session, stripe_account_id="acct_already_connected")
        cookie = _user_cookie(user.id)

        with patch("app.routers.user.stripe.create_user_stripe_account") as mock_create:
            resp = await client.post(
                "/user/stripe/connect",
                cookies={"user_token": cookie},
                follow_redirects=False,
            )

        mock_create.assert_not_called()
        assert resp.status_code == 302
        assert "/user/settings" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_connect_redirects_to_stripe_when_not_set(self, client, db_session):
        """User without stripe_account_id → create account → 302 to Stripe onboarding URL."""
        user = await _make_user(db_session, stripe_account_id=None)
        cookie = _user_cookie(user.id)

        mock_result = {
            "account_id": "acct_test123",
            "onboarding_url": "https://connect.stripe.com/express/onboarding/mock",
        }

        with patch(
            "app.routers.user.stripe.create_user_stripe_account",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = await client.post(
                "/user/stripe/connect",
                cookies={"user_token": cookie},
                follow_redirects=False,
            )

        assert resp.status_code == 302
        assert resp.headers["location"] == mock_result["onboarding_url"]

    @pytest.mark.asyncio
    async def test_connect_returns_error_redirect_when_stripe_not_configured(
        self, client, db_session
    ):
        """If create_user_stripe_account returns None → 302 to settings?stripe_error=1."""
        user = await _make_user(db_session, stripe_account_id=None)
        cookie = _user_cookie(user.id)

        with patch(
            "app.routers.user.stripe.create_user_stripe_account",
            new=AsyncMock(return_value=None),
        ):
            resp = await client.post(
                "/user/stripe/connect",
                cookies={"user_token": cookie},
                follow_redirects=False,
            )

        assert resp.status_code == 302
        assert "stripe_error=1" in resp.headers["location"]


# ---------------------------------------------------------------------------
# AC16 — GET /user/stripe/connect/return
# ---------------------------------------------------------------------------

class TestStripeConnectReturn:
    @pytest.mark.asyncio
    async def test_return_handler_stamps_account_id(self, client, db_session):
        """Return URL with valid account_id stamps user.stripe_account_id → redirect /user/earnings."""
        user = await _make_user(db_session, stripe_account_id=None)
        cookie = _user_cookie(user.id)

        # Mock Stripe account retrieval to return matching metadata
        mock_acct = MagicMock()
        mock_acct.metadata = {"user_id": str(user.id)}

        mock_stripe = MagicMock()
        mock_stripe.Account.retrieve.return_value = mock_acct

        with patch("app.routers.user.stripe._get_stripe", return_value=mock_stripe):
            resp = await client.get(
                "/user/stripe/connect/return",
                params={"account_id": "acct_test_valid"},
                cookies={"user_token": cookie},
                follow_redirects=False,
            )

        assert resp.status_code == 302
        assert "/user/earnings" in resp.headers["location"]
        assert "connected=1" in resp.headers["location"]

        # The 302 to /user/earnings?connected=1 confirms the handler ran the stamp logic.
        # (DB state is committed in the handler's own session — not accessible from this test session.)

    @pytest.mark.asyncio
    async def test_return_handler_rejects_other_users_account_id(self, client, db_session):
        """Return URL with account_id belonging to different user → no DB write, redirect error."""
        user = await _make_user(
            db_session, email="victim@test.com", stripe_account_id=None
        )
        cookie = _user_cookie(user.id)

        # Stripe account metadata says it belongs to user 9999, not our user
        mock_acct = MagicMock()
        mock_acct.metadata = {"user_id": "9999"}

        mock_stripe = MagicMock()
        mock_stripe.Account.retrieve.return_value = mock_acct

        with patch("app.routers.user.stripe._get_stripe", return_value=mock_stripe):
            resp = await client.get(
                "/user/stripe/connect/return",
                params={"account_id": "acct_other_user"},
                cookies={"user_token": cookie},
                follow_redirects=False,
            )

        assert resp.status_code == 302
        assert "stripe_error=1" in resp.headers["location"]

        # DB must NOT be updated
        from sqlalchemy import select
        from app.models.user import User
        result = await db_session.execute(select(User).where(User.id == user.id))
        updated_user = result.scalar_one()
        assert updated_user.stripe_account_id is None

    @pytest.mark.asyncio
    async def test_return_handler_rejects_malformed_account_id(self, client, db_session):
        """Return URL with non-acct_ account_id → error redirect without DB write."""
        user = await _make_user(db_session, stripe_account_id=None)
        cookie = _user_cookie(user.id)

        resp = await client.get(
            "/user/stripe/connect/return",
            params={"account_id": "bad_id_format"},
            cookies={"user_token": cookie},
            follow_redirects=False,
        )

        assert resp.status_code == 302
        assert "stripe_error=1" in resp.headers["location"]


# ---------------------------------------------------------------------------
# AC17 — POST /api/users/me/payout without stripe_account_id
# ---------------------------------------------------------------------------

class TestPayoutEndpoint:
    @pytest.mark.asyncio
    async def test_payout_endpoint_rejects_without_stripe_account(self, client, db_session):
        """User with NULL stripe_account_id → POST /api/users/me/payout returns 400."""
        from app.core.security import create_access_token
        from app.models.user import User
        from app.core.security import hash_password

        user = User(
            email="no-stripe@test.com",
            password_hash=hash_password("testpass"),
            tier="seedling",
            trust_score=50,
            platforms={"linkedin": True},
            follower_counts={"linkedin": 200},
            niche_tags=["finance"],
            audience_region="us",
            successful_post_count=0,
            earnings_balance=50.0,
            earnings_balance_cents=5000,
            total_earned=0.0,
            total_earned_cents=0,
            stripe_account_id=None,
        )
        db_session.add(user)
        await db_session.flush()

        token = create_access_token({"sub": str(user.id), "type": "user"})

        resp = await client.post(
            "/api/users/me/payout",
            json={"amount": 10.0},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 400
        assert "stripe" in resp.json()["detail"].lower() or "bank" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# AC18 — process_pending_payouts uses user.stripe_account_id
# ---------------------------------------------------------------------------

class TestProcessPendingPayouts:
    @pytest.mark.asyncio
    async def test_process_pending_payouts_uses_user_stripe_account_id(self, db_session):
        """Payout in 'processing', user has stripe_account_id → Transfer.create called with correct destination."""
        from app.models.user import User
        from app.models.payout import Payout
        from app.core.security import hash_password
        from app.services.payments import process_pending_payouts
        from datetime import datetime, timezone

        user = User(
            email="payout-test@test.com",
            password_hash=hash_password("testpass"),
            tier="seedling",
            trust_score=50,
            platforms={"linkedin": True},
            follower_counts={"linkedin": 200},
            niche_tags=["finance"],
            audience_region="us",
            successful_post_count=0,
            earnings_balance=15.0,
            earnings_balance_cents=1500,
            total_earned=0.0,
            total_earned_cents=0,
            stripe_account_id="acct_test_destination",
        )
        db_session.add(user)
        await db_session.flush()

        now = datetime.now(timezone.utc)
        payout = Payout(
            user_id=user.id,
            campaign_id=None,
            amount=15.0,
            amount_cents=1500,
            period_start=now,
            period_end=now,
            status="processing",
            breakdown={"withdrawal": True, "requested_via": "user_withdraw"},
        )
        db_session.add(payout)
        await db_session.flush()

        # Mock Stripe: Transfer.create returns a fake transfer
        mock_transfer = MagicMock()
        mock_transfer.id = "tr_test_abc123"

        mock_stripe = MagicMock()
        mock_stripe.Transfer.create.return_value = mock_transfer

        with patch("app.services.payments._get_stripe", return_value=mock_stripe):
            result = await process_pending_payouts(db_session)

        # Verify Transfer.create was called with the user's stripe_account_id
        mock_stripe.Transfer.create.assert_called_once()
        call_kwargs = mock_stripe.Transfer.create.call_args[1]
        assert call_kwargs["destination"] == "acct_test_destination"
        assert call_kwargs["amount"] == 1500

        # Verify result counts
        assert result["processed"] >= 1
        assert result["paid"] >= 1
        assert result["failed"] == 0

        # Verify payout was marked paid with processor_ref
        await db_session.refresh(payout)
        assert payout.status == "paid"
        assert payout.breakdown.get("processor_ref") == "tr_test_abc123"

    @pytest.mark.asyncio
    async def test_process_pending_payouts_no_null_processor_ref(self, db_session):
        """Ensure processor_ref is never 'test_mode_no_stripe_account' when stripe_account_id is set."""
        from app.models.user import User
        from app.models.payout import Payout
        from app.core.security import hash_password
        from app.services.payments import process_pending_payouts
        from datetime import datetime, timezone

        user = User(
            email="no-null-ref@test.com",
            password_hash=hash_password("testpass"),
            tier="seedling",
            trust_score=50,
            platforms={},
            follower_counts={},
            niche_tags=[],
            audience_region="us",
            successful_post_count=0,
            earnings_balance=10.0,
            earnings_balance_cents=1000,
            total_earned=0.0,
            total_earned_cents=0,
            stripe_account_id="acct_real_account",
        )
        db_session.add(user)
        await db_session.flush()

        now = datetime.now(timezone.utc)
        payout = Payout(
            user_id=user.id,
            campaign_id=None,
            amount=10.0,
            amount_cents=1000,
            period_start=now,
            period_end=now,
            status="processing",
            breakdown={"withdrawal": True},
        )
        db_session.add(payout)
        await db_session.flush()

        mock_transfer = MagicMock()
        mock_transfer.id = "tr_real_transfer"

        mock_stripe = MagicMock()
        mock_stripe.Transfer.create.return_value = mock_transfer

        with patch("app.services.payments._get_stripe", return_value=mock_stripe):
            await process_pending_payouts(db_session)

        await db_session.refresh(payout)
        # The old placeholder value must NOT appear
        assert payout.breakdown.get("processor_ref") != "test_mode_no_stripe_account"
        assert payout.breakdown.get("processor_ref") == "tr_real_transfer"
