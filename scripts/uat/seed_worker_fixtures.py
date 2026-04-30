"""Seed synthetic fixture rows for Task #44 worker UAT tests.

Usage:
    python scripts/uat/seed_worker_fixtures.py --output data/uat/worker_fixtures.json

Connects to the database at DATABASE_URL env var (defaults to local docker-compose
Postgres). Creates 4 fixture rows and emits their IDs as JSON.

Seeded rows:
    pending_payout_ready_id    — Payout status=pending, available_at=NOW()-1min
    available_payout_ready_id  — Payout status=available, amount_cents=1500, user
                                  has stripe_account_id='acct_test_123'
    anomalous_post_id          — Post + two Metrics showing a 100x engagement jump
    orphan_metric_id           — Metric row with no Payout referencing it
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure server/ is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SERVER_DIR = _REPO_ROOT / "server"
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

# Override DATABASE_URL to docker-compose Postgres if not set
_DEFAULT_DB = "postgresql+asyncpg://postgres:postgres@localhost:5432/amplifier_test"
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = _DEFAULT_DB

# Patch settings so database.py picks up the override
from app.core.config import get_settings
_settings = get_settings()
# Pydantic-settings reads from env at creation time; we need to override after the fact
# by patching the cached object directly.
_settings.__dict__["database_url"] = os.environ["DATABASE_URL"]

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from app.core.database import Base


async def _get_session(db_url: str) -> tuple:
    """Create a new engine + sessionmaker against db_url."""
    import ssl
    # asyncpg with Postgres — no SSL for local docker
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


async def _ensure_schema(engine):
    """Create all tables (idempotent)."""
    # Import all models so Base.metadata is populated
    import app.models.user  # noqa
    import app.models.campaign  # noqa
    import app.models.assignment  # noqa
    import app.models.post  # noqa
    import app.models.metric  # noqa
    import app.models.payout  # noqa
    import app.models.audit_log  # noqa
    import app.models.penalty  # noqa
    import app.models.company  # noqa
    import app.models.invitation_log  # noqa
    import app.models.content_screening  # noqa
    import app.models.campaign_post  # noqa
    import app.models.company_transaction  # noqa
    import app.models.admin_review_queue  # noqa

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def truncate_all(engine):
    """Truncate all worker-relevant tables before reseeding to prevent cross-test contamination."""
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE TABLE metrics, posts, payouts, campaign_assignments, "
            "audit_log, campaigns, companies, users RESTART IDENTITY CASCADE"
        ))


async def seed(db_url: str) -> dict:
    from app.models.user import User
    from app.models.campaign import Campaign
    from app.models.assignment import CampaignAssignment
    from app.models.post import Post
    from app.models.metric import Metric
    from app.models.payout import Payout
    from app.models.company import Company

    engine, session_factory = await _get_session(db_url)
    await _ensure_schema(engine)
    await truncate_all(engine)

    now = datetime.now(timezone.utc)

    async with session_factory() as db:
        # ── Company (required for Campaign FK) ───────────────────────────────
        company = Company(
            name="UAT Worker Company",
            email=f"uat-worker-{int(now.timestamp())}@example.com",
            password_hash="$2b$12$unused",
            balance_cents=100_000,
        )
        db.add(company)
        await db.flush()

        # ── Campaign ─────────────────────────────────────────────────────────
        campaign = Campaign(
            company_id=company.id,
            title="UAT Worker Campaign",
            brief="Seed campaign for worker UAT",
            targeting={"niche_tags": ["finance"], "required_platforms": ["linkedin"]},
            budget_total=500.0,
            budget_remaining=500.0,
            payout_rules={
                "rate_per_1k_impressions": 2.0,
                "rate_per_like": 0.05,
                "rate_per_repost": 0.10,
                "rate_per_click": 0.02,
            },
            status="active",
            start_date=now - timedelta(days=30),
            end_date=now + timedelta(days=30),
        )
        db.add(campaign)
        await db.flush()

        # ── User A — owns pending payout ──────────────────────────────────────
        user_a = User(
            email=f"uat-worker-a-{int(now.timestamp())}@example.com",
            password_hash="$2b$12$unused",
            trust_score=80,
            tier="grower",
            earnings_balance=0.0,
            earnings_balance_cents=0,
        )
        db.add(user_a)
        await db.flush()

        # Assignment for user_a
        assign_a = CampaignAssignment(
            campaign_id=campaign.id,
            user_id=user_a.id,
            status="posted",
        )
        db.add(assign_a)
        await db.flush()

        # Post for user_a
        post_a = Post(
            assignment_id=assign_a.id,
            platform="linkedin",
            post_url="https://linkedin.com/uat-a",
            content_hash=hashlib.sha256(b"uat-a").hexdigest(),
            posted_at=now - timedelta(days=8),
            status="live",
        )
        db.add(post_a)
        await db.flush()

        # Pending payout — available_at 1 minute ago (past hold period)
        pending_payout = Payout(
            user_id=user_a.id,
            campaign_id=campaign.id,
            amount=5.00,
            amount_cents=500,
            period_start=now - timedelta(days=8),
            period_end=now - timedelta(days=1),
            status="pending",
            available_at=now - timedelta(minutes=1),
            breakdown={"metric_id": None, "post_id": post_a.id, "seeded": True},
        )
        db.add(pending_payout)
        await db.flush()

        # ── User B — owns available payout (Stripe-ready) ────────────────────
        user_b = User(
            email=f"uat-worker-b-{int(now.timestamp())}@example.com",
            password_hash="$2b$12$unused",
            trust_score=75,
            tier="grower",
            earnings_balance=15.00,
            earnings_balance_cents=1500,
            stripe_account_id="acct_test_123",
        )
        db.add(user_b)
        await db.flush()

        assign_b = CampaignAssignment(
            campaign_id=campaign.id,
            user_id=user_b.id,
            status="posted",
        )
        db.add(assign_b)
        await db.flush()

        post_b = Post(
            assignment_id=assign_b.id,
            platform="linkedin",
            post_url="https://linkedin.com/uat-b",
            content_hash=hashlib.sha256(b"uat-b").hexdigest(),
            posted_at=now - timedelta(days=10),
            status="live",
        )
        db.add(post_b)
        await db.flush()

        available_payout = Payout(
            user_id=user_b.id,
            campaign_id=campaign.id,
            amount=15.00,
            amount_cents=1500,
            period_start=now - timedelta(days=10),
            period_end=now - timedelta(days=3),
            status="available",
            available_at=now - timedelta(days=3),
            breakdown={"metric_id": None, "post_id": post_b.id, "seeded": True},
        )
        db.add(available_payout)
        await db.flush()

        # ── User C — anomalous post (100x engagement jump) ───────────────────
        user_c = User(
            email=f"uat-worker-c-{int(now.timestamp())}@example.com",
            password_hash="$2b$12$unused",
            trust_score=80,
            tier="grower",
        )
        db.add(user_c)
        await db.flush()

        assign_c = CampaignAssignment(
            campaign_id=campaign.id,
            user_id=user_c.id,
            status="posted",
        )
        db.add(assign_c)
        await db.flush()

        # 3 separate posts (anomaly detector uses latest_metric_filter which keeps
        # only 1 metric per post; we need metric_count>=3 per user, so 3 posts).
        anomalous_post = Post(
            assignment_id=assign_c.id,
            platform="linkedin",
            post_url="https://linkedin.com/uat-c-1",
            content_hash=hashlib.sha256(b"uat-c-1").hexdigest(),
            posted_at=now - timedelta(hours=3),
            status="live",
        )
        db.add(anomalous_post)
        post_c2 = Post(
            assignment_id=assign_c.id,
            platform="linkedin",
            post_url="https://linkedin.com/uat-c-2",
            content_hash=hashlib.sha256(b"uat-c-2").hexdigest(),
            posted_at=now - timedelta(hours=2),
            status="live",
        )
        db.add(post_c2)
        post_c3 = Post(
            assignment_id=assign_c.id,
            platform="linkedin",
            post_url="https://linkedin.com/uat-c-3",
            content_hash=hashlib.sha256(b"uat-c-3").hexdigest(),
            posted_at=now - timedelta(hours=1),
            status="live",
        )
        db.add(post_c3)
        await db.flush()

        # 1 anomalous metric per post = 3 total metrics with very high engagement
        for p, mins_ago in [(anomalous_post, 90), (post_c2, 60), (post_c3, 30)]:
            db.add(Metric(
                post_id=p.id,
                impressions=10_000, likes=500, reposts=200, comments=100, clicks=50,
                scraped_at=now - timedelta(minutes=mins_ago),
                is_final=False,
            ))
        await db.flush()

        # Seed 4 more users with normal engagement (5 users total satisfies the
        # >=5 user_stats requirement). Each user has 3 posts with 1 metric each
        # so metric_count>=3 — anomaly detector ignores users with fewer.
        normal_post_ids = []
        for i in range(4):
            u_normal = User(
                email=f"uat-worker-normal-{i}-{int(now.timestamp())}@example.com",
                password_hash="$2b$12$unused",
                trust_score=70,
                tier="grower",
            )
            db.add(u_normal)
            await db.flush()

            a_normal = CampaignAssignment(
                campaign_id=campaign.id,
                user_id=u_normal.id,
                status="posted",
            )
            db.add(a_normal)
            await db.flush()

            # 3 posts per normal user (latest_metric_filter keeps only 1 metric/post,
            # so we need 3 posts to satisfy the >=3 metric_count requirement).
            for j in range(3):
                p_normal = Post(
                    assignment_id=a_normal.id,
                    platform="linkedin",
                    post_url=f"https://linkedin.com/uat-normal-{i}-{j}",
                    content_hash=hashlib.sha256(f"uat-normal-{i}-{j}".encode()).hexdigest(),
                    posted_at=now - timedelta(hours=5 - j),
                    status="live",
                )
                db.add(p_normal)
                await db.flush()
                normal_post_ids.append(p_normal.id)

                m_normal = Metric(
                    post_id=p_normal.id,
                    impressions=100 + j,
                    likes=2 + j,
                    reposts=1,
                    comments=0,
                    clicks=1,
                    scraped_at=now - timedelta(minutes=240 - 60*j),
                    is_final=False,
                )
                db.add(m_normal)
                await db.flush()

        # ── Orphan metric — no Payout references it ──────────────────────────
        # Reuse post_a for the orphan metric (different post to avoid confusion)
        user_d = User(
            email=f"uat-worker-d-{int(now.timestamp())}@example.com",
            password_hash="$2b$12$unused",
            trust_score=65,
            tier="seedling",
        )
        db.add(user_d)
        await db.flush()

        assign_d = CampaignAssignment(
            campaign_id=campaign.id,
            user_id=user_d.id,
            status="posted",
        )
        db.add(assign_d)
        await db.flush()

        post_d = Post(
            assignment_id=assign_d.id,
            platform="linkedin",
            post_url="https://linkedin.com/uat-d",
            content_hash=hashlib.sha256(b"uat-d").hexdigest(),
            posted_at=now - timedelta(days=2),
            status="live",
        )
        db.add(post_d)
        await db.flush()

        orphan_metric = Metric(
            post_id=post_d.id,
            impressions=500,
            likes=10,
            reposts=2,
            comments=1,
            clicks=5,
            scraped_at=now - timedelta(hours=6),
            is_final=False,
        )
        db.add(orphan_metric)
        await db.flush()
        # No Payout row references orphan_metric.id — that's the orphan

        await db.commit()

        result = {
            "pending_payout_ready_id": pending_payout.id,
            "available_payout_ready_id": available_payout.id,
            "anomalous_post_id": anomalous_post.id,
            "orphan_metric_id": orphan_metric.id,
            # Bonus context for tests
            "user_a_id": user_a.id,
            "user_b_id": user_b.id,
            "user_c_id": user_c.id,
            "campaign_id": campaign.id,
            "db_url": db_url,
        }

    await engine.dispose()
    return result


def main():
    parser = argparse.ArgumentParser(description="Seed Task #44 worker UAT fixtures")
    parser.add_argument(
        "--output",
        default="data/uat/worker_fixtures.json",
        help="Path to write fixture IDs JSON",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Database URL (defaults to DATABASE_URL env or local docker-compose Postgres)",
    )
    args = parser.parse_args()

    db_url = args.db_url or os.environ.get("DATABASE_URL", _DEFAULT_DB)

    fixtures = asyncio.run(seed(db_url))

    out_path = _REPO_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fixtures, indent=2))

    print(json.dumps(fixtures, indent=2))
    print(f"\nFixtures written to {out_path}")


if __name__ == "__main__":
    main()
