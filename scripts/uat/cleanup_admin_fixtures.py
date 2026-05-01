"""UAT helper: delete admin fixtures created by seed_admin_fixtures.py.

Usage:
    python scripts/uat/cleanup_admin_fixtures.py \\
      --input data/uat/admin_fixtures.json

Deletes exactly the rows captured in the fixture JSON — no broader blasts.

Safety: reads IDs from the fixture file and deletes only those rows.
DB target: DATABASE_URL env var OR --db-url.
    export DATABASE_URL=sqlite+aiosqlite:///./data/uat/test_seed.db
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SERVER_DIR = _REPO_ROOT / "server"
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))


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


async def cleanup(db_url: str, fixtures: dict) -> None:
    import app.models  # noqa
    from sqlalchemy import select
    from app.models.user import User
    from app.models.company import Company
    from app.models.campaign import Campaign
    from app.models.payout import Payout
    from app.models.penalty import Penalty
    from app.models.admin_review_queue import AdminReviewQueue

    engine, session_factory = await _get_session(db_url)

    async with session_factory() as db:
        # Delete in FK-safe order: payouts/penalties/review_queue → campaigns → users/companies

        for payout_id in fixtures.get("pending_payout_ids", []) + fixtures.get("available_payout_ids", []):
            row = await db.execute(select(Payout).where(Payout.id == payout_id))
            obj = row.scalar_one_or_none()
            if obj:
                await db.delete(obj)
                print(f"  Deleted Payout id={payout_id}")
            else:
                print(f"  Payout id={payout_id} not found (already deleted?)")

        for penalty_id in fixtures.get("penalty_ids", []):
            row = await db.execute(select(Penalty).where(Penalty.id == penalty_id))
            obj = row.scalar_one_or_none()
            if obj:
                await db.delete(obj)
                print(f"  Deleted Penalty id={penalty_id}")
            else:
                print(f"  Penalty id={penalty_id} not found (already deleted?)")

        for rq_id in fixtures.get("review_queue_ids", []):
            row = await db.execute(select(AdminReviewQueue).where(AdminReviewQueue.id == rq_id))
            obj = row.scalar_one_or_none()
            if obj:
                await db.delete(obj)
                print(f"  Deleted AdminReviewQueue id={rq_id}")
            else:
                print(f"  AdminReviewQueue id={rq_id} not found (already deleted?)")

        await db.flush()

        for campaign_id in fixtures.get("campaign_ids", []):
            row = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
            obj = row.scalar_one_or_none()
            if obj:
                await db.delete(obj)
                print(f"  Deleted Campaign id={campaign_id}")
            else:
                print(f"  Campaign id={campaign_id} not found (already deleted?)")

        await db.flush()

        for user_id in fixtures.get("user_ids", []):
            row = await db.execute(select(User).where(User.id == user_id))
            obj = row.scalar_one_or_none()
            if obj:
                await db.delete(obj)
                print(f"  Deleted User id={user_id}")
            else:
                print(f"  User id={user_id} not found (already deleted?)")

        for company_id in fixtures.get("company_ids", []):
            row = await db.execute(select(Company).where(Company.id == company_id))
            obj = row.scalar_one_or_none()
            if obj:
                await db.delete(obj)
                print(f"  Deleted Company id={company_id}")
            else:
                print(f"  Company id={company_id} not found (already deleted?)")

        await db.commit()

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete admin fixtures created by seed_admin_fixtures.py."
    )
    parser.add_argument("--input", default="data/uat/admin_fixtures.json",
                        help="Path to fixture JSON written by seed_admin_fixtures.py")
    parser.add_argument("--db-url", default=None,
                        help="Database URL (defaults to DATABASE_URL env var)")
    args = parser.parse_args()

    input_path = _REPO_ROOT / args.input
    if not input_path.exists():
        print(f"Error: fixture file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    fixtures = json.loads(input_path.read_text())

    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        print(
            "Error: DATABASE_URL env var not set. Set it explicitly to avoid writing to prod:\n"
            "  export DATABASE_URL=sqlite+aiosqlite:///./data/uat/test_seed.db",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Cleaning up fixtures from: {input_path}")
    asyncio.run(cleanup(db_url, fixtures))
    print("Cleanup complete.")


if __name__ == "__main__":
    main()
