"""Tests for campaign CSV export endpoint (Task 12).

Covers:
- CSV has correct headers
- CSV contains all posts for campaign
- Date range filtering
- Empty campaign returns headers only
- Other company can't export (authorization)
"""

import csv
import io
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ── Path setup ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _server_env(monkeypatch):
    """Point server to an in-memory SQLite DB for testing."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    from app.core import config
    config.get_settings.cache_clear()


@pytest_asyncio.fixture
async def db_session():
    """Create tables and yield an async DB session."""
    from app.core.database import engine, async_session, Base
    import app.models  # noqa: F401 — register all models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def seed_data(db_session):
    """Seed company, campaign, users, assignments, posts, metrics, payouts."""
    from app.models.company import Company
    from app.models.campaign import Campaign
    from app.models.user import User
    from app.models.assignment import CampaignAssignment
    from app.models.post import Post
    from app.models.metric import Metric
    from app.models.payout import Payout
    from app.core.security import hash_password

    # Company
    company = Company(
        name="TestCo",
        email="company@test.com",
        password_hash=hash_password("pass123"),
        balance=5000.0,
    )
    db_session.add(company)
    await db_session.flush()

    # Second company (for auth tests)
    company2 = Company(
        name="OtherCo",
        email="other@test.com",
        password_hash=hash_password("pass123"),
        balance=1000.0,
    )
    db_session.add(company2)
    await db_session.flush()

    # Campaign
    now = datetime.now(timezone.utc)
    campaign = Campaign(
        company_id=company.id,
        title="Test Campaign",
        brief="Promote our product",
        assets={},
        budget_total=500.0,
        budget_remaining=300.0,
        payout_rules={
            "rate_per_1k_impressions": 0.50,
            "rate_per_like": 0.01,
            "rate_per_repost": 0.05,
            "rate_per_click": 0.10,
        },
        targeting={"niche_tags": ["finance"], "required_platforms": ["x"]},
        content_guidance="Be creative",
        penalty_rules={},
        status="active",
        start_date=now - timedelta(days=30),
        end_date=now + timedelta(days=30),
    )
    db_session.add(campaign)
    await db_session.flush()

    # Users
    user1 = User(
        email="user1@test.com",
        password_hash=hash_password("pass123"),
        platforms={"x": {"connected": True}},
        niche_tags=["finance"],
    )
    user2 = User(
        email="user2@test.com",
        password_hash=hash_password("pass123"),
        platforms={"x": {"connected": True}},
        niche_tags=["finance"],
    )
    db_session.add_all([user1, user2])
    await db_session.flush()

    # Assignments
    assign1 = CampaignAssignment(
        campaign_id=campaign.id, user_id=user1.id, status="posted"
    )
    assign2 = CampaignAssignment(
        campaign_id=campaign.id, user_id=user2.id, status="posted"
    )
    db_session.add_all([assign1, assign2])
    await db_session.flush()

    # Posts (with different dates for filtering tests)
    post1 = Post(
        assignment_id=assign1.id,
        platform="x",
        post_url="https://x.com/user1/status/111",
        content_hash="abc123",
        posted_at=datetime(2026, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
        status="live",
    )
    post2 = Post(
        assignment_id=assign1.id,
        platform="linkedin",
        post_url="https://linkedin.com/post/222",
        content_hash="def456",
        posted_at=datetime(2026, 3, 20, 14, 0, 0, tzinfo=timezone.utc),
        status="live",
    )
    post3 = Post(
        assignment_id=assign2.id,
        platform="x",
        post_url="https://x.com/user2/status/333",
        content_hash="ghi789",
        posted_at=datetime(2026, 3, 25, 8, 0, 0, tzinfo=timezone.utc),
        status="live",
    )
    db_session.add_all([post1, post2, post3])
    await db_session.flush()

    # Metrics (final metrics for post1 and post2, non-final for post3)
    metric1 = Metric(
        post_id=post1.id,
        impressions=5000,
        likes=120,
        reposts=30,
        comments=15,
        clicks=45,
        scraped_at=now,
        is_final=True,
    )
    metric2 = Metric(
        post_id=post2.id,
        impressions=3000,
        likes=80,
        reposts=20,
        comments=10,
        clicks=25,
        scraped_at=now,
        is_final=True,
    )
    metric3 = Metric(
        post_id=post3.id,
        impressions=1000,
        likes=40,
        reposts=10,
        comments=5,
        clicks=15,
        scraped_at=now,
        is_final=False,
    )
    db_session.add_all([metric1, metric2, metric3])
    await db_session.flush()

    # Payouts
    payout1 = Payout(
        user_id=user1.id,
        campaign_id=campaign.id,
        amount=12.50,
        period_start=now - timedelta(days=7),
        period_end=now,
        status="paid",
        breakdown={"impressions_earned": 10.00, "likes_earned": 2.50},
    )
    db_session.add(payout1)
    await db_session.flush()
    await db_session.commit()

    return {
        "company_id": company.id,
        "company2_id": company2.id,
        "campaign_id": campaign.id,
        "user1_id": user1.id,
        "user2_id": user2.id,
        "post_count": 3,
    }


@pytest_asyncio.fixture
async def company_token(seed_data):
    """JWT for the campaign-owning company."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(seed_data["company_id"]), "type": "company"})


@pytest_asyncio.fixture
async def other_company_token(seed_data):
    """JWT for a different company (should not have access)."""
    from app.core.security import create_access_token
    return create_access_token({"sub": str(seed_data["company2_id"]), "type": "company"})


