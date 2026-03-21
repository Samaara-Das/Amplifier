"""Payment processing via Stripe Connect.

Companies top up balance via Stripe Checkout.
Users receive payouts via Stripe Connect Express.
"""

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User
from app.models.payout import Payout

logger = logging.getLogger(__name__)
settings = get_settings()

# Stripe is optional — only import if key is set
_stripe = None


def _get_stripe():
    global _stripe
    if _stripe is None:
        try:
            import stripe
            stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
            if stripe.api_key:
                _stripe = stripe
            else:
                logger.warning("STRIPE_SECRET_KEY not set — payments disabled")
        except ImportError:
            logger.warning("stripe package not installed — payments disabled")
    return _stripe


async def create_company_checkout(company_id: int, amount_cents: int, db: AsyncSession) -> str | None:
    """Create a Stripe Checkout session for company to top up balance.

    Returns the checkout URL or None if Stripe is not configured.
    """
    stripe = _get_stripe()
    if not stripe:
        return None

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Amplifier Balance Top-Up"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{os.getenv('SERVER_URL', 'http://localhost:8000')}/api/company/dashboard?payment=success",
            cancel_url=f"{os.getenv('SERVER_URL', 'http://localhost:8000')}/api/company/dashboard?payment=cancelled",
            metadata={"company_id": str(company_id)},
        )
        return session.url
    except Exception as e:
        logger.error("Failed to create checkout session: %s", e)
        return None


async def create_user_stripe_account(user_id: int, email: str) -> str | None:
    """Create a Stripe Connect Express account for a user.

    Returns the onboarding URL or None.
    """
    stripe = _get_stripe()
    if not stripe:
        return None

    try:
        account = stripe.Account.create(
            type="express",
            email=email,
            capabilities={"transfers": {"requested": True}},
            metadata={"user_id": str(user_id)},
        )

        # Create account link for onboarding
        link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=f"{os.getenv('SERVER_URL', 'http://localhost:8000')}/api/users/me",
            return_url=f"{os.getenv('SERVER_URL', 'http://localhost:8000')}/api/users/me",
            type="account_onboarding",
        )

        return {"account_id": account.id, "onboarding_url": link.url}
    except Exception as e:
        logger.error("Failed to create Stripe account: %s", e)
        return None


async def process_payout(user_id: int, amount: float, stripe_account_id: str, db: AsyncSession) -> bool:
    """Send a payout to a user via Stripe Connect."""
    stripe = _get_stripe()
    if not stripe:
        return False

    try:
        transfer = stripe.Transfer.create(
            amount=int(amount * 100),  # cents
            currency="usd",
            destination=stripe_account_id,
            metadata={"user_id": str(user_id)},
        )
        logger.info("Payout of $%.2f to user %d: %s", amount, user_id, transfer.id)
        return True
    except Exception as e:
        logger.error("Payout failed for user %d: %s", user_id, e)
        return False


async def run_payout_cycle(db: AsyncSession) -> dict:
    """Process pending payouts for all eligible users.

    Returns summary: {users_paid, total_paid, failures}
    """
    min_threshold = settings.min_payout_threshold

    # Get users with balance above threshold
    result = await db.execute(
        select(User).where(
            and_(
                User.earnings_balance >= min_threshold,
                User.status == "active",
            )
        )
    )
    users = result.scalars().all()

    users_paid = 0
    total_paid = 0.0
    failures = 0

    for user in users:
        amount = float(user.earnings_balance)
        # TODO: Get stripe_account_id from user profile (needs schema update)
        # For now, just create payout records marked as pending
        payout = Payout(
            user_id=user.id,
            campaign_id=0,  # Aggregate payout
            amount=amount,
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            status="pending",
            breakdown={"aggregate": True, "balance_at_time": amount},
        )
        db.add(payout)

        # Reset balance (will be moved to "processing" when Stripe is fully integrated)
        user.earnings_balance = 0.0
        users_paid += 1
        total_paid += amount

    await db.flush()

    logger.info("Payout cycle: %d users, $%.2f total, %d failures",
                users_paid, total_paid, failures)

    return {"users_paid": users_paid, "total_paid": total_paid, "failures": failures}
