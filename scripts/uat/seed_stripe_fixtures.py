"""UAT helper: seed Stripe-related user/company fixtures for Task #74 UAT.

Usage:
    python scripts/uat/seed_stripe_fixtures.py \\
      --user-email uat-user-74@uat.local \\
      --user-available-balance-cents 1500 \\
      --user-pending-balance-cents 800 \\
      --output data/uat/stripe_fixtures.json

    # Optional — add company and Stripe account ID:
    python scripts/uat/seed_stripe_fixtures.py \\
      --company-email uat-co-74@uat.local \\
      --user-email uat-user-74@uat.local \\
      --user-available-balance-cents 1500 \\
      --user-pending-balance-cents 800 \\
      --user-stripe-account-id acct_test_123 \\
      --output data/uat/stripe_fixtures.json

Safety: refuses unless --user-email / --company-email contain "uat-".
Idempotent: run twice → same user + company, same payout rows (tagged for cleanup).

DB target: DATABASE_URL env var OR --db-url. No automatic fallback to server/.env
(that would write to prod). Export DATABASE_URL explicitly for local runs:
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

_DEFAULT_DB = "sqlite+aiosqlite:///./amplifier.db"

_UAT_TAG_STRIPE = "uat-stripe-fixture"
_UAT_TAG_PREFIX = "uat-"


def _check_uat_prefix(email: str, flag: str) -> None:
    if email and not email.startswith(_UAT_TAG_PREFIX):
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
    company_email: str | None,
    user_email: str | None,
    user_available_cents: int,
    user_pending_cents: int,
    user_stripe_account_id: str | None,
) -> dict:
    from sqlalchemy import select
    from app.models.company import Company
    from app.models.user import User
    from app.models.payout import Payout
    from app.core.security import hash_password

    engine, session_factory = await _get_session(db_url)
    await _ensure_schema(engine)

    now = datetime.now(timezone.utc)
    result: dict = {
        "company_id": None,
        "user_id": None,
        "available_payout_ids": [],
        "pending_payout_ids": [],
    }

    async with session_factory() as db:
        # ── Company (optional) ──────────────────────────────────────────────
        if company_email:
            row = await db.execute(select(Company).where(Company.email == company_email))
            company = row.scalar_one_or_none()
            if company is None:
                company = Company(
                    name=f"UAT Company ({company_email})",
                    email=company_email,
                    password_hash=hash_password("uat-pass-74"),
                    balance_cents=0,
                    balance=0.0,
                    status="active",
                    tos_accepted_at=now,
                )
                db.add(company)
                await db.flush()
                print(f"Created company: id={company.id}, email={company.email}")
            else:
                company.status = "active"
                company.tos_accepted_at = company.tos_accepted_at or now
                await db.flush()
                print(f"Company already exists: id={company.id}, email={company.email} — updated")
            result["company_id"] = company.id

        # ── User (optional) ─────────────────────────────────────────────────
        if user_email:
            row = await db.execute(select(User).where(User.email == user_email))
            user = row.scalar_one_or_none()
            if user is None:
                user = User(
                    email=user_email,
                    password_hash=hash_password("uat-pass-74"),
                    status="active",
                    tos_accepted_at=now,
                    audience_region="US",
                    mode="semi_auto",
                    tier="seedling",
                    trust_score=50,
                )
                db.add(user)
                await db.flush()
                print(f"Created user: id={user.id}, email={user.email}")
            else:
                print(f"User already exists: id={user.id}, email={user.email} — updating")
                await db.flush()

            # Apply stripe_account_id if given
            if user_stripe_account_id is not None:
                user.stripe_account_id = user_stripe_account_id
                print(f"  Set stripe_account_id={user_stripe_account_id}")

            # Update balance totals to match requested amounts
            user.earnings_balance_cents = user_available_cents
            user.earnings_balance = user_available_cents / 100.0

            await db.flush()
            result["user_id"] = user.id

            # ── Purge stale UAT payout rows (idempotency) ──────────────────
            from sqlalchemy import select as sel_
            existing = await db.execute(
                sel_(Payout).where(Payout.user_id == user.id)
            )
            existing_payouts = existing.scalars().all()
            stale = [
                p for p in existing_payouts
                if isinstance(p.breakdown, dict) and p.breakdown.get("uat_tag") == _UAT_TAG_STRIPE
            ]
            for p in stale:
                await db.delete(p)
            if stale:
                await db.flush()
                print(f"  Purged {len(stale)} stale UAT payout row(s)")

            # ── Available payouts (past hold period) ───────────────────────
            if user_available_cents > 0:
                avail_payout = Payout(
                    user_id=user.id,
                    campaign_id=None,
                    amount_cents=user_available_cents,
                    amount=user_available_cents / 100.0,
                    period_start=now - timedelta(days=14),
                    period_end=now - timedelta(days=7),
                    status="available",
                    available_at=now - timedelta(days=7),
                    breakdown={
                        "uat_tag": _UAT_TAG_STRIPE,
                        "note": "seeded available balance",
                    },
                )
                db.add(avail_payout)
                await db.flush()
                result["available_payout_ids"].append(avail_payout.id)
                print(f"  Created available payout: id={avail_payout.id}, cents={user_available_cents}")

            # ── Pending payouts (5 days in future — still in hold) ─────────
            if user_pending_cents > 0:
                pend_payout = Payout(
                    user_id=user.id,
                    campaign_id=None,
                    amount_cents=user_pending_cents,
                    amount=user_pending_cents / 100.0,
                    period_start=now - timedelta(days=2),
                    period_end=now,
                    status="pending",
                    available_at=now + timedelta(days=5),
                    breakdown={
                        "uat_tag": _UAT_TAG_STRIPE,
                        "note": "seeded pending balance",
                    },
                )
                db.add(pend_payout)
                await db.flush()
                result["pending_payout_ids"].append(pend_payout.id)
                print(f"  Created pending payout: id={pend_payout.id}, cents={user_pending_cents}")

        await db.commit()

    await engine.dispose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed Stripe/earnings UAT fixtures for Task #74."
    )
    parser.add_argument("--company-email", default=None,
                        help="Company email to create/update (must start with 'uat-')")
    parser.add_argument("--user-email", default=None,
                        help="User email to create/update (must start with 'uat-')")
    parser.add_argument("--user-available-balance-cents", type=int, default=0,
                        help="Seeded available (past-hold) balance in cents")
    parser.add_argument("--user-pending-balance-cents", type=int, default=0,
                        help="Seeded pending (in-hold) balance in cents")
    parser.add_argument("--user-stripe-account-id", default=None,
                        help="Set users.stripe_account_id to this value (leave unset to leave NULL)")
    parser.add_argument("--output", default="data/uat/stripe_fixtures.json",
                        help="Path to write output JSON")
    parser.add_argument("--db-url", default=None,
                        help="Database URL (defaults to DATABASE_URL env var)")
    args = parser.parse_args()

    # Safety checks
    if args.company_email:
        _check_uat_prefix(args.company_email, "--company-email")
    if args.user_email:
        _check_uat_prefix(args.user_email, "--user-email")
    if not args.company_email and not args.user_email:
        print("Error: at least one of --company-email or --user-email must be provided.", file=sys.stderr)
        sys.exit(1)

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
        company_email=args.company_email,
        user_email=args.user_email,
        user_available_cents=args.user_available_balance_cents,
        user_pending_cents=args.user_pending_balance_cents,
        user_stripe_account_id=args.user_stripe_account_id,
    ))

    out_path = _REPO_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fixtures, indent=2))

    print(json.dumps(fixtures, indent=2))
    print(f"\nFixtures written to {out_path}")


if __name__ == "__main__":
    main()