@pytest_asyncio.fixture
async def client():
    """Async HTTP client bound to the FastAPI app."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ===================================================================
# Helpers
# ===================================================================


def _parse_csv(text: str) -> list[dict]:
    """Parse CSV text into list of dicts keyed by header."""
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


# ===================================================================
# Tests
# ===================================================================


class TestCSVHeaders:

    @pytest.mark.asyncio
    async def test_csv_has_correct_headers(self, client, company_token, seed_data):
        """CSV response contains the expected column headers."""
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}/export?format=csv",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers.get("content-disposition", "")

        rows = _parse_csv(resp.text)
        expected_headers = {
            "User", "Platform", "Post URL", "Impressions", "Likes",
            "Reposts", "Comments", "Clicks", "Earned", "Posted At",
        }
        # Check headers from the first row's keys
        assert set(rows[0].keys()) == expected_headers


class TestCSVContent:

    @pytest.mark.asyncio
    async def test_csv_contains_all_posts(self, client, company_token, seed_data):
        """CSV contains one row per post (3 posts seeded)."""
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}/export?format=csv",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        rows = _parse_csv(resp.text)
        assert len(rows) == seed_data["post_count"]

    @pytest.mark.asyncio
    async def test_csv_row_values(self, client, company_token, seed_data):
        """Spot-check specific values in the first post row."""
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}/export?format=csv",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        rows = _parse_csv(resp.text)

        # Find the row for post with URL containing "user1/status/111"
        post1_rows = [r for r in rows if "user1/status/111" in r.get("Post URL", "")]
        assert len(post1_rows) == 1
        row = post1_rows[0]

        assert row["Platform"] == "x"
        assert row["Impressions"] == "5000"
        assert row["Likes"] == "120"
        assert row["Reposts"] == "30"
        assert row["Comments"] == "15"
        assert row["Clicks"] == "45"
        assert row["User"] == "user1@test.com"
        # Earned = (5000/1000 * 0.50) + (120 * 0.01) + (30 * 0.05) + (45 * 0.10) = 2.50 + 1.20 + 1.50 + 4.50 = $9.70
        assert row["Earned"] == "$9.70"

    @pytest.mark.asyncio
    async def test_csv_filename(self, client, company_token, seed_data):
        """Content-Disposition header contains the campaign ID in filename."""
        cid = seed_data["campaign_id"]
        resp = await client.get(
            f"/api/company/campaigns/{cid}/export?format=csv",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert f"campaign-{cid}-report.csv" in resp.headers["content-disposition"]


class TestDateRangeFiltering:

    @pytest.mark.asyncio
    async def test_filter_by_start_date(self, client, company_token, seed_data):
        """Only posts on or after start_date are included."""
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}/export?format=csv&start_date=2026-03-20",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        rows = _parse_csv(resp.text)
        # post1 is 2026-03-15 (excluded), post2 is 2026-03-20, post3 is 2026-03-25
        assert len(rows) == 2
        urls = [r["Post URL"] for r in rows]
        assert not any("user1/status/111" in u for u in urls)

    @pytest.mark.asyncio
    async def test_filter_by_end_date(self, client, company_token, seed_data):
        """Only posts on or before end_date are included."""
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}/export?format=csv&end_date=2026-03-20",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        rows = _parse_csv(resp.text)
        # post1 is 2026-03-15, post2 is 2026-03-20 (included), post3 is 2026-03-25 (excluded)
        assert len(rows) == 2
        urls = [r["Post URL"] for r in rows]
        assert not any("user2/status/333" in u for u in urls)

    @pytest.mark.asyncio
    async def test_filter_by_both_dates(self, client, company_token, seed_data):
        """Date range filters combine correctly."""
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}/export?format=csv&start_date=2026-03-16&end_date=2026-03-24",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        rows = _parse_csv(resp.text)
        # Only post2 (2026-03-20) falls in range
        assert len(rows) == 1
        assert "linkedin" in rows[0]["Post URL"]


class TestEmptyCampaign:

    @pytest.mark.asyncio
    async def test_empty_campaign_returns_headers_only(self, client, company_token, seed_data, db_session):
        """A campaign with no posts returns CSV with headers but no data rows."""
        from app.models.campaign import Campaign

        empty_campaign = Campaign(
            company_id=seed_data["company_id"],
            title="Empty Campaign",
            brief="Nothing here",
            assets={},
            budget_total=100.0,
            budget_remaining=100.0,
            payout_rules={"rate_per_1k_impressions": 0.50},
            targeting={},
            status="draft",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db_session.add(empty_campaign)
        await db_session.flush()
        await db_session.commit()

        resp = await client.get(
            f"/api/company/campaigns/{empty_campaign.id}/export?format=csv",
            headers={"Authorization": f"Bearer {company_token}"},
        )
        assert resp.status_code == 200
        rows = _parse_csv(resp.text)
        assert len(rows) == 0

        # But headers should still be present
        lines = resp.text.strip().split("\n")
        assert len(lines) == 1  # Just the header row
        assert "User" in lines[0]
        assert "Impressions" in lines[0]


class TestAuthorization:

    @pytest.mark.asyncio
    async def test_other_company_cannot_export(self, client, other_company_token, seed_data):
        """A company that doesn't own the campaign gets 404."""
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}/export?format=csv",
            headers={"Authorization": f"Bearer {other_company_token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_request(self, client, seed_data):
        """Request without auth token is rejected."""
        resp = await client.get(
            f"/api/company/campaigns/{seed_data['campaign_id']}/export?format=csv",
        )
        assert resp.status_code in (401, 403)
