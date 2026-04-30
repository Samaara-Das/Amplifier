"""Tests for server/app/routers/metrics.py — post registration, metric submission, status updates."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "server"))

from app.core.security import create_access_token
from app.models.post import Post
from app.models.metric import Metric
from app.models.payout import Payout


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    from app.routers import auth as auth_router
    auth_router.limiter.reset()
    yield


def _user_token(user_id: int) -> str:
    return create_access_token({"sub": str(user_id), "type": "user"})


async def _seed_post_chain(db_session, factory):
    """Seed user → company → campaign → assignment → post. Returns (user, assignment, post)."""
    user = await factory.create_user(db_session, email="metrics-user@test.com")
    company = await factory.create_company(db_session, email="metrics-co@test.com")
    campaign = await factory.create_campaign(
        db_session,
        company_id=company.id,
        payout_rules={
            "rate_per_1k_impressions": 0.50,
            "rate_per_like": 0.01,
            "rate_per_repost": 0.05,
            "rate_per_click": 0.10,
        },
    )
    assignment = await factory.create_assignment(db_session, campaign_id=campaign.id, user_id=user.id)
    post = await factory.create_post(db_session, assignment_id=assignment.id, platform="linkedin")
    await db_session.commit()
    return user, assignment, campaign, post


class TestPostRegister:
    async def test_register_creates_post_row(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="reg-post@test.com")
        company = await factory.create_company(db_session, email="reg-post-co@test.com")
        campaign = await factory.create_campaign(db_session, company_id=company.id)
        assignment = await factory.create_assignment(db_session, campaign_id=campaign.id, user_id=user.id)
        await db_session.commit()

        now = datetime.now(timezone.utc)
        resp = await client.post(
            "/api/posts",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={
                "posts": [{
                    "assignment_id": assignment.id,
                    "platform": "linkedin",
                    "post_url": "https://linkedin.com/posts/test-123",
                    "content_hash": "deadbeef",
                    "posted_at": now.isoformat(),
                }]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["created"][0]["platform"] == "linkedin"

        # Verify DB row
        result = await db_session.execute(
            select(Post).where(Post.assignment_id == assignment.id)
        )
        posts = result.scalars().all()
        assert any(p.post_url == "https://linkedin.com/posts/test-123" for p in posts)

    async def test_register_invalid_assignment_skipped_silently(self, client, db_session, factory):
        user = await factory.create_user(db_session, email="reg-invalid@test.com")
        await db_session.commit()

        now = datetime.now(timezone.utc)
        resp = await client.post(
            "/api/posts",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={
                "posts": [{
                    "assignment_id": 99999,
                    "platform": "linkedin",
                    "post_url": "https://linkedin.com/posts/no-assign",
                    "content_hash": "aabb",
                    "posted_at": now.isoformat(),
                }]
            },
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


class TestMetricsSubmit:
    async def test_submit_metrics_creates_payout(self, client, db_session, factory):
        user, assignment, campaign, post = await _seed_post_chain(db_session, factory)
        scraped_at = datetime.now(timezone.utc)

        resp = await client.post(
            "/api/metrics",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={
                "metrics": [{
                    "post_id": post.id,
                    "impressions": 1000,
                    "likes": 50,
                    "reposts": 10,
                    "clicks": 5,
                    "comments": 3,
                    "scraped_at": scraped_at.isoformat(),
                    "is_final": False,
                }]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == 1

        # Billing should have run — a Payout row should exist
        result = await db_session.execute(
            select(Payout).where(Payout.user_id == user.id)
        )
        payouts = result.scalars().all()
        assert len(payouts) >= 1

    async def test_dedup_same_scraped_at_no_duplicate_metric(self, client, db_session, factory):
        user, assignment, campaign, post = await _seed_post_chain(db_session, factory)
        # Use a unique email to avoid cross-test collision
        user2 = await factory.create_user(db_session, email="dedup-metrics@test.com")
        company2 = await factory.create_company(db_session, email="dedup-co@test.com")
        campaign2 = await factory.create_campaign(db_session, company_id=company2.id)
        assign2 = await factory.create_assignment(db_session, campaign_id=campaign2.id, user_id=user2.id)
        post2 = await factory.create_post(db_session, assignment_id=assign2.id, platform="reddit")
        await db_session.commit()

        scraped_at = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        payload = {
            "metrics": [{
                "post_id": post2.id,
                "impressions": 500,
                "likes": 20,
                "reposts": 5,
                "clicks": 2,
                "comments": 1,
                "scraped_at": scraped_at.isoformat(),
                "is_final": False,
            }]
        }
        auth = {"Authorization": f"Bearer {_user_token(user2.id)}"}

        resp1 = await client.post("/api/metrics", headers=auth, json=payload)
        assert resp1.status_code == 200
        assert resp1.json()["accepted"] == 1

        resp2 = await client.post("/api/metrics", headers=auth, json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["skipped_duplicate"] == 1

        # Only one Metric row for this post + scraped_at
        result = await db_session.execute(
            select(Metric).where(Metric.post_id == post2.id)
        )
        metrics = result.scalars().all()
        assert len(metrics) == 1


class TestPostStatusUpdate:
    async def test_patch_status_deleted_voids_payouts(self, client, db_session, factory):
        user, assignment, campaign, post = await _seed_post_chain(db_session, factory)

        # Seed a payout for this post
        payout = Payout(
            user_id=user.id,
            campaign_id=campaign.id,
            amount=5.00,
            amount_cents=500,
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            status="pending",
            breakdown={"post_id": post.id},
        )
        db_session.add(payout)
        await db_session.commit()

        resp = await client.patch(
            f"/api/posts/{post.id}/status",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"status": "deleted"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_status"] == "deleted"

        # Post status updated in DB
        await db_session.refresh(post)
        assert post.status == "deleted"

        # Payout should be voided
        await db_session.refresh(payout)
        assert payout.status == "voided"

    async def test_patch_invalid_status_returns_422(self, client, db_session, factory):
        user, assignment, campaign, post = await _seed_post_chain(db_session, factory)

        resp = await client.patch(
            f"/api/posts/{post.id}/status",
            headers={"Authorization": f"Bearer {_user_token(user.id)}"},
            json={"status": "nonsense"},
        )
        assert resp.status_code == 422
