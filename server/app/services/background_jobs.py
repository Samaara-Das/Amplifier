"""Background jobs — billing cycles, trust checks, scheduled tasks via ARQ."""

import logging
from arq import cron
from app.core.database import async_session
from app.services.billing import run_billing_cycle
from app.services.trust import run_trust_check

logger = logging.getLogger(__name__)


async def billing_cycle(ctx):
    """Run billing calculation for all posts with final metrics."""
    async with async_session() as db:
        try:
            result = await run_billing_cycle(db)
            await db.commit()
            logger.info("Billing cycle: %s", result)
        except Exception as e:
            await db.rollback()
            logger.error("Billing cycle failed: %s", e)


async def trust_check(ctx):
    """Run trust/fraud detection checks."""
    async with async_session() as db:
        try:
            result = await run_trust_check(db)
            await db.commit()
            logger.info("Trust check: %s", result)
        except Exception as e:
            await db.rollback()
            logger.error("Trust check failed: %s", e)


class WorkerSettings:
    """ARQ worker settings."""
    functions = [billing_cycle, trust_check]
    cron_jobs = [
        cron(billing_cycle, hour={0, 6, 12, 18}),   # Every 6 hours
        cron(trust_check, hour={3, 15}),              # Twice daily
    ]
    redis_settings = None  # Set from env at startup

    @staticmethod
    def on_startup(ctx):
        logger.info("Background worker started")

    @staticmethod
    def on_shutdown(ctx):
        logger.info("Background worker stopped")
