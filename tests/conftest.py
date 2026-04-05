"""Shared fixtures for the Amplifier test suite.

Provides:
- In-memory async SQLite engine + session for server tests
- httpx.AsyncClient wired to the FastAPI app
- Factory helpers for creating test data (users, companies, campaigns, etc.)
"""

import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Path setup — make server/ importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = PROJECT_ROOT / "server"
sys.path.insert(0, str(SERVER_DIR))

# Force env vars BEFORE any app module is imported so Settings picks them up
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci")

from app.core.database import Base  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password, create_access_token  # noqa: E402
from app.models import (  # noqa: E402
    Company, Campaign, User, CampaignAssignment, Post, Metric, Payout,
)

# Clear the lru_cache so our env overrides are picked up
get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Async engine + session (in-memory SQLite, shared across a single test)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_engine():
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
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# FastAPI test client (overrides get_db to use the test session)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Data factories — create objects directly in the test session
# ---------------------------------------------------------------------------

class Factory:
    """Helpers to create test database records."""

    @staticmethod
    async def create_user(
        session: AsyncSession,
        email: str = "user@test.com",
        password: str = "testpass123",
        tier: str = "seedling",
        trust_score: int = 50,
        platforms: dict | None = None,
        follower_counts: dict | None = None,
        niche_tags: list | None = None,
        audience_region: str = "us",
        successful_post_count: int = 0,
    ) -> User:
        user = User(
            email=email,
            password_hash=hash_password(password),
            tier=tier,
            trust_score=trust_score,
            platforms=platforms or {"x": True, "linkedin": True},
            follower_counts=follower_counts or {"x": 500, "linkedin": 200},
            niche_tags=niche_tags or ["finance", "tech"],
            audience_region=audience_region,
            successful_post_count=successful_post_count,
            earnings_balance=0.0,
            earnings_balance_cents=0,
            total_earned=0.0,
            total_earned_cents=0,
        )
        session.add(user)
        await session.flush()
        return user

    @staticmethod
    async def create_company(
        session: AsyncSession,
        name: str = "TestCorp",
        email: str = "corp@test.com",
        password: str = "corppass123",
        balance: float = 10000.0,
    ) -> Company:
        company = Company(
            name=name,
            email=email,
            password_hash=hash_password(password),
            balance=balance,
        )
        session.add(company)
        await session.flush()
        return company

    @staticmethod
    async def create_campaign(
        session: AsyncSession,
        company_id: int,
        title: str = "Test Campaign",
        brief: str = "Buy our product",
        budget_total: float = 1000.0,
        budget_remaining: float | None = None,
        payout_rules: dict | None = None,
        targeting: dict | None = None,
        status: str = "active",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> Campaign:
        now = datetime.now(timezone.utc)
        campaign = Campaign(
            company_id=company_id,
            title=title,
            brief=brief,
            budget_total=budget_total,
            budget_remaining=budget_remaining if budget_remaining is not None else budget_total,
            payout_rules=payout_rules or {
                "rate_per_1k_impressions": 0.50,
                "rate_per_like": 0.01,
                "rate_per_repost": 0.05,
                "rate_per_click": 0.10,
            },
            targeting=targeting or {
                "required_platforms": ["x"],
                "niche_tags": ["finance"],
                "min_followers": {},
            },
            status=status,
            screening_status="approved",
            start_date=start_date or now,
            end_date=end_date or (now + timedelta(days=30)),
        )
        session.add(campaign)
        await session.flush()
        return campaign

    @staticmethod
    async def create_assignment(
        session: AsyncSession,
        campaign_id: int,
        user_id: int,
        status: str = "accepted",
    ) -> CampaignAssignment:
        now = datetime.now(timezone.utc)
        assignment = CampaignAssignment(
            campaign_id=campaign_id,
            user_id=user_id,
            status=status,
            invited_at=now,
            expires_at=now + timedelta(days=3),
        )
        session.add(assignment)
        await session.flush()
        return assignment

    @staticmethod
    async def create_post(
        session: AsyncSession,
        assignment_id: int,
        platform: str = "x",
        post_url: str = "https://x.com/user/status/123",
    ) -> Post:
        post = Post(
            assignment_id=assignment_id,
            platform=platform,
            post_url=post_url,
            content_hash="abc123",
            posted_at=datetime.now(timezone.utc),
        )
        session.add(post)
        await session.flush()
        return post

    @staticmethod
    async def create_metric(
        session: AsyncSession,
        post_id: int,
        impressions: int = 1000,
        likes: int = 50,
        reposts: int = 10,
        clicks: int = 5,
        comments: int = 3,
        is_final: bool = False,
    ) -> Metric:
        metric = Metric(
            post_id=post_id,
            impressions=impressions,
            likes=likes,
            reposts=reposts,
            comments=comments,
            clicks=clicks,
            scraped_at=datetime.now(timezone.utc),
            is_final=is_final,
        )
        session.add(metric)
        await session.flush()
        return metric


@pytest.fixture
def factory():
    return Factory
