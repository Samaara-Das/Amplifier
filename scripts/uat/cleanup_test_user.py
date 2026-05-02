"""UAT cleanup helper — delete a test user and all associated rows.

Usage:
    python scripts/uat/cleanup_test_user.py --email uat-task75-user@pointcapitalis.com

Safety guard:
    Only deletes emails matching uat-task\\d+.*@pointcapitalis\\.com
    Set DATABASE_URL env var to point at the target database.
    For production UAT: export DATABASE_URL=<supabase-pooler-url> before running.
"""

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

# Make server/ importable
_SERVER_DIR = Path(__file__).resolve().parent.parent.parent / "server"
sys.path.insert(0, str(_SERVER_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./amplifier.db")
os.environ.setdefault("JWT_SECRET_KEY", "change-me-to-a-random-secret")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.pool import NullPool

# Import models
from app.models.user import User
from app.models.assignment import CampaignAssignment
from app.models.post import Post
from app.models.metric import Metric
from app.models.payout import Payout
from app.models.penalty import Penalty
from app.models.agent_status import AgentStatus
from app.models.agent_command import AgentCommand
from app.models.draft import Draft

_ALLOWED_PATTERN = re.compile(r"^uat-task\d+.*@pointcapitalis\.com$")


async def cleanup(email: str) -> None:
    if not _ALLOWED_PATTERN.match(email):
        print(f"ERROR: '{email}' does not match uat-task<n>*@pointcapitalis.com — refusing to delete.")
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./amplifier.db")

    # NullPool avoids pgbouncer prepared-statement cache issues on Supabase
    engine = create_async_engine(
        db_url,
        poolclass=NullPool,
        connect_args={"prepared_statement_cache_size": 0} if "postgresql" in db_url else {},
    )

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        async with session.begin():
            # Look up user
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                print(f"No user found with email '{email}' — nothing to delete.")
                await engine.dispose()
                return

            user_id = user.id
            print(f"Found user id={user_id} email={email}")

            counts = {}

            # Cascade: Metric -> Post -> CampaignAssignment
            # We need post_ids first, then assignment_ids
            assign_result = await session.execute(
                select(CampaignAssignment.id).where(CampaignAssignment.user_id == user_id)
            )
            assignment_ids = [r[0] for r in assign_result.fetchall()]

            if assignment_ids:
                post_result = await session.execute(
                    select(Post.id).where(Post.assignment_id.in_(assignment_ids))
                )
                post_ids = [r[0] for r in post_result.fetchall()]

                if post_ids:
                    r = await session.execute(delete(Metric).where(Metric.post_id.in_(post_ids)))
                    counts["metrics"] = r.rowcount

                    r = await session.execute(delete(Post).where(Post.id.in_(post_ids)))
                    counts["posts"] = r.rowcount

                r = await session.execute(
                    delete(CampaignAssignment).where(CampaignAssignment.id.in_(assignment_ids))
                )
                counts["campaign_assignments"] = r.rowcount

            # Payout
            r = await session.execute(delete(Payout).where(Payout.user_id == user_id))
            counts["payouts"] = r.rowcount

            # Penalty
            r = await session.execute(delete(Penalty).where(Penalty.user_id == user_id))
            counts["penalties"] = r.rowcount

            # AgentStatus (PK is user_id)
            r = await session.execute(delete(AgentStatus).where(AgentStatus.user_id == user_id))
            counts["agent_status"] = r.rowcount

            # AgentCommand
            r = await session.execute(delete(AgentCommand).where(AgentCommand.user_id == user_id))
            counts["agent_commands"] = r.rowcount

            # Draft
            r = await session.execute(delete(Draft).where(Draft.user_id == user_id))
            counts["drafts"] = r.rowcount

            # Finally delete the user
            await session.delete(user)
            counts["users"] = 1

    await engine.dispose()

    print(f"\nDeleted rows:")
    for table, count in counts.items():
        if count:
            print(f"  {table}: {count}")
    print(f"\nUser '{email}' successfully removed.")


def main():
    parser = argparse.ArgumentParser(description="Delete a UAT test user and all associated data.")
    parser.add_argument("--email", required=True, help="Email of the test user to delete")
    args = parser.parse_args()
    asyncio.run(cleanup(args.email))


if __name__ == "__main__":
    main()
