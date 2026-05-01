"""UAT helper: seed company fixtures for Task #74.2 UAT (company dashboard sweep).

Usage:
    python scripts/uat/seed_company_fixtures.py \\
      --email uat-co-existing@uat.local \\
      --password uat-pass-existing \\
      --balance-cents 20000 \\
      --with-active-campaign true \\
      --output data/uat/company_fixture.json

Safety: refuses unless --email starts with "uat-".
Idempotent: run twice → same company / campaign, no duplicates.

If --with-active-campaign true, creates ONE campaign that meets the quality gate
threshold (>=85 score). Status is set to 'active' directly in DB — the quality
gate is intentionally bypassed so the fixture is deterministic. Campaign values
are chosen to match high-quality defaults established by seed_campaign.py.

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

_UAT_TAG_PREFIX = "uat-"
_CAMPAIGN_UAT_TAG = "uat-company-fixture"


def _check_uat_prefix(email: str, flag: str) -> None:
    if not email.startswith(_UAT_TAG_PREFIX):
        print(
            f"Safety violation: {flag}={email!r} does not start with 'uat-'. "
            "Refusing to modify non-UAT data.",
            file=sys.stderr,
        )
        sys.exit(1)


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


async def seed(
    *,
    db_url: str,
    email: str,
    password: str,
    balance_cents: int,
    with_active_campaign: bool,
) -> dict:
    from sqlalchemy import select
    from app.models.company import Company
    from app.models.campaign import Campaign
    from app.core.security import hash_password

    engine, session_factory = await _get_session(db_url)
    await _ensure_schema(engine)

    now = datetime.now(timezone.utc)
    result: dict = {"company_id": None, "campaign_id": None}

    async with session_factory() as db:
        # ── Company ─────────────────────────────────────────────────────────
        row = await db.execute(select(Company).where(Company.email == email))
        company = row.scalar_one_or_none()
        if company is None:
            company = Company(
                name=f"UAT Company ({email})",
                email=email,
                password_hash=hash_password(password),
                balance_cents=balance_cents,
                balance=balance_cents / 100.0,
                status="active",
                tos_accepted_at=now,
            )
            db.add(company)
            await db.flush()
            print(f"Created company: id={company.id}, email={company.email}")
        else:
            company.balance_cents = balance_cents
            company.balance = balance_cents / 100.0
            company.status = "active"
            company.tos_accepted_at = company.tos_accepted_at or now
            # Update password in case it changed
            company.password_hash = hash_password(password)
            await db.flush()
            print(f"Company already exists: id={company.id} — updated balance + password")

        result["company_id"] = company.id

        # ── Active campaign (optional) ───────────────────────────────────────
        if with_active_campaign:
            # Find existing UAT campaign for this company
            row = await db.execute(
                select(Campaign).where(
                    Campaign.company_id == company.id,
                    Campaign.title.like("UAT-742%"),
                )
            )
            campaign = row.scalar_one_or_none()

            brief = (
                "UAT-742 Bamboo Desk Organizer is a premium workspace accessory "
                "designed for remote workers and productivity enthusiasts. "
                "Made from sustainably sourced bamboo, it features 8 compartments "
                "for pens, cables, and desk essentials. The organizer ships flat-packed "
                "and assembles in under 5 minutes. Perfect for home office setups. "
                "Available in natural and dark bamboo. Loved by 10,000+ remote workers."
            )  # 300+ chars, satisfies quality gate rubric

            guidance = (
                "Share your honest experience using the organizer daily. "
                "Mention the bamboo quality and how it reduced clutter. "
                "Include a photo of your desk setup if possible."
            )  # 80+ chars

            if campaign is None:
                campaign = Campaign(
                    company_id=company.id,
                    title="UAT-742 Bamboo Desk Organizer",
                    brief=brief,
                    content_guidance=guidance,
                    assets={"company_urls": ["https://example.com"]},
                    budget_total=50.0,
                    budget_remaining=50.0,
                    payout_rules={
                        "rate_per_1k_impressions": 0.50,
                        "rate_per_like": 0.01,
                        "rate_per_comment": 0.02,
                        "rate_per_repost": 0.05,
                        "rate_per_click": 0.0,
                        # Cents equivalents (billing.py uses these)
                        "rate_per_1k_views_cents": 200,
                        "rate_per_like_cents": 2,
                        "rate_per_comment_cents": 5,
                        "rate_per_repost_cents": 10,
                    },
                    targeting={
                        "niche_tags": ["productivity", "work-from-home"],
                        "required_platforms": ["linkedin", "reddit"],
                        "target_regions": [],
                        "min_followers": {},
                        "min_engagement": 0.0,
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
                print(f"Created campaign: id={campaign.id}, title={campaign.title!r}")
            else:
                campaign.status = "active"
                campaign.brief = brief
                campaign.content_guidance = guidance
                await db.flush()
                print(f"Campaign already exists: id={campaign.id} — set to active")

            result["campaign_id"] = campaign.id

        await db.commit()

    await engine.dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed company fixtures for Task #74.2 UAT."
    )
    parser.add_argument("--email", required=True,
                        help="Company email (must start with 'uat-')")
    parser.add_argument("--password", required=True,
                        help="Company password")
    parser.add_argument("--balance-cents", type=int, default=0,
                        help="Company balance in cents")
    parser.add_argument("--with-active-campaign",
                        choices=["true", "false"], default="false",
                        help="If 'true', create one active high-quality campaign")
    parser.add_argument("--output", default="data/uat/company_fixture.json",
                        help="Path to write output JSON")
    parser.add_argument("--db-url", default=None,
                        help="Database URL (defaults to DATABASE_URL env var)")
    args = parser.parse_args()

    _check_uat_prefix(args.email, "--email")

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
        email=args.email,
        password=args.password,
        balance_cents=args.balance_cents,
        with_active_campaign=(args.with_active_campaign == "true"),
    ))

    out_path = _REPO_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fixtures, indent=2))

    print(json.dumps(fixtures, indent=2))
    print(f"\nFixtures written to {out_path}")


if __name__ == "__main__":
    main()
