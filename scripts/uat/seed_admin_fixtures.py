"""UAT helper: seed admin dashboard fixtures for Task #74.3 UAT.

Usage:
    python scripts/uat/seed_admin_fixtures.py \\
      --users 3 \\
      --companies 2 \\
      --campaigns 3 \\
      --pending-payouts 1 \\
      --available-payouts 1 \\
      --fraud-penalty-with-appeal 1 \\
      --review-queue-caution-campaign 1 \\
      --output data/uat/admin_fixtures.json

Idempotent: keyed by email pattern uat-744-user-<n>@uat.local etc.
Run twice → same rows, same IDs (no duplicates).

Safety: all emails hard-coded to uat-744-* prefix. Refuses to run if
DATABASE_URL is not set (to prevent accidental prod writes).

Spec note: The spec says fraud penalties have appeal_status='pending'.
The actual Penalty model uses `appealed: bool` + `appeal_result: str | None`.
We map "pending appeal" to `appealed=True, appeal_result=None`.

Spec note: AdminReviewQueue has no 'verdict' column — the table only ever
contains caution-verdict campaigns (implicit). We seed with a concerns_json
string and leave resolved_at=None.

DB target: DATABASE_URL env var OR --db-url. No fallback to server/.env.
    export DATABASE_URL=sqlite+aiosqlite:///./data/uat/test_seed.db
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SERVER_DIR = _REPO_ROOT / "server"
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

_UAT_PREFIX = "uat-744-"
_UAT_TAG = "uat-744-admin-fixture"


def _user_email(n: int) -> str:
    return f"{_UAT_PREFIX}user-{n}@uat.local"


def _company_email(n: int) -> str:
    return f"{_UAT_PREFIX}company-{n}@uat.local"


async def _get_session(db_url: str):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import StaticPool, NullPool

    kwargs: dict = {"echo": False}
    if db_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = StaticPool
    else:
        kwargs["poolclass"] = NullPool

    engine = create_async_engine(db_url, **kwargs)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


async def _ensure_schema(engine) -> None:
    import app.models  # noqa — populates Base.metadata
    from app.core.database import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _upsert_user(db, email: str, pw_hash: str, now: datetime):
    from sqlalchemy import select
    from app.models.user import User

    row = await db.execute(select(User).where(User.email == email))
    user = row.scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            password_hash=pw_hash,
            status="active",
            tos_accepted_at=now,
            audience_region="US",
            mode="semi_auto",
            tier="seedling",
            trust_score=65,
        )
        db.add(user)
        await db.flush()
        print(f"  Created user: id={user.id}, email={user.email}")
    else:
        print(f"  User exists: id={user.id}, email={user.email}")
    return user


async def _upsert_company(db, email: str, pw_hash: str, now: datetime):
    from sqlalchemy import select
    from app.models.company import Company

    row = await db.execute(select(Company).where(Company.email == email))
    company = row.scalar_one_or_none()
    if company is None:
        company = Company(
            name=f"UAT Admin Company ({email})",
            email=email,
            password_hash=pw_hash,
            balance_cents=50_000,
            balance=500.0,
            status="active",
            tos_accepted_at=now,
        )
        db.add(company)
        await db.flush()
        print(f"  Created company: id={company.id}, email={company.email}")
    else:
        print(f"  Company exists: id={company.id}, email={company.email}")
    return company


async def _upsert_campaign(db, company_id: int, n: int, now: datetime):
    from sqlalchemy import select
    from app.models.campaign import Campaign

    title = f"UAT-744 Admin Campaign {n}"
    row = await db.execute(
        select(Campaign).where(
            Campaign.company_id == company_id,
            Campaign.title == title,
        )
    )
    campaign = row.scalar_one_or_none()
    if campaign is None:
        brief = (
            f"UAT-744 Admin Fixture Campaign {n}. "
            "A productivity tool for distributed teams. "
            "Helps remote workers organize their workspace and increase focus time. "
            "Backed by science-based habit formation methods. "
            "Trusted by 5000+ users across 30 countries. "
            "Eco-friendly materials, carbon-neutral shipping."
        )
        campaign = Campaign(
            company_id=company_id,
            title=title,
            brief=brief,
            content_guidance="Mention how you use it daily. Be authentic and specific.",
            assets={},
            budget_total=50.0,
            budget_remaining=50.0,
            payout_rules={
                "rate_per_1k_impressions": 0.50,
                "rate_per_like": 0.01,
                "rate_per_repost": 0.05,
            },
            targeting={
                "niche_tags": ["productivity", "work-from-home"],
                "required_platforms": ["linkedin", "reddit"],
                "target_regions": [],
                "min_followers": {},
            },
            campaign_goal="brand_awareness",
            campaign_type="ai_generated",
            tone="casual",
            preferred_formats={},
            status="active",
            screening_status="approved",
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=29),
        )
        db.add(campaign)
        await db.flush()
        print(f"  Created campaign: id={campaign.id}, title={campaign.title!r}")
    else:
        print(f"  Campaign exists: id={campaign.id}, title={campaign.title!r}")
    return campaign


async def seed(
    *,
    db_url: str,
    n_users: int,
    n_companies: int,
    n_campaigns: int,
    n_pending_payouts: int,
    n_available_payouts: int,
    n_fraud_penalties: int,
    n_review_queue_campaigns: int,
) -> dict:
    from app.core.security import hash_password
    from app.models.payout import Payout
    from app.models.penalty import Penalty
    from app.models.admin_review_queue import AdminReviewQueue
    from sqlalchemy import select

    engine, session_factory = await _get_session(db_url)
    await _ensure_schema(engine)

    now = datetime.now(timezone.utc)
    pw_hash = hash_password("uat-pass-744")

    result: dict = {
        "user_ids": [],
        "company_ids": [],
        "campaign_ids": [],
        "pending_payout_ids": [],
        "available_payout_ids": [],
        "penalty_ids": [],
        "review_queue_ids": [],
    }

    async with session_factory() as db:
        # ── Users ───────────────────────────────────────────────────────────
        print(f"Seeding {n_users} user(s)...")
        users = []
        for i in range(n_users):
            u = await _upsert_user(db, _user_email(i), pw_hash, now)
            users.append(u)
            result["user_ids"].append(u.id)

        # ── Companies ───────────────────────────────────────────────────────
        print(f"Seeding {n_companies} company(ies)...")
        companies = []
        for i in range(n_companies):
            c = await _upsert_company(db, _company_email(i), pw_hash, now)
            companies.append(c)
            result["company_ids"].append(c.id)

        # ── Campaigns ───────────────────────────────────────────────────────
        print(f"Seeding {n_campaigns} campaign(s)...")
        # Distribute campaigns across companies (round-robin)
        campaigns = []
        for i in range(n_campaigns):
            company = companies[i % len(companies)] if companies else None
            if company is None:
                print("  Warning: no companies seeded — skipping campaign seed", file=sys.stderr)
                break
            c = await _upsert_campaign(db, company.id, i, now)
            campaigns.append(c)
            result["campaign_ids"].append(c.id)

        # ── Pending payouts (immediately promotable: available_at = NOW()-1min) ──
        # Attach to first user; idempotent via uat_tag lookup
        target_user = users[0] if users else None

        if target_user and n_pending_payouts > 0:
            print(f"Seeding {n_pending_payouts} pending payout(s) for user id={target_user.id}...")
            # Purge stale
            existing = await db.execute(
                select(Payout).where(Payout.user_id == target_user.id)
            )
            for p in existing.scalars().all():
                if (isinstance(p.breakdown, dict)
                        and p.breakdown.get("uat_tag") == _UAT_TAG
                        and p.status == "pending"):
                    await db.delete(p)
            await db.flush()

            for i in range(n_pending_payouts):
                campaign_id = campaigns[i % len(campaigns)].id if campaigns else None
                payout = Payout(
                    user_id=target_user.id,
                    campaign_id=campaign_id,
                    amount_cents=1000 + i * 100,
                    amount=(1000 + i * 100) / 100.0,
                    period_start=now - timedelta(days=8),
                    period_end=now - timedelta(days=1),
                    status="pending",
                    # available_at set to NOW()-1min so it's immediately promotable
                    available_at=now - timedelta(minutes=1),
                    breakdown={
                        "uat_tag": _UAT_TAG,
                        "note": f"seeded pending payout #{i}",
                        "post_id": None,
                    },
                )
                db.add(payout)
                await db.flush()
                result["pending_payout_ids"].append(payout.id)
                print(f"  Created pending payout: id={payout.id}, cents={payout.amount_cents}")

        # ── Available payouts ────────────────────────────────────────────────
        if target_user and n_available_payouts > 0:
            print(f"Seeding {n_available_payouts} available payout(s)...")
            # Purge stale
            existing = await db.execute(
                select(Payout).where(Payout.user_id == target_user.id)
            )
            for p in existing.scalars().all():
                if (isinstance(p.breakdown, dict)
                        and p.breakdown.get("uat_tag") == _UAT_TAG
                        and p.status == "available"):
                    await db.delete(p)
            await db.flush()

            for i in range(n_available_payouts):
                campaign_id = campaigns[i % len(campaigns)].id if campaigns else None
                payout = Payout(
                    user_id=target_user.id,
                    campaign_id=campaign_id,
                    amount_cents=1500 + i * 100,
                    amount=(1500 + i * 100) / 100.0,
                    period_start=now - timedelta(days=14),
                    period_end=now - timedelta(days=7),
                    status="available",
                    available_at=now - timedelta(days=7),
                    breakdown={
                        "uat_tag": _UAT_TAG,
                        "note": f"seeded available payout #{i}",
                        "post_id": None,
                    },
                )
                db.add(payout)
                await db.flush()
                result["available_payout_ids"].append(payout.id)
                print(f"  Created available payout: id={payout.id}, cents={payout.amount_cents}")

        # ── Fraud penalties with pending appeal ──────────────────────────────
        # Spec says appeal_status='pending'. Actual model: appealed=True, appeal_result=None.
        if target_user and n_fraud_penalties > 0:
            print(f"Seeding {n_fraud_penalties} fraud penalty(ies) with pending appeal...")
            # Purge stale (identify by description tag)
            existing = await db.execute(
                select(Penalty).where(Penalty.user_id == target_user.id)
            )
            for pen in existing.scalars().all():
                if pen.description and _UAT_TAG in pen.description:
                    await db.delete(pen)
            await db.flush()

            for i in range(n_fraud_penalties):
                penalty = Penalty(
                    user_id=target_user.id,
                    post_id=None,
                    reason="fake_metrics",
                    amount=5.0,
                    amount_cents=500,
                    description=f"{_UAT_TAG}: seeded penalty #{i} with pending appeal",
                    # appealed=True + appeal_result=None = "appeal pending"
                    appealed=True,
                    appeal_result=None,
                )
                db.add(penalty)
                await db.flush()
                result["penalty_ids"].append(penalty.id)
                print(f"  Created penalty: id={penalty.id}, appealed=True, appeal_result=None")

        # ── Review queue campaigns (caution verdict) ─────────────────────────
        # AdminReviewQueue has no 'verdict' column — all rows are implicit 'caution'.
        if n_review_queue_campaigns > 0:
            print(f"Seeding {n_review_queue_campaigns} review queue campaign(s)...")
            # Purge stale (identify by concerns_json tag)
            from sqlalchemy import select as sel_
            existing = await db.execute(sel_(AdminReviewQueue))
            for rq in existing.scalars().all():
                if _UAT_TAG in rq.concerns_json:
                    await db.delete(rq)
            await db.flush()

            for i in range(n_review_queue_campaigns):
                # Use a campaign from the seeded set, or create a fresh one
                if i < len(campaigns):
                    campaign_id = campaigns[i].id
                else:
                    # Need extra campaigns beyond what was seeded — create minimally
                    company = companies[0] if companies else None
                    if company is None:
                        print("  Warning: no company to attach review queue campaign — skipping", file=sys.stderr)
                        continue
                    extra = await _upsert_campaign(db, company.id, 1000 + i, now)
                    campaign_id = extra.id

                rq = AdminReviewQueue(
                    campaign_id=campaign_id,
                    concerns_json=json.dumps([
                        f"{_UAT_TAG}: seeded caution verdict #{i}",
                        "Brand safety: mentions competitor product names",
                    ]),
                    resolved_at=None,
                    resolved_by=None,
                )
                db.add(rq)
                await db.flush()
                result["review_queue_ids"].append(rq.id)
                print(f"  Created review queue entry: id={rq.id}, campaign_id={campaign_id}")

        await db.commit()

    await engine.dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed admin dashboard fixtures for Task #74.3 UAT."
    )
    parser.add_argument("--users", type=int, default=3,
                        help="Number of users to seed (keyed by uat-744-user-<n>@uat.local)")
    parser.add_argument("--companies", type=int, default=2,
                        help="Number of companies to seed")
    parser.add_argument("--campaigns", type=int, default=3,
                        help="Number of campaigns to seed")
    parser.add_argument("--pending-payouts", type=int, default=1,
                        help="Number of pending payouts (immediately promotable)")
    parser.add_argument("--available-payouts", type=int, default=1,
                        help="Number of available payouts (past hold)")
    parser.add_argument("--fraud-penalty-with-appeal", type=int, default=1,
                        help="Number of fraud penalties with pending appeal")
    parser.add_argument("--review-queue-caution-campaign", type=int, default=1,
                        help="Number of campaigns in admin_review_queue with caution verdict")
    parser.add_argument("--output", default="data/uat/admin_fixtures.json",
                        help="Path to write output JSON")
    parser.add_argument("--db-url", default=None,
                        help="Database URL (defaults to DATABASE_URL env var)")
    args = parser.parse_args()

    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        print(
            "Error: DATABASE_URL env var not set. Set it explicitly to avoid writing to prod:\n"
            "  export DATABASE_URL=sqlite+aiosqlite:///./data/uat/test_seed.db",
            file=sys.stderr,
        )
        sys.exit(1)

    fixtures = asyncio.run(seed(
        db_url=db_url,
        n_users=args.users,
        n_companies=args.companies,
        n_campaigns=args.campaigns,
        n_pending_payouts=args.pending_payouts,
        n_available_payouts=args.available_payouts,
        n_fraud_penalties=args.fraud_penalty_with_appeal,
        n_review_queue_campaigns=args.review_queue_caution_campaign,
    ))

    out_path = _REPO_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fixtures, indent=2))

    print(json.dumps(fixtures, indent=2))
    print(f"\nFixtures written to {out_path}")


if __name__ == "__main__":
    main()
