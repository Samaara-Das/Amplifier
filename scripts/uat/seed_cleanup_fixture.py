"""Seed a UAT fixture for /uat-task 85.

Creates one synthetic test user + one row in every cleanup-target table
(campaign_assignments, posts, metrics, payouts, penalties, agent_status,
agent_command, drafts, campaign_invitation_log) so the cleanup script can
prove cascade coverage end-to-end without hitting real platform APIs.

Usage:
    python scripts/uat/seed_cleanup_fixture.py --email uat-task85-user@pointcapitalis.com
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parent.parent.parent / "server"
sys.path.insert(0, str(_SERVER_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./amplifier.db")
os.environ.setdefault("JWT_SECRET_KEY", "change-me-to-a-random-secret")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
from sqlalchemy.pool import NullPool

from app.core.database import Base  # registers all model tables
from app.models.user import User
from app.models.company import Company
from app.models.campaign import Campaign
from app.models.assignment import CampaignAssignment
from app.models.post import Post
from app.models.metric import Metric
from app.models.payout import Payout
from app.models.penalty import Penalty
from app.models.agent_status import AgentStatus
from app.models.agent_command import AgentCommand
from app.models.draft import Draft
from app.models.invitation_log import CampaignInvitationLog


async def seed(email: str) -> int:
    db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./amplifier.db")
    engine = create_async_engine(
        db_url,
        poolclass=NullPool,
        connect_args={"prepared_statement_cache_size": 0} if "postgresql" in db_url else {},
    )
    # Auto-create tables on local SQLite — the seed runs in dev environments
    # where alembic upgrade head may not have been run. NO-OP on prod (we never
    # call this with a postgres DATABASE_URL).
    if "sqlite" in db_url:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        async with session.begin():
            # Idempotent — if the user already exists, blow it away and
            # re-seed (tests rely on a known-shape fixture).
            existing = await session.execute(select(User).where(User.email == email))
            old = existing.scalar_one_or_none()
            if old:
                # Light cleanup so the rest of the seed can re-create
                await session.delete(old)
                await session.flush()

            # Need a company + campaign for FK targets
            company_email = "uat-task85-co@pointcapitalis.com"
            existing_co = await session.execute(select(Company).where(Company.email == company_email))
            company = existing_co.scalar_one_or_none()
            if not company:
                company = Company(
                    email=company_email,
                    password_hash="seeded",
                    name="UAT Cleanup Co",
                    balance_cents=0,
                )
                session.add(company)
                await session.flush()

            existing_camp = await session.execute(
                select(Campaign).where(Campaign.title == "UAT cleanup fixture")
            )
            campaign = existing_camp.scalar_one_or_none()
            if not campaign:
                _now = datetime.now(timezone.utc)
                campaign = Campaign(
                    title="UAT cleanup fixture",
                    company_id=company.id,
                    brief="Seed fixture for /uat-task 85",
                    budget_total=10000,
                    budget_remaining=10000,
                    payout_rules={"rate_per_1k_views_cents": 200},
                    targeting={
                        "niche_tags": ["test"],
                        "required_platforms": ["linkedin"],
                        "target_regions": [],
                    },
                    status="active",
                    campaign_type="ai_generated",
                    start_date=_now,
                    end_date=_now,
                )
                session.add(campaign)
                await session.flush()

            user = User(
                email=email,
                password_hash="seeded",
                audience_region="US",
                tos_accepted_at=datetime.now(timezone.utc),
            )
            session.add(user)
            await session.flush()

            assignment = CampaignAssignment(
                user_id=user.id,
                campaign_id=campaign.id,
                status="accepted",
            )
            session.add(assignment)
            await session.flush()

            post = Post(
                assignment_id=assignment.id,
                platform="linkedin",
                post_url=f"https://linkedin.com/uat/{user.id}",
                content_hash=f"uat-hash-{user.id}",
                posted_at=datetime.now(timezone.utc),
                status="posted",
            )
            session.add(post)
            await session.flush()

            _ts = datetime.now(timezone.utc)
            session.add(Metric(post_id=post.id, impressions=10, likes=1, comments=0, reposts=0, clicks=0, scraped_at=_ts))
            session.add(Metric(post_id=post.id, impressions=20, likes=2, comments=1, reposts=0, clicks=0, scraped_at=_ts))
            session.add(Payout(
                user_id=user.id,
                amount_cents=1000,
                status="pending",
                period_start=_now,
                period_end=_now,
            ))
            session.add(Penalty(user_id=user.id, amount_cents=100, reason="seed"))
            session.add(AgentStatus(user_id=user.id, paused=False, platform_health={}))
            session.add(AgentCommand(user_id=user.id, type="ping", payload={}, status="done"))
            session.add(Draft(
                user_id=user.id,
                campaign_id=campaign.id,
                platform="linkedin",
                text="seed",
                status="pending",
            ))
            session.add(CampaignInvitationLog(
                user_id=user.id,
                campaign_id=campaign.id,
                event="invited",
            ))

        await engine.dispose()
        print(f"seeded user_id={user.id} email={email}")
        return user.id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    asyncio.run(seed(args.email))


if __name__ == "__main__":
    main()
